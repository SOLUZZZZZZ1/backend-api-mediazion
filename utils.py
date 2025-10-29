# utils.py — utilidades comunes MEDIAZION
import os, sqlite3, hashlib, ssl, smtplib
from email.message import EmailMessage

DB_PATH = os.getenv("DB_PATH", "mediazion.db")

def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def ensure_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mediadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password_hash TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            telefono TEXT,
            bio TEXT,
            provincia TEXT,
            especialidad TEXT,
            web TEXT,
            linkedin TEXT,
            photo_url TEXT,
            cv_url TEXT,
            is_subscriber INTEGER DEFAULT 0
        )
    """)
    conn.execute
