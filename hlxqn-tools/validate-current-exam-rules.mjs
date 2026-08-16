import fs from 'node:fs';
import path from 'node:path';

const repoRoot=path.resolve(import.meta.dirname,'..');
const targetRoot=process.argv[2]?path.resolve(repoRoot,process.argv[2]):repoRoot;
const errors=[];
const findings=[];
const htmlFiles=[];

function walk(dir){
  for(const e of fs.readdirSync(dir,{withFileTypes:true})){
    const p=path.join(dir,e.name);
    if(e.isDirectory()){
      if(['.git','_site','node_modules','coin-v7','coin-v8','coin-v9','src','tests'].includes(e.name))continue;
      walk(p);
    }else if(e.name.endsWith('.html'))htmlFiles.push(p);
  }
}
walk(targetRoot);

function visibleText(html){
  return html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,' ')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi,' ')
    .replace(/<\/(?:p|h[1-6]|li|div|section|article|br)>/gi,'$&\n')
    .replace(/<[^>]+>/g,' ')
    .replace(/[ \t]+/g,' ')
    .replace(/\n\s*/g,'\n')
    .trim();
}
function clauses(text){return text.split(/(?<=[.!?])\s+|\n+/).map(x=>x.trim()).filter(Boolean)}
function isCurrentRemovalStatement(s){
  const t=s.toLowerCase();
  return /không còn[^.]{0,140}mô phỏng/.test(t)
    || /bỏ[^.]{0,140}mô phỏng/.test(t)
    || /loại bỏ[^.]{0,140}mô phỏng/.test(t)
    || /mô phỏng[^.]{0,140}(?:đã\s+)?(?:được\s+)?bỏ/.test(t)
    || /mô phỏng[^.]{0,180}không còn[^.]{0,120}(?:là\s+)?(?:một\s+)?phần thi/.test(t);
}
function isFacilityOrTrainingContext(s){
  const t=s.toLowerCase();
  return /phòng học\s*(?:&|và|,)?\s*mô phỏng/.test(t)
    || /không gian học[^.]{0,120}mô phỏng/.test(t)
    || /học (?:lý thuyết,?\s*)?mô phỏng/.test(t)
    || /cơ sở[^.]{0,120}mô phỏng/.test(t);
}
function looksLikeExamClaim(s){
  const t=s.toLowerCase();
  return t.includes('mô phỏng') && (/sát hạch|kỳ thi|bài thi|phần thi|thi ô tô|ngày thi/.test(t));
}

const currentRulePages=[];
for(const file of htmlFiles){
  const rel=path.relative(targetRoot,file).replaceAll(path.sep,'/');
  const text=visibleText(fs.readFileSync(file,'utf8'));
  const lower=text.toLowerCase();
  if(lower.includes('không còn phần thi mô phỏng')||lower.includes('phần thi mô phỏng trên máy tính đã được bỏ'))currentRulePages.push(rel);
  for(const sentence of clauses(text)){
    if(!looksLikeExamClaim(sentence))continue;
    findings.push({file:rel,sentence});
    if(isCurrentRemovalStatement(sentence)||isFacilityOrTrainingContext(sentence))continue;
    errors.push(`${rel}: possible outdated exam-simulation claim: ${sentence}`);
  }
}
if(currentRulePages.length===0)errors.push('No page states the current rule that the automobile simulation exam was removed from 01/07/2026');

console.log(JSON.stringify({root:targetRoot,htmlPages:htmlFiles.length,simulationExamContextFindings:findings,currentRulePages,errors},null,2));
if(errors.length)process.exit(1);
