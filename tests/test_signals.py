from src.signals import get_signal


def test_buy_2_with_two_confirmations():
    assert get_signal(84, 2) == "BUY_2"


def test_buy_2_downgrades_with_one_confirmation():
    assert get_signal(84, 1) == "BUY_1"


def test_buy_3_is_protected_when_long_term_trend_is_broken():
    assert get_signal(93, 3, True) == "BUY_2"
