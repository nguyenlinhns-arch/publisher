from __future__ import annotations
import math, shutil, subprocess, sys, time, wave
from pathlib import Path
import requests, numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'; WORK=ROOT/'work_v11'
OUT.mkdir(parents=True,exist_ok=True); WORK.mkdir(parents=True,exist_ok=True)
W,H,FPS=1080,1920,30
WHITE=(248,246,240); GOLD=(228,177,73); MUTED=(205,201,192); GREEN=(72,196,112); RED=(216,74,64)
FONT_B='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'; FONT_R='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
UA={'User-Agent':'Mozilla/5.0 Chrome/151 Safari/537.36'}
S=requests.Session(); S.headers.update(UA)
SRC={
 'book_vertical':'https://videos.pexels.com/video-files/6243989/6243989-uhd_2160_3840_24fps.mp4',
 'book_warm':'https://videos.pexels.com/video-files/13011710/13011710-hd_1920_1080_30fps.mp4',
 'page_fast':'https://videos.pexels.com/video-files/856242/856242-hd_1920_1080_30fps.mp4',
 'jewelry':'https://videos.pexels.com/video-files/5705007/5705007-uhd_4096_2160_24fps.mp4',
 'cover':'https://pos.nvncdn.com/fd5775-40602/ps/20240620_vAHc49veeP.jpeg?v=1718865566',
}
NARR=(
"Có một chi tiết trong Chết Vì Chứng Khoán mà tôi nhớ lâu hơn cả cú sập năm 1929. "
"Năm 1901, Jesse Livermore trắng tay. Ông xin người vợ đầu Nettie cho cầm bộ nữ trang trị giá khoảng mười hai nghìn đô la mà chính ông đã mua tặng bà ở châu Âu, để lấy vốn quay lại thị trường. Bà từ chối. Livermore phải vay mượn để làm lại từ đầu. "
"Rồi ông trở lại. Năm 1907, ông thắng lớn. Năm 1929, khi Wall Street sụp đổ, ông kiếm khoảng một trăm triệu đô la. "
"Nhưng câu chuyện không kết thúc ở đó. Đến năm 1934, ông lại phá sản. "
"Đọc đến đây, tôi nghĩ tới Việt Nam năm 2022: thị trường giảm sâu, ký quỹ có thể biến một quyết định sai thành áp lực phải bán. "
"Cuốn sách làm tôi gạch lại ba điều: chỉ mua khi giá xác nhận; chỉ gia tăng vị thế đang đúng; và quyết định mức lỗ trước khi bấm mua. "
"Nếu bạn thích những cuốn sách kể chuyện thật để buộc mình giao dịch kỷ luật hơn, cuốn này đáng đọc. Link sách ở bio hoặc bình luận ghim."
)

def run(cmd,quiet=False):
    kw={}
    if quiet: kw={'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL}
    print('+',' '.join(map(str,cmd)),flush=True)
    return subprocess.run(cmd,check=True,**kw)

def ensure():
    if not shutil.which('ffmpeg'):
        subprocess.run(['sudo','apt-get','update'],check=True)
        subprocess.run(['sudo','apt-get','install','-y','ffmpeg','fonts-dejavu-core'],check=True)

def dl(url,dest,minb=20000):
    if dest.exists() and dest.stat().st_size>=minb:return dest
    last=None
    for a in range(5):
        try:
            with S.get(url,stream=True,timeout=(20,180),allow_redirects=True) as r:
                r.raise_for_status(); total=0
                with open(dest,'wb') as f:
                    for ch in r.iter_content(1024*1024):
                        if ch: f.write(ch); total+=len(ch)
            if total<minb: raise RuntimeError(total)
            return dest
        except Exception as e:
            last=e; time.sleep(2+a*2)
    raise RuntimeError(f'download fail {url}: {last}')

def fnt(sz,b=True): return ImageFont.truetype(FONT_B if b else FONT_R,sz)

def shadow(d,xy,text,ft,fill,anchor='la'):
    x,y=xy; d.text((x+3,y+4),text,font=ft,fill=(0,0,0,180),anchor=anchor); d.text((x,y),text,font=ft,fill=fill,anchor=anchor)

def fit(d,text,ft,maxw):
    words=text.split(); lines=[]; cur=''
    for w in words:
        t=(cur+' '+w).strip(); bb=d.textbbox((0,0),t,font=ft)
        if bb[2]-bb[0]<=maxw or not cur: cur=t
        else: lines.append(cur); cur=w
    if cur: lines.append(cur)
    return lines

def make_text_overlay(name,title='',sub='',tag='',accent='',bottom=310):
    im=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)
    # subtle bottom gradient only, no card
    for y in range(H-520,H):
        a=int(max(0,min(170,(y-(H-520))/520*170)))
        d.rectangle((0,y,W,y+1),fill=(0,0,0,a))
    if tag:
        shadow(d,(72,112),tag.upper(),fnt(26,True),GOLD)
    if title:
        size=58 if len(title)<=30 else 50
        ft=fnt(size,True); lines=fit(d,title.upper(),ft,920); yy=H-bottom-len(lines)*66
        for line in lines:
            col=GOLD if accent and accent.lower() in line.lower() else WHITE
            shadow(d,(72,yy),line,ft,col); yy+=67
        if sub:
            sf=fnt(30,False); yy+=8
            for line in fit(d,sub,sf,900): shadow(d,(74,yy),line,sf,MUTED); yy+=42
    p=WORK/f'{name}.png'; im.save(p); return p

def cover_hero(cover,out):
    c=Image.open(cover).convert('RGB')
    bg=c.copy(); bw,bh=bg.size; sc=max(W/bw,H/bh); bg=bg.resize((int(bw*sc),int(bh*sc)),Image.Resampling.LANCZOS)
    x=(bg.width-W)//2; y=(bg.height-H)//2; bg=bg.crop((x,y,x+W,y+H)).filter(ImageFilter.GaussianBlur(42))
    bg=Image.blend(bg,Image.new('RGB',(W,H),(8,7,8)),0.58)
    c.thumbnail((650,980),Image.Resampling.LANCZOS)
    x=(W-c.width)//2; y=285
    sh=Image.new('RGBA',(W,H),(0,0,0,0)); sd=ImageDraw.Draw(sh)
    sd.rounded_rectangle((x+32,y+38,x+c.width+32,y+c.height+38),24,fill=(0,0,0,165)); sh=sh.filter(ImageFilter.GaussianBlur(28))
    base=Image.alpha_composite(bg.convert('RGBA'),sh).convert('RGB'); base.paste(c,(x,y))
    d=ImageDraw.Draw(base); shadow(d,(W//2,1475),'CHẾT VÌ CHỨNG KHOÁN',fnt(52,True),WHITE,anchor='ma'); shadow(d,(W//2,1540),'Richard Smitten',fnt(30,False),GOLD,anchor='ma')
    base.save(out,quality=96); return out

def vintage_card(year,title,out):
    im=Image.new('RGB',(W,H),(40,38,34)); d=ImageDraw.Draw(im)
    # paper centered with subtle texture
    d.rounded_rectangle((95,240,985,1610),radius=18,fill=(219,209,187),outline=(115,99,73),width=3)
    rng=np.random.default_rng(int(year))
    for _ in range(1400):
        x=int(rng.integers(105,975)); y=int(rng.integers(250,1600)); v=int(rng.integers(150,210)); d.point((x,y),fill=(v,v-8,v-20))
    shadow(d,(W//2,380),str(year),fnt(120,True),(62,52,39),anchor='ma')
    for i,line in enumerate(fit(d,title.upper(),fnt(54,True),720)):
        shadow(d,(W//2,620+i*70),line,fnt(54,True),(62,52,39),anchor='ma')
    for yy in range(940,1390,95): d.line((210,yy,870,yy),fill=(120,108,88),width=3)
    im=im.filter(ImageFilter.GaussianBlur(0.25)); im.save(out,quality=95); return out

def vn_mini_chart(out):
    im=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)
    # compact glass panel at upper-right over live book footage
    x1,y1,x2,y2=520,220,1010,760
    d.rounded_rectangle((x1,y1,x2,y2),radius=32,fill=(8,12,14,220),outline=(255,255,255,32),width=2)
    shadow(d,(560,270),'VIỆT NAM • 2022',fnt(30,True),GOLD)
    shadow(d,(560,320),'VN-Index',fnt(28,False),MUTED)
    pts=[(575,425),(650,400),(720,455),(790,540),(860,590),(940,650)]
    d.line(pts,fill=RED,width=7)
    for x,y in pts: d.ellipse((x-8,y-8,x+8,y+8),fill=RED)
    shadow(d,(580,690),'Giảm sâu • áp lực ký quỹ',fnt(26,True),WHITE)
    im.save(out); return out

def lesson_overlay(num,text,out):
    im=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)
    # only typographic line, no box
    shadow(d,(72,125),f'{num:02d}',fnt(46,True),GOLD)
    shadow(d,(145,130),text.upper(),fnt(43,True),WHITE)
    d.rounded_rectangle((72,195,350,202),radius=3,fill=GOLD)
    im.save(out); return out

def vseg(src,out,start,dur,ov=None,zoom=False):
    filt=f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},eq=contrast=1.05:saturation=0.92:brightness=-0.015,unsharp=5:5:0.2:5:5:0.0,setpts=PTS-STARTPTS[b]"
    cmd=['ffmpeg','-y','-ss',str(start),'-i',str(src)]
    if ov:
        cmd+=['-loop','1','-i',str(ov)]; filt+=',null[b2];[b2][1:v]overlay=0:0:shortest=1[v]'; mapv='[v]'
    else: filt+=',null[v]'; mapv='[v]'
    run(cmd+['-filter_complex',filt,'-map',mapv,'-t',str(dur),'-an','-r',str(FPS),'-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(out)],True)

def stillseg(src,out,dur,ov=None,zoom=0.00045):
    filt=f"[0:v]scale=1500:2400:force_original_aspect_ratio=increase,zoompan=z='min(zoom+{zoom},1.10)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{H}:fps={FPS},eq=contrast=1.05:saturation=0.9:brightness=-0.02[b]"
    cmd=['ffmpeg','-y','-loop','1','-framerate',str(FPS),'-i',str(src)]
    if ov:
        cmd+=['-loop','1','-i',str(ov)]; filt+=';[b][1:v]overlay=0:0:shortest=1[v]'; mapv='[v]'
    else: filt+=';[b]null[v]'; mapv='[v]'
    run(cmd+['-filter_complex',filt,'-map',mapv,'-t',str(dur),'-an','-r',str(FPS),'-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p',str(out)],True)

def duration(p):
    return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nk=1:nw=1',str(p)],text=True).strip())

def make_voice(out):
    subprocess.run([sys.executable,'-m','pip','install','-q','edge-tts'],check=True)
    raw=WORK/'voice_raw.mp3'
    cmd=['edge-tts','--voice','vi-VN-NamMinhNeural','--rate=-4%','--pitch=-8Hz','--text',NARR,'--write-media',str(raw)]
    for a in range(4):
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        if p.returncode==0 and raw.exists() and raw.stat().st_size>5000:break
        time.sleep(3+a*2)
    af='highpass=f=70,lowpass=f=11500,equalizer=f=130:t=q:w=1:g=2.4,equalizer=f=300:t=q:w=1:g=-0.8,equalizer=f=3200:t=q:w=1:g=1.1,acompressor=threshold=-18dB:ratio=2.2:attack=15:release=180:makeup=2,loudnorm=I=-16:TP=-1.5:LRA=7'
    run(['ffmpeg','-y','-i',str(raw),'-af',af,'-ar','48000','-ac','2',str(out)],True)

def music(out,dur,sr=48000):
    n=int(dur*sr); t=np.arange(n)/sr; y=np.zeros(n)
    chords=[(98,123.47,146.83),(87.31,110,130.81),(110,138.59,164.81),(92.5,116.54,138.59)]
    for k,st in enumerate(np.arange(0,dur,7.5)):
        ed=min(dur,st+7.5); idx=(t>=st)&(t<ed); tt=t[idx]-st; env=np.minimum(tt/1.6,1)*np.minimum((ed-st-tt)/1.7,1); env=np.clip(env,0,1)
        sig=sum(np.sin(2*np.pi*f*tt)+.18*np.sin(4*np.pi*f*tt) for f in chords[k%4])/4.5
        y[idx]+=sig*env*.12
    y*=np.minimum(np.arange(n)/(sr*2),1)*np.minimum((n-1-np.arange(n))/(sr*2.8),1)
    stereo=np.stack([y,np.roll(y,int(.009*sr))*.98],axis=1); stereo=(np.clip(stereo,-1,1)*32767).astype(np.int16)
    with wave.open(str(out),'wb') as wf: wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(sr); wf.writeframes(stereo.tobytes())

def sfx(out,dur,sr=48000):
    n=int(dur*sr); y=np.zeros(n); rng=np.random.default_rng(11)
    def add(st,kind='w'):
        i=int(st*sr)
        if kind=='w':
            m=int(.28*sr); tt=np.arange(m)/sr; sig=rng.normal(0,1,m); sig=np.convolve(sig,np.ones(8)/8,mode='same')*np.sin(np.pi*tt/.28)**2*.12
        elif kind=='hit':
            m=int(.22*sr); tt=np.arange(m)/sr; sig=(np.sin(2*np.pi*65*tt)+.3*np.sin(2*np.pi*130*tt))*np.exp(-10*tt)*.16
        else:
            m=int(.36*sr); tt=np.arange(m)/sr; sig=np.convolve(rng.normal(0,1,m),np.ones(15)/15,mode='same')*np.sin(np.pi*tt/.36)**2*.11
        j=min(n,i+len(sig)); y[i:j]+=sig[:j-i]
    for st,k in [(0,'hit'),(2.5,'w'),(5.4,'page'),(9.2,'hit'),(12,'page'),(15.2,'w'),(18.4,'w'),(22,'page'),(25.2,'hit'),(29.2,'w'),(35.4,'page'),(39.3,'page'),(43.2,'page'),(48.2,'w')]: add(st,k)
    stereo=np.stack([y,np.roll(y,int(.007*sr))],axis=1); stereo=(np.clip(stereo,-1,1)*32767).astype(np.int16)
    with wave.open(str(out),'wb') as wf: wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(sr); wf.writeframes(stereo.tobytes())

def main():
    ensure(); files={}
    for k,u in SRC.items():
        ext='.mp4' if k!='cover' else '.jpg'; files[k]=dl(u,WORK/f'{k}{ext}',500000 if ext=='.mp4' else 20000)
    hero=cover_hero(files['cover'],WORK/'hero.jpg')
    y1907=vintage_card(1907,'Một lần trở lại',WORK/'1907.jpg')
    y1929=vintage_card(1929,'Đỉnh cao giữa khủng hoảng',WORK/'1929.jpg')
    y1934=vintage_card(1934,'Phá sản lần nữa',WORK/'1934.jpg')
    ovs={
      'hook':make_text_overlay('hook','Một chi tiết tôi nhớ mãi','',tag='Review sách',accent=''),
      'jewel':make_text_overlay('jewel','1901 • Trắng tay','Xin cầm bộ nữ trang để lấy vốn.'),
      'refuse':make_text_overlay('refuse','Bà từ chối.','Livermore phải vay mượn để làm lại.'),
      'vn':vn_mini_chart(WORK/'vn.png'),
      'l1':lesson_overlay(1,'Chờ giá xác nhận',WORK/'l1.png'),
      'l2':lesson_overlay(2,'Chỉ gia tăng vị thế đang đúng',WORK/'l2.png'),
      'l3':lesson_overlay(3,'Mức lỗ phải biết trước',WORK/'l3.png'),
      'cta':make_text_overlay('cta','Đáng đọc nếu bạn muốn học kỷ luật','Link sách ở bio / bình luận ghim',tag='Chết Vì Chứng Khoán'),
    }
    scenes=[]
    def add(name,fn,*args):
        p=WORK/f'{len(scenes):02d}_{name}.mp4'; fn(*args,p) if False else None
    # render short, native-paced scenes
    p=WORK/'s01.mp4'; stillseg(hero,p,2.5,ovs['hook'],0.0006); scenes.append(p)
    p=WORK/'s02.mp4'; vseg(files['jewelry'],p,1.0,3.0,ovs['jewel']); scenes.append(p)
    p=WORK/'s03.mp4'; vseg(files['book_vertical'],p,1.0,3.7,None); scenes.append(p)
    p=WORK/'s04.mp4'; vseg(files['jewelry'],p,4.6,2.5,ovs['refuse']); scenes.append(p)
    p=WORK/'s05.mp4'; vseg(files['book_warm'],p,0.6,3.0,None); scenes.append(p)
    p=WORK/'s06.mp4'; stillseg(y1907,p,3.2,None,0.00055); scenes.append(p)
    p=WORK/'s07.mp4'; stillseg(y1929,p,3.6,None,0.00055); scenes.append(p)
    p=WORK/'s08.mp4'; vseg(files['page_fast'],p,0.0,3.2,None); scenes.append(p)
    p=WORK/'s09.mp4'; stillseg(y1934,p,3.2,None,0.00055); scenes.append(p)
    p=WORK/'s10.mp4'; vseg(files['book_vertical'],p,3.0,5.4,ovs['vn']); scenes.append(p)
    p=WORK/'s11.mp4'; vseg(files['book_warm'],p,2.0,3.9,ovs['l1']); scenes.append(p)
    p=WORK/'s12.mp4'; vseg(files['book_vertical'],p,5.0,3.9,ovs['l2']); scenes.append(p)
    p=WORK/'s13.mp4'; vseg(files['book_warm'],p,5.2,3.9,ovs['l3']); scenes.append(p)
    p=WORK/'s14.mp4'; vseg(files['book_vertical'],p,7.0,4.2,None); scenes.append(p)
    p=WORK/'s15.mp4'; stillseg(hero,p,5.0,ovs['cta'],0.00035); scenes.append(p)
    concat=WORK/'concat.txt'; concat.write_text(''.join(f"file '{x.as_posix()}'\n" for x in scenes),encoding='utf-8')
    silent=OUT/'Review_Chet_Vi_Chung_Khoan_AFF_V11_Silent_1080p.mp4'
    run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),'-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(silent)],True)
    dur=duration(silent)
    voice=WORK/'voice.wav'; make_voice(voice); vd=duration(voice)
    # preserve natural Nam Minh speed. If narration is longer, extend last hero frame.
    if vd>dur-0.5:
        extra=vd-dur+1.2; tail=WORK/'tail.mp4'; stillseg(hero,tail,extra,ovs['cta'],0.0001)
        c2=WORK/'concat2.txt'; c2.write_text(concat.read_text()+f"file '{tail.as_posix()}'\n",encoding='utf-8')
        run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(c2),'-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(silent)],True); dur=duration(silent)
    mus=WORK/'music.wav'; music(mus,dur); fx=WORK/'sfx.wav'; sfx(fx,dur)
    final=OUT/'Review_Chet_Vi_Chung_Khoan_AFF_V11_Native_1080p.mp4'
    fc='[1:a]volume=1.0[v];[2:a]volume=0.13[m];[3:a]volume=0.24[s];[m][v]sidechaincompress=threshold=0.025:ratio=8:attack=12:release=260[md];[md][v][s]amix=inputs=3:duration=longest:dropout_transition=1,loudnorm=I=-14.5:TP=-1.0:LRA=8[a]'
    run(['ffmpeg','-y','-i',str(silent),'-i',str(voice),'-i',str(mus),'-i',str(fx),'-filter_complex',fc,'-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-shortest','-movflags','+faststart',str(final)],True)
    small=OUT/'Review_Chet_Vi_Chung_Khoan_AFF_V11_Native_720p.mp4'
    run(['ffmpeg','-y','-i',str(final),'-vf','scale=720:1280','-c:v','libx264','-preset','veryfast','-crf','22','-c:a','aac','-b:a','160k','-movflags','+faststart',str(small)],True)
    (OUT/'LOI_DOC_V11.txt').write_text(NARR,encoding='utf-8')
    (OUT/'NGUON_V11.txt').write_text('\n'.join(f'{k}: {v}' for k,v in SRC.items()),encoding='utf-8')
    print('FINAL',final,duration(final),final.stat().st_size)
if __name__=='__main__': main()
