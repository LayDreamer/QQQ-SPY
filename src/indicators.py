"""Pure DataFrame transformations for price, volatility and yield indicators."""

from __future__ import annotations

import pandas as pd


def _sorted(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"])
    return result.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def add_price_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    result = _sorted(frame)
    close = pd.to_numeric(result["close"], errors="coerce")
    for window in (20, 50, 100, 200):
        result[f"ma{window}"] = close.rolling(window, min_periods=window).mean()
    for window in (20, 60, 120):
        result[f"momentum{window}"] = close / close.shift(window) - 1
    result["high252"] = close.rolling(252, min_periods=252).max()
    result["drawdown"] = close / result["high252"] - 1
    return result


def add_vix_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    result = _sorted(frame)
    value_column = "close" if "close" in result else "vix"
    values = pd.to_numeric(result[value_column], errors="coerce")
    result["vix"] = values
    result["vix_ma5"] = values.rolling(5, min_periods=5).mean()
    result["vix_ma20"] = values.rolling(20, min_periods=20).mean()
    return result


def add_yield_indicators(frame: pd.DataFrame, prefix: str | None = None) -> pd.DataFrame:
    result = _sorted(frame)
    value_column = "value" if "value" in result else (prefix or "yield")
    if prefix is None:
        if "series" not in result or result.empty:
            raise ValueError("prefix is required when series is unavailable")
        prefix = str(result["series"].iloc[0]).lower()
    values = pd.to_numeric(result[value_column], errors="coerce")
    result[prefix] = values
    result[f"{prefix}_ma20"] = values.rolling(20, min_periods=20).mean()
    result[f"{prefix}_ma60"] = values.rolling(60, min_periods=60).mean()
    return result


def align_inputs(price: pd.DataFrame, vix: pd.DataFrame, us10y: pd.DataFrame, us2y: pd.DataFrame) -> pd.DataFrame:
    """Align inputs to price trading dates without ever backfilling from the future."""
    base = add_price_indicators(price).set_index("date")
    vix_i = add_vix_indicators(vix).set_index("date")[["vix", "vix_ma5", "vix_ma20"]]
    y10 = add_yield_indicators(us10y, "us10y").set_index("date")[["us10y", "us10y_ma20", "us10y_ma60"]]
    y2 = add_yield_indicators(us2y, "us2y").set_index("date")[["us2y", "us2y_ma20", "us2y_ma60"]]

    # VIX may be carried for one asset trading day only; yields may be carried indefinitely.
    base = base.join(vix_i.reindex(base.index).ffill(limit=1))
    base = base.join(y10.reindex(base.index).ffill())
    base = base.join(y2.reindex(base.index).ffill())
    return base.reset_index()
