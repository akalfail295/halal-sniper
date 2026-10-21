"""قاعدة بيانات SQLite. كل عملية متعددة الخطوات داخل معاملة واحدة (BEGIN IMMEDIATE)."""
import datetime
import json
import os
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = os.environ.get("SNIPER_DB", str(ROOT / "halal_sniper.db"))
BACKUP_DIR = ROOT / "backups"
OLD_JSON = ROOT / "portfolio_db.json"
LOCK = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY, cash REAL, initial REAL);
CREATE TABLE IF NOT EXISTS open_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, direction TEXT,
    timeframe TEXT, entry REAL, current REAL, shares REAL, cost REAL,
    sl REAL, tp REAL, stop_dist REAL, init_risk REAL, extreme REAL,
    be_done INTEGER DEFAULT 0, half_closed INTEGER DEFAULT 0,
    fees REAL DEFAULT 0, opened TEXT
);
CREATE TABLE IF NOT EXISTS closed_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, direction TEXT,
    timeframe TEXT, entry REAL, exit REAL, shares REAL, pnl REAL,
    pnl_pct REAL, r_mult REAL, reason TEXT, fees REAL, opened TEXT, closed TEXT
);
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, day TEXT, symbol TEXT,
    timeframe TEXT, price REAL, score INTEGER, decision TEXT, priority INTEGER
);
CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY, added TEXT, note TEXT DEFAULT '',
    above REAL, below REAL, last_alert TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, direction TEXT, kind TEXT,
    trigger REAL, atr REAL, timeframe TEXT, priority INTEGER DEFAULT 2, created TEXT,
    expires TEXT, note TEXT DEFAULT '', status TEXT DEFAULT 'open', info TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS equity_history (
    day TEXT PRIMARY KEY, equity REAL, cash REAL, open_pnl REAL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, msg TEXT
);
"""

# أعمدة أضيفت بعد النسخة الأولى (ترقية تلقائية للقواعد القديمة)
MIGRATIONS = {
    "open_trades": {"half_closed": "INTEGER DEFAULT 0", "note": "TEXT DEFAULT ''",
                    "setup": "TEXT DEFAULT ''"},
    "closed_trades": {"note": "TEXT DEFAULT ''", "setup": "TEXT DEFAULT ''",
                      "trade_id": "INTEGER"},
}


def use_db(path):
    """تغيير مسار القاعدة (للاختبارات أو الاستعادة)."""
    global DB_PATH
    DB_PATH = str(path)
    init_db()


def connect():
    c = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    return c


def q(sql, params=()):
    with LOCK:
        c = connect()
        try:
            return c.execute(sql, params).fetchall()
        finally:
            c.close()


@contextmanager
def tx():
    with LOCK:
        c = connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.execute("COMMIT")
        except BaseException:
            if c.in_transaction:
                c.execute("ROLLBACK")
            raise
        finally:
            c.close()


def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def init_db():
    with LOCK:
        c = connect()
        try:
            c.executescript(SCHEMA)
            for table, cols in MIGRATIONS.items():
                have = {r["name"] for r in c.execute("PRAGMA table_info(" + table + ")")}
                for col, decl in cols.items():
                    if col not in have:
                        c.execute("ALTER TABLE " + table + " ADD COLUMN " + col + " " + decl)
            if not c.execute("SELECT id FROM account WHERE id=1").fetchall():
                cap0 = 10000.0
                if OLD_JSON.exists():
                    try:
                        cap0 = float(json.loads(OLD_JSON.read_text("utf-8")).get("initial_capital", cap0))
                    except (ValueError, OSError):
                        pass
                c.execute("INSERT INTO account (id, cash, initial) VALUES (1,?,?)", (cap0, cap0))
        finally:
            c.close()


def meta_get(k, default=None, conn=None):
    rows = (conn.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchall() if conn
            else q("SELECT v FROM meta WHERE k=?", (k,)))
    if rows:
        try:
            return json.loads(rows[0]["v"])
        except (TypeError, ValueError):
            return default
    return default


def meta_set(k, v, conn=None):
    sql, params = "INSERT OR REPLACE INTO meta (k,v) VALUES(?,?)", (k, json.dumps(v))
    if conn:
        conn.execute(sql, params)
    else:
        q(sql, params)


# =====================================================================
# نسخ احتياطي واستعادة
# =====================================================================
REQUIRED_TABLES = {"meta", "account", "open_trades", "closed_trades"}


def backup_to(path):
    with LOCK:
        src = connect()
        dst = sqlite3.connect(str(path))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()


def backup_bytes():
    tmp = Path(DB_PATH + ".export")
    backup_to(tmp)
    try:
        return tmp.read_bytes()
    finally:
        tmp.unlink(missing_ok=True)


def daily_backup(keep=7):
    BACKUP_DIR.mkdir(exist_ok=True)
    target = BACKUP_DIR / ("halal_sniper_" + datetime.date.today().strftime("%Y%m%d") + ".db")
    if not target.exists():
        backup_to(target)
    olds = sorted(BACKUP_DIR.glob("halal_sniper_*.db"))
    for f in olds[:-keep]:
        f.unlink(missing_ok=True)
    return target


def validate_db_file(path):
    try:
        c = sqlite3.connect(str(path))
        try:
            names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            c.close()
    except sqlite3.DatabaseError:
        return False
    return REQUIRED_TABLES <= names


def restore_from_bytes(raw):
    """يستبدل القاعدة الحالية بملف مرفوع بعد التحقق منه. يحفظ نسخة من الحالية قبل الاستبدال."""
    tmp = Path(DB_PATH + ".upload")
    tmp.write_bytes(raw)
    if not validate_db_file(tmp):
        tmp.unlink(missing_ok=True)
        return False
    with LOCK:
        BACKUP_DIR.mkdir(exist_ok=True)
        if Path(DB_PATH).exists():
            shutil.copy2(DB_PATH, BACKUP_DIR / ("before_restore_" + datetime.datetime.now()
                                                .strftime("%Y%m%d_%H%M%S") + ".db"))
        os.replace(tmp, DB_PATH)
    init_db()
    return True
