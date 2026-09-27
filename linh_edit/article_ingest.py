from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .news_ingest import NewsScene, apply_news_scenes
from .project import ProjectState

MAX_HTML_BYTES = 5 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ArticleData:
    url: str
    title: str
    description: str
    paragraphs: tuple[str, ...]
    image_urls: tuple[str, ...]
    local_images: tuple[str, ...] = ()

    @property
    def source_text(self) -> str:
        values = [self.title, self.description, *self.paragraphs]
        return "\n\n".join(value for value in values if value).strip()


class _ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.paragraphs: list[str] = []
        self.images: list[str] = []
        self._stack: list[str] = []
        self._text: list[str] = []
        self._paragraph_depth = 0
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = {str(k).lower(): str(v or "") for k, v in attrs}
        self._stack.append(tag)
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"}:
            self._skip_depth += 1
        if tag == "p" and self._skip_depth == 0:
            self._paragraph_depth += 1
            self._text = []
        if tag == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            content = values.get("content", "").strip()
            if key and content and key not in self.meta:
                self.meta[key] = content
        if tag == "img":
            src = (
                values.get("data-src")
                or values.get("data-original")
                or values.get("src")
                or ""
            ).strip()
            if src:
                self.images.append(src)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "p" and self._paragraph_depth:
            text = _clean(" ".join(self._text))
            if len(text) >= 24:
                self.paragraphs.append(text)
            self._paragraph_depth = max(0, self._paragraph_depth - 1)
            self._text = []
        if tag in {"script", "style", "noscript", "svg", "nav", "footer"} and self._skip_depth:
            self._skip_depth -= 1
        if self._stack:
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._stack and self._stack[-1] == "title":
            self.title_parts.append(data)
        if self._paragraph_depth:
            self._text.append(data)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return tuple(result)


def _validate_public_http_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL bài viết phải dùng http/https và có tên miền hợp lệ.")
    host = parsed.hostname
    try:
        default_port = 443 if parsed.scheme == "https" else 80
        addresses = {info[4][0] for info in socket.getaddrinfo(host, parsed.port or default_port)}
    except OSError as exc:
        raise ValueError(f"Không phân giải được tên miền: {host}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError("URL trỏ vào mạng riêng/nội bộ nên không được tải.")
    return parsed.geturl()


def parse_article_html(html: str, url: str) -> ArticleData:
    parser = _ArticleParser()
    parser.feed(html)

    title = _clean(
        parser.meta.get("og:title")
        or parser.meta.get("twitter:title")
        or " ".join(parser.title_parts)
    )
    description = _clean(
        parser.meta.get("og:description")
        or parser.meta.get("description")
        or parser.meta.get("twitter:description")
        or ""
    )
    paragraphs = _dedupe(parser.paragraphs)

    image_candidates = []
    for key in ("og:image", "twitter:image", "twitter:image:src"):
        value = parser.meta.get(key)
        if value:
            image_candidates.append(value)
    image_candidates.extend(parser.images)
    image_urls = _dedupe(
        urljoin(url, item)
        for item in image_candidates
        if not item.lower().startswith(("data:", "javascript:"))
    )

    if not title and paragraphs:
        title = paragraphs[0][:120]
    if not title:
        raise ValueError("Không tìm thấy tiêu đề bài viết.")
    if not paragraphs and not description:
        raise ValueError("Không tìm thấy phần nội dung có thể biên tập.")

    return ArticleData(
        url=url,
        title=title,
        description=description,
        paragraphs=paragraphs[:40],
        image_urls=image_urls[:30],
    )


def _read_limited(response, maximum: int) -> bytes:
    payload = response.read(maximum + 1)
    if len(payload) > maximum:
        raise ValueError("Nội dung tải về vượt giới hạn an toàn.")
    return payload


def _image_extension(content_type: str, url: str) -> str:
    content_type = content_type.lower()
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    if "gif" in content_type:
        return ".gif"
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return suffix
    return ".jpg"


def _download_image(url: str, target_dir: Path, index: int) -> str | None:
    safe_url = _validate_public_http_url(url)
    request = Request(
        safe_url,
        headers={
            "User-Agent": "Mozilla/5.0 LinhEdit/1.1",
            "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*;q=0.6",
        },
    )
    try:
        with urlopen(request, timeout=12) as response:
            final_url = _validate_public_http_url(response.geturl())
            content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0]
            if not content_type.lower().startswith("image/"):
                return None
            payload = _read_limited(response, MAX_IMAGE_BYTES)
    except Exception:
        return None
    if len(payload) < 512:
        return None

    digest = hashlib.sha256((final_url + str(index)).encode("utf-8")).hexdigest()[:12]
    extension = _image_extension(content_type, final_url)
    target = target_dir / f"article_{index:02d}_{digest}{extension}"
    temp = target.with_suffix(target.suffix + ".partial")
    temp.write_bytes(payload)
    temp.replace(target)
    return str(target.resolve())


def fetch_article(
    url: str,
    workspace: Path,
    *,
    max_images: int = 8,
) -> ArticleData:
    safe_url = _validate_public_http_url(url)
    request = Request(
        safe_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LinhEdit/1.1",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=15) as response:
        final_url = _validate_public_http_url(response.geturl())
        content_type = str(response.headers.get("Content-Type", ""))
        if "html" not in content_type.lower():
            raise ValueError("URL không trả về trang HTML.")
        raw = _read_limited(response, MAX_HTML_BYTES)
        charset = response.headers.get_content_charset() or "utf-8"

    html = raw.decode(charset, errors="replace")
    article = parse_article_html(html, final_url)

    image_dir = workspace.expanduser().resolve() / "assets" / "article_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    local: list[str] = []
    for index, image_url in enumerate(article.image_urls, start=1):
        if len(local) >= max(1, min(12, max_images)):
            break
        path = _download_image(image_url, image_dir, index)
        if path:
            local.append(path)

    return ArticleData(
        url=article.url,
        title=article.title,
        description=article.description,
        paragraphs=article.paragraphs,
        image_urls=article.image_urls,
        local_images=tuple(local),
    )


def article_scenes(article: ArticleData, *, target_scenes: int = 7) -> list[NewsScene]:
    target = max(4, min(10, target_scenes))
    paragraphs = [item for item in article.paragraphs if len(item.split()) >= 6]
    if article.description and article.description not in paragraphs:
        paragraphs.insert(0, article.description)
    if not paragraphs:
        paragraphs = [article.description or article.title]

    selected: list[str] = []
    if len(paragraphs) <= target:
        selected = paragraphs
    else:
        for index in range(target):
            pos = round(index * (len(paragraphs) - 1) / max(1, target - 1))
            value = paragraphs[pos]
            if value not in selected:
                selected.append(value)

    scenes: list[NewsScene] = []
    host = (urlparse(article.url).hostname or "BÀI VIẾT").upper()
    for index, paragraph in enumerate(selected):
        title = article.title if index == 0 else " ".join(paragraph.split()[:9])
        summary_words = paragraph.split()[:18]
        summary = " ".join(summary_words)
        if len(paragraph.split()) > 18:
            summary = summary.rstrip(" ,.;:—-") + "…"
        scenes.append(
            NewsScene(
                title=title,
                voice_text=paragraph,
                summary=summary,
                badge=host if index == 0 else "",
                role="detail",
            )
        )
    return scenes


def apply_article(
    project: ProjectState,
    article: ArticleData,
    *,
    total_seconds: float | None = None,
) -> ProjectState:
    if not article.local_images:
        raise ValueError("Bài viết chưa tải được ảnh hợp lệ.")
    scenes = article_scenes(article)
    return apply_news_scenes(
        project,
        scenes,
        images=article.local_images,
        total_seconds=total_seconds,
        source_mode="ARTICLE_URL",
        source_text=article.source_text,
        source_url=article.url,
        title=article.title,
    )
