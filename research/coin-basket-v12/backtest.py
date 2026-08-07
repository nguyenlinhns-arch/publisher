from __future__ import annotations
import shutil, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'; OUT.mkdir(parents=True,exist_ok=True)
PARAS=[
"Trước khi kiếm khoảng một trăm triệu đô trong cú sập năm 1929, Jesse Livermore từng trắng tay.",
"Năm 1901, ông xin người vợ đầu Nettie cho cầm bộ nữ trang mười hai nghìn đô ông mua ở châu Âu để lấy vốn quay lại thị trường. Bà từ chối. Hai người rạn nứt, còn ông phải vay mượn để làm lại.",
"Năm 1907, Livermore thắng lớn trong hoảng loạn. Năm 1929, ông lại đứng đúng phía cú sập. Nhưng năm 1934, ông lại phá sản.",
"Đó là phần tôi thấy đắt nhất trong Chết Vì Chứng Khoán. Không phải bí quyết kiếm tiền, mà là vòng lặp kiếm rồi mất khi kỷ luật vỡ.",
"Nhìn Việt Nam năm 2022: VN-Index giảm hơn bốn mươi phần trăm từ đỉnh. Bối cảnh khác, bài học giống nhau: chờ giá xác nhận; chỉ gia tăng vị thế đang thắng; xác định mức lỗ trước khi mua.",
"Thị trường không cần mình đúng. Mình cần sống sót đủ lâu.",
"Nếu bạn muốn hiểu tâm lý, kỷ luật và quản trị vị thế, cuốn này đáng đọc."
]
TEXT='\n\n'.join(PARAS)
def run(c): subprocess.run(c,check=True)
def dur(p): return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(p)],text=True).strip())
def main():
    if not shutil.which('ffmpeg'):
        run(['sudo','apt-get','update']); run(['sudo','apt-get','install','-y','ffmpeg'])
    run([sys.executable,'-m','pip','install','-q','edge-tts'])
    chunks=[]
    for i,t in enumerate(PARAS,1):
        p=OUT/f'chunk_{i:02d}.mp3'; chunks.append(p)
        cmd=['edge-tts','--voice','vi-VN-NamMinhNeural','--rate=-4%','--pitch=-8Hz','--text',t,'--write-media',str(p)]
        for a in range(4):
            r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            if r.returncode==0 and p.exists() and p.stat().st_size>3000: break
            time.sleep(2+a*2)
    con=OUT/'concat.txt'; con.write_text(''.join(f"file '{p.as_posix()}'\n" for p in chunks),encoding='utf-8')
    raw=OUT/'NamMinh_V10_raw.mp3'; run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(con),'-c:a','libmp3lame','-b:a','192k',str(raw)])
    af='highpass=f=70,lowpass=f=11500,equalizer=f=130:t=q:w=1:g=2.4,equalizer=f=280:t=q:w=1.2:g=-0.8,equalizer=f=3200:t=q:w=1:g=1.2,acompressor=threshold=-18dB:ratio=2.2:attack=15:release=180:makeup=2,loudnorm=I=-16:TP=-1.5:LRA=7'
    wav=OUT/'NamMinh_V10_Master.wav'; run(['ffmpeg','-y','-i',str(raw),'-af',af,'-ar','48000','-ac','2',str(wav)])
    mp3=OUT/'NamMinh_V10_Master.mp3'; run(['ffmpeg','-y','-i',str(wav),'-c:a','libmp3lame','-b:a','192k',str(mp3)])
    (OUT/'LOI_DOC_V10.txt').write_text(TEXT,encoding='utf-8')
    print('VOICE_DURATION',dur(wav))
if __name__=='__main__': main()
