# Coin V7 — Kết quả baseline thực tế

- Sinh lúc UTC: `2026-07-24T12:02:21.430521+00:00`
- Dữ liệu: `2020-01-01` đến `2026-07-19 23:55:00+00:00`
- Holdout: 365 ngày, bắt đầu `2025-07-19 23:55:00+00:00`
- Số candidate: `80`
- Chi phí cơ sở: `12.0 bps` round trip; stress `24.0 bps`.
- Trạng thái: **NO_BASELINE_WINNER**

> Đây là vòng baseline tham số cố định, chưa phải chứng nhận triển khai vốn thật.

## Top 10 theo holdout

| candidate_id                       |   oos_trades |   oos_win_rate |   oos_profit_factor |   oos_mean_bps |   oos_total_return |   oos_max_drawdown |   oos_positive_week_rate |   oos_positive_month_rate |   gates_passed | baseline_pass   |
|:-----------------------------------|-------------:|---------------:|--------------------:|---------------:|-------------------:|-------------------:|-------------------------:|--------------------------:|---------------:|:----------------|
| ETHUSDT_60m_SQUEEZE_BREAKOUT_LONG  |           48 |       0.4375   |            1.59932  |       33.1202  |         0.163896   |         -0.0726558 |                 0.53125  |                 0.538462  |              3 | False           |
| BTCUSDT_30m_SQUEEZE_BREAKOUT_LONG  |           81 |       0.444444 |            1.07924  |        2.7667  |         0.019813   |         -0.0517826 |                 0.431818 |                 0.384615  |              3 | False           |
| ETHUSDT_30m_SQUEEZE_BREAKOUT_LONG  |           92 |       0.391304 |            0.955219 |       -2.52039 |        -0.0296364  |         -0.0869033 |                 0.478261 |                 0.416667  |              2 | False           |
| BTCUSDT_15m_RANGE_BB_RSI_LONG      |           18 |       0.555556 |            0.915992 |       -1.48197 |        -0.00278673 |         -0.0173115 |                 0.588235 |                 0.583333  |              2 | False           |
| ETHUSDT_30m_SQUEEZE_BREAKOUT_SHORT |           82 |       0.341463 |            0.784956 |      -13.9398  |        -0.114071   |         -0.14907   |                 0.428571 |                 0.384615  |              2 | False           |
| ETHUSDT_60m_SQUEEZE_BREAKOUT_SHORT |           50 |       0.32     |            0.666582 |      -28.4061  |        -0.138077   |         -0.147876  |                 0.37931  |                 0.307692  |              2 | False           |
| BTCUSDT_60m_SQUEEZE_BREAKOUT_SHORT |           53 |       0.301887 |            0.663492 |      -22.1066  |        -0.114146   |         -0.149005  |                 0.366667 |                 0.333333  |              2 | False           |
| ETHUSDT_5m_RANGE_BB_RSI_LONG       |           62 |       0.483871 |            0.526563 |       -9.28901 |        -0.0563264  |         -0.0586414 |                 0.378378 |                 0.25      |              2 | False           |
| BTCUSDT_5m_RANGE_BB_RSI_SHORT      |           80 |       0.4      |            0.323924 |       -8.60632 |        -0.0666989  |         -0.0671841 |                 0.372093 |                 0.153846  |              2 | False           |
| ETHUSDT_5m_RANGE_BB_RSI_SHORT      |           71 |       0.422535 |            0.286266 |      -15.8238  |        -0.106614   |         -0.102907  |                 0.307692 |                 0.0769231 |              2 | False           |

## Tệp kết quả

- `data_audit.csv`
- `candidate_summary.csv`
- `top_candidates.csv`
- `period_pnl_top10.csv`
- `top_candidate_trades.parquet`
- `research_summary.json`
- `latest_run.json`