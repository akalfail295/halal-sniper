import io

import pandas as pd
import streamlit as st

import ui
from sniper import analytics, charts, data, engine
from sniper.db import q

st.title("📊 الأداء والسجل")
ui.flash()

df_all = analytics.closed_df()
if df_all.empty:
    st.info("لا توجد صفقات مغلقة بعد. أول ما تقفل صفقة يبدأ التحليل هنا.")
    st.stop()

# صف فلاتر واحد فوق كل الرسوم
f1, f2, f3 = st.columns(3)
with f1:
    rng = st.selectbox("الفترة", ["الكل", "آخر 30 يوم", "آخر 90 يوم", "آخر سنة"])
with f2:
    dirs = st.selectbox("الاتجاه", ["الكل", "شراء", "شورت"])
with f3:
    tfs = st.selectbox("الإطار", ["الكل"] + sorted(df_all["timeframe"].dropna().unique().tolist()))
df = df_all.copy()
days = {"آخر 30 يوم": 30, "آخر 90 يوم": 90, "آخر سنة": 365}.get(rng)
if days:
    df = df[df["closed_dt"] >= pd.Timestamp.now() - pd.Timedelta(days=days)]
if dirs != "الكل":
    df = df[df["direction"] == ("short" if dirs == "شورت" else "long")]
if tfs != "الكل":
    df = df[df["timeframe"] == tfs]
if df.empty:
    st.info("ما في صفقات بهالفلتر.")
    st.stop()

initial = engine.get_initial()
eqh = analytics.equity_history()
filtered = rng != "الكل" or dirs != "الكل" or tfs != "الكل"
curve = analytics.realized_curve(df, initial) if filtered or len(eqh) < 10 else eqh
sm = analytics.summary(df, curve)

k = st.columns(4)
k[0].metric("صافي الربح", ui.money(sm["net"], True))
k[1].metric("نسبة الربح", "{:.0f}%".format(sm["win_rate"]))
k[2].metric("متوسط R", "{:+.2f}R".format(sm["avg_r"]))
k[3].metric("Profit Factor", "∞" if sm["pf"] == float("inf") else "{:.2f}".format(sm["pf"]))
k = st.columns(4)
k[0].metric("التوقع لكل صفقة", ui.money(sm["expectancy"], True))
k[1].metric("أقصى تراجع", "{:.1f}%".format(sm["mdd"]))
k[2].metric("Sharpe (سنوي)", "-" if sm["sharpe"] is None else "{:.2f}".format(sm["sharpe"]))
k[3].metric("متوسط مدة الصفقة", "-" if sm["avg_hold_h"] is None else (
    "{:.1f} ساعة".format(sm["avg_hold_h"]) if sm["avg_hold_h"] < 48 else "{:.1f} يوم".format(sm["avg_hold_h"] / 24)))
st.caption(ui.esc("الصفقات: {} | متوسط الربح {} | متوسط الخسارة {} | أفضل {} | أسوأ {} | "
                  "أطول سلسلة خسائر {} | العمولات {}".format(
                      sm["n"], ui.money(sm["avg_win"]), ui.money(sm["avg_loss"]), ui.money(sm["best"], True),
                      ui.money(sm["worst"], True), sm["max_loss_streak"], ui.money(sm["fees"]))))

st.subheader("📈 المحفظة مقابل SPY")
spy = data.load_spy(years=5)
st.plotly_chart(charts.equity_vs_benchmark(curve, spy), use_container_width=True)
st.caption("المنحنى من {}.".format("سجل المحفظة اليومي" if curve is eqh else "الأرباح المحققة (الصفقات المغلقة)"))
st.plotly_chart(charts.drawdown_chart(analytics.drawdown(curve)), use_container_width=True)

st.subheader("🗓️ الأرباح الشهرية")
mt = analytics.monthly_table(df)
if not mt.empty:
    st.plotly_chart(charts.monthly_heatmap(mt), use_container_width=True)
    with st.expander("عرض كجدول"):
        st.dataframe(mt.round(2), use_container_width=True)

st.subheader("🔬 التفصيل")
dims = [("symbol", "الرمز"), ("sector", "القطاع"), ("timeframe", "الإطار"), ("reason", "سبب الخروج"),
        ("weekday", "يوم الدخول"), ("direction", "الاتجاه"), ("setup", "النمط")]
tabs = st.tabs([lbl for _, lbl in dims])
for (col, lbl), tab in zip(dims, tabs):
    with tab:
        sub = df.copy()
        if col == "setup":
            sub[col] = sub[col].replace("", "بدون")
        b = analytics.breakdown(sub, col, lbl)
        st.plotly_chart(charts.signed_bars(b[lbl].astype(str).tolist()[::-1], b["الصافي $"].tolist()[::-1],
                                           horizontal=True, height=max(220, 34 * len(b) + 60)),
                        use_container_width=True)
        st.dataframe(b, use_container_width=True, hide_index=True)

st.subheader("📐 توزيع R")
st.plotly_chart(charts.r_histogram(df["r_mult"].tolist()), use_container_width=True)

st.subheader("📓 يوميات التداول")
st.caption("عدّل الملاحظة أو النمط لأي صفقة واضغط حفظ. التقييم الصادق لكل صفقة أهم أداة للتطور.")
journal = df.sort_values("id", ascending=False)[
    ["id", "symbol", "direction", "timeframe", "entry", "exit", "shares", "pnl", "pnl_pct", "r_mult",
     "reason", "setup", "note", "opened", "closed"]].fillna({"setup": "", "note": ""}).reset_index(drop=True)
edited = st.data_editor(
    journal, use_container_width=True, hide_index=True, key="journal",
    disabled=[c for c in journal.columns if c not in ("setup", "note")],
    column_config={
        "id": None, "symbol": "الرمز", "direction": "الاتجاه", "timeframe": "الإطار",
        "entry": st.column_config.NumberColumn("الدخول", format="$%.2f"),
        "exit": st.column_config.NumberColumn("الخروج", format="$%.2f"),
        "shares": "الأسهم", "pnl": st.column_config.NumberColumn("الصافي $", format="$%+.2f"),
        "pnl_pct": st.column_config.NumberColumn("النسبة %", format="%+.2f%%"),
        "r_mult": st.column_config.NumberColumn("R", format="%+.2f"), "reason": "السبب",
        "setup": st.column_config.TextColumn("النمط"), "note": st.column_config.TextColumn("ملاحظة", width="large"),
        "opened": "فتح", "closed": "إغلاق"})
if st.button("💾 حفظ اليوميات"):
    changed = 0
    for (_, old), (_, new) in zip(journal.iterrows(), edited.iterrows()):
        if (old["note"] or "") != (new["note"] or "") or (old["setup"] or "") != (new["setup"] or ""):
            q("UPDATE closed_trades SET note=?, setup=? WHERE id=?",
              (new["note"] or "", new["setup"] or "", int(old["id"])))
            changed += 1
    ui.set_flash("تم حفظ {} تعديل.".format(changed))
    st.rerun()

e1, e2 = st.columns(2)
export = df_all.drop(columns=["opened_dt", "closed_dt"])
e1.download_button("⬇️ تصدير CSV", export.to_csv(index=False).encode("utf-8-sig"),
                   file_name="closed_trades.csv", mime="text/csv", use_container_width=True)
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as xw:
    export.to_excel(xw, sheet_name="trades", index=False)
    analytics.breakdown(df_all, "symbol", "الرمز").to_excel(xw, sheet_name="by_symbol", index=False)
e2.download_button("⬇️ تصدير Excel", buf.getvalue(), file_name="halal_sniper_report.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   use_container_width=True)
