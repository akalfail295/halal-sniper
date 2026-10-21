"""تنبيهات تيليجرام + بوت أوامر بسيط (يرد فقط على رقم المحادثة المسجّل)."""
import datetime
import json
import logging
import urllib.parse
import urllib.request

log = logging.getLogger("sniper.notify")

CONFIG = {"token": None, "chat_id": None}


def configure(token, chat_id):
    CONFIG["token"] = (token or "").strip() or None
    CONFIG["chat_id"] = str(chat_id).strip() if chat_id else None


def enabled():
    return bool(CONFIG["token"] and CONFIG["chat_id"])


def _api(method, params, timeout=10):
    url = "https://api.telegram.org/bot" + CONFIG["token"] + "/" + method
    body = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(url, data=body, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def send_telegram(msg):
    if not enabled():
        return False
    try:
        _api("sendMessage", {"chat_id": CONFIG["chat_id"], "text": msg[:4000]})
        return True
    except Exception as e:
        # لا نسجّل الرابط لأنه يحتوي التوكن
        log.warning("telegram send failed: %s", type(e).__name__)
        return False


def notify(msg):
    return send_telegram(msg)


def get_updates(offset, timeout=25):
    try:
        res = _api("getUpdates", {"offset": offset, "timeout": timeout,
                                  "allowed_updates": json.dumps(["message"])}, timeout=timeout + 10)
        return res.get("result", []) if res.get("ok") else []
    except Exception as e:
        log.debug("telegram poll: %s", type(e).__name__)
        return []


HELP = ("أوامر Halal Sniper:\n"
        "/status — ملخص المحفظة\n"
        "/positions — الصفقات المفتوحة\n"
        "/close AAPL — إغلاق صفقة بالسعر الحالي\n"
        "/orders — الأوامر المعلقة\n"
        "/watch AAPL — إضافة لقائمة المراقبة\n"
        "/signals — إشارات اليوم القوية")


def handle_command(text):
    """ينفذ أمر من البوت على المحفظة التجريبية ويرجّع الرد."""
    from . import data, engine
    from .db import q

    parts = (text or "").strip().split()
    if not parts:
        return None
    cmd = parts[0].split("@")[0].lower()
    arg = parts[1].upper() if len(parts) > 1 else ""
    S = engine.load_settings()

    if cmd in ("/start", "/help"):
        return HELP
    if cmd == "/status":
        eq, base = engine.get_equity(), engine.get_initial()
        trades = engine.list_open()
        heat = engine.open_heat(trades) / eq * 100 if eq > 0 else 0
        return ("💼 قيمة المحفظة: ${:,.2f} ({:+.2f}%)\n💵 الكاش: ${:,.2f}\n📂 صفقات مفتوحة: {}\n"
                "🔥 المخاطرة المفتوحة: {:.2f}%").format(eq, (eq / base - 1) * 100 if base else 0,
                                                     engine.get_cash(), len(trades), heat)
    if cmd == "/positions":
        trades = engine.list_open()
        if not trades:
            return "لا توجد صفقات مفتوحة."
        lines = []
        for t in trades:
            pnl = engine.trade_pnl(t)
            lines.append("{} {} | ${:,.2f} → ${:,.2f} | {} | وقف ${:,.2f}".format(
                "🔴" if t["direction"] == "short" else "🟢", t["symbol"], t["entry"], t["current"],
                engine.usd(pnl), t["sl"]))
        return "\n".join(lines)
    if cmd == "/close":
        tr = next((t for t in engine.list_open() if t["symbol"] == arg), None)
        if not tr:
            return "ما في صفقة مفتوحة على " + (arg or "؟")
        p = data.fetch_last_price(arg) or tr["current"]
        net = engine.close_position(S, tr["id"], p, "إغلاق من تيليجرام", 1.0)
        return "تم إغلاق " + arg + " | الصافي: " + engine.usd(net)
    if cmd == "/orders":
        orders = engine.list_orders("open")
        if not orders:
            return "لا توجد أوامر معلقة."
        return "\n".join("{} {} @ ${:,.2f} (ينتهي {})".format(o["symbol"],
                         engine.ORDER_KINDS.get(o["kind"], o["kind"]), o["trigger"], o["expires"])
                         for o in orders)
    if cmd == "/watch":
        if not arg:
            return "اكتب الرمز: /watch AAPL"
        engine.add_watch(arg)
        return "أضفت " + arg + " لقائمة المراقبة."
    if cmd == "/signals":
        rows = q("SELECT symbol, decision, price FROM signals WHERE day=? ORDER BY priority, score DESC",
                 (str(datetime.date.today()),))
        if not rows:
            return "ما في إشارات اليوم."
        return "\n".join("{} | {} | ${:,.2f}".format(r["symbol"], r["decision"], r["price"])
                         for r in rows[:15])
    return "أمر غير معروف.\n" + HELP
