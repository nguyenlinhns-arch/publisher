import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const domain = 'https://hoclaixequangninh.vn';
const utility = new Set(['404.html', 'lich-sat-hach-lai-xe.html', 'lien-he.html', 'dieu-khoan-su-dung.html', 'chinh-sach-bao-mat.html', 'gioi-thieu.html', 'tin-tuc.html']);
const files = fs.readdirSync(root).filter(file => file.endsWith('.html')).sort();
const errors = [];
const warnings = [];
const seenCanonical = new Map();

const text = html => html
  .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
  .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
  .replace(/<[^>]+>/g, ' ')
  .replace(/&[^;]+;/g, ' ')
  .replace(/\s+/g, ' ')
  .trim();

function existsTarget(href) {
  const clean = href.split('#')[0].split('?')[0];
  if (!clean) return true;
  const relative = clean.startsWith('/') ? clean.slice(1) : clean;
  const target = relative === '' ? 'index.html' : relative.endsWith('/') ? `${relative}index.html` : relative;
  return fs.existsSync(path.join(root, target));
}

for (const file of files) {
  const html = fs.readFileSync(path.join(root, file), 'utf8');
  const canonical = (html.match(/<link\s+rel="canonical"\s+href="([^"]+)"/i) || [])[1];
  const title = (html.match(/<title>([\s\S]*?)<\/title>/i) || [])[1];
  const description = (html.match(/<meta\s+name="description"\s+content="([^"]+)"/i) || [])[1];

  if (!title) errors.push(`${file}: thiếu title`);
  if (!description && !utility.has(file)) errors.push(`${file}: thiếu meta description`);
  if (!/<h1\b/i.test(html) && !utility.has(file)) errors.push(`${file}: thiếu H1`);
  if (!canonical) errors.push(`${file}: thiếu canonical`);
  if (canonical && !canonical.startsWith(domain)) errors.push(`${file}: canonical ngoài tên miền (${canonical})`);
  if (canonical) {
    if (seenCanonical.has(canonical) && !utility.has(file)) errors.push(`${file}: canonical trùng ${seenCanonical.get(canonical)}`);
    seenCanonical.set(canonical, file);
  }
  if (!html.includes('application/ld+json') && !utility.has(file)) errors.push(`${file}: thiếu schema`);
  if (!html.includes('BreadcrumbList') && !utility.has(file)) errors.push(`${file}: thiếu BreadcrumbList`);
  if (!html.includes('assets/mobile-v2.css') && !utility.has(file)) errors.push(`${file}: thiếu CSS mobile`);
  if (!html.includes('assets/site-runtime.js')) errors.push(`${file}: thiếu tracking/CTA dùng chung`);
  if (/nguyenlinhns-arch\.github\.io\/publisher/i.test(html)) errors.push(`${file}: còn URL GitHub Pages cũ`);

  const wordCount = text(html).split(/\s+/).filter(Boolean).length;
  if (!utility.has(file) && wordCount < 250) warnings.push(`${file}: nội dung còn mỏng (${wordCount} từ)`);

  for (const match of html.matchAll(/<a\b[^>]*href="([^"]+)"/gi)) {
    const href = match[1];
    if (/^(https?:|tel:|mailto:|javascript:|#)/i.test(href)) continue;
    if (!existsTarget(href)) errors.push(`${file}: liên kết nội bộ hỏng ${href}`);
  }
  for (const match of html.matchAll(/<img\b[^>]*src="([^"]+)"/gi)) {
    const src = match[1];
    if (/^https?:/i.test(src)) errors.push(`${file}: ảnh còn phụ thuộc máy chủ ngoài ${src}`);
    else if (!fs.existsSync(path.join(root, src))) errors.push(`${file}: thiếu ảnh ${src}`);
  }
}

const sitemap = fs.readFileSync(path.join(root, 'sitemap.xml'), 'utf8');
const sitemapUrls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map(match => match[1]);
if (sitemapUrls.length !== 60) errors.push(`sitemap: cần 60 URL, hiện có ${sitemapUrls.length}`);
if (new Set(sitemapUrls).size !== sitemapUrls.length) errors.push('sitemap: có URL trùng');
for (const url of sitemapUrls) {
  const relative = url.replace(`${domain}/`, '');
  const target = relative === '' ? 'index.html' : relative.endsWith('/') ? `${relative}index.html` : relative;
  if (!fs.existsSync(path.join(root, target))) errors.push(`sitemap: URL không có tệp ${url}`);
}

const lead = fs.readFileSync(path.join(root, 'assets/site-runtime.js'), 'utf8');
const ackIndex = lead.indexOf('const ack=await confirmLead');
const conversionIndex = lead.indexOf("fireAdsConversion(CONFIG.GOOGLE_ADS_CONVERSION_LABEL");
if (ackIndex < 0 || conversionIndex < ackIndex) errors.push('site-runtime: conversion chưa được khóa sau xác nhận Sheet');
if (!lead.includes("event('lead_submit_unconfirmed'")) errors.push('site-runtime: thiếu nhánh không xác nhận được');
if (!lead.includes('function normalizeLicense')) errors.push('site-runtime: thiếu chuẩn hóa hạng bằng cho Google Sheet');

console.log(JSON.stringify({pages: files.length, sitemapUrls: sitemapUrls.length, errors, warnings}, null, 2));
if (errors.length) process.exit(1);
