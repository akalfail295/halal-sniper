import pandas as pd
import streamlit as st

from sniper import data
from sniper.db import q

st.title("📡 سجل الإشارات ونتائجها")
st.caption("كل إشارة شراء (STRONG BUY / BUY NOW) تنحفظ مرة باليوم. هنا تقدر تشوف هل الإشارات فعلاً تربح بعد صدورها.")

srows = q("SELECT * FROM signals ORDER BY id DESC LIMIT 500")
if not srows:
    st.info("لا توجد إشارات محفوظة. شغّل الفحص من الرادار.")
    st.stop()

dfs = pd.DataFrame([dict(r) for r in srows])
tfs = ["الكل"] + sorted(dfs["timeframe"].unique().tolist())
c1, c2 = st.columns([2, 1])
tf = c1.selectbox("الإطار", tfs)
c2.write("")
if c2.button("🔄 حدّث النتائج بالأسعار الحالية", use_container_width=True):
    st.session_state["sig_prices"] = data.fetch_prices(dfs["symbol"].unique().tolist())
if tf != "الكل":
    dfs = dfs[dfs["timeframe"] == tf]

pm = st.session_state.get("sig_prices", {})
if pm:
    dfs["now"] = dfs["symbol"].map(pm)
    dfs["ret"] = (dfs["now"] / dfs["price"] - 1) * 100.0
    g = dfs.dropna(subset=["ret"]).groupby("decision")["ret"].agg(
        ["count", "mean", "median", lambda x: (x > 0).mean() * 100]).reset_index()
    g.columns = ["القرار", "العدد", "متوسط العائد %", "الوسيط %", "نسبة النجاح %"]
    st.dataframe(g.round(2), use_container_width=True, hide_index=True)
    st.caption("العائد من سعر الإشارة للسعر الحالي (بدون وقف أو هدف) — مقياس تقريبي لجودة الإشارة.")

out = dfs.rename(columns={
    "ts": "الوقت", "symbol": "الرمز", "timeframe": "الإطار", "price": "سعر الإشارة",
    "score": "النقاط", "decision": "القرار", "priority": "الأولوية", "now": "السعر الآن", "ret": "العائد %"
}).drop(columns=["id", "day"])
st.dataframe(out, use_container_width=True, hide_index=True, column_config={
    "سعر الإشارة": st.column_config.NumberColumn(format="$%.2f"),
    "السعر الآن": st.column_config.NumberColumn(format="$%.2f"),
    "العائد %": st.column_config.NumberColumn(format="%+.2f%%")})
st.download_button("⬇️ تصدير CSV", out.to_csv(index=False).encode("utf-8-sig"), file_name="signals.csv",
                   mime="text/csv")
