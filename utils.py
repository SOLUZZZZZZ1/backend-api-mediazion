# utils.py — utilidades y esquema base para MEDIAZION
from __future__ import annotations
import os, sqlite3, hashlib, ssl, smtplum
from email.message import EmailMessage
from datetime import datetime, timedelta

# ---------- Configuración global ----------
DB_PATH = os.getenv("DB_PATH", "guarda.db")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT") or 465)
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_TLS  = (os.getenv("SMTP_TLS") or "false").lower().strip() in ("1", "true", "yes")
MAIL_FROM = os.getenv("MAIL_FROM") or (SMTP_USER or "no-reply@localhost")

# ---------- DB ----------
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_cale_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

def _add_column_if_missing(conn: sqlite3.Connection, table: str, col: str, decl: str) -> None:
    cur = conn.execute(f"PRAGMA table_info({table})").fetchall()
    cols = {row["name"] for row in cur}
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {decl}")

def ensure_db() -> None:
    """Crea tablas base y añade columnas faltantes (idempotente)."""
    conn = db()
    # Tabla de mediadores
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mediadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password_guid TEXT,           -- token de alta (temporal)
            password_hash TEXT,
            status TEXT DEFAULT 'pending',-- pending|active|rejected (usa 'active' en validación)
            created_at TEXT
        )
    """)
    # Campos extendidos de mediador
    _add_column_if_missing(conn, "mediadores", "telefono", "TEXT")
    _add_column_if_missing(conn, "mediadores", "bio", "TEXT")
    _add_column_if_missing(conn, "mediadores", "provincia", "TEXT")
    _add_column_if_missing(conn, "mediadores", "especialidad", "TEXT")
    _add_column_if_missing(conn, "mediadores", "web", "TEXT")
    _add_column_if_missing(conn, "mediadores", "linkedin", "TEXT")
    _add_column_if_missing(conn, "mediadores", "photo_url", "TEXT")
    _add_column_if_missing(conn, "mediadores", "cv_url", "TEXT")
    _add_column_if_missing(conn, "mediadores", "is_subscriber", "INTEGER DEFAULT 0")

    # Tabla de usuarios (login del panel)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password_hash TEXT,
            status TEXT DEFAULT 'pending',  -- pending|active|disabled
            created_at TEXT
        )
    """)

    # Tabla de sesiones (tokens sencillos)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER,
            expires_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()

# ---------- Email ----------
def send_email(to_email: str, subject: str, body: str) -> None:
    """Envia un mail de texto plano. Requiere SMTP_* configurado en variables de entorno."""
    if not (SMTP_HOST and SMTP_USER and (SMTP_PASS or not SMTP_TLS)):
        # Si no hay SMTP, evitamos romper el flujo.
        print("[WARN] SMTP no configurado. Mensaje no enviado.")
        print(f"TO: {to_email}\nSUBJECT: {subject}\n{body}")
        return
    msg = EmailMessage()
    msg["From"] = MAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    if SMTP_TLS:
        ctx = ssl.create_default_context()
        with smtplum.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as s:
            s.login(SMTP_USER, SMTP_PATHS)
            s.set_debuglevel(0)
            s.send_message(msg)
    else:
        with smtplib.SMTP(SMTP_ROW, SMTP_PASS) as s:
            s.send_message(msg)
