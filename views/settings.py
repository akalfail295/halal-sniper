import datetime

import streamlit as st

import ui
from sniper import db, engine, monitor, notify

S = engine.load_settings()

st.title("⚙️ الإعدادات")
ui.flash()

t_risk, t_auto, t_backup, t_danger = st.tabs(["🛡️ المخاطرة والتكاليف", "🤖 الأتمتة والتنبيهات",
                                              "💾 النسخ الاحتياطي", "⚠️ منطقة الخطر"])

with t_risk:
    with st.form("risk"):
        g1, g2 = st.columns(2)
        with g1:
            n_risk = st.number_input("المخاطرة لكل صفقة (%)", 0.1, 5.0, float(S["risk_pct"]), 0.1)
            n_atr = st.number_input("مضاعف ATR للوقف", 0.5, 6.0, float(S["atr_mult"]), 0.25)
            n_rr = st.number_input("نسبة الهدف للوقف (RR)", 0.5, 6.0, float(S["rr"]), 0.25)
            n_open = st.number_input("أقصى صفقات مفتوحة", 1, 30, int(S["max_open"]), 1)
            n_sec = st.number_input("أقصى صفقات بالقطاع الواحد", 1, 10, int(S["max_per_sector"]), 1)
            n_heat = st.number_input("أقصى مخاطرة مفتوحة إجمالية (%)", 0.5, 20.0, float(S["max_heat_pct"]), 0.5)
            n_tt = st.number_input("حد قالب الترند (0 = معطل، 7 = صارم)", 0, 7, int(S.get("tt_min", 0)), 1)
        with g2:
            n_dl = st.number_input("حد الخسارة اليومي (%)", 0.5, 20.0, float(S["daily_loss_pct"]), 0.5)
            n_pos = st.number_input("أقصى حجم صفقة (%)", 1.0, 100.0, float(S["max_pos_pct"]), 1.0)
            n_hold = st.number_input("وقف زمني للسوينغ (أيام)", 1, 120, int(S["max_hold_days"]), 1)
            n_hold_h = st.number_input("وقف زمني للمضاربة اللحظية (ساعات)", 1, 72, int(S.get("max_hold_hours", 6)), 1)
            n_dd = st.number_input("تقليص المخاطرة بعد تراجع (%)", 2.0, 40.0, float(S["dd_cut_pct"]), 1.0)
            n_comm = st.number_input("عمولة % لكل جهة", 0.0, 1.0, float(S["commission_pct"]), 0.01)
            n_slip = st.number_input("انزلاق % لكل جهة", 0.0, 1.0, float(S["slippage_pct"]), 0.01)
        n_auto50 = st.checkbox("✂️ جني الأرباح الآلي (بيع 50% عند منتصف الهدف وتأمين الدخول)",
                               value=bool(S.get("auto_scale_out", True)))
        n_halal = st.checkbox("☪️ امنع الدخول إذا السهم لا يجتاز الفحص الشرعي", value=bool(S.get("halal_gate", True)))
        n_gate = st.checkbox("🔒 بوابة الجدوى: امنع الدخول إلا إذا الباك-تست مربح", value=bool(S["edge_gate"]))
        n_short = st.checkbox("تفعيل البيع على المكشوف (Short)", value=bool(S["allow_short"]))
        st.caption("تنبيه شرعي: الشورت فيه اقتراض أسهم وفوائد ولا تجيزه المجامع الفقهية. الأصل تركه معطلاً.")
        new_cap = st.number_input("رأس المال الإجمالي ($)", 100.0, value=float(engine.get_initial()), step=1000.0)
        if st.form_submit_button("💾 حفظ الإعدادات", type="primary", use_container_width=True):
            engine.save_settings({
                "risk_pct": n_risk, "atr_mult": n_atr, "rr": n_rr, "max_open": int(n_open),
                "max_per_sector": int(n_sec), "max_heat_pct": n_heat, "daily_loss_pct": n_dl,
                "dd_cut_pct": n_dd, "max_pos_pct": n_pos, "max_hold_days": int(n_hold),
                "max_hold_hours": int(n_hold_h), "commission_pct": n_comm, "slippage_pct": n_slip,
                "auto_scale_out": bool(n_auto50), "edge_gate": bool(n_gate), "tt_min": int(n_tt),
                "halal_gate": bool(n_halal), "allow_short": bool(n_short)})
            engine.set_capital(new_cap)
            ui.set_flash("تم حفظ الإعدادات.")
            st.rerun()

with t_auto:
    alive, age = ui.monitor_status(S)
    if alive:
        st.success("🛰️ المراقب الخلفي شغال — آخر نبضة قبل {:.0f} ثانية.".format(age))
    else:
        st.warning("🛰️ المراقب الخلفي متوقف أو لسه يبدأ.")
        if st.button("إعادة تشغيل المراقب"):
            monitor.ensure_started()
            st.rerun()
    with st.form("auto"):
        a_secs = st.slider("فترة تحديث المراقب أثناء السوق (ثواني)", 5, 120, int(S.get("monitor_secs", 20)), 5)
        a_scan = st.checkbox("🌅 فحص صباحي آلي للقياديات (يومي) + إرسال الإشارات", value=bool(S.get("auto_scan")))
        a_hour = st.slider("ساعة الفحص الصباحي (بتوقيت نيويورك)", 10, 15, int(S.get("auto_scan_hour", 10)))
        a_week = st.checkbox("📊 تقرير أسبوعي كل جمعة بعد الإغلاق", value=bool(S.get("weekly_report", True)))
        a_halal = st.checkbox("☪️ إعادة فحص الصفقات المفتوحة شرعياً كل يوم", value=bool(S.get("halal_recheck", True)))
        a_backup = st.checkbox("💾 نسخة احتياطية يومية تلقائية (آخر 7 أيام)", value=bool(S.get("auto_backup", True)))
        if st.form_submit_button("💾 حفظ", type="primary", use_container_width=True):
            engine.save_settings({"monitor_secs": int(a_secs), "auto_scan": bool(a_scan),
                                  "auto_scan_hour": int(a_hour), "weekly_report": bool(a_week),
                                  "halal_recheck": bool(a_halal), "auto_backup": bool(a_backup)})
            ui.set_flash("تم حفظ إعدادات الأتمتة.")
            st.rerun()

    st.subheader("📲 تيليجرام")
    if notify.enabled():
        st.success("تيليجرام مفعّل. البوت يرد على أوامر: /status /positions /close /orders /watch /signals")
        if st.button("إرسال رسالة تجربة"):
            ok = notify.send_telegram("✅ رسالة تجربة من Halal Sniper — " + datetime.datetime.now().strftime("%H:%M"))
            if ok:
                st.success("انرسلت.")
            else:
                st.error("ما انرسلت. تأكد من التوكن ورقم المحادثة.")
    else:
        st.info("تيليجرام غير مفعّل.")
    with st.expander("طريقة التفعيل"):
        st.markdown(
            "1. افتح **@BotFather** بتيليجرام وأرسل `/newbot` وخذ التوكن.\n"
            "2. أرسل أي رسالة للبوت الجديد، ثم افتح `https://api.telegram.org/bot<TOKEN>/getUpdates` "
            "وخذ رقم `chat.id`.\n"
            "3. أنشئ ملف `.streamlit/secrets.toml` (أو Secrets في Streamlit Cloud) وحط:\n"
            "```toml\nTELEGRAM_TOKEN = \"...\"\nTELEGRAM_CHAT_ID = \"...\"\nAPP_PASSWORD = \"كلمة سر للدخول\"\n```\n"
            "4. أعد تشغيل التطبيق. البوت يرد فقط على رقم المحادثة هذا.")

with t_backup:
    st.download_button("⬇️ تنزيل نسخة احتياطية الآن (.db)", db.backup_bytes(),
                       file_name="halal_sniper_" + datetime.date.today().strftime("%Y%m%d") + ".db",
                       use_container_width=True)
    st.caption("على Streamlit Cloud الملفات تُمسح عند إعادة النشر. نزّل نسخة احتياطية كل أسبوع على الأقل.")
    up = st.file_uploader("استعادة من نسخة احتياطية", type=["db"])
    if up is not None:
        st.warning("الاستعادة تستبدل كل البيانات الحالية (تنحفظ نسخة من الحالية بمجلد backups قبل الاستبدال).")
        if st.button("♻️ استعادة", type="primary"):
            if db.restore_from_bytes(up.getvalue()):
                ui.set_flash("تمت الاستعادة بنجاح.")
                st.rerun()
            st.error("الملف مو قاعدة بيانات صالحة لهالتطبيق.")
    files = sorted(db.BACKUP_DIR.glob("*.db"), reverse=True) if db.BACKUP_DIR.exists() else []
    if files:
        st.caption("النسخ المحلية: " + "، ".join(f.name for f in files[:10]))

with t_danger:
    st.error("تصفير المحفظة يحذف كل الصفقات المفتوحة والمغلقة وسجل المحفظة، ويرجّع الكاش لرأس المال. "
             "الإعدادات وقائمة المراقبة والإشارات تبقى.")
    confirm = st.checkbox("أؤكد أني أبي أصفّر المحفظة بالكامل")
    if st.button("🗑️ تصفير المحفظة", use_container_width=True, disabled=not confirm):
        db.BACKUP_DIR.mkdir(exist_ok=True)
        db.backup_to(db.BACKUP_DIR / ("before_reset_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".db"))
        engine.reset_portfolio()
        ui.set_flash("تم تصفير المحفظة (وانحفظت نسخة احتياطية قبلها).")
        st.rerun()
