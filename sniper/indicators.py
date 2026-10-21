"""المؤشرات الفنية (كلها محسوبة من بيانات الماضي فقط، بدون نظر للمستقبل)."""
import numpy as np
import pandas as pd


def add_indicators(df, intraday=False):
    d = df.copy()
    c, h, l = d["Close"], d["High"], d["Low"]
    v = d["Volume"].fillna(0) if "Volume" in d.columns else pd.Series(0.0, index=d.index)

    for n in (20, 50, 150, 200):
        d["SMA" + str(n)] = c.rolling(n).mean()
    d["EMA21"] = c.ewm(span=21, adjust=False).mean()

    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    d["RSI"] = rsi.where(loss != 0, 100.0).where(gain.notna())

    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    d["MACD"] = ema12 - ema26
    d["MACD_sig"] = d["MACD"].ewm(span=9, adjust=False).mean()
    d["MACD_hist"] = d["MACD"] - d["MACD_sig"]

    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    d["ATR"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    d["VolAvg"] = v.rolling(20).mean()
    d["VolRatio"] = v / d["VolAvg"].replace(0, np.nan)

    tp = (h + l + c) / 3
    if intraday:
        day = d.index.date
        vwap = (tp * v).groupby(day).cumsum() / v.groupby(day).cumsum().replace(0, np.nan)
    else:
        vwap = (tp * v).rolling(20).sum() / v.rolling(20).sum().replace(0, np.nan)
    d["VWAP"] = vwap.fillna(tp)

    d["High20"] = h.rolling(20).max().shift(1)
    d["Low20"] = l.rolling(20).min().shift(1)
    d["Hi52"] = h.rolling(252, min_periods=60).max()
    d["Lo52"] = l.rolling(252, min_periods=60).min()
    return d


def trend_template(d):
    """قالب ترند مينرفيني (7 شروط). يرجّع عدد الشروط المتحققة لكل شمعة."""
    c, s50, s150, s200 = d["Close"], d["SMA50"], d["SMA150"], d["SMA200"]
    conds = [
        (c > s150) & (c > s200),
        s150 > s200,
        s200 > s200.shift(21),
        (s50 > s150) & (s50 > s200),
        c > s50,
        c >= 1.3 * d["Lo52"],
        c >= 0.75 * d["Hi52"],
    ]
    tt = sum(x.astype(int) for x in conds)
    return tt.where(s200.shift(21).notna())


def candle_flags(d):
    """+1 شمعة انعكاس شرائية، -1 بيعية، 0 عادية — مع اسم النمط."""
    o, h, l, c = d["Open"], d["High"], d["Low"], d["Close"]
    po, pc = o.shift(1), c.shift(1)
    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    upper = h - pd.concat([o, c], axis=1).max(axis=1)
    lower = pd.concat([o, c], axis=1).min(axis=1) - l

    doji = body <= 0.1 * rng
    bull_engulf = (c > o) & (pc < po) & (c >= po) & (o <= pc)
    bear_engulf = (c < o) & (pc > po) & (o >= pc) & (c <= po)
    hammer = (lower >= 2 * body) & (upper <= body) & ~doji
    star = (upper >= 2 * body) & (lower <= body) & ~doji

    names = np.select(
        [doji, bull_engulf, bear_engulf, hammer, star, c > o],
        ["⚖️ دوجي", "🟢 ابتلاع شرائي", "🔴 ابتلاع بيعي", "🔨 مطرقة", "🌠 شهاب", "🟢 صاعدة"],
        default="🔴 هابطة")
    flag = np.where(bull_engulf | hammer, 1, np.where(bear_engulf | star, -1, 0))
    return pd.Series(flag, index=d.index), pd.Series(names, index=d.index)


def swing_levels(d, window=5, n=2):
    """أقرب مستويات دعم ومقاومة من القمم والقيعان المحلية."""
    if len(d) < window * 2 + 1:
        return [], []
    h, l = d["High"], d["Low"]
    size = window * 2 + 1
    piv_h = h[(h == h.rolling(size, center=True).max())].dropna()
    piv_l = l[(l == l.rolling(size, center=True).min())].dropna()
    price = float(d["Close"].iloc[-1])

    def pick(cands):
        # نتجاهل المستويات الملاصقة للسعر أو لبعضها (أقل من 1%) عشان ما تتراكب
        out = []
        for x in cands:
            if abs(x - price) / price >= 0.005 and all(abs(x - y) / price >= 0.01 for y in out):
                out.append(round(x, 2))
            if len(out) == n:
                break
        return out

    res = pick(sorted(float(x) for x in piv_h if x > price))
    sup = pick(sorted((float(x) for x in piv_l if x < price), reverse=True))
    return sup, res
