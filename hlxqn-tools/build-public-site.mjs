import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'..');
const out=path.join(root,'_site');
fs.rmSync(out,{recursive:true,force:true});
fs.mkdirSync(out,{recursive:true});

function copyFile(rel){
  const src=path.join(root,rel);
  const dst=path.join(out,rel);
  if(!fs.existsSync(src)||!fs.statSync(src).isFile())throw new Error(`Missing public dependency: ${rel}`);
  fs.mkdirSync(path.dirname(dst),{recursive:true});
  fs.copyFileSync(src,dst);
}
function copyDir(rel){
  const src=path.join(root,rel);
  if(!fs.existsSync(src))return;
  fs.cpSync(src,path.join(out,rel),{recursive:true});
}
function assetRefs(content){
  const refs=new Set();
  const patterns=[
    /(?:src|href)=["']\/?(assets\/[^"'?#)]+)(?:[?#][^"']*)?["']/gi,
    /url\(\s*["']?\/?(assets\/[^"')?#]+)(?:[?#][^"')]+)?["']?\s*\)/gi,
    /["']\/?(assets\/[A-Za-z0-9_./-]+\.(?:css|js|svg|png|jpe?g|webp|gif|ico|mp3|woff2?|ttf))(?:\?[^"']*)?["']/gi
  ];
  for(const re of patterns){for(const m of content.matchAll(re))refs.add(m[1]);}
  return refs;
}
function replaceRequired(content,from,to,label){
  if(!content.includes(from))throw new Error(`Production transform anchor missing: ${label}`);
  return content.replace(from,to);
}

const rootFiles=fs.readdirSync(root).filter(name=>name.endsWith('.html'));
for(const file of rootFiles)copyFile(file);
for(const file of ['robots.txt','sitemap.xml','llms.txt','CNAME','favicon.svg','.nojekyll'])copyFile(file);
copyDir('lich-sat-hach');

const queue=[];
const seen=new Set();
function enqueueFrom(content){for(const ref of assetRefs(content)){if(!seen.has(ref)){seen.add(ref);queue.push(ref);}}}
for(const file of rootFiles)enqueueFrom(fs.readFileSync(path.join(root,file),'utf8'));
for(const rel of ['lich-sat-hach/index.html']){
  const p=path.join(root,rel);if(fs.existsSync(p))enqueueFrom(fs.readFileSync(p,'utf8'));
}

while(queue.length){
  const rel=queue.shift();
  if(!rel.startsWith('assets/'))throw new Error(`Unsafe dependency path: ${rel}`);
  copyFile(rel);
  if(/\.(?:css|js|svg)$/i.test(rel))enqueueFrom(fs.readFileSync(path.join(root,rel),'utf8'));
}

function optimizeHomepage(){
  const p=path.join(out,'index.html');
  let html=fs.readFileSync(p,'utf8');
  html=replaceRequired(html,
    '<h1>Thông tin rõ ràng để <em>chọn đúng khóa học</em> trước khi đăng ký</h1>',
    '<h1>Học lái xe Quảng Ninh: <em>chọn đúng khóa học</em> trước khi đăng ký</h1>',
    'homepage H1');
  html=replaceRequired(html,
    '<p class="institutional-hero-lead">Tra cứu hạng bằng, học phí, thời gian học, hồ sơ, DAT, khu vực đào tạo và lịch sát hạch. Đăng ký trực tuyến để được hướng dẫn theo đúng nhu cầu sử dụng xe.</p>',
    '<p class="institutional-hero-lead">Tra cứu B số tự động, B số cơ khí, C1, A1; học phí, hồ sơ, DAT, khu vực học và lịch sát hạch. Đăng ký tư vấn trực tuyến để được hướng dẫn theo nhu cầu sử dụng xe.</p>',
    'homepage hero lead');
  html=replaceRequired(html,
    '<div class="institutional-actions"><a class="primary" href="#khoa-hoc">Xem các khóa học</a><a class="secondary" href="#dang-ky">Đăng ký tư vấn</a></div>',
    '<div class="institutional-actions"><a class="primary" href="#dang-ky">Đăng ký tư vấn</a><a class="secondary" href="#khoa-hoc">Xem các khóa học</a></div>',
    'homepage hero CTA');
  fs.writeFileSync(p,html);
}

function enrichPricingPage(){
  const p=path.join(out,'hoc-phi-hoc-lai-xe-quang-ninh.html');
  let html=fs.readFileSync(p,'utf8');
  html=replaceRequired(html,'"dateModified":"2026-08-15"','"dateModified":"2026-08-16"','pricing dateModified');
  html=replaceRequired(html,'Cập nhật ngày 15/08/2026.','Cập nhật ngày 16/08/2026.','pricing visible update date');
  const anchor='</ol><div class="info-callout">';
  const section='</ol><h2>Nếu B tự động và B cơ khí cùng mức 20,9 triệu, chọn thế nào?</h2><p>Điểm khác biệt chính không nằm ở mức học phí đang thông tin mà ở loại xe bạn dự kiến sử dụng sau khi có giấy phép. B số tự động có thời gian dự kiến 42 ngày và phù hợp khi nhu cầu chủ yếu là xe số tự động. B số cơ khí có thời gian dự kiến 46 ngày và phù hợp hơn nếu gia đình hoặc công việc có thể cần xe số cơ khí.</p><p>Nếu chắc chắn chỉ sử dụng xe số tự động, B số tự động là lựa chọn gọn hơn. Nếu có khả năng cần xe số cơ khí, nên cân nhắc B số cơ khí ngay từ đầu để phạm vi sử dụng phù hợp hơn với nhu cầu thực tế.</p><div class="info-callout">';
  html=replaceRequired(html,anchor,section,'pricing decision guidance');
  fs.writeFileSync(p,html);
}

function updateAccurateLastmod(){
  const p=path.join(out,'sitemap.xml');
  let xml=fs.readFileSync(p,'utf8');
  xml=replaceRequired(xml,
    '<url><loc>https://hoclaixequangninh.vn/</loc><lastmod>2026-08-15</lastmod>',
    '<url><loc>https://hoclaixequangninh.vn/</loc><lastmod>2026-08-16</lastmod>',
    'homepage sitemap lastmod');
  xml=replaceRequired(xml,
    '<url><loc>https://hoclaixequangninh.vn/hoc-phi-hoc-lai-xe-quang-ninh.html</loc><lastmod>2026-08-15</lastmod>',
    '<url><loc>https://hoclaixequangninh.vn/hoc-phi-hoc-lai-xe-quang-ninh.html</loc><lastmod>2026-08-16</lastmod>',
    'pricing sitemap lastmod');
  fs.writeFileSync(p,xml);
}

function flattenMobileCssImports(){
  const mobilePath=path.join(out,'assets/mobile-v2.css');
  let css=fs.readFileSync(mobilePath,'utf8');
  css=css.replace(/^@import url\('\/assets\/official-site\.css\?v=20260815'\);\s*@import url\('\/assets\/official-pages\.css\?v=20260815d'\);\s*/,'');
  if(/@import[^\n]+official-(?:site|pages)\.css/i.test(css))throw new Error('mobile-v2.css still contains institutional @import chain');
  fs.writeFileSync(mobilePath,css);

  const htmlFiles=[];
  function walkHtml(dir){
    for(const entry of fs.readdirSync(dir,{withFileTypes:true})){
      const p=path.join(dir,entry.name);
      if(entry.isDirectory())walkHtml(p);
      else if(entry.name.endsWith('.html'))htmlFiles.push(p);
    }
  }
  walkHtml(out);
  for(const p of htmlFiles){
    let html=fs.readFileSync(p,'utf8');
    const mobile=html.match(/<link\s+rel=["']stylesheet["']\s+href=["']([^"']*assets\/mobile-v2\.css[^"']*)["']\s*\/?\s*>/i);
    if(!mobile)continue;
    html=html.replace(/<link\s+rel=["']stylesheet["']\s+href=["'][^"']*assets\/official-site\.css[^"']*["']\s*\/?\s*>/gi,'');
    html=html.replace(/<link\s+rel=["']stylesheet["']\s+href=["'][^"']*assets\/official-pages\.css[^"']*["']\s*\/?\s*>/gi,'');
    const href=mobile[1];
    const idx=href.indexOf('mobile-v2.css');
    const prefix=href.slice(0,idx);
    const links=`<link rel="stylesheet" href="${prefix}official-site.css?v=20260815"><link rel="stylesheet" href="${prefix}official-pages.css?v=20260815d"><link rel="stylesheet" href="${href}">`;
    html=html.replace(mobile[0],links);
    fs.writeFileSync(p,html);
  }
}

optimizeHomepage();
enrichPricingPage();
updateAccurateLastmod();
flattenMobileCssImports();

const forbidden=['coin-v7','coin-v8','coin-v9','coin_research','src','tests','.github','hlxqn-tools','requirements.txt','requirements-dev.txt','nen.png','sound.mp3'];
for(const item of forbidden){
  const p=path.join(out,item);
  if(fs.existsSync(p))throw new Error(`Forbidden file leaked into public artifact: ${item}`);
}

const home=fs.readFileSync(path.join(out,'index.html'),'utf8');
const pricing=fs.readFileSync(path.join(out,'hoc-phi-hoc-lai-xe-quang-ninh.html'),'utf8');
if(!home.includes('Học lái xe Quảng Ninh: <em>chọn đúng khóa học</em>'))throw new Error('Optimized homepage H1 missing');
if(!home.includes('<a class="primary" href="#dang-ky">Đăng ký tư vấn</a>'))throw new Error('Optimized homepage primary CTA missing');
if(!pricing.includes('Nếu B tự động và B cơ khí cùng mức 20,9 triệu'))throw new Error('Pricing decision guidance missing');
if(!pricing.includes('"dateModified":"2026-08-16"'))throw new Error('Pricing modified date missing');

let files=0,bytes=0;
function walk(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,entry.name);if(entry.isDirectory())walk(p);else{files++;bytes+=fs.statSync(p).size;}}}
walk(out);
console.log(JSON.stringify({publicFiles:files,publicBytes:bytes,assets:[...seen].sort(),productionOptimizations:['homepage-intent-copy','primary-registration-cta','pricing-decision-guidance','accurate-lastmod','flattened-css-imports']},null,2));
