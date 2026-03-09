from __future__ import annotations
import json
from datetime import datetime, timezone

import pandas as pd

from db import init_db, get_conn
from data_provider import fetch_daily_bars
from analytics import compute_indicators, score_from_latest

DEFAULT_SYMBOLS = ["AAPL", "MSFT", "NVDA", "SPY", "JPM"]

def upsert_price(symbol: str, df: pd.DataFrame) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT INTO price_bars_daily(symbol, date, open, high, low, close, volume)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, date) DO UPDATE SET
              open=excluded.open, high=excluded.high, low=excluded.low,
              close=excluded.close, volume=excluded.volume
            """,
            [
                (symbol, r["date"], float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["volume"]))
                for _, r in df.iterrows()
            ],
        )

def load_price(symbol: str) -> pd.DataFrame:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM price_bars_daily WHERE symbol=? ORDER BY date",
            (symbol,),
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=["date","open","high","low","close","volume"])
    return pd.DataFrame([dict(r) for r in rows])

def upsert_indicators(symbol: str, df: pd.DataFrame) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT INTO indicators_daily(symbol, date, ma20, ma60, rsi14, vol20)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, date) DO UPDATE SET
              ma20=excluded.ma20, ma60=excluded.ma60, rsi14=excluded.rsi14, vol20=excluded.vol20
            """,
            [
                (
                    symbol,
                    r["date"],
                    None if pd.isna(r["ma20"]) else float(r["ma20"]),
                    None if pd.isna(r["ma60"]) else float(r["ma60"]),
                    None if pd.isna(r["rsi14"]) else float(r["rsi14"]),
                    None if pd.isna(r["vol20"]) else float(r["vol20"]),
                )
                for _, r in df.iterrows()
            ],
        )

def load_latest_indicator_row(symbol: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT date, ma20, ma60, rsi14, vol20
            FROM indicators_daily
            WHERE symbol=?
            ORDER BY date DESC
            LIMIT 1
            """,
            (symbol,),
        ).fetchone()
    return dict(row) if row else None

def upsert_score(symbol: str, score: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO score_snapshot(
              symbol, asof_date, score_total, reco, confidence,
              subscores_json, evidence_json, caveats_json
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, asof_date) DO UPDATE SET
              score_total=excluded.score_total,
              reco=excluded.reco,
              confidence=excluded.confidence,
              subscores_json=excluded.subscores_json,
              evidence_json=excluded.evidence_json,
              caveats_json=excluded.caveats_json
            """,
            (
                symbol,
                score["asof_date"],
                score["score_total"],
                score["reco"],
                score["confidence"],
                score["subscores_json"],
                score["evidence_json"],
                score["caveats_json"],
            ),
        )

def refresh_symbol(symbol: str) -> None:
    df = fetch_daily_bars(symbol, years=2)
    if df.empty:
        print(f"[WARN] no data for {symbol}")
        return

    upsert_price(symbol, df)

    price_df = load_price(symbol)
    ind_df = compute_indicators(price_df)
    upsert_indicators(symbol, ind_df[["date","ma20","ma60","rsi14","vol20"]])

    latest = load_latest_indicator_row(symbol)
    if latest:
        score = score_from_latest(latest)
        upsert_score(symbol, score)
        print(f"[OK] {symbol} asof={score['asof_date']} score={score['score_total']:.1f} reco={score['reco']}")

def main(symbols: list[str] | None = None) -> None:
    init_db()
    syms = symbols or DEFAULT_SYMBOLS
    print(f"Refresh start: {datetime.now(timezone.utc).isoformat()} symbols={syms}")
    for s in syms:
        refresh_symbol(s.strip().upper())
    print("Refresh done.")

if __name__ == "__main__":
    main()