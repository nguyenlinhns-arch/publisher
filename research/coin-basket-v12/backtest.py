from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
WORK = ROOT / "work_book_affiliate"
OUT.mkdir(parents=True, exist_ok=True)
WORK.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1080, 1920, 30
BG = (10, 10, 11)
WHITE = (245, 242, 234)
GOLD = (222, 170, 68)
RED = (197, 54, 48)
GREEN = (72, 194, 111)
MUTED = (177, 174, 165)

UA = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/150 Safari/537.36",
    "Accept": "*/*",
}
S = requests.Session()
S.headers.update(UA)


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print("+", " ".join(str(x) for x in cmd), flush=True)
    return subprocess.run(cmd, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return
    subprocess.run(["sudo", "apt-get", "update"], check=True)
    subprocess.run(["sudo", "apt-get", "install", "-y", "ffmpeg"], check=True)


def download(url: str, dest: Path, min_bytes: int = 100_000, referer: str | None = None) -> Path:
    if dest.exists() and dest.stat().st_size >= min_bytes:
        return dest
    headers = dict(UA)
    if referer:
        headers["Referer"] = referer
    last = None
    for attempt in range(4):
        try:
            with S.get(url, headers=headers, stream=True, timeout=(20, 180), allow_redirects=True) as r:
                r.raise_for_status()
                total = 0
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            total += len(chunk)
                if total < min_bytes:
                    raise RuntimeError(f"Downloaded only {total} bytes from {url}")
                print(f"downloaded {dest.name}: {total/1024/1024:.1f} MB <- {r.url}")
                return dest
        except Exception as e:
            last = e
            print(f"download attempt {attempt+1} failed: {url}: {e}")
            time.sleep(2 + attempt * 2)
    raise RuntimeError(f"download failed {url}: {last}")


def pexels_video(video_id: int, dest: Path) -> Path:
    # Official Pexels free-download endpoint. It redirects to the current MP4 rendition.
    urls = [f"https://www.pexels.com/download/video/{video_id}/"]
    # Known direct fallback for one of the main clips.
    if video_id == 11530055:
        urls.append("https://videos.pexels.com/video-files/11530055/11530055-uhd_3840_2160_25fps.mp4")
    last = None
    for u in urls:
        try:
            return download(u, dest, min_bytes=800_000, referer=f"https://www.pexels.com/video/{video_id}/")
        except Exception as e:
            last = e
    raise RuntimeError(str(last))


def hf_mixkit(path: str, dest: Path) -> Path:
    u = "https://huggingface.co/datasets/FastVideo/Mixkit-Src/resolve/main/" + path + "?download=true"
    return download(u, dest, min_bytes=700_000)


def commons_file(name: str, dest: Path) -> Path:
    u = "https://commons.wikimedia.org/wiki/Special:Redirect/file/" + requests.utils.quote(name, safe="")
    return download(u, dest, min_bytes=30_000)


def fetch_alphabooks_cover(dest: Path) -> Path | None:
    page = "https://shop.alphabooks.vn/chet-vi-chung-khoan-cau-chuyen-ve-nha-dau-tu-chung-khoan-vi-dai-nhat-moi-thoi-dai-jesse-livermore-p30249939.html"
    try:
        r = S.get(page, timeout=30)
        r.raise_for_status()
        body = html.unescape(r.text)
        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        ]
        img = None
        for p in patterns:
            m = re.search(p, body, re.I)
            if m:
                img = urljoin(page, m.group(1))
                break
        if img:
            return download(img, dest, min_bytes=20_000, referer=page)
    except Exception as e:
        print("AlphaBooks cover fetch skipped:", e)
    return None


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def fit_lines(draw: ImageDraw.ImageDraw, text: str, max_width: int, fnt: ImageFont.FreeTypeFont) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for word in words:
        test = (cur + " " + word).strip()
        box = draw.textbbox((0, 0), test, font=fnt)
        if box[2] - box[0] <= max_width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def overlay_png(path: Path, headline: str = "", sub: str = "", accent_words: list[str] | None = None,
                y: int = 1140, align: str = "left", tag: str | None = None, darken: float = 0.18) -> Path:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if darken > 0:
        d.rectangle((0, 0, W, H), fill=(0, 0, 0, int(255 * darken)))
    # subtle bottom gradient
    for yy in range(max(0, y - 180), H):
        a = int(min(145, max(0, (yy - (y - 180)) / 520 * 145)))
        d.rectangle((0, yy, W, yy + 1), fill=(0, 0, 0, a))
    if tag:
        ft = font(34, True)
        d.rounded_rectangle((72, 92, 72 + 470, 154), radius=20, fill=(15, 15, 16, 190), outline=(*GOLD, 220), width=2)
        d.text((94, 104), tag, font=ft, fill=(*GOLD, 255))
    if headline:
        fh = font(64, True)
        lines = fit_lines(d, headline, 900, fh)
        lh = 80
        total_h = len(lines) * lh
        if align == "center":
            yy = y - total_h // 2
        else:
            yy = y
        for line in lines:
            box = d.textbbox((0, 0), line, font=fh)
            tw = box[2] - box[0]
            x = (W - tw) // 2 if align == "center" else 72
            d.text((x + 3, yy + 4), line, font=fh, fill=(0, 0, 0, 190))
            color = GOLD if accent_words and any(w.lower() in line.lower() for w in accent_words) else WHITE
            d.text((x, yy), line, font=fh, fill=(*color, 255))
            yy += lh
    if sub:
        fs = font(35, False)
        lines = fit_lines(d, sub, 900, fs)
        yy = min(H - 260, y + 205)
        for line in lines:
            d.text((74, yy), line, font=fs, fill=(*MUTED, 255))
            yy += 50
    im.save(path)
    return path


def make_cover_card(cover_path: Path | None, out: Path) -> Path:
    canvas = Image.new("RGB", (W, H), BG)
    if cover_path and cover_path.exists():
        c = Image.open(cover_path).convert("RGB")
        # background from cover, blurred and darkened
        bg = c.copy()
        bg.thumbnail((1600, 1600))
        bw, bh = bg.size
        scale = max(W / bw, H / bh)
        bg = bg.resize((int(bw * scale), int(bh * scale)), Image.Resampling.LANCZOS)
        left, top = (bg.width - W) // 2, (bg.height - H) // 2
        bg = bg.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(32))
        shade = Image.new("RGB", (W, H), (0, 0, 0))
        canvas = Image.blend(bg, shade, 0.58)
        c.thumbnail((720, 1120), Image.Resampling.LANCZOS)
        x, y = (W - c.width) // 2, 270
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.rounded_rectangle((x + 25, y + 35, x + c.width + 25, y + c.height + 35), radius=18, fill=(0, 0, 0, 150))
        shadow = shadow.filter(ImageFilter.GaussianBlur(20))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow).convert("RGB")
        canvas.paste(c, (x, y))
    else:
        d = ImageDraw.Draw(canvas)
        d.rectangle((180, 260, 900, 1420), fill=(22, 21, 18), outline=GOLD, width=5)
        d.text((250, 390), "RICHARD SMITTEN", font=font(38, False), fill=MUTED)
        d.text((250, 570), "CHẾT VÌ", font=font(88, True), fill=WHITE)
        d.text((250, 690), "CHỨNG KHOÁN", font=font(72, True), fill=GOLD)
        d.text((250, 870), "JESSE LIVERMORE", font=font(44, True), fill=WHITE)
    d = ImageDraw.Draw(canvas)
    d.text((W//2, 1570), "CHẾT VÌ CHỨNG KHOÁN", anchor="mm", font=font(52, True), fill=WHITE)
    d.text((W//2, 1640), "RICHARD SMITTEN", anchor="mm", font=font(32, False), fill=GOLD)
    canvas.save(out, quality=96)
    return out


def make_chart(out: Path, mode: int) -> Path:
    im = Image.new("RGB", (W, H), (8, 12, 13))
    d = ImageDraw.Draw(im)
    # grid
    for x in range(90, W - 50, 110):
        d.line((x, 360, x, 1510), fill=(29, 36, 37), width=1)
    for y in range(430, 1510, 120):
        d.line((80, y, W - 55, y), fill=(29, 36, 37), width=1)
    # deterministic candlesticks
    vals = [0, 12, 5, 18, 15, 28, 22, 35, 33, 48, 44, 61, 59, 76, 69, 91, 88, 105, 101, 121, 114, 135]
    if mode == 3:
        vals = [65, 72, 78, 73, 84, 91, 86, 93, 88, 79, 71, 67, 60, 55, 50, 47, 43, 39, 42, 36, 33, 31]
    x0, step = 105, 40
    base = 1330
    scale = 5.5
    for i, v in enumerate(vals):
        x = x0 + i * step
        op = base - v * scale
        cl = op - (18 if i % 3 else -12)
        hi = min(op, cl) - 28
        lo = max(op, cl) + 28
        col = GREEN if cl < op else RED
        d.line((x, hi, x, lo), fill=col, width=3)
        d.rectangle((x - 9, min(op, cl), x + 9, max(op, cl) + 1), fill=col)
    if mode == 1:
        pivot_y = base - 76 * scale
        d.line((90, pivot_y, 995, pivot_y), fill=GOLD, width=3)
        d.ellipse((x0+13*step-34, base-91*scale-34, x0+13*step+34, base-91*scale+34), outline=GOLD, width=5)
        title, sub, color = "1. CHỜ GIÁ XÁC NHẬN", "Không đoán trước cú bứt phá.", GOLD
    elif mode == 2:
        for idx in (12, 15, 18):
            x = x0 + idx * step
            y = base - vals[idx] * scale
            d.ellipse((x-28, y-28, x+28, y+28), outline=GREEN, width=5)
        title, sub, color = "2. CHỈ GIA TĂNG VỊ THẾ THẮNG", "Mua thêm khi lệnh đang có lợi nhuận.", GREEN
    else:
        entry_y = base - vals[8] * scale
        stop_y = entry_y + 155
        d.line((80, entry_y, 1000, entry_y), fill=GREEN, width=3)
        d.line((80, stop_y, 1000, stop_y), fill=RED, width=4)
        d.text((740, entry_y-55), "ĐIỂM VÀO", font=font(30, True), fill=GREEN)
        d.text((740, stop_y+12), "STOP-LOSS", font=font(30, True), fill=RED)
        title, sub, color = "3. GIỚI HẠN KHOẢN LỖ TRƯỚC KHI MUA", "Rủi ro phải được xác định trước lệnh.", RED
    d.text((75, 145), title, font=font(54, True), fill=color)
    d.text((76, 225), sub, font=font(34, False), fill=WHITE)
    d.text((75, 1660), "MINH HỌA NGUYÊN TẮC GIAO DỊCH — KHÔNG PHẢI KHUYẾN NGHỊ MUA BÁN", font=font(25, False), fill=MUTED)
    im.save(out, quality=96)
    return out


def duration(src: Path) -> float:
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(src)])
    try:
        return float(p.stdout.strip().splitlines()[-1])
    except Exception:
        return 10.0


def video_segment(src: Path, start: float, dur: float, overlay: Path, out: Path, speed: float = 1.0) -> Path:
    src_dur = duration(src)
    effective = dur * speed
    if src_dur <= effective + 0.5:
        start = 0
    else:
        start = min(max(0, start), src_dur - effective - 0.2)
    filter0 = (
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        "eq=contrast=1.07:saturation=0.78:brightness=-0.025,"
        "unsharp=5:5:0.35:5:5:0.0,setpts=PTS-STARTPTS"
    )
    if speed != 1.0:
        filter0 += f",setpts=PTS/{speed}"
    fc = filter0 + "[b];[b][1:v]overlay=0:0:format=auto,format=yuv420p[v]"
    run([
        "ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(src), "-loop", "1", "-i", str(overlay),
        "-filter_complex", fc, "-map", "[v]", "-t", f"{dur:.3f}", "-an", "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)
    ])
    return out


def still_segment(src: Path, dur: float, overlay: Path, out: Path, zoom: float = 0.00055) -> Path:
    frames = int(dur * FPS)
    zexpr = f"min(zoom+{zoom:.6f},1.10)"
    fc = (
        f"[0:v]scale=1500:2300:force_original_aspect_ratio=increase,"
        f"zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},"
        "eq=contrast=1.06:saturation=0.72:brightness=-0.04[b];"
        "[b][1:v]overlay=0:0:format=auto,format=yuv420p[v]"
    )
    run([
        "ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(src), "-loop", "1", "-i", str(overlay),
        "-filter_complex", fc, "-map", "[v]", "-frames:v", str(frames), "-an", "-r", str(FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", str(out)
    ])
    return out


def main() -> None:
    ensure_ffmpeg()
    # Download real book footage. Every failure is tolerated as long as at least 3 clips survive.
    candidates: list[tuple[str, Path, callable]] = []
    for vid, name in [
        (9115655, "book_vertical_library.mp4"),
        (11530055, "book_candle_hands.mp4"),
        (6981525, "book_warm_pages.mp4"),
        (7055351, "book_dark_pages.mp4"),
        (11530072, "book_opening_candle.mp4"),
    ]:
        p = WORK / name
        try:
            pexels_video(vid, p)
            candidates.append((name, p, None))
        except Exception as e:
            print("Pexels candidate failed", vid, e)
    for rel, name in [
        ("Woman/mixkit-a-woman-gently-turning-the-pages-of-a-book-50731_clip_1.mp4", "mixkit_page_turn.mp4"),
        ("Woman/mixkit-a-young-woman-reading-a-book-with-interest-50716_clip_1.mp4", "mixkit_reading.mp4"),
        ("People/mixkit-a-person-reading-a-book-close-up-1724_clip_1.mp4", "mixkit_closeup.mp4"),
    ]:
        if len(candidates) >= 5:
            break
        p = WORK / name
        try:
            hf_mixkit(rel, p)
            candidates.append((name, p, None))
        except Exception as e:
            print("Mixkit mirror candidate failed", rel, e)
    if len(candidates) < 3:
        (OUT / "BUILD_FAILED.txt").write_text(
            "Không tải đủ tối thiểu 3 video stock thật để dựng.\n" + "\n".join(n for n,_,_ in candidates), encoding="utf-8")
        return

    clips = [p for _, p, _ in candidates]
    # Images / official product cover.
    cover = fetch_alphabooks_cover(WORK / "alphabooks_cover.jpg")
    img1907 = commons_file("1907 Panic.png", WORK / "1907_panic.png")
    img1929 = commons_file("Crowds gathering outside New York Stock Exchange.jpg", WORK / "1929_crowd.jpg")
    jesse = commons_file("Jesse Livermore (c. 1923) (cropped).jpg", WORK / "jesse_livermore.jpg")

    cover_card = make_cover_card(cover, WORK / "cover_card.jpg")
    chart1 = make_chart(WORK / "chart1.jpg", 1)
    chart2 = make_chart(WORK / "chart2.jpg", 2)
    chart3 = make_chart(WORK / "chart3.jpg", 3)

    overlays: dict[str, Path] = {}
    def ov(key: str, *args, **kwargs) -> Path:
        p = WORK / f"ov_{key}.png"
        overlays[key] = overlay_png(p, *args, **kwargs)
        return p

    ov("hook1", "MỘT THIÊN TÀI TỪNG THẮNG CẢ THỊ TRƯỜNG…", accent_words=["THẮNG"], y=1260)
    ov("hook2", "…NHƯNG CUỐI CÙNG THUA CHÍNH MÌNH.", accent_words=["THUA"], y=1290)
    ov("cover", "", "", y=1450, darken=0.02)
    ov("timeline", "1907  →  1929  →  QUẢN TRỊ TIỀN  →  SUY SỤP", accent_words=["1907", "1929"], y=1260, align="center")
    ov("1907", "THE CRASH OF 1907", sub="CHAPTER 4", accent_words=["1907"], y=1320, tag="1907")
    ov("1929", "THE CRASH OF 1929", sub="CHAPTER 10", accent_words=["1929"], y=1320, tag="1929")
    ov("jesse", "HIỂU XU HƯỚNG.  BIẾT CHỜ ĐỢI.", sub="JESSE LIVERMORE", accent_words=["CHỜ ĐỢI"], y=1280)
    ov("ch11", "WHEN TO HOLD AND WHEN TO FOLD", sub="CHAPTER 11", accent_words=["HOLD", "FOLD"], y=1320)
    ov("ch12", "LIVERMORE'S MONEY-MANAGEMENT RULES", sub="CHAPTER 12", accent_words=["MONEY-MANAGEMENT"], y=1260)
    ov("ch13", "LIVERMORE'S LUCK SOURS", sub="CHAPTER 13", accent_words=["LUCK SOURS"], y=1320, darken=0.34)
    ov("blank", "", "", y=1500, darken=0.02)
    ov("end", "ĐỪNG TRẢ HỌC PHÍ BẰNG CẢ TÀI KHOẢN.", sub="CHẾT VÌ CHỨNG KHOÁN  •  LINK SÁCH Ở BIO / BÌNH LUẬN GHIM", accent_words=["CẢ TÀI KHOẢN"], y=1270)

    # Choose footage by visual role; reuse with different in-points when needed.
    a, b, c = clips[0], clips[1], clips[2]
    d = clips[3] if len(clips) > 3 else b
    e = clips[4] if len(clips) > 4 else a

    segs: list[Path] = []
    def v(idx, src, start, dur, overlay, speed=1.0):
        p = WORK / f"seg_{idx:02d}.mp4"; video_segment(src, start, dur, overlay, p, speed); segs.append(p)
    def s(idx, src, dur, overlay, zoom=0.00055):
        p = WORK / f"seg_{idx:02d}.mp4"; still_segment(src, dur, overlay, p, zoom); segs.append(p)

    v(1, a, 0.0, 3.0, overlays["hook1"], 0.92)
    v(2, a, 3.2, 3.0, overlays["hook2"], 0.94)
    s(3, cover_card, 4.0, overlays["cover"], 0.00035)
    v(4, c, 0.8, 5.0, overlays["timeline"], 0.90)
    s(5, img1907, 6.0, overlays["1907"], 0.00065)
    s(6, img1929, 6.0, overlays["1929"], 0.00055)
    s(7, jesse, 6.0, overlays["jesse"], 0.00045)
    v(8, d, 1.0, 5.0, overlays["ch11"], 0.86)
    v(9, e, 2.0, 5.0, overlays["ch12"], 0.88)
    v(10, b, 4.0, 5.0, overlays["ch13"], 0.82)
    s(11, chart1, 6.0, overlays["blank"], 0.00028)
    s(12, chart2, 6.0, overlays["blank"], 0.00028)
    s(13, chart3, 5.0, overlays["blank"], 0.00028)
    v(14, a, 0.8, 4.0, overlays["end"], 0.82)

    concat = WORK / "concat.txt"
    concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in segs) + "\n", encoding="utf-8")
    final = OUT / "Chet_Vi_Chung_Khoan_Affiliate_Silent_V1_1080x1920.mp4"
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-movflags", "+faststart", str(final)
    ])

    # Small preview for easy review.
    preview = OUT / "Chet_Vi_Chung_Khoan_Affiliate_Silent_V1_720x1280.mp4"
    run([
        "ffmpeg", "-y", "-i", str(final), "-vf", "scale=720:1280", "-an", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(preview)
    ])

    src_txt = OUT / "SOURCES_AND_LICENSE_NOTES.txt"
    src_txt.write_text(
        "VIDEO AFFILIATE SÁCH — BẢN IM TIẾNG\n\n"
        "Footage chính (Pexels, các trang ghi Free to use):\n"
        "- https://www.pexels.com/video/a-person-flipping-pages-of-a-book-9115655/\n"
        "- https://www.pexels.com/video/close-up-of-male-hands-flipping-pages-of-an-old-book-11530055/\n"
        "- https://www.pexels.com/video/person-flipping-through-book-pages-6981525/\n"
        "- https://www.pexels.com/video/flipping-pages-of-a-book-7055351/\n"
        "- https://www.pexels.com/video/hands-opening-old-book-11530072/\n\n"
        "Fallback footage: FastVideo/Mixkit-Src public dataset mirror (original Mixkit stock clips).\n\n"
        "Tư liệu lịch sử (Wikimedia Commons):\n"
        "- Jesse Livermore (c. 1923) (cropped).jpg — public domain in US.\n"
        "- 1907 Panic.png — public domain in US.\n"
        "- Crowds gathering outside New York Stock Exchange.jpg — 1929 historical photograph; verify file-page license before publication.\n\n"
        "Ảnh bìa sản phẩm: thử lấy từ trang sản phẩm Alpha Books để nhận diện/review tác phẩm; nếu truy xuất thất bại, bản dựng dùng cover card tự thiết kế.\n"
        "Không có voice-over, không nhạc, không audio.\n",
        encoding="utf-8"
    )
    print("FINAL", final, final.stat().st_size)


if __name__ == "__main__":
    main()
