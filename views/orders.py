import pandas as pd
import streamlit as st

import ui
from sniper import data, engine

st.title("⏳ الأوامر المعلقة وقائمة المراقبة")
ui.flash()

tab_orders, tab_watch = st.tabs(["⏳ الأوامر المعلقة", "👀 قائمة المراقبة والتنبيهات"])

with tab_orders:
    st.caption("الأمر المعلق ينفذه المراقب الخلفي لما يوصل السعر لسعر التفعيل، بعد ما يمر على كل "
               "شروط الحماية (حد الخسارة اليومي، الحد الأقصى، القطاع، المخاطرة، الشريعة، البوابة).")
    orders = engine.list_orders("open")
    if not orders:
        st.info("لا توجد أوامر معلقة. ضع أمر من تذكرة الأمر بصفحة الرادار.")
    else:
        prices = data.fetch_prices([o["symbol"] for o in orders])
        for o in orders:
            p = prices.get(o["symbol"])
            dist = (p / o["trigger"] - 1) * 100 if p else None
            c1, c2 = st.columns([5, 1])
            c1.markdown(ui.esc(
                "**{}** — {} {} @ **${:,.2f}** | الآن: {} {} | ينتهي: {}{}".format(
                    o["symbol"], "شراء" if o["direction"] == "long" else "شورت",
                    engine.ORDER_KINDS.get(o["kind"], o["kind"]), o["trigger"],
                    ui.money(p) if p else "-", "({:+.2f}%)".format(dist) if dist is not None else "",
                    o["expires"], (" | 📝 " + o["note"]) if o["note"] else "")))
            if c2.button("إلغاء", key="cancel_" + str(o["id"]), use_container_width=True):
                engine.cancel_order(o["id"])
                ui.set_flash("تم إلغاء أمر " + o["symbol"])
                st.rerun()

    hist = [o for o in engine.list_orders(None) if o["status"] != "open"]
    if hist:
        st.subheader("📜 سجل الأوامر")
        status = {"filled": "✅ نُفّذ", "rejected": "⛔ مرفوض", "expired": "⌛ منتهي",
                  "cancelled": "✖️ ملغي"}
        st.dataframe(pd.DataFrame([{
            "الرمز": o["symbol"], "النوع": engine.ORDER_KINDS.get(o["kind"], o["kind"]),
            "التفعيل": o["trigger"], "الحالة": status.get(o["status"], o["status"]),
            "التفاصيل": o["info"], "أُنشئ": o["created"]} for o in hist]),
            use_container_width=True, hide_index=True,
            column_config={"التفعيل": st.column_config.NumberColumn(format="$%.2f")})

with tab_watch:
    with st.form("add_watch", clear_on_submit=True):
        w1, w2, w3 = st.columns(3)
        sym = w1.text_input("الرمز").strip().upper()
        above = w2.number_input("نبهني إذا تعدّى ($)", min_value=0.0, value=0.0, step=0.5)
        below = w3.number_input("نبهني إذا نزل تحت ($)", min_value=0.0, value=0.0, step=0.5)
        note = st.text_input("ملاحظة")
        if st.form_submit_button("➕ إضافة / تحديث", type="primary", use_container_width=True):
            if not sym:
                st.error("اكتب الرمز.")
            elif not data.fetch_last_price(sym):
                st.error("ما لقيت سعر لهالرمز. تأكد من كتابته.")
            else:
                engine.add_watch(sym, above or None, below or None, note)
                ui.set_flash("تم حفظ " + sym)
                st.rerun()

    wl = engine.list_watch()
    if not wl:
        st.info("قائمة المراقبة فاضية.")
    else:
        prices = data.fetch_prices([w["symbol"] for w in wl])
        rows = []
        for w in wl:
            rows.append({"الرمز": w["symbol"], "السعر": prices.get(w["symbol"]),
                         "تنبيه فوق": w["above"], "تنبيه تحت": w["below"],
                         "آخر تنبيه": w["last_alert"] or "-", "ملاحظة": w["note"], "أُضيف": w["added"]})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, column_config={
            "السعر": st.column_config.NumberColumn(format="$%.2f"),
            "تنبيه فوق": st.column_config.NumberColumn(format="$%.2f"),
            "تنبيه تحت": st.column_config.NumberColumn(format="$%.2f")})
        st.caption("التنبيه يوصل تيليجرام (إذا مفعّل) ويظهر بالتطبيق، ثم ينمسح عشان ما يتكرر.")
        r1, r2 = st.columns([3, 1])
        rm = r1.selectbox("حذف رمز", [w["symbol"] for w in wl], key="rm_watch")
        r2.write("")
        if r2.button("🗑️ حذف", use_container_width=True):
            engine.remove_watch(rm)
            st.rerun()
        st.page_link("views/radar.py", label="افحص قائمة المراقبة من الرادار", icon="🎯")
