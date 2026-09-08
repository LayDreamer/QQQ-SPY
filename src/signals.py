"""Market-state and signal rules for Investment Score V0.1."""

from __future__ import annotations


def get_market_state(total_score: float) -> str:
    if not 0 <= total_score <= 100:
        raise ValueError("total_score must be between 0 and 100")
    if total_score < 40:
        return "RISK_OFF"
    if total_score < 55:
        return "CAUTIOUS"
    if total_score < 70:
        return "NORMAL"
    if total_score < 80:
        return "OPPORTUNITY"
    if total_score < 90:
        return "STRONG_OPPORTUNITY"
    return "EXTREME_OPPORTUNITY"


def calculate_confirmation_count(*, close: float, ma20: float, momentum20: float,
                                   vix_ma5: float, vix_ma20: float,
                                   us10y: float, us10y_ma20: float) -> int:
    return sum((
        close > ma20,
        momentum20 > 0,
        vix_ma5 < vix_ma20,
        us10y < us10y_ma20,
    ))


def is_long_term_trend_broken(*, close: float, ma200: float,
                              momentum60: float, momentum120: float) -> bool:
    return close < ma200 and momentum60 < 0 and momentum120 < 0


def get_signal(total_score: float, confirmation_count: int,
               long_term_trend_broken: bool = False) -> str:
    if total_score < 55:
        signal = "WAIT"
    elif total_score < 70:
        signal = "NORMAL"
    elif total_score < 80:
        signal = "BUY_1" if confirmation_count >= 1 else "NORMAL"
    elif total_score < 90:
        signal = "BUY_2" if confirmation_count >= 2 else "BUY_1"
    else:
        signal = "BUY_3" if confirmation_count >= 2 else "BUY_2"
    if signal == "BUY_3" and long_term_trend_broken:
        return "BUY_2"
    return signal
