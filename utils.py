# utils.py
import os, sqlite3, hashlib, smtplib, ssl
from email.message import EmailMessage
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "mediazion.db")

def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def now_iso() -> str:
    """Devuelve la fecha/hora actual en ISO 8601 (UTC)."""
    return datetime.utcnow().isoformat()

def send_mail(to: str, subject: str, body: str):
    """Envía email simple (por ahora sólo log)."""
    print(f"[MAIL] To: {to}\nSubject: {subject}\n{body}")
    # Aquí luego añadiremos SMTP real si lo deseas.

def ensure_db():
    con = db()
    con.execute("""
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
        is_subscriber INTEGER DEFAULT 0,
        subscription_status TEXT,
        is_trial INTEGER DEFAULT 0,
        trial_expires_at TEXT
    )
    """)
    con.commit()
    con.close()
