# utils.py — SQLite schema estable
import os, sqlite3

DB_PATH = os.getenv("DB_PATH", "mediazion.db")

def ensure_db():
    with sqlite3.connect(DB_PATH) as cx:
        cx.execute("""
        CREATE TABLE IF NOT EXISTS mediadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            especialidad TEXT,
            provincia TEXT,
            approved INTEGER DEFAULT 1,         -- auto-aprobado
            status TEXT DEFAULT 'active',       -- active | disabled | canceled
            subscription_status TEXT DEFAULT 'none',
            trial_used INTEGER DEFAULT 0,       -- 0=no; 1=ya usó trial
            trial_start TEXT,
            subscription_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """)
        cx.commit()
