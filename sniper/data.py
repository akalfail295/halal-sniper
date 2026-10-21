"""جلب البيانات من Yahoo Finance مع كاش بسيط وتسجيل الأخطاء بدل إخفائها."""
import datetime
import logging
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

log = logging.getLogger("sniper.data")

NY = ZoneInfo("America/New_York")
INTRADAY = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}
OHLCV = ["Open", "High", "Low", "Close", "Volume"]

_CACHE = {}
_CACHE_LOCK = threading.Lock()


# =====================================================================
# كاش بمدة صلاحية
# =====================================================================
def _is_empty(v):
    return v is None or (isinstance(v, (pd.DataFrame, pd.Series)) and v.empty)


def _cache_peek(key, ttl):
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if hit is not None and time.time() - hit[0] < ttl:
        return True, hit[1]
    return False, None


def _cache_put(key, val):
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), val)


def ttl_get(key, ttl, fn):
    found, val = _cache_peek(key, ttl)
    if found:
        return val
    val = fn()
    if not _is_empty(val):
        _cache_put(key, val)
    return val


def clear_cache():
    with _CACHE_LOCK:
        _CACHE.clear()


def _ttl_for(interval):
    return {"1m": 30, "2m": 45, "5m": 60, "15m": 120, "30m": 180,
            "60m": 300, "90m": 300, "1h": 300, "1d": 900}.get(interval, 3600)


# =====================================================================
# الأسعار التاريخية
# =====================================================================
def _normalize(df, interval):
    if _is_empty(df):
        return pd.DataFrame()
    df = df[[c for c in OHLCV if c in df.columns]].dropna(subset=["Close"])
    if df.empty:
        return df
    idx = pd.DatetimeIndex(df.index)
    if interval in INTRADAY:
        idx = idx.tz_localize("UTC").tz_convert(NY) if idx.tz is None else idx.tz_convert(NY)
    elif idx.tz is not None:
        idx = idx.tz_localize(None)
    df = df.copy()
    df.index = idx
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if "Volume" in df.columns:
        df["Volume"] = df["Volume"].fillna(0)
    return df


def fetch_history(sym, period, interval, start=None, ttl=None):
    ttl = ttl or _ttl_for(interval)

    def load():
        try:
            kw = {"start": start} if start else {"period": period}
            raw = yf.Ticker(sym).history(interval=interval, auto_adjust=True, **kw)
            return _normalize(raw, interval)
        except Exception as e:
            log.warning("history %s %s/%s: %s", sym, period, interval, e)
            return None

    return ttl_get(("hist", sym, start or period, interval), ttl, load)


def fetch_many(symbols, period, interval, start=None, ttl=None, progress=None):
    """تحميل جماعي (أسرع وأقل طلبات) مع الرجوع للتحميل الفردي عند الفشل."""
    ttl = ttl or _ttl_for(interval)
    out, missing = {}, []
    for s in symbols:
        found, val = _cache_peek(("hist", s, start or period, interval), ttl)
        if found:
            out[s] = val
        else:
            missing.append(s)
    total = max(1, len(symbols))
    done = len(out)
    if progress:
        progress(done / total)
    chunk = 30
    for i in range(0, len(missing), chunk):
        part = missing[i:i + chunk]
        raw = None
        try:
            kw = {"start": start} if start else {"period": period}
            raw = yf.download(part, interval=interval, group_by="ticker", auto_adjust=True,
                              progress=False, threads=True, **kw)
        except Exception as e:
            log.warning("download %s..: %s", part[:3], e)
        for s in part:
            df = None
            if not _is_empty(raw):
                try:
                    sub = raw[s] if isinstance(raw.columns, pd.MultiIndex) else raw
                    df = _normalize(sub, interval)
                except KeyError:
                    df = None
            if _is_empty(df):
                df = fetch_history(s, period, interval, start=start, ttl=ttl)
            elif df is not None:
                _cache_put(("hist", s, start or period, interval), df)
            if not _is_empty(df):
                out[s] = df
        done += len(part)
        if progress:
            progress(min(1.0, done / total))
    return out


def load_hists(symbols, years, progress=None):
    """بيانات يومية للباك-تست + سنة إضافية لتسخين المؤشرات."""
    start = (datetime.date.today() - datetime.timedelta(days=int((years + 1) * 365.25))).isoformat()
    return fetch_many(symbols, None, "1d", start=start, ttl=3600, progress=progress)


def load_spy(years=11):
    start = (datetime.date.today() - datetime.timedelta(days=int(years * 365.25))).isoformat()
    df = fetch_history("SPY", None, "1d", start=start, ttl=3600)
    return None if _is_empty(df) else df["Close"]


# =====================================================================
# السعر اللحظي
# =====================================================================
def fetch_last_price(sym):
    def load():
        try:
            p = yf.Ticker(sym).fast_info.get("lastPrice")
            if p and p == p and p > 0:
                return float(p)
        except Exception as e:
            log.debug("fast_info %s: %s", sym, e)
        try:
            h = yf.Ticker(sym).history(period="1d", interval="1m")
            if not h.empty:
                return float(h["Close"].dropna().iloc[-1])
        except Exception as e:
            log.warning("last price %s: %s", sym, e)
        return None

    return ttl_get(("last", sym), 5, load)


def fetch_prices(symbols):
    symbols = sorted(set(symbols))
    if not symbols:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(symbols))) as ex:
        return {s: p for s, p in zip(symbols, ex.map(fetch_last_price, symbols)) if p}


# =====================================================================
# حالة السوق والأرباح والأخبار
# =====================================================================
def market_state():
    def load():
        st = {"known": False, "ok": True, "spy": None, "sma200": None, "vix": None}
        spy = fetch_history("SPY", "2y", "1d")
        if not _is_empty(spy) and len(spy) >= 200:
            c = spy["Close"]
            st["known"] = True
            st["spy"] = float(c.iloc[-1])
            st["sma200"] = float(c.rolling(200).mean().iloc[-1])
            st["ok"] = st["spy"] > st["sma200"]
        vix = fetch_history("^VIX", "5d", "1d")
        if not _is_empty(vix):
            st["vix"] = float(vix["Close"].iloc[-1])
        return st

    return ttl_get("market", 300, load)


def ny_now():
    return datetime.datetime.now(NY)


def market_open(now=None):
    now = now or ny_now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= t < 16 * 60


def days_to_earnings(sym):
    def load():
        try:
            cal = yf.Ticker(sym).calendar
            dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
            if not dates:
                return -1
            today = datetime.date.today()
            ds = [d.date() if isinstance(d, datetime.datetime) else d for d in dates]
            fut = [d for d in ds if d >= today]
            return (min(fut) - today).days if fut else -1
        except Exception as e:
            log.debug("calendar %s: %s", sym, e)
            return -1

    v = ttl_get(("earn", sym), 12 * 3600, load)
    return None if v is None or v < 0 else v


def fetch_headlines(sym, n=6):
    def load():
        url = ("https://feeds.finance.yahoo.com/rss/2.0/headline?s="
               + urllib.parse.quote(sym) + "&region=US&lang=en-US")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(urllib.request.urlopen(req, timeout=8).read())
            items = []
            for it in root.findall(".//item")[:n]:
                items.append({"title": (it.findtext("title") or "").strip(),
                              "link": (it.findtext("link") or "").strip(),
                              "date": (it.findtext("pubDate") or "").strip()})
            return items
        except Exception as e:
            log.debug("rss %s: %s", sym, e)
            return []

    return ttl_get(("news", sym), 1800, load) or []


def gold_gram_price():
    df = fetch_history("GC=F", "5d", "1d", ttl=3600)
    if _is_empty(df):
        return None
    return float(df["Close"].iloc[-1]) / 31.1034768


def ticker_info(sym):
    def load():
        try:
            return dict(yf.Ticker(sym).info or {})
        except Exception as e:
            log.warning("info %s: %s", sym, e)
            return None

    return ttl_get(("info", sym), 24 * 3600, load)
