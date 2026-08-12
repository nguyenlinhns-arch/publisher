import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const site = 'https://hoclaixequangninh.vn';
const modified = '2026-08-12';
const skipped = new Set(['404.html', 'lich-sat-hach-lai-xe.html']);

const decode = (value = '') => value
  .replace(/<[^>]+>/g, ' ')
  .replace(/&amp;/g, '&')
  .replace(/&quot;/g, '"')
  .replace(/&#39;/g, "'")
  .replace(/&nbsp;/g, ' ')
  .replace(/\s+/g, ' ')
  .trim();

const attr = (html, pattern) => decode((html.match(pattern) || [])[1] || '');
const esc = value => String(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;');

function pageType(file) {
  if (file === 'tin-tuc.html' || file === 'hoc-ly-thuyet.html') return 'CollectionPage';
  if (file === 'lien-he.html') return 'ContactPage';
  if (file === 'gioi-thieu.html') return 'AboutPage';
  if (/^(chinh-sach-bao-mat|dieu-khoan-su-dung)/.test(file)) return 'WebPage';
  if (/^(hoc-(bang-b|c1|a1)-quang-ninh|hoc-lai-xe-(cam-pha|ha-long|uong-bi|mong-cai)|trung-tam-quang-hanh)/.test(file)) return 'WebPage';
  return 'Article';
}

let schemaAdded = 0;
let breadcrumbsAdded = 0;
let mobileCssAdded = 0;
let openGraphAdded = 0;

for (const file of fs.readdirSync(root).filter(name => name.endsWith('.html')).sort()) {
  if (skipped.has(file)) continue;
  const full = path.join(root, file);
  let html = fs.readFileSync(full, 'utf8');

  const expectedUrl = file === 'index.html' ? `${site}/` : `${site}/${file}`;
  html = html.replaceAll('https://nguyenlinhns-arch.github.io/publisher/', `${site}/`);

  if (!html.includes('assets/mobile-v2.css')) {
    html = html.replace('<link rel="stylesheet" href="assets/style.css">', '<link rel="stylesheet" href="assets/style.css"><link rel="stylesheet" href="assets/mobile-v2.css">');
    mobileCssAdded++;
  }

  const title = attr(html, /<title>([\s\S]*?)<\/title>/i) || 'Học Lái Xe Quảng Ninh';
  const heading = attr(html, /<h1[^>]*>([\s\S]*?)<\/h1>/i) || title;
  const description = attr(html, /<meta\s+name="description"\s+content="([^"]*)"/i);
  const canonical = attr(html, /<link\s+rel="canonical"\s+href="([^"]+)"/i) || expectedUrl;

  if (!/<meta\s+property="og:url"/i.test(html)) {
    const og = `<meta property="og:type" content="${pageType(file) === 'Article' ? 'article' : 'website'}"><meta property="og:locale" content="vi_VN"><meta property="og:site_name" content="Học Lái Xe Quảng Ninh"><meta property="og:title" content="${esc(title)}"><meta property="og:description" content="${esc(description)}"><meta property="og:url" content="${esc(canonical)}"><meta property="og:image" content="${site}/assets/thumbnail-tuyen-sinh-lai-xe.jpg">`;
    html = html.replace('</head>', `${og}</head>`);
    openGraphAdded++;
  }

  const type = pageType(file);
  if (!html.includes('application/ld+json')) {
    const schema = type === 'Article'
      ? {
          '@context': 'https://schema.org',
          '@type': 'Article',
          headline: heading,
          description,
          datePublished: '2026-08-09',
          dateModified: modified,
          inLanguage: 'vi-VN',
          mainEntityOfPage: canonical,
          author: {'@type': 'Organization', name: 'Học Lái Xe Quảng Ninh'},
          publisher: {'@type': 'Organization', name: 'Học Lái Xe Quảng Ninh', url: `${site}/`}
        }
      : {
          '@context': 'https://schema.org',
          '@type': type,
          name: heading,
          description,
          url: canonical,
          inLanguage: 'vi-VN',
          isPartOf: {'@type': 'WebSite', name: 'Học Lái Xe Quảng Ninh', url: `${site}/`}
        };
    html = html.replace('</head>', `<script type="application/ld+json">${JSON.stringify(schema)}</script></head>`);
    schemaAdded++;
  }

  if (!html.includes('BreadcrumbList')) {
    const breadcrumb = {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      itemListElement: [
        {'@type': 'ListItem', position: 1, name: 'Học Lái Xe Quảng Ninh', item: `${site}/`},
        {'@type': 'ListItem', position: 2, name: heading, item: canonical}
      ]
    };
    html = html.replace('</head>', `<script type="application/ld+json">${JSON.stringify(breadcrumb)}</script></head>`);
    breadcrumbsAdded++;
  }

  fs.writeFileSync(full, html);
}

console.log(JSON.stringify({schemaAdded, breadcrumbsAdded, mobileCssAdded, openGraphAdded}));
