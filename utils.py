# utils.py
import os, sqlite3, hashlib, smtplib, ssl
from email.message import EmailMessage
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "mediazion.db")

def db():
    # ojo: es check_same_thread, no "window"
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def sha256(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()

def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def send_mail(subject: str, body: str, to: str, bcc: str | None = None):
    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASS", "")
    mail_from = os.getenv("MAIL_FROM", user or "info@mediazion.eu")
    context = ssl.create_default_context()

    if not host or not user:
        # modo silencioso si no hay SMTP
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = to
    if bcc:
        msg["Bcc"] = bcc
    msg.set_content(body)

    with smtplib.SMTP(host, port) as s:
        s.starttls(context=context) if os.getenv("SMTP_TLS", "true").lower() == "true" else None
        s.login(user, password)
        s.send_message(msg)

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
        subscription_status TEXT DEFAULT '',
        is_trial INTEGER DEFAULT 0,
        trial_expires_at TEXT DEFAULT ''
    )
    """)
    con.commit()
    con.close()
