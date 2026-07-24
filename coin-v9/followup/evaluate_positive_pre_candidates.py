from __future__ import annotations

import importlib.util
import itertools
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "audit" / "v9_research_original.py"
RUNTIME_SOURCE = ROOT / "v9_followup_base.py"
CANDIDATE_FILE = ROOT / "followup" / "positive_pre_candidates_run_30112153560.json"
OUT = ROOT / "results_followup"
OUT.mkdir(parents=True, exist_ok=True)


def load_v9():
    shutil.copy2(SOURCE, RUNTIME_SOURCE)
    spec = importlib.util.spec_from_file_location("coin_v9_followup_base", RUNTIME_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load V9 source")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def jsonable(value: Any) -> Any:
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def clean_cfg(item: dict[str, Any], v9) -> tuple[str, dict[str, Any]]:
    original = str(item["original_config_id"])
    cfg = {k: v for k, v in item.items() if k not in {"original_config_id", "pre_metrics_snapshot"}}
    if cfg.get("family") == "SQUEE_BREAKOUT":
        cfg["family"] = "SQUEEZE_BREAKOUT"
    return original, v9.normalize_cfg(cfg)


def portfolio_metrics_cost(v9, members: list[str], trade_map: dict[str, pd.DataFrame], start: pd.Timestamp, end: pd.Timestamp, extra_cost: float) -> dict[str, Any]:
    cal = pd.date_range(start.floor("D"), end.floor("D") - pd.Timedelta(days=1), freq="1D", tz="UTC")
    ret_cols: list[pd.Series] = []
    count_cols: list[pd.Series] = []
    for cid in members:
        t = trade_map[cid]
        tt = t[(t["exit_time"] >= start) & (t["exit_time"] < end)].copy()
        vals = tt["net_return"].to_numpy(float) - extra_cost
        daily = v9.corrected_aggregate_period(pd.DatetimeIndex(tt["exit_time"]), vals, "1D")
        counts = v9.corrected_period_counts(pd.DatetimeIndex(tt["exit_time"]), "1D")
        ret_cols.append(daily.reindex(cal, fill_value=0.0).rename(cid))
        count_cols.append(counts.reindex(cal, fill_value=0).rename(cid))
    aligned = pd.concat(ret_cols, axis=1) if ret_cols else pd.DataFrame(index=cal)
    counts = pd.concat(count_cols, axis=1) if count_cols else pd.DataFrame(index=cal)
    port = aligned.mean(axis=1) if members else pd.Series(0.0, index=cal)
    ntr = counts.sum(axis=1)
    active = ntr > 0
    eq = np.cumprod(1.0 + np.clip(port.to_numpy(float), -0.999, None))
    peak = np.maximum.accumulate(eq) if len(eq) else np.array([])
    dd = float(np.min(eq / peak - 1.0)) if len(eq) else np.nan
    std = float(port.std(ddof=1))
    return {
        "members": json.dumps(members),
        "size": len(members),
        "trades": int(ntr.sum()),
        "trades_per_calendar_day": float(ntr.mean()),
        "median_trades_per_day": float(ntr.median()),
        "pct_calendar_days_ge4": float(np.mean(ntr >= 4)),
        "active_days": int(active.sum()),
        "positive_active_day_rate": float(np.mean(port[active] > 0)) if active.any() else np.nan,
        "positive_calendar_day_rate": float(np.mean(port > 0)),
        "total_return": float(eq[-1] - 1.0) if len(eq) else np.nan,
        "max_dd": dd,
        "daily_sharpe": float(port.mean() / std * math.sqrt(365)) if std > 0 else np.nan,
        "daily_pf": v9.profit_factor(port.to_numpy(float)),
    }


def main() -> None:
    v9 = load_v9()
    payload = json.loads(CANDIDATE_FILE.read_text(encoding="utf-8"))
    items = payload["candidates"]
    v9.ensure_data()

    data: dict[str, dict[str, Any]] = {}
    audits: list[dict[str, Any]] = []
    common_end: pd.Timestamp | None = None
    funding_end: pd.Timestamp | None = None
    for symbol in v9.SYMBOLS:
        v9.base.RAW_DIR = v9.RAW_DIR
        v9.base.REQUESTED_START = v9.REQUESTED_START
        k = v9.base.load_kline(symbol)
        f = v9.base.load_funding(symbol)
        m = v9.base.load_metrics(symbol)
        audits.extend(v9.base.audit_data(symbol, k, m, f))
        end = k.index.max() + pd.Timedelta(minutes=5)
        common_end = end if common_end is None else min(common_end, end)
        fend = f["time"].max()
        funding_end = fend if funding_end is None else min(funding_end, fend)
        data[symbol] = {"kline": k, "funding": f, "metrics": m}
    assert common_end is not None and funding_end is not None
    holdout_start = common_end - pd.Timedelta(days=v9.FINAL_HOLDOUT_DAYS)
    robust_end = min(common_end, funding_end + pd.Timedelta(hours=8))
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
    pd.DataFrame(audits).to_csv(OUT / "data_audit_followup.csv", index=False)

    rows: list[dict[str, Any]] = []
    trade_map: dict[str, pd.DataFrame] = {}
    for symbol in v9.SYMBOLS:
        selected = [it for it in items if it["symbol"] == symbol]
        if not selected:
            continue
        base5 = data[symbol]["kline"]
        funding = data[symbol]["funding"]
        metrics = data[symbol]["metrics"]
        raw60 = v9.base.resample_ohlcv(base5, 60)
        htf60 = v9.build_features(raw60, 60, None, metrics, funding)
        raw15 = v9.base.resample_ohlcv(base5, 15)
        x = v9.build_features(raw15, 15, htf60, metrics, funding)
        fund_cum = v9.base.build_funding_cumulative(x.index, 15, funding)
        for item in selected:
            original_id, cfg = clean_cfg(item, v9)
            row, tdf = v9.evaluate_config(x, fund_cum, cfg, pre_start, holdout_start, robust_end, folds, True)
            row["original_config_id"] = original_id
            row["computed_config_id"] = row["config_id"]
            row["pre_snapshot_match_id"] = bool(row["config_id"] == original_id)
            if tdf is not None:
                diag = v9.diagnostic_for_trades(tdf, holdout_start, robust_end, 12_000)
                row.update(diag)
                trade_map[row["config_id"]] = tdf
                tdf.to_parquet(OUT / f"trades_{row['config_id']}.parquet", index=False)
            strict = {
                "sample30": row.get("oos_trades", 0) >= 30,
                "pf": row.get("oos_pf", 0) >= 1.15,
                "mean": row.get("oos_mean", -1) > 0,
                "stress": row.get("stress_pf", 0) >= 1.02 and row.get("stress_mean", -1) > 0,
                "drawdown": row.get("oos_max_dd", -1) >= -0.20,
                "days": row.get("oos_positive_active_day_rate", 0) >= 0.55,
                "weeks": row.get("oos_positive_week_rate", 0) >= 0.52,
                "months": row.get("oos_positive_month_rate", 0) >= 0.55,
                "bootstrap": row.get("bootstrap_mean_lo95", -1) > 0,
                "dsr": row.get("dsr_probability", 0) >= 0.95,
            }
            row.update({f"followup_gate_{k}": bool(v) for k, v in strict.items()})
            row["followup_gates_passed"] = int(sum(strict.values()))
            row["followup_strict_pass"] = bool(all(strict.values()))
            rows.append(row)

    frame = pd.DataFrame(rows)
    frame = frame.sort_values(
        ["followup_strict_pass", "oos_mean", "oos_pf", "oos_positive_active_day_rate", "oos_total_return"],
        ascending=False,
    )
    frame.to_csv(OUT / "positive_candidates_holdout.csv", index=False)

    # Select ensembles entirely on pre-holdout data, then reveal holdout and stress.
    ids = list(trade_map)
    combo_rows: list[dict[str, Any]] = []
    for size in range(2, min(7, len(ids) + 1)):
        for combo in itertools.combinations(ids, size):
            pre = portfolio_metrics_cost(v9, list(combo), trade_map, pre_start, holdout_start, 0.0)
            if pre["total_return"] <= 0 or pre["daily_pf"] <= 1.0 or pre["max_dd"] < -0.25:
                continue
            combo_rows.append({"members_tuple": combo, "pre_score": v9.ensemble_pre_score(pre), **{f"pre_{k}": v for k, v in pre.items() if k != "members"}})
    combo_rows.sort(key=lambda r: r["pre_score"], reverse=True)
    ensemble_rows: list[dict[str, Any]] = []
    for candidate in combo_rows[:50]:
        members = list(candidate.pop("members_tuple"))
        oos = portfolio_metrics_cost(v9, members, trade_map, holdout_start, robust_end, 0.0)
        stress = portfolio_metrics_cost(v9, members, trade_map, holdout_start, robust_end, v9.STRESS_COST - v9.BASE_COST)
        strict = bool(
            oos["total_return"] > 0
            and oos["daily_pf"] >= 1.10
            and oos["max_dd"] >= -0.20
            and oos["positive_active_day_rate"] >= 0.55
            and stress["total_return"] > 0
            and stress["daily_pf"] >= 1.02
        )
        ensemble_rows.append({
            **candidate,
            "members": json.dumps(members),
            **{f"oos_{k}": v for k, v in oos.items() if k != "members"},
            **{f"stress_{k}": v for k, v in stress.items() if k != "members"},
            "followup_strict_pass": strict,
        })
    ensemble_df = pd.DataFrame(ensemble_rows)
    if not ensemble_df.empty:
        ensemble_df = ensemble_df.sort_values(["followup_strict_pass", "oos_positive_active_day_rate", "oos_total_return"], ascending=False)
    ensemble_df.to_csv(OUT / "preselected_ensembles_holdout.csv", index=False)

    leverage_frames = []
    for cid, tdf in trade_map.items():
        lev = v9.leverage_overlay_single(tdf, holdout_start, robust_end, cid)
        if not lev.empty:
            leverage_frames.append(lev)
    leverage_df = pd.concat(leverage_frames, ignore_index=True) if leverage_frames else pd.DataFrame()
    leverage_df.to_csv(OUT / "leverage_overlay_followup.csv", index=False)

    positive_oos = frame[(frame["oos_mean"] > 0) & (frame["oos_pf"] > 1)].copy()
    stress_positive = frame[(frame["stress_mean"] > 0) & (frame["stress_pf"] > 1.02)].copy()
    best_daily = positive_oos.sort_values(["oos_positive_active_day_rate", "oos_total_return"], ascending=False).head(1)
    best_profit = positive_oos.sort_values(["oos_total_return", "oos_pf"], ascending=False).head(1)
    best_stress = stress_positive.sort_values(["stress_total_return", "oos_total_return"], ascending=False).head(1)
    best_ensemble = ensemble_df.head(1) if not ensemble_df.empty else pd.DataFrame()

    def rec(df: pd.DataFrame) -> dict[str, Any] | None:
        if df.empty:
            return None
        return {k: jsonable(v) for k, v in df.iloc[0].to_dict().items()}

    summary = {
        "source_run_id": payload["source_run_id"],
        "candidate_count": len(items),
        "selection": payload["selection"],
        "holdout_start": holdout_start.isoformat(),
        "robust_end": robust_end.isoformat(),
        "base_cost_bps": v9.BASE_COST * 10000,
        "stress_cost_bps": v9.STRESS_COST * 10000,
        "positive_oos_candidates": int(len(positive_oos)),
        "stress_positive_candidates": int(len(stress_positive)),
        "strict_pass_candidates": int(frame["followup_strict_pass"].sum()),
        "best_daily": rec(best_daily),
        "best_profit": rec(best_profit),
        "best_stress": rec(best_stress),
        "best_preselected_ensemble": rec(best_ensemble),
        "important_note": "Exploratory follow-up after 12,000-trial selection. Low sample candidates are not validated winners.",
        "mode": "RESEARCH_ONLY / NO_PAPER / NO_LIVE",
    }
    (OUT / "followup_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=jsonable), encoding="utf-8")

    lines = [
        "# COIN V9 FOLLOW-UP — POSITIVE PRE-HOLDOUT CANDIDATES",
        "",
        f"- Source run: {payload['source_run_id']}",
        f"- Candidates evaluated: {len(items)}",
        f"- Holdout: {holdout_start} → {robust_end}",
        f"- Positive OOS candidates: {len(positive_oos)}",
        f"- Positive after 24 bps stress: {len(stress_positive)}",
        f"- Strict passes: {int(frame['followup_strict_pass'].sum())}",
        "",
        "## Best daily candidate",
        "```json",
        json.dumps(rec(best_daily), indent=2, ensure_ascii=False, default=jsonable),
        "```",
        "",
        "## Best profit candidate",
        "```json",
        json.dumps(rec(best_profit), indent=2, ensure_ascii=False, default=jsonable),
        "```",
        "",
        "## Best stress-surviving candidate",
        "```json",
        json.dumps(rec(best_stress), indent=2, ensure_ascii=False, default=jsonable),
        "```",
        "",
        "## Best preselected ensemble",
        "```json",
        json.dumps(rec(best_ensemble), indent=2, ensure_ascii=False, default=jsonable),
        "```",
        "",
        "No production, paper or testnet order was sent.",
    ]
    (OUT / "REPORT_FOLLOWUP_V9_VI.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=jsonable))


if __name__ == "__main__":
    main()
