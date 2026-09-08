"""Small sqlite3 persistence layer for market, macro and score data."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd

from config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS market_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL NOT NULL,
    volume REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_market_symbol_date
ON market_daily(symbol, date);

CREATE TABLE IF NOT EXISTS macro_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    series TEXT NOT NULL,
    value REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(series, date)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_macro_series_date
ON macro_daily(series, date);

CREATE TABLE IF NOT EXISTS investment_score (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trend_score REAL NOT NULL,
    drawdown_score REAL NOT NULL,
    risk_score REAL NOT NULL,
    macro_score REAL NOT NULL,
    total_score REAL NOT NULL,
    market_state TEXT NOT NULL,
    signal TEXT NOT NULL,
    close REAL,
    drawdown REAL,
    vix REAL,
    us10y REAL,
    us2y REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, date)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_score_symbol_date
ON investment_score(symbol, date);
"""


def _db_path(db_path: str | Path | None = None) -> Path:
    return Path(db_path) if db_path is not None else settings.resolved_database_path()


@contextmanager
def connect(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db(db_path: str | Path | None = None) -> Path:
    path = _db_path(db_path)
    with connect(path) as connection:
        connection.executescript(SCHEMA)
    return path


def _records(frame: pd.DataFrame, columns: list[str]) -> list[tuple]:
    clean = frame.loc[:, columns].copy()
    clean = clean.astype(object).where(pd.notna(clean), None)
    return list(clean.itertuples(index=False, name=None))


def upsert_market_daily(frame: pd.DataFrame, db_path: str | Path | None = None) -> int:
    columns = ["date", "symbol", "open", "high", "low", "close", "volume"]
    rows = _records(frame, columns)
    if not rows:
        return 0
    sql = """
        INSERT INTO market_daily(date, symbol, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol, date) DO UPDATE SET
            open=excluded.open, high=excluded.high, low=excluded.low,
            close=excluded.close, volume=excluded.volume,
            updated_at=CURRENT_TIMESTAMP
    """
    with connect(db_path) as connection:
        connection.executemany(sql, rows)
    return len(rows)


def upsert_macro_daily(frame: pd.DataFrame, db_path: str | Path | None = None) -> int:
    rows = _records(frame, ["date", "series", "value"])
    if not rows:
        return 0
    sql = """
        INSERT INTO macro_daily(date, series, value) VALUES (?, ?, ?)
        ON CONFLICT(series, date) DO UPDATE SET
            value=excluded.value, updated_at=CURRENT_TIMESTAMP
    """
    with connect(db_path) as connection:
        connection.executemany(sql, rows)
    return len(rows)


def upsert_score(frame: pd.DataFrame, db_path: str | Path | None = None) -> int:
    columns = ["date", "symbol", "trend_score", "drawdown_score", "risk_score",
               "macro_score", "total_score", "market_state", "signal", "close",
               "drawdown", "vix", "us10y", "us2y"]
    rows = _records(frame, columns)
    if not rows:
        return 0
    placeholders = ",".join("?" for _ in columns)
    updates = ",".join(f"{c}=excluded.{c}" for c in columns if c not in {"date", "symbol"})
    sql = (f"INSERT INTO investment_score({','.join(columns)}) VALUES ({placeholders}) "
           f"ON CONFLICT(symbol, date) DO UPDATE SET {updates}, updated_at=CURRENT_TIMESTAMP")
    with connect(db_path) as connection:
        connection.executemany(sql, rows)
    return len(rows)


def get_market_data(symbol: str, db_path: str | Path | None = None) -> pd.DataFrame:
    with connect(db_path) as connection:
        return pd.read_sql_query(
            "SELECT date, symbol, open, high, low, close, volume FROM market_daily "
            "WHERE symbol=? ORDER BY date", connection, params=(symbol.upper(),)
        )


def get_macro_data(series: str, db_path: str | Path | None = None) -> pd.DataFrame:
    with connect(db_path) as connection:
        return pd.read_sql_query(
            "SELECT date, series, value FROM macro_daily WHERE series=? ORDER BY date",
            connection, params=(series.upper(),)
        )


def get_score_data(symbol: str, db_path: str | Path | None = None) -> pd.DataFrame:
    with connect(db_path) as connection:
        return pd.read_sql_query(
            "SELECT * FROM investment_score WHERE symbol=? ORDER BY date",
            connection, params=(symbol.upper(),)
        )


def get_last_date(kind: str, name: str, db_path: str | Path | None = None) -> str | None:
    if kind not in {"market", "macro"}:
        raise ValueError("kind must be 'market' or 'macro'")
    table, column = ("market_daily", "symbol") if kind == "market" else ("macro_daily", "series")
    with connect(db_path) as connection:
        row = connection.execute(
            f"SELECT MAX(date) AS last_date FROM {table} WHERE {column}=?", (name.upper(),)
        ).fetchone()
    return row["last_date"] if row else None
