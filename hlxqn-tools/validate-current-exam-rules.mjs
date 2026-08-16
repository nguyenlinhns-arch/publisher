import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'..');
const targetRoot=process.argv[2]?path.resolve(root,process.argv[2]):root;
const errors=[];
const findings=[];
const htmlFiles=[];
function walk(dir){for(const e of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(e.isDirectory()){if(e.name==='.git'||e.name==='_site'||e.name==='node_modules'||e.name==='coin-v7'||e.name==='coin-v8'||e.name==='coin-v9'||e.name==='src'||e.name==='tests')continue;walk(p)}else if(e.name.endsWith('.html'))htmlFiles.push(p)}}
walk(targetRoot);

function stripTags(s){return s.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,' ').replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi,' ').replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim()}
for(const file of htmlFiles){
  const rel=path.relative(targetRoot,file).replaceAll(path.sep,'/');
  const text=stripTags(fs.readFileSync(file,'utf8'));
  const lower=text.toLowerCase();
  let pos=0;
  while((pos=lower.indexOf('mô phỏng',pos))!==-1){
    const start=Math.max(0,pos-180),end=Math.min(text.length,pos+260);
    const snippet=text.slice(start,end);
    const normalized=snippet.toLowerCase();
    if(normalized.includes('sát hạch')||normalized.includes('thi '))findings.push({file:rel,snippet});
    pos+=8;
  }
}
for(const f of findings){
  const s=f.snippet.toLowerCase();
  const allowed=/không còn[^.]{0,100}mô phỏng|bỏ[^.]{0,120}mô phỏng|loại bỏ[^.]{0,120}mô phỏng|phòng học,?\s*mô phỏng/.test(s);
  if(!allowed)errors.push(`${f.file}: possible outdated exam-simulation claim: ${f.snippet}`);
}
const required='không còn phần thi mô phỏng';
const currentRulePages=htmlFiles.filter(file=>stripTags(fs.readFileSync(file,'utf8')).toLowerCase().includes(required));
if(currentRulePages.length===0)errors.push('No page states the current rule that the simulation exam was removed from 01/07/2026');
console.log(JSON.stringify({root:targetRoot,htmlPages:htmlFiles.length,simulationExamContextFindings:findings.map(f=>f.file),currentRulePages:currentRulePages.map(f=>path.relative(targetRoot,f).replaceAll(path.sep,'/')),errors},null,2));
if(errors.length)process.exit(1);
