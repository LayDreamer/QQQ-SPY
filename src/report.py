"""Markdown daily report generation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def format_score_block(row: pd.Series) -> str:
    return f"""## {row['symbol']}

- Close: {row['close']:.2f}
- Score: {row['total_score']:.0f} / 100
- State: {row['market_state']}
- Signal: {row['signal']}
- Trend: {row['trend_score']:.0f} / 35
- Drawdown score: {row['drawdown_score']:.0f} / 25
- Risk: {row['risk_score']:.0f} / 20
- Macro: {row['macro_score']:.0f} / 20
- 52W drawdown: {row['drawdown']:.1%}
- VIX: {row['vix']:.2f}
- US10Y: {row['us10y']:.2f}%
- US2Y: {row['us2y']:.2f}%
"""


def generate_daily_report(scores: pd.DataFrame,
                          output_dir: str | Path = "output/reports") -> Path:
    if scores.empty:
        raise ValueError("Cannot generate a report without scores")
    report_date = str(scores["date"].max())
    selected = scores.loc[scores["date"] == report_date].sort_values("symbol")
    content = [f"# Investment Score V0.1 — {report_date}\n"]
    content.extend(format_score_block(row) for _, row in selected.iterrows())
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{report_date}.md"
    path.write_text("\n".join(content), encoding="utf-8")
    return path
