"""FRED-based US Treasury yield data provider."""

from __future__ import annotations

from io import StringIO

import httpx
import pandas as pd

from config import settings


FRED_SERIES = {"US10Y": "DGS10", "US2Y": "DGS2"}


def fetch_macro_history(series: str, start_date: str, end_date: str | None = None) -> pd.DataFrame:
    series = series.upper()
    if series not in FRED_SERIES:
        raise ValueError(f"Unsupported macro series: {series}")
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date or pd.Timestamp.today().date())
    if start > end:
        raise ValueError("start_date must not be after end_date")
    fred_id = FRED_SERIES[series]
    url = (f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"
           f"&cosd={start:%Y-%m-%d}&coed={end:%Y-%m-%d}")
    response = httpx.get(url, timeout=settings.http_timeout, follow_redirects=True)
    response.raise_for_status()
    frame = pd.read_csv(StringIO(response.text))
    frame = frame.rename(columns={"DATE": "date", "observation_date": "date", fred_id: "value"})
    if "date" not in frame or "value" not in frame:
        raise ValueError(f"FRED response for {series} is missing date/value columns")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["value"] = pd.to_numeric(frame["value"].replace({".": pd.NA, "N/A": pd.NA}), errors="coerce")
    frame["series"] = series
    return (frame.dropna(subset=["date", "value"])
            .drop_duplicates(subset=["date"], keep="last")
            .sort_values("date")
            .loc[:, ["date", "series", "value"]])
