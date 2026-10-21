import streamlit as st

import ui
from sniper import data, engine

S = engine.load_settings()

st.title("💼 المحفظة الحية")
ui.flash()


@st.fragment(run_every=5)
def live():
    alive, _ = ui.monitor_status(S)
    if not alive:
        # المراقب الخلفي متوقف: الصفحة تتولى التحديث بنفسها
        for e in engine.refresh_open_positions(S):
            st.toast(ui.esc(e))
    ui.toast_new_events()
    trades = engine.list_open()
    eq, base, cash = engine.get_equity(), engine.get_initial(), engine.get_cash()
    heat = engine.open_heat(trades) / eq * 100.0 if eq > 0 else 0.0
    st.caption("⚡ تحديث كل 5 ثوان — {} — المخاطرة المفتوحة: {:.2f}% (الحد {}%)".format(
        "المراقب الخلفي يدير الوقف والجني حتى لو سكرت الصفحة" if alive
        else "المراقب متوقف: الإدارة الآلية تعمل والصفحة مفتوحة فقط", heat, S["max_heat_pct"]))
    a, b, c, d = st.columns(4)
    a.metric("قيمة المحفظة", ui.money(eq), ui.pct((eq / base - 1) * 100 if base else 0))
    b.metric("الربح / الخسارة", ui.money(eq - base, True), "رأس المال: ${:,.0f}".format(base),
             delta_color="off")
    c.metric("الكاش المتاح", ui.money(cash))
    d.metric("ربح الصفقات المفتوحة", ui.money(sum(engine.trade_pnl(t) for t in trades), True))
    for tr in trades:
        st.markdown(ui.trade_card_html(tr), unsafe_allow_html=True)
    if not trades:
        st.info("لا توجد صفقات مفتوحة. اختر سهماً من الرادار.")


live()

open_now = engine.list_open()
if open_now:
    st.subheader("🎛️ إدارة الصفقات")
    for tr in open_now:
        tid = str(tr["id"])
        with st.expander(tr["symbol"] + " — " + ("شورت" if tr["direction"] == "short" else "شراء")
                         + " @ $" + format(tr["entry"], ",.2f")):
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🔴 إغلاق كامل", key="all_" + tid, type="primary", use_container_width=True):
                    p = data.fetch_last_price(tr["symbol"]) or tr["current"]
                    net = engine.close_position(S, tr["id"], p, "إغلاق يدوي", 1.0)
                    ui.set_flash("تم إغلاق " + tr["symbol"] + " | الصافي: " + ui.money(net or 0, True))
                    st.rerun()
            with c2:
                frac = st.select_slider("إغلاق جزئي", [25, 33, 50, 66, 75], value=50, key="frac_" + tid,
                                        format_func=lambda v: str(v) + "%")
                if st.button("✂️ بيع " + str(frac) + "%", key="part_" + tid, use_container_width=True,
                             help="إذا الصفقة رابحة ينتقل وقف الباقي لسعر الدخول (تعادل)."):
                    p = data.fetch_last_price(tr["symbol"]) or tr["current"]
                    engine.close_position(S, tr["id"], p, "بيع جزئي يدوي " + str(frac) + "%", frac / 100.0)
                    ui.set_flash("تم بيع " + str(frac) + "% من " + tr["symbol"] + " وتأمين الباقي")
                    st.rerun()

            with st.form("edit_" + tid):
                e1, e2 = st.columns(2)
                new_sl = e1.number_input("الوقف ($)", value=round(float(tr["sl"]), 2), step=0.01,
                                         format="%.2f")
                new_tp = e2.number_input("الهدف ($)", value=round(float(tr["tp"]), 2), step=0.01,
                                         format="%.2f")
                new_note = st.text_area("ملاحظة", value=tr.get("note") or "", height=70)
                if st.form_submit_button("💾 حفظ التعديلات", use_container_width=True):
                    short = tr["direction"] == "short"
                    cur = tr["current"]
                    if (not short and not new_sl < cur < new_tp) or (short and not new_tp < cur < new_sl):
                        st.error("لازم السعر الحالي يكون بين الوقف والهدف.")
                    else:
                        engine.modify_trade(tr["id"], sl=new_sl, tp=new_tp, note=new_note)
                        ui.set_flash("تم تحديث " + tr["symbol"])
                        st.rerun()
            st.link_button("📈 TradingView", ui.tv_link(tr["symbol"]), use_container_width=True)

orders = engine.list_orders("open")
if orders:
    st.caption("⏳ عندك {} أمر معلق.".format(len(orders)))
    st.page_link("views/orders.py", label="إدارة الأوامر المعلقة", icon="⏳")
