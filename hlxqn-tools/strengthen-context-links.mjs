import fs from 'node:fs';
import path from 'node:path';

const root=path.resolve(import.meta.dirname,'..','_site');
function patch(file,anchor,replacement,label,marker){
  const p=path.join(root,file);
  let html=fs.readFileSync(p,'utf8');
  if(marker&&html.includes(marker))return;
  if(html.includes(replacement))return;
  if(!html.includes(anchor))throw new Error(`Context-link anchor missing: ${label}`);
  html=html.replace(anchor,replacement);
  fs.writeFileSync(p,html);
}
function touchArticle(file,oldDate){
  const p=path.join(root,file);
  let html=fs.readFileSync(p,'utf8');
  html=html.replace(`\"dateModified\":\"${oldDate}\"`,'\"dateModified\":\"2026-08-16\"');
  fs.writeFileSync(p,html);
}

patch('buoi-hoc-lai-xe-dau-tien-can-biet-gi.html','<div class="actions"><a class="cta" href="cach-chinh-ghe-guong-vo-lang-khi-hoc-lai-xe.html">Học tiếp: ghế, gương, vô-lăng</a>','<div class="lesson-list"><a href="kinh-nghiem-hoc-lai-xe-lan-dau.html"><b>Kinh nghiệm học lái xe lần đầu</b><small>Checklist và cách chuẩn bị tâm lý trước những buổi thực hành đầu tiên.</small></a></div><div class="actions"><a class="cta" href="cach-chinh-ghe-guong-vo-lang-khi-hoc-lai-xe.html">Học tiếp: ghế, gương, vô-lăng</a>','first lesson to first-time experience','href="kinh-nghiem-hoc-lai-xe-lan-dau.html"');
touchArticle('buoi-hoc-lai-xe-dau-tien-can-biet-gi.html','2026-08-09');

patch('loi-thuong-gap-khi-hoc-sa-hinh.html','<div class="actions"><a class="cta" href="meo-ghep-xe-doc.html">Mẹo ghép xe dọc</a>','<div class="lesson-list"><a href="loi-de-mat-diem-khi-thi-sa-hinh.html"><b>Những lỗi dễ mất điểm khi thi sa hình</b><small>Chuyển từ lỗi lúc luyện sang các tình huống cần đặc biệt tránh khi sát hạch.</small></a></div><div class="actions"><a class="cta" href="meo-ghep-xe-doc.html">Mẹo ghép xe dọc</a>','practice errors to exam point-loss errors','href="loi-de-mat-diem-khi-thi-sa-hinh.html"');
touchArticle('loi-thuong-gap-khi-hoc-sa-hinh.html','2026-08-09');

patch('meo-lai-xe-duong-truong-cho-nguoi-moi.html','<a href="dat-hoc-lai-xe-la-gi.html"><b>Học DAT hiệu quả</b><small>Tận dụng buổi thực hành đường giao thông.</small></a></div>','<a href="dat-hoc-lai-xe-la-gi.html"><b>Học DAT hiệu quả</b><small>Tận dụng buổi thực hành đường giao thông.</small></a><a href="cach-lai-xe-an-toan-khi-troi-mua.html"><b>Lái xe an toàn khi trời mưa</b><small>Giảm tốc, tăng khoảng cách và quan sát mặt đường.</small></a><a href="cach-lai-xe-xuong-doc-an-toan.html"><b>Lái xe xuống dốc an toàn</b><small>Kiểm soát tốc độ và sử dụng phanh hợp lý.</small></a></div>','road driving to rain and downhill guides','href="cach-lai-xe-an-toan-khi-troi-mua.html"');
touchArticle('meo-lai-xe-duong-truong-cho-nguoi-moi.html','2026-08-12');

patch('hoc-lai-xe-so-tu-dong-quang-ninh.html','<a href="dat-hoc-lai-xe-la-gi.html">DAT là gì?<small>Hiểu phần thực hành và cách theo dõi tiến độ.</small></a></div>','<a href="dat-hoc-lai-xe-la-gi.html">DAT là gì?<small>Hiểu phần thực hành và cách theo dõi tiến độ.</small></a><a href="cach-lai-xe-so-tu-dong-cho-nguoi-moi.html">Hướng dẫn xe số tự động cho người mới<small>Làm quen phanh, ga, cần số và tốc độ thấp trước khi luyện bài phức tạp.</small></a></div>','B automatic course to beginner automatic guide','href="cach-lai-xe-so-tu-dong-cho-nguoi-moi.html"');

patch('hoc-thuc-hanh-sa-hinh.html','<a href="meo-can-banh-xe-sa-hinh.html"><b>Mẹo căn bánh xe</b><small>Tạo điểm chuẩn có thể lặp lại.</small></a></div>','<a href="meo-can-banh-xe-sa-hinh.html"><b>Mẹo căn bánh xe</b><small>Tạo điểm chuẩn có thể lặp lại.</small></a><a href="meo-hoc-thuc-hanh-lai-xe-b.html"><b>Mẹo học thực hành hạng B</b><small>Tổng hợp cách luyện tư thế, quan sát và nhịp điều khiển theo từng buổi.</small></a></div>','sa hinh hub to B practical guide','href="meo-hoc-thuc-hanh-lai-xe-b.html"');
touchArticle('hoc-thuc-hanh-sa-hinh.html','2026-08-12');

const sitemapPath=path.join(root,'sitemap.xml');
let sitemap=fs.readFileSync(sitemapPath,'utf8');
const files=['buoi-hoc-lai-xe-dau-tien-can-biet-gi.html','loi-thuong-gap-khi-hoc-sa-hinh.html','meo-lai-xe-duong-truong-cho-nguoi-moi.html','hoc-lai-xe-so-tu-dong-quang-ninh.html','hoc-thuc-hanh-sa-hinh.html','ke-hoach-on-thi-sat-hach-7-ngay.html','quy-dinh-hoc-phi-thoi-gian-dat.html'];
for(const file of files){
  const escaped=file.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const re=new RegExp(`(<loc>https://hoclaixequangninh\\.vn/${escaped}<\\/loc><lastmod>)[^<]+(<\\/lastmod>)`);
  if(!re.test(sitemap))throw new Error(`Sitemap date anchor missing: ${file}`);
  sitemap=sitemap.replace(re,'$12026-08-16$2');
}
fs.writeFileSync(sitemapPath,sitemap);
console.log(JSON.stringify({contextualLinks:6,updatedPages:7,lastmod:'2026-08-16',idempotent:true},null,2));
