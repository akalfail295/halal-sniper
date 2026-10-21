"""مراقب خلفي يشتغل طول ما السيرفر شغال، حتى لو ما في صفحة مفتوحة.

يدير: الوقف المتحرك والجني الآلي، الأوامر المعلقة، تنبيهات السعر، لقطة المحفظة اليومية،
إعادة الفحص الشرعي، النسخ الاحتياطي، الفحص الصباحي، التقرير الأسبوعي، وبوت تيليجرام.
"""
import datetime
import logging
import threading
import time

from . import data, db, engine, halal, notify, signals
from .config import MODES
from .db import meta_get, meta_set, q
from .universe import LEADERS

log = logging.getLogger("sniper.monitor")

NAME = "sniper-monitor"
BOT_NAME = "sniper-telegram"
_STOP = threading.Event()


def _running(name):
    return any(t.name == name and t.is_alive() for t in threading.enumerate())


def ensure_started():
    if not _running(NAME):
        threading.Thread(target=_loop, name=NAME, daemon=True).start()
    if notify.enabled() and not _running(BOT_NAME):
        threading.Thread(target=_bot_loop, name=BOT_NAME, daemon=True).start()


def heartbeat_age():
    hb = meta_get("monitor_heartbeat", None)
    return None if hb is None else time.time() - float(hb)


def _job_due(name, key):
    jobs = meta_get("jobs", {}) or {}
    return jobs.get(name) != key


def _job_done(name, key):
    jobs = meta_get("jobs", {}) or {}
    jobs[name] = key
    meta_set("jobs", jobs)


def _emit(events, prefix="Halal Sniper: "):
    for e in events:
        notify.notify(prefix + e)


def daily_jobs(S):
    today = str(datetime.date.today())
    if S.get("auto_backup", True) and _job_due("backup", today):
        db.daily_backup()
        _job_done("backup", today)
    if S.get("halal_recheck", True) and _job_due("halal", today):
        bad = []
        for sym in sorted({t["symbol"] for t in engine.list_open()}):
            h = halal.halal_screen(sym)
            if h and h["verdict"] == "fail":
                bad.append(sym)
        if bad:
            msg = "☪️ صفقات مفتوحة لم تعد تجتاز الفحص الشرعي: " + ", ".join(bad)
            engine.log_event("halal", msg)
            notify.notify(msg)
        _job_done("halal", today)


def morning_scan(S, now_ny):
    key = str(now_ny.date())
    if not (S.get("auto_scan") and data.market_open(now_ny)
            and now_ny.hour >= int(S.get("auto_scan_hour", 10)) and _job_due("auto_scan", key)):
        return
    _job_done("auto_scan", key)
    mode = next(m for m in MODES if m[3] == "1d")
    assets = [(s, "Stock") for s in LEADERS]
    results = signals.run_scan(assets, mode, data.market_state(), S)
    strong = engine.save_signals(results, mode[1])
    top = [r["الرمز"] + " (" + str(r["score_num"]) + ")" for r in results if r["priority"] <= 2][:8]
    msg = "🌅 الفحص الصباحي: " + (", ".join(top) if top else "لا توجد إشارات شراء اليوم.")
    engine.log_event("scan", msg)
    notify.notify(msg + ("\n🔥 قوية جديدة: " + ", ".join(strong) if strong else ""))


def weekly_report(S, now_ny):
    key = now_ny.strftime("%G-W%V")
    if not (S.get("weekly_report", True) and now_ny.weekday() == 4
            and now_ny.hour * 60 + now_ny.minute >= 16 * 60 + 15 and _job_due("weekly", key)):
        return
    _job_done("weekly", key)
    notify.notify(build_weekly_report())


def build_weekly_report():
    eq = engine.get_equity()
    since = (datetime.date.today() - datetime.timedelta(days=7))
    old = q("SELECT equity FROM equity_history WHERE day<=? ORDER BY day DESC LIMIT 1", (str(since),))
    rows = q("SELECT pnl FROM closed_trades WHERE closed>=?", (str(since),))
    pnls = [r["pnl"] for r in rows]
    wins = sum(1 for p in pnls if p > 0)
    lines = ["📊 التقرير الأسبوعي — Halal Sniper",
             "قيمة المحفظة: ${:,.2f}".format(eq)]
    if old:
        lines.append("تغير الأسبوع: {:+.2f}%".format((eq / old[0]["equity"] - 1) * 100))
    lines.append("صفقات مغلقة: {} | صافي: {} | نسبة ربح: {}".format(
        len(pnls), engine.usd(sum(pnls)), "{:.0f}%".format(wins / len(pnls) * 100) if pnls else "-"))
    lines.append("صفقات مفتوحة: {}".format(len(engine.list_open())))
    return "\n".join(lines)


def tick(S):
    mkt = data.market_state()
    events = engine.refresh_open_positions(S)
    events += engine.process_orders(S, mkt, halal_fn=halal.halal_screen)
    events += engine.check_watch_alerts()
    _emit(events)
    engine.snapshot_equity()
    daily_jobs(S)
    now_ny = data.ny_now()
    morning_scan(S, now_ny)
    weekly_report(S, now_ny)


def _loop():
    log.info("monitor started")
    while not _STOP.is_set():
        S = engine.load_settings()
        try:
            meta_set("monitor_heartbeat", time.time())
            tick(S)
        except Exception:
            log.exception("monitor tick failed")
        wait = S.get("monitor_secs", 20) if data.market_open() else 120
        _STOP.wait(max(5, int(wait)))


def _bot_loop():
    log.info("telegram bot started")
    offset = int(meta_get("tg_offset", 0) or 0)
    while not _STOP.is_set() and notify.enabled():
        t0 = time.time()
        updates = notify.get_updates(offset)
        if not updates and time.time() - t0 < 2:
            time.sleep(10)  # الشبكة أو التوكن فيها مشكلة: لا نكرر الطلب بسرعة
        for u in updates:
            offset = max(offset, int(u.get("update_id", 0)) + 1)
            meta_set("tg_offset", offset)
            msg = u.get("message") or {}
            if str((msg.get("chat") or {}).get("id")) != notify.CONFIG["chat_id"]:
                continue
            try:
                reply = notify.handle_command(msg.get("text", ""))
            except Exception:
                log.exception("telegram command failed")
                reply = "صار خطأ أثناء تنفيذ الأمر."
            if reply:
                notify.send_telegram(reply)


def stop():
    _STOP.set()
