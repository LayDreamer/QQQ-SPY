"""Minimal threshold/forward-return analysis for historical scores."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


HORIZONS = (20, 60, 120, 250)
THRESHOLDS = (60, 70, 75, 80, 85, 90)


def add_forward_returns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.sort_values("date").reset_index(drop=True).copy()
    close = pd.to_numeric(result["close"], errors="coerce")
    for days in HORIZONS:
        result[f"forward_{days}d"] = close.shift(-days) / close - 1
    return result


def summarize_thresholds(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    rows = []
    for threshold in THRESHOLDS:
        group = frame.loc[frame["total_score"] >= threshold]
        row = {"symbol": symbol.upper(), "threshold": threshold, "count": len(group)}
        for days in HORIZONS:
            returns = group[f"forward_{days}d"].dropna()
            row[f"avg_{days}d"] = returns.mean() if len(returns) else np.nan
            row[f"median_{days}d"] = returns.median() if len(returns) else np.nan
            row[f"win_rate_{days}d"] = (returns > 0).mean() if len(returns) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def buy_and_hold_metrics(frame: pd.DataFrame) -> dict[str, float]:
    data = frame.dropna(subset=["date", "close"]).sort_values("date")
    if len(data) < 2:
        return {"cagr": float("nan"), "max_drawdown": float("nan")}
    dates = pd.to_datetime(data["date"])
    years = (dates.iloc[-1] - dates.iloc[0]).days / 365.2425
    cagr = (float(data["close"].iloc[-1]) / float(data["close"].iloc[0])) ** (1 / years) - 1
    drawdown = data["close"] / data["close"].cummax() - 1
    return {"cagr": cagr, "max_drawdown": float(drawdown.min())}


def run_backtest(score_frame: pd.DataFrame, symbol: str,
                 output_dir: str | Path = "output/backtest",
                 benchmark_frame: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    detailed = add_forward_returns(score_frame)
    summary = summarize_thresholds(detailed, symbol)
    benchmark = buy_and_hold_metrics(benchmark_frame if benchmark_frame is not None else detailed)
    detailed.to_csv(output / f"{symbol.upper()}_backtest.csv", index=False)
    return detailed, summary, benchmark
