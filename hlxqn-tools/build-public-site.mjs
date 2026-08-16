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

const forbidden=['coin-v7','coin-v8','coin-v9','coin_research','src','tests','.github','hlxqn-tools','requirements.txt','requirements-dev.txt','nen.png','sound.mp3'];
for(const item of forbidden){
  const p=item.includes('.')?path.join(out,item):path.join(out,item);
  if(fs.existsSync(p))throw new Error(`Forbidden file leaked into public artifact: ${item}`);
}

let files=0,bytes=0;
function walk(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,entry.name);if(entry.isDirectory())walk(p);else{files++;bytes+=fs.statSync(p).size;}}}
walk(out);
console.log(JSON.stringify({publicFiles:files,publicBytes:bytes,assets:[...seen].sort()},null,2));
