from __future__ import annotations
import shutil, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'; OUT.mkdir(parents=True,exist_ok=True)
TEXT='''Trong Chết Vì Chứng Khoán, có một chi tiết tôi nhớ hơn cả 1929. Năm 1901, Jesse Livermore trắng tay. Ông xin Nettie cho cầm bộ nữ trang khoảng mười hai nghìn đô mà ông từng mua tặng bà để lấy vốn quay lại thị trường. Bà từ chối. Livermore phải vay mượn làm lại. Năm 1907 ông thắng lớn. Năm 1929 ông kiếm khoảng một trăm triệu đô khi Wall Street sụp đổ. Nhưng 1934, ông lại phá sản. Đọc tới đây, tôi nghĩ tới Việt Nam 2022: khi thị trường giảm sâu, đòn bẩy có thể tước mất quyền chờ. Ba điều tôi gạch lại: chờ giá xác nhận; chỉ gia tăng vị thế đang đúng; biết mức lỗ trước khi mua. Tôi không đọc cuốn này để học giàu nhanh, mà để nhớ: sống sót quan trọng hơn một cú thắng lớn. Nếu thích sách kể chuyện thật về tâm lý và kỷ luật giao dịch, link ở bio hoặc bình luận ghim.'''

def run(cmd):
 print('+',' '.join(map(str,cmd)),flush=True); subprocess.run(cmd,check=True)
def dur(p):
 return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nk=1:nw=1',str(p)],text=True).strip())
def main():
 if not shutil.which('ffmpeg'):
  run(['sudo','apt-get','update']); run(['sudo','apt-get','install','-y','ffmpeg'])
 run([sys.executable,'-m','pip','install','-q','edge-tts'])
 raw=OUT/'NamMinh_V12_raw.mp3'
 cmd=['edge-tts','--voice','vi-VN-NamMinhNeural','--rate=-4%','--pitch=-8Hz','--text',TEXT,'--write-media',str(raw)]
 for a in range(4):
  p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  if p.returncode==0 and raw.exists() and raw.stat().st_size>5000: break
  time.sleep(2+a*2)
 if not raw.exists() or raw.stat().st_size<5000: raise RuntimeError('edge tts failed')
 af='highpass=f=70,lowpass=f=11500,equalizer=f=130:t=q:w=1:g=2.4,equalizer=f=300:t=q:w=1:g=-0.8,equalizer=f=3200:t=q:w=1:g=1.1,acompressor=threshold=-18dB:ratio=2.2:attack=15:release=180:makeup=2,loudnorm=I=-16:TP=-1.5:LRA=7'
 wav=OUT/'NamMinh_V12_Master.wav'; run(['ffmpeg','-y','-i',str(raw),'-af',af,'-ar','48000','-ac','2',str(wav)])
 mp3=OUT/'NamMinh_V12_Master.mp3'; run(['ffmpeg','-y','-i',str(wav),'-c:a','libmp3lame','-b:a','192k',str(mp3)])
 (OUT/'LOI_DOC_V12.txt').write_text(TEXT,encoding='utf-8')
 print('VOICE_DURATION',dur(wav),flush=True)
if __name__=='__main__': main()
