from __future__ import annotations
import math, shutil, subprocess, sys, time, wave
from pathlib import Path
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'; WORK=ROOT/'work_book_v7'
OUT.mkdir(parents=True,exist_ok=True); WORK.mkdir(parents=True,exist_ok=True)
W,H,FPS=1080,1920,30
WHITE=(247,244,237); GOLD=(224,174,72); RED=(210,65,58); GREEN=(74,195,112); MUTED=(194,190,180)
FB='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'; FR='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
UA={'User-Agent':'Mozilla/5.0 Chrome/150 Safari/537.36'}
S=requests.Session(); S.headers.update(UA)

SRC={
'book_vertical':'https://videos.pexels.com/video-files/9115655/9115655-uhd_2160_3840_30fps.mp4',
'book_candle':'https://videos.pexels.com/video-files/11530055/11530055-uhd_3840_2160_25fps.mp4',
'book_warm':'https://videos.pexels.com/video-files/6981525/6981525-uhd_3840_2160_25fps.mp4',
'book_dark':'https://videos.pexels.com/video-files/7055351/7055351-uhd_3840_2160_30fps.mp4',
'cover':'https://pos.nvncdn.com/fd5775-40602/ps/20240620_vAHc49veeP.jpeg?v=1718865566',
'crowd1929':'https://upload.wikimedia.org/wikipedia/commons/3/3f/Crowds_gathering_outside_New_York_Stock_Exchange.jpg',
'jesse':'https://upload.wikimedia.org/wikipedia/commons/6/67/Jesse_Livermore_%28c._1923%29_%28cropped%29.jpg',
}

def run(cmd,quiet=False):
    print('+',' '.join(map(str,cmd)),flush=True)
    kw={}
    if quiet: kw={'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL}
    return subprocess.run(cmd,check=True,**kw)

def tools():
    if not shutil.which('ffmpeg'):
        subprocess.run(['sudo','apt-get','update'],check=True)
        subprocess.run(['sudo','apt-get','install','-y','ffmpeg','fonts-dejavu-core'],check=True)

def dl(url,dest,minb=20000,optional=False):
    if dest.exists() and dest.stat().st_size>=minb:return dest
    last=None
    for n in range(5):
        try:
            with S.get(url,stream=True,timeout=(20,180),allow_redirects=True) as r:
                r.raise_for_status(); total=0
                with open(dest,'wb') as f:
                    for ch in r.iter_content(1024*1024):
                        if ch: f.write(ch); total+=len(ch)
            if total<minb: raise RuntimeError(total)
            print('downloaded',dest.name,total,flush=True); return dest
        except Exception as e:
            last=e; time.sleep(2+n*2)
    if optional:return None
    raise RuntimeError(f'download fail {url}: {last}')

def fnt(sz,b=True): return ImageFont.truetype(FB if b else FR,sz)

def fit(d,text,font,maxw):
    words=text.split(); lines=[]; cur=''
    for w in words:
        t=(cur+' '+w).strip(); bb=d.textbbox((0,0),t,font=font)
        if bb[2]-bb[0]<=maxw or not cur:cur=t
        else:lines.append(cur);cur=w
    if cur:lines.append(cur)
    return lines

def shadow(d,xy,text,font,fill,anchor='la'):
    x,y=xy;d.text((x+3,y+4),text,font=font,fill=(0,0,0,195),anchor=anchor);d.text((x,y),text,font=font,fill=fill,anchor=anchor)

def grad(im,start=1110,a=210):
    d=ImageDraw.Draw(im)
    for y in range(start,H):
        alpha=int(min(a,(y-start)/(H-start)*a));d.rectangle((0,y,W,y+1),fill=(0,0,0,alpha))

def overlay(name,tag,title,sub='',accent='',y=1320):
    im=Image.new('RGBA',(W,H),(0,0,0,0));grad(im);d=ImageDraw.Draw(im)
    if tag:
        tf=fnt(28,True);shadow(d,(74,102),tag.upper(),tf,GOLD);d.rounded_rectangle((74,148,238,154),3,fill=GOLD)
    size=62 if len(title)<31 else 54
    ft=fnt(size,True);lines=fit(d,title.upper(),ft,910)
    yy=y-len(lines)*72
    for ln in lines:
        col=GOLD if accent and accent.lower() in ln.lower() else WHITE
        shadow(d,(74,yy),ln,ft,col);yy+=74
    if sub:
        sf=fnt(31,False);yy+=10
        for ln in fit(d,sub,sf,900):shadow(d,(76,yy),ln,sf,MUTED);yy+=45
    p=WORK/f'ov_{name}.png';im.save(p);return p

def hook_overlay():
    im=Image.new('RGBA',(W,H),(0,0,0,0));grad(im,1030,225);d=ImageDraw.Draw(im)
    shadow(d,(74,1210),'JESSE LIVERMORE',fnt(34,True),MUTED)
    shadow(d,(74,1280),'100 TRIỆU USD',fnt(86,True),GOLD)
    shadow(d,(74,1383),'TRONG CÚ SẬP 1929',fnt(58,True),WHITE)
    shadow(d,(74,1472),'RỒI VẪN MẤT GẦN NHƯ TẤT CẢ.',fnt(43,True),WHITE)
    d.rounded_rectangle((74,1570,390,1578),4,fill=GOLD)
    p=WORK/'ov_hook.png';im.save(p);return p

def qualify_overlay():
    im=Image.new('RGBA',(W,H),(0,0,0,0));d=ImageDraw.Draw(im)
    d.rounded_rectangle((55,105,1025,860),32,fill=(4,7,8,205),outline=(46,52,54,180),width=2)
    shadow(d,(86,150),'NÊN ĐỌC NẾU…',fnt(42,True),GOLD)
    shadow(d,(88,225),'Muốn hiểu kỷ luật, tâm lý',fnt(38,True),WHITE)
    shadow(d,(88,280),'và cách quản lý vị thế.',fnt(38,True),WHITE)
    d.rounded_rectangle((86,375,975,382),3,fill=(55,60,61,220))
    shadow(d,(86,440),'KHÔNG PHÙ HỢP NẾU…',fnt(42,True),RED)
    shadow(d,(88,515),'Chỉ tìm mã mua-bán hoặc',fnt(38,True),WHITE)
    shadow(d,(88,570),'công thức làm giàu nhanh.',fnt(38,True),WHITE)
    p=WORK/'ov_qualify.png';im.save(p);return p

def cover_card(src,out):
    c=Image.open(src).convert('RGB');bg=c.copy();bw,bh=bg.size;sc=max(W/bw,H/bh);bg=bg.resize((int(bw*sc),int(bh*sc)),Image.Resampling.LANCZOS)
    x=(bg.width-W)//2;y=(bg.height-H)//2;bg=bg.crop((x,y,x+W,y+H)).filter(ImageFilter.GaussianBlur(32));bg=Image.blend(bg,Image.new('RGB',(W,H),'black'),0.60)
    c.thumbnail((720,1080),Image.Resampling.LANCZOS);x=(W-c.width)//2;y=260
    sh=Image.new('RGBA',(W,H),(0,0,0,0));sd=ImageDraw.Draw(sh);sd.rounded_rectangle((x+25,y+35,x+c.width+25,y+c.height+35),24,fill=(0,0,0,160));sh=sh.filter(ImageFilter.GaussianBlur(22))
    canvas=Image.alpha_composite(bg.convert('RGBA'),sh).convert('RGB');canvas.paste(c,(x,y));canvas.save(out,quality=96);return out

def fallback1907(out):
    im=Image.new('RGB',(W,H),(72,58,39));d=ImageDraw.Draw(im)
    for y in range(H):
        c=int(62+35*y/H);d.line((0,y,W,y),fill=(c,c-12,c-28))
    rng=np.random.default_rng(7)
    for i in range(120):
        x=int(rng.integers(70,1010));y=int(rng.integers(570,1510));r=int(rng.integers(10,22));d.ellipse((x-r,y-r,x+r,y+r),fill=(32,28,22))
    d.rectangle((120,230,960,560),fill=(222,205,163),outline=(80,64,42),width=5)
    shadow(d,(W//2,300),'PANIC OF 1907',fnt(72,True),(76,54,30),anchor='ma');shadow(d,(W//2,405),'NEW YORK',fnt(42,True),(76,54,30),anchor='ma')
    im=im.filter(ImageFilter.GaussianBlur(0.35));im.save(out,quality=95);return out

def vseg(src,out,start,dur,ov=None,flash=False):
    fc=[f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},eq=contrast=1.07:saturation=0.82:brightness=-0.02,noise=alls=2:allf=t+u,setpts=PTS-STARTPTS[b]"]
    prev='b'
    if ov:fc+=['[1:v]format=rgba[o]','[b][o]overlay=0:0:shortest=1[v0]'];prev='v0'
    if flash:fc.append(f"[{prev}]drawbox=x=0:y=0:w=iw:h=ih:color=white@0.38:t=fill:enable='lt(t,0.07)'[v]")
    else:fc.append(f'[{prev}]null[v]')
    cmd=['ffmpeg','-y','-ss',str(start),'-i',str(src)]
    if ov:cmd+=['-loop','1','-i',str(ov)]
    cmd+=['-filter_complex',';'.join(fc),'-map','[v]','-t',str(dur),'-an','-r',str(FPS),'-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(out)]
    run(cmd,True)

def stillseg(src,out,dur,ov=None,zoom=0.00055,flash=False):
    fc=[f"[0:v]scale=1500:2400:force_original_aspect_ratio=increase,zoompan=z='min(zoom+{zoom},1.12)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{H}:fps={FPS},eq=contrast=1.07:saturation=0.78:brightness=-0.025,noise=alls=2:allf=t+u[b]"]
    prev='b'
    if ov:fc+=['[1:v]format=rgba[o]','[b][o]overlay=0:0:shortest=1[v0]'];prev='v0'
    if flash:fc.append(f"[{prev}]drawbox=x=0:y=0:w=iw:h=ih:color=white@0.35:t=fill:enable='lt(t,0.07)'[v]")
    else:fc.append(f'[{prev}]null[v]')
    cmd=['ffmpeg','-y','-loop','1','-framerate',str(FPS),'-i',str(src)]
    if ov:cmd+=['-loop','1','-i',str(ov)]
    cmd+=['-filter_complex',';'.join(fc),'-map','[v]','-t',str(dur),'-an','-r',str(FPS),'-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p',str(out)]
    run(cmd,True)

def chart_video(mode,out,dur=5.4):
    vals_up=[8,12,10,18,15,24,20,31,28,41,38,52,49,66,62,80,77,94,90,108,103,124]
    vals_dn=[72,76,70,80,75,84,79,88,82,76,70,65,60,55,50,47,43,39,42,36,33,30]
    vals=vals_dn if mode==3 else vals_up
    proc=subprocess.Popen(['ffmpeg','-y','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{W}x{H}','-framerate',str(FPS),'-i','-','-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p',str(out)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    N=int(dur*FPS);x0=110;step=39;base=1320;sc=6.1
    for frame in range(N):
        im=Image.new('RGB',(W,H),(5,9,10));d=ImageDraw.Draw(im)
        for x in range(80,W-50,120):d.line((x,350,x,1500),fill=(24,34,35),width=1)
        for y in range(420,1500,120):d.line((65,y,W-45,y),fill=(24,34,35),width=1)
        progress=min(len(vals),max(1,int((frame/N)*len(vals)*1.25)))
        for i,v in enumerate(vals[:progress]):
            x=x0+i*step;op=base-v*sc;cl=op-(18 if i%3 else -11);hi=min(op,cl)-25;lo=max(op,cl)+25;col=GREEN if cl<op else RED
            d.line((x,hi,x,lo),fill=col,width=3);d.rectangle((x-8,min(op,cl),x+8,max(op,cl)+1),fill=col)
        if mode==1:
            y=base-66*sc;d.line((80,y,990,y),fill=GOLD,width=3)
            if frame>N*.43:
                cx=x0+14*step;cy=base-vals[14]*sc;r=22+int(5*math.sin(frame*.18));d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=GOLD,width=5)
            tag='BÀI HỌC 01';title='CHỜ GIÁ XÁC NHẬN';sub='Không đoán trước cú bứt phá.';color=GOLD
        elif mode==2:
            for idx in (12,15,18):
                if progress>idx and frame>N*.34:
                    cx=x0+idx*step;cy=base-vals[idx]*sc;r=20+int(4*math.sin(frame*.2+idx));d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=GREEN,width=4)
            tag='BÀI HỌC 02';title='CHỈ GIA TĂNG KHI ĐANG LÃI';sub='Không bình quân giá xuống vì hy vọng.';color=GREEN
        else:
            ey=base-vals[7]*sc;sy=ey+170;d.line((75,ey,995,ey),fill=GREEN,width=3);d.line((75,sy,995,sy),fill=RED,width=4)
            d.text((765,ey-48),'ĐIỂM VÀO',font=fnt(27,True),fill=GREEN);d.text((765,sy+12),'MỨC CẮT LỖ',font=fnt(27,True),fill=RED)
            tag='BÀI HỌC 03';title='XÁC ĐỊNH MỨC LỖ TRƯỚC KHI MUA';sub='Rủi ro phải được xác định trước lệnh.';color=RED
        shadow(d,(70,112),tag,fnt(29,True),GOLD);tf=fnt(53 if mode!=3 else 48,True);yy=175
        for ln in fit(d,title,tf,930):shadow(d,(70,yy),ln,tf,WHITE);yy+=65
        shadow(d,(72,yy+8),sub,fnt(29,False),color)
        proc.stdin.write(np.asarray(im,dtype=np.uint8).tobytes())
    proc.stdin.close();proc.wait();
    if proc.returncode:raise RuntimeError('chart render failed')

def music(path,dur,sr=48000):
    n=int(dur*sr);t=np.arange(n)/sr;y=np.zeros(n)
    chords=[(98,123.47,146.83),(110,130.81,164.81),(87.31,110,130.81),(130.81,164.81,196)]
    for ci,st in enumerate(np.arange(0,dur,7.0)):
        ed=min(dur,st+7.0);m=(t>=st)&(t<ed);tt=t[m]-st;env=np.minimum(tt/1.1,1)*np.minimum((ed-st-tt)/1.4,1);env=np.clip(env,0,1);pad=np.zeros_like(tt)
        for f in chords[ci%4]:pad+=np.sin(2*np.pi*f*tt)+.22*np.sin(2*np.pi*2*f*tt)
        y[m]+=pad/4*env*.11
    y*=np.clip(np.minimum(np.arange(n)/(sr*1.2),1)*np.minimum((n-1-np.arange(n))/(sr*2.0),1),0,1)
    stereo=np.stack([y,np.roll(y,int(.012*sr))*.98],1);mx=np.max(np.abs(stereo)) or 1;pcm=(stereo/mx*.52*32767).astype(np.int16)
    with wave.open(str(path),'wb') as wf:wf.setnchannels(2);wf.setsampwidth(2);wf.setframerate(sr);wf.writeframes(pcm.tobytes())

def sfx(path,dur,sr=48000):
    rng=np.random.default_rng(5);n=int(dur*sr);y=np.zeros(n)
    def add(sig,st):i=int(st*sr);j=min(n,i+len(sig));y[i:j]+=sig[:j-i]
    def hit():
        tt=np.arange(int(.28*sr))/sr;env=np.exp(-10*tt);return (np.sin(2*np.pi*66*tt)+.35*np.sin(2*np.pi*132*tt))*env*.23
    def whoosh():
        m=int(.34*sr);tt=np.arange(m)/sr;noise=np.convolve(rng.standard_normal(m),np.ones(6)/6,mode='same');env=np.sin(np.pi*tt/.34)**2;return noise*env*.08
    def page():
        m=int(.38*sr);tt=np.arange(m)/sr;noise=np.convolve(rng.standard_normal(m),np.ones(18)/18,mode='same');return noise*np.sin(np.pi*tt/.38)**1.3*.12
    for typ,st in [('hit',0.05),('whoosh',3.4),('page',7.4),('whoosh',12.0),('hit',17.8),('page',22.0),('hit',27.4),('hit',32.8),('hit',38.2),('whoosh',43.2),('page',49.0)]:add({'hit':hit(),'whoosh':whoosh(),'page':page()}[typ],st)
    mx=np.max(np.abs(y)) or 1;stereo=np.stack([y/mx*.5,np.roll(y,int(.007*sr))/mx*.48],1);pcm=(stereo*32767).astype(np.int16)
    with wave.open(str(path),'wb') as wf:wf.setnchannels(2);wf.setsampwidth(2);wf.setframerate(sr);wf.writeframes(pcm.tobytes())

def duration(p):
    r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(p)],capture_output=True,text=True,check=True);return float(r.stdout.strip())

def voice(text,out,target=53.0):
    subprocess.run([sys.executable,'-m','pip','install','-q','edge-tts'],check=True)
    raw=WORK/'voice_raw.mp3'
    cmd=['edge-tts','--voice','vi-VN-NamMinhNeural','--rate=-4%','--pitch=-7Hz','--text',text,'--write-media',str(raw)]
    for i in range(3):
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        if p.returncode==0 and raw.exists() and raw.stat().st_size>5000:break
        time.sleep(3)
    rd=duration(raw);tempo=max(.88,min(1.18,rd/target));af=f'atempo={tempo:.6f},highpass=f=70,lowpass=f=11500,equalizer=f=120:t=q:w=1:g=2.2,acompressor=threshold=-18dB:ratio=2.2:attack=15:release=180:makeup=2,loudnorm=I=-16:TP=-1.5:LRA=7'
    run(['ffmpeg','-y','-i',str(raw),'-af',af,'-ar','48000','-ac','2',str(out)],True)

def main():
    tools();files={}
    for k,u in SRC.items():
        ext='.mp4' if '.mp4' in u else '.jpg';files[k]=dl(u,WORK/f'{k}{ext}',700000 if ext=='.mp4' else 25000,optional=k in ('crowd1929','jesse'))
    panic=dl('https://commons.wikimedia.org/wiki/Special:Redirect/file/1907_Panic.png',WORK/'panic1907.png',25000,optional=True)
    if not panic:panic=fallback1907(WORK/'panic1907.jpg')
    if not files['crowd1929']:files['crowd1929']=panic
    if not files['jesse']:files['jesse']=cover_card(files['cover'],WORK/'jesse_fallback.jpg')
    cover=cover_card(files['cover'],WORK/'cover_card.jpg')
    ovs={
      'hook':hook_overlay(),
      'why':overlay('why','KHÔNG CHỈ LÀ CHUYỆN THẮNG THUA','VÌ SAO CUỐN NÀY ĐÁNG ĐỌC?','Nó kể cả cách một thiên tài tự phá hệ thống của mình.'),
      '1907':overlay('1907','1907','KHỦNG HOẢNG 1907','Một trong những bước ngoặt lớn trong sự nghiệp Livermore.'),
      '1929':overlay('1929','1929','CÚ SẬP LÀM NÊN HUYỀN THOẠI','Khoảng 100 triệu USD lợi nhuận được ghi nhận trong cú sập này.'),
      'rehook':overlay('rehook','NHƯNG…','PHẦN ĐẮT GIÁ NHẤT KHÔNG PHẢI CÚ SẬP','Mà là cách ông quản lý — và có lúc phá vỡ — kỷ luật của mình.',accent='ĐẮT GIÁ'),
      'ego':overlay('ego','ĐIỂM CHUNG CỦA 3 BÀI HỌC','ĐỪNG ĐỂ CÁI TÔI TRANH LUẬN VỚI THỊ TRƯỜNG','Hiểu thị trường là chưa đủ. Kỷ luật mới quyết định bạn tồn tại bao lâu.',accent='CÁI TÔI'),
      'qualify':qualify_overlay(),
      'cta':overlay('cta','ĐÁNH GIÁ CUỐI','ĐÁNG ĐỌC — NẾU BẠN MUỐN GIAO DỊCH KỶ LUẬT HƠN','Link sách ở bio / bình luận ghim. Có liên kết tiếp thị.',accent='ĐÁNG ĐỌC',y=1410),
    }
    segs=[]
    # 0-3.5 actual cover over moving book footage
    hookbg=WORK/'hookbg.mp4';vseg(files['book_vertical'],hookbg,.3,3.5,None,False)
    hook=WORK/'s01.mp4';fc=f"[0:v]scale={W}:{H}[b];[1:v]scale=390:-1,format=rgba[c];[b][c]overlay=W-w-70:210[m];[2:v]format=rgba[o];[m][o]overlay=0:0:shortest=1[v]";run(['ffmpeg','-y','-i',str(hookbg),'-loop','1','-i',str(files['cover']),'-loop','1','-i',str(ovs['hook']),'-filter_complex',fc,'-map','[v]','-t','3.5','-an','-r',str(FPS),'-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p',str(hook)],True);segs.append(hook)
    s=WORK/'s02.mp4';stillseg(files['jesse'],s,4.0,ovs['why'],.0007,True);segs.append(s)
    s=WORK/'s03.mp4';vseg(files['book_warm'],s,.8,4.6,ovs['why'],False);segs.append(s)
    s=WORK/'s04.mp4';stillseg(panic,s,3.0,ovs['1907'],.0007,True);segs.append(s)
    s=WORK/'s05.mp4';stillseg(files['crowd1929'],s,3.2,ovs['1929'],.00065,True);segs.append(s)
    s=WORK/'s06.mp4';vseg(files['book_candle'],s,2.0,4.2,ovs['rehook'],False);segs.append(s)
    for i in (1,2,3):
        s=WORK/f's0{6+i}.mp4';chart_video(i,s,5.4);segs.append(s)
    s=WORK/'s10.mp4';stillseg(files['jesse'],s,5.0,ovs['ego'],.0005,True);segs.append(s)
    s=WORK/'s11.mp4';vseg(files['book_dark'],s,1.0,5.4,ovs['qualify'],False);segs.append(s)
    s=WORK/'s12.mp4';stillseg(cover,s,4.0,ovs['cta'],.0002,False);segs.append(s)
    concat=WORK/'concat.txt';concat.write_text('\n'.join(f"file '{p.as_posix()}'" for p in segs),encoding='utf-8')
    silent=OUT/'Chet_Vi_Chung_Khoan_Content_First_Silent_1080p.mp4';run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),'-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-r',str(FPS),'-movflags','+faststart',str(silent)],True)
    total=duration(silent)
    narration=('Jesse Livermore từng kiếm khoảng một trăm triệu đô la trong cú sập năm 1929, rồi vẫn mất gần như tất cả. '
      'Đó là lý do tôi thấy Chết Vì Chứng Khoán đáng đọc hơn nhiều cuốn sách chỉ dạy điểm mua bán. '
      'Sách đi từ khủng hoảng 1907, cú sập 1929, đến khi nào giữ, khi nào rút và cách quản lý tiền. '
      'Nhưng phần đắt giá nhất là ba nguyên tắc này. Một, chỉ hành động khi giá xác nhận. Hai, chỉ gia tăng khi vị thế đang có lãi, không bình quân giá xuống vì hy vọng. '
      'Ba, xác định khoản lỗ trước khi bấm mua. Cả ba đều dẫn về một điều: đừng để cái tôi tranh luận với thị trường. '
      'Nếu bạn chỉ muốn tín hiệu mua bán, đừng mua cuốn này. Nếu muốn hiểu kỷ luật, tâm lý và quản lý vị thế, tôi nghĩ rất đáng đọc. '
      'Link sách tôi để ở bio hoặc bình luận ghim. Đây là liên kết tiếp thị, tôi có thể nhận hoa hồng nếu bạn mua qua link.')
    (OUT/'KICH_BAN_LOI_DOC_V7.txt').write_text(narration,encoding='utf-8')
    vo=OUT/'voice_nam_viet.wav';voice(narration,vo,max(50.0,total-1.2));bgm=OUT/'nhac_nen.wav';music(bgm,total);fx=OUT/'sfx.wav';sfx(fx,total)
    final=OUT/'Chet_Vi_Chung_Khoan_Content_First_FINAL_1080p.mp4';mix='[1:a]adelay=180|180,volume=1.0[v];[2:a]volume=0.12[m];[3:a]volume=0.40[f];[v][m][f]amix=inputs=3:duration=longest:dropout_transition=2,loudnorm=I=-15.5:TP=-1:LRA=7[a]';run(['ffmpeg','-y','-i',str(silent),'-i',str(vo),'-i',str(bgm),'-i',str(fx),'-filter_complex',mix,'-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-shortest','-movflags','+faststart',str(final)],True)
    small=OUT/'Chet_Vi_Chung_Khoan_Content_First_FINAL_720p.mp4';run(['ffmpeg','-y','-i',str(final),'-vf','scale=720:1280','-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac','-b:a','160k','-movflags','+faststart',str(small)],True)
    (OUT/'NGUON_V7.txt').write_text('\n'.join(f'{k}: {v}' for k,v in SRC.items()),encoding='utf-8');print('FINAL',final,duration(final),final.stat().st_size,flush=True)

if __name__=='__main__':main()
