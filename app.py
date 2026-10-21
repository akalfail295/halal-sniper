"""Halal Sniper Ultra Pro — نقطة التشغيل: streamlit run app.py"""
import logging

import streamlit as st

from sniper import db, monitor
from sniper.config import APP_NAME

st.set_page_config(page_title=APP_NAME, page_icon="👑", layout="wide",
                   initial_sidebar_state="collapsed")

import ui  # noqa: E402  (بعد set_page_config)

_log = logging.getLogger("sniper")
if not _log.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    _log.addHandler(_h)
    _log.setLevel(logging.INFO)


@st.cache_resource
def boot():
    db.init_db()
    return True


ui.inject_css()
ui.require_login()
boot()
ui.configure_notifications()
monitor.ensure_started()

pages = {
    "التداول": [
        st.Page("views/dashboard.py", title="الرئيسية", icon="🏠", default=True),
        st.Page("views/radar.py", title="الرادار", icon="🎯"),
        st.Page("views/portfolio.py", title="المحفظة", icon="💼"),
        st.Page("views/orders.py", title="الأوامر والمراقبة", icon="⏳"),
    ],
    "التحليل": [
        st.Page("views/performance.py", title="الأداء والسجل", icon="📊"),
        st.Page("views/backtest.py", title="الباك-تست", icon="🧪"),
        st.Page("views/signals_log.py", title="سجل الإشارات", icon="📡"),
    ],
    "المزيد": [
        st.Page("views/halal.py", title="الشريعة والزكاة", icon="☪️"),
        st.Page("views/settings.py", title="الإعدادات", icon="⚙️"),
        st.Page("views/guide.py", title="الدليل", icon="📘"),
    ],
}
st.navigation(pages, position="top").run()
