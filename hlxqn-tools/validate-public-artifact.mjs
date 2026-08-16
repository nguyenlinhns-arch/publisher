import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'..','_site');
const domain='https://hoclaixequangninh.vn';
const errors=[];
const warnings=[];
const redirectRoot=new Set(['huong-dan-hoc-lai-xe.html','lich-sat-hach-lai-xe.html']);

function walk(dir,list=[]){
  for(const entry of fs.readdirSync(dir,{withFileTypes:true})){
    const p=path.join(dir,entry.name);
    if(entry.isDirectory())walk(p,list);else list.push(p);
  }
  return list;
}
function count(haystack,needle){return haystack.split(needle).length-1;}
function localTarget(page,raw){
  const clean=raw.split('#')[0].split('?')[0];
  if(!clean||/^(?:https?:|tel:|mailto:|javascript:|data:)/i.test(clean))return null;
  if(clean.startsWith('/'))return path.join(root,clean.slice(1));
  return path.resolve(path.dirname(page),clean);
}
function existsResolved(p){
  if(!p)return true;
  if(fs.existsSync(p)&&fs.statSync(p).isFile())return true;
  if(fs.existsSync(p)&&fs.statSync(p).isDirectory()&&fs.existsSync(path.join(p,'index.html')))return true;
  if(!path.extname(p)&&fs.existsSync(`${p}.html`))return true;
  return false;
}

if(!fs.existsSync(root))throw new Error('_site does not exist');
const all=walk(root);
const htmlFiles=all.filter(p=>p.endsWith('.html'));

for(const page of htmlFiles){
  const rel=path.relative(root,page).replaceAll(path.sep,'/');
  const html=fs.readFileSync(page,'utf8');
  const isRootRedirect=!rel.includes('/')&&redirectRoot.has(rel);
  const robots=(html.match(/<meta\s+name=["']robots["']\s+content=["']([^"']+)/i)||[])[1]||'';
  const noindex=/noindex/i.test(robots);

  if(!/<title>[\s\S]+?<\/title>/i.test(html))errors.push(`${rel}: missing title`);
  if(!noindex&&!/<h1\b/i.test(html))errors.push(`${rel}: indexable page missing H1`);
  if(!noindex&&rel!=='404.html'&&!/<link\s+rel=["']canonical["']/i.test(html))errors.push(`${rel}: indexable page missing canonical`);
  const canonical=(html.match(/<link\s+rel=["']canonical["']\s+href=["']([^"']+)/i)||[])[1];
  if(canonical&&!canonical.startsWith(domain))errors.push(`${rel}: canonical outside domain`);

  if(!isRootRedirect){
    if(count(html,'class="official-header"')!==1)errors.push(`${rel}: expected exactly one official header`);
    if(count(html,'class="official-footer"')!==1)errors.push(`${rel}: expected exactly one official footer`);
  }
  if(/official-shell\.js/i.test(html))errors.push(`${rel}: runtime shell reference leaked`);
  if(/adsterra|effectivecpmnetwork|highperformanceformat/i.test(html))errors.push(`${rel}: Adsterra leaked`);

  for(const m of html.matchAll(/<(?:a|link)\b[^>]*href=["']([^"']+)["']/gi)){
    const raw=m[1];
    const target=localTarget(page,raw);
    if(target&&!existsResolved(target))errors.push(`${rel}: broken href ${raw}`);
  }
  for(const m of html.matchAll(/<(?:img|script)\b[^>]*src=["']([^"']+)["']/gi)){
    const raw=m[1];
    const target=localTarget(page,raw);
    if(target&&!existsResolved(target))errors.push(`${rel}: broken src ${raw}`);
  }
  for(const m of html.matchAll(/<img\b[^>]*>/gi)){
    const tag=m[0];
    if(!/\balt=["'][^"']*["']/i.test(tag))errors.push(`${rel}: image missing alt`);
    if(!/\b(?:width=["']\d+["']\s+height=["']\d+["']|height=["']\d+["']\s+width=["']\d+["'])/i.test(tag)&&!/loading=["']lazy["']/i.test(tag))warnings.push(`${rel}: non-lazy image without explicit width/height`);
  }
}

const mobile=fs.readFileSync(path.join(root,'assets/mobile-v2.css'),'utf8');
if(/@import[^;]+official-(?:site|pages)\.css/i.test(mobile))errors.push('mobile-v2.css: render-blocking institutional @import remains');
if(fs.existsSync(path.join(root,'assets/official-shell.js')))errors.push('official-shell.js should not be deployed');
const config=fs.readFileSync(path.join(root,'assets/site-config.js'),'utf8');
if(config.includes('official-shell.js'))errors.push('site-config still references official-shell.js');
if(!config.includes('if(isGooglePaidVisit())return'))errors.push('site-config does not block affiliate on Google paid traffic');
const productionText=all.filter(p=>/\.(?:html|js|css)$/i.test(p)).map(p=>fs.readFileSync(p,'utf8')).join('\n');
if(/adsterra|effectivecpmnetwork|highperformanceformat/i.test(productionText))errors.push('production artifact contains Adsterra');

const home=fs.readFileSync(path.join(root,'index.html'),'utf8');
if(!home.includes('<title>Học Lái Xe Quảng Ninh | B tự động, B cơ khí, C1, A1</title>'))errors.push('homepage optimized title missing');
if(!home.includes('Học lái xe Quảng Ninh: <em>chọn đúng khóa học</em>'))errors.push('homepage intent-led H1 missing');
if(!home.includes('<a class="primary" href="#dang-ky">Đăng ký tư vấn</a>'))errors.push('homepage registration CTA is not primary');
if(!home.includes('rel="preload" as="image" href="/assets/quang-hanh-san-sat-hach.jpg"'))errors.push('homepage LCP preload missing');
if(!/<img[^>]+quang-hanh-san-sat-hach\.jpg[^>]+fetchpriority=["']high["']/i.test(home))errors.push('homepage LCP image missing fetchpriority=high');

const pricing=fs.readFileSync(path.join(root,'hoc-phi-hoc-lai-xe-quang-ninh.html'),'utf8');
if(!pricing.includes('Nếu B tự động và B cơ khí cùng mức 20,9 triệu'))errors.push('pricing decision guidance missing');
if(!pricing.includes('"dateModified":"2026-08-16"'))errors.push('pricing dateModified not current');

const affiliate=fs.readFileSync(path.join(root,'uu-dai-hoc-vien.html'),'utf8');
if(!/noindex/i.test((affiliate.match(/<meta\s+name=["']robots["']\s+content=["']([^"']+)/i)||[])[1]||''))errors.push('affiliate utility page must be noindex');
if(!affiliate.includes('rel="sponsored nofollow noopener"'))errors.push('affiliate external link missing sponsored/nofollow/noopener');

const sitemap=fs.readFileSync(path.join(root,'sitemap.xml'),'utf8');
const urls=[...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1]);
if(new Set(urls).size!==urls.length)errors.push('sitemap contains duplicate URLs');
if(sitemap.includes('/uu-dai-hoc-vien.html'))errors.push('affiliate noindex page leaked into sitemap');
if(!sitemap.includes('<loc>https://hoclaixequangninh.vn/</loc><lastmod>2026-08-16</lastmod>'))errors.push('homepage sitemap lastmod not updated');
if(!sitemap.includes('<loc>https://hoclaixequangninh.vn/hoc-phi-hoc-lai-xe-quang-ninh.html</loc><lastmod>2026-08-16</lastmod>'))errors.push('pricing sitemap lastmod not updated');
for(const url of urls){
  let rel=url.replace(`${domain}/`,'');
  const target=rel===''?path.join(root,'index.html'):rel.endsWith('/')?path.join(root,rel,'index.html'):path.join(root,rel);
  if(!existsResolved(target))errors.push(`sitemap target missing: ${url}`);
}

console.log(JSON.stringify({htmlPages:htmlFiles.length,publicFiles:all.length,sitemapUrls:urls.length,errors,warnings:[...new Set(warnings)]},null,2));
if(errors.length)process.exit(1);
