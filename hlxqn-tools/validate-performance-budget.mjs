import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'..','_site');
const assets=path.join(root,'assets');
const errors=[];
const rows=[];
let assetBytes=0;

const LIMITS={
  image:250*1024,
  js:80*1024,
  css:120*1024,
  totalAssets:650*1024,
  homepage:90*1024
};

function walk(dir){
  for(const entry of fs.readdirSync(dir,{withFileTypes:true})){
    const p=path.join(dir,entry.name);
    if(entry.isDirectory())walk(p);
    else{
      const size=fs.statSync(p).size;
      const rel=path.relative(root,p).replaceAll(path.sep,'/');
      assetBytes+=size;
      rows.push({file:rel,bytes:size});
      if(/\.(?:png|jpe?g|webp|gif|svg)$/i.test(entry.name)&&size>LIMITS.image)errors.push(`${rel}: image ${size} bytes > ${LIMITS.image}`);
      if(/\.js$/i.test(entry.name)&&size>LIMITS.js)errors.push(`${rel}: JS ${size} bytes > ${LIMITS.js}`);
      if(/\.css$/i.test(entry.name)&&size>LIMITS.css)errors.push(`${rel}: CSS ${size} bytes > ${LIMITS.css}`);
      if(/\.(?:ttf|otf|woff2?)$/i.test(entry.name))errors.push(`${rel}: font file should not be shipped unless explicitly required`);
    }
  }
}
if(!fs.existsSync(assets))throw new Error('assets directory missing');
walk(assets);
if(assetBytes>LIMITS.totalAssets)errors.push(`assets total ${assetBytes} bytes > ${LIMITS.totalAssets}`);

const homeBytes=fs.statSync(path.join(root,'index.html')).size;
if(homeBytes>LIMITS.homepage)errors.push(`index.html ${homeBytes} bytes > ${LIMITS.homepage}`);

rows.sort((a,b)=>b.bytes-a.bytes);
console.log(JSON.stringify({assetBytes,homepageBytes:homeBytes,largest:rows.slice(0,12),limits:LIMITS,errors},null,2));
if(errors.length)process.exit(1);
