import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'..','_site');
const redirectPages=new Set(['huong-dan-hoc-lai-xe.html','lich-sat-hach-lai-xe.html']);
let updated=0;

function walk(dir,list=[]){
  for(const entry of fs.readdirSync(dir,{withFileTypes:true})){
    const p=path.join(dir,entry.name);
    if(entry.isDirectory())walk(p,list);else if(entry.name.endsWith('.html'))list.push(p);
  }
  return list;
}

for(const p of walk(root)){
  const rel=path.relative(root,p).replaceAll(path.sep,'/');
  if(redirectPages.has(rel))continue;
  let html=fs.readFileSync(p,'utf8');
  let changed=false;
  if(/<main\b(?![^>]*\bid=)/i.test(html)){
    html=html.replace(/<main\b/i,'<main id="main-content"');
    changed=true;
  }
  if(!html.includes('class="skip-link"')){
    if(!/<body[^>]*>/i.test(html))throw new Error(`Missing body: ${rel}`);
    html=html.replace(/(<body[^>]*>)/i,'$1<a class="skip-link" href="#main-content">Bỏ qua điều hướng</a>');
    changed=true;
  }
  if(/<nav class="sticky-mobile"(?![^>]*aria-label)/i.test(html)){
    html=html.replace(/<nav class="sticky-mobile"/i,'<nav class="sticky-mobile" aria-label="Liên hệ nhanh"');
    changed=true;
  }
  if(/<a class="official-brand" href="\/" aria-label="Học Lái Xe Quảng Ninh - Trang chủ">/i.test(html)){
    html=html.replace(/<a class="official-brand" href="\/" aria-label="Học Lái Xe Quảng Ninh - Trang chủ">/gi,'<a class="official-brand" href="/">');
    changed=true;
  }
  if(changed){fs.writeFileSync(p,html);updated++;}
}

const cssPath=path.join(root,'assets/official-site.css');
let css=fs.readFileSync(cssPath,'utf8');
const rule='.skip-link{position:fixed;left:12px;top:8px;z-index:10000;transform:translateY(-160%);background:#fff;color:#062f57;border:2px solid #0b5ea8;border-radius:8px;padding:9px 12px;font-weight:900;text-decoration:none;box-shadow:0 6px 18px rgba(0,0,0,.16)}.skip-link:focus{transform:translateY(0)}';
if(!css.includes('.skip-link{'))css=`${rule}\n${css}`;
css=css.replace('--official-orange:#f58220;','--official-orange:#b94700;');
css=css.replace('--official-muted:#617589;','--official-muted:#5c7084;');
fs.writeFileSync(cssPath,css);

let checked=0;
for(const p of walk(root)){
  const rel=path.relative(root,p).replaceAll(path.sep,'/');
  if(redirectPages.has(rel))continue;
  const html=fs.readFileSync(p,'utf8');
  if(!html.includes('class="skip-link"')||!html.includes('id="main-content"'))throw new Error(`Accessibility navigation incomplete: ${rel}`);
  if(html.includes('aria-label="Học Lái Xe Quảng Ninh - Trang chủ"'))throw new Error(`Brand accessible-name mismatch remains: ${rel}`);
  checked++;
}
if(!css.includes('--official-orange:#b94700;')||!css.includes('--official-muted:#5c7084;'))throw new Error('Accessible contrast palette missing');
console.log(JSON.stringify({updatedPages:updated,checkedPages:checked,skipNavigation:true,mobileNavLabels:true,brandNameMatch:true,contrastPalette:true},null,2));
