from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys
import textwrap

SOURCE = pathlib.Path("coin-v8/audit/iterative_research_original.py")
TARGET = pathlib.Path("coin-v8/iterative_research_v82.py")
EXPECTED_SOURCE_SHA256 = "ec5b1979369135917866bb732eaca0f856b964545691db9952026d84f5c45273"


def replace_function(text: str, name: str, next_name: str, replacement: str) -> str:
    start = text.index(f"def {name}(")
    end = text.index(f"\n\ndef {next_name}", start)
    return text[:start] + textwrap.dedent(replacement).strip() + "\n" + text[end:]


def main() -> None:
    raw = SOURCE.read_bytes()
    source_sha = hashlib.sha256(raw).hexdigest()
    if source_sha != EXPECTED_SOURCE_SHA256:
        raise SystemExit(f"Source SHA mismatch: {source_sha}")
    text = raw.decode("utf-8")

    text = text.replace('RESULT_DIR = ROOT / "results"', 'RESULT_DIR = ROOT / "results_v82"', 1)

    make_signal_anchor = (
        'def make_signal(x: pd.DataFrame, cfg: dict[str, Any]) -> np.ndarray:\n'
        '    side = int(cfg["side"])\n'
    )
    make_signal_replacement = (
        'def make_signal(x: pd.DataFrame, cfg: dict[str, Any]) -> np.ndarray:\n'
        '    if "lookback" in cfg:\n'
        '        cfg["lookback"] = int(round(float(cfg["lookback"])))\n'
        '    side = int(cfg["side"])\n'
    )
    if make_signal_anchor not in text:
        raise SystemExit("make_signal patch anchor not found")
    text = text.replace(make_signal_anchor, make_signal_replacement, 1)

    config_anchor = '        out[k] = v\n    return out\n\n\ndef ensemble_search'
    config_replacement = (
        '        if k in {"lookback", "max_hold", "side"}:\n'
        '            v = int(round(float(v)))\n'
        '        elif isinstance(v, np.generic):\n'
        '            v = v.item()\n'
        '        out[k] = v\n'
        '    return out\n\n\ndef ensemble_search'
    )
    if config_anchor not in text:
        raise SystemExit("config_from_row patch anchor not found")
    text = text.replace(config_anchor, config_replacement, 1)

    text = replace_function(
        text,
        "aggregate_period",
        "metrics_from_trades",
        '''
        def aggregate_period(exit_times: pd.DatetimeIndex, returns: np.ndarray, freq: str) -> pd.Series:
            if len(returns) == 0:
                return pd.Series(dtype=float)
            s = pd.Series(np.asarray(returns, float), index=pd.DatetimeIndex(exit_times))
            grouped = s.groupby(pd.Grouper(freq=freq))
            counts = grouped.size()
            compounded = grouped.apply(lambda z: float(np.prod(1.0 + z.to_numpy(float)) - 1.0))
            return compounded[counts > 0].dropna()
        ''',
    )

    text = replace_function(
        text,
        "metrics_from_trades",
        "slice_metrics",
        '''
        def metrics_from_trades(exit_times: pd.DatetimeIndex, returns: np.ndarray, calendar_start: pd.Timestamp, calendar_end: pd.Timestamp) -> dict[str, float]:
            n = len(returns)
            keys = ["trades", "win_rate", "pf", "mean", "median", "total_return", "max_dd", "daily_sharpe", "positive_active_day_rate", "positive_calendar_day_rate", "active_days", "positive_week_rate", "active_weeks", "positive_month_rate", "active_months", "payoff"]
            if n == 0:
                return {k: np.nan for k in keys}
            active_daily = aggregate_period(exit_times, returns, "1D")
            active_weekly = aggregate_period(exit_times, returns, "W-SUN")
            active_monthly = aggregate_period(exit_times, returns, "ME")
            calendar_index = pd.date_range(calendar_start.floor("D"), calendar_end.floor("D"), freq="1D", inclusive="left")
            if len(calendar_index) == 0:
                calendar_index = pd.DatetimeIndex([calendar_start.floor("D")])
            calendar_daily = active_daily.reindex(calendar_index, fill_value=0.0)
            daily_std = calendar_daily.std(ddof=1)
            sharpe = float(calendar_daily.mean() / daily_std * math.sqrt(365)) if len(calendar_daily) > 1 and daily_std > 0 else np.nan
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
                "positive_active_day_rate": float(np.mean(active_daily > 0)) if len(active_daily) else np.nan,
                "positive_calendar_day_rate": float((active_daily > 0).sum() / len(calendar_index)),
                "active_days": float(len(active_daily)),
                "positive_week_rate": float(np.mean(active_weekly > 0)) if len(active_weekly) else np.nan,
                "active_weeks": float(len(active_weekly)),
                "positive_month_rate": float(np.mean(active_monthly > 0)) if len(active_monthly) else np.nan,
                "active_months": float(len(active_monthly)),
                "payoff": payoff,
            }
        ''',
    )

    text = replace_function(
        text,
        "ensemble_search",
        "main",
        '''
        def ensemble_search(final_rows: pd.DataFrame, trade_map: dict[str, pd.DataFrame], holdout_start: pd.Timestamp, final_end: pd.Timestamp) -> pd.DataFrame:
            if final_rows.empty:
                return pd.DataFrame()
            pre_start = pd.Timestamp("2021-01-01", tz="UTC")
            viable = final_rows[(final_rows["pre_trades"] >= MIN_PRE_TRADES) & (final_rows["pre_mean"] > 0) & (final_rows["pre_pf"] >= 1.03)].copy()
            if viable.empty:
                return pd.DataFrame()
            top = viable.sort_values(["pre_score", "pre_pf", "pre_trades"], ascending=False).head(20)
            ids = list(top["config_id"])
            pre_map: dict[str, pd.Series] = {}
            oos_map: dict[str, pd.Series] = {}
            stress_map: dict[str, pd.Series] = {}
            for cid in ids:
                t = trade_map.get(cid)
                if t is None or t.empty:
                    continue
                pre = t[(t["exit_time"] >= pre_start) & (t["exit_time"] < holdout_start)]
                oos = t[(t["exit_time"] >= holdout_start) & (t["exit_time"] < final_end)]
                pre_map[cid] = aggregate_period(pd.DatetimeIndex(pre["exit_time"]), pre["net_return"].to_numpy(float), "1D")
                oos_map[cid] = aggregate_period(pd.DatetimeIndex(oos["exit_time"]), oos["net_return"].to_numpy(float), "1D")
                stress_map[cid] = aggregate_period(pd.DatetimeIndex(oos["exit_time"]), (oos["net_return"] - (STRESS_COST - BASE_COST)).to_numpy(float), "1D")

            def port_stats(raw: pd.DataFrame, calendar_start: pd.Timestamp, calendar_end: pd.Timestamp) -> dict[str, float]:
                if raw.empty:
                    return {}
                calendar_index = pd.date_range(calendar_start.floor("D"), calendar_end.floor("D"), freq="1D", inclusive="left")
                raw = raw.reindex(calendar_index)
                active = raw.notna().any(axis=1)
                aligned = raw.fillna(0.0)
                port = aligned.mean(axis=1)
                port_active = port[active]
                if len(port_active) == 0:
                    return {}
                equity = np.cumprod(1 + port.to_numpy(float))
                peak = np.maximum.accumulate(equity)
                std = port.std(ddof=1)
                return {
                    "active_days": int(active.sum()),
                    "positive_active_day_rate": float(np.mean(port_active > 0)),
                    "positive_calendar_day_rate": float(np.mean(port > 0)),
                    "total_return": float(equity[-1] - 1),
                    "max_dd": float(np.min(equity / peak - 1)),
                    "daily_sharpe": float(port.mean() / std * math.sqrt(365)) if std > 0 else np.nan,
                }

            pre_rows: list[dict[str, Any]] = []
            for size in (2, 3):
                for combo in itertools.combinations(pre_map.keys(), size):
                    meta = top.set_index("config_id").loc[list(combo)]
                    if meta.groupby(["symbol", "family"]).size().max() > 1:
                        continue
                    stats = port_stats(pd.concat([pre_map[c] for c in combo], axis=1), pre_start, holdout_start)
                    if not stats or stats["active_days"] < 80 or stats["total_return"] <= 0 or stats["max_dd"] < -0.20:
                        continue
                    sr = np.nan_to_num(stats["daily_sharpe"], nan=-1.0)
                    pre_score = 0.60 * stats["positive_active_day_rate"] + 0.15 * stats["positive_calendar_day_rate"] + 0.15 * min(max(sr / 2.0, -1), 1) + 0.10 * min(max(stats["total_return"], -1), 1)
                    pre_rows.append({
                        "ensemble_id": "+".join(combo),
                        "size": size,
                        "members": json.dumps(list(combo)),
                        "pre_ensemble_score": float(pre_score),
                        **{f"pre_{k}": v for k, v in stats.items()},
                    })
            if not pre_rows:
                return pd.DataFrame()
            frozen = pd.DataFrame(pre_rows).sort_values(["pre_ensemble_score", "pre_total_return"], ascending=False).head(30)
            output: list[dict[str, Any]] = []
            for _, frozen_row in frozen.iterrows():
                combo = json.loads(frozen_row["members"])
                oos_stats = port_stats(pd.concat([oos_map[c] for c in combo], axis=1), holdout_start, final_end)
                stress_stats = port_stats(pd.concat([stress_map[c] for c in combo], axis=1), holdout_start, final_end)
                row = frozen_row.to_dict()
                row.update({f"oos_{k}": v for k, v in oos_stats.items()})
                row.update({f"stress_{k}": v for k, v in stress_stats.items()})
                output.append(row)
            return pd.DataFrame(output).sort_values(["pre_ensemble_score", "pre_total_return"], ascending=False)
        ''',
    )

    diagnostics_anchor = '        daily = aggregate_period(pd.DatetimeIndex(tt["exit_time"]), vals, "1D").to_numpy(float)\n'
    diagnostics_replacement = (
        '        active_daily = aggregate_period(pd.DatetimeIndex(tt["exit_time"]), vals, "1D")\n'
        '        calendar_index = pd.date_range(holdout_start.floor("D"), robust_end.floor("D"), freq="1D", inclusive="left")\n'
        '        daily = active_daily.reindex(calendar_index, fill_value=0.0).to_numpy(float)\n'
    )
    if diagnostics_anchor not in text:
        raise SystemExit("diagnostics daily anchor not found")
    text = text.replace(diagnostics_anchor, diagnostics_replacement, 1)

    strict_anchor = (
        '    if not diag_df.empty:\n'
        '        final_df = final_df.merge(diag_df, on="config_id", how="left")\n'
        '    final_df.to_csv(RESULT_DIR / "finalists_holdout.csv", index=False)\n'
    )
    strict_replacement = (
        '    if not diag_df.empty:\n'
        '        final_df = final_df.merge(diag_df, on="config_id", how="left")\n'
        '    bootstrap_lo = final_df["bootstrap_mean_lo95"] if "bootstrap_mean_lo95" in final_df else pd.Series(np.nan, index=final_df.index)\n'
        '    dsr = final_df["dsr_probability"] if "dsr_probability" in final_df else pd.Series(np.nan, index=final_df.index)\n'
        '    final_df["validated_pass_strict"] = final_df["validated_pass"].fillna(False) & (bootstrap_lo > 0) & (dsr >= 0.95)\n'
        '    final_df.to_csv(RESULT_DIR / "finalists_holdout.csv", index=False)\n'
    )
    if strict_anchor not in text:
        raise SystemExit("strict validation anchor not found")
    text = text.replace(strict_anchor, strict_replacement, 1)
    text = text.replace(
        'validated = final_df[final_df["validated_pass"] == True]',
        'validated = final_df[final_df["validated_pass_strict"] == True]',
        1,
    )
    text = text.replace(
        '"important_note": "Highest observed result is not a guarantee of profit on every day. Final holdout was not used to generate or mutate configurations."',
        '"important_note": "Highest observed result is exploratory. Strict validation requires every original gate, bootstrap lower mean above zero, and Deflated Sharpe probability at least 95%. Ensemble membership and combinations are frozen using pre-holdout data only."',
        1,
    )
    text = text.replace(
        '# COIN V8 — ITERATIVE LONG/SHORT INDICATOR RESEARCH',
        '# COIN V8.2 — RIGOROUS ITERATIVE LONG/SHORT RESEARCH',
        1,
    )

    TARGET.write_text(text, encoding="utf-8")
    subprocess.run([sys.executable, "-m", "py_compile", str(TARGET)], check=True)
    patched_sha = hashlib.sha256(TARGET.read_bytes()).hexdigest()
    pathlib.Path("coin-v8/status/v82_runner_sha256.txt").write_text(patched_sha + "\n", encoding="utf-8")
    print({"source_sha256": source_sha, "patched_sha256": patched_sha, "target": str(TARGET)})


if __name__ == "__main__":
    main()
