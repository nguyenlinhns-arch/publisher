import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'..');
const out=path.join(root,'_site');
const PHONE='0398696879';
const ZALO=`https://zalo.me/${PHONE}`;
const redirectNames=new Set(['huong-dan-hoc-lai-xe.html','lich-sat-hach-lai-xe.html']);

const header=`<header class="official-header"><div class="official-topbar"><div class="official-wrap"><div class="topbar-left">Tuyển sinh & hỗ trợ học viên học lái xe tại Quảng Ninh</div><div class="topbar-right">Tư vấn: <a href="tel:${PHONE}">${PHONE}</a> · <a href="${ZALO}">Zalo</a></div></div></div><div class="official-wrap official-head-main"><a class="official-brand" href="/" aria-label="Học Lái Xe Quảng Ninh - Trang chủ"><span class="official-mark">QN</span><span class="official-brand-copy"><strong>Học Lái Xe Quảng Ninh</strong><small>Tuyển sinh & hỗ trợ học viên</small></span></a><nav class="official-nav" aria-label="Điều hướng chính"><a href="/">Trang chủ</a><a href="/gioi-thieu.html">Giới thiệu</a><details><summary>Khóa học</summary><div class="official-dropdown"><a href="/hoc-lai-xe-so-tu-dong-quang-ninh.html">B số tự động</a><a href="/hoc-lai-xe-so-co-khi-quang-ninh.html">B số cơ khí</a><a href="/hoc-c1-quang-ninh.html">Hạng C1</a><a href="/hoc-a1-quang-ninh.html">Hạng A1</a></div></details><details><summary>Tuyển sinh</summary><div class="official-dropdown"><a href="/hoc-phi-hoc-lai-xe-quang-ninh.html">Học phí</a><a href="/ho-so-hoc-lai-xe-quang-ninh.html">Hồ sơ đăng ký</a><a href="/lich-sat-hach/">Lịch sát hạch</a><a href="/dang-ky-hoc-lai-xe-quang-ninh.html">Đăng ký học</a></div></details><details><summary>Khu vực học</summary><div class="official-dropdown"><a href="/trung-tam-quang-hanh.html">Quang Hanh</a><a href="/hoc-lai-xe-cam-pha.html">Cẩm Phả</a><a href="/hoc-lai-xe-ha-long.html">Hạ Long</a><a href="/hoc-lai-xe-uong-bi.html">Uông Bí</a><a href="/hoc-lai-xe-mong-cai.html">Móng Cái</a></div></details><a href="/hoc-ly-thuyet.html">Cẩm nang</a><a href="/tin-tuc.html">Tin tức</a><a href="/lien-he.html">Liên hệ</a></nav><a class="official-head-cta" href="/dang-ky-hoc-lai-xe-quang-ninh.html#dang-ky">Đăng ký học</a><details class="official-mobile-menu"><summary>☰ Menu</summary><div class="official-mobile-panel"><a href="/">Trang chủ</a><a href="/gioi-thieu.html">Giới thiệu</a><a href="/hoc-lai-xe-so-tu-dong-quang-ninh.html">B số tự động</a><a href="/hoc-lai-xe-so-co-khi-quang-ninh.html">B số cơ khí</a><a href="/hoc-c1-quang-ninh.html">Hạng C1</a><a href="/hoc-a1-quang-ninh.html">Hạng A1</a><a href="/hoc-phi-hoc-lai-xe-quang-ninh.html">Học phí</a><a href="/ho-so-hoc-lai-xe-quang-ninh.html">Hồ sơ</a><a href="/lich-sat-hach/">Lịch sát hạch</a><a href="/hoc-ly-thuyet.html">Cẩm nang</a><a href="/tin-tuc.html">Tin tức</a><a href="/lien-he.html">Liên hệ</a><a href="/dang-ky-hoc-lai-xe-quang-ninh.html#dang-ky">Đăng ký học</a></div></details></div></header>`;

const footer=`<footer class="official-footer"><div class="official-wrap official-footer-main"><div class="official-footer-brand"><strong>Học Lái Xe Quảng Ninh</strong><p>Thông tin tuyển sinh, học phí, hồ sơ, chương trình học, khu vực đào tạo và hướng dẫn dành cho người học lái xe tại Quảng Ninh.</p><p><b style="color:#fff">Tư vấn: ${PHONE}</b></p></div><div><h4>Tuyển sinh</h4><div class="official-footer-links"><a href="/hoc-phi-hoc-lai-xe-quang-ninh.html">Học phí</a><a href="/ho-so-hoc-lai-xe-quang-ninh.html">Hồ sơ đăng ký</a><a href="/dang-ky-hoc-lai-xe-quang-ninh.html">Đăng ký học</a><a href="/lich-sat-hach/">Lịch sát hạch</a></div></div><div><h4>Khóa học</h4><div class="official-footer-links"><a href="/hoc-lai-xe-so-tu-dong-quang-ninh.html">B số tự động</a><a href="/hoc-lai-xe-so-co-khi-quang-ninh.html">B số cơ khí</a><a href="/hoc-c1-quang-ninh.html">Hạng C1</a><a href="/hoc-a1-quang-ninh.html">Hạng A1</a></div></div><div><h4>Thông tin</h4><div class="official-footer-links"><a href="/gioi-thieu.html">Giới thiệu</a><a href="/tin-tuc.html">Tin tức</a><a href="/hoc-ly-thuyet.html">Cẩm nang</a><a href="/uu-dai-hoc-vien.html">Ưu đãi học viên</a><a href="/chinh-sach-bao-mat.html">Chính sách bảo mật</a><a href="/dieu-khoan-su-dung.html">Điều khoản sử dụng</a><a href="/lien-he.html">Liên hệ</a></div></div></div><div class="official-footer-bottom"><div class="official-wrap"><div class="official-disclaimer">hoclaixequangninh.vn là kênh thông tin và tư vấn tuyển sinh, không phải cổng thông tin của cơ quan quản lý nhà nước. Thông tin học phí, lịch học và sát hạch được cập nhật theo thông báo áp dụng của đơn vị đào tạo/cơ quan có thẩm quyền.</div><div>© hoclaixequangninh.vn</div></div></div></footer>`;

const replacements=[
  ['Website tổ chức nội dung theo từng khu vực để người học dễ tìm địa điểm, chương trình và thông tin liên quan.','Chọn khu vực thuận tiện để xem địa điểm học, chương trình và thông tin phù hợp.'],
  ['Website đang cung cấp thông tin theo các khu vực Quang Hanh/Cẩm Phả, Uông Bí, Móng Cái, Hạ Long và khu vực khác.','Có thể lựa chọn Quang Hanh/Cẩm Phả, Hạ Long, Uông Bí, Móng Cái hoặc khu vực khác khi đăng ký.'],
  ['Website đang có thông tin theo Quang Hanh/Cẩm Phả, Uông Bí, Hạ Long và Móng Cái.','Có thể lựa chọn Quang Hanh/Cẩm Phả, Hạ Long, Uông Bí hoặc Móng Cái tùy nơi ở và lịch học.'],
  ['Website được tổ chức theo đúng các câu hỏi mà một người mới thường gặp trong suốt quá trình học.','Các bước được sắp xếp theo hành trình thực tế từ chọn hạng, chuẩn bị hồ sơ đến học và sát hạch.'],
  ['Website có trang Hồ sơ đăng ký riêng. Nên kiểm tra danh mục giấy tờ đang áp dụng trước khi đến nộp để tránh phải bổ sung nhiều lần.','Nên kiểm tra danh mục hồ sơ đang áp dụng trước khi đến nộp để tránh phải bổ sung nhiều lần.'],
  ['Website đã tách nội dung theo Cẩm Phả, Hạ Long, Uông Bí và Móng Cái.','Chọn Cẩm Phả, Hạ Long, Uông Bí hoặc Móng Cái trong mục Khu vực học để xem thông tin phù hợp.'],
  ['Website có trang so sánh riêng để người học xem phạm vi sử dụng, học phí và thời gian trước khi đăng ký.','Hãy so sánh phạm vi sử dụng, học phí và thời gian học trước khi đăng ký.'],
  ['Website có trang giải thích riêng về DAT và tiến độ học.','Xem phần DAT để hiểu cách theo dõi tiến độ thực hành trước khi bắt đầu khóa học.'],
  ['Website không thu phí tư vấn hoặc phí môi giới.','Tư vấn không thu phí hoặc phí môi giới.'],
  ['Website tổng hợp và trình bày theo từng nhu cầu:','Thông tin được trình bày theo từng nhu cầu:'],
  ['Website có thể lưu UTM/GCLID khi truy cập từ quảng cáo để đo hiệu quả.','Hệ thống có thể lưu UTM/GCLID khi truy cập từ quảng cáo để đo hiệu quả.']
];

const sharedBehavior=`<script>(function(){document.addEventListener('click',function(e){document.querySelectorAll('.official-nav details[open],.official-mobile-menu[open]').forEach(function(d){if(!d.contains(e.target))d.removeAttribute('open')});var a=e.target&&e.target.closest&&e.target.closest('a[data-affiliate]');if(!a||a.getAttribute('data-affiliate')==='accesstrade-entry-banner')return;if(window.LaiXeTracking&&typeof window.LaiXeTracking.event==='function')window.LaiXeTracking.event('affiliate_click',{affiliate_network:'ACCESSTRADE',affiliate_campaign:a.getAttribute('data-affiliate')||'site_link',link_url:a.href,page_path:location.pathname})})})();</script>`;

const htmlFiles=[];
function walk(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,entry.name);if(entry.isDirectory())walk(p);else if(entry.name.endsWith('.html'))htmlFiles.push(p);}}
walk(out);
let rendered=0;
for(const p of htmlFiles){
  const name=path.basename(p);
  if(redirectNames.has(name)&&path.dirname(p)===out)continue;
  let html=fs.readFileSync(p,'utf8');
  replacements.forEach(([from,to])=>{html=html.split(from).join(to)});

  if(!html.includes('class="official-header"')){
    html=html.replace(/<header\b[\s\S]*?<\/header>/i,'');
    html=html.replace(/(<body\b[^>]*>)/i,`$1${header}`);
  }
  if(!html.includes('class="official-footer"')){
    html=html.replace(/<footer\b[\s\S]*?<\/footer>/i,'');
    const navMatch=html.match(/<nav\b[^>]*class=["'][^"']*(?:sticky-mobile|mobile)[^"']*["'][^>]*>/i);
    if(navMatch)html=html.replace(navMatch[0],`${footer}${navMatch[0]}`);
    else html=html.replace(/<\/body>/i,`${footer}</body>`);
  }else if(!html.includes('href="/uu-dai-hoc-vien.html"')&&!html.includes('href="uu-dai-hoc-vien.html"')){
    html=html.replace(/(<a href=["']\/?chinh-sach-bao-mat\.html["'])/i,'<a href="/uu-dai-hoc-vien.html">Ưu đãi học viên</a>$1');
  }

  html=html.replace(/<nav\b[^>]*class=["'][^"']*\bmobile\b[^"']*["'][^>]*>[\s\S]*?<\/nav>/gi,function(m){return /sticky-mobile/.test(m)?m:''});

  if(p.endsWith(`${path.sep}hoc-ly-thuyet.html`)&&!html.includes('affiliate-learning-cta')){
    const section='<section class="simple-section affiliate-learning-cta"><div class="wrap"><div class="section-title"><span>TIỆN ÍCH</span><h2>Đồ dùng hữu ích cho người đang học và mới lái xe</h2><p class="lead">Gợi ý phụ kiện, đồ chăm sóc xe và các sản phẩm tiện ích.</p></div><div class="actions"><a class="cta secondary" href="/uu-dai-hoc-vien.html">Xem gợi ý & ưu đãi →</a></div></div></section>';
    html=html.replace(/<\/main>/i,`${section}</main>`);
  }
  if(!html.includes("affiliate_campaign:a.getAttribute('data-affiliate')"))html=html.replace(/<\/body>/i,`${sharedBehavior}</body>`);
  fs.writeFileSync(p,html);
  rendered++;
}

const configPath=path.join(out,'assets/site-config.js');
let config=fs.readFileSync(configPath,'utf8');
const shellBlock=`  var staticHome=!!document.querySelector('.institutional-home')&&!!document.querySelector('.official-header')&&!!document.querySelector('.official-footer');\n  if(!staticHome){\n    var shell=document.createElement('script');\n    shell.src='/assets/official-shell.js?v=20260815h';\n    shell.async=true;\n    document.head.appendChild(shell);\n  }\n\n`;
if(!config.includes(shellBlock))throw new Error('site-config shell fallback anchor missing');
config=config.replace(shellBlock,'');
fs.writeFileSync(configPath,config);

const shellPath=path.join(out,'assets/official-shell.js');
if(fs.existsSync(shellPath))fs.rmSync(shellPath);

for(const p of htmlFiles){
  const name=path.basename(p);
  if(redirectNames.has(name)&&path.dirname(p)===out)continue;
  const html=fs.readFileSync(p,'utf8');
  if(!html.includes('class="official-header"')||!html.includes('class="official-footer"'))throw new Error(`Static shell missing: ${path.relative(out,p)}`);
}
if(fs.existsSync(shellPath)||fs.readFileSync(configPath,'utf8').includes('official-shell.js'))throw new Error('official-shell.js still reachable in public artifact');
console.log(JSON.stringify({staticShellPages:rendered,officialShellRemoved:true},null,2));
