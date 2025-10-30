# utils.py — utilidades comunes MEDIAZION
import os, sqlite3, hashlib, ssl, smtplib
from email.message import EmailMessage

DB_PATH = os.getenv("DB_PATH", "mediazion.db")

# --- conexión base ---
def db():
    # fix correcto (no "check_same_window")
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

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

# --- correo opcional ---
def send_email(to: str, subject: str, body: str):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    if not all([smtp_host, smtp_user, smtp_pass]):
        return False
    msg = EmailMessage()
    msg["From"] = smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, 465, context=ctx) as s:
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        return True
    except Exception as e:
        print("EMAIL ERROR:", e)
        return False
