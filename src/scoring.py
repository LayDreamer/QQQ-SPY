"""Pure scoring rules and historical score calculation."""

from __future__ import annotations

import math

import pandas as pd

from src.signals import (
    calculate_confirmation_count,
    get_market_state,
    get_signal,
    is_long_term_trend_broken,
)


def _finite(*values: float) -> bool:
    return all(v is not None and math.isfinite(float(v)) for v in values)


def calculate_trend_score(row) -> int:
    required = [row[k] for k in ("close", "ma20", "ma50", "ma100", "ma200",
                                  "momentum20", "momentum60", "momentum120")]
    if not _finite(*required):
        raise ValueError("Incomplete trend inputs")
    score = 0
    score += 4 if row["close"] > row["ma20"] else 0
    score += 5 if row["close"] > row["ma50"] else 0
    score += 5 if row["close"] > row["ma100"] else 0
    score += 6 if row["close"] > row["ma200"] else 0
    score += 2 if row["ma20"] > row["ma50"] else 0
    score += 2 if row["ma50"] > row["ma100"] else 0
    score += 3 if row["ma100"] > row["ma200"] else 0
    score += 2 if row["momentum20"] > 0 else 0
    score += 3 if row["momentum60"] > 0 else 0
    score += 3 if row["momentum120"] > 0 else 0
    return score


def calculate_drawdown_score(drawdown: float) -> int:
    if not _finite(drawdown):
        raise ValueError("Incomplete drawdown input")
    if drawdown > -0.03:
        return 0
    if drawdown > -0.05:
        return 3
    if drawdown > -0.08:
        return 6
    if drawdown > -0.10:
        return 9
    if drawdown > -0.12:
        return 12
    if drawdown > -0.15:
        return 16
    if drawdown > -0.20:
        return 20
    return 25


def calculate_risk_score(vix: float, vix_ma5: float, vix_ma20: float) -> int:
    if not _finite(vix, vix_ma5, vix_ma20):
        raise ValueError("Incomplete VIX inputs")
    if vix < 15:
        score = 2
    elif vix < 18:
        score = 4
    elif vix < 20:
        score = 6
    elif vix < 25:
        score = 10
    elif vix < 30:
        score = 14
    elif vix < 40:
        score = 17
    else:
        score = 20
    if vix > 25 and vix_ma5 < vix_ma20:
        score += 1
    return min(score, 20)


def calculate_macro_score(us10y: float, us10y_ma20: float, us10y_ma60: float,
                          us2y: float, us2y_ma20: float, us2y_ma60: float) -> int:
    if not _finite(us10y, us10y_ma20, us10y_ma60, us2y, us2y_ma20, us2y_ma60):
        raise ValueError("Incomplete yield inputs")
    if us10y >= 5.0:
        level = 0
    elif us10y >= 4.5:
        level = 1
    elif us10y >= 4.0:
        level = 3
    elif us10y >= 3.5:
        level = 5
    elif us10y >= 3.0:
        level = 6
    else:
        level = 8
    trend10 = (2 if us10y < us10y_ma20 else 0) + (3 if us10y_ma20 < us10y_ma60 else 0)
    trend2 = (1 if us2y < us2y_ma20 else 0) + (2 if us2y_ma20 < us2y_ma60 else 0)
    spread = us10y - us2y
    spread_score = 4 if spread > 0.50 else 3 if spread > 0 else 2 if spread > -0.50 else 0
    return level + trend10 + trend2 + spread_score


def calculate_total_score(trend_score: float, drawdown_score: float,
                          risk_score: float, macro_score: float) -> float:
    total = float(trend_score + drawdown_score + risk_score + macro_score)
    if not 0 <= total <= 100:
        raise ValueError("Calculated total score is outside 0..100")
    return round(total, 1)


REQUIRED_COLUMNS = ["date", "symbol", "close", "ma20", "ma50", "ma100", "ma200",
                    "momentum20", "momentum60", "momentum120", "drawdown",
                    "vix", "vix_ma5", "vix_ma20", "us10y", "us10y_ma20",
                    "us10y_ma60", "us2y", "us2y_ma20", "us2y_ma60"]


def calculate_score_frame(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(REQUIRED_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing score columns: {sorted(missing)}")
    valid = frame.dropna(subset=REQUIRED_COLUMNS).copy()
    records = []
    for _, row in valid.iterrows():
        trend = calculate_trend_score(row)
        drawdown = calculate_drawdown_score(row["drawdown"])
        risk = calculate_risk_score(row["vix"], row["vix_ma5"], row["vix_ma20"])
        macro = calculate_macro_score(row["us10y"], row["us10y_ma20"], row["us10y_ma60"],
                                      row["us2y"], row["us2y_ma20"], row["us2y_ma60"])
        total = calculate_total_score(trend, drawdown, risk, macro)
        confirmations = calculate_confirmation_count(
            close=row["close"], ma20=row["ma20"], momentum20=row["momentum20"],
            vix_ma5=row["vix_ma5"], vix_ma20=row["vix_ma20"],
            us10y=row["us10y"], us10y_ma20=row["us10y_ma20"])
        broken = is_long_term_trend_broken(
            close=row["close"], ma200=row["ma200"], momentum60=row["momentum60"],
            momentum120=row["momentum120"])
        records.append({
            "date": pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
            "symbol": str(row["symbol"]).upper(), "trend_score": trend,
            "drawdown_score": drawdown, "risk_score": risk, "macro_score": macro,
            "total_score": total, "market_state": get_market_state(total),
            "signal": get_signal(total, confirmations, broken), "close": float(row["close"]),
            "drawdown": float(row["drawdown"]), "vix": float(row["vix"]),
            "us10y": float(row["us10y"]), "us2y": float(row["us2y"]),
        })
    return pd.DataFrame.from_records(records)
