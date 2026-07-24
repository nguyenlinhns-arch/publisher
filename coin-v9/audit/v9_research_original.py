from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import math
import os
import random
import shutil
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.stats import norm

SEED = 20260724
RNG = np.random.default_rng(SEED)
random.seed(SEED)

ROOT = Path(__file__).resolve().parent
BASE_PATH = ROOT.parent / "coin-v8" / "audit" / "iterative_research_original.py"
RAW_DIR = ROOT / "output" / "raw"
RESULT_DIR = ROOT / "results"
RAW_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)

# Load the audited V8 source as a library. We reuse its causal feature builder,
# funding alignment and conservative stop-first Numba simulator.
spec = importlib.util.spec_from_file_location("coin_v8_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Cannot load audited V8 source")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)

SYMBOLS = ("BTCUSDT", "ETHUSDT")
TIMEFRAMES = {"5m": 5, "15m": 15}
FAMILIES = (
    "TREND_STATE_SCALP",
    "FLOW_STATE_SCALP",
    "RSI_ROC_STATE_SCALP",
    "EMA_RSI_SCALP",
    "MACD_ZERO_CROSS",
    "VWAP_FLOW_SCALP",
    "BOLLINGER_FADE",
    "DONCHIAN_MICRO_BREAK",
    "STOCH_EMA_REVERSAL",
    "TREND_PULLBACK",
    "MOMENTUM_CONTINUATION",
    "SQUEEZE_BREAKOUT",
    "SWEEP_RECLAIM",
    "RANGE_REVERSION",
    "VWAP_RECLAIM",
)

REQUESTED_START = pd.Timestamp("2020-01-01", tz="UTC")
BASE_COST = 0.0012   # 12 bps round trip on notional
STRESS_COST = 0.0024 # 24 bps round trip on notional
MAX_TRIALS = 12_000
BROAD_PER_FAMILY_SIDE_DATASET = 80  # 15*2*80*4 = 9,600 broad targets, then mutation to 12,000
DATASET_TRIAL_CAP = MAX_TRIALS // (len(SYMBOLS) * len(TIMEFRAMES))
TOP_PARENTS = 24
MUTATIONS_PER_PARENT = 10
FINALISTS_PER_DATASET = 45
FINAL_HOLDOUT_DAYS = 365
MIN_PRE_TRADES = 500
MIN_FINAL_SAMPLE = 300
TARGET_TRADES_PER_CAL_DAY = 4.0
START_EQUITY_VND = 10_000_000.0
LEVERAGES = (10, 20, 30, 40, 50, 60, 70, 80)
RISK_FRACTIONS = (0.0025, 0.005, 0.0075, 0.01)
MARGIN_ALLOCATIONS = (0.05, 0.10, 0.20)


def log(msg: str) -> None:
    print(f"[{pd.Timestamp.now(tz='UTC').isoformat()}] {msg}", flush=True)


def ensure_data() -> None:
    urls: dict[str, str] = {}
    for symbol in SYMBOLS:
        base_url = f"https://huggingface.co/datasets/linxy/USDT-M_Perpetual_Futures/resolve/main/{symbol}"
        urls[f"{symbol}_5m.parquet"] = f"{base_url}/{symbol}_5m.parquet?download=true"
        urls[f"{symbol}_metrics.parquet"] = f"{base_url}/{symbol}_metrics.parquet?download=true"
        urls[f"{symbol}_fundingRate.parquet"] = f"{base_url}/{symbol}_fundingRate.parquet?download=true"
    for name, url in urls.items():
        base.download(url, RAW_DIR / name)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def choice(seq: Iterable[Any]) -> Any:
    seq = list(seq)
    return seq[int(RNG.integers(0, len(seq)))]


def corrected_aggregate_period(exit_times: pd.DatetimeIndex, returns: np.ndarray, freq: str) -> pd.Series:
    if len(returns) == 0:
        return pd.Series(dtype=float)
    s = pd.Series(np.asarray(returns, float), index=pd.DatetimeIndex(exit_times))
    grouped = s.groupby(pd.Grouper(freq=freq))
    counts = grouped.size()
    compounded = grouped.apply(lambda z: float(np.prod(1.0 + z.to_numpy(float)) - 1.0))
    return compounded[counts > 0].dropna()


def corrected_period_counts(exit_times: pd.DatetimeIndex, freq: str) -> pd.Series:
    if len(exit_times) == 0:
        return pd.Series(dtype=int)
    s = pd.Series(1, index=pd.DatetimeIndex(exit_times), dtype=int)
    grouped = s.groupby(pd.Grouper(freq=freq)).sum()
    return grouped[grouped > 0]


def max_drawdown_from_returns(returns: np.ndarray) -> float:
    if len(returns) == 0:
        return np.nan
    eq = np.cumprod(1.0 + np.clip(np.asarray(returns, float), -0.999, None))
    peak = np.maximum.accumulate(eq)
    return float(np.min(eq / peak - 1.0))


def profit_factor(returns: np.ndarray) -> float:
    r = np.asarray(returns, float)
    gains = r[r > 0].sum()
    losses = -r[r < 0].sum()
    if losses <= 0:
        return float("inf") if gains > 0 else np.nan
    return float(gains / losses)


def metrics_from_trades(exit_times: pd.DatetimeIndex, returns: np.ndarray, calendar_start: pd.Timestamp, calendar_end: pd.Timestamp) -> dict[str, float]:
    returns = np.asarray(returns, float)
    n = len(returns)
    keys = [
        "trades", "win_rate", "pf", "mean", "median", "total_return", "max_dd", "calendar_daily_sharpe",
        "positive_active_day_rate", "positive_calendar_day_rate", "active_days", "trades_per_calendar_day",
        "mean_trades_per_active_day", "median_trades_per_active_day", "pct_calendar_days_ge4", "pct_active_days_ge4",
        "positive_ge4_day_rate", "positive_week_rate", "active_weeks", "positive_month_rate", "active_months", "payoff",
    ]
    if n == 0:
        return {k: np.nan for k in keys}

    daily = corrected_aggregate_period(exit_times, returns, "1D")
    daily_counts = corrected_period_counts(exit_times, "1D")
    weekly = corrected_aggregate_period(exit_times, returns, "W-SUN")
    monthly = corrected_aggregate_period(exit_times, returns, "ME")
    cal_index = pd.date_range(calendar_start.floor("D"), calendar_end.floor("D") - pd.Timedelta(days=1), freq="1D", tz="UTC")
    cal_days = max(1, len(cal_index))
    daily_full = daily.reindex(cal_index, fill_value=0.0)
    dstd = daily_full.std(ddof=1)
    sharpe = float(daily_full.mean() / dstd * math.sqrt(365)) if len(daily_full) > 1 and dstd > 0 else np.nan
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    payoff = float(wins.mean() / -losses.mean()) if len(wins) and len(losses) else np.nan
    ge4_days = daily_counts[daily_counts >= 4].index
    positive_ge4 = daily.reindex(ge4_days).dropna()

    return {
        "trades": float(n),
        "win_rate": float(np.mean(returns > 0)),
        "pf": profit_factor(returns),
        "mean": float(np.mean(returns)),
        "median": float(np.median(returns)),
        "total_return": float(np.prod(1.0 + np.clip(returns, -0.999, None)) - 1.0),
        "max_dd": max_drawdown_from_returns(returns),
        "calendar_daily_sharpe": sharpe,
        "positive_active_day_rate": float(np.mean(daily > 0)) if len(daily) else np.nan,
        "positive_calendar_day_rate": float((daily > 0).sum() / cal_days),
        "active_days": float(len(daily)),
        "trades_per_calendar_day": float(n / cal_days),
        "mean_trades_per_active_day": float(daily_counts.mean()) if len(daily_counts) else np.nan,
        "median_trades_per_active_day": float(daily_counts.median()) if len(daily_counts) else np.nan,
        "pct_calendar_days_ge4": float((daily_counts >= 4).sum() / cal_days),
        "pct_active_days_ge4": float(np.mean(daily_counts >= 4)) if len(daily_counts) else np.nan,
        "positive_ge4_day_rate": float(np.mean(positive_ge4 > 0)) if len(positive_ge4) else np.nan,
        "positive_week_rate": float(np.mean(weekly > 0)) if len(weekly) else np.nan,
        "active_weeks": float(len(weekly)),
        "positive_month_rate": float(np.mean(monthly > 0)) if len(monthly) else np.nan,
        "active_months": float(len(monthly)),
        "payoff": payoff,
    }


def slice_metrics(exit_times: pd.DatetimeIndex, returns: np.ndarray, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, float]:
    mask = (exit_times >= start) & (exit_times < end)
    return metrics_from_trades(exit_times[mask], returns[mask], start, end)


def fold_metrics(exit_times: pd.DatetimeIndex, returns: np.ndarray, bounds: list[tuple[pd.Timestamp, pd.Timestamp]]) -> list[dict[str, float]]:
    return [slice_metrics(exit_times, returns, a, b) for a, b in bounds]


def build_features(df: pd.DataFrame, minutes: int, htf: pd.DataFrame | None, metrics: pd.DataFrame, funding: pd.DataFrame) -> pd.DataFrame:
    x = base.build_features(df, minutes, htf, metrics, funding)
    # Add a causal 3-bar Donchian channel for micro-breakout families.
    x["don_hi3"] = x["high"].shift(1).rolling(3).max()
    x["don_lo3"] = x["low"].shift(1).rolling(3).min()
    atr_rel = x["atr"] / x["close"].replace(0, np.nan)
    x["atr_rel"] = atr_rel
    x["atr_z"] = base.rolling_z(np.log(atr_rel.replace(0, np.nan)), max(60, int(24 * 60 / minutes)))
    x["ema9_slope"] = (x["ema9"] - x["ema9"].shift(3)) / x["atr"].replace(0, np.nan)
    x["macd_cross_up"] = (x["macd_hist"] > 0) & (x["macd_hist"].shift(1) <= 0)
    x["macd_cross_down"] = (x["macd_hist"] < 0) & (x["macd_hist"].shift(1) >= 0)
    x["vwap_cross_up"] = (x["close"] > x["vwap"]) & (x["close"].shift(1) <= x["vwap"].shift(1))
    x["vwap_cross_down"] = (x["close"] < x["vwap"]) & (x["close"].shift(1) >= x["vwap"].shift(1))
    x["hour_utc"] = x.index.hour.astype(np.int16)
    return x


def session_mask(hours: np.ndarray, session: str) -> np.ndarray:
    if session == "ALL":
        return np.ones(len(hours), dtype=bool)
    if session == "ASIA":
        return (hours >= 0) & (hours < 8)
    if session == "EUROPE":
        return (hours >= 7) & (hours < 16)
    if session == "US":
        return (hours >= 13) & (hours < 22)
    if session == "OVERLAP":
        return (hours >= 13) & (hours < 16)
    raise ValueError(session)


def sample_config(family: str, symbol: str, timeframe: str, side: int) -> dict[str, Any]:
    minutes = TIMEFRAMES[timeframe]
    atr_lo = choice([-2.0, -1.0, -0.5, 0.0])
    atr_hi = choice([0.5, 1.0, 1.5, 2.0, 3.0])
    if atr_hi <= atr_lo:
        atr_hi = atr_lo + 1.0
    cfg: dict[str, Any] = {
        "family": family,
        "symbol": symbol,
        "timeframe": timeframe,
        "side": int(side),
        "require_htf": bool(RNG.random() < 0.45),
        "htf_200": bool(RNG.random() < 0.15),
        "close_pos": choice([0.50, 0.55, 0.60, 0.65, 0.70]),
        "vol_z_min": choice([-1.0, -0.5, 0.0, 0.5]),
        "flow_z_min": choice([-1.0, -0.5, -0.1, 0.2, 0.5]),
        "crowding_veto": bool(RNG.random() < 0.15),
        "veto_funding": choice([1.25, 1.5, 1.75, 2.0]),
        "veto_oi": choice([0.25, 0.5, 0.75, 1.0]),
        "stop_atr": choice([0.30, 0.40, 0.50, 0.65, 0.80, 1.0, 1.2, 1.5]),
        "target_atr": choice([0.25, 0.35, 0.50, 0.65, 0.80, 1.0, 1.2, 1.5, 2.0]),
        "max_hold": choice({5: [1, 2, 3, 6, 12, 18, 24], 15: [1, 2, 3, 4, 6, 8, 12]}[minutes]),
        "be_trigger": choice([0.0, 0.0, 0.0, 0.5, 0.75]),
        "session": choice(["ALL", "ALL", "ASIA", "EUROPE", "US", "OVERLAP"]),
        "atr_z_min": atr_lo,
        "atr_z_max": atr_hi,
    }

    if family == "TREND_STATE_SCALP":
        cfg.update(rsi_entry=choice([48, 50, 52, 55, 58, 60]), adx_min=choice([6, 8, 12, 16, 20]), ema_gap_atr=choice([-0.05, 0.0, 0.03, 0.05, 0.1]))
    elif family == "FLOW_STATE_SCALP":
        cfg.update(vwap_dist_min=choice([-0.3, -0.1, 0.0, 0.1, 0.3, 0.5]), rsi_entry=choice([45, 48, 50, 52, 55]), adx_min=choice([0, 6, 10, 14]))
    elif family == "RSI_ROC_STATE_SCALP":
        cfg.update(roc_col=choice(["roc3", "roc6"]), roc_min=choice([-0.002, -0.001, 0.0, 0.001, 0.002]), rsi_entry=choice([48, 50, 52, 55, 58, 60]), adx_min=choice([0, 6, 10, 14, 18]))
    elif family == "EMA_RSI_SCALP":
        cfg.update(ema_fast=choice([9, 20]), rsi_entry=choice([48, 50, 52, 55, 58]), adx_min=choice([8, 12, 16, 20]), pullback_atr=choice([0.0, 0.1, 0.2, 0.35]))
    elif family == "MACD_ZERO_CROSS":
        cfg.update(roc_col=choice(["roc3", "roc6"]), roc_min=choice([-0.001, 0.0, 0.001, 0.002]), rsi_entry=choice([48, 50, 52, 55]), adx_min=choice([8, 12, 16, 20]))
    elif family == "VWAP_FLOW_SCALP":
        cfg.update(vwap_abs=choice([0.0, 0.15, 0.3, 0.5, 0.8]), rsi_entry=choice([45, 48, 50, 52, 55]), adx_max=choice([18, 22, 26, 32, 40]))
    elif family == "BOLLINGER_FADE":
        cfg.update(bb_z_abs=choice([0.8, 1.0, 1.2, 1.5, 1.8, 2.1]), rsi_extreme=choice([25, 30, 35, 40, 45]), adx_max=choice([14, 18, 22, 26, 32]))
    elif family == "DONCHIAN_MICRO_BREAK":
        cfg.update(lookback=choice([3, 5, 10, 20]), buffer_atr=choice([-0.05, 0.0, 0.03, 0.05, 0.1]), adx_min=choice([8, 12, 16, 20]), trend_local=bool(RNG.random() < 0.5))
    elif family == "STOCH_EMA_REVERSAL":
        cfg.update(stoch_extreme=choice([15, 20, 25, 30, 35, 40]), bb_z_abs=choice([0.5, 0.8, 1.0, 1.3, 1.6]), adx_max=choice([14, 18, 22, 26, 32]))
    elif family == "TREND_PULLBACK":
        lo = choice([32, 36, 40, 44, 48]); hi = choice([52, 56, 60, 64, 68])
        cfg.update(touch_atr=choice([0.0, 0.1, 0.2, 0.35, 0.5]), rsi_lo=min(lo, hi - 4), rsi_hi=hi, adx_min=choice([8, 12, 16, 20, 24]))
    elif family == "MOMENTUM_CONTINUATION":
        cfg.update(roc_col=choice(["roc3", "roc6", "roc12"]), roc_min=choice([-0.001, 0.0, 0.001, 0.002, 0.004]), rsi_min=choice([48, 52, 56, 60]), lookback=choice([3, 5, 10, 20]), buffer_atr=choice([-0.05, 0.0, 0.03, 0.05, 0.1]), adx_min=choice([8, 12, 16, 20, 24]))
    elif family == "SQUEEZE_BREAKOUT":
        cfg.update(lookback=choice([3, 5, 10, 20]), buffer_atr=choice([-0.05, 0.0, 0.03, 0.05, 0.1]), width_rel_min=choice([0.65, 0.75, 0.9, 1.0, 1.1]))
    elif family == "SWEEP_RECLAIM":
        cfg.update(lookback=choice([3, 5, 10, 20]), depth_atr=choice([-0.05, 0.0, 0.05, 0.1, 0.2]), wick_min=choice([0.0, 0.05, 0.15, 0.3]), trend_context=bool(RNG.random() < 0.5), htf_adx_max=choice([18, 22, 26, 30, 35]))
    elif family == "RANGE_REVERSION":
        cfg.update(bb_z_abs=choice([0.8, 1.0, 1.2, 1.5, 1.8, 2.1]), vwap_abs=choice([0.2, 0.4, 0.7, 1.0, 1.4]), rsi_extreme=choice([25, 30, 35, 40, 45]), stoch_extreme=choice([15, 20, 25, 30, 35]), adx_max=choice([14, 18, 22, 26, 32]), htf_adx_max=choice([18, 22, 26, 30, 35]))
    elif family == "VWAP_RECLAIM":
        cfg.update(vwap_abs=choice([0.15, 0.3, 0.5, 0.7, 1.0, 1.4]), rsi_max=choice([35, 40, 45, 50, 55, 60]), range_only=bool(RNG.random() < 0.5), adx_max=choice([16, 20, 24, 28, 35]), htf_adx_max=choice([20, 24, 28, 32, 36]))
    else:
        raise ValueError(family)
    return cfg


def normalize_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in cfg.items():
        if isinstance(v, np.generic):
            v = v.item()
        if k in {"lookback", "max_hold", "side", "ema_fast"} and v is not None:
            v = int(round(float(v)))
        out[k] = v
    return out


def cfg_id(cfg: dict[str, Any]) -> str:
    payload = json.dumps(normalize_cfg(cfg), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(payload.encode()).hexdigest()[:14]


def mutate_config(parent: dict[str, Any]) -> dict[str, Any]:
    parent = normalize_cfg(parent)
    fresh = sample_config(parent["family"], parent["symbol"], parent["timeframe"], int(parent["side"]))
    cfg = dict(parent)
    mutable = [k for k in fresh if k not in {"family", "symbol", "timeframe", "side"}]
    n_change = int(RNG.integers(2, min(8, len(mutable)) + 1))
    for key in RNG.choice(np.array(mutable, dtype=object), size=n_change, replace=False):
        cfg[str(key)] = fresh[str(key)]
    return normalize_cfg(cfg)


def make_signal(x: pd.DataFrame, cfg: dict[str, Any]) -> np.ndarray:
    cfg = normalize_cfg(cfg)
    side = int(cfg["side"])
    fam = str(cfg["family"])
    c = x["close"].to_numpy(float)
    o = x["open"].to_numpy(float)
    h = x["high"].to_numpy(float)
    l = x["low"].to_numpy(float)
    atr = x["atr"].to_numpy(float)
    ema9 = x["ema9"].to_numpy(float)
    ema20 = x["ema20"].to_numpy(float)
    ema50 = x["ema50"].to_numpy(float)
    rsi7 = x["rsi7"].to_numpy(float)
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
    atrz = x["atr_z"].to_numpy(float)
    hours = x["hour_utc"].to_numpy(int)
    base_ok = np.isfinite(atr) & (atr > 0) & np.isfinite(ema50) & np.isfinite(rsi14)

    if side > 0:
        htf_trend = (htf_e20 > htf_e50) & (htf_close > htf_e50)
        local_trend = (ema20 > ema50) & (c > ema50)
        cp_ok = close_pos >= cfg.get("close_pos", 0.5)
    else:
        htf_trend = (htf_e20 < htf_e50) & (htf_close < htf_e50)
        local_trend = (ema20 < ema50) & (c < ema50)
        cp_ok = close_pos <= 1.0 - cfg.get("close_pos", 0.5)
    if not cfg.get("require_htf", False):
        htf_trend = np.ones(len(x), dtype=bool)
    if cfg.get("htf_200", False):
        htf_trend &= (htf_close > htf_e200) if side > 0 else (htf_close < htf_e200)

    prev_c = np.roll(c, 1)
    prev_ema9 = np.roll(ema9, 1)
    prev_ema20 = np.roll(ema20, 1)

    if fam == "TREND_STATE_SCALP":
        macdh = x["macd_hist"].to_numpy(float)
        gap = (ema9 - ema20) / np.where(atr == 0, np.nan, atr)
        if side > 0:
            state = (ema9 > ema20) & (ema20 > ema50) & (c > ema9) & (macdh > 0) & (rsi7 >= cfg["rsi_entry"]) & (gap >= cfg["ema_gap_atr"])
        else:
            state = (ema9 < ema20) & (ema20 < ema50) & (c < ema9) & (macdh < 0) & (rsi7 <= 100 - cfg["rsi_entry"]) & (gap <= -cfg["ema_gap_atr"])
        sig = state & (adxv >= cfg["adx_min"]) & cp_ok
        if cfg.get("require_htf", False): sig &= htf_trend
    elif fam == "FLOW_STATE_SCALP":
        vd = x["vwap_dist"].to_numpy(float)
        if side > 0:
            state = (vd >= cfg["vwap_dist_min"]) & (rsi7 >= cfg["rsi_entry"]) & (c >= ema9)
        else:
            state = (vd <= -cfg["vwap_dist_min"]) & (rsi7 <= 100 - cfg["rsi_entry"]) & (c <= ema9)
        sig = state & (adxv >= cfg["adx_min"]) & cp_ok
        if cfg.get("require_htf", False): sig &= htf_trend
    elif fam == "RSI_ROC_STATE_SCALP":
        roc = x[cfg["roc_col"]].to_numpy(float)
        if side > 0:
            state = (rsi7 >= cfg["rsi_entry"]) & (roc >= cfg["roc_min"]) & (c >= ema9)
        else:
            state = (rsi7 <= 100 - cfg["rsi_entry"]) & (roc <= -cfg["roc_min"]) & (c <= ema9)
        sig = state & (adxv >= cfg["adx_min"]) & cp_ok
        if cfg.get("require_htf", False): sig &= htf_trend
    elif fam == "EMA_RSI_SCALP":
        fast = ema9 if cfg["ema_fast"] == 9 else ema20
        prev_fast = prev_ema9 if cfg["ema_fast"] == 9 else prev_ema20
        if side > 0:
            trend = fast > ema20 if cfg["ema_fast"] == 9 else ema20 > ema50
            pull = l <= fast + cfg["pullback_atr"] * atr
            recross = (c > fast) & (prev_c <= prev_fast)
            mom = rsi7 >= cfg["rsi_entry"]
        else:
            trend = fast < ema20 if cfg["ema_fast"] == 9 else ema20 < ema50
            pull = h >= fast - cfg["pullback_atr"] * atr
            recross = (c < fast) & (prev_c >= prev_fast)
            mom = rsi7 <= 100 - cfg["rsi_entry"]
        sig = trend & pull & recross & mom & (adxv >= cfg["adx_min"]) & cp_ok
        if cfg.get("require_htf", False): sig &= htf_trend
    elif fam == "MACD_ZERO_CROSS":
        macdh = x["macd_hist"].to_numpy(float)
        prev_m = np.roll(macdh, 1)
        roc = x[cfg["roc_col"]].to_numpy(float)
        if side > 0:
            cross = (macdh > 0) & (prev_m <= 0)
            mom = (roc >= cfg["roc_min"]) & (rsi14 >= cfg["rsi_entry"])
        else:
            cross = (macdh < 0) & (prev_m >= 0)
            mom = (roc <= -cfg["roc_min"]) & (rsi14 <= 100 - cfg["rsi_entry"])
        sig = cross & mom & (adxv >= cfg["adx_min"]) & cp_ok
        if cfg.get("require_htf", False): sig &= htf_trend
    elif fam == "VWAP_FLOW_SCALP":
        vd = x["vwap_dist"].to_numpy(float)
        vwap = x["vwap"].to_numpy(float)
        prev_vwap = np.roll(vwap, 1)
        if side > 0:
            cross = (c > vwap) & (prev_c <= prev_vwap)
            prior_exc = np.minimum(vd, np.roll(vd, 1)) <= -cfg["vwap_abs"]
            mom = rsi14 >= cfg["rsi_entry"]
        else:
            cross = (c < vwap) & (prev_c >= prev_vwap)
            prior_exc = np.maximum(vd, np.roll(vd, 1)) >= cfg["vwap_abs"]
            mom = rsi14 <= 100 - cfg["rsi_entry"]
        sig = cross & prior_exc & mom & (adxv <= cfg["adx_max"]) & cp_ok
    elif fam == "BOLLINGER_FADE":
        bbz = x["bb_z"].to_numpy(float)
        prev_bbz = np.roll(bbz, 1)
        if side > 0:
            reenter = (bbz > -cfg["bb_z_abs"]) & (prev_bbz <= -cfg["bb_z_abs"])
            extreme = rsi7 <= cfg["rsi_extreme"]
        else:
            reenter = (bbz < cfg["bb_z_abs"]) & (prev_bbz >= cfg["bb_z_abs"])
            extreme = rsi7 >= 100 - cfg["rsi_extreme"]
        sig = reenter & extreme & (adxv <= cfg["adx_max"]) & cp_ok
    elif fam == "DONCHIAN_MICRO_BREAK":
        lb = cfg["lookback"]
        level = x[f"don_hi{lb}"].to_numpy(float) if side > 0 else x[f"don_lo{lb}"].to_numpy(float)
        brk = c >= level + cfg["buffer_atr"] * atr if side > 0 else c <= level - cfg["buffer_atr"] * atr
        sig = brk & (adxv >= cfg["adx_min"]) & cp_ok
        if cfg.get("trend_local", False): sig &= local_trend
        if cfg.get("require_htf", False): sig &= htf_trend
    elif fam == "STOCH_EMA_REVERSAL":
        st = x["stoch"].to_numpy(float); sts = x["stoch_signal"].to_numpy(float)
        pst = np.roll(st, 1); psts = np.roll(sts, 1)
        bbz = x["bb_z"].to_numpy(float)
        if side > 0:
            cross = (st > sts) & (pst <= psts) & (pst <= cfg["stoch_extreme"])
            extreme = bbz <= -cfg["bb_z_abs"]
            ema_ok = c >= ema9
        else:
            cross = (st < sts) & (pst >= psts) & (pst >= 100 - cfg["stoch_extreme"])
            extreme = bbz >= cfg["bb_z_abs"]
            ema_ok = c <= ema9
        sig = cross & extreme & ema_ok & (adxv <= cfg["adx_max"]) & cp_ok
    elif fam == "TREND_PULLBACK":
        touched = (l <= ema20 + cfg["touch_atr"] * atr) if side > 0 else (h >= ema20 - cfg["touch_atr"] * atr)
        crossed = (c > ema20) & (prev_c <= prev_ema20) if side > 0 else (c < ema20) & (prev_c >= prev_ema20)
        rsi_ok = (rsi14 >= cfg["rsi_lo"]) & (rsi14 <= cfg["rsi_hi"])
        sig = local_trend & htf_trend & touched & crossed & rsi_ok & (adxv >= cfg["adx_min"]) & cp_ok
    elif fam == "MOMENTUM_CONTINUATION":
        macdh = x["macd_hist"].to_numpy(float)
        roc = x[cfg["roc_col"]].to_numpy(float)
        lb = cfg["lookback"]
        brk_level = x[f"don_hi{lb}"].to_numpy(float) if side > 0 else x[f"don_lo{lb}"].to_numpy(float)
        price_break = c >= brk_level + cfg["buffer_atr"] * atr if side > 0 else c <= brk_level - cfg["buffer_atr"] * atr
        mom = (macdh > 0) & (roc > cfg["roc_min"]) & (rsi14 >= cfg["rsi_min"]) if side > 0 else (macdh < 0) & (roc < -cfg["roc_min"]) & (rsi14 <= 100 - cfg["rsi_min"])
        sig = local_trend & htf_trend & mom & price_break & (adxv >= cfg["adx_min"]) & cp_ok
    elif fam == "SQUEEZE_BREAKOUT":
        sq = x["squeeze"].fillna(False).to_numpy(bool)
        prev_sq = np.roll(sq, 1)
        width_rel = x["bb_width_rel"].to_numpy(float)
        lb = cfg["lookback"]
        level = x[f"don_hi{lb}"].to_numpy(float) if side > 0 else x[f"don_lo{lb}"].to_numpy(float)
        release = prev_sq & (~sq) & (width_rel >= cfg["width_rel_min"])
        breakout = c >= level + cfg["buffer_atr"] * atr if side > 0 else c <= level - cfg["buffer_atr"] * atr
        sig = release & breakout & cp_ok
        if cfg.get("require_htf", False): sig &= htf_trend
    elif fam == "SWEEP_RECLAIM":
        lb = cfg["lookback"]
        level = x[f"don_lo{lb}"].to_numpy(float) if side > 0 else x[f"don_hi{lb}"].to_numpy(float)
        swept = l < level - cfg["depth_atr"] * atr if side > 0 else h > level + cfg["depth_atr"] * atr
        reclaimed = c > level if side > 0 else c < level
        wick = x["lower_wick_atr"].to_numpy(float) if side > 0 else x["upper_wick_atr"].to_numpy(float)
        sig = swept & reclaimed & (wick >= cfg["wick_min"]) & cp_ok
        if cfg.get("trend_context", False): sig &= htf_trend
        else: sig &= htf_adx <= cfg["htf_adx_max"]
    elif fam == "RANGE_REVERSION":
        bbz = x["bb_z"].to_numpy(float); vd = x["vwap_dist"].to_numpy(float); st = x["stoch"].to_numpy(float)
        if side > 0:
            extreme = (bbz <= -cfg["bb_z_abs"]) & (vd <= -cfg["vwap_abs"]) & (rsi14 <= cfg["rsi_extreme"]) & (st <= cfg["stoch_extreme"])
        else:
            extreme = (bbz >= cfg["bb_z_abs"]) & (vd >= cfg["vwap_abs"]) & (rsi14 >= 100 - cfg["rsi_extreme"]) & (st >= 100 - cfg["stoch_extreme"])
        sig = extreme & (adxv <= cfg["adx_max"]) & (htf_adx <= cfg["htf_adx_max"]) & cp_ok
    elif fam == "VWAP_RECLAIM":
        vd = x["vwap_dist"].to_numpy(float); vwap = x["vwap"].to_numpy(float); pvwap = np.roll(vwap, 1)
        if side > 0:
            excursion = np.minimum(vd, np.roll(vd, 1)) <= -cfg["vwap_abs"]
            reclaim = (c > vwap) & (prev_c <= pvwap)
            rsi_ok = rsi14 <= cfg["rsi_max"]
        else:
            excursion = np.maximum(vd, np.roll(vd, 1)) >= cfg["vwap_abs"]
            reclaim = (c < vwap) & (prev_c >= pvwap)
            rsi_ok = rsi14 >= 100 - cfg["rsi_max"]
        sig = excursion & reclaim & rsi_ok & cp_ok
        if cfg.get("range_only", False): sig &= (adxv <= cfg["adx_max"]) & (htf_adx <= cfg["htf_adx_max"])
        else: sig &= htf_trend
    else:
        raise ValueError(fam)

    sig &= base_ok
    sig &= session_mask(hours, cfg["session"])
    sig &= np.isfinite(atrz) & (atrz >= cfg["atr_z_min"]) & (atrz <= cfg["atr_z_max"])
    sig &= volz >= cfg.get("vol_z_min", -10.0)
    if side > 0: sig &= flowz >= cfg.get("flow_z_min", -10.0)
    else: sig &= flowz <= -cfg.get("flow_z_min", -10.0)
    if cfg.get("crowding_veto", False):
        if side > 0: sig &= ~((funding_z > cfg["veto_funding"]) & (oi_z > cfg["veto_oi"]))
        else: sig &= ~((funding_z < -cfg["veto_funding"]) & (oi_z > cfg["veto_oi"]))
    sig[:250] = False
    sig[-2:] = False
    sig[0] = False
    return np.nan_to_num(sig, nan=False).astype(bool)


def score_pre(folds: list[dict[str, float]], whole: dict[str, float]) -> float:
    valid = [f for f in folds if f.get("trades", 0) >= 80 and np.isfinite(f.get("pf", np.nan))]
    if whole.get("trades", 0) < MIN_PRE_TRADES or len(valid) < 3:
        return -1e9
    positive_folds = sum(f["mean"] > 0 and f["pf"] > 1.0 for f in valid)
    med_wr = float(np.nanmedian([f["win_rate"] for f in valid]))
    med_day = float(np.nanmedian([f["positive_active_day_rate"] for f in valid]))
    med_freq = float(np.nanmedian([f["trades_per_calendar_day"] for f in valid]))
    med_days4 = float(np.nanmedian([f["pct_calendar_days_ge4"] for f in valid]))
    med_pf = float(np.nanmedian([min(f["pf"], 3.0) for f in valid]))
    med_mean = float(np.nanmedian([f["mean"] for f in valid]))
    dd = abs(min(0.0, whole.get("max_dd", -1.0)))
    freq_score = min(max(med_freq / TARGET_TRADES_PER_CAL_DAY, 0.0), 1.25)
    days4_score = min(max(med_days4 / 0.50, 0.0), 1.0)
    score = (
        0.20 * med_wr + 0.18 * med_day + 0.22 * freq_score + 0.15 * days4_score
        + 0.10 * min(med_pf / 1.8, 1.0) + 0.10 * min(max(med_mean * 1500, -1), 1)
        + 0.05 * (positive_folds / len(valid))
    )
    if whole["mean"] <= 0 or whole["pf"] < 1.03: score -= 0.45
    if positive_folds < math.ceil(len(valid) * 0.6): score -= 0.25
    if whole.get("trades_per_calendar_day", 0) < 1.0: score -= 0.20
    if dd > 0.35: score -= min(0.4, dd - 0.35)
    return float(score)


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
    cfg = normalize_cfg(cfg)
    signal = make_signal(x, cfg)
    idx = np.flatnonzero(signal).astype(np.int64)
    row: dict[str, Any] = {**cfg, "config_id": cfg_id(cfg), "raw_signals": int(len(idx))}
    if len(idx) < 50 or len(idx) > len(x) * 0.50:
        row.update(pre_score=-1e9, pre_trades=0)
        return row, None
    entries, exits, net, gross, reasons = base.simulate_trades(
        idx,
        x["open"].to_numpy(float), x["high"].to_numpy(float), x["low"].to_numpy(float), x["close"].to_numpy(float),
        x["atr"].to_numpy(float), funding_cum, int(cfg["side"]), float(cfg["stop_atr"]), float(cfg["target_atr"]),
        int(cfg["max_hold"]), BASE_COST, float(cfg["be_trigger"]),
    )
    exit_times = pd.DatetimeIndex(x.index[exits]) + pd.Timedelta(minutes=TIMEFRAMES[cfg["timeframe"]])
    pre_mask = (exit_times >= pre_start) & (exit_times < holdout_start)
    pre_metrics = metrics_from_trades(exit_times[pre_mask], net[pre_mask], pre_start, holdout_start)
    fmetrics = fold_metrics(exit_times, net, folds)
    row["pre_score"] = score_pre(fmetrics, pre_metrics)
    for k, v in pre_metrics.items(): row[f"pre_{k}"] = v
    row["positive_pre_folds"] = int(sum(f.get("mean", np.nan) > 0 and f.get("pf", 0) > 1 for f in fmetrics if f.get("trades", 0) >= 80))
    row["valid_pre_folds"] = int(sum(f.get("trades", 0) >= 80 for f in fmetrics))
    if not evaluate_holdout:
        return row, None

    final_mask = (exit_times >= holdout_start) & (exit_times < final_end)
    fm = metrics_from_trades(exit_times[final_mask], net[final_mask], holdout_start, final_end)
    stress_ret = net[final_mask] - (STRESS_COST - BASE_COST)
    sm = metrics_from_trades(exit_times[final_mask], stress_ret, holdout_start, final_end)
    for k, v in fm.items(): row[f"oos_{k}"] = v
    for k, v in sm.items(): row[f"stress_{k}"] = v
    gates = {
        "sample": fm["trades"] >= MIN_FINAL_SAMPLE,
        "pf": fm["pf"] >= 1.15,
        "mean": fm["mean"] > 0,
        "stress": sm["pf"] >= 1.02 and sm["mean"] > 0,
        "drawdown": fm["max_dd"] >= -0.20,
        "days": fm["positive_active_day_rate"] >= 0.55,
        "weeks": fm["positive_week_rate"] >= 0.52,
        "months": fm["positive_month_rate"] >= 0.55,
        "folds": row["positive_pre_folds"] >= max(3, math.ceil(max(row["valid_pre_folds"], 1) * 0.60)),
        "frequency4": fm["trades_per_calendar_day"] >= TARGET_TRADES_PER_CAL_DAY,
        "days4coverage": fm["pct_calendar_days_ge4"] >= 0.50,
    }
    row.update({f"gate_{k}": bool(v) for k, v in gates.items()})
    row["gates_passed"] = int(sum(gates.values()))
    row["validated_pass"] = bool(all(gates.values()))
    freq_score = min(np.nan_to_num(fm["trades_per_calendar_day"], nan=0.0) / TARGET_TRADES_PER_CAL_DAY, 1.25)
    days4_score = min(np.nan_to_num(fm["pct_calendar_days_ge4"], nan=0.0) / 0.50, 1.0)
    row["final_score"] = (
        0.22 * np.nan_to_num(fm["positive_active_day_rate"], nan=0.0)
        + 0.18 * np.nan_to_num(fm["win_rate"], nan=0.0)
        + 0.22 * freq_score + 0.13 * days4_score
        + 0.10 * min(np.nan_to_num(fm["pf"], nan=0.0) / 1.8, 1.0)
        + 0.08 * min(max(np.nan_to_num(fm["mean"], nan=-1.0) * 1500, -1), 1)
        + 0.04 * min(max(np.nan_to_num(sm["mean"], nan=-1.0) * 1500, -1), 1)
        + 0.03 * (row["gates_passed"] / len(gates))
    )
    entry_price = x["open"].to_numpy(float)[entries]
    signal_idx = entries - 1
    signal_atr = x["atr"].to_numpy(float)[signal_idx]
    stop_pct = float(cfg["stop_atr"]) * signal_atr / entry_price
    target_pct = float(cfg["target_atr"]) * signal_atr / entry_price
    trades = pd.DataFrame({
        "symbol": cfg["symbol"], "timeframe": cfg["timeframe"], "family": cfg["family"], "side": int(cfg["side"]),
        "config_id": row["config_id"],
        "entry_time": pd.DatetimeIndex(x.index[entries]) + pd.Timedelta(minutes=TIMEFRAMES[cfg["timeframe"]]),
        "exit_time": exit_times,
        "net_return": net,
        "gross_return": gross,
        "reason": reasons,
        "entry_price": entry_price,
        "signal_atr": signal_atr,
        "stop_pct": stop_pct,
        "target_pct": target_pct,
    })
    return row, trades


def config_from_row(row: dict[str, Any]) -> dict[str, Any]:
    ignore_prefixes = ("pre_", "oos_", "stress_", "gate_")
    ignore = {"config_id", "raw_signals", "positive_pre_folds", "valid_pre_folds", "gates_passed", "validated_pass", "final_score", "round", "bootstrap_mean_lo95", "bootstrap_mean_hi95", "dsr_probability", "mc_dd_median", "mc_dd_p95_worst"}
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k in ignore or any(k.startswith(p) for p in ignore_prefixes): continue
        try:
            if pd.isna(v): continue
        except (TypeError, ValueError):
            pass
        out[k] = v
    return normalize_cfg(out)


def choose_finalists(rows: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    frame = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan)
    if frame.empty: return []
    viable = frame[(frame["pre_trades"] >= MIN_PRE_TRADES) & (frame["pre_mean"] > 0) & (frame["pre_pf"] >= 1.03)].copy()
    if viable.empty:
        return frame.sort_values("pre_score", ascending=False).head(n).to_dict("records")
    picks: list[dict[str, Any]] = []
    for _, g in viable.groupby(["family", "side"]):
        picks.extend(g.sort_values(["pre_score", "pre_trades_per_calendar_day"], ascending=False).head(2).to_dict("records"))
    seen = {r["config_id"] for r in picks}
    for r in viable.sort_values(["pre_score", "pre_trades_per_calendar_day", "pre_pf"], ascending=False).to_dict("records"):
        if r["config_id"] not in seen:
            picks.append(r); seen.add(r["config_id"])
        if len(picks) >= n: break
    return picks[:n]


def bootstrap_ci(values: np.ndarray, block: int = 8, reps: int = 2000) -> tuple[float, float]:
    values = np.asarray(values, float)
    values = values[np.isfinite(values)]
    if len(values) < 30: return np.nan, np.nan
    n = len(values); starts = np.arange(n); means = np.empty(reps)
    for r in range(reps):
        sample: list[float] = []
        while len(sample) < n:
            s = int(RNG.choice(starts))
            sample.extend(values[(s + np.arange(block)) % n].tolist())
        means[r] = np.mean(sample[:n])
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def monte_carlo_drawdown(values: np.ndarray, reps: int = 2500) -> dict[str, float]:
    values = np.asarray(values, float)
    if len(values) < 30: return {"mc_dd_median": np.nan, "mc_dd_p95_worst": np.nan}
    dds = np.empty(reps)
    for i in range(reps): dds[i] = max_drawdown_from_returns(RNG.permutation(values))
    return {"mc_dd_median": float(np.median(dds)), "mc_dd_p95_worst": float(np.quantile(dds, 0.05))}


def deflated_sharpe_probability(daily_full: np.ndarray, n_trials: int) -> float:
    d = np.asarray(daily_full, float); d = d[np.isfinite(d)]
    if len(d) < 30 or d.std(ddof=1) <= 0: return np.nan
    sr = d.mean() / d.std(ddof=1) * math.sqrt(365)
    gamma = 0.5772156649
    z1 = norm.ppf(1 - 1 / max(n_trials, 2)); z2 = norm.ppf(1 - 1 / (max(n_trials, 2) * math.e))
    sr0 = math.sqrt(max(1e-12, 1 / max(len(d) - 1, 1))) * ((1 - gamma) * z1 + gamma * z2) * math.sqrt(365)
    skew = pd.Series(d).skew(); kurt = pd.Series(d).kurt() + 3
    denom = math.sqrt(max(1e-12, (1 - skew * sr / math.sqrt(365) + ((kurt - 1) / 4) * (sr / math.sqrt(365)) ** 2) / max(len(d) - 1, 1))) * math.sqrt(365)
    return float(norm.cdf((sr - sr0) / denom))


def diagnostic_for_trades(t: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, n_trials: int) -> dict[str, float]:
    tt = t[(t["exit_time"] >= start) & (t["exit_time"] < end)].copy()
    vals = tt["net_return"].to_numpy(float)
    lo, hi = bootstrap_ci(vals)
    daily = corrected_aggregate_period(pd.DatetimeIndex(tt["exit_time"]), vals, "1D")
    cal = pd.date_range(start.floor("D"), end.floor("D") - pd.Timedelta(days=1), freq="1D", tz="UTC")
    daily_full = daily.reindex(cal, fill_value=0.0).to_numpy(float)
    return {"bootstrap_mean_lo95": lo, "bootstrap_mean_hi95": hi, "dsr_probability": deflated_sharpe_probability(daily_full, n_trials), **monte_carlo_drawdown(vals)}


def strategy_daily_and_counts(t: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.Series, pd.Series]:
    tt = t[(t["exit_time"] >= start) & (t["exit_time"] < end)]
    daily = corrected_aggregate_period(pd.DatetimeIndex(tt["exit_time"]), tt["net_return"].to_numpy(float), "1D")
    counts = corrected_period_counts(pd.DatetimeIndex(tt["exit_time"]), "1D")
    return daily, counts


def portfolio_metrics(members: list[str], trade_map: dict[str, pd.DataFrame], start: pd.Timestamp, end: pd.Timestamp) -> dict[str, Any]:
    cal = pd.date_range(start.floor("D"), end.floor("D") - pd.Timedelta(days=1), freq="1D", tz="UTC")
    ret_cols = []; count_cols = []
    for cid in members:
        d, c = strategy_daily_and_counts(trade_map[cid], start, end)
        ret_cols.append(d.reindex(cal, fill_value=0.0).rename(cid))
        count_cols.append(c.reindex(cal, fill_value=0).rename(cid))
    aligned = pd.concat(ret_cols, axis=1) if ret_cols else pd.DataFrame(index=cal)
    counts = pd.concat(count_cols, axis=1) if count_cols else pd.DataFrame(index=cal)
    port = aligned.mean(axis=1) if len(members) else pd.Series(0.0, index=cal)
    ntr = counts.sum(axis=1)
    active = ntr > 0
    equity = np.cumprod(1 + np.clip(port.to_numpy(float), -0.999, None))
    dd = float(np.min(equity / np.maximum.accumulate(equity) - 1)) if len(equity) else np.nan
    std = port.std(ddof=1)
    return {
        "members": json.dumps(members), "size": len(members), "trades": int(ntr.sum()),
        "trades_per_calendar_day": float(ntr.mean()), "median_trades_per_day": float(ntr.median()),
        "pct_calendar_days_ge4": float(np.mean(ntr >= 4)), "active_days": int(active.sum()),
        "positive_active_day_rate": float(np.mean(port[active] > 0)) if active.any() else np.nan,
        "positive_calendar_day_rate": float(np.mean(port > 0)),
        "total_return": float(equity[-1] - 1) if len(equity) else np.nan,
        "max_dd": dd,
        "daily_sharpe": float(port.mean() / std * math.sqrt(365)) if std > 0 else np.nan,
        "daily_pf": profit_factor(port.to_numpy(float)),
    }


def ensemble_pre_score(m: dict[str, Any]) -> float:
    return (
        0.25 * np.nan_to_num(m["positive_active_day_rate"], nan=0.0)
        + 0.25 * min(m["trades_per_calendar_day"] / TARGET_TRADES_PER_CAL_DAY, 1.25)
        + 0.15 * min(m["pct_calendar_days_ge4"] / 0.50, 1.0)
        + 0.15 * min(np.nan_to_num(m["daily_pf"], nan=0.0) / 1.5, 1.0)
        + 0.10 * min(max(m["total_return"], -1), 1)
        + 0.10 * min(max(m["daily_sharpe"] / 2, -1), 1)
    )


def search_ensembles(final_df: pd.DataFrame, trade_map: dict[str, pd.DataFrame], pre_start: pd.Timestamp, holdout_start: pd.Timestamp, final_end: pd.Timestamp) -> pd.DataFrame:
    viable = final_df[(final_df["pre_mean"] > 0) & (final_df["pre_pf"] >= 1.03) & (final_df["pre_trades"] >= MIN_PRE_TRADES)].copy()
    viable = viable.sort_values(["pre_score", "pre_trades_per_calendar_day"], ascending=False).head(36)
    ids = [cid for cid in viable["config_id"] if cid in trade_map]
    meta = viable.set_index("config_id")
    if len(ids) < 2: return pd.DataFrame()

    candidates: dict[tuple[str, ...], dict[str, Any]] = {}
    # Greedy path selected entirely pre-holdout.
    current: list[str] = []
    available = ids.copy()
    for _ in range(min(8, len(available))):
        best = None; best_score = -1e9
        for cid in available:
            trial = current + [cid]
            # No more than two copies of same symbol/family.
            mm = meta.loc[trial]
            if mm.groupby(["symbol", "family"]).size().max() > 2: continue
            pm = portfolio_metrics(trial, trade_map, pre_start, holdout_start)
            sc = ensemble_pre_score(pm)
            if sc > best_score: best_score, best = sc, (cid, pm)
        if best is None: break
        cid, pm = best; current.append(cid); available.remove(cid)
        key = tuple(sorted(current)); candidates[key] = {**pm, "pre_score": best_score, "selection": "greedy"}

    # Random diversified combinations, selected using pre-holdout only.
    for _ in range(5000):
        size = int(RNG.integers(2, min(9, len(ids) + 1)))
        combo = tuple(sorted(RNG.choice(np.array(ids, dtype=object), size=size, replace=False).tolist()))
        if combo in candidates: continue
        mm = meta.loc[list(combo)]
        if mm.groupby(["symbol", "family"]).size().max() > 2: continue
        pm = portfolio_metrics(list(combo), trade_map, pre_start, holdout_start)
        candidates[combo] = {**pm, "pre_score": ensemble_pre_score(pm), "selection": "random"}

    pre_frame = pd.DataFrame([{**v, "ensemble_id": "+".join(k)} for k, v in candidates.items()])
    pre_frame = pre_frame.sort_values(["pre_score", "trades_per_calendar_day", "total_return"], ascending=False).head(60)
    rows = []
    for _, r in pre_frame.iterrows():
        members = json.loads(r["members"])
        pre = portfolio_metrics(members, trade_map, pre_start, holdout_start)
        oos = portfolio_metrics(members, trade_map, holdout_start, final_end)
        row = {"ensemble_id": r["ensemble_id"], "members": r["members"], "size": len(members), "selection": r["selection"], "pre_score": r["pre_score"]}
        row.update({f"pre_{k}": v for k, v in pre.items() if k not in {"members", "size"}})
        row.update({f"oos_{k}": v for k, v in oos.items() if k not in {"members", "size"}})
        row["gate_frequency4"] = oos["trades_per_calendar_day"] >= TARGET_TRADES_PER_CAL_DAY
        row["gate_days4coverage"] = oos["pct_calendar_days_ge4"] >= 0.50
        row["gate_profit"] = oos["total_return"] > 0 and oos["daily_pf"] > 1.0
        row["gate_drawdown"] = oos["max_dd"] >= -0.20
        row["ensemble_pass"] = all([row["gate_frequency4"], row["gate_days4coverage"], row["gate_profit"], row["gate_drawdown"]])
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["ensemble_pass", "oos_positive_active_day_rate", "oos_trades_per_calendar_day", "oos_total_return"], ascending=False)


def leverage_overlay_single(t: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, config_id: str) -> pd.DataFrame:
    tt = t[(t["exit_time"] >= start) & (t["exit_time"] < end)].sort_values("entry_time").copy()
    rows: list[dict[str, Any]] = []
    cal_days = max(1, (end.floor("D") - start.floor("D")).days)
    for lev, risk, margin_alloc in itertools.product(LEVERAGES, RISK_FRACTIONS, MARGIN_ALLOCATIONS):
        for case, extra_cost, mmr_fee in [("base", 0.0, 0.006), ("stress", STRESS_COST - BASE_COST, 0.011)]:
            equity = START_EQUITY_VND; peak = equity; max_dd = 0.0
            liquidations = 0; skipped_safety = 0; executed = 0
            daily_pnl: dict[pd.Timestamp, float] = {}; daily_count: dict[pd.Timestamp, int] = {}
            eff_levs: list[float] = []
            liq_buffer = 1.0 / lev - mmr_fee
            for rec in tt.itertuples(index=False):
                if equity <= 0: break
                stop_pct = float(rec.stop_pct)
                if not np.isfinite(stop_pct) or stop_pct <= 0 or liq_buffer <= 0 or stop_pct > 0.65 * liq_buffer:
                    skipped_safety += 1
                    continue
                risk_budget = equity * risk
                notional_risk = risk_budget / stop_pct
                notional_margin = equity * margin_alloc * lev
                notional = min(notional_risk, notional_margin)
                if notional <= 0: continue
                margin_used = notional / lev
                gross = float(rec.gross_return)
                net = float(rec.net_return) - extra_cost
                day = pd.Timestamp(rec.exit_time).floor("D")
                if gross <= -liq_buffer:
                    pnl = -margin_used
                    liquidations += 1
                else:
                    pnl = notional * net
                equity += pnl
                peak = max(peak, equity)
                max_dd = min(max_dd, equity / peak - 1.0)
                daily_pnl[day] = daily_pnl.get(day, 0.0) + pnl
                daily_count[day] = daily_count.get(day, 0) + 1
                executed += 1; eff_levs.append(notional / max(equity - pnl, 1e-9))
            vals = np.array(list(daily_pnl.values()), float)
            counts = np.array(list(daily_count.values()), int)
            active_days = len(vals)
            rows.append({
                "config_id": config_id, "cost_case": case, "leverage_setting": lev, "risk_fraction": risk,
                "margin_allocation": margin_alloc, "start_equity_vnd": START_EQUITY_VND, "final_equity_vnd": equity,
                "total_return": equity / START_EQUITY_VND - 1.0, "max_drawdown": max_dd,
                "executed_trades": executed, "trades_per_calendar_day": executed / cal_days,
                "active_days": active_days, "positive_active_day_rate": float(np.mean(vals > 0)) if active_days else np.nan,
                "pct_active_days_ge4": float(np.mean(counts >= 4)) if len(counts) else np.nan,
                "pct_calendar_days_ge4": float(np.sum(counts >= 4) / cal_days) if len(counts) else 0.0,
                "liquidations": liquidations, "skipped_liquidation_safety": skipped_safety,
                "mean_effective_leverage": float(np.mean(eff_levs)) if eff_levs else np.nan,
                "max_effective_leverage": float(np.max(eff_levs)) if eff_levs else np.nan,
                "approx_liq_buffer": liq_buffer,
                "safe_pass": bool(liquidations == 0 and equity > START_EQUITY_VND and max_dd >= -0.20),
                "daily4_pass": bool(executed / cal_days >= TARGET_TRADES_PER_CAL_DAY and np.sum(counts >= 4) / cal_days >= 0.50),
            })
    return pd.DataFrame(rows)


def main() -> None:
    t0 = time.time()
    ensure_data()
    data: dict[str, dict[str, Any]] = {}
    audits: list[dict[str, Any]] = []
    common_end: pd.Timestamp | None = None
    funding_end: pd.Timestamp | None = None
    for symbol in SYMBOLS:
        base.RAW_DIR = RAW_DIR
        base.REQUESTED_START = REQUESTED_START
        k = base.load_kline(symbol); f = base.load_funding(symbol); m = base.load_metrics(symbol)
        audits.extend(base.audit_data(symbol, k, m, f))
        end = k.index.max() + pd.Timedelta(minutes=5)
        common_end = end if common_end is None else min(common_end, end)
        fend = f["time"].max()
        funding_end = fend if funding_end is None else min(funding_end, fend)
        data[symbol] = {"kline": k, "funding": f, "metrics": m}
    assert common_end is not None and funding_end is not None
    holdout_start = common_end - pd.Timedelta(days=FINAL_HOLDOUT_DAYS)
    robust_end = min(common_end, funding_end + pd.Timedelta(hours=8))
    if robust_end - holdout_start < pd.Timedelta(days=300): robust_end = common_end
    pre_start = pd.Timestamp("2021-01-01", tz="UTC")
    folds = [
        (pd.Timestamp("2021-01-01", tz="UTC"), pd.Timestamp("2022-01-01", tz="UTC")),
        (pd.Timestamp("2022-01-01", tz="UTC"), pd.Timestamp("2023-01-01", tz="UTC")),
        (pd.Timestamp("2023-01-01", tz="UTC"), pd.Timestamp("2024-01-01", tz="UTC")),
        (pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2025-01-01", tz="UTC")),
        (pd.Timestamp("2025-01-01", tz="UTC"), holdout_start),
    ]
    pd.DataFrame(audits).to_csv(RESULT_DIR / "data_audit_v9.csv", index=False)

    all_pre: list[dict[str, Any]] = []
    all_final: list[dict[str, Any]] = []
    trade_map: dict[str, pd.DataFrame] = {}
    iteration_log: list[dict[str, Any]] = []
    trials = 0

    for symbol in SYMBOLS:
        base5 = data[symbol]["kline"]; funding = data[symbol]["funding"]; metrics = data[symbol]["metrics"]
        raw60 = base.resample_ohlcv(base5, 60)
        htf60 = build_features(raw60, 60, None, metrics, funding)
        for tf, minutes in TIMEFRAMES.items():
            log(f"Preparing {symbol} {tf}")
            raw = base.resample_ohlcv(base5, minutes)
            x = build_features(raw, minutes, htf60, metrics, funding)
            fund_cum = base.build_funding_cumulative(x.index, minutes, funding)
            dataset_rows: list[dict[str, Any]] = []
            seen: set[str] = set()

            # Broad unique coverage, balanced across all four symbol/timeframe datasets.
            for fam in FAMILIES:
                for side in (1, -1):
                    added = 0; attempts = 0
                    while added < BROAD_PER_FAMILY_SIDE_DATASET and trials < MAX_TRIALS and attempts < BROAD_PER_FAMILY_SIDE_DATASET * 20:
                        attempts += 1
                        cfg = sample_config(fam, symbol, tf, side); cid = cfg_id(cfg)
                        if cid in seen: continue
                        seen.add(cid); trials += 1; added += 1
                        row, _ = evaluate_config(x, fund_cum, cfg, pre_start, holdout_start, robust_end, folds, False)
                        row["round"] = 1; dataset_rows.append(row); all_pre.append(row)
            best1 = max((r.get("pre_score", -1e9) for r in dataset_rows), default=-1e9)
            iteration_log.append({"symbol": symbol, "timeframe": tf, "round": 1, "best_pre_score": best1, "dataset_trials": len(dataset_rows), "trials_cumulative": trials})

            # Mutate top pre-holdout parents until global budget is exhausted.
            round_no = 2
            while trials < MAX_TRIALS and len(dataset_rows) < DATASET_TRIAL_CAP and round_no <= 5:
                parents = sorted(dataset_rows, key=lambda r: r.get("pre_score", -1e9), reverse=True)[:TOP_PARENTS]
                new_rows = 0
                for p in parents:
                    pcfg = config_from_row(p)
                    for _ in range(MUTATIONS_PER_PARENT):
                        if trials >= MAX_TRIALS or len(dataset_rows) >= DATASET_TRIAL_CAP: break
                        cfg = mutate_config(pcfg); cid = cfg_id(cfg)
                        if cid in seen: continue
                        seen.add(cid); trials += 1; new_rows += 1
                        row, _ = evaluate_config(x, fund_cum, cfg, pre_start, holdout_start, robust_end, folds, False)
                        row["round"] = round_no; dataset_rows.append(row); all_pre.append(row)
                bestn = max((r.get("pre_score", -1e9) for r in dataset_rows), default=-1e9)
                iteration_log.append({"symbol": symbol, "timeframe": tf, "round": round_no, "best_pre_score": bestn, "new_trials": new_rows, "dataset_trials": len(dataset_rows), "trials_cumulative": trials})
                if new_rows == 0: break
                round_no += 1

            finalists = choose_finalists(dataset_rows, FINALISTS_PER_DATASET)
            for item in finalists:
                cfg = config_from_row(item)
                row, tdf = evaluate_config(x, fund_cum, cfg, pre_start, holdout_start, robust_end, folds, True)
                row["round"] = item.get("round", np.nan); all_final.append(row)
                if tdf is not None: trade_map[row["config_id"]] = tdf
            log(f"Finished {symbol} {tf}: {len(dataset_rows)} pre trials; {len(finalists)} finalists; cumulative {trials}")
            del x, raw, fund_cum

    pre_df = pd.DataFrame(all_pre)
    final_df = pd.DataFrame(all_final)
    pre_df.to_csv(RESULT_DIR / "all_trials_pre_holdout_v9.csv", index=False)
    pd.DataFrame(iteration_log).to_csv(RESULT_DIR / "iteration_log_v9.csv", index=False)

    # Diagnostics for the top 40 by the frequency/profit score.
    final_df = final_df.sort_values(["validated_pass", "final_score", "oos_trades_per_calendar_day", "oos_positive_active_day_rate", "oos_total_return"], ascending=False)
    diag_rows = []
    for _, r in final_df.head(40).iterrows():
        cid = r["config_id"]; tdf = trade_map.get(cid)
        if tdf is None: continue
        diag_rows.append({"config_id": cid, **diagnostic_for_trades(tdf, holdout_start, robust_end, len(pre_df))})
    if diag_rows:
        final_df = final_df.merge(pd.DataFrame(diag_rows), on="config_id", how="left")
    final_df["validated_pass_strict"] = (
        final_df["validated_pass"].fillna(False)
        & (final_df["bootstrap_mean_lo95"] > 0)
        & (final_df["dsr_probability"] >= 0.95)
    )
    final_df.to_csv(RESULT_DIR / "finalists_holdout_v9.csv", index=False)

    # Save all finalist ledgers; needed for audit and ensemble selection.
    ledger_dir = RESULT_DIR / "trade_ledgers"; ledger_dir.mkdir(exist_ok=True)
    for cid, tdf in trade_map.items():
        tdf.to_parquet(ledger_dir / f"trades_{cid}.parquet", index=False)

    ensembles = search_ensembles(final_df, trade_map, pre_start, holdout_start, robust_end)
    ensembles.to_csv(RESULT_DIR / "ensemble_candidates_v9.csv", index=False)

    # Leverage overlay for the top 25 individual candidates by final score plus profitability/frequency ranks.
    ids: list[str] = []
    for frame in [
        final_df.sort_values("final_score", ascending=False).head(15),
        final_df[final_df["oos_mean"] > 0].sort_values("oos_win_rate", ascending=False).head(10),
        final_df[final_df["oos_mean"] > 0].sort_values("oos_trades_per_calendar_day", ascending=False).head(10),
        final_df[final_df["stress_mean"] > 0].sort_values("oos_total_return", ascending=False).head(10),
    ]:
        for cid in frame["config_id"].tolist():
            if cid not in ids and cid in trade_map: ids.append(cid)
    leverage_frames = []
    for cid in ids[:30]:
        leverage_frames.append(leverage_overlay_single(trade_map[cid], holdout_start, robust_end, cid))
    leverage_df = pd.concat(leverage_frames, ignore_index=True) if leverage_frames else pd.DataFrame()
    leverage_df.to_csv(RESULT_DIR / "leverage_overlay_v9.csv", index=False)

    # Compact rankings.
    positive = final_df[(final_df["oos_mean"] > 0) & (final_df["oos_pf"] > 1.0)].copy()
    rank_high_win = positive.sort_values(["oos_win_rate", "oos_positive_active_day_rate", "oos_total_return"], ascending=False).head(20)
    rank_daily = positive.sort_values(["oos_positive_active_day_rate", "oos_trades_per_calendar_day", "oos_total_return"], ascending=False).head(20)
    rank_freq = positive.sort_values(["oos_trades_per_calendar_day", "oos_pct_calendar_days_ge4", "oos_total_return"], ascending=False).head(20)
    rank_profit = positive.sort_values(["oos_total_return", "oos_pf"], ascending=False).head(20)
    rank_stress = final_df[(final_df["stress_mean"] > 0) & (final_df["stress_pf"] > 1.02)].sort_values(["stress_total_return", "oos_trades_per_calendar_day"], ascending=False).head(20)
    for name, frame in [("high_win", rank_high_win), ("daily", rank_daily), ("frequency", rank_freq), ("profit", rank_profit), ("stress", rank_stress)]:
        frame.to_csv(RESULT_DIR / f"ranking_{name}_v9.csv", index=False)

    lev_safe = leverage_df[(leverage_df.get("safe_pass", False) == True) & (leverage_df.get("cost_case", "") == "base")].copy() if not leverage_df.empty else pd.DataFrame()
    lev_daily = lev_safe[lev_safe["daily4_pass"] == True].sort_values(["positive_active_day_rate", "total_return"], ascending=False) if not lev_safe.empty else pd.DataFrame()
    if not lev_safe.empty: lev_safe.sort_values(["total_return", "positive_active_day_rate"], ascending=False).head(100).to_csv(RESULT_DIR / "ranking_leverage_safe_v9.csv", index=False)
    if not lev_daily.empty: lev_daily.head(100).to_csv(RESULT_DIR / "ranking_leverage_daily4_v9.csv", index=False)

    def rec(frame: pd.DataFrame) -> dict[str, Any] | None:
        if frame is None or frame.empty: return None
        d = frame.iloc[0].replace({np.nan: None}).to_dict()
        out = {}
        for k, v in d.items():
            if isinstance(v, np.bool_): v = bool(v)
            elif isinstance(v, np.integer): v = int(v)
            elif isinstance(v, np.floating): v = float(v)
            out[k] = v
        return out

    summary = {
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": "BTCUSDT/ETHUSDT Binance public mirror data previously collected by Coin project",
        "requested_start": str(REQUESTED_START), "common_price_end": str(common_end), "holdout_start": str(holdout_start), "robust_end": str(robust_end),
        "trial_budget": MAX_TRIALS, "trials_executed": int(len(pre_df)), "minimum_requested_trials_met": bool(len(pre_df) >= 10_000),
        "symbols": list(SYMBOLS), "execution_timeframes": list(TIMEFRAMES), "families": list(FAMILIES),
        "base_cost_bps": BASE_COST * 10000, "stress_cost_bps": STRESS_COST * 10000,
        "starting_capital_vnd": START_EQUITY_VND, "leverage_settings_tested": list(LEVERAGES),
        "target_trades_per_calendar_day": TARGET_TRADES_PER_CAL_DAY,
        "finalists": int(len(final_df)), "validated_winners": int(final_df["validated_pass"].fillna(False).sum()),
        "strict_validated_winners": int(final_df["validated_pass_strict"].fillna(False).sum()),
        "daily4_validated_winners": int((final_df["gate_frequency4"].fillna(False) & final_df["gate_days4coverage"].fillna(False) & final_df["gate_mean"].fillna(False) & final_df["gate_stress"].fillna(False)).sum()),
        "champion_high_win": rec(rank_high_win), "champion_daily": rec(rank_daily), "champion_frequency": rec(rank_freq),
        "champion_profit": rec(rank_profit), "champion_stress": rec(rank_stress),
        "preselected_ensemble_champion": rec(ensembles),
        "best_safe_leverage_overlay": rec(lev_safe.sort_values(["total_return", "positive_active_day_rate"], ascending=False)) if not lev_safe.empty else None,
        "best_daily4_leverage_overlay": rec(lev_daily) if not lev_daily.empty else None,
        "methodology_notes": [
            "At least 10,000 unique signal configurations evaluated before holdout ranking.",
            "Final holdout was not used to mutate signal configurations.",
            "Ensemble membership was selected using pre-holdout performance only.",
            "Leverage is an execution/risk overlay; it does not increase the underlying signal win rate.",
            "Position size is stop-risk based and capped by isolated-margin allocation and leverage setting.",
            "80x is blocked whenever the stop is not safely inside a conservative approximate liquidation buffer.",
            "No production, paper or testnet orders were sent.",
        ],
        "runtime_seconds": time.time() - t0,
    }
    (RESULT_DIR / "research_summary_v9.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    # Human-readable Vietnamese report.
    lines = [
        "# COIN V9 — NGHIÊN CỨU GIAO DỊCH HÀNG NGÀY & ĐÒN BẨY",
        "",
        f"- Thời gian tạo: {summary['generated_at_utc']}",
        f"- Số trial thực tế: {summary['trials_executed']:,}",
        f"- Đạt yêu cầu tối thiểu 10.000 trial: {summary['minimum_requested_trials_met']}",
        f"- Holdout khóa: {holdout_start} → {robust_end}",
        f"- Vốn mô phỏng: {START_EQUITY_VND:,.0f} VND",
        f"- Đòn bẩy được stress: {', '.join(map(str, LEVERAGES))}x",
        f"- Winner đầy đủ: {summary['validated_winners']}",
        f"- Winner strict bootstrap + DSR: {summary['strict_validated_winners']}",
        f"- Winner đồng thời đạt ưu tiên ≥4 lệnh/ngày: {summary['daily4_validated_winners']}",
        "",
        "## Champion tỷ lệ thắng (chỉ xét expectancy dương)",
        "```json", json.dumps(summary["champion_high_win"], indent=2, ensure_ascii=False, default=str), "```",
        "",
        "## Champion tần suất", "```json", json.dumps(summary["champion_frequency"], indent=2, ensure_ascii=False, default=str), "```",
        "",
        "## Champion lợi nhuận", "```json", json.dumps(summary["champion_profit"], indent=2, ensure_ascii=False, default=str), "```",
        "",
        "## Champion chịu chi phí 24 bps", "```json", json.dumps(summary["champion_stress"], indent=2, ensure_ascii=False, default=str), "```",
        "",
        "## Ensemble được chọn bằng pre-holdout", "```json", json.dumps(summary["preselected_ensemble_champion"], indent=2, ensure_ascii=False, default=str), "```",
        "",
        "## Overlay đòn bẩy an toàn tốt nhất", "```json", json.dumps(summary["best_safe_leverage_overlay"], indent=2, ensure_ascii=False, default=str), "```",
        "",
        "## Kết luận phương pháp",
        "Đòn bẩy chỉ khuếch đại lãi/lỗ và không làm tăng tỷ lệ thắng của tín hiệu. Kết quả chỉ được gọi là ứng viên triển vọng khi còn dương sau phí, funding, stress chi phí, drawdown và kiểm tra khoảng cách thanh lý bảo thủ. Không có lệnh thật nào được gửi.",
    ]
    (RESULT_DIR / "REPORT_V9_VI.md").write_text("\n".join(lines), encoding="utf-8")

    manifest = {
        "files": [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha256_file(p)} for p in sorted(RESULT_DIR.rglob("*")) if p.is_file()],
        "summary": summary,
    }
    (RESULT_DIR / "manifest_v9.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    zip_path = ROOT / "COIN_V9_DAILY_LEVERAGE_RESULTS.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in RESULT_DIR.rglob("*"):
            if p.is_file(): zf.write(p, p.relative_to(ROOT))
    (ROOT / "COIN_V9_DAILY_LEVERAGE_RESULTS.zip.sha256").write_text(sha256_file(zip_path) + "\n", encoding="utf-8")
    log(f"V9 complete in {(time.time()-t0)/60:.1f} min; trials={len(pre_df)}; zip={zip_path}")


if __name__ == "__main__":
    main()
