import requests

url = 'https://raw.githubusercontent.com/nguyenlinhns-arch/publisher/e9a8d8b0a7c2222dc7fa54473ebdb5a7f9b85c36/research/coin-basket-v12/backtest.py'
source = requests.get(url, timeout=30).text
source = source.replace("filt+=',null[b2];[b2][1:v]overlay=0:0:shortest=1[v]'", "filt+=';[b]null[b2];[b2][1:v]overlay=0:0:shortest=1[v]'")
source = source.replace("filt+=',null[v]'", "filt+=';[b]null[v]'")
source = source.replace("fc='[1:a]volume=1.0[v];[2:a]volume=0.13[m];[3:a]volume=0.24[s];[m][v]sidechaincompress=threshold=0.025:ratio=8:attack=12:release=260[md];[md][v][s]amix=inputs=3:duration=longest:dropout_transition=1,loudnorm=I=-14.5:TP=-1.0:LRA=8[a]'", "fc='[1:a]volume=1.0,asplit=2[vsc][vmix];[2:a]volume=0.13[m];[3:a]volume=0.24[s];[m][vsc]sidechaincompress=threshold=0.025:ratio=8:attack=12:release=260[md];[md][vmix][s]amix=inputs=3:duration=longest:dropout_transition=1,loudnorm=I=-14.5:TP=-1.0:LRA=8[a]'")
exec(compile(source, 'native_v11_runtime.py', 'exec'), globals(), globals())
