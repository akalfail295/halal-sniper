import datetime

import pandas as pd
import streamlit as st

import ui
from sniper import ai, analytics, charts, data, engine, halal, notify, signals
from sniper.config import COLORS as C
from sniper.config import DEFAULT_MODE, MODES
from sniper.indicators import add_indicators, swing_levels
from sniper.universe import ALL_ASSETS, HALAL_FUNDS, LEADERS, is_fund

S = engine.load_settings()

st.title("🎯 الرادار والشارت")
ui.flash()
mkt, blocked, peak, edge = ui.status_banners(S)

labels = [m[0] for m in MODES]
watch = [w["symbol"] for w in engine.list_watch()]
scopes = {
    "⚡ القياديات (" + str(len(LEADERS)) + ")": [(s, "Stock") for s in LEADERS],
    "🌐 الكل (" + str(len(ALL_ASSETS)) + ")": ALL_ASSETS,
    "👀 المراقبة (" + str(len(watch)) + ")": [(s, "ETF" if is_fund(s) else "Stock") for s in watch],
    "🏦 الصناديق (" + str(len(HALAL_FUNDS)) + ")": [(s, "ETF") for s in HALAL_FUNDS],
}

c1, c2, c3 = st.columns([2, 3, 1])
with c1:
    lbl = st.selectbox("⏱️ الفاصل الزمني", labels, index=DEFAULT_MODE, key="radar_mode")
mode = MODES[labels.index(lbl)]
with c2:
    scope = st.radio("نطاق الفحص", list(scopes), horizontal=True, key="radar_scope")
with c3:
    st.write("")
    go_btn = st.button("🚀 افحص الآن", type="primary", use_container_width=True)


def _store(results, mode_):
    st.session_state["scan"] = {"results": results, "mode": mode_,
                                "ts": datetime.datetime.now().strftime("%H:%M")}


if go_btn:
    assets = scopes[scope]
    if not assets:
        st.warning("قائمة المراقبة فاضية. أضف رموز من صفحة الأوامر والمراقبة.")
    else:
        prog = st.progress(0.0, text="جاري تحميل البيانات والتحليل...")
        results = signals.run_scan(assets, mode, mkt, S,
                                   progress=lambda x: prog.progress(min(1.0, x), text="جاري التحليل..."))
        prog.empty()
        _store(results, mode)
        strong = engine.save_signals(results, mode[1])
        if strong:
            notify.notify("Halal Sniper STRONG BUY: " + ", ".join(strong[:8]))
        buys = sum(1 for r in results if r["priority"] <= 2)
        st.success("✅ تم تحليل {} أصل — {} إشارة شراء.".format(len(results), buys))

with st.expander("🔎 تحليل رمز خارج القائمة"):
    k1, k2 = st.columns([3, 1])
    with k1:
        custom = ui.sym_input("الرمز (مثال: ASML)", "custom_sym")
    with k2:
        st.write("")
        custom_go = st.button("حلّل", key="custom_go", use_container_width=True)
    if custom_go and custom:
        with st.spinner("جاري التحليل..."):
            res = signals.run_scan([(custom, "ETF" if is_fund(custom) else "Stock")], mode, mkt, S)
        if res:
            prev = st.session_state.get("scan")
            keep = [r for r in (prev["results"] if prev and prev["mode"] == mode else [])
                    if r["الرمز"] != custom]
            _store(res + keep, mode)
            st.session_state["radar_pick"] = custom
        else:
            st.error("ما قدرت أجيب بيانات كافية لهالرمز على هالفاصل.")

scan = st.session_state.get("scan")
if not scan:
    st.info("اختر الفاصل والنطاق واضغط «افحص الآن».")
    st.stop()

results, smode = scan["results"], scan["mode"]
_, tf_name, period, interval, intraday = smode
if smode != mode:
    st.caption("⚠️ النتائج المعروضة من فحص «" + smode[0] + "». أعد الفحص للفاصل الحالي.")

f1, f2 = st.columns([3, 1])
with f1:
    kw = st.text_input("🔍 تصفية بالرمز", "", key="radar_kw").strip().upper()
with f2:
    st.write("")
    only_buy = st.toggle("إشارات الشراء فقط", key="radar_only_buy")
view = [r for r in results if (not kw or kw in r["الرمز"]) and (not only_buy or r["priority"] <= 2)]
if not view:
    st.info("لا توجد نتائج مطابقة.")
    st.stop()

COLS = ["الرمز", "القرار", "النقاط", "السعر", "التغير %", "القطاع", "النوع", "RSI", "MACD", "السيولة",
        "VWAP", "اختراق", "قوة نسبية", "ترتيب RS", "قالب الترند", "الإطار الأكبر", "الشمعة",
        "الأرباح", "الأخبار", "وقف (ATR)", "الهدف"]
table = pd.DataFrame(view)[[c for c in COLS if c in view[0]]]
st.caption("آخر فحص: " + scan["ts"] + " — اضغط على أي صف لعرض الشارت.")
ev = st.dataframe(
    table, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row",
    key="radar_table", height=min(560, 38 + 35 * len(table)),
    column_config={
        "النقاط": st.column_config.ProgressColumn("النقاط", min_value=0, max_value=100, format="%d"),
        "ترتيب RS": st.column_config.ProgressColumn("ترتيب RS", min_value=0, max_value=99, format="%d"),
        "السعر": st.column_config.NumberColumn(format="$%.2f"),
        "التغير %": st.column_config.NumberColumn(format="%+.2f%%"),
        "وقف (ATR)": st.column_config.NumberColumn(format="$%.2f"),
        "الهدف": st.column_config.NumberColumn(format="$%.2f"),
    })

syms = [r["الرمز"] for r in view]
picked = st.session_state.pop("radar_pick", None)
rows = ev.selection.rows if ev is not None and hasattr(ev, "selection") else []
if rows:
    picked = syms[rows[0]]
default = picked if picked in syms else syms[0]

st.divider()
st.subheader("⚡ الشارت وتذكرة الأمر")
sel = st.selectbox("السهم", syms, index=syms.index(default))
info = next(r for r in view if r["الرمز"] == sel)
price = data.fetch_last_price(sel) or info["raw_price"]

dir_opts = ["🟢 شراء (Long)"] + (["🔴 بيع (Short)"] if S["allow_short"] else [])
direction = "short" if "Short" in st.radio("الاتجاه", dir_opts, horizontal=True) else "long"

equity, cash = engine.get_equity(), engine.get_cash()
scale, scale_notes = engine.risk_scale(S, mkt, peak, equity)
shares, stop_dist = engine.position_size(S, price, info["atr"], equity, cash, scale)
sl, tp, mid = engine.levels(direction, price, stop_dist, S["rr"])

d = None
raw = data.fetch_history(sel, period, interval)
if raw is not None and len(raw) > 30:
    d = add_indicators(raw, intraday=intraday)
    sup, res = swing_levels(d.tail(150))
    cdf = analytics.closed_df()
    past = cdf[cdf["symbol"] == sel] if not cdf.empty else None
    lv = [{"y": price, "label": "الدخول", "color": C["blue"], "dash": "solid"},
          {"y": tp, "label": "الهدف", "color": C["good"]},
          {"y": sl, "label": "الوقف", "color": C["critical"]}]
    if S.get("auto_scale_out", True):
        lv.insert(1, {"y": mid, "label": "جني النصف", "color": C["warning"], "dash": "dot"})
    st.plotly_chart(charts.price_chart(d, lv, past, sup, res, intraday), use_container_width=True)
else:
    st.warning("تعذر تحميل الشارت لهالفاصل.")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("السعر اللحظي", ui.money(price))
m2.metric("الأسهم المحسوبة", format(shares, "g"))
m3.metric("المبلغ المطلوب", "${:,.0f}".format(shares * price))
m4.metric("المخاطرة الفعلية", ui.money(shares * stop_dist))
m5.metric("العائد المتوقع", ui.money(shares * stop_dist * S["rr"]), "{:.1f}R".format(S["rr"]),
          delta_color="off")
if scale_notes:
    st.warning("تم تقليص المخاطرة تلقائياً بسبب: " + " + ".join(scale_notes))
st.info(ui.esc("📌 " + sel + " | " + info["القرار"] + " | النقاط " + str(info["score_num"])
               + "/100 | وقف: $" + format(sl, ",.2f") + " | هدف: $" + format(tp, ",.2f")))

hs = halal.halal_screen(sel)
if hs["verdict"] == "fund":
    st.success("☪️ " + hs["watch"])
elif hs["verdict"] == "fail" and hs["debt"] is not None:
    st.error("☪️ لا يجتاز الفحص: دين {:.0f}% / كاش {:.0f}% من القيمة السوقية ({}) — الحد 30%.".format(
        hs["debt"] * 100, hs["cash"] * 100, hs["basis"]))
elif hs["verdict"] == "fail":
    st.error("☪️ لا يجتاز الفحص الشرعي.")
elif hs["verdict"] == "review":
    st.warning("☪️ بيانات النسب غير متاحة. راجع Zoya أو Musaffa قبل الدخول.")
else:
    st.success("☪️ نسب الدين والكاش ضمن الحد: دين {:.0f}% / كاش {:.0f}% ({}) — تقريبي وليس فتوى.".format(
        hs["debt"] * 100, hs["cash"] * 100, hs["basis"]))
if hs.get("watch") and hs["verdict"] != "fund":
    st.warning("☪️ " + hs["watch"])

if info.get("headlines"):
    with st.expander("📰 أحدث الأخبار — " + info["الأخبار"]):
        for hd in info["headlines"]:
            title = ui.esc(hd["title"].replace("[", "(").replace("]", ")"))
            st.markdown("• [" + title + "](" + hd["link"] + ")  \n<small>" + hd["date"] + "</small>",
                        unsafe_allow_html=True)

api_key = ui.secret("ANTHROPIC_API_KEY")
ai_key = "ai_" + sel + "_" + tf_name
if ai.available(api_key):
    if st.button("🤖 تحليل ذكي للسهم (Claude)", use_container_width=True):
        with st.spinner("Claude يحلل الأخبار والمؤشرات..."):
            text, err = ai.analyze(info, api_key)
        if err:
            st.error(err)
        else:
            st.session_state[ai_key] = text
    if st.session_state.get(ai_key):
        with st.container(border=True):
            st.markdown(ui.esc(st.session_state[ai_key]))
            st.caption("تحليل آلي تعليمي وليس نصيحة استثمارية.")
else:
    st.caption("🤖 التحليل الذكي (تلخيص الأخبار وشرح الإشارة بالعربي) يتفعّل إذا أضفت ANTHROPIC_API_KEY في الإعدادات السرية.")

st.markdown("#### 🧾 تذكرة الأمر")
otype = st.radio("نوع الأمر", ["⚡ تنفيذ فوري", "⏳ معلق عند الاختراق", "⏳ معلق عند التراجع"],
                 horizontal=True)
pending = otype != "⚡ تنفيذ فوري"
kind = "stop" if "الاختراق" in otype else "limit"
if d is not None and pd.notna(d["High20"].iloc[-1]):
    hi20, lo20 = float(d["High20"].iloc[-1]), float(d["Low20"].iloc[-1])
else:
    hi20, lo20 = price * 1.01, price * 0.99
if kind == "stop":
    default_trig = max(hi20, price * 1.002) if direction == "long" else min(lo20, price * 0.998)
else:
    default_trig = price - 0.5 * info["atr"] if direction == "long" else price + 0.5 * info["atr"]

with st.form("ticket"):
    if pending:
        t1, t2 = st.columns(2)
        trigger = t1.number_input("سعر التفعيل ($)", min_value=0.01, value=round(float(default_trig), 2),
                                  step=0.01, format="%.2f")
        days = t2.slider("صلاحية الأمر (أيام)", 1, 30, 5)
        st.caption("الحجم والوقف ينحسبون وقت التفعيل حسب المحفظة والسعر الفعلي.")
    setup = st.text_input("سبب الدخول / النمط", placeholder="مثال: اختراق قمة 20 يوم بفوليوم عالي")
    note = st.text_area("ملاحظة (اختياري)", height=70)
    override = False if pending else st.checkbox("أتجاوز تحذير الإشارة الضعيفة / السوق الهابط")
    submit = st.form_submit_button("⏳ ضع الأمر المعلق" if pending else "🚀 نفّذ الصفقة الآن",
                                   type="primary", use_container_width=True)

if submit:
    if pending:
        probe = {"kind": kind, "direction": direction, "trigger": trigger}
        if direction == "short" and not S["allow_short"]:
            st.error("البيع على المكشوف معطل من الإعدادات.")
        elif engine.order_triggered(probe, price):
            st.warning("السعر الحالي يحقق شرط التفعيل فعلاً. استخدم التنفيذ الفوري أو غيّر السعر.")
        else:
            engine.place_order(sel, direction, kind, trigger, info["atr"], tf_name, info["priority"],
                               days, note=(setup + " — " + note).strip(" —"))
            ui.set_flash("⏳ تم وضع أمر معلق على " + sel + " @ $" + format(trigger, ",.2f"))
            st.rerun()
    else:
        err = engine.entry_error(S, sel, direction, shares, stop_dist, info["priority"], mkt, override,
                                 interval, blocked, edge, hs["verdict"], equity)
        if err:
            st.error(err)
        else:
            ok, msg = engine.open_position(S, sel, direction, price, shares, info["atr"], tf_name,
                                           note=note, setup=setup)
            if ok:
                ui.set_flash("✅ تم فتح صفقة " + sel + " بنجاح!")
                st.rerun()
            st.error(msg)

b1, b2 = st.columns(2)
with b1:
    if st.button("👀 أضف لقائمة المراقبة", use_container_width=True, disabled=sel in watch):
        engine.add_watch(sel, note="من الرادار: " + info["القرار"])
        ui.set_flash("أضفت " + sel + " لقائمة المراقبة.")
        st.rerun()
with b2:
    st.link_button("📈 فتح في TradingView", ui.tv_link(sel), use_container_width=True)
