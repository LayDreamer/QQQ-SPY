from types import SimpleNamespace

import pytest

from src.scoring import (
    calculate_drawdown_score,
    calculate_macro_score,
    calculate_risk_score,
    calculate_total_score,
    calculate_trend_score,
)


def test_drawdown_score_at_minus_twenty_percent():
    assert 80 / 100 - 1 == pytest.approx(-0.2)
    assert calculate_drawdown_score(-0.2) == 25


def test_maximum_trend_score():
    row = vars(SimpleNamespace(close=110, ma20=108, ma50=106, ma100=104, ma200=100,
                               momentum20=.01, momentum60=.02, momentum120=.03))
    assert calculate_trend_score(row) == 35


def test_risk_score_is_capped_at_twenty():
    assert calculate_risk_score(42, 35, 40) == 20


def test_maximum_macro_score():
    assert calculate_macro_score(2.5, 2.6, 2.7, 1.8, 1.9, 2.0) == 20


def test_maximum_total_score():
    assert calculate_total_score(35, 25, 20, 20) == 100
