"""الباك-تست اليومي: نفس قواعد الإشارة والتنفيذ الحي (وقف ATR متحرك، تعادل عند +1R، جني 50%)."""
import datetime

import numpy as np
import pandas as pd

from .indicators import add_indicators, trend_template
from .signals import classify, score_frame


def prepare(df, spy_close):
    """يحسب المؤشرات والنقاط والأولوية مرة وحدة لكل سهم (ما تعتمد على ATR/RR)."""
    d = add_indicators(df, intraday=False)
    d["TT"] = trend_template(d)
    c = d["Close"]
    rs = None
    spy_ok = pd.Series(True, index=d.index)
    if spy_close is not None and len(spy_close) > 200:
        spy = spy_close.reindex(spy_close.index.union(d.index)).ffill().reindex(d.index)
        spy_sma = spy_close.rolling(200).mean()
        spy_sma = spy_sma.reindex(spy_sma.index.union(d.index)).ffill().reindex(d.index)
        rs = ((c / c.shift(63) - 1) - (spy / spy.shift(63) - 1)) * 100
        spy_ok = (spy > spy_sma) | spy_sma.isna()
    score, comp = score_frame(d, rs_excess=rs, htf_up=c > d["SMA150"])
    d["Score"] = score
    d["Breakout"] = comp["breakout"]
    d["SpyOK"] = spy_ok
    return d


def signals_for(d, pmax, tt_min):
    prio = classify(d["Score"], d["Close"], d["SMA50"], d["RSI"], d["Breakout"],
                    d["VolRatio"].fillna(0), d["TT"], tt_min)
    return (prio <= pmax) & d["SpyOK"].values & d["ATR"].notna().values


def simulate(d, sig, S, hold, start_date=None):
    """محاكاة صفقات سهم واحد. الدخول على افتتاح الشمعة التالية للإشارة."""
    o, h, l, c = (d[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    atr = d["ATR"].to_numpy(float)
    idx = d.index
    slip = S["slippage_pct"] / 100.0
    comm = S["commission_pct"] / 100.0
    am, rr = S["atr_mult"], S["rr"]
    scale_out = bool(S.get("auto_scale_out", True))
    first = 1
    if start_date is not None:
        first = max(1, int(np.searchsorted(idx.values, np.datetime64(start_date))))

    trades, pos = [], None
    for i in range(first, len(d)):
        if pos is None:
            if not sig[i - 1] or not atr[i - 1] > 0:
                continue
            entry = o[i] * (1 + slip)
            sd = am * atr[i - 1]
            pos = {"i0": i, "entry": entry, "sd": sd, "sl": entry - sd, "tp": entry + rr * sd,
                   "ext": entry, "be": False, "half": False, "qty": 1.0, "realized": 0.0,
                   "fees": entry * comm}
        p = pos
        same_bar = i == p["i0"]
        exit_px = reason = None
        if l[i] <= p["sl"]:
            exit_px = p["sl"] if same_bar else min(o[i], p["sl"])
            reason = "stop"
        else:
            mid = p["entry"] + (p["tp"] - p["entry"]) / 2.0
            if scale_out and not p["half"] and h[i] >= mid:
                fill = (mid if same_bar else max(o[i], mid)) * (1 - slip)
                q = p["qty"] * 0.5
                p["realized"] += (fill - p["entry"]) * q - fill * q * comm
                p["qty"] -= q
                p["half"] = p["be"] = True
                p["sl"] = max(p["sl"], p["entry"])
            if h[i] >= p["tp"]:
                exit_px = p["tp"] if same_bar else max(o[i], p["tp"])
                reason = "target"
        held = i - p["i0"] + 1
        if exit_px is None and held >= hold:
            fill = c[i] * (1 - slip)
            r_now = (p["realized"] + (fill - p["entry"]) * p["qty"] - p["fees"]) / p["sd"]
            if r_now < 1.0 or held >= 3 * hold:
                exit_px, reason = c[i], "time"
        if exit_px is not None:
            fill = exit_px * (1 - slip)
            net = p["realized"] + (fill - p["entry"]) * p["qty"] - fill * p["qty"] * comm - p["fees"]
            trades.append({"entry_date": idx[p["i0"]], "exit_date": idx[i], "r": net / p["sd"],
                           "reason": reason, "bars": held, "half": p["half"]})
            pos = None
            continue
        p["ext"] = max(p["ext"], h[i])
        p["sl"] = max(p["sl"], p["ext"] - p["sd"])
        if not p["be"] and h[i] >= p["entry"] + p["sd"]:
            p["sl"] = max(p["sl"], p["entry"])
            p["be"] = True
    return trades


def collect_trades(prepared, S, pmax, hold, start_date=None):
    all_trades, per_sym = [], []
    for sym, d in prepared.items():
        if d is None or len(d) < 260:
            continue
        sig = signals_for(d, pmax, int(S.get("tt_min", 0)))
        trs = simulate(d, sig, S, hold, start_date)
        for t in trs:
            t["symbol"] = sym
        all_trades.extend(trs)
        if trs:
            rs = np.array([t["r"] for t in trs])
            per_sym.append({"الرمز": sym, "الصفقات": len(rs),
                            "نسبة الربح %": round(float((rs > 0).mean() * 100), 1),
                            "متوسط R": round(float(rs.mean()), 3),
                            "مجموع R": round(float(rs.sum()), 2)})
    return all_trades, per_sym


def stats(trades, risk_pct):
    if not trades:
        return None
    trs = sorted(trades, key=lambda t: t["exit_date"])
    rs = np.array([t["r"] for t in trs], dtype=float)
    gp, gl = rs[rs > 0].sum(), -rs[rs < 0].sum()
    eq = np.cumprod(1 + rs * risk_pct / 100.0)
    peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:]
    curve = pd.Series(eq * 100, index=pd.DatetimeIndex([t["exit_date"] for t in trs]))
    curve = curve.groupby(level=0).last()
    return {
        "n": len(rs),
        "win": float((rs > 0).mean() * 100),
        "avg_r": float(rs.mean()),
        "pf": float(gp / gl) if gl > 0 else float("inf"),
        "mdd": float(((peak - eq) / peak).max() * 100),
        "ret": float((eq[-1] - 1) * 100),
        "rs": rs.tolist(),
        "curve": curve,
    }


def split_stats(trades, risk_pct, split=0.6):
    """أول 60% من الزمن تحقق، وآخر 40% اختبار خارج العينة."""
    if not trades:
        return None, None, None
    dates = pd.DatetimeIndex([t["entry_date"] for t in trades])
    cut = dates.min() + (dates.max() - dates.min()) * split
    s_in = [t for t in trades if t["entry_date"] < cut]
    s_out = [t for t in trades if t["entry_date"] >= cut]
    return stats(trades, risk_pct), stats(s_in, risk_pct), stats(s_out, risk_pct)


def mc_drawdown(rs, risk_pct, sims=2000, pct=95, seed=7):
    """أسوأ تراجع محتمل: إعادة سحب ترتيب الصفقات عشوائياً (Bootstrap)."""
    rs = np.asarray(rs, dtype=float)
    if rs.size == 0:
        return 0.0
    rng = np.random.default_rng(seed)
    samples = rng.choice(rs, size=(sims, rs.size), replace=True)
    eq = np.cumprod(1 + samples * risk_pct / 100.0, axis=1)
    eq = np.concatenate([np.ones((sims, 1)), eq], axis=1)
    peak = np.maximum.accumulate(eq, axis=1)
    dd = ((peak - eq) / peak).max(axis=1) * 100
    return float(np.percentile(dd, pct))


def period_start(years):
    return datetime.date.today() - datetime.timedelta(days=int(years * 365.25))
