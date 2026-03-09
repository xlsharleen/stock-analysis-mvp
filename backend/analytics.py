from __future__ import annotations
import json
import numpy as np
import pandas as pd

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    df columns: date(str), open, high, low, close, volume
    returns df with ma20, ma60, rsi14, vol20
    """
    d = df.copy()
    d = d.sort_values("date").reset_index(drop=True)

    close = d["close"].astype(float)

    d["ma20"] = close.rolling(20, min_periods=20).mean()
    d["ma60"] = close.rolling(60, min_periods=60).mean()

    # RSI14
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.rolling(14, min_periods=14).mean()
    avg_loss = loss.rolling(14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    d["rsi14"] = 100 - (100 / (1 + rs))

    # VOL20: std of daily returns over 20 days
    ret = close.pct_change()
    d["vol20"] = ret.rolling(20, min_periods=20).std()

    return d

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def score_from_latest(ind_row: dict) -> dict:
    """
    ind_row contains: ma20, ma60, rsi14, vol20, date
    returns ScoreSnapshot fields (structured)
    """
    caveats = []
    evidence = []
    subscores = {}

    ma20 = ind_row.get("ma20")
    ma60 = ind_row.get("ma60")
    rsi14 = ind_row.get("rsi14")
    vol20 = ind_row.get("vol20")

    # trend 0-100
    if ma20 is None or ma60 is None:
        trend = 50.0
        caveats.append("MA 历史不足（需要至少 60 个交易日）。")
    else:
        # strength based on ratio
        ratio = (ma20 / ma60) - 1.0
        # map roughly: [-5%, +5%] -> [0, 100]
        trend = _clamp((ratio + 0.05) / 0.10 * 100.0, 0.0, 100.0)
        if ma20 > ma60:
            evidence.append(f"MA20({ma20:.2f}) > MA60({ma60:.2f})，趋势偏多。")
        else:
            evidence.append(f"MA20({ma20:.2f}) <= MA60({ma60:.2f})，趋势偏空/走弱。")
    subscores["trend"] = float(trend)

    # momentum 0-100 via RSI
    if rsi14 is None or np.isnan(rsi14):
        momentum = 50.0
        caveats.append("RSI 历史不足（需要至少 14 个交易日）。")
    else:
        # map: RSI 30->0, 70->100
        momentum = _clamp((float(rsi14) - 30.0) / 40.0 * 100.0, 0.0, 100.0)
        if rsi14 >= 60:
            evidence.append(f"RSI14={rsi14:.1f}，动量偏多。")
        elif rsi14 <= 40:
            evidence.append(f"RSI14={rsi14:.1f}，动量偏空。")
        else:
            evidence.append(f"RSI14={rsi14:.1f}，动量中性。")
    subscores["momentum"] = float(momentum)

    # risk: higher is better (lower vol)
    if vol20 is None or np.isnan(vol20):
        risk = 50.0
        caveats.append("VOL 历史不足（需要至少 20 个交易日）。")
    else:
        v = float(vol20)
        # map: 1% -> 90, 4% -> 10 (daily vol)
        risk = _clamp(100.0 - ((v - 0.01) / 0.03 * 80.0 + 10.0), 0.0, 100.0)
        evidence.append(f"VOL20={v*100:.2f}%（日收益波动），风险分={risk:.0f}。")
        if v >= 0.04:
            caveats.append("波动较高，建议降低仓位或等待信号确认。")
    subscores["risk"] = float(risk)

    # total
    score_total = 0.45 * trend + 0.45 * momentum + 0.10 * risk

    # reco
    if score_total >= 65:
        reco = "LONG"
    elif score_total <= 35:
        reco = "SHORT"
    else:
        reco = "NEUTRAL"

    # confidence: signal consistency
    conf = 0.5
    # trend direction
    trend_dir = None
    mom_dir = None
    if ma20 is not None and ma60 is not None:
        trend_dir = 1 if ma20 > ma60 else -1
    if rsi14 is not None and not np.isnan(rsi14):
        mom_dir = 1 if rsi14 >= 55 else (-1 if rsi14 <= 45 else 0)

    if trend_dir is not None and mom_dir is not None and mom_dir != 0 and trend_dir == mom_dir:
        conf += 0.2
    if vol20 is None or (isinstance(vol20, float) and np.isnan(vol20)):
        conf -= 0.2
    if ma20 is None or ma60 is None or rsi14 is None or (isinstance(rsi14, float) and np.isnan(rsi14)):
        conf -= 0.2
    if vol20 is not None and not np.isnan(vol20) and float(vol20) >= 0.04:
        conf -= 0.1
    confidence = _clamp(conf, 0.1, 0.9)

    # minimal caveat if empty
    if not caveats:
        caveats.append("信号基于日线指标，非实时；请结合自身风险承受能力。")

    return {
        "asof_date": ind_row["date"],
        "score_total": float(score_total),
        "reco": reco,
        "confidence": float(confidence),
        "subscores_json": json.dumps(subscores, ensure_ascii=False),
        "evidence_json": json.dumps(evidence[:6], ensure_ascii=False),
        "caveats_json": json.dumps(caveats[:6], ensure_ascii=False),
    }