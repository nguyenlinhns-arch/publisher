import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'..','_site');
const p=path.join(root,'index.html');
let html=fs.readFileSync(p,'utf8');

const oldTitle='<title>Học Lái Xe Quảng Ninh | Tuyển sinh B, C1, A1</title>';
const newTitle='<title>Học Lái Xe Quảng Ninh | B tự động, B cơ khí, C1, A1</title>';
if(html.includes(oldTitle))html=html.replace(oldTitle,newTitle);
else if(!html.includes(newTitle))throw new Error('Homepage title anchor missing');

const preload='<link rel="preload" as="image" href="/assets/quang-hanh-san-sat-hach.jpg" type="image/jpeg" fetchpriority="high">';
if(!html.includes('rel="preload" as="image" href="/assets/quang-hanh-san-sat-hach.jpg"')){
  const icon='<link rel="icon" type="image/svg+xml" href="/favicon.svg">';
  if(!html.includes(icon))throw new Error('Homepage favicon anchor missing');
  html=html.replace(icon,`${icon}\n  ${preload}`);
}
fs.writeFileSync(p,html);

const sitemapPath=path.join(root,'sitemap.xml');
let sitemap=fs.readFileSync(sitemapPath,'utf8');
const guideMatch=sitemap.match(/<url><loc>https:\/\/hoclaixequangninh\.vn\/hoc-ly-thuyet\.html<\/loc><lastmod>(\d{4}-\d{2}-\d{2})<\/lastmod>/);
if(!guideMatch)throw new Error('Sitemap handbook lastmod anchor missing');
fs.writeFileSync(sitemapPath,sitemap);

const llmsPath=path.join(root,'llms.txt');
let llms=fs.readFileSync(llmsPath,'utf8');
if(llms.includes('Cập nhật nội dung trọng tâm: 2026-08-15'))llms=llms.replace('Cập nhật nội dung trọng tâm: 2026-08-15','Cập nhật nội dung trọng tâm: 2026-08-16');
else if(!llms.includes('Cập nhật nội dung trọng tâm: 2026-08-16'))throw new Error('llms.txt freshness anchor missing');
const articleLine='- Cập nhật đào tạo lái xe TKV 2026: https://hoclaixequangninh.vn/dao-tao-lai-xe-tkv-6-thang-2026.html';
if(!llms.includes(articleLine)){
  const newsLine='- Tin đào tạo & sát hạch: https://hoclaixequangninh.vn/tin-tuc.html';
  if(!llms.includes(newsLine))throw new Error('llms.txt news anchor missing');
  llms=llms.replace(newsLine,`${newsLine}\n${articleLine}`);
}
const dataLine='- 6 tháng đầu năm 2026, Trường Cao đẳng Than - Khoáng sản Việt Nam công bố 9.965/11.929 học viên ô tô, đạt 83,5% kế hoạch.';
if(!llms.includes(dataLine)){
  const updateHeading='## Cập nhật quản lý đào tạo năm 2026';
  if(!llms.includes(updateHeading))throw new Error('llms.txt 2026 update anchor missing');
  llms=llms.replace(updateHeading,`${updateHeading}\n${dataLine}`);
}
fs.writeFileSync(llmsPath,llms);

console.log(JSON.stringify({homepageTitle:true,lcpPreload:true,llmsFreshness:'2026-08-16',llmsTrainingUpdate:true,handbookLastmod:guideMatch[1]},null,2));
