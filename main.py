"""Command-line entry point for Investment Score V0.1."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from config import BASE_DIR, settings
from database import (
    get_last_date,
    get_macro_data,
    get_market_data,
    get_score_data,
    init_db,
    upsert_macro_daily,
    upsert_market_daily,
    upsert_score,
)
from src.backtest import run_backtest
from src.indicators import align_inputs
from src.macro import fetch_macro_history
from src.market import fetch_market_history
from src.report import generate_daily_report
from src.scoring import calculate_score_frame


LOG = logging.getLogger("investment-score")
MARKET_SYMBOLS = ("QQQ", "SPY", "VIX")
MACRO_SERIES = ("US10Y", "US2Y")


def _validate_date(value: str) -> str:
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except Exception as exc:
        raise argparse.ArgumentTypeError(f"Invalid date: {value}") from exc


def _incremental_start(kind: str, name: str, explicit_start: str | None) -> str:
    if explicit_start:
        return explicit_start
    last = get_last_date(kind, name)
    if not last:
        return settings.default_start_date
    return (date.fromisoformat(str(last)) - timedelta(days=5)).isoformat()


def sync_data(start: str | None = None) -> bool:
    init_db()
    failures: list[str] = []
    end = date.today().isoformat()
    for symbol in MARKET_SYMBOLS:
        fetch_start = _incremental_start("market", symbol, start)
        try:
            LOG.info("Fetching %s from %s to %s", symbol, fetch_start, end)
            frame = fetch_market_history(symbol, fetch_start, end)
            if frame.empty:
                raise ValueError("provider returned no usable rows")
            count = upsert_market_daily(frame)
            LOG.info("Stored %s rows for %s", count, symbol)
        except Exception as exc:
            failures.append(symbol)
            LOG.exception("Failed to sync %s: %s", symbol, exc)
    for series in MACRO_SERIES:
        fetch_start = _incremental_start("macro", series, start)
        try:
            LOG.info("Fetching %s from %s to %s", series, fetch_start, end)
            frame = fetch_macro_history(series, fetch_start, end)
            if frame.empty:
                raise ValueError("provider returned no usable rows")
            count = upsert_macro_daily(frame)
            LOG.info("Stored %s rows for %s", count, series)
        except Exception as exc:
            failures.append(series)
            LOG.exception("Failed to sync %s: %s", series, exc)
    if failures:
        LOG.error("Sync incomplete; failed series: %s", ", ".join(failures))
        return False
    return True


def calculate_symbol_scores(symbol: str) -> pd.DataFrame:
    price = get_market_data(symbol)
    vix = get_market_data("VIX")
    us10y = get_macro_data("US10Y")
    us2y = get_macro_data("US2Y")
    missing = [name for name, frame in ((symbol, price), ("VIX", vix),
                                         ("US10Y", us10y), ("US2Y", us2y)) if frame.empty]
    if missing:
        raise RuntimeError("Missing required data: " + ", ".join(missing))
    scores = calculate_score_frame(align_inputs(price, vix, us10y, us2y))
    if scores.empty:
        raise RuntimeError(f"No calculable score rows for {symbol}; at least 252 trading days are required")
    upsert_score(scores)
    LOG.info("Calculated %s scores for %s; latest=%s score=%.0f signal=%s",
             len(scores), symbol, scores.iloc[-1]["date"], scores.iloc[-1]["total_score"],
             scores.iloc[-1]["signal"])
    return scores


def _select_row(scores: pd.DataFrame, requested_date: str | None) -> pd.Series:
    if requested_date:
        candidates = scores.loc[scores["date"] <= requested_date]
        if candidates.empty:
            raise RuntimeError(f"No calculable trading date on or before {requested_date}")
        return candidates.iloc[-1]
    return scores.iloc[-1]


def print_score(row: pd.Series) -> None:
    print(f"\n{row['symbol']}  {row['date']}")
    print(f"Close: {row['close']:.2f}")
    print(f"Score: {row['total_score']:.0f} / 100")
    print(f"State: {row['market_state']}")
    print(f"Signal: {row['signal']}")
    print(f"Trend {row['trend_score']:.0f}/35 | Drawdown {row['drawdown_score']:.0f}/25 | "
          f"Risk {row['risk_score']:.0f}/20 | Macro {row['macro_score']:.0f}/20")
    print(f"Drawdown {row['drawdown']:.1%} | VIX {row['vix']:.2f} | "
          f"US10Y {row['us10y']:.2f}% | US2Y {row['us2y']:.2f}%")


def score_command(symbol: str | None = None, requested_date: str | None = None) -> pd.DataFrame:
    symbols = (symbol.upper(),) if symbol else ("QQQ", "SPY")
    selected = []
    for item in symbols:
        if item not in {"QQQ", "SPY"}:
            raise ValueError("score symbol must be QQQ or SPY")
        scores = calculate_symbol_scores(item)
        row = _select_row(scores, requested_date)
        print_score(row)
        selected.append(row)
    return pd.DataFrame(selected).reset_index(drop=True)


def backtest_command(symbol: str | None = None) -> None:
    symbols = (symbol.upper(),) if symbol else ("QQQ", "SPY")
    summaries = []
    for item in symbols:
        scores = get_score_data(item)
        if scores.empty:
            scores = calculate_symbol_scores(item)
        _, summary, benchmark = run_backtest(
            scores, item, BASE_DIR / "output/backtest", benchmark_frame=get_market_data(item))
        summaries.append(summary)
        print(f"{item} buy & hold: CAGR={benchmark['cagr']:.2%}, "
              f"Max Drawdown={benchmark['max_drawdown']:.2%}")
    combined = pd.concat(summaries, ignore_index=True)
    output = BASE_DIR / "output/backtest"
    output.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output / "summary.csv", index=False)
    print(combined.to_string(index=False))
    print(f"\nBacktest files: {output}")


def daily_command() -> None:
    if not sync_data():
        raise RuntimeError("Daily stopped because one or more required data sources failed")
    selected = score_command()
    path = generate_daily_report(selected, BASE_DIR / "output/reports")
    print(f"\nDaily report: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Investment Score V0.1")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Initialize the SQLite database")
    sync = sub.add_parser("sync", help="Incrementally synchronize market and macro data")
    sync.add_argument("--start", type=_validate_date)
    score = sub.add_parser("score", help="Calculate historical and latest scores")
    score.add_argument("--symbol", choices=("QQQ", "SPY"), type=str.upper)
    score.add_argument("--date", type=_validate_date)
    backtest = sub.add_parser("backtest", help="Run threshold forward-return analysis")
    backtest.add_argument("--symbol", choices=("QQQ", "SPY"), type=str.upper)
    sub.add_parser("daily", help="Sync, score and generate the daily report")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            print(f"Database initialized: {init_db()}")
        elif args.command == "sync":
            return 0 if sync_data(args.start) else 1
        elif args.command == "score":
            score_command(args.symbol, args.date)
        elif args.command == "backtest":
            backtest_command(args.symbol)
        elif args.command == "daily":
            daily_command()
        return 0
    except Exception as exc:
        LOG.exception("Command failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
