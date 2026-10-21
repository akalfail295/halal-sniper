from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st

import ui
from sniper import analytics, data, engine, halal
from sniper.universe import HALAL_STOCKS, LEADERS, sector_of

st.title("☪️ الشريعة: الفحص والتطهير والزكاة")
st.caption("أدوات تنبيه تقريبية وليست فتوى. للاعتماد الكامل راجع Zoya أو Musaffa أو جهة شرعية موثوقة.")

tab_screen, tab_purify, tab_zakat = st.tabs(["🔍 فحص النسب", "🧼 تطهير الأرباح", "💰 حاسبة الزكاة"])

with tab_screen:
    st.caption("يفحص: الدين ÷ القيمة السوقية < 30% والكاش ÷ القيمة السوقية < 30% (معيار AAOIFI الأحوط)، "
               "باستخدام متوسط القيمة السوقية آخر 24 شهر لما تتوفر البيانات، ويفحص طبيعة النشاط من تصنيف الصناعة. "
               "لا يفحص تفاصيل الدخل المحرّم لكل شركة.")
    open_syms = sorted({t["symbol"] for t in engine.list_open()})
    pools = {"صفقاتي المفتوحة (" + str(len(open_syms)) + ")": open_syms,
             "القياديات (25)": LEADERS, "كل الأسهم (" + str(len(HALAL_STOCKS)) + ")": HALAL_STOCKS}
    c1, c2 = st.columns([3, 1])
    pool_name = c1.radio("المجموعة", list(pools), horizontal=True)
    c2.write("")
    if c2.button("🔍 افحص", type="primary", use_container_width=True):
        pool = pools[pool_name]
        if not pool:
            st.info("ما عندك صفقات مفتوحة.")
        else:
            prog = st.progress(0.0, text="جاري قراءة البيانات المالية...")
            out_rows = []
            with ThreadPoolExecutor(max_workers=8) as ex:
                futs = {ex.submit(halal.halal_screen, s_): s_ for s_ in pool}
                for i, f in enumerate(as_completed(futs), 1):
                    prog.progress(i / len(pool))
                    sym, h = futs[f], f.result()
                    out_rows.append({
                        "الرمز": sym, "القطاع": sector_of(sym), "الصناعة": h.get("industry", ""),
                        "الدين %": round(h["debt"] * 100, 1) if h["debt"] is not None else None,
                        "الكاش %": round(h["cash"] * 100, 1) if h["cash"] is not None else None,
                        "الأساس": h.get("basis", ""),
                        "النتيجة": halal.VERDICT_LABELS.get(h["verdict"], h["verdict"]),
                        "ملاحظة": h.get("watch", "")})
            prog.empty()
            st.session_state["halal_rows"] = sorted(out_rows, key=lambda r: (r["النتيجة"], r["الرمز"]))
    if st.session_state.get("halal_rows"):
        hdf = pd.DataFrame(st.session_state["halal_rows"])
        fails = int((hdf["النتيجة"] == halal.VERDICT_LABELS["fail"]).sum())
        st.metric("لا يجتاز الفحص", str(fails) + " من " + str(len(hdf)))
        st.dataframe(hdf, use_container_width=True, hide_index=True, column_config={
            "الدين %": st.column_config.ProgressColumn("الدين %", min_value=0, max_value=60, format="%.1f%%"),
            "الكاش %": st.column_config.ProgressColumn("الكاش %", min_value=0, max_value=60, format="%.1f%%")})
        st.caption("الشركات تتغير بين ربع وربع. المراقب الخلفي يعيد فحص صفقاتك المفتوحة يومياً وينبهك إذا سهم صار لا يجتاز.")

with tab_purify:
    st.caption("التطهير: إخراج نسبة الدخل غير المباح من الأرباح أو التوزيعات والتصدق بها. النسبة التقديرية هنا = "
               "إيرادات الفوائد ÷ إجمالي الإيرادات من آخر قوائم مالية سنوية. بعض العلماء يرون التطهير على "
               "التوزيعات فقط، وبعضهم على الأرباح الرأسمالية أيضاً.")
    cdf = analytics.closed_df()
    if cdf.empty:
        st.info("لا توجد صفقات مغلقة. تقدر تستخدم الحاسبة اليدوية تحت.")
    else:
        prof = cdf[cdf["pnl"] > 0].groupby("symbol")["pnl"].sum()
        if prof.empty:
            st.info("ما في أرباح محققة لحد الآن.")
        else:
            if st.button("احسب التطهير التقديري لأرباحي المحققة", use_container_width=True):
                with st.spinner("جاري قراءة القوائم المالية..."):
                    with ThreadPoolExecutor(max_workers=8) as ex:
                        ratios = dict(zip(prof.index, ex.map(halal.impure_income_ratio, prof.index)))
                rows = []
                for sym, p in prof.items():
                    r = ratios.get(sym)
                    rows.append({"الرمز": sym, "الربح المحقق $": round(p, 2),
                                 "نسبة الدخل غير المباح %": None if r is None else round(r * 100, 2),
                                 "مبلغ التطهير $": None if r is None else round(halal.purification_amount(p, r), 2)})
                pdf = pd.DataFrame(rows)
                st.dataframe(pdf, use_container_width=True, hide_index=True)
                st.metric("إجمالي التطهير التقديري", ui.money(pdf["مبلغ التطهير $"].fillna(0).sum()))
                if pdf["نسبة الدخل غير المباح %"].isna().any():
                    st.caption("الرموز بدون نسبة: البيانات غير متوفرة، راجع Zoya أو Musaffa.")
    st.markdown("##### 🧮 حاسبة يدوية")
    m1, m2 = st.columns(2)
    amt = m1.number_input("المبلغ (ربح أو توزيعات) $", min_value=0.0, value=1000.0, step=100.0)
    ratio = m2.number_input("نسبة الدخل غير المباح %", min_value=0.0, max_value=100.0, value=3.0, step=0.1)
    st.metric("مبلغ التطهير", ui.money(halal.purification_amount(amt, ratio / 100.0)))

with tab_zakat:
    st.caption("للمضارب (نية البيع والشراء): الزكاة على القيمة السوقية الكاملة للأسهم + الكاش عند حولان الحول، "
               "إذا بلغ المجموع النصاب (قيمة 85 غرام ذهب). 2.5% للسنة الهجرية أو 2.577% للميلادية.")
    eq = engine.get_equity()
    gram = data.gold_gram_price()
    z1, z2, z3 = st.columns(3)
    value = z1.number_input("قيمة المحفظة الزكوية $", min_value=0.0, value=round(eq, 2), step=100.0)
    gram_in = z2.number_input("سعر غرام الذهب $", min_value=0.0, value=round(gram or 0.0, 2), step=1.0,
                              help="يُجلب تلقائياً من عقود الذهب الآجلة (GC=F).")
    lunar = z3.radio("نوع السنة", ["هجرية", "ميلادية"], horizontal=True) == "هجرية"
    other = st.number_input("أموال زكوية أخرى (كاش خارج التطبيق، ذهب...) $", min_value=0.0, value=0.0, step=100.0)
    z = halal.zakat(value + other, gram_in or None, lunar)
    r1, r2, r3 = st.columns(3)
    r1.metric("النصاب", "-" if z["nisab"] is None else ui.money(z["nisab"]))
    r2.metric("المجموع", ui.money(value + other))
    r3.metric("الزكاة الواجبة", ui.money(z["amount"]),
              "بلغ النصاب" if z["due"] else "لم يبلغ النصاب", delta_color="off")
    st.caption("هذه حسبة تقريبية للتذكير. للمستثمر طويل الأجل طرق أخرى (زكاة الموجودات الزكوية للشركة). "
               "استشر مختصاً لحالتك.")
