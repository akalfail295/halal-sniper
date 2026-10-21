import datetime
import html

import pandas as pd
import streamlit as st

import ui
from sniper import analytics, charts, data, engine
from sniper.db import meta_get, q

S = engine.load_settings()

st.title("👑 Halal Sniper Ultra Pro")
st.caption("محفظة تجريبية (Paper Trading) لأسهم وصناديق متوافقة مع الشريعة — أداة تعليمية وليست نصيحة استثمارية.")
ui.flash()
mkt, blocked, peak, edge = ui.status_banners(S)

alive, age = ui.monitor_status(S)
if alive:
    st.caption("🛰️ المراقب الخلفي شغال (آخر نبضة قبل {:.0f} ث) — {}".format(
        age, "السوق مفتوح" if data.market_open() else "السوق مغلق حالياً (تحديث كل دقيقتين)"))
else:
    st.warning("🛰️ المراقب الخلفي متوقف. الوقف المتحرك يتحدث فقط وصفحة المحفظة مفتوحة.")


@st.fragment(run_every=10)
def kpis():
    ui.toast_new_events()
    trades = engine.list_open()
    eq, base, cash = engine.get_equity(), engine.get_initial(), engine.get_cash()
    ds = meta_get("day_start", None) or {}
    day_pnl = eq - float(ds.get("equity", eq)) if ds.get("date") == str(datetime.date.today()) else 0.0
    heat = engine.open_heat(trades) / eq * 100 if eq > 0 else 0.0
    a, b, c, d, e = st.columns(5)
    a.metric("قيمة المحفظة", ui.money(eq), ui.pct((eq / base - 1) * 100 if base else 0))
    b.metric("ربح اليوم", ui.money(day_pnl, True))
    c.metric("الكاش المتاح", ui.money(cash))
    d.metric("صفقات مفتوحة", "{} / {}".format(len(trades), S["max_open"]))
    e.metric("المخاطرة المفتوحة", ui.pct(heat, False), "الحد " + str(S["max_heat_pct"]) + "%",
             delta_color="off")


kpis()

left, right = st.columns([3, 2])
with left:
    st.subheader("📈 مسار المحفظة")
    eqh = analytics.equity_history()
    if len(eqh) >= 2:
        spy = data.load_spy(years=3)
        st.plotly_chart(charts.equity_vs_benchmark(eqh, spy), use_container_width=True)
    else:
        cdf = analytics.closed_df()
        curve = analytics.realized_curve(cdf, engine.get_initial())
        if len(curve) >= 2:
            st.plotly_chart(charts.line(curve, "المحفظة (محقق)", height=320, ytitle="$"),
                            use_container_width=True)
        else:
            st.info("يبدأ الرسم بعد يومين من التداول. المراقب يحفظ قيمة المحفظة كل يوم تلقائياً.")

with right:
    st.subheader("🕑 آخر الأحداث")
    evs = engine.recent_events(limit=12)
    if not evs:
        st.caption("لا توجد أحداث بعد.")
    for ev in evs:
        st.markdown(ui.html_dollars('<div class="event">' + html.escape(ev["msg"]) + "<br><small>"
                                    + ev["ts"] + "</small></div>"), unsafe_allow_html=True)

st.divider()
c1, c2 = st.columns(2)
with c1:
    st.subheader("💼 الصفقات المفتوحة")
    trades = engine.list_open()
    if not trades:
        st.info("لا توجد صفقات مفتوحة.")
        st.page_link("views/radar.py", label="افتح الرادار وابحث عن فرصة", icon="🎯")
    else:
        rows = [{"الرمز": t["symbol"], "الاتجاه": "شورت" if t["direction"] == "short" else "شراء",
                 "الدخول": round(t["entry"], 2), "الآن": round(t["current"], 2),
                 "الربح $": round(engine.trade_pnl(t), 2),
                 "R": round(engine.trade_pnl(t) / t["init_risk"], 2) if t["init_risk"] else 0.0}
                for t in trades]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.page_link("views/portfolio.py", label="إدارة الصفقات", icon="💼")
with c2:
    st.subheader("📡 إشارات اليوم")
    sig = q("SELECT symbol, timeframe, price, score, decision FROM signals WHERE day=? "
            "ORDER BY priority, score DESC LIMIT 15", (str(datetime.date.today()),))
    if not sig:
        st.info("ما في إشارات محفوظة اليوم. شغّل الفحص من الرادار.")
    else:
        st.dataframe(pd.DataFrame([dict(r) for r in sig]).rename(columns={
            "symbol": "الرمز", "timeframe": "الإطار", "price": "السعر", "score": "النقاط",
            "decision": "القرار"}), use_container_width=True, hide_index=True)
    orders = engine.list_orders("open")
    if orders:
        st.caption("⏳ أوامر معلقة: " + ", ".join(o["symbol"] for o in orders))
