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
console.log(JSON.stringify({homepageTitle:true,lcpPreload:true},null,2));
