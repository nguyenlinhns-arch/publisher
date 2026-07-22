from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT = Path("research/vn30f1m/output")
OUT.mkdir(parents=True, exist_ok=True)


def record_response(name: str, response: requests.Response, results: dict) -> None:
    item = {
        "status": response.status_code,
        "url": response.url,
        "content_type": response.headers.get("content-type"),
        "length": len(response.content),
        "head": response.text[:1200],
    }
    try:
        payload = response.json()
        item["json_type"] = type(payload).__name__
        if isinstance(payload, dict):
            item["json_keys"] = list(payload.keys())[:50]
        elif isinstance(payload, list):
            item["json_len"] = len(payload)
            if payload:
                item["first_type"] = type(payload[0]).__name__
                if isinstance(payload[0], dict):
                    item["first_keys"] = list(payload[0].keys())[:50]
        if response.status_code == 200 and len(response.content) < 10_000_000:
            (OUT / f"{name}.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
    except Exception:
        pass
    results[name] = item


def main() -> None:
    results: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
    }
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
        }
    )

    # Public S3 metadata archive.
    try:
        r = session.get("https://s3.aipriceaction.com/meta/tickers.json", timeout=30)
        record_response("aipa_tickers", r, results)
    except Exception as exc:
        results["aipa_tickers"] = {"error": repr(exc), "trace": traceback.format_exc()}

    # KBS public chart endpoint: try wrapper and explicit 2026 contracts.
    kbs_symbols = [
        "VN30F1M",
        "VN30F2607",
        "41I1G7000",
        "VN30F2601",
        "41I1G1000",
    ]
    for symbol in kbs_symbols:
        for suffix in ("1P", "5P", "D"):
            name = f"kbs_{symbol}_{suffix}".replace("/", "_")
            url = (
                "https://kbbuddywts.kbsec.com.vn/iis-server/investment/"
                f"stocks/{symbol}/data_{suffix}"
            )
            try:
                r = session.get(
                    url,
                    params={"sdate": "01-07-2026", "edate": "22-07-2026"},
                    timeout=30,
                )
                record_response(name, r, results)
            except Exception as exc:
                results[name] = {"error": repr(exc), "trace": traceback.format_exc()}

    # Vietcap chart endpoint.
    vci_symbols = ["VN30F1M", "VN30F2607", "41I1G7000", "VN30F2601", "41I1G1000"]
    vci_url = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
    end_stamp = int(datetime(2026, 7, 23, tzinfo=timezone.utc).timestamp())
    for symbol in vci_symbols:
        for tf in ("ONE_MINUTE", "ONE_DAY"):
            name = f"vci_{symbol}_{tf}"
            try:
                r = session.post(
                    vci_url,
                    json={"timeFrame": tf, "symbols": [symbol], "to": end_stamp, "countBack": 5000},
                    timeout=45,
                )
                record_response(name, r, results)
            except Exception as exc:
                results[name] = {"error": repr(exc), "trace": traceback.format_exc()}

    # vnstock unified interface, if package API/source supports the contracts.
    try:
        from vnstock import Quote  # type: ignore

        for source in ("KBS", "VCI"):
            for symbol in ("VN30F1M", "VN30F2607", "41I1G7000"):
                name = f"vnstock_{source}_{symbol}"
                try:
                    q = Quote(symbol=symbol, source=source)
                    df = q.history(
                        start="2026-07-01",
                        end="2026-07-22",
                        interval="5m",
                        show_log=False,
                    )
                    results[name] = {
                        "rows": int(len(df)),
                        "columns": list(df.columns),
                        "first": df.head(2).astype(str).to_dict("records"),
                        "last": df.tail(2).astype(str).to_dict("records"),
                    }
                    if len(df):
                        df.to_csv(OUT / f"{name}.csv", index=False)
                except Exception as exc:
                    results[name] = {"error": repr(exc), "trace": traceback.format_exc()}
    except Exception as exc:
        results["vnstock_import"] = {"error": repr(exc), "trace": traceback.format_exc()}

    (OUT / "diagnostic.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
