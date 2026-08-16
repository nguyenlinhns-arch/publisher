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
async function fetchWithRetry(path){
  let last;
  for(let i=0;i<6;i++){
    try{
      const u=new URL(path,origin);
      u.searchParams.set('_smoke',String(stamp));
      const r=await fetch(u,{redirect:'follow',headers:{'cache-control':'no-cache','user-agent':'hoclaixequangninh-live-smoke/1.0'}});
      const text=await r.text();
      last={r,text,url:u.href};
      if(r.ok)return last;
    }catch(e){last={error:e,url:new URL(path,origin).href};}
    await sleep(2000*(i+1));
  }
  return last;
}
for(const check of checks){
  const got=await fetchWithRetry(check.path);
  if(got.error){errors.push(`${check.path}: network ${got.error}`);continue;}
  const {r,text}=got;
  const ct=(r.headers.get('content-type')||'').toLowerCase();
  if(!r.ok)errors.push(`${check.path}: HTTP ${r.status}`);
  if(check.type==='text/html'&&!ct.includes('text/html'))errors.push(`${check.path}: unexpected content-type ${ct}`);
  if(check.type==='text/plain'&&!ct.includes('text/plain'))errors.push(`${check.path}: unexpected content-type ${ct}`);
  if(check.type==='xml'&&!ct.includes('xml'))errors.push(`${check.path}: unexpected content-type ${ct}`);
  if(check.type==='javascript'&&!/(javascript|text\/plain)/.test(ct))errors.push(`${check.path}: unexpected content-type ${ct}`);
  for(const needle of check.contains||[])if(!text.includes(needle))errors.push(`${check.path}: missing ${needle}`);
  for(const needle of check.absent||[])if(text.includes(needle))errors.push(`${check.path}: forbidden ${needle}`);
  if(/adsterra|effectivecpmnetwork|highperformanceformat/i.test(text))errors.push(`${check.path}: Adsterra leaked live`);
  if(check.type==='text/html'&&!text.includes('https://hoclaixequangninh.vn/'))errors.push(`${check.path}: canonical/domain signal missing`);
  results.push({path:check.path,status:r.status,bytes:Buffer.byteLength(text),contentType:ct.split(';')[0]});
}
console.log(JSON.stringify({origin,checks:results,errors},null,2));
if(errors.length)process.exit(1);
