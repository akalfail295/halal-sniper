import datetime
import math

import pandas as pd
import streamlit as st

import ui
from sniper import backtest as bt
from sniper import charts, data, engine
from sniper.db import meta_set
from sniper.universe import ALL_ASSETS, LEADERS

S = engine.load_settings()

st.title("🧪 الباك-تست (يومي) مع اختبار خارج العينة")
st.caption("يحاكي نفس التنفيذ الحي: دخول على افتتاح اليوم التالي للإشارة + وقف ATR متحرك + تعادل عند +1R + "
           "جني 50% (لو مفعّل) + عمولة وانزلاق + فلتر SPY فوق SMA200. أول 60% من الزمن تحقق وآخر 40% "
           "اختبار خارجي. الأخبار والأرباح غير متاحة تاريخياً.")

b1, b2, b3 = st.columns(3)
with b1:
    years = {"5 سنوات": 5, "10 سنوات": 10, "سنتين": 2}[st.selectbox("المدة", ["5 سنوات", "10 سنوات", "سنتين"])]
with b2:
    bt_prio = st.selectbox("الإشارات", ["STRONG BUY فقط", "STRONG BUY + BUY NOW"])
with b3:
    bt_scope = st.selectbox("الأسهم", ["25 قيادي", "كل الـ " + str(len(ALL_ASSETS))])
bt_hold = st.slider("أقصى مدة احتفاظ (شموع)", 5, 60, 20)
bt_syms = tuple(LEADERS if "25" in bt_scope else [a[0] for a in ALL_ASSETS])
bt_pmax = 1 if "فقط" in bt_prio else 2
start = bt.period_start(years)


@st.cache_data(ttl=3600, show_spinner=False, max_entries=4)
def prepared(syms, yrs):
    hists = data.load_hists(list(syms), yrs)
    spy = data.load_spy(years=yrs + 2)
    return {s: bt.prepare(h, spy) for s, h in hists.items() if h is not None and len(h) > 260}, spy


def _load():
    with st.spinner("جاري تحميل البيانات وحساب المؤشرات (أول مرة تاخذ دقيقة)..."):
        return prepared(bt_syms, years)


def _row(name, s_):
    return {"الفترة": name, "الصفقات": s_["n"], "نسبة الربح %": round(s_["win"], 1),
            "متوسط R": round(s_["avg_r"], 3), "PF": round(s_["pf"], 2) if math.isfinite(s_["pf"]) else None,
            "أقصى تراجع %": round(s_["mdd"], 1), "العائد %": round(s_["ret"], 1)}


if st.button("▶️ شغّل الباك-تست", type="primary", use_container_width=True):
    prep, spy_close = _load()
    trades, per_sym = bt.collect_trades(prep, S, bt_pmax, bt_hold, start)
    full, s_in, s_out = bt.split_stats(trades, S["risk_pct"])
    st.session_state["bt_result"] = {"trades": trades, "per_sym": per_sym, "full": full, "in": s_in,
                                     "out": s_out, "spy": spy_close, "years": years}
    n_oos = s_out["n"] if s_out else 0
    if full:
        meta_set("edge", {
            "date": str(datetime.date.today()), "p_max": bt_pmax,
            "atr_mult": S["atr_mult"], "rr": S["rr"], "scale_out": bool(S.get("auto_scale_out", True)),
            "tt_min": int(S.get("tt_min", 0)), "n_oos": int(n_oos),
            "avg_r_oos": float(s_out["avg_r"]) if s_out else 0.0,
            "pf_oos": float(s_out["pf"]) if s_out and math.isfinite(s_out["pf"]) else (99.0 if s_out else 0.0),
            "n_all": int(full["n"])})

res = st.session_state.get("bt_result")
if res:
    full, s_in, s_out = res["full"], res["in"], res["out"]
    if not full:
        st.warning("ما طلعت صفقات. جرّب إشارات أوسع أو مدة أطول.")
    else:
        tbl = [_row(n, s) for n, s in [("كل الفترة", full), ("أول 60% (تحقق)", s_in),
                                       ("آخر 40% (خارجي)", s_out)] if s]
        st.dataframe(pd.DataFrame(tbl), use_container_width=True, hide_index=True)

        n_oos = s_out["n"] if s_out else 0
        avg_oos = s_out["avg_r"] if s_out else 0.0
        pf_oos = s_out["pf"] if s_out else 0.0
        if n_oos < 30:
            st.warning("عينة الاختبار الخارجي صغيرة (<30). وسّع الأسهم أو المدة.")
        elif avg_oos <= 0 or pf_oos < 1.15:
            st.error("⚠️ غير مربح خارج العينة بعد التكاليف. البوابة مقفلة. لا تعدّل الأرقام لين يطلع حلو (overfitting).")
        elif s_in and s_in["avg_r"] > 0 and avg_oos < 0.3 * s_in["avg_r"]:
            st.warning("الأداء الخارجي أضعف بكثير من فترة التحقق: علامة عدم استقرار.")
        else:
            st.success("✅ مربح خارج العينة. البوابة مفتوحة. هذا لا يضمن المستقبل، ابدأ بحجم صغير.")

        m1, m2 = st.columns(2)
        m1.metric("أسوأ تراجع محتمل (95% مونتي كارلو)", "{:.1f}%".format(bt.mc_drawdown(full["rs"], S["risk_pct"])))
        spy_close = res["spy"]
        if spy_close is not None:
            sp = spy_close[spy_close.index >= pd.Timestamp(bt.period_start(res["years"]))]
            if len(sp) > 1:
                m2.metric("شراء SPY والاحتفاظ بنفس المدة", "{:+.1f}%".format((sp.iloc[-1] / sp.iloc[0] - 1) * 100),
                          "الاستراتيجية ≈ {:+.1f}%".format(full["ret"]), delta_color="off")
        st.caption("جهّز نفسيتك لهالتراجع. لو ما تتحمله، قلل المخاطرة لكل صفقة. العائد محسوب بتسلسل "
                   "الصفقات (تقريبي لأن الصفقات المتزامنة تتداخل).")

        curve = full["curve"]
        st.plotly_chart(charts.equity_vs_benchmark(curve, spy_close, name="الاستراتيجية"), use_container_width=True)
        st.plotly_chart(charts.r_histogram(full["rs"]), use_container_width=True)

        reasons = pd.Series([t["reason"] for t in res["trades"]]).map(
            {"stop": "وقف/متحرك", "target": "الهدف", "time": "وقف زمني"}).value_counts()
        st.caption("أسباب الخروج: " + " | ".join("{} {}".format(k, v) for k, v in reasons.items()))
        st.dataframe(pd.DataFrame(res["per_sym"]).sort_values("متوسط R", ascending=False),
                     use_container_width=True, hide_index=True)
        tdf = pd.DataFrame(res["trades"])
        st.download_button("⬇️ تنزيل صفقات الباك-تست CSV", tdf.to_csv(index=False).encode("utf-8-sig"),
                           file_name="backtest_trades.csv", mime="text/csv")
        st.caption("تحذير: الأسهم الحالية فيها انحياز البقاء (الشركات الفاشلة غير موجودة)، فالنتائج أحلى من "
                   "الواقع قليلاً. بيانات yfinance المجانية قد تحوي أخطاء.")

st.divider()
st.subheader("🧱 اختبار ثبات الإعدادات")
st.caption("يجرّب 12 تركيبة (ATR × RR) ويعرض متوسط R خارج العينة. إذا الربح بخلية وحدة فقط فهو صدفة؛ "
           "الاستراتيجية الحقيقية تربح بمعظم الخلايا المجاورة. هذا الاختبار لا يغيّر البوابة.")
if st.button("🧱 شغّل اختبار الثبات", use_container_width=True):
    prep, _ = _load()
    atr_list, rr_list = [1.5, 2.0, 2.5, 3.0], [1.5, 2.0, 3.0]
    grid = {}
    prog = st.progress(0.0, text="جاري اختبار التركيبات...")
    k = 0
    for a_ in atr_list:
        row_ = {}
        for r_ in rr_list:
            k += 1
            prog.progress(k / (len(atr_list) * len(rr_list)))
            s2 = dict(S, atr_mult=a_, rr=r_)
            tr_, _ = bt.collect_trades(prep, s2, bt_pmax, bt_hold, start)
            _, _, o_ = bt.split_stats(tr_, S["risk_pct"])
            row_["RR " + str(r_)] = round(o_["avg_r"], 3) if (o_ and o_["n"] >= 20) else None
        grid["ATR x" + str(a_)] = row_
    prog.empty()
    gdf = pd.DataFrame(grid).T.astype(float)
    st.markdown("**متوسط R خارج العينة لكل تركيبة**")
    st.plotly_chart(charts.grid_heatmap(gdf), use_container_width=True)
    vals = [v for v in gdf.values.flatten() if v == v]
    if vals:
        pos = sum(1 for v in vals if v > 0)
        st.metric("تركيبات مربحة خارج العينة", str(pos) + " من " + str(len(vals)))
        if pos / len(vals) < 0.6:
            st.error("الربحية هشّة: أقل من 60% من التركيبات تربح. لا تثق بالاستراتيجية.")
        else:
            st.success("الربحية مستقرة نسبياً عبر الإعدادات المجاورة.")
    else:
        st.warning("عينات قليلة. وسّع الأسهم أو المدة.")

st.divider()
st.subheader("📐 هل قالب الترند يحسّن النتائج؟")
st.caption("يقارن الاستراتيجية بدون قالب الترند وبحدود 5 و6 و7 (7 = الأصرم). لا يغيّر البوابة.")
if st.button("📐 قارن قالب الترند", use_container_width=True):
    prep, _ = _load()
    rows_ = []
    for tv in [0, 5, 6, 7]:
        tr_, _ = bt.collect_trades(prep, dict(S, tt_min=tv), bt_pmax, bt_hold, start)
        f_, _, o_ = bt.split_stats(tr_, S["risk_pct"])
        if f_:
            rows_.append({"حد القالب": "معطل" if tv == 0 else str(tv), "كل الصفقات": f_["n"],
                          "متوسط R (كل)": round(f_["avg_r"], 3), "صفقات خارجية": o_["n"] if o_ else 0,
                          "متوسط R (خارجي)": round(o_["avg_r"], 3) if o_ else None,
                          "PF خارجي": round(o_["pf"], 2) if o_ and math.isfinite(o_["pf"]) else None})
    if rows_:
        st.dataframe(pd.DataFrame(rows_), use_container_width=True, hide_index=True)
        st.caption("اختر الحد اللي يحسّن R الخارجي بدون ما تقل الصفقات كثير (<30). لا تختار بناءً على فرق صغير.")
    else:
        st.warning("ما طلعت نتائج كافية.")
