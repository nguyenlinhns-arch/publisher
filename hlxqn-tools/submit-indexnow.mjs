import fs from 'node:fs';
import path from 'node:path';

const repoRoot=path.resolve(import.meta.dirname,'..');
const artifactRoot=path.join(repoRoot,'_site');
const root=fs.existsSync(path.join(artifactRoot,'sitemap.xml'))?artifactRoot:repoRoot;
const key=String(process.env.INDEXNOW_KEY||'').trim();
if(!/^[A-Za-z0-9-]{8,128}$/.test(key)){
  console.log(JSON.stringify({indexNow:'skipped',reason:'missing-or-invalid-key'},null,2));
  process.exit(0);
}
const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const sitemapPath=path.join(root,'sitemap.xml');
if(!fs.existsSync(sitemapPath)){
  console.log(JSON.stringify({indexNow:'skipped',reason:'sitemap-missing',sitemapPath},null,2));
  process.exit(0);
}
const sitemap=fs.readFileSync(sitemapPath,'utf8');
const rows=[...sitemap.matchAll(/<url>\s*<loc>([^<]+)<\/loc>\s*<lastmod>([^<]+)<\/lastmod>[\s\S]*?<\/url>/g)].map(m=>({url:m[1],lastmod:m[2]}));
const urlList=rows.filter(x=>x.lastmod===today).map(x=>x.url);
if(!urlList.length){
  console.log(JSON.stringify({indexNow:'skipped',reason:'no-urls-changed-today',today,sitemapRoot:path.relative(repoRoot,root)||'.'},null,2));
  process.exit(0);
}
const payload={
  host:'hoclaixequangninh.vn',
  key,
  keyLocation:`https://hoclaixequangninh.vn/${key}.txt`,
  urlList
};

async function post(endpoint){
  try{
    const response=await fetch(endpoint,{
      method:'POST',
      headers:{'content-type':'application/json; charset=utf-8'},
      body:JSON.stringify(payload)
    });
    const body=await response.text();
    return {endpoint,status:response.status,accepted:response.status===200||response.status===202,response:body.slice(0,500)};
  }catch(error){
    return {endpoint,status:0,accepted:false,error:String(error)};
  }
}

const attempts=[];
const primary=await post('https://api.indexnow.org/indexnow');
attempts.push(primary);
if(!primary.accepted&&(primary.status===403||primary.status===0)){
  attempts.push(await post('https://www.bing.com/indexnow'));
}
const accepted=attempts.find(x=>x.accepted);
console.log(JSON.stringify({
  indexNow:accepted?'accepted':'not-accepted',
  acceptedBy:accepted?.endpoint||'',
  today,
  submitted:urlList.length,
  urls:urlList,
  sitemapRoot:path.relative(repoRoot,root)||'.',
  attempts
},null,2));
process.exit(0);
