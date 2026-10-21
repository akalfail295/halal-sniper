"""قائمة الأصول المرشحة. الفحص الشرعي في halal.py هو اللي يحدد الاجتياز فعلياً."""

TECH = "تقنية"
COMM = "اتصالات"
CONS = "استهلاكي"
HEALTH = "رعاية صحية"
ENERGY = "طاقة"
INDUS = "صناعي"
MATER = "مواد أساسية"
FUNDS = "صناديق"

# أول 25 = القياديات (أعلى سيولة)
_STOCKS = [
    ("AAPL", TECH), ("MSFT", TECH), ("NVDA", TECH), ("GOOGL", COMM), ("AMZN", CONS),
    ("META", COMM), ("TSLA", CONS), ("AVGO", TECH), ("AMD", TECH), ("ADBE", TECH),
    ("CRM", TECH), ("CSCO", TECH), ("QCOM", TECH), ("TXN", TECH), ("INTU", TECH),
    ("AMAT", TECH), ("LLY", HEALTH), ("JNJ", HEALTH), ("MRK", HEALTH), ("ABT", HEALTH),
    ("TMO", HEALTH), ("ISRG", HEALTH), ("COST", CONS), ("XOM", ENERGY), ("CVX", ENERGY),
    # تقنية
    ("LRCX", TECH), ("KLAC", TECH), ("MU", TECH), ("ANET", TECH), ("PANW", TECH),
    ("CRWD", TECH), ("FTNT", TECH), ("SNPS", TECH), ("CDNS", TECH), ("NOW", TECH),
    ("ADI", TECH), ("MRVL", TECH), ("NXPI", TECH), ("ACN", TECH), ("PLTR", TECH),
    ("ADSK", TECH), ("WDAY", TECH), ("MCHP", TECH), ("ON", TECH), ("DDOG", TECH),
    # رعاية صحية
    ("DHR", HEALTH), ("SYK", HEALTH), ("VRTX", HEALTH), ("REGN", HEALTH), ("MDT", HEALTH),
    ("ZTS", HEALTH), ("IDXX", HEALTH), ("EW", HEALTH), ("DXCM", HEALTH), ("BSX", HEALTH),
    ("A", HEALTH), ("RMD", HEALTH),
    # استهلاكي
    ("NKE", CONS), ("PG", CONS), ("PEP", CONS), ("CL", CONS), ("LULU", CONS),
    ("TJX", CONS), ("ROST", CONS), ("ORLY", CONS), ("HD", CONS), ("DECK", CONS),
    ("ULTA", CONS), ("MNST", CONS), ("TSCO", CONS),
    # صناعي
    ("CAT", INDUS), ("AME", INDUS), ("TT", INDUS), ("ETN", INDUS), ("PH", INDUS),
    ("EMR", INDUS), ("ITW", INDUS), ("GWW", INDUS), ("FAST", INDUS), ("ODFL", INDUS),
    ("ROK", INDUS), ("CTAS", INDUS), ("CPRT", INDUS), ("PCAR", INDUS), ("XYL", INDUS),
    # طاقة
    ("COP", ENERGY), ("EOG", ENERGY), ("SLB", ENERGY), ("DVN", ENERGY), ("FANG", ENERGY),
    # مواد أساسية
    ("LIN", MATER), ("SHW", MATER), ("APD", MATER), ("ECL", MATER), ("NUE", MATER),
    ("FCX", MATER), ("NEM", MATER),
]

# صناديق متوافقة مع الشريعة مدرجة بأمريكا
_FUNDS = ["SPUS", "HLAL", "UMMA", "SPTE", "SPWO", "SPRE", "SPSK", "MNZL"]

HALAL_STOCKS = [s for s, _ in _STOCKS]
HALAL_FUNDS = list(_FUNDS)
LEADERS = HALAL_STOCKS[:25]

SECTORS = {s: sec for s, sec in _STOCKS}
SECTORS.update({f: FUNDS for f in _FUNDS})

ALL_ASSETS = [(s, "Stock") for s in HALAL_STOCKS] + [(f, "ETF") for f in _FUNDS]


def sector_of(sym):
    return SECTORS.get(sym, "-")


def is_fund(sym):
    return SECTORS.get(sym) == FUNDS
