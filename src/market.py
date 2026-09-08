"""Market data providers behind a stable public interface."""

from __future__ import annotations

from io import StringIO
from datetime import timezone

import httpx
import pandas as pd

from config import settings


ETF_SYMBOLS = {"QQQ", "SPY"}


def _get_csv(url: str) -> pd.DataFrame:
    response = httpx.get(url, timeout=settings.http_timeout, follow_redirects=True)
    response.raise_for_status()
    if not response.text.strip():
        raise ValueError(f"Empty response from data provider: {url}")
    return pd.read_csv(StringIO(response.text))


def _clean_market(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    frame = frame.rename(columns={c: c.strip().lower() for c in frame.columns})
    if "date" not in frame or "close" not in frame:
        raise ValueError(f"Market response for {symbol} is missing date/close columns")
    for column in ("open", "high", "low", "close", "volume"):
        if column not in frame:
            frame[column] = pd.NA
        values = frame[column].astype("string").str.replace(r"[$,]", "", regex=True)
        frame[column] = pd.to_numeric(values, errors="coerce")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["symbol"] = symbol.upper()
    return (frame.dropna(subset=["date", "close"])
            .drop_duplicates(subset=["date"], keep="last")
            .sort_values("date")
            .loc[:, ["date", "symbol", "open", "high", "low", "close", "volume"]])


def _fetch_yahoo(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    period1 = int(start.tz_localize(timezone.utc).timestamp())
    # Yahoo treats period2 as exclusive, so include the requested end date.
    period2 = int((end + pd.Timedelta(days=1)).tz_localize(timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    response = httpx.get(
        url,
        params={"period1": period1, "period2": period2, "interval": "1d", "events": "history"},
        timeout=settings.http_timeout,
        follow_redirects=True,
        headers={"User-Agent": "investment-score/0.1"},
    )
    response.raise_for_status()
    payload = response.json()
    result = payload.get("chart", {}).get("result")
    if not result:
        error = payload.get("chart", {}).get("error")
        raise ValueError(f"Yahoo returned no data for {symbol}: {error}")
    data = result[0]
    timestamps = data.get("timestamp", [])
    quotes = data.get("indicators", {}).get("quote", [{}])[0]
    frame = pd.DataFrame({"date": pd.to_datetime(timestamps, unit="s", utc=True).date})
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = quotes.get(column, [None] * len(frame))
    return _clean_market(frame, symbol)


def _fetch_nasdaq(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    url = f"https://api.nasdaq.com/api/quote/{symbol}/historical"
    response = httpx.get(
        url,
        params={"assetclass": "etf", "fromdate": start.strftime("%Y-%m-%d"),
                "todate": end.strftime("%Y-%m-%d"), "limit": 5000},
        timeout=settings.http_timeout,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json, text/plain, */*",
                 "Referer": "https://www.nasdaq.com/"},
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or {}
    rows = (data.get("tradesTable") or {}).get("rows")
    if not rows:
        raise ValueError(f"Nasdaq returned no data for {symbol}: {payload.get('status')}")
    return _clean_market(pd.DataFrame(rows), symbol)


def fetch_market_history(symbol: str, start_date: str, end_date: str | None = None) -> pd.DataFrame:
    """Fetch daily QQQ/SPY from the configured provider and VIX from FRED."""
    symbol = symbol.upper()
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date or pd.Timestamp.today().date())
    if start > end:
        raise ValueError("start_date must not be after end_date")

    if symbol in ETF_SYMBOLS:
        if settings.market_data_provider == "yahoo":
            return _fetch_yahoo(symbol, start, end)
        if settings.market_data_provider != "nasdaq":
            raise ValueError(f"Unsupported MARKET_DATA_PROVIDER: {settings.market_data_provider}")
        return _fetch_nasdaq(symbol, start, end)
    if symbol == "VIX":
        url = ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS"
               + "&cosd=" + start.strftime("%Y-%m-%d")
               + "&coed=" + end.strftime("%Y-%m-%d"))
        frame = _get_csv(url).rename(columns={"DATE": "date", "observation_date": "date", "VIXCLS": "close"})
        return _clean_market(frame, symbol)
    raise ValueError(f"Unsupported market symbol: {symbol}")
