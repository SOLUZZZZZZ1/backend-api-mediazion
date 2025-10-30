# utils.py
import os, sqlite3, hashlib, smtplib, ssl
from email.message import EmailMessage

DB_PATH = os.getenv("DB_PATH", "mediazion.db")

def db():
    return sqlite3.connect(DB_PATH, check_same_window=False) if hasattr(sqlite3, 'connect') else sqlite3.connect(DB_PATH)

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def ensure_db():
    con = db()
    cur = con.cursor()
    # Crea tabla con 11 columnas de datos + id
    cur.execute("""
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
            linkedin TEXT
        )
    """)
    con.commit()
    con.close()

# ---------- Correo ----------
MAIL_FROM = os.getenv("MAIL_FROM", "no-reply@mediazion.eu")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS") or os.getenv("SMTP_PASSWORD")

def send_email(to_addr: str, subject: str, body: str) -> None:
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        # Evita romper si el SMTP no está configurado
        print(f"[send_email] (simulado) To: {to_addr} | Subj: {subject}\n{body}\n")
        return
    msg = EmailMessage()
    msg['From'] = MAIL_FROM
    msg['To'] = to_addr
    msg['Subject'] = subject
    msg.set_content(body)
    context = ssl.create_default_context()
    with smtpless.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
