import pandas as pd
import pytest

from src.backtest import add_forward_returns


def test_forward_return_direction():
    frame = pd.DataFrame({
        "date": pd.date_range("2025-01-01", periods=251),
        "close": [100.0] + [110.0] * 19 + [120.0] * 231,
    })
    result = add_forward_returns(frame)
    assert result.iloc[0]["forward_20d"] == pytest.approx(0.2)
