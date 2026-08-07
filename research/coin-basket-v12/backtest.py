from pathlib import Path
import os, re, subprocess, sys, time, wave
import numpy as np
import requests

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output'; OUT.mkdir(exist_ok=True)
OLD='https://raw.githubusercontent.com/nguyenlinhns-arch/publisher/16d77c7ed47050bc7a22e0abb091be3a9249a7ea/research/coin-basket-v12/backtest.py'

def run(cmd):
    print('+',' '.join(map(str,cmd)), flush=True)
    return subprocess.run(cmd,check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)

def dur(p):
    return float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(p)]).stdout.strip())

def atempo(x):
    a=[]
    while x>2: a.append(2.0); x/=2
    while x<0.5: a.append(0.5); x/=0.5
    a.append(x)
    return ','.join(f'atempo={v:.6f}' for v in a)

def music(path,duration,sr=44100):
    n=int(duration*sr); t=np.arange(n)/sr; y=np.zeros(n)
    chords=[(110,130.81,164.81),(87.31,110,130.81),(130.81,164.81,196),(98,123.47,146.83)]
    for ci,st in enumerate(np.arange(0,duration,8.0)):
        en=min(duration,st+8); m=(t>=st)&(t<en); tt=t[m]-st; env=np.clip(np.minimum(tt/1.6,(en-st-tt)/1.6),0,1); z=np.zeros_like(tt)
        for f in chords[ci%4]: z+=np.sin(2*np.pi*f*tt)+.22*np.sin(4*np.pi*f*tt)
        y[m]+=z/3.7*env*.12
    fade=np.clip(np.minimum(np.arange(n)/(sr*2.5),(n-1-np.arange(n))/(sr*3.0)),0,1); y*=fade
    st=np.stack([y,np.roll(y,int(.011*sr))],axis=1); st=(st/(np.max(np.abs(st)) or 1)*.55*32767).astype(np.int16)
    with wave.open(str(path),'wb') as w: w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes(st.tobytes())

def main():
    code=requests.get(OLD,timeout=60).text
    repl={
      '1907 → 1929 → QUẢN TRỊ TIỀN → SUY SỤP':'1907 → 1929 → QUẢN LÝ TIỀN → VẬN MAY ĐẢO CHIỀU',
      'CHAPTER 4 — THE CRASH OF 1907':'CHƯƠNG 4 — CÚ SỤP ĐỔ NĂM 1907',
      'CHAPTER 10 — THE CRASH OF 1929':'CHƯƠNG 10 — CÚ SỤP ĐỔ NĂM 1929',
      'CHAPTER 11 — WHEN TO HOLD AND WHEN TO FOLD':'CHƯƠNG 11 — KHI NÀO GIỮ, KHI NÀO RÚT',
      "CHAPTER 12 — LIVERMORE'S MONEY-MANAGEMENT RULES":'CHƯƠNG 12 — QUY TẮC QUẢN LÝ TIỀN',
      'CHAPTER 13 — LIVERMORE’S LUCK SOURS':'CHƯƠNG 13 — KHI VẬN MAY ĐẢO CHIỀU',
      "CHAPTER 13 — LIVERMORE'S LUCK SOURS":'CHƯƠNG 13 — KHI VẬN MAY ĐẢO CHIỀU',
      'STOP-LOSS':'MỨC CẮT LỖ', 'RISK 1–2%':'RỦI RO 1–2%', 'ENTRY':'ĐIỂM VÀO'}
    for a,b in repl.items(): code=code.replace(a,b)
    code=code.replace('Chet_Vi_Chung_Khoan_Affiliate_Silent_V1_1080x1920.mp4','Chet_Vi_Chung_Khoan_Affiliate_VN_Silent_1080x1920.mp4').replace('Chet_Vi_Chung_Khoan_Affiliate_Silent_V1_720x1280.mp4','Chet_Vi_Chung_Khoan_Affiliate_VN_Silent_720x1280.mp4')
    patched=ROOT/'render_vn_patched.py'; patched.write_text(code,encoding='utf-8'); run([sys.executable,str(patched)])
    silent=OUT/'Chet_Vi_Chung_Khoan_Affiliate_VN_Silent_1080x1920.mp4'; total=dur(silent)
    text=('Jesse Livermore từng kiếm được những khoản tiền rất lớn khi thị trường hoảng loạn, nhưng cuối cùng lại thất bại vì chính những sai lầm kỷ luật. '
          'Chết Vì Chứng Khoán của Richard Smitten không chỉ kể cuộc đời Livermore. Sách đi qua khủng hoảng năm 1907, cú sập năm 1929, cách giữ hoặc rút khỏi vị thế và những quy tắc quản lý tiền. '
          'Tôi rút ra ba nguyên tắc. Một, chỉ hành động khi giá xác nhận nhận định. Hai, chỉ gia tăng khi vị thế đang có lợi nhuận; không bình quân giá xuống vì hy vọng. Ba, xác định mức lỗ trước khi đặt lệnh, để một giao dịch sai không làm tổn thương cả tài khoản. '
          'Đây không phải cuốn sách dạy làm giàu nhanh. Đây là lời nhắc rằng hiểu thị trường là chưa đủ. Kỷ luật mới quyết định bạn tồn tại bao lâu. Đừng trả học phí bằng cả tài khoản.')
    (OUT/'LOI_DOC_TIENG_VIET.txt').write_text(text,encoding='utf-8')
    subprocess.run([sys.executable,'-m','pip','install','-q','edge-tts'],check=True)
    raw=OUT/'giong_nam_raw.mp3'; cmd=['edge-tts','--voice','vi-VN-NamMinhNeural','--rate=-2%','--pitch=-8Hz','--text',text,'--write-media',str(raw)]
    for i in range(3):
        p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if p.returncode==0 and raw.exists() and raw.stat().st_size>5000: break
        print('TTS retry',i+1,p.stdout); time.sleep(3)
    target=max(58,total-3.0); tempo=max(.90,min(1.12,dur(raw)/target)); voice=OUT/'giong_nam_tram_am.wav'
    af=atempo(tempo)+',highpass=f=70,lowpass=f=11500,equalizer=f=120:t=q:w=1:g=2.2,acompressor=threshold=-18dB:ratio=2.2:attack=15:release=180:makeup=2,loudnorm=I=-16:TP=-1.5:LRA=7'
    run(['ffmpeg','-y','-i',str(raw),'-af',af,'-ar','48000','-ac','2',str(voice)])
    bg=OUT/'nhac_nen_nhe.wav'; music(bg,total)
    final=OUT/'Chet_Vi_Chung_Khoan_Affiliate_VN_Voice_Music_1080x1920.mp4'; fc='[1:a]volume=1.0[v];[2:a]volume=0.14[m];[v][m]amix=inputs=2:duration=longest:dropout_transition=2,loudnorm=I=-15.5:TP=-1.0:LRA=7[a]'
    run(['ffmpeg','-y','-i',str(silent),'-i',str(voice),'-i',str(bg),'-filter_complex',fc,'-map','0:v:0','-map','[a]','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-shortest','-movflags','+faststart',str(final)])
    small=OUT/'Chet_Vi_Chung_Khoan_Affiliate_VN_Voice_Music_720x1280.mp4'; run(['ffmpeg','-y','-i',str(final),'-vf','scale=720:1280','-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac','-b:a','160k','-movflags','+faststart',str(small)])
    (OUT/'GHI_CHU_V3.txt').write_text('Chữ chèn: tiếng Việt; ngoại lệ chỉ tên riêng Richard Smitten và Jesse Livermore.\nGiọng: vi-VN-NamMinhNeural, hạ cao độ nhẹ, xử lý ấm/rõ.\nNhạc nền: tự tổng hợp, không vướng bản quyền.\n',encoding='utf-8')
    print('FINAL',final,final.stat().st_size,'duration',dur(final))

if __name__=='__main__': main()
