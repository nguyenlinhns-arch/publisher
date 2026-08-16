import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'..');
const domain='https://hoclaixequangninh.vn';
const redirectPages=new Set(['huong-dan-hoc-lai-xe.html','lich-sat-hach-lai-xe.html']);
const utility=new Set(['404.html','huong-dan-hoc-lai-xe.html','lich-sat-hach-lai-xe.html','lien-he.html','dieu-khoan-su-dung.html','chinh-sach-bao-mat.html','gioi-thieu.html','tin-tuc.html','uu-dai-hoc-vien.html']);
const noindexPages=new Set(['404.html','huong-dan-hoc-lai-xe.html','lich-sat-hach-lai-xe.html','uu-dai-hoc-vien.html']);
const excludedFromSitemap=new Set(['404.html','huong-dan-hoc-lai-xe.html','lich-sat-hach-lai-xe.html','uu-dai-hoc-vien.html']);
const files=fs.readdirSync(root).filter(f=>f.endsWith('.html')).sort();
const errors=[];
const warnings=[];
const seenCanonical=new Map();

const text=html=>html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,' ').replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi,' ').replace(/<[^>]+>/g,' ').replace(/&[^;]+;/g,' ').replace(/\s+/g,' ').trim();

function existsTarget(href){
  const clean=href.split('#')[0].split('?')[0];
  if(!clean)return true;
  const relative=clean.startsWith('/')?clean.slice(1):clean;
  const target=relative===''?'index.html':relative.endsWith('/')?`${relative}index.html`:relative;
  return fs.existsSync(path.join(root,target));
}

for(const file of files){
  const html=fs.readFileSync(path.join(root,file),'utf8');
  const canonical=(html.match(/<link\s+rel="canonical"\s+href="([^"]+)"/i)||[])[1];
  const title=(html.match(/<title>([\s\S]*?)<\/title>/i)||[])[1];
  const description=(html.match(/<meta\s+name="description"\s+content="([^"]+)"/i)||[])[1];
  const robots=(html.match(/<meta\s+name="robots"\s+content="([^"]+)"/i)||[])[1]||'';

  if(!title)errors.push(`${file}: thiếu title`);
  if(!description&&!utility.has(file))errors.push(`${file}: thiếu meta description`);
  if(!/<h1\b/i.test(html)&&!utility.has(file))errors.push(`${file}: thiếu H1`);
  if(!canonical&&file!=='404.html')errors.push(`${file}: thiếu canonical`);
  if(canonical&&!canonical.startsWith(domain))errors.push(`${file}: canonical ngoài tên miền (${canonical})`);
  if(canonical){
    if(seenCanonical.has(canonical)&&!utility.has(file))errors.push(`${file}: canonical trùng ${seenCanonical.get(canonical)}`);
    seenCanonical.set(canonical,file);
  }
  if(!html.includes('application/ld+json')&&!utility.has(file))errors.push(`${file}: thiếu schema`);
  if(file!=='index.html'&&!html.includes('BreadcrumbList')&&!utility.has(file))errors.push(`${file}: thiếu BreadcrumbList`);
  if(!html.includes('assets/mobile-v2.css')&&!utility.has(file))errors.push(`${file}: thiếu CSS mobile`);
  if(!html.includes('assets/site-runtime.js')&&!redirectPages.has(file))errors.push(`${file}: thiếu tracking/CTA dùng chung`);
  if(/nguyenlinhns-arch\.github\.io\/publisher/i.test(html))errors.push(`${file}: còn URL GitHub Pages cũ`);
  if(noindexPages.has(file)&&!/noindex/i.test(robots))errors.push(`${file}: trang utility/redirect phải noindex`);

  const wordCount=text(html).split(/\s+/).filter(Boolean).length;
  if(!utility.has(file)&&wordCount<150)warnings.push(`${file}: nội dung rất ngắn (${wordCount} từ); chỉ mở rộng khi có thêm thông tin hữu ích`);

  for(const match of html.matchAll(/<a\b[^>]*href="([^"]+)"/gi)){
    const href=match[1];
    if(/^(https?:|tel:|mailto:|javascript:|#)/i.test(href))continue;
    if(!existsTarget(href))errors.push(`${file}: liên kết nội bộ hỏng ${href}`);
  }
  for(const match of html.matchAll(/<img\b[^>]*src="([^"]+)"/gi)){
    const src=match[1];
    if(/^https?:/i.test(src))errors.push(`${file}: ảnh còn phụ thuộc máy chủ ngoài ${src}`);
    else if(!fs.existsSync(path.join(root,src)))errors.push(`${file}: thiếu ảnh ${src}`);
  }
}

const sitemap=fs.readFileSync(path.join(root,'sitemap.xml'),'utf8');
const sitemapUrls=[...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1]);
const expectedSitemapUrls=files.filter(file=>!excludedFromSitemap.has(file)).length+1;
if(sitemapUrls.length!==expectedSitemapUrls)errors.push(`sitemap: cần ${expectedSitemapUrls} URL, hiện có ${sitemapUrls.length}`);
if(new Set(sitemapUrls).size!==sitemapUrls.length)errors.push('sitemap: có URL trùng');
for(const url of sitemapUrls){
  const relative=url.replace(`${domain}/`,'');
  const target=relative===''?'index.html':relative.endsWith('/')?`${relative}index.html`:relative;
  if(!fs.existsSync(path.join(root,target)))errors.push(`sitemap: URL không có tệp ${url}`);
}
for(const file of excludedFromSitemap){
  const url=file==='index.html'?`${domain}/`:`${domain}/${file}`;
  if(sitemapUrls.includes(url))errors.push(`sitemap: không đưa trang utility/redirect vào sitemap (${url})`);
}

const robots=fs.readFileSync(path.join(root,'robots.txt'),'utf8');
if(!robots.includes(`Sitemap: ${domain}/sitemap.xml`))errors.push('robots.txt: thiếu sitemap chuẩn');

const runtime=fs.readFileSync(path.join(root,'assets/site-runtime.js'),'utf8');
const ackIndex=runtime.indexOf('const ack=await confirmLead');
const conversionIndex=runtime.indexOf('fireAdsConversion(CONFIG.GOOGLE_ADS_CONVERSION_LABEL');
if(ackIndex<0||conversionIndex<ackIndex)errors.push('site-runtime: conversion chưa được khóa sau xác nhận Sheet');
if(!runtime.includes("event('lead_submit_unconfirmed'"))errors.push('site-runtime: thiếu nhánh không xác nhận được');
if(!runtime.includes('function normalizeLicense'))errors.push('site-runtime: thiếu chuẩn hóa hạng bằng cho Google Sheet');

const siteConfig=fs.readFileSync(path.join(root,'assets/site-config.js'),'utf8');
const affiliate=fs.readFileSync(path.join(root,'assets/accesstrade-entry-overlay.js'),'utf8');
const productionFiles=[siteConfig,runtime,affiliate,...files.map(f=>fs.readFileSync(path.join(root,f),'utf8'))].join('\n');
if(/adsterra|effectivecpmnetwork|highperformanceformat/i.test(productionFiles))errors.push('monetization: còn mã Adsterra trong production');
const protectsCurrentPaid=siteConfig.includes("q.get('gclid')")&&siteConfig.includes("q.get('gbraid')")&&siteConfig.includes("q.get('wbraid')");
const protectsPersistedPaid=siteConfig.includes("localStorage.getItem('hlxqn_attribution_v1')")&&siteConfig.includes('return paidSignals(saved)');
const blocksAffiliateForPaid=siteConfig.includes('window.HLX_IS_GOOGLE_PAID_VISIT=isGooglePaidVisit()')&&siteConfig.includes('if(window.HLX_IS_GOOGLE_PAID_VISIT)return');
if(!protectsCurrentPaid||!protectsPersistedPaid||!blocksAffiliateForPaid)errors.push('affiliate: chưa loại đầy đủ traffic Google Ads hiện tại và đã lưu trước khi tải');
if(/at-entry-lock|inset:0;z-index:214748/i.test(affiliate))errors.push('affiliate: còn dấu hiệu interstitial che toàn màn hình');
if(!affiliate.includes('at-offer-banner'))errors.push('affiliate: chưa dùng banner không xâm lấn');
if(!affiliate.includes('rel="sponsored nofollow noopener"'))errors.push('affiliate: thiếu rel sponsored/nofollow/noopener');

const home=fs.readFileSync(path.join(root,'index.html'),'utf8');
if(!/fetchpriority="high"/i.test(home))warnings.push('index.html: ảnh LCP chưa có fetchpriority=high');
if(!/<img[^>]+width="\d+"[^>]+height="\d+"/i.test(home))warnings.push('index.html: nên khai báo kích thước ảnh để giảm CLS');

console.log(JSON.stringify({pages:files.length,sitemapUrls:sitemapUrls.length,errors,warnings},null,2));
if(errors.length)process.exit(1);
