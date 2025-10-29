# utils.py — utilidades y esquema base
import os, sqlite3, smtplib, ssl
from email.message import EmailMessage
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "mediazion.db")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", os.getenv("SMTP_PASSWORD",""))
SMTP_TLS  = (os.getenv("SMTP_TLS","false").lower() in ("1","true","yes"))
MAIL_FROM = os.getenv("MAIL_FROM", SMTP_USER or "no-reply@mediazion")

def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def sha256(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

def ensure_db():
    conn = db()
    cur = conn.cursor()
    # mediadores
    cur.execute("""
    CREATE TABLE IF NOT EXISTS mediadores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password_hash TEXT,
        status TEXT DEFAULT 'pending',   -- pending|active|rejected
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
    # users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password_hash TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT
    )
    """)
    # sessions
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER,
        expires_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    conn.commit(); conn.close()

def send_email(to_email: str, subject: str, body: str):
    if not SMTP_HOST:
        print(f"[email simulate] TO={to_email}\nSUBJECT={subject}\n{body}")
        return
    msg = EmailMessage()
    msg["From"] = MAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    if SMTP_TLS:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls(context=context)
            if SMTP_USER and SMTP_PASS:
                s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
    else:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as s:
            if SMTP_USER and SMTP_PASS:
                s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
