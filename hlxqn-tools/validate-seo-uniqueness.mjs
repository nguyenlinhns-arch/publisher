import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'..');
const domain='https://hoclaixequangninh.vn';
const sitemap=fs.readFileSync(path.join(root,'sitemap.xml'),'utf8');
const urls=[...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1]);
const errors=[];
const titles=new Map();
const descriptions=new Map();

function targetFor(url){
  const rel=url.replace(`${domain}/`,'');
  return rel===''?path.join(root,'index.html'):rel.endsWith('/')?path.join(root,rel,'index.html'):path.join(root,rel);
}
function addUnique(map,value,label,file){
  if(!value)return;
  const key=value.replace(/\s+/g,' ').trim().toLocaleLowerCase('vi');
  const prior=map.get(key);
  if(prior)errors.push(`${label} trùng: ${prior} và ${file}`);else map.set(key,file);
}

for(const url of urls){
  const file=targetFor(url);
  if(!fs.existsSync(file)){errors.push(`Sitemap target missing: ${url}`);continue;}
  const html=fs.readFileSync(file,'utf8');
  const rel=path.relative(root,file).replaceAll(path.sep,'/');
  const robots=(html.match(/<meta\s+name=["']robots["']\s+content=["']([^"']+)/i)||[])[1]||'';
  if(/noindex/i.test(robots))errors.push(`Sitemap URL is noindex: ${url}`);
  const canonical=(html.match(/<link\s+rel=["']canonical["']\s+href=["']([^"']+)/i)||[])[1];
  if(!canonical)errors.push(`${rel}: sitemap page missing canonical`);
  else if(canonical!==url)errors.push(`${rel}: canonical ${canonical} does not match sitemap URL ${url}`);
  const title=(html.match(/<title>([\s\S]*?)<\/title>/i)||[])[1];
  const description=(html.match(/<meta\s+name=["']description["']\s+content=["']([^"']+)/i)||[])[1];
  addUnique(titles,title,'Title',rel);
  addUnique(descriptions,description,'Meta description',rel);
}

console.log(JSON.stringify({sitemapUrls:urls.length,uniqueTitles:titles.size,uniqueDescriptions:descriptions.size,errors},null,2));
if(errors.length)process.exit(1);
