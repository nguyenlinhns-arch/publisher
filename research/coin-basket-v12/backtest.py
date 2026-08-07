from __future__ import annotations
import math, os, shutil, subprocess, sys, time, wave
from pathlib import Path
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'; WORK=ROOT/'work_v6'
OUT.mkdir(parents=True,exist_ok=True); WORK.mkdir(parents=True,exist_ok=True)
W,H,FPS=1080,1920,30
WHITE=(247,244,236); GOLD=(224,173,72); RED=(209,63,56); GREEN=(74,193,111); MUTED=(196,191,181)
FONT_B='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_R='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
UA={'User-Agent':'Mozilla/5.0 Chrome/150 Safari/537.36'}
S=requests.Session(); S.headers.update(UA)

SRC={
'book_vertical':'https://videos.pexels.com/video-files/9115655/9115655-uhd_2160_3840_30fps.mp4',
'book_candle':'https://videos.pexels.com/video-files/11530055/11530055-uhd_3840_2160_25fps.mp4',
'book_warm':'https://videos.pexels.com/video-files/6981525/6981525-uhd_3840_2160_25fps.mp4',
'book_dark':'https://videos.pexels.com/video-files/7055351/7055351-uhd_3840_2160_30fps.mp4',
'book_open':'https://videos.pexels.com/video-files/11530072/11530072-uhd_3840_2160_25fps.mp4',
'cover':'https://pos.nvncdn.com/fd5775-40602/ps/20240620_vAHc49veeP.jpeg?v=1718865566',
'panic1907':'https://upload.wikimedia.org/wikipedia/commons/1/18/1907_Panic.png',
'crowd1929':'https://upload.wikimedia.org/wikipedia/commons/3/3f/Crowds_gathering_outside_New_York_Stock_Exchange.jpg',
'jesse':'https://upload.wikimedia.org/wikipedia/commons/6/67/Jesse_Livermore_%28c._1923%29_%28cropped%29.jpg',
}

def run(cmd, quiet=False):
    print('+',' '.join(map(str,cmd)),flush=True)
    kw={}
    if quiet: kw={'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL}
    return subprocess.run(cmd,check=True,**kw)

def tools():
    if not shutil.which('ffmpeg'):
        subprocess.run(['sudo','apt-get','update'],check=True)
        subprocess.run(['sudo','apt-get','install','-y','ffmpeg','fonts-dejavu-core'],check=True)

def dl(url,dest,minb=20000):
    if dest.exists() and dest.stat().st_size>=minb:return dest
    last=None
    for n in range(4):
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
    raise RuntimeError(f'download fail {url}: {last}')

def fnt(sz,b=True): return ImageFont.truetype(FONT_B if b else FONT_R,sz)

def fit(d,text,font,maxw):
    words=text.split(); lines=[]; cur=''
    for word in words:
        t=(cur+' '+word).strip(); bb=d.textbbox((0,0),t,font=font)
        if bb[2]-bb[0]<=maxw or not cur: cur=t
        else: lines.append(cur); cur=word
    if cur: lines.append(cur)
    return lines

def text_shadow(d,xy,text,font,fill,anchor='la'):
    x,y=xy; d.text((x+3,y+4),text,font=font,fill=(0,0,0,190),anchor=anchor); d.text((x,y),text,font=font,fill=fill,anchor=anchor)

def gradient(im,start=1080,alpha=205):
    d=ImageDraw.Draw(im)
    for y in range(start,H):
        a=int(min(alpha,(y-start)/(H-start)*alpha)); d.rectangle((0,y,W,y+1),fill=(0,0,0,a))

def overlay(name,tag,title,sub='',accent=None,center=False):
    im=Image.new('RGBA',(W,H),(0,0,0,0)); gradient(im)
    d=ImageDraw.Draw(im)
    if tag:
        ft=fnt(29,True); text_shadow(d,(74,104),tag.upper(),ft,GOLD)
        d.rounded_rectangle((74,150,235,156),radius=3,fill=GOLD)
    size=64 if len(title)<31 else 55
    tf=fnt(size,True); lines=fit(d,title.upper(),tf,900)
    y=1330-len(lines)*72
    for ln in lines:
        fill=GOLD if accent and accent.lower() in ln.lower() else WHITE
        if center:
            text_shadow(d,(W//2,y),ln,tf,fill,anchor='ma')
        else:
            text_shadow(d,(74,y),ln,tf,fill)
        y+=74
    if sub:
        sf=fnt(31,False); ls=fit(d,sub,sf,900); y+=12
        for ln in ls:
            text_shadow(d,(76,y),ln,sf,MUTED); y+=46
    p=WORK/f'ov_{name}.png'; im.save(p); return p

def hook_overlay(name,line1,line2):
    im=Image.new('RGBA',(W,H),(0,0,0,0)); gradient(im,1040,220); d=ImageDraw.Draw(im)
    f1=fnt(57,True); f2=fnt(82,True)
    text_shadow(d,(74,1350),line1.upper(),f1,WHITE)
    text_shadow(d,(74,1435),line2.upper(),f2,GOLD)
    d.rounded_rectangle((74,1545,340,1553),radius=4,fill=GOLD)
    p=WORK/f'ov_{name}.png'; im.save(p); return p

def cover_card(src,out):
    c=Image.open(src).convert('RGB')
    bg=c.copy(); bw,bh=bg.size; sc=max(W/bw,H/bh); bg=bg.resize((int(bw*sc),int(bh*sc)),Image.Resampling.LANCZOS)
    x=(bg.width-W)//2;y=(bg.height-H)//2;bg=bg.crop((x,y,x+W,y+H)).filter(ImageFilter.GaussianBlur(35))
    bg=Image.blend(bg,Image.new('RGB',(W,H),'black'),0.62)
    c.thumbnail((700,1000),Image.Resampling.LANCZOS); x=(W-c.width)//2; y=250
    sh=Image.new('RGBA',(W,H),(0,0,0,0)); sd=ImageDraw.Draw(sh); sd.rounded_rectangle((x+25,y+32,x+c.width+25,y+c.height+32),24,fill=(0,0,0,160)); sh=sh.filter(ImageFilter.GaussianBlur(24))
    canvas=Image.alpha_composite(bg.convert('RGBA'),sh).convert('RGB'); canvas.paste(c,(x,y))
    canvas.save(out,quality=96); return out

def collage(cover,portrait,out):
    base=Image.new('RGB',(W,H),(7,8,9)); d=ImageDraw.Draw(base)
    p=Image.open(portrait).convert('RGB'); pw,ph=p.size; sc=max((W*0.66)/pw,H/ph); p=p.resize((int(pw*sc),int(ph*sc)),Image.Resampling.LANCZOS)
    px=max(0,(p.width-int(W*0.66))//2); p=p.crop((px,0,px+int(W*0.66),H)); base.paste(p,(0,0))
    shade=Image.new('RGBA',(W,H),(0,0,0,0)); sd=ImageDraw.Draw(shade); sd.rectangle((0,0,W,H),fill=(0,0,0,40));
    for x in range(430,W):
        a=int(min(245,(x-430)/(W-430)*245)); sd.rectangle((x,0,x+1,H),fill=(0,0,0,a))
    base=Image.alpha_composite(base.convert('RGBA'),shade).convert('RGB')
    c=Image.open(cover).convert('RGB'); c.thumbnail((410,620),Image.Resampling.LANCZOS); base.paste(c,(620,350))
    dr=ImageDraw.Draw(base); text_shadow(dr,(620,1040),'JESSE LIVERMORE',fnt(42,True),GOLD); text_shadow(dr,(620,1105),'Richard Smitten',fnt(29,False),MUTED)
    base.save(out,quality=96); return out

def vseg(src,out,start,dur,ov=None,flash=False):
    filters=[f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},eq=contrast=1.07:saturation=0.82:brightness=-0.02,noise=alls=2:allf=t+u,setpts=PTS-STARTPTS[b]"]
    if ov:
        filters.append('[1:v]format=rgba[o]'); filters.append('[b][o]overlay=0:0:shortest=1[v0]'); prev='v0'
    else: prev='b'
    if flash:
        filters.append(f"[{prev}]drawbox=x=0:y=0:w=iw:h=ih:color=white@0.42:t=fill:enable='lt(t,0.08)'[v]")
    else: filters.append(f'[{prev}]null[v]')
    cmd=['ffmpeg','-y','-ss',str(start),'-i',str(src)]
    if ov: cmd += ['-loop','1','-i',str(ov)]
    cmd += ['-filter_complex',';'.join(filters),'-map','[v]','-t',str(dur),'-an','-r',str(FPS),'-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(out)]
    run(cmd,True)

def stillseg(src,out,dur,ov=None,zoom=0.0005,flash=False):
    filters=[f"[0:v]scale=1500:2400:force_original_aspect_ratio=increase,zoompan=z='min(zoom+{zoom},1.12)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={W}x{H}:fps={FPS},eq=contrast=1.07:saturation=0.78:brightness=-0.025,noise=alls=2:allf=t+u[b]"]
    if ov:
        filters.append('[1:v]format=rgba[o]'); filters.append('[b][o]overlay=0:0:shortest=1[v0]'); prev='v0'
    else: prev='b'
    if flash: filters.append(f"[{prev}]drawbox=x=0:y=0:w=iw:h=ih:color=white@0.4:t=fill:enable='lt(t,0.08)'[v]")
    else: filters.append(f'[{prev}]null[v]')
    cmd=['ffmpeg','-y','-loop','1','-framerate',str(FPS),'-i',str(src)]
    if ov: cmd += ['-loop','1','-i',str(ov)]
    cmd += ['-filter_complex',';'.join(filters),'-map','[v]','-t',str(dur),'-an','-r',str(FPS),'-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p',str(out)]
    run(cmd,True)

def cover_motion(bgvideo,cover,out,dur,ov):
    fc=(f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=12,eq=brightness=-0.12:saturation=0.6[b];"
        "[1:v]scale=590:-1,format=rgba[c];[b][c]overlay=(W-w)/2:(H-h)/2-100[m];[2:v]format=rgba[o];[m][o]overlay=0:0:shortest=1[v]")
    run(['ffmpeg','-y','-ss','0.5','-i',str(bgvideo),'-loop','1','-i',str(cover),'-loop','1','-i',str(ov),'-filter_complex',fc,'-map','[v]','-t',str(dur),'-an','-r',str(FPS),'-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p',str(out)],True)

def chart_video(mode,out,dur=6.0):
    vals_up=[8,12,10,18,15,24,20,31,28,41,38,52,49,66,62,80,77,94,90,108,103,124]
    vals_dn=[72,76,70,80,75,84,79,88,82,76,70,65,60,55,50,47,43,39,42,36,33,30]
    vals=vals_dn if mode==3 else vals_up
    proc=subprocess.Popen(['ffmpeg','-y','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{W}x{H}','-framerate',str(FPS),'-i','-','-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p',str(out)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    N=int(dur*FPS); x0=110; step=39; base=1320; sc=6.1
    for frame in range(N):
        im=Image.new('RGB',(W,H),(5,9,10)); d=ImageDraw.Draw(im)
        for x in range(80,W-50,120): d.line((x,350,x,1500),fill=(24,34,35),width=1)
        for y in range(420,1500,120): d.line((65,y,W-45,y),fill=(24,34,35),width=1)
        progress=min(len(vals),max(1,int((frame/N)*len(vals)*1.25)))
        for i,v in enumerate(vals[:progress]):
            x=x0+i*step; op=base-v*sc; cl=op-(18 if i%3 else -11); hi=min(op,cl)-25; lo=max(op,cl)+25; col=GREEN if cl<op else RED
            d.line((x,hi,x,lo),fill=col,width=3); d.rectangle((x-8,min(op,cl),x+8,max(op,cl)+1),fill=col)
        if mode==1:
            y=base-66*sc; d.line((80,y,990,y),fill=GOLD,width=3)
            if frame>N*.45:
                cx=x0+14*step; cy=base-vals[14]*sc; r=22+int(5*math.sin(frame*.18)); d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=GOLD,width=5)
            tag='BÀI HỌC 01'; title='CHỜ GIÁ XÁC NHẬN'; sub='Không đoán trước cú bứt phá.'; color=GOLD
        elif mode==2:
            for idx in (12,15,18):
                if progress>idx and frame>N*.35:
                    cx=x0+idx*step;cy=base-vals[idx]*sc;r=20+int(4*math.sin(frame*.2+idx));d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=GREEN,width=4)
            tag='BÀI HỌC 02'; title='CHỈ GIA TĂNG KHI ĐANG LÃI'; sub='Không bình quân giá xuống vì hy vọng.'; color=GREEN
        else:
            ey=base-vals[7]*sc; sy=ey+170; d.line((75,ey,995,ey),fill=GREEN,width=3); d.line((75,sy,995,sy),fill=RED,width=4)
            d.text((765,ey-48),'ĐIỂM VÀO',font=fnt(26,True),fill=GREEN); d.text((735,sy+12),'MỨC CẮT LỖ',font=fnt(26,True),fill=RED)
            tag='BÀI HỌC 03'; title='XÁC ĐỊNH MỨC LỖ TRƯỚC LỆNH'; sub='Rủi ro phải được xác định trước khi mua.'; color=RED
        d.text((72,100),tag,font=fnt(28,True),fill=GOLD); d.rounded_rectangle((72,146,250,152),radius=3,fill=GOLD)
        d.text((72,205),title,font=fnt(50 if mode!=3 else 46,True),fill=WHITE); d.text((74,275),sub,font=fnt(29,False),fill=MUTED)
        imarr=np.asarray(im,dtype=np.uint8); proc.stdin.write(imarr.tobytes())
    proc.stdin.close(); rc=proc.wait();
    if rc: raise RuntimeError('chart ffmpeg')

def music(path,duration,sr=48000):
    n=int(duration*sr); t=np.arange(n)/sr; y=np.zeros(n)
    chords=[(110,164.81,220),(98,146.83,196),(130.81,196,261.63),(87.31,130.81,174.61)]
    block=8
    for j,st in enumerate(np.arange(0,duration,block)):
        en=min(duration,st+block); m=(t>=st)&(t<en); tt=t[m]-st; env=np.minimum(tt/1.8,1)*np.minimum((en-st-tt)/1.8,1); env=np.clip(env,0,1); sig=np.zeros_like(tt)
        for f in chords[j%4]: sig += np.sin(2*np.pi*f*tt)+.18*np.sin(2*np.pi*2*f*tt)
        y[m]+=sig/3.5*env*.10
    for st in np.arange(.8,duration,2.0):
        m=(t>=st)&(t<st+.7); tt=t[m]-st; env=np.exp(-5*tt)*(1-np.exp(-18*tt)); y[m]+=.035*env*np.sin(2*np.pi*440*tt)
    mx=np.max(np.abs(y)) or 1; y=y/mx*.5; stereo=np.stack([y,np.roll(y,int(.012*sr))*.97],1); pcm=(stereo*32767).astype(np.int16)
    with wave.open(str(path),'wb') as wf: wf.setnchannels(2);wf.setsampwidth(2);wf.setframerate(sr);wf.writeframes(pcm.tobytes())

def sfx(path,duration,sr=48000):
    rng=np.random.default_rng(4); n=int(duration*sr); y=np.zeros(n)
    def add(sig,st):
        i=int(st*sr); j=min(n,i+len(sig)); y[i:j]+=sig[:j-i]
    def whoosh(d=.32,a=.16):
        m=int(d*sr); tt=np.arange(m)/sr; z=rng.normal(size=m); z=np.convolve(z,np.ones(12)/12,'same'); env=np.sin(np.pi*tt/d)**1.8; return z*env*a
    def hit(d=.25,a=.2):
        m=int(d*sr); tt=np.arange(m)/sr; return (np.sin(2*np.pi*62*tt)+.35*np.sin(2*np.pi*124*tt))*np.exp(-10*tt)*a
    def page(d=.38,a=.12):
        m=int(d*sr); tt=np.arange(m)/sr; z=rng.normal(size=m); z=np.convolve(z,np.ones(25)/25,'same'); return z*np.sin(np.pi*tt/d)*a
    for typ,st in [('hit',0.05),('whoosh',3.0),('whoosh',6.45),('hit',10.45),('hit',14.45),('whoosh',18.45),('page',23.95),('page',27.95),('page',31.95),('hit',35.95),('whoosh',41.95),('whoosh',47.95),('hit',53.95),('page',57.95)]:
        add({'whoosh':whoosh(),'hit':hit(),'page':page()}[typ],st)
    mx=np.max(np.abs(y)) or 1; y=y/mx*.65; pcm=(np.stack([y,np.roll(y,int(.006*sr))*.97],1)*32767).astype(np.int16)
    with wave.open(str(path),'wb') as wf: wf.setnchannels(2);wf.setsampwidth(2);wf.setframerate(sr);wf.writeframes(pcm.tobytes())

def duration(p):
    r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nk=1:nw=1',str(p)],capture_output=True,text=True,check=True); return float(r.stdout.strip())

def voice(text,out,target=60.0):
    subprocess.run([sys.executable,'-m','pip','install','-q','edge-tts'],check=True)
    raw=WORK/'voice_raw.mp3'
    cmd=['edge-tts','--voice','vi-VN-NamMinhNeural','--rate=+2%','--pitch=-8Hz','--text',text,'--write-media',str(raw)]
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    if p.returncode: raise RuntimeError(p.stdout)
    d=duration(raw); tempo=d/target; tempo=max(.82,min(1.18,tempo))
    af=f'atempo={tempo:.6f},highpass=f=70,lowpass=f=11500,equalizer=f=120:t=q:w=1:g=2.2,acompressor=threshold=-18dB:ratio=2.2:attack=15:release=180:makeup=2,loudnorm=I=-16:TP=-1.5:LRA=7'
    run(['ffmpeg','-y','-i',str(raw),'-af',af,'-ar','48000','-ac','2',str(out)],True)

def main():
    tools(); files={}
    for k,u in SRC.items():
        ext='.mp4' if '.mp4' in u else ('.png' if '.png' in u else '.jpg'); files[k]=dl(u,WORK/f'{k}{ext}',700000 if ext=='.mp4' else 20000)
    cover=cover_card(files['cover'],WORK/'cover_card.jpg'); col=collage(files['cover'],files['jesse'],WORK/'collage.jpg')
    ov_hook1=hook_overlay('hook1','CUỐN NÀY KHÔNG DẠY BẠN','GIÀU NHANH.')
    ov_hook2=hook_overlay('hook2','NÓ KỂ CÁI GIÁ CỦA VIỆC','MẤT KỶ LUẬT.')
    ovs={
        'cover':overlay('cover','CUỐN SÁCH','CHẾT VÌ CHỨNG KHOÁN','Richard Smitten • Jesse Livermore','CHỨNG KHOÁN'),
        '1907':overlay('1907','CHƯƠNG 4','CÚ SỤP ĐỔ NĂM 1907','Một bước ngoặt lớn trong sự nghiệp Livermore.','1907'),
        '1929':overlay('1929','CHƯƠNG 10','CÚ SẬP NĂM 1929','Khi phần đông thị trường hoảng loạn.','1929'),
        'jesse':overlay('jesse','JESSE LIVERMORE','HIỂU XU HƯỚNG. BIẾT CHỜ ĐỢI.','Nhưng kỷ luật mới quyết định kết quả.','KỶ LUẬT'),
        'ch11':overlay('ch11','CHƯƠNG 11','KHI NÀO GIỮ, KHI NÀO RÚT','Biết rút lui đúng lúc cũng là một kỹ năng.'),
        'ch12':overlay('ch12','CHƯƠNG 12','QUY TẮC QUẢN LÝ TIỀN','Không để một lệnh sai làm tổn thương cả tài khoản.'),
        'ch13':overlay('ch13','CHƯƠNG 13','KHI VẬN MAY ĐẢO CHIỀU','Bi kịch bắt đầu khi hệ thống không còn được tuân thủ.'),
        'insight':overlay('insight','ĐIỀU ĐÁNG NHỚ','HIỂU THỊ TRƯỜNG CHƯA ĐỦ.','Kỷ luật mới quyết định bạn tồn tại bao lâu.','KỶ LUẬT'),
        'cta':overlay('cta','','ĐỪNG TRẢ HỌC PHÍ BẰNG CẢ TÀI KHOẢN.','Xem sách tại bio / bình luận ghim.','HỌC PHÍ'),
    }
    scenes=[]
    out=WORK/'s01.mp4'; cover_motion(files['book_vertical'],files['cover'],out,3.0,ov_hook1); scenes.append(out)
    out=WORK/'s02.mp4'; vseg(files['book_vertical'],out,2.0,3.5,ov_hook2); scenes.append(out)
    out=WORK/'s03.mp4'; stillseg(col,out,4.0,ovs['cover'],.0003); scenes.append(out)
    out=WORK/'s04.mp4'; stillseg(files['panic1907'],out,4.0,ovs['1907'],.0007,True); scenes.append(out)
    out=WORK/'s05.mp4'; stillseg(files['crowd1929'],out,4.0,ovs['1929'],.00065,True); scenes.append(out)
    out=WORK/'s06.mp4'; stillseg(files['jesse'],out,5.5,ovs['jesse'],.00045); scenes.append(out)
    out=WORK/'s07.mp4'; vseg(files['book_dark'],out,1.0,4.0,ovs['ch11']); scenes.append(out)
    out=WORK/'s08.mp4'; vseg(files['book_open'],out,1.5,4.0,ovs['ch12']); scenes.append(out)
    out=WORK/'s09.mp4'; vseg(files['book_candle'],out,3.5,4.0,ovs['ch13']); scenes.append(out)
    out=WORK/'s10.mp4'; chart_video(1,out,6.0); scenes.append(out)
    out=WORK/'s11.mp4'; chart_video(2,out,6.0); scenes.append(out)
    out=WORK/'s12.mp4'; chart_video(3,out,6.0); scenes.append(out)
    out=WORK/'s13.mp4'; vseg(files['book_warm'],out,1.0,4.0,ovs['insight']); scenes.append(out)
    out=WORK/'s14.mp4'; cover_motion(files['book_vertical'],files['cover'],out,4.5,ovs['cta']); scenes.append(out)
    concat=WORK/'concat.txt'; concat.write_text(''.join(f"file '{p.as_posix()}'\n" for p in scenes),encoding='utf-8')
    silent=OUT/'Chet_Vi_Chung_Khoan_Affiliate_PRO_V6_Silent_1080p.mp4'
    run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),'-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-r','30','-movflags','+faststart',str(silent)],True)
    finaldur=duration(silent)
    narration=('Cuốn này không dạy bạn giàu nhanh. Nó kể cái giá phải trả khi một thiên tài đánh mất kỷ luật. '
        'Jesse Livermore từng kiếm được những gia tài lớn khi thị trường hoảng loạn, từ năm 1907 đến cú sập 1929. '
        'Nhưng phần đáng đọc nhất lại nằm ở những chương về giữ vị thế, quản lý tiền và lúc vận may đảo chiều. '
        'Tôi rút ra ba nguyên tắc. Một, chỉ hành động khi giá xác nhận. Hai, chỉ gia tăng khi vị thế đang có lợi nhuận; không bình quân giá xuống vì hy vọng. '
        'Ba, xác định mức lỗ trước khi đặt lệnh. Chết Vì Chứng Khoán không phải công thức làm giàu. '
        'Nó là lời cảnh báo rằng hiểu thị trường vẫn chưa đủ. Kỷ luật mới quyết định bạn tồn tại bao lâu. Đừng trả học phí bằng cả tài khoản.')
    (OUT/'LOI_DOC_PRO_V6.txt').write_text(narration,encoding='utf-8')
    va=OUT/'voice.wav'; voice(narration,va,max(57.5,finaldur-1.2))
    mu=OUT/'music.wav'; music(mu,finaldur); fx=OUT/'sfx.wav'; sfx(fx,finaldur)
    final=OUT/'Chet_Vi_Chung_Khoan_Affiliate_PRO_V6_1080p.mp4'
    fc='[1:a]volume=1.0[v];[2:a]volume=0.12[m];[3:a]volume=0.32[s];[v][m][s]amix=inputs=3:duration=longest:dropout_transition=1,loudnorm=I=-15.5:TP=-1.0:LRA=7[a]'
    run(['ffmpeg','-y','-i',str(silent),'-i',str(va),'-i',str(mu),'-i',str(fx),'-filter_complex',fc,'-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-shortest','-movflags','+faststart',str(final)],True)
    small=OUT/'Chet_Vi_Chung_Khoan_Affiliate_PRO_V6_720p.mp4'
    run(['ffmpeg','-y','-i',str(final),'-vf','scale=720:1280','-c:v','libx264','-preset','veryfast','-crf','22','-c:a','aac','-b:a','160k','-movflags','+faststart',str(small)],True)
    (OUT/'SOURCES_PRO_V6.txt').write_text('\n'.join(f'{k}: {v}' for k,v in SRC.items()),encoding='utf-8')
    print('FINAL',final,finaldur,final.stat().st_size,flush=True)
if __name__=='__main__': main()
