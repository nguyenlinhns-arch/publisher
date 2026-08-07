import requests

url = 'https://raw.githubusercontent.com/nguyenlinhns-arch/publisher/e9a8d8b0a7c2222dc7fa54473ebdb5a7f9b85c36/research/coin-basket-v12/backtest.py'
source = requests.get(url, timeout=30).text
source = source.replace("filt+=',null[b2];[b2][1:v]overlay=0:0:shortest=1[v]'", "filt+=';[b]null[b2];[b2][1:v]overlay=0:0:shortest=1[v]'")
source = source.replace("filt+=',null[v]'", "filt+=';[b]null[v]'")
exec(compile(source, 'native_v11_runtime.py', 'exec'), globals(), globals())
