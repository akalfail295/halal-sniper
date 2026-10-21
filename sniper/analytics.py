"""مقاييس الأداء من الصفقات المغلقة وسجل المحفظة اليومي."""
import math

import numpy as np
import pandas as pd

from .db import q
from .universe import sector_of

WEEKDAYS = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]


def closed_df():
    rows = q("SELECT * FROM closed_trades ORDER BY id")
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["opened_dt"] = pd.to_datetime(df["opened"], errors="coerce")
    df["closed_dt"] = pd.to_datetime(df["closed"], errors="coerce")
    df["hold_h"] = (df["closed_dt"] - df["opened_dt"]).dt.total_seconds() / 3600.0
    df["sector"] = df["symbol"].map(sector_of)
    df["weekday"] = df["opened_dt"].dt.weekday.map(lambda i: WEEKDAYS[int(i)] if i == i else "-")
    return df


def equity_history():
    rows = q("SELECT * FROM equity_history ORDER BY day")
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame([dict(r) for r in rows])
    return pd.Series(df["equity"].values, index=pd.to_datetime(df["day"]))


def realized_curve(df, initial):
    """منحنى المحفظة المحقق (رأس المال + مجموع الأرباح المغلقة) لكل يوم."""
    if df.empty:
        return pd.Series(dtype=float)
    daily = df.groupby(df["closed_dt"].dt.normalize())["pnl"].sum()
    start = pd.Series([float(initial)], index=[daily.index.min() - pd.Timedelta(days=1)])
    return pd.concat([start, initial + daily.cumsum()])


def drawdown(curve):
    if curve.empty:
        return curve
    peak = curve.cummax()
    return (curve / peak - 1) * 100


def _streak(signs, target):
    best = cur = 0
    for s in signs:
        cur = cur + 1 if s == target else 0
        best = max(best, cur)
    return best


def summary(df, curve):
    pnl = df["pnl"]
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    gl = abs(losses.sum())
    rets = curve.pct_change().dropna() if len(curve) > 2 else pd.Series(dtype=float)
    sharpe = sortino = None
    if len(rets) >= 10 and rets.std() > 0:
        sharpe = float(rets.mean() / rets.std() * math.sqrt(252))
        downside = rets[rets < 0].std()
        if downside and downside > 0:
            sortino = float(rets.mean() / downside * math.sqrt(252))
    dd = drawdown(curve)
    return {
        "n": len(df),
        "net": float(pnl.sum()),
        "win_rate": float((pnl > 0).mean() * 100),
        "avg_r": float(df["r_mult"].mean()),
        "pf": float(wins.sum() / gl) if gl > 0 else float("inf"),
        "expectancy": float(pnl.mean()),
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "best": float(pnl.max()),
        "worst": float(pnl.min()),
        "max_loss_streak": _streak(np.sign(pnl.values), -1) if len(pnl) else 0,
        "max_win_streak": _streak(np.sign(pnl.values), 1) if len(pnl) else 0,
        "avg_hold_h": float(df["hold_h"].mean()) if df["hold_h"].notna().any() else None,
        "fees": float(df["fees"].sum()),
        "mdd": float(dd.min()) if not dd.empty else 0.0,
        "sharpe": sharpe,
        "sortino": sortino,
    }


def breakdown(df, col, label):
    g = df.groupby(col).agg(n=("pnl", "size"), net=("pnl", "sum"),
                           win=("pnl", lambda x: (x > 0).mean() * 100), r=("r_mult", "mean"))
    g = g.reset_index().rename(columns={col: label, "n": "الصفقات", "net": "الصافي $",
                                        "win": "نسبة الربح %", "r": "متوسط R"})
    return g.sort_values("الصافي $", ascending=False).round(2)


def monthly_table(df):
    """جدول سنة × شهر بالصافي بالدولار."""
    if df.empty:
        return pd.DataFrame()
    m = df.groupby([df["closed_dt"].dt.year.rename("السنة"),
                    df["closed_dt"].dt.month.rename("الشهر")])["pnl"].sum()
    t = m.unstack("الشهر").reindex(columns=range(1, 13))
    t.index = t.index.astype(int)
    return t
