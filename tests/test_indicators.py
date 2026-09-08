import pandas as pd
import pytest

from src.indicators import add_price_indicators, align_inputs


def test_price_indicators_drawdown():
    frame = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=252),
                          "symbol": "QQQ", "close": [100.0] * 251 + [80.0]})
    result = add_price_indicators(frame)
    assert result.iloc[-1]["high252"] == 100
    assert result.iloc[-1]["drawdown"] == pytest.approx(-0.2)


def test_vix_alignment_does_not_backfill_future_value():
    dates = pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"])
    price = pd.DataFrame({"date": dates, "symbol": "QQQ", "close": [1, 2, 3]})
    vix = pd.DataFrame({"date": [dates[1]], "close": [20]})
    y10 = pd.DataFrame({"date": dates, "series": "US10Y", "value": [4, 4, 4]})
    y2 = pd.DataFrame({"date": dates, "series": "US2Y", "value": [3, 3, 3]})
    aligned = align_inputs(price, vix, y10, y2)
    assert pd.isna(aligned.iloc[0]["vix"])
    assert aligned.iloc[1]["vix"] == 20
    assert aligned.iloc[2]["vix"] == 20
