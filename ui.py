"""أدوات الواجهة المشتركة: التنسيق، الدخول، الشريط العلوي، بطاقات الصفقات."""
import hmac
import html
import logging
import os
import time

import streamlit as st

from sniper import data, engine, monitor, notify

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700;900&display=swap');
html, body, .stApp, .stMarkdown, button, input, textarea, select, label {
    font-family: 'Tajawal', system-ui, sans-serif;
}
.stApp { direction: rtl; }
.block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1400px; }
h1, h2, h3, h4, p, label, .stMarkdown, [data-testid="stCaptionContainer"] { text-align: right; }
[data-testid="stDataFrame"], [data-testid="stDataEditor"], [data-testid="stPlotlyChart"],
[data-testid="stArrowVegaLiteChart"], .js-plotly-plot { direction: ltr; }
[data-testid="stMetricValue"] { font-size: 1.4rem !important; font-weight: 900; }
[data-testid="stMetricValue"] > div, [data-testid="stMetricDelta"] > div { direction: ltr; unicode-bidi: plaintext; }
[data-testid="stMetric"] {
    background: #161B22; border: 1px solid #30363D; border-radius: 12px; padding: 12px 14px;
}
div.stButton > button, div[data-testid="stFormSubmitButton"] > button,
div.stDownloadButton > button, a[data-testid="stBaseLinkButton-secondary"] {
    border-radius: 10px; font-weight: 700;
}
.trade-box {
    background: #161B22; border: 1px solid #30363D; border-radius: 12px;
    padding: 14px 16px; margin-bottom: 12px;
}
.trade-box .head { display: flex; justify-content: space-between; align-items: center; gap: 8px;
    flex-wrap: wrap; }
.trade-box .sym { font-size: 1.25rem; font-weight: 900; }
.trade-box .pnl { font-size: 1.1rem; font-weight: 700; direction: ltr; }
.trade-box .meta { margin-top: 8px; font-size: 0.95rem; color: #8B949E; line-height: 1.8; }
.trade-box .bar { height: 6px; border-radius: 4px; background: #2c2c2a; margin-top: 10px;
    position: relative; overflow: hidden; }
.trade-box .bar span { position: absolute; top: 0; bottom: 0; border-radius: 4px; }
.pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.85rem;
    background: #21262D; border: 1px solid #30363D; margin-inline-start: 6px; }
.event { padding: 6px 0; border-bottom: 1px solid #21262D; font-size: 0.95rem; }
.event small { color: #8B949E; direction: ltr; display: inline-block; }
@media (max-width: 640px) {
    .block-container { padding-left: 0.8rem; padding-right: 0.8rem; }
    [data-testid="stMetricValue"] { font-size: 1.15rem !important; }
}
</style>
"""

log = logging.getLogger("sniper.ui")


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def secret(name, default=None):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, default)


def require_login():
    pw = secret("APP_PASSWORD")
    if not pw or st.session_state.get("auth_ok"):
        return
    st.markdown("## 👑 Halal Sniper Ultra Pro")
    with st.form("login"):
        entered = st.text_input("كلمة المرور", type="password")
        if st.form_submit_button("دخول", type="primary", use_container_width=True):
            if hmac.compare_digest(entered.encode("utf-8"), str(pw).encode("utf-8")):
                st.session_state["auth_ok"] = True
                st.rerun()
            time.sleep(1.5)
            st.error("كلمة المرور غير صحيحة.")
    st.stop()


def configure_notifications():
    notify.configure(secret("TELEGRAM_TOKEN"), secret("TELEGRAM_CHAT_ID"))


# =====================================================================
# تنسيق الأرقام
# =====================================================================
def money(x, sign=False):
    x = float(x or 0.0)
    s = "${:,.2f}".format(abs(x))
    if x < 0:
        return "-" + s
    return "+" + s if sign else s


def ltr(s):
    return '<span dir="ltr">' + str(s) + "</span>"


def esc(s):
    """Streamlit يحوّل النص بين علامتي $ لمعادلة رياضية، فنهرب العلامة بنصوص الماركداون."""
    return str(s).replace("$", "\\$")


def html_dollars(s):
    return str(s).replace("$", "&#36;")


def pct(x, sign=True):
    return ("{:+.2f}%" if sign else "{:.2f}%").format(x or 0.0)


def flash():
    if "flash" in st.session_state:
        st.success(esc(st.session_state.pop("flash")))


def set_flash(msg):
    st.session_state["flash"] = msg


# =====================================================================
# الشريط العلوي: السوق + الحماية + البوابة
# =====================================================================
def status_banners(S, show_edge=True):
    mkt = data.market_state()
    if mkt["known"]:
        vix = " | VIX: " + format(mkt["vix"], ".1f") if mkt["vix"] else ""
        line = esc("SPY: $" + format(mkt["spy"], ",.2f") + " | SMA200: $" + format(mkt["sma200"], ",.2f") + vix)
        if mkt["ok"]:
            st.success("🟢 السوق العام صاعد — " + line)
        else:
            st.error("🔴 السوق العام هابط — الشراء محظور إلا بالتجاوز — " + line)
    else:
        st.warning("⚠️ تعذر قراءة SPY. فلتر السوق معطل مؤقتاً.")

    blocked, peak = engine.day_guard(S)
    if blocked:
        st.error("🛑 وصلت حد الخسارة اليومي (" + str(S["daily_loss_pct"]) + "%). لا صفقات جديدة اليوم.")

    edge = engine.edge_status(S)
    if show_edge and S["edge_gate"]:
        ok, msg, info = edge
        if ok:
            st.success("✅ بوابة الجدوى مفتوحة (الفاصل اليومي): توقع خارج العينة {:+.2f}R على {} صفقة"
                       .format(info["avg_r_oos"], info["n_oos"]))
        else:
            st.warning("🔒 بوابة الجدوى مغلقة: " + msg)
    return mkt, blocked, peak, edge


def monitor_status(S):
    age = monitor.heartbeat_age()
    limit = max(S.get("monitor_secs", 20), 120) * 3
    alive = age is not None and age < limit
    return alive, age


# =====================================================================
# بطاقة الصفقة
# =====================================================================
def trade_card_html(tr):
    pnl = engine.trade_pnl(tr)
    pc = pnl / tr["cost"] * 100.0 if tr["cost"] else 0.0
    r_now = pnl / tr["init_risk"] if tr["init_risk"] else 0.0
    short = tr["direction"] == "short"
    tag = "🟢" if pnl >= 0 else "🔴"
    dlabel = "🔴 بيع (Short)" if short else "🟢 شراء (Long)"
    pills = ""
    if tr["be_done"]:
        pills += '<span class="pill">🛡️ تعادل مفعّل</span>'
    if tr.get("half_closed"):
        pills += '<span class="pill">✂️ جني جزئي تم</span>'
    if tr.get("setup"):
        pills += '<span class="pill">' + html.escape(tr["setup"]) + "</span>"

    # موقع السعر بين الوقف والهدف
    lo, hi = (tr["tp"], tr["sl"]) if short else (tr["sl"], tr["tp"])
    span = hi - lo
    pos = 0.0 if span <= 0 else min(1.0, max(0.0, (tr["current"] - lo) / span))
    if short:
        pos = 1 - pos
    color = "#3987e5" if pnl >= 0 else "#e66767"
    bar = ('<div class="bar" title="الموقع بين الوقف والهدف"><span style="right:0;width:'
           + format(pos * 100, ".0f") + '%;background:' + color + '"></span></div>')
    note = ""
    if tr.get("note"):
        note = "<br>📝 " + html.escape(tr["note"])
    return html_dollars(
        '<div class="trade-box"><div class="head">'
        '<span class="sym">' + html.escape(tr["symbol"]) + " | " + dlabel + pills + "</span>"
        '<span class="pnl">' + tag + " " + pct(pc) + " (" + money(pnl, True) + ") | "
        + format(r_now, "+.2f") + "R</span></div>"
        '<div class="meta"><b>الدخول:</b> ' + ltr(money(tr["entry"]))
        + " | <b>الآن:</b> " + ltr(money(tr["current"]))
        + " | <b>الوقف:</b> " + ltr(money(tr["sl"]))
        + " | <b>الهدف:</b> " + ltr(money(tr["tp"])) + "<br>"
        "<b>المبلغ:</b> " + ltr(money(tr["cost"])) + " (" + format(tr["shares"], "g") + " سهم)"
        + " | " + html.escape(str(tr["timeframe"])) + " | " + html.escape(str(tr["opened"]))
        + note + "</div>" + bar + "</div>"
    )


def toast_new_events():
    last = st.session_state.get("last_event_id")
    if last is None:
        st.session_state["last_event_id"] = engine.last_event_id()
        return
    evs = engine.recent_events(after_id=last, limit=10)
    if evs:
        st.session_state["last_event_id"] = max(e["id"] for e in evs)
        for e in reversed(evs):
            if e["kind"] in ("close", "order", "alert", "halal", "scan"):
                st.toast(esc(e["msg"]))


def tv_link(sym):
    return "https://www.tradingview.com/chart/?symbol=" + str(sym)


def sym_input(label, key, value=""):
    return st.text_input(label, value, key=key).strip().upper()
