from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import requests
from numba import njit
from scipy.stats import norm

SEED = 20260724
RNG = np.random.default_rng(SEED)
random.seed(SEED)

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "output" / "raw"
RESULT_DIR = ROOT / "results"
RAW_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)

SYMBOLS = ("BTCUSDT", "ETHUSDT")
TIMEFRAMES = {"5m": 5, "15m": 15, "30m": 30, "60m": 60}
FAMILIES = (
    "TREND_PULLBACK",
    "MOMENTUM_CONTINUATION",
    "DONCHIAN_BREAKOUT",
    "SQUEEZE_BREAKOUT",
    "SWEEP_RECLAIM",
    "RANGE_REVERSION",
    "VWAP_RECLAIM",
    "STOCH_REVERSAL",
    "CROWDING_REVERSAL",
)

URLS: dict[str, str] = {}
for symbol in SYMBOLS:
    base = f"https://huggingface.co/datasets/linxy/USDT-M_Perpetual_Futures/resolve/main/{symbol}"
    URLS[f"{symbol}_5m.parquet"] = f"{base}/{symbol}_5m.parquet?download=true"
    URLS[f"{symbol}_metrics.parquet"] = f"{base}/{symbol}_metrics.parquet?download=true"
    URLS[f"{symbol}_fundingRate.parquet"] = f"{base}/{symbol}_fundingRate.parquet?download=true"

REQUESTED_START = pd.Timestamp("2020-01-01", tz="UTC")
LATEST_DATA_END = None
BASE_COST = 0.0012   # 12 bps round trip
STRESS_COST = 0.0024 # 24 bps round trip
MAX_TRIALS = 7000
BROAD_PER_FAMILY = 20
MUTATIONS_PER_PARENT = 8
TOP_PARENTS_PER_DATASET = 18
FINALISTS_PER_DATASET = 25
FINAL_HOLDOUT_DAYS = 365
MIN_PRE_TRADES = 100
MIN_FINAL_TRADES = 50


def log(msg: str) -> None:
    print(f"[{pd.Timestamp.now(tz='UTC').isoformat()}] {msg}", flush=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str, path: Path) -> None:
    if path.exists() and path.stat().st_size > 1000:
        return
    tmp = path.with_suffix(path.suffix + ".part")
    log(f"Downloading {path.name}")
    with requests.get(url, stream=True, timeout=(30, 180)) as response:
        response.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
    tmp.replace(path)


def to_utc(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, utc=True)
    numeric = pd.to_numeric(series, errors="coerce")
    finite = numeric.dropna()
    if not finite.empty:
        med = float(finite.abs().median())
        unit = "ns" if med > 1e17 else "us" if med > 1e14 else "ms" if med > 1e11 else "s"
        return pd.to_datetime(numeric, unit=unit, utc=True, errors="coerce")
    return pd.to_datetime(series, utc=True, errors="coerce")


def load_kline(symbol: str) -> pd.DataFrame:
    path = RAW_DIR / f"{symbol}_5m.parquet"
    df = pd.read_parquet(path)
    df["open_time"] = to_utc(df["open_time"])
    df = df.loc[df["open_time"] >= REQUESTED_START].copy()
    numeric_cols = ["open", "high", "low", "close", "volume", "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume"]
    for col in numeric_cols:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open_time", "open", "high", "low", "close"]).sort_values("open_time")
    df = df.drop_duplicates("open_time", keep="last").set_index("open_time")
    return df


def load_funding(symbol: str) -> pd.DataFrame:
    path = RAW_DIR / f"{symbol}_fundingRate.parquet"
    df = pd.read_parquet(path)
    time_col = "calc_time" if "calc_time" in df else "funding_time"
    rate_col = "last_funding_rate" if "last_funding_rate" in df else "funding_rate"
    df[time_col] = to_utc(df[time_col])
    df[rate_col] = pd.to_numeric(df[rate_col], errors="coerce")
    df = df.dropna(subset=[time_col, rate_col]).sort_values(time_col).drop_duplicates(time_col, keep="last")
    return df[[time_col, rate_col]].rename(columns={time_col: "time", rate_col: "funding_rate"})


def load_metrics(symbol: str) -> pd.DataFrame:
    path = RAW_DIR / f"{symbol}_metrics.parquet"
    df = pd.read_parquet(path)
    time_col = "create_time"
    df[time_col] = to_utc(df[time_col])
    for col in df.columns:
        if col not in (time_col, "symbol"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=[time_col]).sort_values(time_col).drop_duplicates(time_col, keep="last")


def audit_data(symbol: str, kline: pd.DataFrame, metrics: pd.DataFrame, funding: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    expected = int((kline.index.max() - kline.index.min()) / pd.Timedelta(minutes=5)) + 1
    invalid = int(((kline["high"] < kline[["open", "close", "low"]].max(axis=1)) | (kline["low"] > kline[["open", "close", "high"]].min(axis=1))).sum())
    for kind, filename, frame, time_source in [
        ("kline", f"{symbol}_5m.parquet", kline, kline.index),
        ("metrics", f"{symbol}_metrics.parquet", metrics, metrics["create_time"]),
        ("funding", f"{symbol}_fundingRate.parquet", funding, funding["time"]),
    ]:
        path = RAW_DIR / filename
        row = {
            "symbol": symbol,
            "kind": kind,
            "file": filename,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "rows": len(frame),
            "first_time": str(time_source.min()),
            "last_time": str(time_source.max()),
            "duplicate_timestamps": int(pd.Index(time_source).duplicated().sum()),
            "expected_5m_rows": expected if kind == "kline" else np.nan,
            "missing_5m_rows": expected - len(kline) if kind == "kline" else np.nan,
            "invalid_ohlc_rows": invalid if kind == "kline" else np.nan,
        }
        rows.append(row)
    return rows


def resample_ohlcv(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes == 5:
        return df.copy()
    rule = f"{minutes}min"
    agg = {
        "open": "first", "high": "max", "low": "min", "close": "last",
        "volume": "sum", "quote_volume": "sum", "count": "sum",
        "taker_buy_volume": "sum", "taker_buy_quote_volume": "sum",
    }
    out = df.resample(rule, label="left", closed="left", origin="epoch").agg(agg)
    out = out.dropna(subset=["open", "high", "low", "close"])
    return out


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    diff = close.diff()
    gain = diff.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-diff.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean(), plus_di, minus_di


def rolling_z(s: pd.Series, n: int) -> pd.Series:
    mean = s.rolling(n, min_periods=max(5, n // 2)).mean()
    std = s.rolling(n, min_periods=max(5, n // 2)).std(ddof=0)
    return (s - mean) / std.replace(0, np.nan)


def supertrend_direction(high: pd.Series, low: pd.Series, close: pd.Series, atr: pd.Series, mult: float) -> pd.Series:
    hl2 = (high + low) / 2
    upper = (hl2 + mult * atr).to_numpy(float)
    lower = (hl2 - mult * atr).to_numpy(float)
    c = close.to_numpy(float)
    direction = np.ones(len(c), dtype=np.int8)
    final_upper = upper.copy()
    final_lower = lower.copy()
    for i in range(1, len(c)):
        if np.isnan(upper[i]) or np.isnan(c[i - 1]):
            direction[i] = direction[i - 1]
            continue
        if upper[i] < final_upper[i - 1] or c[i - 1] > final_upper[i - 1]:
            final_upper[i] = upper[i]
        else:
            final_upper[i] = final_upper[i - 1]
        if lower[i] > final_lower[i - 1] or c[i - 1] < final_lower[i - 1]:
            final_lower[i] = lower[i]
        else:
            final_lower[i] = final_lower[i - 1]
        if direction[i - 1] < 0 and c[i] > final_upper[i - 1]:
            direction[i] = 1
        elif direction[i - 1] > 0 and c[i] < final_lower[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]
    return pd.Series(direction, index=close.index)


def build_features(df: pd.DataFrame, minutes: int, htf: pd.DataFrame | None, metrics: pd.DataFrame, funding: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    high, low, close, open_ = x["high"], x["low"], x["close"], x["open"]
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    x["atr"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    for n in (9, 20, 50, 100, 200):
        x[f"ema{n}"] = close.ewm(span=n, adjust=False, min_periods=n).mean()
    x["ema20_slope"] = (x["ema20"] - x["ema20"].shift(5)) / x["atr"].replace(0, np.nan)
    for n in (7, 14, 21):
        x[f"rsi{n}"] = rsi(close, n)
    x["adx"], x["plus_di"], x["minus_di"] = adx(high, low, close, 14)
    x["macd"] = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    x["macd_signal"] = x["macd"].ewm(span=9, adjust=False).mean()
    x["macd_hist"] = x["macd"] - x["macd_signal"]
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std(ddof=0)
    x["bb_z"] = (close - sma20) / std20.replace(0, np.nan)
    x["bb_width"] = 4 * std20 / sma20.replace(0, np.nan)
    x["bb_width_rel"] = x["bb_width"] / x["bb_width"].rolling(200, min_periods=100).median()
    x["squeeze"] = (2 * std20) < (1.5 * x["atr"])
    for n in (5, 10, 20, 40):
        x[f"don_hi{n}"] = high.shift(1).rolling(n).max()
        x[f"don_lo{n}"] = low.shift(1).rolling(n).min()
    logq = np.log1p(x["quote_volume"].clip(lower=0))
    x["vol_z"] = rolling_z(logq, 30)
    flow = 2 * x["taker_buy_quote_volume"] / x["quote_volume"].replace(0, np.nan) - 1
    x["flow"] = flow.clip(-1, 1)
    x["flow_z"] = rolling_z(x["flow"], 30)
    x["roc3"] = close.pct_change(3)
    x["roc6"] = close.pct_change(6)
    x["roc12"] = close.pct_change(12)
    absdiff = close.diff().abs()
    x["er10"] = (close - close.shift(10)).abs() / absdiff.rolling(10).sum().replace(0, np.nan)
    rng = (high - low).replace(0, np.nan)
    x["body_atr"] = (close - open_) / x["atr"].replace(0, np.nan)
    x["close_pos"] = (close - low) / rng
    x["lower_wick_atr"] = (np.minimum(open_, close) - low) / x["atr"].replace(0, np.nan)
    x["upper_wick_atr"] = (high - np.maximum(open_, close)) / x["atr"].replace(0, np.nan)
    roll_low = low.rolling(14).min()
    roll_high = high.rolling(14).max()
    x["stoch"] = 100 * (close - roll_low) / (roll_high - roll_low).replace(0, np.nan)
    x["stoch_signal"] = x["stoch"].rolling(3).mean()
    typical = (high + low + close) / 3
    day = x.index.floor("D")
    pv = (typical * x["volume"]).groupby(day).cumsum()
    vv = x["volume"].groupby(day).cumsum().replace(0, np.nan)
    x["vwap"] = pv / vv
    x["vwap_dist"] = (close - x["vwap"]) / x["atr"].replace(0, np.nan)
    for mult in (2.0, 3.0):
        x[f"supertrend_{int(mult)}"] = supertrend_direction(high, low, close, x["atr"], mult)

    # Causal higher-timeframe context: an HTF bar is available only at its close.
    if htf is not None:
        h = htf[["close", "ema20", "ema50", "ema200", "adx", "rsi14", "atr"]].copy()
        h.columns = [f"htf_{c}" for c in h.columns]
        h["available_time"] = h.index + pd.Timedelta(minutes=60)
        left = pd.DataFrame({"available_time": x.index + pd.Timedelta(minutes=minutes)}, index=x.index)
        merged = pd.merge_asof(left.sort_values("available_time"), h.reset_index(drop=True).sort_values("available_time"), on="available_time", direction="backward")
        merged.index = x.index
        for col in h.columns:
            if col != "available_time":
                x[col] = merged[col].to_numpy()
    else:
        x["htf_close"] = close
        x["htf_ema20"] = x["ema20"]
        x["htf_ema50"] = x["ema50"]
        x["htf_ema200"] = x["ema200"]
        x["htf_adx"] = x["adx"]
        x["htf_rsi14"] = x["rsi14"]
        x["htf_atr"] = x["atr"]

    # Metrics/OI as-of signal close.
    if not metrics.empty:
        m = metrics.copy()
        m["oi"] = m.get("sum_open_interest_value", m.get("sum_open_interest"))
        m["oi_change"] = np.log(m["oi"].replace(0, np.nan)).diff()
        m["oi_z"] = rolling_z(m["oi_change"], 288)
        ratio_col = "sum_taker_long_short_vol_ratio" if "sum_taker_long_short_vol_ratio" in m else None
        if ratio_col:
            m["taker_ls_z"] = rolling_z(np.log(m[ratio_col].replace(0, np.nan)), 288)
        else:
            m["taker_ls_z"] = np.nan
        m2 = m[["create_time", "oi_change", "oi_z", "taker_ls_z"]].sort_values("create_time")
        left = pd.DataFrame({"time": x.index + pd.Timedelta(minutes=minutes)}, index=x.index)
        mm = pd.merge_asof(left.sort_values("time"), m2.rename(columns={"create_time": "time"}), on="time", direction="backward", tolerance=pd.Timedelta("30min"))
        mm.index = x.index
        for col in ("oi_change", "oi_z", "taker_ls_z"):
            x[col] = mm[col].to_numpy()
    else:
        x["oi_change"] = np.nan
        x["oi_z"] = np.nan
        x["taker_ls_z"] = np.nan

    # Last settled funding rate is context only; actual funding cashflow handled separately.
    if not funding.empty:
        f = funding.copy()
        f["funding_z"] = rolling_z(f["funding_rate"], 90)
        left = pd.DataFrame({"time": x.index + pd.Timedelta(minutes=minutes)}, index=x.index)
        ff = pd.merge_asof(left.sort_values("time"), f[["time", "funding_rate", "funding_z"]].sort_values("time"), on="time", direction="backward")
        ff.index = x.index
        x["funding_rate_ctx"] = ff["funding_rate"].to_numpy()
        x["funding_z"] = ff["funding_z"].to_numpy()
    else:
        x["funding_rate_ctx"] = np.nan
        x["funding_z"] = np.nan

    x["bar_close_time"] = x.index + pd.Timedelta(minutes=minutes)
    return x


def build_funding_cumulative(index: pd.DatetimeIndex, minutes: int, funding: pd.DataFrame) -> np.ndarray:
    events = np.zeros(len(index), dtype=np.float64)
    if funding.empty:
        return events
    close_ns = (index + pd.Timedelta(minutes=minutes)).asi8
    f_ns = pd.DatetimeIndex(funding["time"]).asi8
    rates = funding["funding_rate"].to_numpy(float)
    loc = np.searchsorted(close_ns, f_ns, side="left")
    valid = (loc >= 0) & (loc < len(events))
    for i, rate in zip(loc[valid], rates[valid]):
        events[i] += rate
    return np.cumsum(events)


@njit(cache=True)
def simulate_trades(
    signal_idx: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr: np.ndarray,
    funding_cum: np.ndarray,
    side: int,
    stop_mult: float,
    target_mult: float,
    max_hold: int,
    cost: float,
    be_trigger: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    nmax = len(signal_idx)
    entries = np.empty(nmax, dtype=np.int64)
    exits = np.empty(nmax, dtype=np.int64)
    rets = np.empty(nmax, dtype=np.float64)
    gross_rets = np.empty(nmax, dtype=np.float64)
    reasons = np.empty(nmax, dtype=np.int8)  # 1 stop, 2 target, 3 time
    count = 0
    last_exit = -1
    n = len(close)
    for k in range(nmax):
        sig = signal_idx[k]
        entry_i = sig + 1
        if entry_i >= n or entry_i <= last_exit:
            continue
        a = atr[sig]
        ep = open_[entry_i]
        if not np.isfinite(a) or a <= 0 or not np.isfinite(ep) or ep <= 0:
            continue
        if side > 0:
            stop = ep - stop_mult * a
            target = ep + target_mult * a
        else:
            stop = ep + stop_mult * a
            target = ep - target_mult * a
        if stop <= 0 or target <= 0:
            continue
        end_i = min(n - 1, entry_i + max_hold - 1)
        exit_i = end_i
        xp = close[end_i]
        reason = 3
        dyn_stop = stop
        moved_be = False
        for j in range(entry_i, end_i + 1):
            if be_trigger > 0 and not moved_be:
                if side > 0 and high[j] >= ep + be_trigger * a:
                    dyn_stop = max(dyn_stop, ep)
                    moved_be = True
                elif side < 0 and low[j] <= ep - be_trigger * a:
                    dyn_stop = min(dyn_stop, ep)
                    moved_be = True
            if side > 0:
                # Conservative intrabar ordering: stop before target.
                if low[j] <= dyn_stop:
                    xp = min(open_[j], dyn_stop) if open_[j] < dyn_stop else dyn_stop
                    exit_i = j
                    reason = 1
                    break
                if high[j] >= target:
                    xp = max(open_[j], target) if open_[j] > target else target
                    exit_i = j
                    reason = 2
                    break
            else:
                if high[j] >= dyn_stop:
                    xp = max(open_[j], dyn_stop) if open_[j] > dyn_stop else dyn_stop
                    exit_i = j
                    reason = 1
                    break
                if low[j] <= target:
                    xp = min(open_[j], target) if open_[j] < target else target
                    exit_i = j
                    reason = 2
                    break
        gross = side * (xp / ep - 1.0)
        f0 = funding_cum[entry_i - 1] if entry_i > 0 else 0.0
        f1 = funding_cum[exit_i]
        funding_sum = f1 - f0
        net = gross - cost - side * funding_sum
        entries[count] = entry_i
        exits[count] = exit_i
        rets[count] = net
        gross_rets[count] = gross
        reasons[count] = reason
        count += 1
        last_exit = exit_i
    return entries[:count], exits[:count], rets[:count], gross_rets[:count], reasons[:count]


def max_drawdown(returns: np.ndarray) -> float:
    if len(returns) == 0:
        return np.nan
    equity = np.cumprod(1 + np.clip(returns, -0.999, None))
    peak = np.maximum.accumulate(equity)
    return float(np.min(equity / peak - 1))


def profit_factor(returns: np.ndarray) -> float:
    gains = returns[returns > 0].sum()
    losses = -returns[returns < 0].sum()
    if losses <= 0:
        return float("inf") if gains > 0 else np.nan
    return float(gains / losses)


def aggregate_period(exit_times: pd.DatetimeIndex, returns: np.ndarray, freq: str) -> pd.Series:
    if len(returns) == 0:
        return pd.Series(dtype=float)
    s = pd.Series(returns, index=exit_times)
    # Realized-period compounding; multiple exits in a period compound.
    return s.groupby(pd.Grouper(freq=freq)).apply(lambda z: float(np.prod(1 + z.to_numpy()) - 1)).dropna()


def metrics_from_trades(exit_times: pd.DatetimeIndex, returns: np.ndarray, calendar_start: pd.Timestamp, calendar_end: pd.Timestamp) -> dict[str, float]:
    n = len(returns)
    if n == 0:
        return {k: np.nan for k in ["trades", "win_rate", "pf", "mean", "median", "total_return", "max_dd", "daily_sharpe", "positive_active_day_rate", "positive_calendar_day_rate", "active_days", "positive_week_rate", "active_weeks", "positive_month_rate", "active_months", "payoff"]}
    daily = aggregate_period(exit_times, returns, "1D")
    weekly = aggregate_period(exit_times, returns, "W-SUN")
    monthly = aggregate_period(exit_times, returns, "ME")
    cal_days = max(1, (calendar_end.floor("D") - calendar_start.floor("D")).days + 1)
    daily_std = daily.std(ddof=1)
    sharpe = float(daily.mean() / daily_std * math.sqrt(365)) if len(daily) > 1 and daily_std > 0 else np.nan
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    payoff = float(wins.mean() / -losses.mean()) if len(wins) and len(losses) else np.nan
    return {
        "trades": float(n),
        "win_rate": float(np.mean(returns > 0)),
        "pf": profit_factor(returns),
        "mean": float(np.mean(returns)),
        "median": float(np.median(returns)),
        "total_return": float(np.prod(1 + np.clip(returns, -0.999, None)) - 1),
        "max_dd": max_drawdown(returns),
        "daily_sharpe": sharpe,
        "positive_active_day_rate": float(np.mean(daily > 0)) if len(daily) else np.nan,
        "positive_calendar_day_rate": float((daily > 0).sum() / cal_days),
        "active_days": float(len(daily)),
        "positive_week_rate": float(np.mean(weekly > 0)) if len(weekly) else np.nan,
        "active_weeks": float(len(weekly)),
        "positive_month_rate": float(np.mean(monthly > 0)) if len(monthly) else np.nan,
        "active_months": float(len(monthly)),
        "payoff": payoff,
    }


def slice_metrics(exit_times: pd.DatetimeIndex, returns: np.ndarray, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, float]:
    mask = (exit_times >= start) & (exit_times < end)
    return metrics_from_trades(exit_times[mask], returns[mask], start, end)


def fold_metrics(exit_times: pd.DatetimeIndex, returns: np.ndarray, fold_bounds: list[tuple[pd.Timestamp, pd.Timestamp]]) -> list[dict[str, float]]:
    return [slice_metrics(exit_times, returns, start, end) for start, end in fold_bounds]


def score_pre(folds: list[dict[str, float]], whole: dict[str, float]) -> float:
    valid = [f for f in folds if f.get("trades", 0) >= 12 and np.isfinite(f.get("pf", np.nan))]
    if whole.get("trades", 0) < MIN_PRE_TRADES or len(valid) < 3:
        return -1e9
    positive_folds = sum(f["mean"] > 0 for f in valid)
    med_wr = float(np.nanmedian([f["win_rate"] for f in valid]))
    med_day = float(np.nanmedian([f["positive_active_day_rate"] for f in valid]))
    med_pf = float(np.nanmedian([min(f["pf"], 3.0) for f in valid]))
    med_mean = float(np.nanmedian([f["mean"] for f in valid]))
    dd = abs(min(0.0, whole.get("max_dd", -1.0)))
    score = 0.42 * med_wr + 0.30 * med_day + 0.12 * min(med_pf / 2.0, 1.0) + 0.10 * min(max(med_mean * 1000, -1), 1) + 0.06 * (positive_folds / len(valid))
    if whole["mean"] <= 0 or whole["pf"] < 1.03:
        score -= 0.35
    if positive_folds < math.ceil(len(valid) * 0.6):
        score -= 0.20
    if dd > 0.30:
        score -= min(0.3, dd - 0.30)
    return float(score)


def bool_col(x: pd.DataFrame, name: str, default: bool = True) -> np.ndarray:
    if name not in x:
        return np.full(len(x), default, dtype=bool)
    return x[name].fillna(False).to_numpy(bool)


def make_signal(x: pd.DataFrame, cfg: dict[str, Any]) -> np.ndarray:
    side = int(cfg["side"])
    fam = cfg["family"]
    c = x["close"].to_numpy(float)
    o = x["open"].to_numpy(float)
    h = x["high"].to_numpy(float)
    l = x["low"].to_numpy(float)
    atr = x["atr"].to_numpy(float)
    ema20 = x["ema20"].to_numpy(float)
    ema50 = x["ema50"].to_numpy(float)
    ema200 = x["ema200"].to_numpy(float)
    rsi14 = x["rsi14"].to_numpy(float)
    adxv = x["adx"].to_numpy(float)
    volz = x["vol_z"].to_numpy(float)
    flowz = x["flow_z"].to_numpy(float)
    close_pos = x["close_pos"].to_numpy(float)
    htf_close = x["htf_close"].to_numpy(float)
    htf_e20 = x["htf_ema20"].to_numpy(float)
    htf_e50 = x["htf_ema50"].to_numpy(float)
    htf_e200 = x["htf_ema200"].to_numpy(float)
    htf_adx = x["htf_adx"].to_numpy(float)
    oi_z = x["oi_z"].to_numpy(float)
    funding_z = x["funding_z"].to_numpy(float)
    base = np.isfinite(atr) & (atr > 0) & np.isfinite(ema50) & np.isfinite(rsi14)

    if side > 0:
        htf_trend = (htf_e20 > htf_e50) & (htf_close > htf_e50)
        local_trend = (ema20 > ema50) & (c > ema50)
        cp_ok = close_pos >= cfg.get("close_pos", 0.55)
    else:
        htf_trend = (htf_e20 < htf_e50) & (htf_close < htf_e50)
        local_trend = (ema20 < ema50) & (c < ema50)
        cp_ok = close_pos <= 1 - cfg.get("close_pos", 0.55)

    if not cfg.get("require_htf", True):
        htf_trend = np.ones(len(x), dtype=bool)
    if cfg.get("htf_200", False):
        htf_trend &= (htf_close > htf_e200) if side > 0 else (htf_close < htf_e200)

    if fam == "TREND_PULLBACK":
        prev_c = np.roll(c, 1); prev_e20 = np.roll(ema20, 1)
        touched = (l <= ema20 + cfg["touch_atr"] * atr) if side > 0 else (h >= ema20 - cfg["touch_atr"] * atr)
        crossed = (c > ema20) & (prev_c <= prev_e20) if side > 0 else (c < ema20) & (prev_c >= prev_e20)
        rsi_ok = (rsi14 >= cfg["rsi_lo"]) & (rsi14 <= cfg["rsi_hi"])
        sig = local_trend & htf_trend & touched & crossed & rsi_ok & (adxv >= cfg["adx_min"]) & cp_ok
    elif fam == "MOMENTUM_CONTINUATION":
        macdh = x["macd_hist"].to_numpy(float)
        roc = x[cfg["roc_col"]].to_numpy(float)
        brk = x[f"don_hi{cfg['lookback']}"] .to_numpy(float) if side > 0 else x[f"don_lo{cfg['lookback']}"] .to_numpy(float)
        price_break = c >= brk + cfg["buffer_atr"] * atr if side > 0 else c <= brk - cfg["buffer_atr"] * atr
        mom = (macdh > 0) & (roc > cfg["roc_min"]) & (rsi14 >= cfg["rsi_min"]) if side > 0 else (macdh < 0) & (roc < -cfg["roc_min"]) & (rsi14 <= 100 - cfg["rsi_min"])
        sig = local_trend & htf_trend & mom & price_break & (adxv >= cfg["adx_min"]) & cp_ok
    elif fam == "DONCHIAN_BREAKOUT":
        level = x[f"don_hi{cfg['lookback']}"] .to_numpy(float) if side > 0 else x[f"don_lo{cfg['lookback']}"] .to_numpy(float)
        breakout = c >= level + cfg["buffer_atr"] * atr if side > 0 else c <= level - cfg["buffer_atr"] * atr
        sig = htf_trend & breakout & (adxv >= cfg["adx_min"]) & cp_ok
        if cfg.get("trend_local", True):
            sig &= local_trend
    elif fam == "SQUEEZE_BREAKOUT":
        sq = x["squeeze"].fillna(False).to_numpy(bool)
        prev_sq = np.roll(sq, 1)
        width_rel = x["bb_width_rel"].to_numpy(float)
        level = x[f"don_hi{cfg['lookback']}"] .to_numpy(float) if side > 0 else x[f"don_lo{cfg['lookback']}"] .to_numpy(float)
        release = prev_sq & (~sq) & (width_rel >= cfg["width_rel_min"])
        breakout = c >= level + cfg["buffer_atr"] * atr if side > 0 else c <= level - cfg["buffer_atr"] * atr
        sig = htf_trend & release & breakout & cp_ok
    elif fam == "SWEEP_RECLAIM":
        level = x[f"don_lo{cfg['lookback']}"] .to_numpy(float) if side > 0 else x[f"don_hi{cfg['lookback']}"] .to_numpy(float)
        swept = l < level - cfg["depth_atr"] * atr if side > 0 else h > level + cfg["depth_atr"] * atr
        reclaimed = c > level if side > 0 else c < level
        wick = x["lower_wick_atr"].to_numpy(float) if side > 0 else x["upper_wick_atr"].to_numpy(float)
        sig = swept & reclaimed & (wick >= cfg["wick_min"]) & cp_ok
        if cfg.get("trend_context", True):
            sig &= htf_trend
        else:
            sig &= htf_adx <= cfg.get("htf_adx_max", 28)
    elif fam == "RANGE_REVERSION":
        bbz = x["bb_z"].to_numpy(float)
        vd = x["vwap_dist"].to_numpy(float)
        st = x["stoch"].to_numpy(float)
        if side > 0:
            extreme = (bbz <= -cfg["bb_z_abs"]) & (vd <= -cfg["vwap_abs"]) & (rsi14 <= cfg["rsi_extreme"]) & (st <= cfg["stoch_extreme"])
        else:
            extreme = (bbz >= cfg["bb_z_abs"]) & (vd >= cfg["vwap_abs"]) & (rsi14 >= 100 - cfg["rsi_extreme"]) & (st >= 100 - cfg["stoch_extreme"])
        sig = extreme & (adxv <= cfg["adx_max"]) & (htf_adx <= cfg["htf_adx_max"]) & cp_ok
    elif fam == "VWAP_RECLAIM":
        vd = x["vwap_dist"].to_numpy(float)
        prev_c = np.roll(c, 1); prev_vwap = np.roll(x["vwap"].to_numpy(float), 1)
        if side > 0:
            excursion = np.minimum(vd, np.roll(vd, 1)) <= -cfg["vwap_abs"]
            reclaim = (c > x["vwap"].to_numpy(float)) & (prev_c <= prev_vwap)
            rsi_ok = rsi14 <= cfg["rsi_max"]
        else:
            excursion = np.maximum(vd, np.roll(vd, 1)) >= cfg["vwap_abs"]
            reclaim = (c < x["vwap"].to_numpy(float)) & (prev_c >= prev_vwap)
            rsi_ok = rsi14 >= 100 - cfg["rsi_max"]
        sig = excursion & reclaim & rsi_ok & cp_ok
        if cfg.get("range_only", False):
            sig &= (adxv <= cfg["adx_max"]) & (htf_adx <= cfg["htf_adx_max"])
        else:
            sig &= htf_trend
    elif fam == "STOCH_REVERSAL":
        st = x["stoch"].to_numpy(float); sts = x["stoch_signal"].to_numpy(float)
        prev_st = np.roll(st, 1); prev_sts = np.roll(sts, 1)
        bbz = x["bb_z"].to_numpy(float)
        if side > 0:
            cross = (st > sts) & (prev_st <= prev_sts) & (prev_st <= cfg["stoch_extreme"])
            extreme = bbz <= -cfg["bb_z_abs"]
        else:
            cross = (st < sts) & (prev_st >= prev_sts) & (prev_st >= 100 - cfg["stoch_extreme"])
            extreme = bbz >= cfg["bb_z_abs"]
        sig = cross & extreme & (adxv <= cfg["adx_max"]) & cp_ok
    elif fam == "CROWDING_REVERSAL":
        level = x[f"don_lo{cfg['lookback']}"] .to_numpy(float) if side > 0 else x[f"don_hi{cfg['lookback']}"] .to_numpy(float)
        swept = l < level if side > 0 else h > level
        reclaimed = c > level if side > 0 else c < level
        crowd = (funding_z <= -cfg["funding_abs"]) if side > 0 else (funding_z >= cfg["funding_abs"])
        oi = oi_z >= cfg["oi_min"]
        sig = swept & reclaimed & crowd & oi & cp_ok & (htf_adx <= cfg["htf_adx_max"])
    else:
        raise ValueError(f"unknown family {fam}")

    sig &= base
    sig &= volz >= cfg.get("vol_z_min", -10.0)
    if side > 0:
        sig &= flowz >= cfg.get("flow_z_min", -10.0)
    else:
        sig &= flowz <= -cfg.get("flow_z_min", -10.0)
    if cfg.get("crowding_veto", False):
        if side > 0:
            sig &= ~((funding_z > cfg.get("veto_funding", 1.5)) & (oi_z > cfg.get("veto_oi", 0.5)))
        else:
            sig &= ~((funding_z < -cfg.get("veto_funding", 1.5)) & (oi_z > cfg.get("veto_oi", 0.5)))
    sig[:250] = False
    sig[-2:] = False
    sig[0] = False
    return np.nan_to_num(sig, nan=False).astype(bool)


def choice(seq: Iterable[Any]) -> Any:
    seq = list(seq)
    return seq[int(RNG.integers(0, len(seq)))]


def sample_config(family: str, symbol: str, timeframe: str, side: int) -> dict[str, Any]:
    minutes = TIMEFRAMES[timeframe]
    cfg: dict[str, Any] = {
        "family": family, "symbol": symbol, "timeframe": timeframe, "side": side,
        "require_htf": bool(RNG.random() < 0.80), "htf_200": bool(RNG.random() < 0.30),
        "close_pos": choice([0.52, 0.58, 0.64, 0.70, 0.78]),
        "vol_z_min": choice([-0.5, 0.0, 0.35, 0.7, 1.0]),
        "flow_z_min": choice([-0.5, -0.1, 0.2, 0.5, 0.8]),
        "crowding_veto": bool(RNG.random() < 0.25),
        "veto_funding": choice([1.25, 1.5, 1.75, 2.0]), "veto_oi": choice([0.25, 0.5, 0.75, 1.0]),
        "stop_atr": choice([0.6, 0.8, 1.0, 1.2, 1.5, 1.8, 2.2]),
        "target_atr": choice([0.4, 0.5, 0.65, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]),
        "max_hold": choice({5: [6, 12, 24, 48, 72], 15: [4, 8, 16, 24, 32], 30: [3, 6, 12, 18, 24], 60: [2, 4, 6, 8, 12, 24]}[minutes]),
        "be_trigger": choice([0.0, 0.0, 0.5, 0.75, 1.0]),
    }
    if family == "TREND_PULLBACK":
        lo = choice([32, 36, 40, 44, 48]); hi = choice([52, 56, 60, 64])
        cfg.update(touch_atr=choice([0.0, 0.1, 0.2, 0.35]), rsi_lo=min(lo, hi - 4), rsi_hi=hi, adx_min=choice([14, 18, 22, 26]))
    elif family == "MOMENTUM_CONTINUATION":
        cfg.update(roc_col=choice(["roc3", "roc6", "roc12"]), roc_min=choice([0.0, 0.001, 0.002, 0.004]), rsi_min=choice([52, 56, 60, 64]), lookback=choice([5, 10, 20]), buffer_atr=choice([0.0, 0.05, 0.1, 0.2]), adx_min=choice([16, 20, 24, 28]))
    elif family == "DONCHIAN_BREAKOUT":
        cfg.update(lookback=choice([5, 10, 20, 40]), buffer_atr=choice([0.0, 0.05, 0.1, 0.2]), adx_min=choice([12, 16, 20, 24, 28]), trend_local=bool(RNG.random() < 0.7))
    elif family == "SQUEEZE_BREAKOUT":
        cfg.update(lookback=choice([5, 10, 20]), buffer_atr=choice([0.0, 0.05, 0.1, 0.2]), width_rel_min=choice([0.75, 0.9, 1.0, 1.1, 1.25]))
    elif family == "SWEEP_RECLAIM":
        cfg.update(lookback=choice([5, 10, 20, 40]), depth_atr=choice([0.0, 0.05, 0.1, 0.2]), wick_min=choice([0.05, 0.15, 0.3, 0.5]), trend_context=bool(RNG.random() < 0.65), htf_adx_max=choice([18, 22, 26, 30]))
    elif family == "RANGE_REVERSION":
        cfg.update(bb_z_abs=choice([1.2, 1.5, 1.8, 2.1, 2.5]), vwap_abs=choice([0.5, 0.8, 1.2, 1.6, 2.0]), rsi_extreme=choice([20, 25, 30, 35, 40]), stoch_extreme=choice([10, 15, 20, 25, 30]), adx_max=choice([14, 18, 22, 26]), htf_adx_max=choice([18, 22, 26, 30]))
    elif family == "VWAP_RECLAIM":
        cfg.update(vwap_abs=choice([0.4, 0.7, 1.0, 1.4, 1.8]), rsi_max=choice([35, 40, 45, 50, 55]), range_only=bool(RNG.random() < 0.5), adx_max=choice([16, 20, 24]), htf_adx_max=choice([20, 24, 28]))
    elif family == "STOCH_REVERSAL":
        cfg.update(stoch_extreme=choice([10, 15, 20, 25, 30]), bb_z_abs=choice([1.0, 1.3, 1.6, 2.0, 2.4]), adx_max=choice([14, 18, 22, 26]))
    elif family == "CROWDING_REVERSAL":
        cfg.update(lookback=choice([5, 10, 20]), funding_abs=choice([1.0, 1.25, 1.5, 1.75, 2.0]), oi_min=choice([0.0, 0.25, 0.5, 0.75, 1.0]), htf_adx_max=choice([18, 22, 26, 30]))
        cfg["crowding_veto"] = False
    return cfg


def mutate_config(parent: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(parent)
    # Replace a small number of fields with nearby/random supported values.
    fresh = sample_config(cfg["family"], cfg["symbol"], cfg["timeframe"], int(cfg["side"]))
    mutable = [k for k in fresh if k not in ("family", "symbol", "timeframe", "side")]
    n_change = int(RNG.integers(2, min(7, len(mutable)) + 1))
    for key in RNG.choice(np.array(mutable, dtype=object), size=n_change, replace=False):
        cfg[str(key)] = fresh[str(key)]
    return cfg


def cfg_id(cfg: dict[str, Any]) -> str:
    payload = json.dumps(cfg, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(payload.encode()).hexdigest()[:14]


def evaluate_config(
    x: pd.DataFrame,
    funding_cum: np.ndarray,
    cfg: dict[str, Any],
    pre_start: pd.Timestamp,
    holdout_start: pd.Timestamp,
    final_end: pd.Timestamp,
    folds: list[tuple[pd.Timestamp, pd.Timestamp]],
    evaluate_holdout: bool = False,
) -> tuple[dict[str, Any], pd.DataFrame | None]:
    signal = make_signal(x, cfg)
    idx = np.flatnonzero(signal).astype(np.int64)
    row: dict[str, Any] = {**cfg, "config_id": cfg_id(cfg), "raw_signals": int(len(idx))}
    if len(idx) < 10 or len(idx) > len(x) * 0.25:
        row.update(pre_score=-1e9, pre_trades=0)
        return row, None
    entries, exits, net, gross, reasons = simulate_trades(
        idx,
        x["open"].to_numpy(float), x["high"].to_numpy(float), x["low"].to_numpy(float), x["close"].to_numpy(float),
        x["atr"].to_numpy(float), funding_cum, int(cfg["side"]), float(cfg["stop_atr"]), float(cfg["target_atr"]),
        int(cfg["max_hold"]), BASE_COST, float(cfg["be_trigger"]),
    )
    exit_times = pd.DatetimeIndex(x.index[exits]) + pd.Timedelta(minutes=TIMEFRAMES[cfg["timeframe"]])
    pre_mask = (exit_times >= pre_start) & (exit_times < holdout_start)
    pre_metrics = metrics_from_trades(exit_times[pre_mask], net[pre_mask], pre_start, holdout_start)
    fmetrics = fold_metrics(exit_times, net, folds)
    ps = score_pre(fmetrics, pre_metrics)
    row["pre_score"] = ps
    for k, v in pre_metrics.items():
        row[f"pre_{k}"] = v
    row["positive_pre_folds"] = int(sum(f.get("mean", np.nan) > 0 for f in fmetrics if f.get("trades", 0) >= 12))
    row["valid_pre_folds"] = int(sum(f.get("trades", 0) >= 12 for f in fmetrics))
    if not evaluate_holdout:
        return row, None

    final_mask = (exit_times >= holdout_start) & (exit_times < final_end)
    final_metrics = metrics_from_trades(exit_times[final_mask], net[final_mask], holdout_start, final_end)
    stress_returns = net[final_mask] - (STRESS_COST - BASE_COST)
    stress_metrics = metrics_from_trades(exit_times[final_mask], stress_returns, holdout_start, final_end)
    for k, v in final_metrics.items():
        row[f"oos_{k}"] = v
    for k, v in stress_metrics.items():
        row[f"stress_{k}"] = v
    gates = {
        "trades": final_metrics["trades"] >= MIN_FINAL_TRADES,
        "pf": final_metrics["pf"] >= 1.20,
        "mean": final_metrics["mean"] > 0,
        "stress": stress_metrics["pf"] >= 1.02 and stress_metrics["mean"] > 0,
        "drawdown": final_metrics["max_dd"] >= -0.15,
        "days": final_metrics["positive_active_day_rate"] >= 0.55,
        "weeks": final_metrics["positive_week_rate"] >= 0.52,
        "months": final_metrics["positive_month_rate"] >= 0.55,
        "folds": row["positive_pre_folds"] >= max(3, math.ceil(row["valid_pre_folds"] * 0.6)),
    }
    row.update({f"gate_{k}": bool(v) for k, v in gates.items()})
    row["gates_passed"] = int(sum(gates.values()))
    row["validated_pass"] = bool(all(gates.values()))
    # Primary objective: daily positive rate, then trade win rate and profitability.
    row["final_score"] = (
        0.40 * np.nan_to_num(final_metrics["positive_active_day_rate"], nan=0.0)
        + 0.30 * np.nan_to_num(final_metrics["win_rate"], nan=0.0)
        + 0.12 * min(np.nan_to_num(final_metrics["pf"], nan=0.0) / 2.0, 1.0)
        + 0.08 * min(max(np.nan_to_num(final_metrics["mean"], nan=-1.0) * 1000, -1), 1)
        + 0.05 * min(max(np.nan_to_num(stress_metrics["mean"], nan=-1.0) * 1000, -1), 1)
        + 0.05 * (row["gates_passed"] / len(gates))
    )
    trades = pd.DataFrame({
        "symbol": cfg["symbol"], "timeframe": cfg["timeframe"], "family": cfg["family"], "side": int(cfg["side"]),
        "config_id": row["config_id"], "entry_time": pd.DatetimeIndex(x.index[entries]) + pd.Timedelta(minutes=TIMEFRAMES[cfg["timeframe"]]),
        "exit_time": exit_times, "net_return": net, "gross_return": gross, "reason": reasons,
    })
    return row, trades


def bootstrap_ci(values: np.ndarray, block: int = 5, reps: int = 1500) -> tuple[float, float]:
    values = np.asarray(values, float)
    values = values[np.isfinite(values)]
    if len(values) < 10:
        return np.nan, np.nan
    n = len(values)
    starts = np.arange(n)
    means = np.empty(reps)
    for r in range(reps):
        sample: list[float] = []
        while len(sample) < n:
            s = int(RNG.choice(starts))
            for j in range(block):
                sample.append(values[(s + j) % n])
                if len(sample) >= n:
                    break
        means[r] = np.mean(sample)
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def monte_carlo_drawdown(values: np.ndarray, reps: int = 2000) -> dict[str, float]:
    values = np.asarray(values, float)
    if len(values) < 10:
        return {"mc_dd_median": np.nan, "mc_dd_p95_worst": np.nan}
    dds = np.empty(reps)
    for i in range(reps):
        dds[i] = max_drawdown(RNG.permutation(values))
    return {"mc_dd_median": float(np.median(dds)), "mc_dd_p95_worst": float(np.quantile(dds, 0.05))}


def deflated_sharpe_probability(daily: np.ndarray, n_trials: int) -> float:
    daily = np.asarray(daily, float)
    daily = daily[np.isfinite(daily)]
    if len(daily) < 20 or daily.std(ddof=1) <= 0:
        return np.nan
    sr = daily.mean() / daily.std(ddof=1) * math.sqrt(365)
    # Expected maximum SR under multiple testing (Bailey/Lopez de Prado approximation).
    gamma = 0.5772156649
    z1 = norm.ppf(1 - 1 / max(n_trials, 2))
    z2 = norm.ppf(1 - 1 / (max(n_trials, 2) * math.e))
    sr0 = math.sqrt(max(1e-12, 1 / max(len(daily) - 1, 1))) * ((1 - gamma) * z1 + gamma * z2) * math.sqrt(365)
    skew = pd.Series(daily).skew()
    kurt = pd.Series(daily).kurt() + 3
    denom = math.sqrt(max(1e-12, (1 - skew * sr / math.sqrt(365) + ((kurt - 1) / 4) * (sr / math.sqrt(365)) ** 2) / max(len(daily) - 1, 1))) * math.sqrt(365)
    return float(norm.cdf((sr - sr0) / denom))


def choose_finalists(rows: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return []
    frame = frame.replace([np.inf, -np.inf], np.nan)
    viable = frame[(frame["pre_trades"] >= MIN_PRE_TRADES) & (frame["pre_mean"] > 0) & (frame["pre_pf"] >= 1.03)].copy()
    if viable.empty:
        viable = frame.sort_values("pre_score", ascending=False).head(n)
    else:
        # Diversify by family and side before filling globally.
        picks = []
        for _, group in viable.groupby(["family", "side"]):
            picks.extend(group.sort_values("pre_score", ascending=False).head(2).to_dict("records"))
        seen = {r["config_id"] for r in picks}
        for r in viable.sort_values("pre_score", ascending=False).to_dict("records"):
            if r["config_id"] not in seen:
                picks.append(r); seen.add(r["config_id"])
            if len(picks) >= n:
                break
        return picks[:n]
    return viable.to_dict("records")[:n]


def config_from_row(row: dict[str, Any]) -> dict[str, Any]:
    ignore_prefixes = ("pre_", "oos_", "stress_", "gate_")
    ignore = {"config_id", "raw_signals", "positive_pre_folds", "valid_pre_folds", "gates_passed", "validated_pass", "final_score", "round"}
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k in ignore or any(k.startswith(p) for p in ignore_prefixes):
            continue
        try:
            if pd.isna(v):
                continue
        except (TypeError, ValueError):
            pass
        out[k] = v
    return out


def ensemble_search(final_rows: pd.DataFrame, trade_map: dict[str, pd.DataFrame], holdout_start: pd.Timestamp, final_end: pd.Timestamp) -> pd.DataFrame:
    if final_rows.empty:
        return pd.DataFrame()
    top = final_rows.sort_values(["validated_pass", "final_score"], ascending=False).head(14)
    ids = list(top["config_id"])
    daily_map: dict[str, pd.Series] = {}
    for cid in ids:
        t = trade_map.get(cid)
        if t is None or t.empty:
            continue
        tt = t[(t["exit_time"] >= holdout_start) & (t["exit_time"] < final_end)]
        daily_map[cid] = aggregate_period(pd.DatetimeIndex(tt["exit_time"]), tt["net_return"].to_numpy(float), "1D")
    rows = []
    for size in (2, 3):
        for combo in itertools.combinations(daily_map.keys(), size):
            meta = top.set_index("config_id").loc[list(combo)]
            # Avoid duplicate family+symbol copies and highly concentrated same-symbol portfolios.
            if meta.groupby(["symbol", "family"]).size().max() > 1:
                continue
            aligned = pd.concat([daily_map[c] for c in combo], axis=1).fillna(0.0)
            port = aligned.mean(axis=1)
            active = (aligned != 0).any(axis=1)
            port_active = port[active]
            if len(port_active) < 50:
                continue
            cal_days = max(1, (final_end.floor("D") - holdout_start.floor("D")).days + 1)
            equity = np.cumprod(1 + port.to_numpy())
            dd = float(np.min(equity / np.maximum.accumulate(equity) - 1))
            rows.append({
                "ensemble_id": "+".join(combo), "size": size,
                "positive_active_day_rate": float(np.mean(port_active > 0)),
                "positive_calendar_day_rate": float(np.sum(port > 0) / cal_days),
                "active_days": int(active.sum()),
                "total_return": float(equity[-1] - 1),
                "max_dd": dd,
                "daily_sharpe": float(port.mean() / port.std(ddof=1) * math.sqrt(365)) if port.std(ddof=1) > 0 else np.nan,
                "members": json.dumps(list(combo)),
            })
    return pd.DataFrame(rows).sort_values(["positive_active_day_rate", "total_return"], ascending=False) if rows else pd.DataFrame()


def main() -> None:
    t0 = time.time()
    for name, url in URLS.items():
        download(url, RAW_DIR / name)

    data: dict[str, dict[str, Any]] = {}
    audits: list[dict[str, Any]] = []
    common_end: pd.Timestamp | None = None
    funding_end: pd.Timestamp | None = None
    for symbol in SYMBOLS:
        k = load_kline(symbol)
        f = load_funding(symbol)
        m = load_metrics(symbol)
        audits.extend(audit_data(symbol, k, m, f))
        common_end = k.index.max() + pd.Timedelta(minutes=5) if common_end is None else min(common_end, k.index.max() + pd.Timedelta(minutes=5))
        funding_end = f["time"].max() if funding_end is None else min(funding_end, f["time"].max())
        data[symbol] = {"kline": k, "funding": f, "metrics": m}
    assert common_end is not None
    holdout_start = common_end - pd.Timedelta(days=FINAL_HOLDOUT_DAYS)
    # Robust final endpoint uses complete funding coverage; price-only statistics still saved to common_end later if needed.
    robust_end = min(common_end, funding_end + pd.Timedelta(hours=8) if funding_end is not None else common_end)
    if robust_end - holdout_start < pd.Timedelta(days=300):
        robust_end = common_end
    pre_start = pd.Timestamp("2021-01-01", tz="UTC")
    folds = [
        (pd.Timestamp("2021-01-01", tz="UTC"), pd.Timestamp("2022-01-01", tz="UTC")),
        (pd.Timestamp("2022-01-01", tz="UTC"), pd.Timestamp("2023-01-01", tz="UTC")),
        (pd.Timestamp("2023-01-01", tz="UTC"), pd.Timestamp("2024-01-01", tz="UTC")),
        (pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2025-01-01", tz="UTC")),
        (pd.Timestamp("2025-01-01", tz="UTC"), holdout_start),
    ]
    pd.DataFrame(audits).to_csv(RESULT_DIR / "data_audit_v8.csv", index=False)

    all_pre_rows: list[dict[str, Any]] = []
    all_final_rows: list[dict[str, Any]] = []
    trade_map: dict[str, pd.DataFrame] = {}
    improvement_log: list[dict[str, Any]] = []
    trials = 0

    for symbol in SYMBOLS:
        base5 = data[symbol]["kline"]
        funding = data[symbol]["funding"]
        metrics = data[symbol]["metrics"]
        raw60 = resample_ohlcv(base5, 60)
        htf60 = build_features(raw60, 60, None, metrics, funding)
        for timeframe, minutes in TIMEFRAMES.items():
            log(f"Preparing {symbol} {timeframe}")
            raw = resample_ohlcv(base5, minutes)
            x = htf60 if minutes == 60 else build_features(raw, minutes, htf60, metrics, funding)
            fund_cum = build_funding_cumulative(x.index, minutes, funding)
            dataset_rows: list[dict[str, Any]] = []
            seen: set[str] = set()
            best_score = -1e9
            no_improve_rounds = 0

            # Round 1: broad, pre-registered random coverage.
            broad_cfgs = []
            for fam in FAMILIES:
                for side in (1, -1):
                    for _ in range(BROAD_PER_FAMILY):
                        broad_cfgs.append(sample_config(fam, symbol, timeframe, side))
            for cfg in broad_cfgs:
                cid = cfg_id(cfg)
                if cid in seen or trials >= MAX_TRIALS:
                    continue
                seen.add(cid); trials += 1
                row, _ = evaluate_config(x, fund_cum, cfg, pre_start, holdout_start, robust_end, folds, False)
                row["round"] = 1
                dataset_rows.append(row); all_pre_rows.append(row)
            current_best = max((r["pre_score"] for r in dataset_rows), default=-1e9)
            improvement_log.append({"symbol": symbol, "timeframe": timeframe, "round": 1, "best_pre_score": current_best, "trials_cumulative": trials})
            best_score = current_best

            # Rounds 2-4: mutate the best pre-holdout configurations. Stop after two non-improving rounds.
            for round_no in (2, 3, 4):
                parents = sorted(dataset_rows, key=lambda r: r.get("pre_score", -1e9), reverse=True)[:TOP_PARENTS_PER_DATASET]
                new_rows = []
                for p in parents:
                    pcfg = config_from_row(p)
                    for _ in range(MUTATIONS_PER_PARENT):
                        cfg = mutate_config(pcfg)
                        cid = cfg_id(cfg)
                        if cid in seen or trials >= MAX_TRIALS:
                            continue
                        seen.add(cid); trials += 1
                        row, _ = evaluate_config(x, fund_cum, cfg, pre_start, holdout_start, robust_end, folds, False)
                        row["round"] = round_no
                        dataset_rows.append(row); all_pre_rows.append(row); new_rows.append(row)
                new_best = max((r["pre_score"] for r in dataset_rows), default=-1e9)
                improvement = new_best - best_score
                improvement_log.append({"symbol": symbol, "timeframe": timeframe, "round": round_no, "best_pre_score": new_best, "improvement": improvement, "new_trials": len(new_rows), "trials_cumulative": trials})
                if improvement < 0.0025:
                    no_improve_rounds += 1
                else:
                    no_improve_rounds = 0
                    best_score = new_best
                if no_improve_rounds >= 2 or trials >= MAX_TRIALS:
                    break

            # Lock shortlist before revealing the final holdout.
            finalists = choose_finalists(dataset_rows, FINALISTS_PER_DATASET)
            for item in finalists:
                cfg = config_from_row(item)
                row, trades_df = evaluate_config(x, fund_cum, cfg, pre_start, holdout_start, robust_end, folds, True)
                row["round"] = item.get("round", np.nan)
                all_final_rows.append(row)
                if trades_df is not None:
                    trade_map[row["config_id"]] = trades_df
            log(f"Finished {symbol} {timeframe}: {len(dataset_rows)} pre trials, {len(finalists)} finalists")
            del x, raw, fund_cum

    pre_df = pd.DataFrame(all_pre_rows)
    final_df = pd.DataFrame(all_final_rows)
    pre_df.to_csv(RESULT_DIR / "all_trials_pre_holdout.csv", index=False)
    final_df = final_df.sort_values(["validated_pass", "final_score", "oos_positive_active_day_rate", "oos_win_rate"], ascending=False)

    # Robustness diagnostics for the best finalists.
    diag_rows = []
    for _, row in final_df.head(20).iterrows():
        cid = row["config_id"]
        t = trade_map.get(cid)
        if t is None:
            continue
        tt = t[(t["exit_time"] >= holdout_start) & (t["exit_time"] < robust_end)].copy()
        vals = tt["net_return"].to_numpy(float)
        lo, hi = bootstrap_ci(vals)
        daily = aggregate_period(pd.DatetimeIndex(tt["exit_time"]), vals, "1D").to_numpy(float)
        diag = {
            "config_id": cid, "bootstrap_mean_lo95": lo, "bootstrap_mean_hi95": hi,
            "dsr_probability": deflated_sharpe_probability(daily, max(1, len(pre_df))),
            **monte_carlo_drawdown(vals),
        }
        diag_rows.append(diag)
    diag_df = pd.DataFrame(diag_rows)
    if not diag_df.empty:
        final_df = final_df.merge(diag_df, on="config_id", how="left")
    final_df.to_csv(RESULT_DIR / "finalists_holdout.csv", index=False)
    pd.DataFrame(improvement_log).to_csv(RESULT_DIR / "iteration_log.csv", index=False)

    # Save top candidate trades and daily/weekly/monthly summaries.
    period_rows = []
    for _, row in final_df.head(20).iterrows():
        cid = row["config_id"]
        t = trade_map.get(cid)
        if t is None:
            continue
        t.to_parquet(RESULT_DIR / f"trades_{cid}.parquet", index=False)
        tt = t[(t["exit_time"] >= holdout_start) & (t["exit_time"] < robust_end)]
        for label, freq in [("daily", "1D"), ("weekly", "W-SUN"), ("monthly", "ME")]:
            s = aggregate_period(pd.DatetimeIndex(tt["exit_time"]), tt["net_return"].to_numpy(float), freq)
            period_rows.append({
                "config_id": cid, "period": label, "active_periods": len(s),
                "positive_rate": float(np.mean(s > 0)) if len(s) else np.nan,
                "mean_return": float(s.mean()) if len(s) else np.nan,
                "median_return": float(s.median()) if len(s) else np.nan,
                "compounded_return": float(np.prod(1 + s.to_numpy()) - 1) if len(s) else np.nan,
                "best_period": float(s.max()) if len(s) else np.nan,
                "worst_period": float(s.min()) if len(s) else np.nan,
            })
    pd.DataFrame(period_rows).to_csv(RESULT_DIR / "period_summary_top20.csv", index=False)

    ensembles = ensemble_search(final_df, trade_map, holdout_start, robust_end)
    ensembles.to_csv(RESULT_DIR / "ensemble_candidates.csv", index=False)

    validated = final_df[final_df["validated_pass"] == True]
    high_win_pool = final_df[(final_df["oos_trades"] >= MIN_FINAL_TRADES) & (final_df["oos_pf"] >= 1.10) & (final_df["oos_mean"] > 0)]
    champion_daily = (validated if not validated.empty else high_win_pool).sort_values(["oos_positive_active_day_rate", "oos_win_rate", "oos_total_return"], ascending=False).head(1)
    champion_win = (validated if not validated.empty else high_win_pool).sort_values(["oos_win_rate", "oos_positive_active_day_rate", "oos_total_return"], ascending=False).head(1)
    champion_profit = (validated if not validated.empty else high_win_pool).sort_values(["oos_total_return", "oos_pf"], ascending=False).head(1)

    def record(frame: pd.DataFrame) -> dict[str, Any] | None:
        if frame.empty:
            return None
        out = frame.iloc[0].replace({np.nan: None}).to_dict()
        for k, v in list(out.items()):
            if isinstance(v, (np.bool_,)):
                out[k] = bool(v)
            elif isinstance(v, (np.integer,)):
                out[k] = int(v)
            elif isinstance(v, (np.floating,)):
                out[k] = float(v)
        return out

    summary = {
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": "linxy/USDT-M_Perpetual_Futures mirror of Binance public data",
        "requested_start": str(REQUESTED_START), "common_price_end": str(common_end), "robust_funding_complete_end": str(robust_end),
        "holdout_start": str(holdout_start), "base_cost_bps": BASE_COST * 10000, "stress_cost_bps": STRESS_COST * 10000,
        "trial_budget": MAX_TRIALS, "trials_executed": int(len(pre_df)), "finalists": int(len(final_df)),
        "validated_winner_count": int(len(validated)),
        "status": "VALIDATED_WINNER_FOUND" if len(validated) else "NO_FULLY_VALIDATED_WINNER",
        "stopping_rule": "Maximum four rounds per symbol/timeframe; stop after two consecutive rounds improve pre-holdout score by <0.25 percentage point or global trial budget reached.",
        "champion_daily_positive_rate": record(champion_daily),
        "champion_trade_win_rate": record(champion_win),
        "champion_profit": record(champion_profit),
        "best_ensemble": record(ensembles.head(1)) if not ensembles.empty else None,
        "important_note": "Highest observed result is not a guarantee of profit on every day. Final holdout was not used to generate or mutate configurations.",
        "runtime_seconds": time.time() - t0,
    }
    (RESULT_DIR / "research_summary_v8.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    # Human-readable report.
    lines = [
        "# COIN V8 — ITERATIVE LONG/SHORT INDICATOR RESEARCH",
        "",
        f"- Generated: {summary['generated_at_utc']}",
        f"- Price data: {REQUESTED_START} to {common_end}",
        f"- Funding-complete robust endpoint: {robust_end}",
        f"- Locked final holdout starts: {holdout_start}",
        f"- Trials executed: {len(pre_df):,}",
        f"- Finalists evaluated on locked holdout: {len(final_df):,}",
        f"- Fully validated winners: {len(validated):,}",
        f"- Status: **{summary['status']}**",
        "",
        "## Stopping rule",
        summary["stopping_rule"],
        "",
        "## Champion by positive active-day rate",
        "```json",
        json.dumps(summary["champion_daily_positive_rate"], indent=2, ensure_ascii=False, default=str),
        "```",
        "",
        "## Champion by trade win rate",
        "```json",
        json.dumps(summary["champion_trade_win_rate"], indent=2, ensure_ascii=False, default=str),
        "```",
        "",
        "## Best equal-weight ensemble",
        "```json",
        json.dumps(summary["best_ensemble"], indent=2, ensure_ascii=False, default=str),
        "```",
        "",
        "## Interpretation",
        "A high win rate is accepted only when expectancy is positive, Profit Factor and drawdown gates pass, and profitability survives doubled trading cost. No result guarantees a positive P/L every calendar day.",
    ]
    (RESULT_DIR / "REPORT_V8_VI.md").write_text("\n".join(lines), encoding="utf-8")
    (RESULT_DIR / "run_manifest.json").write_text(json.dumps({
        "github_run_id": os.getenv("GITHUB_RUN_ID"), "github_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
        "github_sha": os.getenv("GITHUB_SHA"), "generated_at_utc": summary["generated_at_utc"],
        "result_files": sorted(p.name for p in RESULT_DIR.iterdir()),
    }, indent=2), encoding="utf-8")
    log(f"Research complete in {(time.time() - t0) / 60:.1f} minutes: {summary['status']}")


if __name__ == "__main__":
    main()
