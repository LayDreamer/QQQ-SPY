import pandas as pd

from database import get_market_data, init_db, upsert_market_daily


def test_market_upsert_is_idempotent_and_updates(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    row = pd.DataFrame([{
        "date": "2025-01-02", "symbol": "QQQ", "open": 99.0,
        "high": 101.0, "low": 98.0, "close": 100.0, "volume": 10.0,
    }])
    upsert_market_daily(row, db)
    row.loc[0, "close"] = 102.0
    upsert_market_daily(row, db)
    result = get_market_data("QQQ", db)
    assert len(result) == 1
    assert result.iloc[0]["close"] == 102.0
