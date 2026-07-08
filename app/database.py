import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).resolve().parent.parent / "agentviz.db"

TURSO_URL = os.getenv("TURSO_DATABASE_URL", "")
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")

_use_turso = bool(TURSO_URL and TURSO_TOKEN)

if _use_turso:
    try:
        import libsql_experimental as libsql
        _turso_available = True
    except ImportError:
        _turso_available = False


class RowDict:
    def __init__(self, row, columns):
        self._row = row
        self._cols = columns
        self._map = {col: val for col, val in zip(columns, row)}

    def keys(self):
        return self._cols

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._row[key]
        return self._map[key]

    def __iter__(self):
        return iter(self._map.values())

    def __contains__(self, key):
        return key in self._map


class TursoWrapper:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        cur = self._conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return TursoCursor(cur, cur.description)

    def executescript(self, sql):
        self._conn.executescript(sql)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


class TursoCursor:
    def __init__(self, cursor, description):
        self._cursor = cursor
        self._columns = [d[0].lower() for d in description] if description else []
        self.lastrowid = cursor.lastrowid if hasattr(cursor, 'lastrowid') else None

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return RowDict(row, self._columns)

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [RowDict(r, self._columns) for r in rows]


def _connect():
    if _use_turso and _turso_available:
        conn = libsql.connect(TURSO_URL, auth_token=TURSO_TOKEN)
        return TursoWrapper(conn)
    else:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn


@contextmanager
def get_db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                stripe_customer_id TEXT,
                plan TEXT DEFAULT 'starter',
                stripe_subscription_id TEXT,
                stripe_account_id TEXT,
                stripe_access_token TEXT,
                stripe_refresh_token TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                stripe_account_id TEXT NOT NULL,
                payment_intent_id TEXT UNIQUE NOT NULL,
                amount INTEGER NOT NULL,
                currency TEXT DEFAULT 'usd',
                agent_name TEXT,
                customer_email TEXT,
                status TEXT,
                created_at TIMESTAMP,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                stripe_account_id TEXT NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                transactions_synced INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running'
            );
        """)
        # Migration: add stripe_subscription_id to existing databases
        try:
            db.execute("ALTER TABLE users ADD COLUMN stripe_subscription_id TEXT")
        except Exception:
            pass
