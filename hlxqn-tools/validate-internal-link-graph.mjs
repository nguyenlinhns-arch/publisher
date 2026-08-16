import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'..','_site');
const domain='https://hoclaixequangninh.vn';
const sitemap=fs.readFileSync(path.join(root,'sitemap.xml'),'utf8');
const sitemapUrls=[...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m=>m[1]);
const sitemapSet=new Set(sitemapUrls);
const errors=[];
const warnings=[];

function urlToFile(url){
  const rel=url.replace(`${domain}/`,'');
  return rel===''?'index.html':rel.endsWith('/')?`${rel}index.html`:rel;
}
function fileToUrl(file){
  if(file==='index.html')return `${domain}/`;
  if(file.endsWith('/index.html'))return `${domain}/${file.slice(0,-'index.html'.length)}`;
  return `${domain}/${file}`;
}
function cleanMarkup(html){return html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,' ').replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi,' ')}
function resolveInternal(fromFile,href){
  const raw=href.split('#')[0].split('?')[0];
  if(!raw||/^(?:https?:|tel:|mailto:|javascript:|data:)/i.test(raw)){
    if(raw.startsWith(domain))return raw.replace(/\/$/,'/') || `${domain}/`;
    return null;
  }
  const base=new URL(fileToUrl(fromFile));
  const u=new URL(raw,base);
  if(u.origin!==domain)return null;
  return u.href.split('#')[0].split('?')[0];
}

const graph=new Map();
const indegree=new Map(sitemapUrls.map(u=>[u,0]));
for(const url of sitemapUrls){
  const file=urlToFile(url);
  const p=path.join(root,file);
  if(!fs.existsSync(p)){errors.push(`missing sitemap page for graph: ${url}`);continue;}
  const html=cleanMarkup(fs.readFileSync(p,'utf8'));
  const out=new Set();
  for(const m of html.matchAll(/<a\b[^>]*href=["']([^"']+)["']/gi)){
    const target=resolveInternal(file,m[1]);
    if(!target)continue;
    const canonicalTarget=target.endsWith('/index.html')?target.slice(0,-'index.html'.length):target;
    if(sitemapSet.has(canonicalTarget)){out.add(canonicalTarget);}
  }
  graph.set(url,out);
}
for(const [,outs] of graph){for(const u of outs)indegree.set(u,(indegree.get(u)||0)+1)}

const start=`${domain}/`;
const depth=new Map([[start,0]]);
const queue=[start];
while(queue.length){
  const cur=queue.shift();
  const d=depth.get(cur);
  for(const next of graph.get(cur)||[]){
    if(!depth.has(next)){depth.set(next,d+1);queue.push(next)}
  }
}
for(const url of sitemapUrls){
  if(!depth.has(url))errors.push(`orphan/unreachable from homepage: ${url}`);
  else if(depth.get(url)>4)warnings.push(`crawl depth ${depth.get(url)}: ${url}`);
  if(url!==start&&(indegree.get(url)||0)<2)warnings.push(`only ${indegree.get(url)||0} internal links point to ${url}`);
}

const depthCounts={};
for(const d of depth.values())depthCounts[d]=(depthCounts[d]||0)+1;
const lowInDegree=[...indegree.entries()].filter(([u,n])=>u!==start&&n<2).map(([u,n])=>({url:u,inbound:n}));
console.log(JSON.stringify({sitemapUrls:sitemapUrls.length,reachable:depth.size,maxDepth:Math.max(...depth.values()),depthCounts,lowInbound:lowInDegree,errors,warnings},null,2));
if(errors.length)process.exit(1);
