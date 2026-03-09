from __future__ import annotations
import datetime as dt
import pandas as pd
import yfinance as yf

def fetch_daily_bars(symbol: str, years: int = 2) -> pd.DataFrame:
    """
    Fetch daily OHLCV for a US symbol using yfinance.
    Returns DataFrame with columns: date, open, high, low, close, volume
    """
    end = dt.date.today()
    start = end - dt.timedelta(days=365 * years + 30)

    t = yf.Ticker(symbol)
    hist = t.history(start=str(start), end=str(end), interval="1d", auto_adjust=False)

    if hist is None or hist.empty:
        return pd.DataFrame(columns=["date","open","high","low","close","volume"])

    hist = hist.reset_index()

    # Normalize column names
    # yfinance uses "Date", "Open", "High", "Low", "Close", "Volume"
    hist["date"] = hist["Date"].dt.date.astype(str)
    out = pd.DataFrame({
        "date": hist["date"],
        "open": hist["Open"].astype(float),
        "high": hist["High"].astype(float),
        "low": hist["Low"].astype(float),
        "close": hist["Close"].astype(float),
        "volume": hist["Volume"].astype(float),
    })
    return out