from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
OUT.mkdir(parents=True, exist_ok=True)

TEXT = """Năm 1929, khi Wall Street hoảng loạn, Jesse Livermore kiếm khoảng một trăm triệu đô la.

Trước đó, ông cũng từng thắng lớn trong khủng hoảng năm 1907. Ông hiểu xu hướng... và biết chờ đợi.

Nhưng vài năm sau, gần như tất cả lại biến mất.

Đó là phần tôi thấy đắt nhất trong Chết Vì Chứng Khoán: một người cực giỏi vẫn có thể thua... khi kỷ luật biến mất.

Nghe rất xa. Nhưng nhìn Việt Nam năm 2022. VN-Index từ một nghìn năm trăm ba mươi sáu điểm xuống còn tám trăm bảy mươi ba điểm; áp lực ký quỹ và bán giải chấp xuất hiện dày đặc.

Bối cảnh khác... bài học lại rất giống nhau.

Chờ giá xác nhận.

Chỉ gia tăng khi vị thế đang thắng.

Và quyết định mức lỗ trước khi bấm mua.

Tôi không đọc cuốn này để học cách thắng một cú sập. Tôi đọc để nhớ rằng thị trường không cần mình đúng... mình cần sống sót đủ lâu.

Nếu bạn muốn hiểu tâm lý và kỷ luật giao dịch, đây là cuốn đáng đọc. Link tiếp thị ở bio hoặc bình luận ghim."""


def run(cmd):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run(cmd, check=True)


def duration(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], text=True)
    return float(out.strip())


def atempo_chain(x: float) -> str:
    parts=[]
    while x > 2.0:
        parts.append(2.0); x /= 2.0
    while x < 0.5:
        parts.append(0.5); x /= 0.5
    parts.append(x)
    return ",".join(f"atempo={p:.6f}" for p in parts)


def main():
    if not shutil.which("ffmpeg"):
        run(["sudo", "apt-get", "update"])
        run(["sudo", "apt-get", "install", "-y", "ffmpeg"])
    run([sys.executable, "-m", "pip", "install", "-q", "edge-tts"])

    raw = OUT / "NamMinh_raw.mp3"
    cmd = [
        "edge-tts",
        "--voice", "vi-VN-NamMinhNeural",
        "--rate=-4%",
        "--pitch=-8Hz",
        "--text", TEXT,
        "--write-media", str(raw),
    ]
    last = None
    for attempt in range(4):
        p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if p.returncode == 0 and raw.exists() and raw.stat().st_size > 5000:
            break
        last = p.stdout
        time.sleep(2 + attempt * 2)
    if not raw.exists() or raw.stat().st_size <= 5000:
        raise RuntimeError(f"edge-tts failed: {last}")

    # Match the current storytelling video while preserving the requested -4% delivery.
    target = 53.5
    raw_dur = duration(raw)
    tempo = max(0.92, min(1.08, raw_dur / target))
    af = (
        atempo_chain(tempo)
        + ",highpass=f=70"
        + ",lowpass=f=11500"
        + ",equalizer=f=130:t=q:w=1:g=2.4"
        + ",equalizer=f=280:t=q:w=1.2:g=-0.8"
        + ",equalizer=f=3200:t=q:w=1:g=1.2"
        + ",acompressor=threshold=-18dB:ratio=2.2:attack=15:release=180:makeup=2"
        + ",loudnorm=I=-16:TP=-1.5:LRA=7"
    )
    processed = OUT / "NamMinh_Storytelling_Master.wav"
    run(["ffmpeg", "-y", "-i", str(raw), "-af", af, "-ar", "48000", "-ac", "2", str(processed)])

    mp3 = OUT / "NamMinh_Storytelling_Master.mp3"
    run(["ffmpeg", "-y", "-i", str(processed), "-c:a", "libmp3lame", "-b:a", "192k", str(mp3)])
    (OUT / "LOI_DOC_NAM_MINH.txt").write_text(TEXT, encoding="utf-8")
    print("VOICE_DURATION", duration(processed), flush=True)


if __name__ == "__main__":
    main()
