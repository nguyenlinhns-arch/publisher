const origin='https://hoclaixequangninh.vn';
const stamp=Date.now();
const checks=[
  {path:'/',type:'text/html',contains:['Học lái xe Quảng Ninh:','Đăng ký tư vấn']},
  {path:'/robots.txt',type:'text/plain',contains:['Sitemap: https://hoclaixequangninh.vn/sitemap.xml']},
  {path:'/sitemap.xml',type:'xml',contains:['dao-tao-lai-xe-tkv-6-thang-2026.html','hoc-a1-quang-ninh.html'],absent:['uu-dai-hoc-vien.html']},
  {path:'/hoc-lai-xe-so-tu-dong-quang-ninh.html',type:'text/html',contains:['không còn phần thi mô phỏng','20.900.000đ']},
  {path:'/hoc-lai-xe-so-co-khi-quang-ninh.html',type:'text/html',contains:['228 giờ đào tạo tối thiểu','1.050 km thực hành']},
  {path:'/hoc-c1-quang-ninh.html',type:'text/html',contains:['237 giờ đào tạo tối thiểu','1.050 km thực hành']},
  {path:'/hoc-a1-quang-ninh.html',type:'text/html',contains:['18 tuổi','21/01/2026']},
  {path:'/dang-ky-hoc-lai-xe-quang-ninh.html',type:'text/html',contains:['Gửi thông tin một lần','Tư vấn miễn phí']},
  {path:'/quy-dinh-hoc-phi-thoi-gian-dat.html',type:'text/html',contains:['196 giờ','228 giờ','237 giờ','mô phỏng vẫn thuộc']},
  {path:'/assets/site-runtime.js',type:'javascript',contains:["mode:'status',lead_id:leadId,phone:",'confirmLead(payload.lead_id,payload.phone)']}
];
const errors=[];
const results=[];
async function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
function validate(check,r,text){
  const issues=[];
  const ct=(r.headers.get('content-type')||'').toLowerCase();
  if(!r.ok)issues.push(`HTTP ${r.status}`);
  if(check.type==='text/html'&&!ct.includes('text/html'))issues.push(`unexpected content-type ${ct}`);
  if(check.type==='text/plain'&&!ct.includes('text/plain'))issues.push(`unexpected content-type ${ct}`);
  if(check.type==='xml'&&!ct.includes('xml'))issues.push(`unexpected content-type ${ct}`);
  if(check.type==='javascript'&&!/(javascript|text\/plain)/.test(ct))issues.push(`unexpected content-type ${ct}`);
  for(const needle of check.contains||[])if(!text.includes(needle))issues.push(`missing ${needle}`);
  for(const needle of check.absent||[])if(text.includes(needle))issues.push(`forbidden ${needle}`);
  if(/adsterra|effectivecpmnetwork|highperformanceformat/i.test(text))issues.push('Adsterra leaked live');
  if(check.type==='text/html'&&!text.includes('https://hoclaixequangninh.vn/'))issues.push('canonical/domain signal missing');
  return issues;
}
async function fetchUntilCurrent(check){
  let last={issues:['not fetched']};
  for(let i=0;i<12;i++){
    try{
      const u=new URL(check.path,origin);
      u.searchParams.set('_smoke',`${stamp}-${i}`);
      const r=await fetch(u,{redirect:'follow',headers:{'cache-control':'no-cache, no-store','pragma':'no-cache','user-agent':'hoclaixequangninh-live-smoke/1.1'}});
      const text=await r.text();
      const issues=validate(check,r,text);
      last={r,text,url:u.href,issues,attempt:i+1};
      if(!issues.length)return last;
    }catch(error){
      last={error,url:new URL(check.path,origin).href,issues:[`network ${error}`],attempt:i+1};
    }
    await sleep(2500);
  }
  return last;
}
for(const check of checks){
  const got=await fetchUntilCurrent(check);
  if(got.issues?.length){
    for(const issue of got.issues)errors.push(`${check.path}: ${issue}`);
    continue;
  }
  const ct=(got.r.headers.get('content-type')||'').toLowerCase();
  results.push({path:check.path,status:got.r.status,bytes:Buffer.byteLength(got.text),contentType:ct.split(';')[0],attempt:got.attempt});
}
console.log(JSON.stringify({origin,checks:results,errors},null,2));
if(errors.length)process.exit(1);
