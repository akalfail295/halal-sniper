"""نظام النقاط والإشارات. نفس الدالة تُستخدم بالفحص الحي وبالباك-تست."""
import logging
import re

import numpy as np
import pandas as pd

from . import data
from .config import DECISIONS
from .indicators import add_indicators, candle_flags, trend_template
from .universe import is_fund, sector_of

log = logging.getLogger("sniper.signals")

POS_WORDS = ["beat", "beats", "surge", "soar", "jump", "rally", "upgrade", "record", "raises",
             "raised", "strong", "growth", "buyback", "outperform", "bullish", "approval", "wins"]
NEG_WORDS = ["miss", "misses", "plunge", "plummet", "drop", "falls", "downgrade", "lawsuit", "probe",
             "recall", "cut", "cuts", "weak", "bearish", "investigation", "fraud", "layoff", "warns",
             "sink", "slump", "decline"]


def score_frame(d, rs_excess=None, htf_up=None):
    """يرجّع (النقاط، مكوّنات) لكل شمعة. rs_excess و htf_up إما Series أو قيمة واحدة أو None."""
    c = d["Close"]
    rsi = d["RSI"]
    hist = d["MACD_hist"]
    volr = d["VolRatio"]
    cflag, _ = candle_flags(d)

    s = pd.Series(0.0, index=d.index)
    s += np.where(c > d["SMA50"], 12, 0)
    s += np.where(d["SMA50"] > d["SMA200"], 10, 0)
    s += np.select([(rsi >= 50) & (rsi <= 70), (rsi >= 40) & (rsi < 50), rsi > 75, rsi < 30],
                   [12, 4, -8, -4], 0)
    s += np.where(hist > 0, 8, 0) + np.where(hist > hist.shift(1), 4, 0)
    s += np.select([volr >= 1.5, volr >= 1.0], [8, 4], 0)
    s += np.where(c > d["VWAP"], 8, 0)
    breakout = c > d["High20"]
    s += np.where(breakout, 10, 0)
    if rs_excess is not None:
        rs = rs_excess if isinstance(rs_excess, pd.Series) else pd.Series(rs_excess, index=d.index)
        s += np.select([rs > 0, rs < -5], [8, -4], 0)
    if htf_up is not None:
        hu = htf_up if isinstance(htf_up, pd.Series) else pd.Series(htf_up, index=d.index)
        s += np.select([hu == True, hu == False], [8, -8], 0)  # noqa: E712
    s += cflag * 4
    return s, {"breakout": breakout, "candle": cflag}


def classify(score, close, sma50, rsi, breakout, volr, tt, tt_min):
    """يحوّل النقاط لأولوية: 1 قوي جداً ... 5 تجنب. يعمل على قيم مفردة أو Series."""
    tt_ok = True if not tt_min else (tt >= tt_min)
    above = close > sma50
    strong = (score >= 72) & above & (rsi < 75) & (breakout | (volr >= 1.5)) & tt_ok
    buy = (score >= 60) & above & tt_ok
    return np.select([strong, buy, score >= 45, score >= 30], [1, 2, 3, 4], 5)


def news_sentiment(headlines):
    pos = neg = 0
    for hd in headlines:
        words = set(re.findall(r"[a-z]+", hd.get("title", "").lower()))
        pos += len(words & set(POS_WORDS))
        neg += len(words & set(NEG_WORDS))
    if pos - neg >= 2:
        return 1, "🟢 إيجابية"
    if neg - pos >= 2:
        return -1, "🔴 سلبية"
    return 0, "⚪ محايدة" if headlines else "-"


def _ret(series, n):
    if series is None or len(series) <= n:
        return None
    return float(series.iloc[-1] / series.iloc[-1 - n] - 1)


def rs_metrics(daily_close, spy_close):
    """القوة النسبية: فرق عائد 3 شهور عن SPY + نقاط ترتيب على طريقة IBD."""
    r63 = _ret(daily_close, 63)
    spy63 = _ret(spy_close, 63)
    excess = None if r63 is None or spy63 is None else (r63 - spy63) * 100
    parts = [(0.4, _ret(daily_close, 63)), (0.2, _ret(daily_close, 126)),
             (0.2, _ret(daily_close, 189)), (0.2, _ret(daily_close, 252))]
    parts = [(w, r) for w, r in parts if r is not None]
    score = sum(w * r for w, r in parts) / sum(w for w, _ in parts) if parts else None
    return excess, score


def rs_rank(scores):
    vals = {k: v for k, v in scores.items() if v is not None}
    if not vals:
        return {}
    ranked = pd.Series(vals).rank(pct=True)
    return {k: int(max(1, min(99, round(v * 99)))) for k, v in ranked.items()}


def htf_trend(daily, interval):
    """اتجاه الإطار الأكبر: إطار أكبر من إطار الفحص."""
    if daily is None or daily.empty:
        return None
    c = daily["Close"]
    if interval in data.INTRADAY:
        base, n = c, 50
    elif interval == "1d":
        base, n = c.resample("W-FRI").last().dropna(), 30
    elif interval == "1wk":
        base, n = c.resample("ME").last().dropna(), 10
    else:
        return None
    if len(base) < n:
        return None
    return bool(base.iloc[-1] > base.rolling(n).mean().iloc[-1])


def scan_asset(sym, a_type, mode, mkt, S, frame, daily, spy_close, with_news=True):
    """تحليل أصل واحد. frame = بيانات فاصل الفحص، daily = يومي سنتين (للقوة النسبية والإطار الأكبر)."""
    _, tf_name, _, interval, intraday = mode
    if frame is None or len(frame) < 60:
        return None
    try:
        d = add_indicators(frame, intraday=intraday)
        tt = trend_template(d)
        excess, rs_score = rs_metrics(daily["Close"] if daily is not None else None, spy_close)
        htf = htf_trend(daily, interval)
        score, comp = score_frame(d, rs_excess=excess, htf_up=htf)
        _, cname = candle_flags(d)
        last = d.iloc[-1]
        price = float(last["Close"])
        atr = float(last["ATR"]) if pd.notna(last["ATR"]) else 0.0
        if atr <= 0:
            return None

        total = float(score.iloc[-1])
        headlines, news_lbl = [], "-"
        earn_lbl, earn_days = "-", None
        if with_news:
            headlines = data.fetch_headlines(sym)
            ns, news_lbl = news_sentiment(headlines)
            total += {1: 4, -1: -8}.get(ns, 0)
            if not is_fund(sym):
                earn_days = data.days_to_earnings(sym)
                if earn_days is not None and earn_days <= 14:
                    earn_lbl = "📅 بعد " + str(earn_days) + " يوم"
                    if earn_days <= 3:
                        total -= 8
        total = max(0.0, min(100.0, total))

        tt_last = tt.iloc[-1]
        tt_val = int(tt_last) if pd.notna(tt_last) else None
        volr = float(last["VolRatio"]) if pd.notna(last["VolRatio"]) else 0.0
        rsi = float(last["RSI"]) if pd.notna(last["RSI"]) else 50.0
        prio = int(classify(total, price, float(last["SMA50"]) if pd.notna(last["SMA50"]) else price * 2,
                            rsi, bool(comp["breakout"].iloc[-1]), volr,
                            tt_val if tt_val is not None else 0, int(S.get("tt_min", 0))))
        decision = DECISIONS[prio]
        if prio <= 2 and not mkt.get("ok", True):
            prio = 3
            decision = DECISIONS[3] + " (السوق هابط)"

        prev_close = float(d["Close"].iloc[-2])
        stop_dist = S["atr_mult"] * atr
        return {
            "النوع": "صندوق" if a_type == "ETF" else "سهم",
            "الرمز": sym,
            "القطاع": sector_of(sym),
            "السعر": round(price, 2),
            "التغير %": round((price / prev_close - 1) * 100, 2) if prev_close else 0.0,
            "النقاط": int(round(total)),
            "الشمعة": cname.iloc[-1],
            "RSI": round(rsi, 1),
            "MACD": "🟢 صاعد" if last["MACD_hist"] > 0 else "🔴 هابط",
            "السيولة": "x" + format(volr, ".1f"),
            "VWAP": "🟢 فوق" if price > last["VWAP"] else "🔴 تحت",
            "اختراق": "✅" if comp["breakout"].iloc[-1] else "-",
            "قوة نسبية": "-" if excess is None else format(excess, "+.1f") + "%",
            "قالب الترند": "-" if tt_val is None else str(tt_val) + "/7",
            "الإطار الأكبر": "-" if htf is None else ("🟢 صاعد" if htf else "🔴 هابط"),
            "الأرباح": earn_lbl,
            "الأخبار": news_lbl,
            "وقف (ATR)": round(price - stop_dist, 2),
            "الهدف": round(price + S["rr"] * stop_dist, 2),
            "القرار": decision,
            "priority": prio,
            "score_num": int(round(total)),
            "raw_price": price,
            "atr": atr,
            "rs_score": rs_score,
            "headlines": headlines,
            "timeframe": tf_name,
            "interval": interval,
        }
    except Exception as e:
        log.warning("scan %s: %s", sym, e)
        return None


def run_scan(assets, mode, mkt, S, progress=None, with_news=True):
    """فحص قائمة أصول: تحميل جماعي ثم تحليل متوازي. يرجّع النتائج مرتبة."""
    from concurrent.futures import ThreadPoolExecutor

    _, _, period, interval, _ = mode
    syms = [s for s, _ in assets]
    types = dict(assets)
    p = progress or (lambda x: None)
    frames = data.fetch_many(syms, period, interval, progress=lambda x: p(0.45 * x))
    if interval == "1d" and period == "2y":
        dailies = frames
    else:
        dailies = data.fetch_many(syms, "2y", "1d", progress=lambda x: p(0.45 + 0.15 * x))
    spy = data.fetch_history("SPY", "2y", "1d")
    spy_close = None if spy is None or spy.empty else spy["Close"]

    results = []
    todo = [s for s in syms if s in frames]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(scan_asset, s, types[s], mode, mkt, S, frames.get(s), dailies.get(s),
                          spy_close, with_news) for s in todo]
        for i, f in enumerate(futs, 1):
            r = f.result()
            if r:
                results.append(r)
            p(0.6 + 0.4 * i / max(1, len(futs)))
    ranks = rs_rank({r["الرمز"]: r["rs_score"] for r in results})
    for r in results:
        rk = ranks.get(r["الرمز"])
        r["ترتيب RS"] = rk if rk is not None else None
    results.sort(key=lambda x: (x["priority"], -x["score_num"]))
    return results
