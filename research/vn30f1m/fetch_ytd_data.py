from __future__ import annotations

import json
import math
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
from zoneinfo import ZoneInfo

OUT = Path("research/vn30f1m/ytd_output")
OUT.mkdir(parents=True, exist_ok=True)

API_URL = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
ICT = ZoneInfo("Asia/Ho_Chi_Minh")
START_LOCAL = datetime(2025, 12, 1, 0, 0, tzinfo=ICT)
END_LOCAL = datetime.now(ICT) + timedelta(minutes=10)

SESSION_START = datetime(2026, 1, 1, 0, 0, tzinfo=ICT)


def to_epoch(dt: datetime) -> int:
    return int(dt.timestamp())


def third_thursday(year: int, month: int) -> date:
    d = date(year, month, 1)
    offset = (3 - d.weekday()) % 7
    return d + timedelta(days=offset + 14)


def contract_symbol_2026(month: int) -> str:
    month_code = str(month) if month <= 9 else {10: "A", 11: "B", 12: "C"}[month]
    return f"41I1G{month_code}000"


def normalize_payload(payload: object, requested_symbol: str) -> pd.DataFrame:
    if not isinstance(payload, list) or not payload:
        return pd.DataFrame()
    obj = payload[0]
    if not isinstance(obj, dict):
        return pd.DataFrame()
    required = ("t", "o", "h", "l", "c", "v")
    if not all(k in obj for k in required):
        return pd.DataFrame()
    lengths = [len(obj[k]) for k in required if isinstance(obj[k], list)]
    if len(lengths) != len(required) or not lengths:
        return pd.DataFrame()
    n = min(lengths)
    if n <= 0:
        return pd.DataFrame()
    df = pd.DataFrame(
        {
            "timestamp": pd.to_numeric(pd.Series(obj["t"][:n]), errors="coerce"),
            "open": pd.to_numeric(pd.Series(obj["o"][:n]), errors="coerce"),
            "high": pd.to_numeric(pd.Series(obj["h"][:n]), errors="coerce"),
            "low": pd.to_numeric(pd.Series(obj["l"][:n]), errors="coerce"),
            "close": pd.to_numeric(pd.Series(obj["c"][:n]), errors="coerce"),
            "volume": pd.to_numeric(pd.Series(obj["v"][:n]), errors="coerce"),
        }
    )
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"])
    if df.empty:
        return df
    df["timestamp"] = df["timestamp"].astype("int64")
    df["time"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert(ICT)
    df["symbol"] = str(obj.get("symbol") or requested_symbol)
    df["requested_symbol"] = requested_symbol
    return df[["time", "timestamp", "open", "high", "low", "close", "volume", "symbol", "requested_symbol"]]


def fetch_page(session: requests.Session, symbol: str, to_ts: int, count_back: int = 5000) -> tuple[pd.DataFrame, dict]:
    payload = {"timeFrame": "ONE_MINUTE", "symbols": [symbol], "to": int(to_ts), "countBack": int(count_back)}
    response = session.post(API_URL, json=payload, timeout=(10, 90))
    response.raise_for_status()
    data = response.json()
    df = normalize_payload(data, symbol)
    meta = {
        "symbol": symbol,
        "to": int(to_ts),
        "status": response.status_code,
        "bytes": len(response.content),
        "rows": int(len(df)),
        "min_timestamp": int(df["timestamp"].min()) if not df.empty else None,
        "max_timestamp": int(df["timestamp"].max()) if not df.empty else None,
    }
    return df, meta


def fetch_range(session: requests.Session, symbol: str, start_local: datetime, end_local: datetime, max_pages: int = 60) -> tuple[pd.DataFrame, list[dict]]:
    start_ts = to_epoch(start_local)
    cursor = to_epoch(end_local)
    frames: list[pd.DataFrame] = []
    logs: list[dict] = []
    seen_min: set[int] = set()

    for page_no in range(1, max_pages + 1):
        df, meta = fetch_page(session, symbol, cursor)
        meta["page"] = page_no
        logs.append(meta)
        if df.empty:
            break
        frames.append(df)
        min_ts = int(df["timestamp"].min())
        if min_ts <= start_ts:
            break
        if min_ts in seen_min or min_ts >= cursor:
            logs.append({"symbol": symbol, "page": page_no, "warning": "pagination made no progress", "cursor": cursor, "min_ts": min_ts})
            break
        seen_min.add(min_ts)
        cursor = min_ts - 1
        time.sleep(0.15)

    if not frames:
        return pd.DataFrame(), logs
    result = pd.concat(frames, ignore_index=True)
    result = result.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp")
    result = result[(result["timestamp"] >= start_ts) & (result["timestamp"] <= to_epoch(end_local))].reset_index(drop=True)
    return result, logs


def trading_slice(df: pd.DataFrame, start_day: date, end_day: date) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    local_date = df["time"].dt.date
    return df[(local_date >= start_day) & (local_date <= end_day)].copy()


def main() -> None:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Content-Type": "application/json",
            "Origin": "https://trading.vietcap.com.vn",
            "Referer": "https://trading.vietcap.com.vn/",
        }
    )

    manifest: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start_local": START_LOCAL.isoformat(),
        "end_local": END_LOCAL.isoformat(),
        "api_url": API_URL,
        "symbols": {},
    }

    # Continuous front-month alias for validation and a VN30 index confirmation series.
    fetched: dict[str, pd.DataFrame] = {}
    for symbol in ["VN30F1M", "VN30"]:
        df, logs = fetch_range(session, symbol, START_LOCAL, END_LOCAL)
        fetched[symbol] = df
        manifest["symbols"][symbol] = {
            "rows": int(len(df)),
            "first": str(df["time"].min()) if not df.empty else None,
            "last": str(df["time"].max()) if not df.empty else None,
            "pages": logs,
        }
        if not df.empty:
            df.to_csv(OUT / f"{symbol}_1m_raw.csv", index=False)

    # Explicit monthly contracts, stitched according to front-month expiry windows.
    contract_frames: list[pd.DataFrame] = []
    contract_windows: list[dict] = []
    previous_expiry = date(2025, 12, 18)
    for month in range(1, 9):
        symbol = contract_symbol_2026(month)
        expiry = third_thursday(2026, month)
        active_start = max(date(2026, 1, 1), previous_expiry + timedelta(days=1))
        active_end = min(expiry, END_LOCAL.date())
        fetch_start = datetime.combine(active_start - timedelta(days=7), datetime.min.time(), tzinfo=ICT)
        fetch_end = min(END_LOCAL, datetime.combine(expiry + timedelta(days=1), datetime.min.time(), tzinfo=ICT))
        df, logs = fetch_range(session, symbol, fetch_start, fetch_end, max_pages=12)
        active = trading_slice(df, active_start, active_end)
        active["front_month_contract"] = symbol
        contract_frames.append(active)
        contract_windows.append(
            {
                "month": month,
                "symbol": symbol,
                "expiry": expiry.isoformat(),
                "active_start": active_start.isoformat(),
                "active_end": active_end.isoformat(),
                "raw_rows": int(len(df)),
                "active_rows": int(len(active)),
                "raw_first": str(df["time"].min()) if not df.empty else None,
                "raw_last": str(df["time"].max()) if not df.empty else None,
                "pages": logs,
            }
        )
        if not df.empty:
            df.to_csv(OUT / f"{symbol}_1m_raw.csv", index=False)
        previous_expiry = expiry

    front = pd.concat(contract_frames, ignore_index=True) if contract_frames else pd.DataFrame()
    if not front.empty:
        front = front.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp").reset_index(drop=True)
        front = front[front["time"] >= SESSION_START].copy()
        front.to_csv(OUT / "VN30F1M_front_month_2026_1m.csv", index=False)

    # Compare explicit stitched series against the alias for data-quality diagnostics.
    alias = fetched.get("VN30F1M", pd.DataFrame())
    compare = {}
    if not alias.empty and not front.empty:
        m = front[["timestamp", "close"]].merge(
            alias[["timestamp", "close"]], on="timestamp", how="inner", suffixes=("_explicit", "_alias")
        )
        if not m.empty:
            diff = (m["close_explicit"] - m["close_alias"]).abs()
            compare = {
                "overlap_rows": int(len(m)),
                "match_rows_0_1_point": int((diff <= 0.100001).sum()),
                "match_rate_0_1_point": float((diff <= 0.100001).mean()),
                "median_abs_diff": float(diff.median()),
                "p95_abs_diff": float(diff.quantile(0.95)),
                "max_abs_diff": float(diff.max()),
            }
            m.assign(abs_diff=diff).to_csv(OUT / "alias_vs_explicit_comparison.csv", index=False)

    manifest["contract_windows"] = contract_windows
    manifest["front_month"] = {
        "rows": int(len(front)),
        "first": str(front["time"].min()) if not front.empty else None,
        "last": str(front["time"].max()) if not front.empty else None,
    }
    manifest["alias_vs_explicit"] = compare
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
