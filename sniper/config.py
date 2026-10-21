"""الإعدادات الافتراضية والفواصل الزمنية والألوان."""

APP_NAME = "Halal Sniper Ultra Pro"

DEFAULTS = {
    # المخاطرة
    "risk_pct": 1.0,            # المخاطرة لكل صفقة % من المحفظة
    "atr_mult": 2.0,            # مضاعف ATR للوقف
    "rr": 2.0,                  # الهدف ÷ الوقف
    "max_open": 8,
    "max_per_sector": 2,
    "max_heat_pct": 6.0,        # أقصى مخاطرة مفتوحة إجمالية %
    "daily_loss_pct": 3.0,
    "dd_cut_pct": 10.0,         # تقليص المخاطرة للنصف بعد هذا التراجع من القمة
    "max_pos_pct": 20.0,        # أقصى حجم صفقة % من المحفظة
    "max_hold_days": 20,
    "max_hold_hours": 6,        # وقف زمني لصفقات الفواصل اللحظية
    "commission_pct": 0.05,
    "slippage_pct": 0.05,
    # الأتمتة والبوابات
    "auto_scale_out": True,
    "edge_gate": True,
    "tt_min": 0,
    "halal_gate": True,
    "allow_short": False,
    # المراقب الخلفي والتنبيهات
    "monitor_secs": 20,
    "auto_scan": False,         # فحص صباحي آلي للقياديات
    "auto_scan_hour": 10,       # بتوقيت نيويورك
    "weekly_report": True,
    "halal_recheck": True,
    "auto_backup": True,
}

# (العنوان، اسم الإطار، المدة، الفاصل، لحظي؟)
MODES = [
    ("⚡ 1m - خطف لحظي", "خطف لحظي (1 دقيقة)", "5d", "1m", True),
    ("🔥 5m - مضاربة سريعة", "مضاربة (5 دقائق)", "5d", "5m", True),
    ("📈 15m - مضاربة ربع ساعة", "مضاربة (15 دقيقة)", "1mo", "15m", True),
    ("⏱️ 30m - مضاربة نصف ساعة", "مضاربة (30 دقيقة)", "1mo", "30m", True),
    ("🕐 1h - مضاربة ساعية", "مضاربة ساعية (1 ساعة)", "1y", "1h", True),
    ("🎯 1D - سوينغ يومي", "سوينغ يومي (1 يوم)", "2y", "1d", False),
    ("📅 1W - سوينغ أسبوعي", "سوينغ أسبوعي (1 أسبوع)", "5y", "1wk", False),
    ("🏦 1M - استثمار شهري", "استثمار شهري (1 شهر)", "max", "1mo", False),
]
DEFAULT_MODE = 5

INTRADAY_TF = {m[1] for m in MODES if m[4]}

DECISIONS = {
    1: "🔥 STRONG BUY",
    2: "🟢 BUY NOW",
    3: "🟡 مراقبة",
    4: "⚪ انتظار",
    5: "🔴 تجنب",
}

# ألوان الرسوم (الوضع الداكن) — مأخوذة من لوحة ألوان مختبرة لعمى الألوان
COLORS = {
    "surface": "rgba(0,0,0,0)",
    "grid": "#2c2c2a",
    "axis": "#383835",
    "text": "#c3c2b7",
    "muted": "#898781",
    "blue": "#3987e5",
    "orange": "#d95926",
    "aqua": "#199e70",
    "yellow": "#c98500",
    "violet": "#9085e9",
    "red": "#e66767",
    "good": "#0ca30c",
    "warning": "#fab219",
    "critical": "#d03b3b",
    "neutral": "#383835",
}
