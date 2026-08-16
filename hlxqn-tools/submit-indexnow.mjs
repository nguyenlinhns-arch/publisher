import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'..','_site');
const key=String(process.env.INDEXNOW_KEY||'').trim();
if(!/^[A-Za-z0-9-]{8,128}$/.test(key)){
  console.log(JSON.stringify({indexNow:'skipped',reason:'missing-or-invalid-key'},null,2));
  process.exit(0);
}
const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const sitemap=fs.readFileSync(path.join(root,'sitemap.xml'),'utf8');
const rows=[...sitemap.matchAll(/<url>\s*<loc>([^<]+)<\/loc>\s*<lastmod>([^<]+)<\/lastmod>[\s\S]*?<\/url>/g)].map(m=>({url:m[1],lastmod:m[2]}));
const urlList=rows.filter(x=>x.lastmod===today).map(x=>x.url);
if(!urlList.length){
  console.log(JSON.stringify({indexNow:'skipped',reason:'no-urls-changed-today',today},null,2));
  process.exit(0);
}
const payload={
  host:'hoclaixequangninh.vn',
  key,
  keyLocation:`https://hoclaixequangninh.vn/${key}.txt`,
  urlList
};
try{
  const response=await fetch('https://api.indexnow.org/indexnow',{
    method:'POST',
    headers:{'content-type':'application/json; charset=utf-8'},
    body:JSON.stringify(payload)
  });
  const body=await response.text();
  const accepted=response.status===200||response.status===202;
  console.log(JSON.stringify({indexNow:accepted?'accepted':'not-accepted',status:response.status,today,submitted:urlList.length,urls:urlList,response:body.slice(0,500)},null,2));
  // IndexNow is a discovery enhancement; transient remote failures must not roll back a valid website deployment.
  process.exit(0);
}catch(error){
  console.log(JSON.stringify({indexNow:'network-error',today,submitted:urlList.length,error:String(error)},null,2));
  process.exit(0);
}
