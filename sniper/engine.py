"""محرك المحفظة التجريبية: الصفقات، الحماية، الأوامر المعلقة، المراقبة، والأحداث."""
import datetime
import math

from . import data, db
from .config import DEFAULTS, INTRADAY_TF, MODES
from .db import meta_get, meta_set, now_str, q, tx
from .universe import is_fund, sector_of

TF_INTERVAL = {m[1]: m[3] for m in MODES}


def usd(x, sign=True):
    x = float(x or 0.0)
    return ("-" if x < 0 else ("+" if sign else "")) + "${:,.2f}".format(abs(x))


# =====================================================================
# الإعدادات
# =====================================================================
def load_settings():
    S = dict(DEFAULTS)
    S.update(meta_get("settings", {}) or {})
    return S


def save_settings(new):
    S = load_settings()
    S.update(new)
    meta_set("settings", S)
    return S


# =====================================================================
# الحساب
# =====================================================================
def _one(conn, sql, params=()):
    return (conn.execute(sql, params).fetchall() if conn else q(sql, params))


def get_cash(conn=None):
    return float(_one(conn, "SELECT cash FROM account WHERE id=1")[0]["cash"])


def get_initial(conn=None):
    return float(_one(conn, "SELECT initial FROM account WHERE id=1")[0]["initial"])


def list_open(conn=None):
    return [dict(r) for r in _one(conn, "SELECT * FROM open_trades ORDER BY id")]


def trade_pnl(tr, price=None):
    p = tr["current"] if price is None else price
    if tr["direction"] == "short":
        return (tr["entry"] - p) * tr["shares"]
    return (p - tr["entry"]) * tr["shares"]


def get_equity(conn=None):
    total = get_cash(conn)
    for tr in list_open(conn):
        total += tr["cost"] + trade_pnl(tr)
    return total


def open_heat(trades=None):
    """المخاطرة المفتوحة فعلياً بالدولار (المسافة بين السعر الحالي والوقف)."""
    h = 0.0
    for t in (list_open() if trades is None else trades):
        if t["direction"] == "short":
            h += max(0.0, t["sl"] - t["current"]) * t["shares"]
        else:
            h += max(0.0, t["current"] - t["sl"]) * t["shares"]
    return h


def day_guard(S):
    """يرجّع (محظور اليوم؟، قمة المحفظة)."""
    today = str(datetime.date.today())
    with tx() as c:
        eq = get_equity(c)
        ds = meta_get("day_start", None, c)
        if not ds or ds.get("date") != today:
            ds = {"date": today, "equity": eq}
            meta_set("day_start", ds, c)
        peak = max(float(meta_get("peak_equity", eq, c) or eq), eq)
        meta_set("peak_equity", peak, c)
    limit = ds["equity"] * (1 - S["daily_loss_pct"] / 100.0)
    return eq < limit, peak


def _shift_baselines(c, delta):
    """تعديل رأس المال يحرّك نقطة بداية اليوم والقمة بنفس المقدار (عشان ما ينحسب خسارة)."""
    ds = meta_get("day_start", None, c)
    if ds:
        ds["equity"] = float(ds["equity"]) + delta
        meta_set("day_start", ds, c)
    pk = meta_get("peak_equity", None, c)
    if pk is not None:
        meta_set("peak_equity", max(float(pk) + delta, get_equity(c)), c)


def set_capital(new_cap):
    with tx() as c:
        init, cash = get_initial(c), get_cash(c)
        diff = float(new_cap) - init
        if abs(diff) < 1e-9:
            return 0.0
        new_cash = max(0.0, cash + diff)
        c.execute("UPDATE account SET initial=?, cash=? WHERE id=1", (float(new_cap), new_cash))
        _shift_baselines(c, new_cash - cash)
        log_event("settings", "تعديل رأس المال إلى ${:,.0f}".format(new_cap), c)
        return new_cash - cash


def reset_portfolio():
    with tx() as c:
        c.execute("DELETE FROM open_trades")
        c.execute("DELETE FROM closed_trades")
        c.execute("DELETE FROM equity_history")
        c.execute("DELETE FROM orders")
        c.execute("DELETE FROM events")
        c.execute("UPDATE account SET cash=initial WHERE id=1")
        init = get_initial(c)
        meta_set("peak_equity", init, c)
        meta_set("day_start", {"date": str(datetime.date.today()), "equity": init}, c)
        log_event("settings", "تم تصفير المحفظة", c)


# =====================================================================
# الأحداث
# =====================================================================
def log_event(kind, msg, conn=None):
    sql = "INSERT INTO events (ts, kind, msg) VALUES (?,?,?)"
    params = (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), kind, msg)
    if conn:
        conn.execute(sql, params)
    else:
        q(sql, params)


def recent_events(after_id=0, limit=50):
    return [dict(r) for r in q("SELECT * FROM events WHERE id>? ORDER BY id DESC LIMIT ?",
                               (after_id, limit))]


def last_event_id():
    r = q("SELECT MAX(id) AS m FROM events")
    return int(r[0]["m"] or 0)


# =====================================================================
# الحجم والمستويات والبوابات
# =====================================================================
def levels(direction, price, stop_dist, rr):
    if direction == "short":
        return price + stop_dist, price - rr * stop_dist, price - rr * stop_dist / 2.0
    return price - stop_dist, price + rr * stop_dist, price + rr * stop_dist / 2.0


def position_size(S, price, atr, equity, cash, scale=1.0):
    stop_dist = S["atr_mult"] * atr
    if price <= 0 or stop_dist <= 0:
        return 0.0, stop_dist
    risk_amt = equity * S["risk_pct"] / 100.0 * scale
    cost_factor = 1 + (S["slippage_pct"] + S["commission_pct"]) / 100.0
    sh = min(risk_amt / stop_dist, equity * S["max_pos_pct"] / 100.0 / price,
             cash / (price * cost_factor))
    return math.floor(max(0.0, sh) * 1000) / 1000.0, stop_dist


def risk_scale(S, mkt, peak, equity=None):
    scale, notes = 1.0, []
    if mkt.get("vix") and mkt["vix"] > 25:
        scale *= 0.5
        notes.append("VIX مرتفع (>25)")
    eq = get_equity() if equity is None else equity
    if peak > 0 and eq < peak * (1 - S["dd_cut_pct"] / 100.0):
        scale *= 0.5
        notes.append("تراجع المحفظة عن قمتها")
    return scale, notes


def edge_status(S):
    e = meta_get("edge", None)
    if not e:
        return False, "ما في باك-تست محفوظ. شغّل الباك-تست أولاً.", None
    if abs(e["atr_mult"] - S["atr_mult"]) > 1e-9 or abs(e["rr"] - S["rr"]) > 1e-9:
        return False, "إعدادات ATR/RR تغيرت بعد الاختبار. أعد الباك-تست.", e
    if bool(e.get("scale_out", True)) != bool(S.get("auto_scale_out", True)):
        return False, "إعداد الجني الآلي 50% تغير بعد الاختبار. أعد الباك-تست.", e
    if int(e.get("tt_min", 0)) != int(S.get("tt_min", 0)):
        return False, "حد قالب الترند تغير بعد الاختبار. أعد الباك-تست.", e
    try:
        age = (datetime.date.today() - datetime.date.fromisoformat(e["date"])).days
    except (KeyError, ValueError):
        age = 999
    if age > 30:
        return False, "نتيجة الباك-تست قديمة (+30 يوم). أعد الاختبار.", e
    if e["n_oos"] < 30:
        return False, "عينة الاختبار الخارجي صغيرة (<30 صفقة).", e
    if e["avg_r_oos"] <= 0 or e["pf_oos"] < 1.15:
        return False, "التوقع خارج العينة غير مربح. الدخول محظور.", e
    return True, "ok", e


def entry_error(S, sym, direction, shares, stop_dist, priority, mkt, override, interval,
                blocked_today, edge, halal_verdict, equity, open_now=None):
    """كل شروط الحماية قبل فتح صفقة. يرجّع رسالة الخطأ أو None."""
    edge_ok, edge_msg, edge_info = edge
    open_now = list_open() if open_now is None else open_now
    sec = sector_of(sym)
    same_sec = [t for t in open_now if sector_of(t["symbol"]) == sec]
    is_short = direction == "short"
    if blocked_today:
        return "حد الخسارة اليومي مفعّل."
    if is_short and not S["allow_short"]:
        return "البيع على المكشوف معطل من الإعدادات."
    if S["edge_gate"] and not edge_ok:
        return "بوابة الجدوى مغلقة: " + edge_msg
    if S["edge_gate"] and interval != "1d":
        return "بوابة الجدوى مختبرة على الفاصل اليومي فقط. استخدم 1D أو عطّل البوابة (غير مفضل)."
    if S["edge_gate"] and edge_info and priority > edge_info["p_max"]:
        return "الإشارة أضعف من المستوى المربح في الباك-تست."
    if S.get("halal_gate", True) and halal_verdict == "fail":
        return "السهم لا يجتاز الفحص الشرعي (نسب الدين/الكاش أو النشاط)."
    if len(open_now) >= S["max_open"]:
        return "وصلت الحد الأقصى للصفقات (" + str(S["max_open"]) + ")."
    if sec != "صناديق" and sec != "-" and len(same_sec) >= S["max_per_sector"]:
        return "وصلت حد القطاع (" + sec + "): " + str(S["max_per_sector"]) + " صفقات."
    if open_heat(open_now) + shares * stop_dist > equity * S["max_heat_pct"] / 100.0:
        return "إجمالي المخاطرة المفتوحة سيتعدى " + str(S["max_heat_pct"]) + "% من المحفظة."
    if any(t["symbol"] == sym for t in open_now):
        return "عندك صفقة مفتوحة على هذا السهم."
    if shares <= 0:
        return "الحجم المحسوب صفر (الكاش أو المخاطرة لا تكفي)."
    if not override and (priority > 2 or (not is_short and not mkt.get("ok", True))):
        return "الإشارة ضعيفة أو السوق هابط. فعّل التجاوز إذا تبي تدخل."
    return None


# =====================================================================
# تنفيذ الصفقات
# =====================================================================
def open_position(S, sym, direction, price, shares, atr, tf, note="", setup=""):
    slip = S["slippage_pct"] / 100.0
    comm = S["commission_pct"] / 100.0
    fill = price * (1 + slip) if direction == "long" else price * (1 - slip)
    cost = shares * fill
    fee = cost * comm
    stop_dist = S["atr_mult"] * atr
    sl, tp, _ = levels(direction, fill, stop_dist, S["rr"])
    with tx() as c:
        if cost + fee > get_cash(c):
            return False, "الكاش لا يكفي."
        c.execute("UPDATE account SET cash = cash - ? WHERE id=1", (cost + fee,))
        c.execute("""INSERT INTO open_trades (symbol, direction, timeframe, entry, current, shares,
                     cost, sl, tp, stop_dist, init_risk, extreme, be_done, half_closed, fees, opened,
                     note, setup) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,?,?,?)""",
                  (sym, direction, tf, fill, fill, shares, cost, sl, tp, stop_dist,
                   stop_dist * shares, fill, fee, now_str(), note or "", setup or ""))
        log_event("open", "فتح " + ("شورت " if direction == "short" else "شراء ") + sym
                  + " | " + format(shares, "g") + " سهم @ $" + format(fill, ",.2f"), c)
    return True, "ok"


def close_position(S, tid, price, reason, fraction=1.0, conn=None):
    if conn is None:
        with tx() as c:
            return close_position(S, tid, price, reason, fraction, c)
    c = conn
    slip = S["slippage_pct"] / 100.0
    comm = S["commission_pct"] / 100.0
    rows = c.execute("SELECT * FROM open_trades WHERE id=?", (tid,)).fetchall()
    if not rows:
        return None
    tr = dict(rows[0])
    is_short = tr["direction"] == "short"
    fraction = min(1.0, max(0.0, float(fraction)))
    fill = price * (1 + slip) if is_short else price * (1 - slip)
    sh = tr["shares"] * fraction
    cost_part = tr["cost"] * fraction
    gross = (tr["entry"] - fill) * sh if is_short else (fill - tr["entry"]) * sh
    fee_close = sh * fill * comm
    fee_open_part = tr["fees"] * fraction
    net = gross - fee_close - fee_open_part
    risk_part = tr["init_risk"] * fraction
    r_mult = net / risk_part if risk_part > 0 else 0.0
    pnl_pct = net / cost_part * 100.0 if cost_part > 0 else 0.0
    c.execute("UPDATE account SET cash = cash + ? WHERE id=1", (cost_part + gross - fee_close,))
    if fraction >= 0.999:
        c.execute("DELETE FROM open_trades WHERE id=?", (tid,))
    else:
        # الباقي يتأمن على التعادل إذا الصفقة رابحة، بدون ما ننزّل وقف متحرك أفضل من الدخول.
        # إذا الصفقة خسرانة نترك الوقف مكانه (وإلا ينضرب فوراً).
        in_profit = price < tr["entry"] if is_short else price > tr["entry"]
        new_sl = tr["sl"]
        if in_profit:
            new_sl = min(tr["sl"], tr["entry"]) if is_short else max(tr["sl"], tr["entry"])
        c.execute("""UPDATE open_trades SET shares=?, cost=?, fees=?, init_risk=?, sl=?,
                     be_done=?, half_closed=1 WHERE id=?""",
                  (tr["shares"] - sh, tr["cost"] - cost_part, tr["fees"] - fee_open_part,
                   tr["init_risk"] - risk_part, new_sl, 1 if in_profit else tr["be_done"], tid))
    c.execute("""INSERT INTO closed_trades (symbol, direction, timeframe, entry, exit, shares,
                 pnl, pnl_pct, r_mult, reason, fees, opened, closed, note, setup, trade_id)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (tr["symbol"], tr["direction"], tr["timeframe"], tr["entry"], fill, sh,
               round(net, 2), round(pnl_pct, 2), round(r_mult, 2), reason,
               round(fee_close + fee_open_part, 2), tr["opened"], now_str(),
               tr.get("note") or "", tr.get("setup") or "", tid))
    pct = "" if fraction >= 0.999 else " (" + format(fraction * 100, ".0f") + "%)"
    log_event("close", tr["symbol"] + pct + " | " + reason + " | " + usd(net), c)
    return net


def modify_trade(tid, sl=None, tp=None, note=None):
    with tx() as c:
        rows = c.execute("SELECT * FROM open_trades WHERE id=?", (tid,)).fetchall()
        if not rows:
            return False
        tr = dict(rows[0])
        sets, params = [], []
        if sl is not None:
            sets.append("sl=?")
            params.append(float(sl))
        if tp is not None:
            sets.append("tp=?")
            params.append(float(tp))
        if note is not None:
            sets.append("note=?")
            params.append(note)
        if not sets:
            return False
        c.execute("UPDATE open_trades SET " + ", ".join(sets) + " WHERE id=?", (*params, tid))
        if sl is not None or tp is not None:
            log_event("modify", tr["symbol"] + " | تعديل يدوي: وقف $" + format(sl or tr["sl"], ",.2f")
                      + " / هدف $" + format(tp or tr["tp"], ",.2f"), c)
    return True


def _age(tr, now):
    try:
        return now - datetime.datetime.strptime(tr["opened"], "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return datetime.timedelta(0)


def refresh_open_positions(S, prices=None, now=None):
    """تحديث الأسعار + الوقف المتحرك + التعادل + الجني الآلي + الخروج. ذرّي لكل صفقة."""
    trades = list_open()
    if not trades:
        return []
    prices = data.fetch_prices([t["symbol"] for t in trades]) if prices is None else prices
    now = now or datetime.datetime.now()
    earn = {}
    for t in trades:
        if t["direction"] != "short" and not is_fund(t["symbol"]) and t["symbol"] not in earn:
            earn[t["symbol"]] = data.days_to_earnings(t["symbol"])
    events = []
    for t0 in trades:
        p = prices.get(t0["symbol"])
        if not p:
            continue
        with tx() as c:
            rows = c.execute("SELECT * FROM open_trades WHERE id=?", (t0["id"],)).fetchall()
            if not rows:
                continue
            tr = dict(rows[0])
            short = tr["direction"] == "short"
            sd = tr["stop_dist"]
            ext = min(tr["extreme"], p) if short else max(tr["extreme"], p)
            sl, be = tr["sl"], tr["be_done"]
            if short:
                sl = min(sl, ext + sd)
                if not be and p <= tr["entry"] - sd:
                    sl, be = min(sl, tr["entry"]), 1
            else:
                sl = max(sl, ext - sd)
                if not be and p >= tr["entry"] + sd:
                    sl, be = max(sl, tr["entry"]), 1
            c.execute("UPDATE open_trades SET current=?, extreme=?, sl=?, be_done=? WHERE id=?",
                      (p, ext, sl, be, tr["id"]))
            tr.update(current=p, extreme=ext, sl=sl, be_done=be)

            hit_sl = p >= sl if short else p <= sl
            hit_tp = p <= tr["tp"] if short else p >= tr["tp"]
            if S.get("auto_scale_out", True) and not tr["half_closed"] and not hit_sl and not hit_tp:
                mid = tr["entry"] + (tr["tp"] - tr["entry"]) / 2.0
                if (p <= mid) if short else (p >= mid):
                    net = close_position(S, tr["id"], p, "جني ربح آلي 50% + تأمين للتعادل", 0.5, c)
                    events.append("✂️ " + tr["symbol"] + " | جني آلي 50% | " + usd(net))
                    continue

            reason = None
            if hit_sl:
                reason = "وقف الخسارة / الوقف المتحرك"
            elif hit_tp:
                reason = "تحقق الهدف النهائي"
            else:
                age = _age(tr, now)
                pnl_r = trade_pnl(tr, p) / tr["init_risk"] if tr["init_risk"] else 0.0
                if tr["timeframe"] in INTRADAY_TF:
                    too_old = age >= datetime.timedelta(hours=S.get("max_hold_hours", 6))
                else:
                    too_old = age.days >= S["max_hold_days"]
                if too_old and pnl_r < 1.0:
                    reason = "وقف زمني (طالت المدة بدون تقدم)"
                elif not short:
                    ed = earn.get(tr["symbol"])
                    if ed is not None and ed <= 1:
                        reason = "خروج آمن قبل إعلان الأرباح"
            if reason:
                net = close_position(S, tr["id"], p, reason, 1.0, c)
                events.append("🎯 " + tr["symbol"] + " | " + reason + " | " + usd(net))
    return events


# =====================================================================
# الأوامر المعلقة
# =====================================================================
ORDER_KINDS = {"stop": "عند الاختراق", "limit": "عند التراجع"}


def place_order(sym, direction, kind, trigger, atr, tf, priority, days_valid=5, note=""):
    expires = (datetime.datetime.now() + datetime.timedelta(days=days_valid)).strftime("%Y-%m-%d %H:%M")
    with tx() as c:
        c.execute("""INSERT INTO orders (symbol, direction, kind, trigger, atr, timeframe, priority,
                     created, expires, note) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                  (sym, direction, kind, float(trigger), float(atr), tf, int(priority), now_str(),
                   expires, note or ""))
        log_event("order", "أمر معلق " + sym + " " + ORDER_KINDS.get(kind, kind)
                  + " @ $" + format(float(trigger), ",.2f"), c)


def list_orders(status="open"):
    if status is None:
        return [dict(r) for r in q("SELECT * FROM orders ORDER BY id DESC LIMIT 200")]
    return [dict(r) for r in q("SELECT * FROM orders WHERE status=? ORDER BY id", (status,))]


def cancel_order(oid, info="إلغاء يدوي"):
    q("UPDATE orders SET status='cancelled', info=? WHERE id=? AND status='open'", (info, oid))


def order_triggered(o, price):
    up = (o["kind"] == "stop") == (o["direction"] == "long")
    return price >= o["trigger"] if up else price <= o["trigger"]


def process_orders(S, mkt, prices=None, halal_fn=None):
    orders = list_orders("open")
    if not orders:
        return []
    now = datetime.datetime.now()
    prices = data.fetch_prices([o["symbol"] for o in orders]) if prices is None else prices
    events = []
    blocked, peak = day_guard(S)
    edge = edge_status(S)
    for o in orders:
        try:
            expired = now >= datetime.datetime.strptime(o["expires"], "%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            expired = False
        if expired:
            q("UPDATE orders SET status='expired', info='انتهت صلاحيته' WHERE id=?", (o["id"],))
            events.append("⌛ انتهى أمر " + o["symbol"])
            continue
        p = prices.get(o["symbol"])
        if not p or not order_triggered(o, p):
            continue
        equity, cash = get_equity(), get_cash()
        scale, _ = risk_scale(S, mkt, peak, equity)
        shares, stop_dist = position_size(S, p, o["atr"], equity, cash, scale)
        verdict = halal_fn(o["symbol"])["verdict"] if halal_fn else "pass"
        err = entry_error(S, o["symbol"], o["direction"], shares, stop_dist, o["priority"], mkt,
                          True, TF_INTERVAL.get(o["timeframe"], "1d"), blocked, edge, verdict, equity)
        if err:
            q("UPDATE orders SET status='rejected', info=? WHERE id=?", (err, o["id"]))
            log_event("order", "رُفض أمر " + o["symbol"] + ": " + err)
            events.append("⛔ رُفض أمر " + o["symbol"] + ": " + err)
            continue
        ok, msg = open_position(S, o["symbol"], o["direction"], p, shares, o["atr"], o["timeframe"],
                                note=o["note"], setup="أمر معلق " + ORDER_KINDS.get(o["kind"], ""))
        q("UPDATE orders SET status=?, info=? WHERE id=?",
          ("filled" if ok else "rejected", "نُفّذ @ $" + format(p, ",.2f") if ok else msg, o["id"]))
        events.append(("✅ نُفّذ أمر " if ok else "⛔ فشل أمر ") + o["symbol"] + " @ $" + format(p, ",.2f"))
    return events


# =====================================================================
# قائمة المراقبة وتنبيهات السعر
# =====================================================================
def add_watch(sym, above=None, below=None, note=""):
    q("""INSERT INTO watchlist (symbol, added, note, above, below) VALUES (?,?,?,?,?)
         ON CONFLICT(symbol) DO UPDATE SET note=excluded.note, above=excluded.above,
         below=excluded.below""", (sym.upper(), now_str(), note or "", above, below))


def remove_watch(sym):
    q("DELETE FROM watchlist WHERE symbol=?", (sym,))


def list_watch():
    return [dict(r) for r in q("SELECT * FROM watchlist ORDER BY symbol")]


def check_watch_alerts(prices=None):
    rows = [w for w in list_watch() if w["above"] or w["below"]]
    if not rows:
        return []
    prices = data.fetch_prices([w["symbol"] for w in rows]) if prices is None else prices
    events = []
    for w in rows:
        p = prices.get(w["symbol"])
        if not p:
            continue
        if w["above"] and p >= w["above"]:
            q("UPDATE watchlist SET above=NULL, last_alert=? WHERE symbol=?", (now_str(), w["symbol"]))
            events.append("🔔 " + w["symbol"] + " تعدّى $" + format(w["above"], ",.2f")
                          + " (الآن $" + format(p, ",.2f") + ")")
        if w["below"] and p <= w["below"]:
            q("UPDATE watchlist SET below=NULL, last_alert=? WHERE symbol=?", (now_str(), w["symbol"]))
            events.append("🔔 " + w["symbol"] + " نزل تحت $" + format(w["below"], ",.2f")
                          + " (الآن $" + format(p, ",.2f") + ")")
    for e in events:
        log_event("alert", e)
    return events


# =====================================================================
# السجل اليومي للمحفظة والإشارات
# =====================================================================
def snapshot_equity():
    trades = list_open()
    cash = get_cash()
    open_pnl = sum(trade_pnl(t) for t in trades)
    eq = cash + sum(t["cost"] for t in trades) + open_pnl
    q("INSERT OR REPLACE INTO equity_history (day, equity, cash, open_pnl) VALUES (?,?,?,?)",
      (str(datetime.date.today()), eq, cash, open_pnl))
    return eq


def save_signals(results, tf_name):
    """يحفظ إشارات الشراء (أولوية 1-2) مرة وحدة باليوم لكل سهم وإطار. يرجّع القوية الجديدة."""
    day = str(datetime.date.today())
    ts = now_str()
    new_strong = []
    with tx() as c:
        for r in results:
            if r["priority"] > 2:
                continue
            exists = c.execute("SELECT id FROM signals WHERE day=? AND symbol=? AND timeframe=?",
                               (day, r["الرمز"], tf_name)).fetchall()
            if exists:
                continue
            c.execute("""INSERT INTO signals (ts, day, symbol, timeframe, price, score, decision,
                         priority) VALUES(?,?,?,?,?,?,?,?)""",
                      (ts, day, r["الرمز"], tf_name, r["raw_price"], r["score_num"], r["القرار"],
                       r["priority"]))
            if r["priority"] == 1:
                new_strong.append(r["الرمز"])
    return new_strong
