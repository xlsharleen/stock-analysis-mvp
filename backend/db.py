import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "mvp.db"

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS price_bars_daily (
            symbol TEXT NOT NULL,
            date   TEXT NOT NULL,
            open   REAL,
            high   REAL,
            low    REAL,
            close  REAL,
            volume REAL,
            PRIMARY KEY(symbol, date)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS indicators_daily (
            symbol TEXT NOT NULL,
            date   TEXT NOT NULL,
            ma20   REAL,
            ma60   REAL,
            rsi14  REAL,
            vol20  REAL,
            PRIMARY KEY(symbol, date)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS score_snapshot (
            symbol TEXT NOT NULL,
            asof_date TEXT NOT NULL,
            score_total REAL NOT NULL,
            reco TEXT NOT NULL,
            confidence REAL NOT NULL,
            subscores_json TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            caveats_json TEXT NOT NULL,
            PRIMARY KEY(symbol, asof_date)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_explain_cache (
            symbol TEXT NOT NULL,
            asof_date TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(symbol, asof_date)
        )
        """)