"""Central database (SQLite) + per-officer local store.

central.db  (data/central.db on the PC that runs the server - every officer's work lands here)
    users(username, name, role, branch, pw_hash, salt, active, created)
    cases(id, username, company, created, score, grade, recommendation, flags_high, flags_total,
          cost_inr, cost_usd, ai_calls, docx_path, xlsx_path, case_json_path, source_files, metrics)
    activity(id, username, ts, action, detail)

Officer local store: cases/<username>/*.json  (a copy of each case for the officer, exportable)
"""
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import sqlite3

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("CREDITINTEL_DB", os.path.join(HERE, "data", "central.db"))


def _con():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def init():
    with _con() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            username TEXT PRIMARY KEY, name TEXT, role TEXT CHECK(role IN ('admin','officer')),
            branch TEXT, pw_hash TEXT, salt TEXT, active INTEGER DEFAULT 1, created TEXT);
        CREATE TABLE IF NOT EXISTS cases(
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, company TEXT, created TEXT,
            score REAL, grade TEXT, recommendation TEXT, flags_high INTEGER, flags_total INTEGER,
            cost_inr REAL, cost_usd REAL, ai_calls INTEGER,
            docx_path TEXT, xlsx_path TEXT, case_json_path TEXT, source_files TEXT);
        CREATE TABLE IF NOT EXISTS activity(
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, ts TEXT, action TEXT, detail TEXT);
        """)
        c.execute("""CREATE TABLE IF NOT EXISTS watchlist(
            id INTEGER PRIMARY KEY AUTOINCREMENT, list_name TEXT, name TEXT, norm TEXT, identifier TEXT, reason TEXT,
            list_date TEXT, directors TEXT, amount TEXT, source TEXT, added_by TEXT, added_on TEXT)""")
        c.execute("CREATE INDEX IF NOT EXISTS ix_wl_norm ON watchlist(norm)")
        c.execute("""CREATE TABLE IF NOT EXISTS figure_changes(
            id INTEGER PRIMARY KEY AUTOINCREMENT, case_uid TEXT, company TEXT, username TEXT, ts TEXT,
            year TEXT, line_key TEXT, line TEXT, old_value REAL, new_value REAL, source TEXT, reason TEXT)""")
        c.execute("CREATE INDEX IF NOT EXISTS ix_fc_case ON figure_changes(case_uid)")
        # the audit trail is append-only in the database itself: no user, screen or script can rewrite or delete history
        c.execute("""CREATE TRIGGER IF NOT EXISTS fc_no_update BEFORE UPDATE ON figure_changes
                     BEGIN SELECT RAISE(ABORT, 'audit trail is append-only'); END""")
        c.execute("""CREATE TRIGGER IF NOT EXISTS fc_no_delete BEFORE DELETE ON figure_changes
                     BEGIN SELECT RAISE(ABORT, 'audit trail is append-only'); END""")
        c.execute("CREATE INDEX IF NOT EXISTS ix_act_user ON activity(username, action, ts)")
        cols = {r_[1] for r_ in c.execute("PRAGMA table_info(cases)")}
        if "metrics" not in cols:  # portfolio metrics (added later; older databases are migrated in place)
            c.execute("ALTER TABLE cases ADD COLUMN metrics TEXT")


def _hash(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), 200_000).hex()


def has_admin():
    with _con() as c:
        return c.execute("SELECT 1 FROM users WHERE role='admin' AND active=1").fetchone() is not None


def create_user(username, password, name="", role="officer", branch=""):
    username = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,39}", username) or len(password) < 8:
        raise ValueError("Username: 2-40 letters, digits, '.', '_' or '-'; password at least 8 characters.")
    salt = secrets.token_hex(16)
    with _con() as c:
        c.execute("INSERT INTO users(username,name,role,branch,pw_hash,salt,active,created) VALUES(?,?,?,?,?,?,1,?)",
                  (username, name, role, branch, _hash(password, salt), salt, dt.datetime.now().isoformat(timespec="seconds")))
    log(username, "account_created", role)


def set_password(username, password):
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    salt = secrets.token_hex(16)
    with _con() as c:
        c.execute("UPDATE users SET pw_hash=?, salt=? WHERE username=?", (_hash(password, salt), salt, username))
    log(username, "password_reset", "")  # also clears a sign-in lock


def set_active(username, active):
    with _con() as c:
        c.execute("UPDATE users SET active=? WHERE username=?", (1 if active else 0, username))


MAX_FAILS = 5        # failed sign-ins ...
LOCK_MINUTES = 15    # ... within this window lock the username for this long


def login_locked(username):
    """Minutes left on a lock after repeated failed sign-ins (0 = not locked). Counted from the activity log, so a
    lock survives a server restart and applies whichever PC the attempts come from."""
    username = (username or "").strip().lower()
    since = (dt.datetime.now() - dt.timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds")
    with _con() as c:
        last_ok = c.execute("SELECT MAX(ts) FROM activity WHERE username=? AND action IN ('login','password_reset')",
                            (username,)).fetchone()[0] or ""
        rows = c.execute("SELECT ts FROM activity WHERE username=? AND action='login_failed' AND ts>=? AND ts>? ORDER BY ts",
                         (username, since, last_ok)).fetchall()
    if len(rows) < MAX_FAILS:
        return 0
    unlock = dt.datetime.fromisoformat(rows[MAX_FAILS - 1][0]) + dt.timedelta(minutes=LOCK_MINUTES)
    return max(0, int((unlock - dt.datetime.now()).total_seconds() // 60) + 1)


def verify(username, password):
    """User record on a correct password; None otherwise. Every failure is logged (and counts towards the lock);
    an unknown username costs the same hashing time as a known one, so names cannot be probed by timing."""
    username = (username or "").strip().lower()
    if not username or login_locked(username):
        return None
    with _con() as c:
        r = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not r:
        _hash(password or "", "00" * 16)
        log(username[:40], "login_failed", "unknown user")
        return None
    if r["active"] and secrets.compare_digest(_hash(password or "", r["salt"]), r["pw_hash"]):
        log(username, "login", "")
        return dict(r)
    log(username, "login_failed", "disabled account" if not r["active"] else "wrong password")
    return None


def users():
    with _con() as c:
        return [dict(r) for r in c.execute("SELECT username,name,role,branch,active,created FROM users ORDER BY role, username")]


def log(username, action, detail=""):
    with _con() as c:
        c.execute("INSERT INTO activity(username,ts,action,detail) VALUES(?,?,?,?)",
                  (username, dt.datetime.now().isoformat(timespec="seconds"), action, str(detail)[:500]))


def add_case(username, company, summary, cost_inr, cost_usd, ai_calls, docx_path, xlsx_path, case_json_path, source_files, metrics=None):
    with _con() as c:
        cur = c.execute("""INSERT INTO cases(username,company,created,score,grade,recommendation,flags_high,flags_total,
                           cost_inr,cost_usd,ai_calls,docx_path,xlsx_path,case_json_path,source_files,metrics)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (username, company, dt.datetime.now().isoformat(timespec="seconds"), summary.get("score"),
                         summary.get("grade"), summary.get("recommendation"), summary.get("flags_high"),
                         summary.get("flags_total"), round(cost_inr, 4), round(cost_usd, 6), ai_calls,
                         docx_path, xlsx_path, case_json_path, source_files, json.dumps(metrics or {})))
        return cur.lastrowid


def cases(username=None, limit=500):
    q = "SELECT * FROM cases"
    args = ()
    if username:
        q += " WHERE username=?"
        args = (username,)
    q += " ORDER BY id DESC LIMIT ?"
    with _con() as c:
        return [dict(r) for r in c.execute(q, args + (limit,))]


def activity(limit=300):
    with _con() as c:
        return [dict(r) for r in c.execute("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,))]


# ------------------------------------------------------------------ audit trail of figure changes (append-only)
def add_figure_changes(case_uid, company, username, rows, reason, source="Spread review"):
    """rows: [{year, key, line, old, new}]. Never updated or deleted - a correction is a new row.
    A hand edit must carry a reason, a known user, and the case must belong to that user (case ids start with the owner's
    username); automatic corrections are logged as 'system'."""
    if not str(reason or "").strip():
        raise ValueError("a reason is required for every figure change")
    if not username:
        raise ValueError("the user making the change must be identified")
    if username != "system" and not re.fullmatch(re.escape(username) + r"-\d{20}", str(case_uid or "")):
        with _con() as c:
            role = (c.execute("SELECT role FROM users WHERE username=?", (username,)).fetchone() or [None])[0]
        if role != "admin":
            raise PermissionError("figures can be changed only on your own case")
    now = dt.datetime.now().isoformat(timespec="seconds")
    with _con() as c:
        c.executemany("""INSERT INTO figure_changes(case_uid,company,username,ts,year,line_key,line,old_value,new_value,source,reason)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                      [(case_uid, company, username, now, r["year"], r["key"], r["line"], r["old"], r["new"], source, reason) for r in rows])
    return len(rows)


def figure_changes(case_uid):
    with _con() as c:
        return [dict(r) for r in c.execute("SELECT ts,username,year,line,old_value,new_value,source,reason FROM figure_changes "
                                           "WHERE case_uid=? ORDER BY id", (case_uid,))]


# ------------------------------------------------------------------ case access
def can_access(user, owner, path=None, root=None):
    """An officer opens only their own cases and files; an admin opens all. A stored path must also sit inside the
    application's own folder for that kind of file (a tampered database row cannot point at other files)."""
    if not user:
        return False
    if user.get("role") != "admin" and (owner or "") != user.get("username"):
        return False
    if path:
        base = os.path.realpath(root or HERE)
        try:
            if os.path.commonpath([os.path.realpath(path), base]) != base:
                return False
        except ValueError:  # different drives on Windows
            return False
    return True


def officer_dir(username):
    p = os.path.join(HERE, "cases", username)
    os.makedirs(p, exist_ok=True)
    return p


def save_local(username, payload, stem):
    path = os.path.join(officer_dir(username), f"{stem}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, default=str, indent=1)
    return path


# ------------------------------------------------------------------ watch-lists (fraud / defaulter / regulatory)
def wl_add(rows, username):
    from .watchlist import norm
    now = dt.datetime.now().isoformat(timespec="seconds")
    with _con() as c:
        c.executemany("""INSERT INTO watchlist(list_name,name,norm,identifier,reason,list_date,directors,amount,source,added_by,added_on)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                      [(r["list_name"], r["name"], norm(r["name"]), r.get("identifier", ""), r.get("reason", ""), r.get("list_date", ""),
                        r.get("directors", ""), r.get("amount", ""), r.get("source", ""), username, now) for r in rows])
    return len(rows)


def wl_entries():
    with _con() as c:
        return [dict(r) for r in c.execute("SELECT * FROM watchlist")]


def wl_lists():
    with _con() as c:
        return [dict(r) for r in c.execute("""SELECT list_name, source, COUNT(*) AS entries, MAX(added_on) AS updated, MAX(added_by) AS by
                                              FROM watchlist GROUP BY list_name, source ORDER BY list_name""")]


def wl_delete(list_name, source=None):
    with _con() as c:
        if source is None:
            c.execute("DELETE FROM watchlist WHERE list_name=?", (list_name,))
        else:
            c.execute("DELETE FROM watchlist WHERE list_name=? AND source=?", (list_name, source))
