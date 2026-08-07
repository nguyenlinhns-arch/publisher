from __future__ import annotations

import math
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
WORK = ROOT / "work_book_story_v8"
OUT.mkdir(parents=True, exist_ok=True)
WORK.mkdir(parents=True, exist_ok=True)

W, H, FPS = 1080, 1920, 30
WHITE = (247, 244, 237)
GOLD = (226, 176, 75)
RED = (214, 66, 58)
GREEN = (72, 196, 112)
MUTED = (198, 194, 184)
DARK = (6, 10, 12)
UA = {"User-Agent": "Mozilla/5.0 Chrome/150 Safari/537.36"}
S = requests.Session(); S.headers.update(UA)

SRC = {
    "book_vertical": "https://videos.pexels.com/video-files/9115655/9115655-uhd_2160_3840_30fps.mp4",
    "book_candle": "https://videos.pexels.com/video-files/11530055/11530055-uhd_3840_2160_25fps.mp4",
    "book_warm": "https://videos.pexels.com/video-files/6981525/6981525-uhd_3840_2160_25fps.mp4",
    "book_dark": "https://videos.pexels.com/video-files/7055351/7055351-uhd_3840_2160_30fps.mp4",
    "cover": "https://pos.nvncdn.com/fd5775-40602/ps/20240620_vAHc49veeP.jpeg?v=1718865566",
    "crowd1929": "https://upload.wikimedia.org/wikipedia/commons/3/3f/Crowds_gathering_outside_New_York_Stock_Exchange.jpg",
    "jesse": "https://upload.wikimedia.org/wikipedia/commons/6/67/Jesse_Livermore_%28c._1923%29_%28cropped%29.jpg",
}

NARRATION = (
    "Năm 1929, khi Wall Street hoảng loạn, Jesse Livermore kiếm khoảng một trăm triệu đô la. "
    "Trước đó, ông cũng từng thắng lớn trong khủng hoảng năm 1907. Ông hiểu xu hướng và biết chờ đợi. "
    "Nhưng vài năm sau, gần như tất cả lại biến mất. "
    "Đó là phần tôi thấy đắt nhất trong Chết Vì Chứng Khoán: một người cực giỏi vẫn có thể thua khi kỷ luật biến mất. "
    "Nghe rất xa, nhưng nhìn Việt Nam năm 2022. VN-Index từ một nghìn năm trăm ba mươi sáu điểm xuống còn tám trăm bảy mươi ba điểm; áp lực ký quỹ và bán giải chấp xuất hiện dày đặc. "
    "Bối cảnh khác, bài học lại rất giống nhau. Chờ giá xác nhận. Chỉ gia tăng khi vị thế đang thắng. Và quyết định mức lỗ trước khi bấm mua. "
    "Tôi không đọc cuốn này để học cách thắng một cú sập. Tôi đọc để nhớ rằng thị trường không cần mình đúng; mình cần sống sót đủ lâu. "
    "Nếu bạn muốn hiểu tâm lý và kỷ luật giao dịch, đây là cuốn đáng đọc. Link tiếp thị ở bio hoặc bình luận ghim."
)

SCRIPT_TXT = """KỊCH BẢN V8 — KỂ CHUYỆN + LIÊN HỆ THỊ TRƯỜNG VIỆT NAM

0–3,4s: 1929 — Livermore kiếm khoảng 100 triệu đô la khi Wall Street sụp đổ.
3,4–7,4s: 1907 — ông đã từng thắng lớn trong một cơn hoảng loạn trước đó.
7,4–12,6s: 1929 — tư liệu đám đông ngoài NYSE; nhấn nghịch lý chiến thắng trong khủng hoảng.
12,6–17,6s: Jesse Livermore — người hiểu xu hướng nhưng sau đó vẫn mất gần như tất cả.
17,6–22,6s: Chết Vì Chứng Khoán — vấn đề không phải thiếu kiến thức; vấn đề là kỷ luật.
22,6–32,1s: Việt Nam 2022 — VN-Index 1.536,24 → 873,78; call margin/bán giải chấp.
32,1–36,9s: Bài học 1 — chờ giá xác nhận.
36,9–41,7s: Bài học 2 — chỉ gia tăng khi vị thế đang thắng.
41,7–46,5s: Bài học 3 — xác định mức lỗ trước khi mua.
46,5–52,0s: Kết luận — không đọc để học cách thắng cú sập; đọc để học cách tồn tại.
52,0–56,0s: CTA — ai phù hợp + disclosure affiliate.
"""


def run(cmd, quiet=False):
    print("+", " ".join(map(str, cmd)), flush=True)
    kwargs = {}
    if quiet:
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    return subprocess.run(cmd, check=True, **kwargs)


def ensure_tools():
    if not shutil.which("ffmpeg"):
        subprocess.run(["sudo", "apt-get", "update"], check=True)
        subprocess.run(["sudo", "apt-get", "install", "-y", "ffmpeg", "fonts-noto-core", "fonts-dejavu-core"], check=True)


def download(url, dest: Path, min_bytes=20_000, optional=False):
    if dest.exists() and dest.stat().st_size >= min_bytes:
        return dest
    last = None
    for attempt in range(5):
        try:
            with S.get(url, stream=True, timeout=(20, 180), allow_redirects=True) as r:
                r.raise_for_status()
                total = 0
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(1024 * 1024):
                        if chunk:
                            f.write(chunk); total += len(chunk)
            if total < min_bytes:
                raise RuntimeError(f"too small: {total}")
            print("downloaded", dest.name, total, flush=True)
            return dest
        except Exception as e:
            last = e; time.sleep(2 + attempt * 2)
    if optional:
        return None
    raise RuntimeError(f"download failed {url}: {last}")


def font_path(bold=True):
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSans-SemiCondensedBold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSans-SemiCondensed.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).exists(): return p
    return candidates[-1]


def fnt(size, bold=True):
    return ImageFont.truetype(font_path(bold), size)


def fit(draw, text, ft, max_w):
    words = text.split(); lines = []; cur = ""
    for word in words:
        test = (cur + " " + word).strip()
        bb = draw.textbbox((0, 0), test, font=ft)
        if bb[2] - bb[0] <= max_w or not cur:
            cur = test
        else:
            lines.append(cur); cur = word
    if cur: lines.append(cur)
    return lines


def shadow(draw, xy, text, ft, fill, anchor="la"):
    x, y = xy
    draw.text((x+3, y+4), text, font=ft, fill=(0,0,0,195), anchor=anchor)
    draw.text((x, y), text, font=ft, fill=fill, anchor=anchor)


def bottom_gradient(im, start=1030, alpha=215):
    d = ImageDraw.Draw(im)
    for y in range(start, H):
        a = int(min(alpha, (y-start)/(H-start) * alpha))
        d.rectangle((0,y,W,y+1), fill=(0,0,0,a))


def make_overlay(name, tag, title, sub="", accent="", y=1350):
    im = Image.new("RGBA", (W,H), (0,0,0,0)); bottom_gradient(im)
    d = ImageDraw.Draw(im)
    if tag:
        shadow(d, (72, 100), tag.upper(), fnt(28, True), GOLD)
        d.rounded_rectangle((72,148,248,154), radius=3, fill=GOLD)
    size = 65 if len(title) <= 28 else 54
    ft = fnt(size, True)
    lines = fit(d, title.upper(), ft, 910)
    yy = y - len(lines)*74
    for line in lines:
        col = GOLD if accent and accent.lower() in line.lower() else WHITE
        shadow(d, (72, yy), line, ft, col); yy += 75
    if sub:
        sf = fnt(31, False); yy += 8
        for line in fit(d, sub, sf, 900):
            shadow(d, (75, yy), line, sf, MUTED); yy += 45
    p = WORK / f"ov_{name}.png"; im.save(p); return p


def hook_overlay():
    im = Image.new("RGBA", (W,H), (0,0,0,0)); bottom_gradient(im, 950, 230)
    d = ImageDraw.Draw(im)
    shadow(d, (72, 1125), "1929", fnt(42, True), MUTED)
    shadow(d, (72, 1200), "100 TRIỆU ĐÔ LA", fnt(82, True), GOLD)
    shadow(d, (72, 1300), "KIẾM ĐƯỢC KHI", fnt(54, True), WHITE)
    shadow(d, (72, 1372), "THỊ TRƯỜNG SỤP ĐỔ", fnt(54, True), WHITE)
    d.rounded_rectangle((72,1488,390,1496), radius=4, fill=GOLD)
    p = WORK / "ov_hook.png"; im.save(p); return p


def cover_card(src: Path, out: Path):
    cover = Image.open(src).convert("RGB")
    bg = cover.copy(); bw,bh = bg.size; sc = max(W/bw, H/bh)
    bg = bg.resize((int(bw*sc), int(bh*sc)), Image.Resampling.LANCZOS)
    x=(bg.width-W)//2; y=(bg.height-H)//2
    bg = bg.crop((x,y,x+W,y+H)).filter(ImageFilter.GaussianBlur(34))
    bg = Image.blend(bg, Image.new("RGB", (W,H), "black"), 0.62)
    cover.thumbnail((700,1060), Image.Resampling.LANCZOS)
    x=(W-cover.width)//2; y=260
    sh=Image.new("RGBA",(W,H),(0,0,0,0)); sd=ImageDraw.Draw(sh)
    sd.rounded_rectangle((x+25,y+35,x+cover.width+25,y+cover.height+35),22,fill=(0,0,0,160))
    sh=sh.filter(ImageFilter.GaussianBlur(22))
    canvas=Image.alpha_composite(bg.convert("RGBA"), sh).convert("RGB")
    canvas.paste(cover,(x,y)); canvas.save(out,quality=96); return out


def fallback_1929(out: Path):
    im=Image.new("RGB",(W,H),(20,20,18)); d=ImageDraw.Draw(im)
    for y in range(H):
        v=int(35+50*y/H); d.line((0,y,W,y),fill=(v,v,v-4))
    rng=np.random.default_rng(29)
    for _ in range(230):
        x=int(rng.integers(45,W-45)); y=int(rng.integers(500,1580)); r=int(rng.integers(9,22))
        d.ellipse((x-r,y-r,x+r,y+r),fill=(18,18,17))
    shadow(d,(W//2,255),"WALL STREET • 1929",fnt(70,True),(220,220,215),anchor="ma")
    im=im.filter(ImageFilter.GaussianBlur(0.4)); im.save(out,quality=94); return out


def vseg(src: Path, out: Path, start, dur, ov=None, flash=False):
    fc=[f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},eq=contrast=1.06:saturation=0.84:brightness=-0.02,noise=alls=1.5:allf=t+u,setpts=PTS-STARTPTS[b]"]
    prev="b"
    cmd=["ffmpeg","-y","-ss",str(start),"-i",str(src)]
    if ov:
        cmd += ["-loop","1","-i",str(ov)]
        fc += ["[1:v]format=rgba[o]","[b][o]overlay=0:0:shortest=1[v0]"]; prev="v0"
    if flash:
        fc.append(f"[{prev}]drawbox=x=0:y=0:w=iw:h=ih:color=white@0.30:t=fill:enable='lt(t,0.06)'[v]")
    else:
        fc.append(f"[{prev}]null[v]")
    cmd += ["-filter_complex",";".join(fc),"-map","[v]","-t",str(dur),"-an","-r",str(FPS),"-c:v","libx264","-preset","veryfast","-crf","19","-pix_fmt","yuv420p","-movflags","+faststart",str(out)]
    run(cmd, True)


def stillseg(src: Path, out: Path, dur, ov=None, zoom=0.00055, flash=False):
    fc=[f"[0:v]scale=1500:2400:force_original_aspect_ratio=increase,zoompan=z='min(zoom+{zoom},1.12)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{H}:fps={FPS},eq=contrast=1.05:saturation=0.80:brightness=-0.025,noise=alls=1.5:allf=t+u[b]"]
    prev="b"; cmd=["ffmpeg","-y","-loop","1","-framerate",str(FPS),"-i",str(src)]
    if ov:
        cmd += ["-loop","1","-i",str(ov)]
        fc += ["[1:v]format=rgba[o]","[b][o]overlay=0:0:shortest=1[v0]"]; prev="v0"
    if flash:
        fc.append(f"[{prev}]drawbox=x=0:y=0:w=iw:h=ih:color=white@0.28:t=fill:enable='lt(t,0.06)'[v]")
    else:
        fc.append(f"[{prev}]null[v]")
    cmd += ["-filter_complex",";".join(fc),"-map","[v]","-t",str(dur),"-an","-r",str(FPS),"-c:v","libx264","-preset","veryfast","-crf","19","-pix_fmt","yuv420p",str(out)]
    run(cmd, True)


def cover_motion(bgvideo: Path, cover: Path, out: Path, dur, ov: Path):
    fc=(f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=14,eq=brightness=-0.15:saturation=0.55[b];"
        "[1:v]scale=600:-1,format=rgba[c];[b][c]overlay=(W-w)/2:(H-h)/2-100[m];[2:v]format=rgba[o];[m][o]overlay=0:0:shortest=1[v]")
    run(["ffmpeg","-y","-ss","0.7","-i",str(bgvideo),"-loop","1","-i",str(cover),"-loop","1","-i",str(ov),"-filter_complex",fc,"-map","[v]","-t",str(dur),"-an","-r",str(FPS),"-c:v","libx264","-preset","veryfast","-crf","19","-pix_fmt","yuv420p",str(out)], True)


def vnindex_video(out: Path, dur=9.5):
    points=[
        ("07/01",1536.24),
        ("19/04",1406.00),
        ("13/06",1242.00),
        ("19/09",1205.00),
        ("10/11",947.24),
        ("16/11",873.78),
    ]
    proc=subprocess.Popen(["ffmpeg","-y","-f","rawvideo","-pixel_format","rgb24","-video_size",f"{W}x{H}","-framerate",str(FPS),"-i","-","-an","-c:v","libx264","-preset","veryfast","-crf","18","-pix_fmt","yuv420p",str(out)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    N=int(dur*FPS)
    minv,maxv=820,1580; x0,x1=95,985; y0,y1=420,1435
    xs=np.linspace(x0,x1,len(points))
    ys=[y1-(v-minv)/(maxv-minv)*(y1-y0) for _,v in points]
    for frame in range(N):
        im=Image.new("RGB",(W,H),(5,9,12)); d=ImageDraw.Draw(im)
        for gy in range(520,1450,150): d.line((75,gy,1000,gy),fill=(26,34,40),width=1)
        for gx in range(120,1000,160): d.line((gx,390,gx,1470),fill=(22,31,36),width=1)
        shadow(d,(70,110),"VIỆT NAM • 2022",fnt(31,True),MUTED)
        shadow(d,(70,175),"VN-INDEX",fnt(58,True),WHITE)
        shadow(d,(70,252),"1.536,24  →  873,78",fnt(54,True),RED)
        shadow(d,(790,260),"-43%",fnt(50,True),GOLD)
        p=min(1,(frame/N)*1.18)
        total=(len(points)-1)*p; full=int(total); frac=total-full
        coords=[]
        for i in range(min(full+1,len(points))): coords.append((xs[i],ys[i]))
        if full < len(points)-1:
            nx=xs[full]+(xs[full+1]-xs[full])*frac; ny=ys[full]+(ys[full+1]-ys[full])*frac
            coords.append((nx,ny))
        if len(coords)>1: d.line(coords,fill=RED,width=7,joint="curve")
        for i,(label,val) in enumerate(points):
            if p >= i/(len(points)-1)-0.01:
                r=10; d.ellipse((xs[i]-r,ys[i]-r,xs[i]+r,ys[i]+r),fill=GOLD)
                if i in (0,5):
                    shadow(d,(xs[i],ys[i]-55),f"{val:,.2f}".replace(",","X").replace(".",",").replace("X","."),fnt(27,True),WHITE,anchor="ma")
                    shadow(d,(xs[i],ys[i]+28),label,fnt(24,False),MUTED,anchor="ma")
        if frame>N*.40:
            shadow(d,(85,1535),"KÝ QUỸ • BÁN GIẢI CHẤP",fnt(38,True),GOLD)
            shadow(d,(85,1595),"Khi thị trường ép bạn phải hành động.",fnt(29,False),MUTED)
        proc.stdin.write(im.tobytes())
    proc.stdin.close(); proc.wait()
    if proc.returncode != 0: raise RuntimeError("vnindex render failed")


def principle_video(mode, out: Path, dur=4.8):
    vals_up=[8,12,10,18,15,24,20,31,28,41,38,52,49,66,62,80,77,94,90,108,103,124]
    vals_dn=[72,76,70,80,75,84,79,88,82,76,70,65,60,55,50,47,43,39,42,36,33,30]
    vals=vals_dn if mode==3 else vals_up
    proc=subprocess.Popen(["ffmpeg","-y","-f","rawvideo","-pixel_format","rgb24","-video_size",f"{W}x{H}","-framerate",str(FPS),"-i","-","-an","-c:v","libx264","-preset","veryfast","-crf","18","-pix_fmt","yuv420p",str(out)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    N=int(dur*FPS);x0=108;step=39;base=1330;sc=6.0
    for frame in range(N):
        im=Image.new("RGB",(W,H),DARK);d=ImageDraw.Draw(im)
        for x in range(80,W-50,120):d.line((x,390,x,1490),fill=(24,34,35),width=1)
        for y in range(460,1500,120):d.line((65,y,W-45,y),fill=(24,34,35),width=1)
        progress=min(len(vals),max(1,int((frame/N)*len(vals)*1.3)))
        for i,v in enumerate(vals[:progress]):
            x=x0+i*step;op=base-v*sc;cl=op-(18 if i%3 else -11);hi=min(op,cl)-25;lo=max(op,cl)+25;col=GREEN if cl<op else RED
            d.line((x,hi,x,lo),fill=col,width=3);d.rectangle((x-8,min(op,cl),x+8,max(op,cl)+1),fill=col)
        if mode==1:
            y=base-66*sc;d.line((80,y,990,y),fill=GOLD,width=3);tag="BÀI HỌC 01";title="CHỜ GIÁ XÁC NHẬN";sub="Đừng mua chỉ vì mình nghĩ giá sẽ tăng.";color=GOLD
            if frame>N*.45:
                cx=x0+14*step;cy=base-vals[14]*sc;r=21+int(4*math.sin(frame*.2));d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=GOLD,width=5)
        elif mode==2:
            tag="BÀI HỌC 02";title="CHỈ GIA TĂNG KHI ĐANG THẮNG";sub="Đừng bình quân giá xuống chỉ để nuôi hy vọng.";color=GREEN
            for idx in (12,15,18):
                if progress>idx and frame>N*.35:
                    cx=x0+idx*step;cy=base-vals[idx]*sc;r=19+int(4*math.sin(frame*.22+idx));d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=GREEN,width=4)
        else:
            tag="BÀI HỌC 03";title="QUYẾT ĐỊNH MỨC LỖ TRƯỚC KHI MUA";sub="Để thị trường không quyết định thay bạn.";color=RED
            ey=base-vals[7]*sc;sy=ey+170;d.line((75,ey,995,ey),fill=GREEN,width=3);d.line((75,sy,995,sy),fill=RED,width=4)
            d.text((760,ey-48),"ĐIỂM VÀO",font=fnt(27,True),fill=GREEN);d.text((760,sy+12),"MỨC CẮT LỖ",font=fnt(27,True),fill=RED)
        shadow(d,(70,115),tag,fnt(29,True),color)
        ft=fnt(52 if mode!=3 else 45,True); yy=175
        for line in fit(d,title,ft,930):shadow(d,(70,yy),line,ft,WHITE);yy+=62
        sf=fnt(28,False);yy+=8
        for line in fit(d,sub,sf,900):shadow(d,(72,yy),line,sf,MUTED);yy+=40
        proc.stdin.write(im.tobytes())
    proc.stdin.close();proc.wait()
    if proc.returncode!=0:raise RuntimeError("principle render failed")


def duration(path: Path):
    p=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)],capture_output=True,text=True,check=True)
    return float(p.stdout.strip())


def make_voice(text, out: Path, target):
    subprocess.run([sys.executable,"-m","pip","install","-q","edge-tts"],check=True)
    raw=WORK/"voice_raw.mp3"
    cmd=["edge-tts","--voice","vi-VN-NamMinhNeural","--rate=-4%","--pitch=-8Hz","--text",text,"--write-media",str(raw)]
    for n in range(4):
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        if p.returncode==0 and raw.exists() and raw.stat().st_size>5000:break
        time.sleep(3+n*2)
    if not raw.exists() or raw.stat().st_size<5000:raise RuntimeError("edge tts failed")
    dur=duration(raw);tempo=max(0.85,min(1.18,dur/target))
    af=f"atempo={tempo:.6f},highpass=f=70,lowpass=f=11500,equalizer=f=125:t=q:w=1:g=2.3,acompressor=threshold=-18dB:ratio=2.2:attack=15:release=180:makeup=2,loudnorm=I=-16:TP=-1.5:LRA=7"
    run(["ffmpeg","-y","-i",str(raw),"-af",af,"-ar","48000","-ac","2",str(out)],True)
    return out


def make_music(out: Path, dur, sr=48000):
    n=int(dur*sr);t=np.arange(n)/sr;y=np.zeros(n,dtype=np.float64)
    chords=[(73.42,110.0,146.83),(65.41,98.0,130.81),(82.41,123.47,164.81),(55.0,82.41,110.0)]
    block=7.5
    for ci,start in enumerate(np.arange(0,dur,block)):
        end=min(dur,start+block);idx=(t>=start)&(t<end);tt=t[idx]-start;freqs=chords[ci%4]
        env=np.clip(np.minimum(tt/1.2,1)*np.minimum((end-start-tt)/1.5,1),0,1);pad=np.zeros_like(tt)
        for f in freqs: pad += np.sin(2*np.pi*f*tt)+0.22*np.sin(4*np.pi*f*tt)
        y[idx]+=pad/len(freqs)*env*0.10
        pulse=np.sin(2*np.pi*1.15*tt)>0.83; y[idx]+=pulse.astype(float)*0.008*env
    fade=np.minimum(np.arange(n)/(sr*1.7),1)*np.minimum((n-1-np.arange(n))/(sr*2.2),1);y*=np.clip(fade,0,1)
    stereo=np.stack([y,np.roll(y,int(sr*.011))*.97],axis=1);mx=np.max(np.abs(stereo)) or 1;pcm=(stereo/mx*.50*32767).astype(np.int16)
    with wave.open(str(out),"wb") as wf:wf.setnchannels(2);wf.setsampwidth(2);wf.setframerate(sr);wf.writeframes(pcm.tobytes())
    return out


def make_sfx(out: Path, dur, sr=48000):
    rng=np.random.default_rng(15);n=int(dur*sr);y=np.zeros(n)
    def add(sig,sec):
        i=int(sec*sr);j=min(n,i+len(sig));y[i:j]+=sig[:j-i]
    def hit(d=.28,a=.25):
        m=int(d*sr);tt=np.arange(m)/sr;env=np.exp(-10*tt);return ((np.sin(2*np.pi*65*tt)+.35*np.sin(2*np.pi*130*tt))*env+rng.normal(0,.03,m)*env)*a
    def whoosh(d=.32,a=.16):
        m=int(d*sr);tt=np.arange(m)/sr;noise=np.convolve(rng.normal(0,1,m),np.ones(8)/8,mode="same");env=np.sin(np.pi*np.clip(tt/d,0,1))**1.6;return noise*.18*env*a
    def tick(d=.12,a=.10):
        m=int(d*sr);tt=np.arange(m)/sr;return np.sin(2*np.pi*1100*tt)*np.exp(-22*tt)*a
    events=[("hit",.05),("whoosh",3.35),("whoosh",7.35),("hit",12.55),("whoosh",17.55),("hit",22.55),("tick",32.05),("tick",36.85),("tick",41.65),("whoosh",46.45),("hit",51.95)]
    for typ,sec in events:add({"hit":hit(),"whoosh":whoosh(),"tick":tick()}[typ],sec)
    mx=np.max(np.abs(y)) or 1;y=y/mx*.55;st=np.stack([y,np.roll(y,int(.007*sr))*.96],axis=1);pcm=(st*32767).astype(np.int16)
    with wave.open(str(out),"wb") as wf:wf.setnchannels(2);wf.setsampwidth(2);wf.setframerate(sr);wf.writeframes(pcm.tobytes())
    return out


def main():
    ensure_tools()
    files={}
    for key,url in SRC.items():
        ext=".mp4" if ".mp4" in url else ".jpg"
        files[key]=download(url,WORK/f"{key}{ext}",700_000 if ext==".mp4" else 20_000,optional=key in ("crowd1929","jesse"))
    if files["crowd1929"] is None: files["crowd1929"]=fallback_1929(WORK/"crowd1929_fallback.jpg")
    if files["jesse"] is None: files["jesse"]=files["cover"]
    cover_clean=files["cover"]
    cover_card(files["cover"],WORK/"cover_card.jpg")

    segs=[]; durs=[3.4,4.0,5.2,5.0,5.0,9.5,4.8,4.8,4.8,5.5,4.0]
    ov=hook_overlay(); s=WORK/"s01.mp4"; cover_motion(files["book_vertical"],cover_clean,s,durs[0],ov);segs.append(s)
    ov=make_overlay("1907","1907","ÔNG ĐÃ TỪNG THẮNG LỚN","Một cơn hoảng loạn khác. Một lần ông đọc đúng thị trường.","THẮNG",1340);s=WORK/"s02.mp4";vseg(files["book_warm"],s,.8,durs[1],ov);segs.append(s)
    ov=make_overlay("1929","PHỐ WALL","KHI ĐÁM ĐÔNG HOẢNG LOẠN","Livermore đi ngược số đông — và đúng.","HOẢNG LOẠN",1340);s=WORK/"s03.mp4";stillseg(files["crowd1929"],s,durs[2],ov,.00065,True);segs.append(s)
    ov=make_overlay("jesse","JESSE LIVERMORE","NHƯNG VẪN MẤT GẦN NHƯ TẤT CẢ","Đúng thị trường không đồng nghĩa với đúng mãi.","MẤT",1340);s=WORK/"s04.mp4";stillseg(files["jesse"],s,durs[3],ov,.00050);segs.append(s)
    ov=make_overlay("book","CHẾT VÌ CHỨNG KHOÁN","VẤN ĐỀ KHÔNG PHẢI KIẾN THỨC","Phần đắt giá là lúc một người cực giỏi đánh mất kỷ luật.","KỶ LUẬT",1340);s=WORK/"s05.mp4";vseg(files["book_dark"],s,.9,durs[4],ov);segs.append(s)
    s=WORK/"s06.mp4";vnindex_video(s,durs[5]);segs.append(s)
    for mode,dur in zip((1,2,3),durs[6:9]):s=WORK/f"s{6+mode:02d}.mp4";principle_video(mode,s,dur);segs.append(s)
    ov=make_overlay("survive","ĐIỀU TÔI NHỚ NHẤT","THỊ TRƯỜNG KHÔNG CẦN MÌNH ĐÚNG","Mình cần tồn tại đủ lâu để còn cơ hội sửa sai.","TỒN TẠI",1340);s=WORK/"s10.mp4";vseg(files["book_candle"],s,2.2,durs[9],ov);segs.append(s)
    ov=make_overlay("cta","AI NÊN ĐỌC?","TÂM LÝ • KỶ LUẬT • QUẢN LÝ VỊ THẾ","Link tiếp thị ở bio / bình luận ghim • Tôi có thể nhận hoa hồng.","KỶ LUẬT",1315);s=WORK/"s11.mp4";cover_motion(files["book_vertical"],cover_clean,s,durs[10],ov);segs.append(s)

    concat=WORK/"concat.txt";concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in segs),encoding="utf-8")
    silent=OUT/"Review_Chet_Vi_Chung_Khoan_Storytelling_V8_Silent_1080p.mp4"
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-an","-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-r",str(FPS),"-movflags","+faststart",str(silent)],True)
    total=duration(silent)
    voice=make_voice(NARRATION,OUT/"voice_story_v8.wav",max(50,total-.6));music=make_music(OUT/"music_story_v8.wav",total);sfx=make_sfx(OUT/"sfx_story_v8.wav",total)
    final=OUT/"Review_Chet_Vi_Chung_Khoan_Storytelling_V8_FINAL_1080p.mp4"
    fc="[1:a]volume=1.0[v];[2:a]volume=0.12[m];[3:a]volume=0.38[s];[v][m][s]amix=inputs=3:duration=longest:dropout_transition=2,loudnorm=I=-15.3:TP=-1.0:LRA=7[a]"
    run(["ffmpeg","-y","-i",str(silent),"-i",str(voice),"-i",str(music),"-i",str(sfx),"-filter_complex",fc,"-map","0:v:0","-map","[a]","-c:v","copy","-c:a","aac","-b:a","192k","-ar","48000","-shortest","-movflags","+faststart",str(final)],True)
    small=OUT/"Review_Chet_Vi_Chung_Khoan_Storytelling_V8_FINAL_720p.mp4"
    run(["ffmpeg","-y","-i",str(final),"-vf","scale=720:1280","-c:v","libx264","-preset","veryfast","-crf","23","-c:a","aac","-b:a","160k","-movflags","+faststart",str(small)],True)
    (OUT/"KICH_BAN_STORYTELLING_V8.txt").write_text(SCRIPT_TXT+"\n\nLỜI ĐỌC:\n"+NARRATION,encoding="utf-8")
    (OUT/"NGUON_V8.txt").write_text("Pexels footage: 9115655, 11530055, 6981525, 7055351.\nHistorical image: Wikimedia Commons NYSE 1929, Jesse Livermore portrait when available.\nVietnam 2022 data points used in animated VN-Index chart: 07/01 1536.24; 19/04 1406; 13/06 1242; 19/09 1205; 10/11 947.24; 16/11 873.78.\nResearch references for publication copy: Financial Times Jesse Livermore 1929; VnExpress/CafeF Vietnam 2022; YouTube Shorts official storytelling and affiliate guidance.\n",encoding="utf-8")
    print("FINAL",final,total,final.stat().st_size,flush=True)

if __name__ == "__main__":
    main()
