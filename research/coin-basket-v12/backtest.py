import requests

SOURCE_URL = "https://raw.githubusercontent.com/nguyenlinhns-arch/publisher/d315a9df8b5b4d354136827e8be8858e171cd327/research/coin-basket-v12/backtest.py"
r = requests.get(SOURCE_URL, timeout=60)
r.raise_for_status()
code = r.text

# Use real Library of Congress archival photographs for the market-panic scenes.
code = code.replace(
    "https://upload.wikimedia.org/wikipedia/commons/1/18/1907_Panic.png",
    "https://tile.loc.gov/storage-services/service/pnp/ds/16700/16775v.jpg",
)
code = code.replace(
    "https://upload.wikimedia.org/wikipedia/commons/3/3f/Crowds_gathering_outside_New_York_Stock_Exchange.jpg",
    "https://cdn.loc.gov/service/pnp/cph/3c20000/3c23000/3c23400/3c23429v.jpg",
)
code = code.replace(
    "https://upload.wikimedia.org/wikipedia/commons/6/67/Jesse_Livermore_%28c._1923%29_%28cropped%29.jpg",
    "https://commons.wikimedia.org/wiki/Special:Redirect/file/Jesse_Livermore_%28c._1923%29_%28cropped%29.jpg?width=960",
)

# Keep portrait retrieval non-blocking; if Commons throttles, preserve the render with archival imagery.
old = "ext='.mp4' if '.mp4' in u else ('.png' if '.png' in u else '.jpg'); files[k]=dl(u,WORK/f'{k}{ext}',700000 if ext=='.mp4' else 20000)"
new = "ext='.mp4' if '.mp4' in u else ('.png' if '.png' in u else '.jpg')\n        try:\n            files[k]=dl(u,WORK/f'{k}{ext}',700000 if ext=='.mp4' else 20000)\n        except Exception as e:\n            if k=='jesse':\n                print('Jesse portrait unavailable; using 1929 archival image fallback:', e, flush=True)\n                files[k]=files['crowd1929']\n            else:\n                raise"
if old not in code:
    raise RuntimeError("Expected render source pattern not found")
code = code.replace(old, new)

exec(compile(code, "render_v6_runtime.py", "exec"), globals(), globals())
