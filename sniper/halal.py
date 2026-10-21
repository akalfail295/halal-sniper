"""فحص شرعي تقريبي (نسب AAOIFI) + التطهير + الزكاة. أداة تنبيه وليست فتوى."""
import logging

import yfinance as yf

from . import data
from .universe import is_fund

log = logging.getLogger("sniper.halal")

LIMIT = 0.30

# نشاط محرّم أساساً → لا يجتاز
_FAIL_INDUSTRIES = [
    "banks", "insurance", "credit services", "mortgage finance", "capital markets",
    "financial conglomerates", "brewers", "wineries", "distiller", "tobacco",
    "gambling", "casinos", "shell companies",
]
# نشاط يحتاج مراجعة
_WATCH_INDUSTRIES = {
    "asset management": "إدارة أصول (قد تتضمن أدوات ربوية)",
    "reit": "عقار مدر للدخل: راجع المستأجرين والتمويل",
    "entertainment": "ترفيه: راجع المحتوى",
    "broadcasting": "بث وإعلام: راجع المحتوى",
    "lodging": "فنادق: قد تتضمن خمور",
    "restaurants": "مطاعم: قد تتضمن لحم خنزير أو خمور",
    "aerospace & defense": "صناعات دفاعية: محل خلاف",
    "advertising": "إعلانات: راجع طبيعة المعلنين",
    "internet content": "محتوى وإعلانات: تأكد من نسبة الدخل غير المباح",
    "packaged foods": "أغذية مصنعة: تأكد من خلوها من المحرمات",
    "electronic gaming": "ألعاب إلكترونية: راجع المحتوى",
    "leisure": "ترفيه: راجع النشاط",
}


def _industry_check(industry):
    ind = (industry or "").lower().replace("—", " ").replace("-", " ")
    for k in _FAIL_INDUSTRIES:
        if k in ind:
            return "fail", "نشاط غير مباح: " + industry
    for k, msg in _WATCH_INDUSTRIES.items():
        if k in ind:
            return "watch", msg
    return "ok", ""


def _avg_market_cap(sym, shares):
    """متوسط القيمة السوقية آخر 24 شهر (أدق من القيمة اللحظية)."""
    if not shares:
        return None
    h = data.fetch_history(sym, "2y", "1mo", ttl=24 * 3600)
    if h is None or h.empty:
        return None
    return float(h["Close"].tail(24).mean()) * float(shares)


def halal_screen(sym):
    def load():
        res = {"verdict": "review", "debt": None, "cash": None, "watch": "", "industry": "",
               "basis": "", "mcap": None}
        if is_fund(sym):
            res.update(verdict="fund", watch="صندوق متوافق مع الشريعة حسب مُصدره")
            return res
        info = data.ticker_info(sym) or {}
        res["industry"] = info.get("industry") or ""
        kind, msg = _industry_check(res["industry"])
        mcap_now = info.get("marketCap")
        mcap_avg = _avg_market_cap(sym, info.get("sharesOutstanding"))
        mcap = mcap_avg or mcap_now
        res["basis"] = "متوسط 24 شهر" if mcap_avg else ("لحظية" if mcap_now else "")
        res["mcap"] = mcap
        debt, cash = info.get("totalDebt"), info.get("totalCash")
        if mcap and debt is not None and cash is not None:
            res["debt"] = float(debt) / mcap
            res["cash"] = float(cash) / mcap
            res["verdict"] = "pass" if res["debt"] < LIMIT and res["cash"] < LIMIT else "fail"
        if kind == "fail":
            res["verdict"] = "fail"
            res["watch"] = msg
        elif kind == "watch":
            res["watch"] = msg
        return res

    return data.ttl_get(("halal", sym), 24 * 3600, load)


VERDICT_LABELS = {"pass": "✅ مجتاز", "fail": "❌ لا يجتاز", "review": "⚠️ يحتاج مراجعة",
                  "fund": "✅ صندوق متوافق"}


def impure_income_ratio(sym):
    """نسبة تقريبية للدخل غير المباح = إيراد الفوائد ÷ إجمالي الإيرادات (آخر سنة مالية)."""
    def load():
        try:
            inc = yf.Ticker(sym).income_stmt
            if inc is None or inc.empty:
                return -1.0
            col = inc.columns[0]
            rev = inc.loc["Total Revenue", col] if "Total Revenue" in inc.index else None
            intr = None
            for k in ("Interest Income", "Interest Income Non Operating"):
                if k in inc.index and inc.loc[k, col] == inc.loc[k, col]:
                    intr = inc.loc[k, col]
                    break
            if not rev or intr is None:
                return -1.0
            return max(0.0, float(intr) / float(rev))
        except Exception as e:
            log.debug("income %s: %s", sym, e)
            return -1.0

    v = data.ttl_get(("impure", sym), 24 * 3600, load)
    return None if v is None or v < 0 else v


def purification_amount(amount, ratio):
    return max(0.0, float(amount)) * max(0.0, float(ratio))


NISAB_GOLD_GRAMS = 85.0


def zakat(value, gold_gram, lunar=True):
    """زكاة عروض التجارة: 2.5% للسنة الهجرية أو 2.577% للميلادية عند بلوغ النصاب."""
    nisab = NISAB_GOLD_GRAMS * gold_gram if gold_gram else None
    rate = 0.025 if lunar else 0.02577
    due = nisab is None or value >= nisab
    return {"nisab": nisab, "rate": rate, "due": due, "amount": value * rate if due else 0.0}
