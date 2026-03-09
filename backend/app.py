from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from db import init_db, get_conn

load_dotenv()

app = FastAPI(title="Stock MVP")
from fastapi.middleware.cors import CORSMiddleware

# ... 之前的 app = FastAPI(title="Stock MVP") ...

# 添加 CORS 中间件配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（开发阶段最方便）
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有请求方式 (GET, POST 等)
    allow_headers=["*"],  # 允许所有请求头
)

# -------- simple in-memory cache (single process) ----------
CACHE: dict[str, tuple[float, object]] = {}
def cache_get(key: str, now_ts: float, ttl_sec: int):
    v = CACHE.get(key)
    if not v:
        return None
    ts, obj = v
    if now_ts - ts > ttl_sec:
        return None
    return obj

def cache_set(key: str, now_ts: float, obj: object):
    CACHE[key] = (now_ts, obj)

@app.on_event("startup")
def _startup():
    init_db()

# ----------------- models -----------------
class ExplainReq(BaseModel):
    symbol: str
    asof_date: Optional[str] = None

class StrategyReq(BaseModel):
    symbol: str
    question: str
    asof_date: Optional[str] = None
    constraints: Optional[dict] = None

# ----------------- DB helpers -----------------
def _get_latest_asof(symbol: str) -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT asof_date FROM score_snapshot WHERE symbol=? ORDER BY asof_date DESC LIMIT 1",
            (symbol,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"No score for {symbol}. Run refresh first.")
    return row["asof_date"]

def _get_score(symbol: str, asof_date: Optional[str] = None) -> dict:
    symbol = symbol.upper()
    if asof_date is None:
        asof_date = _get_latest_asof(symbol)
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT symbol, asof_date, score_total, reco, confidence,
                   subscores_json, evidence_json, caveats_json
            FROM score_snapshot
            WHERE symbol=? AND asof_date=?
            """,
            (symbol, asof_date),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"No score for {symbol} at {asof_date}")
    d = dict(row)
    d["subscores"] = json.loads(d.pop("subscores_json"))
    d["evidence"] = json.loads(d.pop("evidence_json"))
    d["caveats"] = json.loads(d.pop("caveats_json"))
    return d

# ----------------- REST -----------------
@app.get("/api/stock/{symbol}/price")
def get_price(symbol: str, start: Optional[str] = None, end: Optional[str] = None):
    symbol = symbol.upper()
    now_ts = datetime.now(timezone.utc).timestamp()
    key = f"price:{symbol}:{start}:{end}"
    cached = cache_get(key, now_ts, ttl_sec=600)
    if cached:
        return JSONResponse(cached)

    q = "SELECT date, open, high, low, close, volume FROM price_bars_daily WHERE symbol=?"
    params = [symbol]
    if start:
        q += " AND date>=?"
        params.append(start)
    if end:
        q += " AND date<=?"
        params.append(end)
    q += " ORDER BY date"

    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}. Run refresh first.")

    bars = [dict(r) for r in rows]
    resp = {"symbol": symbol, "bars": bars, "asof_date": bars[-1]["date"]}
    cache_set(key, now_ts, resp)
    return JSONResponse(resp)

@app.get("/api/stock/{symbol}/indicators")
def get_indicators(symbol: str, start: Optional[str] = None, end: Optional[str] = None):
    symbol = symbol.upper()
    now_ts = datetime.now(timezone.utc).timestamp()
    key = f"ind:{symbol}:{start}:{end}"
    cached = cache_get(key, now_ts, ttl_sec=600)
    if cached:
        return JSONResponse(cached)

    q = "SELECT date, ma20, ma60, rsi14, vol20 FROM indicators_daily WHERE symbol=?"
    params = [symbol]
    if start:
        q += " AND date>=?"
        params.append(start)
    if end:
        q += " AND date<=?"
        params.append(end)
    q += " ORDER BY date"

    with get_conn() as conn:
        rows = conn.execute(q, params).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No indicators for {symbol}. Run refresh first.")

    items = [dict(r) for r in rows]
    resp = {"symbol": symbol, "indicators": items, "asof_date": items[-1]["date"]}
    cache_set(key, now_ts, resp)
    return JSONResponse(resp)

@app.get("/api/stock/{symbol}/score")
def get_score(symbol: str, asof_date: Optional[str] = None):
    symbol = symbol.upper()
    now_ts = datetime.now(timezone.utc).timestamp()
    key = f"score:{symbol}:{asof_date}"
    cached = cache_get(key, now_ts, ttl_sec=300)
    if cached:
        return JSONResponse(cached)

    d = _get_score(symbol, asof_date)
    cache_set(key, now_ts, d)
    return JSONResponse(d)

# ----------------- AI explain (non-stream) -----------------
def _openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, None
    from openai import OpenAI
    return OpenAI(api_key=api_key), os.getenv("OPENAI_MODEL", "gpt-4o-mini")

@app.post("/api/ai/explain")
def ai_explain(req: ExplainReq):
    symbol = req.symbol.upper()
    asof = req.asof_date or _get_latest_asof(symbol)

    # cache in DB first (stable per symbol+asof)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT text FROM ai_explain_cache WHERE symbol=? AND asof_date=?",
            (symbol, asof),
        ).fetchone()
    if row:
        return {"symbol": symbol, "asof_date": asof, "explain_text": row["text"], "cached": True}

    snap = _get_score(symbol, asof)

    client, model = _openai_client()
    if client is None:
        # fallback (no key)
        text = (
            f"（未配置 OPENAI_API_KEY，返回占位解释）\n"
            f"- asof={asof} score={snap['score_total']:.1f} reco={snap['reco']} conf={snap['confidence']:.2f}\n"
            f"- 证据: " + "；".join(snap["evidence"][:3]) + "\n"
            f"- 风险: " + "；".join(snap["caveats"][:2])
        )
    else:
        prompt = {
            "symbol": symbol,
            "asof_date": asof,
            "score_total": snap["score_total"],
            "reco": snap["reco"],
            "confidence": snap["confidence"],
            "evidence": snap["evidence"],
            "caveats": snap["caveats"],
            "rules": [
                "只能基于给定 evidence/caveats 写解释，禁止编造实时价格或新闻。",
                "输出 3-6 条要点，每条尽量引用一个 evidence。",
                "若 confidence < 0.4 或 caveats 含“波动较高/历史不足”，语气更保守。"
            ],
        }

        rsp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是投资分析解释助手。只依据用户给的结构化证据输出简洁要点。"},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            temperature=0.2,
        )
        text = rsp.choices[0].message.content.strip()

    # write cache
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO ai_explain_cache(symbol, asof_date, text, created_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(symbol, asof_date) DO UPDATE SET text=excluded.text, created_at=excluded.created_at
            """,
            (symbol, asof, text, datetime.now(timezone.utc).isoformat()),
        )

    return {"symbol": symbol, "asof_date": asof, "explain_text": text, "cached": False}

# ----------------- AI strategy (SSE stream) -----------------
@app.post("/api/ai/strategy/stream")
def ai_strategy_stream(req: StrategyReq):
    symbol = req.symbol.upper()
    asof = req.asof_date or _get_latest_asof(symbol)
    snap = _get_score(symbol, asof)

    client, model = _openai_client()

    def sse_event(event: str, data: str) -> str:
        # SSE format: event: xxx \n data: yyy \n\n
        data = data.replace("\r", "").split("\n")
        payload = f"event: {event}\n" + "".join([f"data: {line}\n" for line in data]) + "\n"
        return payload

    def gen():
        # if no key: fake streaming
        if client is None:
            yield sse_event("token", "（未配置 OPENAI_API_KEY，返回占位策略）")
            yield sse_event("token", f"\n标的 {symbol} asof={asof} reco={snap['reco']} score={snap['score_total']:.1f}")
            yield sse_event("token", "\n\n入场：等待 MA20/MA60 确认 + RSI 回到 50 上方。")
            yield sse_event("token", "\n出场：跌破 MA60 或 RSI<45。")
            yield sse_event("token", "\n仓位：小仓位试探（例如 10–30% 资金），波动高则更低。")
            yield sse_event("token", "\n风控：止损 2–3 倍日波动；不确定时观望。")
            yield sse_event("done", json.dumps({"symbol": symbol, "asof_date": asof}))
            return

        prompt = {
            "symbol": symbol,
            "asof_date": asof,
            "question": req.question,
            "constraints": req.constraints or {},
            "score_total": snap["score_total"],
            "reco": snap["reco"],
            "confidence": snap["confidence"],
            "evidence": snap["evidence"],
            "caveats": snap["caveats"],
            "output_requirements": [
                "必须包含：thesis、entry_rules、exit_rules、position_sizing、risk_controls、invalidation。",
                "禁止编造未提供的数据（例如实时价格、新闻）。",
                "建议基于日线，给出可执行的规则表达（文字即可）。",
            ],
        }

        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是交易策略助手。只基于给定结构化快照给出可执行、保守、可验证的策略建议。"},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            temperature=0.2,
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield sse_event("token", delta.content)

        yield sse_event("done", json.dumps({"symbol": symbol, "asof_date": asof}))

    return StreamingResponse(gen(), media_type="text/event-stream")