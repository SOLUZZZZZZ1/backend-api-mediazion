import os
import sqlite3
import secrets
import hashlib
import datetime
import smtplib, ssl
from email.message import EmailMessage

import stripe
import httpx
import feedparser
from dateutil import parser as dateparser

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# =========================
# Configuración y utilidades
# =========================

app = FastAPI(title="MEDIAZION Backend", version="1.2.0")

# --- CORS ---
def parse_origins(raw: str | None) -> list[str]:
    if not raw or raw.strip() == "*":
        # Por defecto admite solo dominios finales conocidos
        return [
            "https://mediazion.eu",
            "https://www.mediazion.eu",
        ]
    return [o.strip() for o in raw.split(",") if o.strip()]

ALLOWED = os.getenv("ALLOWED_ORIGINS")
allow_origins = parse_origins(ALLOWED)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Email (Nominalia) ---
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_TLS  = (os.getenv("SMTP_TLS", "false").lower() in ("1","true","yes"))
MAIL_FROM = os.getenv("MAIL_FROM") or SMTP_USER
MAIL_TO   = os.getenv("MAIL_TO") or SMTP_USER
MAIL_BCC  = (os.getenv("MAIL_BCC") or "").strip()

def send_email(subject: str, body: str, to_email: str):
    """Envía email; si SMTP no está configurado, registra aviso pero no rompe la petición."""
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        print("[INFO] SMTP no configurado; se omite envío de correo.")
        return
    msg = EmailMessage()
    msg["From"] = MAIL_FROM or SMTP_USER
    msg["To"] = to_email
    if MAIL_BCC:
        msg["Bcc"] = MAIL_BCC
    msg["Subject"] = subject
    msg.set_content(body)

    if SMTP_TLS and SMTP_PORT != 465:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.ehlo()
            s.starttls(context=context)
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
    else:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=30) as s:
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)

# --- DB (SQLite) ---
DB_PATH = os.getenv("DB_PATH", "mediazion.db")

def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def ensure_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mediadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def hash_pw(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

ensure_db()

# --- Stripe ---
STRIPE_SECRET = (os.getenv("STRIPE_SECRET") or os.getenv("STRIPE_SECRET_KEY") or "").strip()
if STRIPE_SECRET:
    stripe.api_key = STRIPE_SECRET
    print("[OK] Stripe secret cargada (preview):", STRIPE_SECRET[:8], "…")
else:
    print("[WARN] STRIPE_SECRET / STRIPE_SECRET_KEY no está configurada.")

STRIPE_PRICE_ID = (os.getenv("STRIPE_PRICE_ID") or "").strip()  # price_xxx (49,90 €/mes)
SUB_SUCCESS_URL = os.getenv("SUB_SUCCESS_URL") or "https://mediazion.eu/suscripcion/ok"
SUB_CANCEL_URL  = os.getenv("SUB_CANCEL_URL")  or "https://mediazion.eu/suscripcion/cancel"
STRIPE_WEBHOOK_SECRET = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()

# =========================
# Diagnóstico y salud
# =========================

@app.get("/health")
def health():
    return {"ok": True, "service": "mediazion-backend"}

@app.get("/diag/env")
def diag_env():
    sec = (os.getenv("STRIPE_SECRET") or os.getenv("STRIPE_SECRET_KEY") or "").strip()
    return {
        "has_secret": bool(sec),
        "secret_preview": (sec[:8] + "…") if sec else "",
        "allowed_origins": allow_origins,
    }

@app.get("/routes")
def list_routes():
    return [getattr(r, "path", str(r)) for r in app.routes]

@app.get("/contact/ping")
def contact_ping():
    return {"ok": True, "message": "CONTACT PING OK"}

# =========================
# Contacto
# =========================

@app.post("/contact")
async def contact(req: Request):
    data = await req.json()
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip()
    subject = str(data.get("subject", "")).strip() or "Mensaje de contacto"
    message = str(data.get("message", "")).strip()

    if len(name) < 2 or "@" not in email or len(message) < 5:
        raise HTTPException(status_code=400, detail="Datos insuficientes.")

    body = f"""Nuevo mensaje desde MEDIAZION
----------------------------------------
Nombre: {name}
Email:  {email}
Asunto: {subject}

{message}
"""
    try:
        send_email(f"[MEDIAZION] {subject}", body, MAIL_TO or SMTP_USER or email)
    except Exception as e:
        print(f"[EMAIL] aviso: {e}")
    # Nunca romper por email:
    return {"ok": True}

# =========================
# Alta de mediadores
# =========================

@app.post("/mediadores/register")
async def mediador_register(req: Request):
    data = await req.json()
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    if len(name) < 2 or "@" not in email:
        raise HTTPException(status_code=400, detail="Nombre o email inválido.")

    password_plain = secrets.token_urlsafe(9)  # ~12 chars
    password_hash = hash_pw(password_plain)

    try:
        conn = db()
        conn.execute(
            "INSERT INTO mediadores (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (name, email, password_hash, datetime.datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Ese email ya está registrado.")

    # Email con credenciales
    body = f"""Hola {name},

Te hemos dado de alta como MEDIADOR en MEDIAZION.

Credenciales:
- Usuario (email): {email}
- Contraseña temporal: {password_plain}

Por seguridad, cambia tu contraseña tras el primer acceso.

Un saludo,
MEDIAZION
"""
    try:
        send_email("Tu acceso a MEDIAZION (Mediadores)", body, email)
    except Exception as e:
        print(f"[EMAIL] aviso: no se pudo enviar el correo automático: {e}")
    return {"ok": True}

# =========================
# Noticias (agregador)
# =========================

FEEDS = {
    "BOE": "https://www.boe.es/rss/boe_es.php",
    "CGPJ": "https://www.poderjudicial.es/cgpj/es/Temas/Actualidad/rss/Actualidad",
    "MINISTERIO_JUSTICIA": "https://www.mjusticia.gob.es/es/actualidad/rss",
    "EURLEX_DOUE": "https://eur-lex.europa.eu/rss/es/index.html",
    "CONFILEGAL": "https://confilegal.com/feed/",
    "LEGALTODAY": "https://www.legaltoday.com/feed/",
}
KEYWORDS = ["mediación", "mediador", "adr", "resolución alternativa", "acuerdo", "conflicto"]

_news_cache = {"items": [], "ts": 0}
CACHE_TTL = int(os.getenv("NEWS_CACHE_TTL", "900"))

def matches_keywords(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in KEYWORDS)

def infer_tags(text: str) -> list[str]:
    t = (text or "").lower()
    tags = []
    mapping = {
        "civil": ["civil", "familia", "arrend", "vecinal"],
        "mercantil": ["mercantil", "societar", "empresa", "comercial"],
        "laboral": ["laboral", "empleo", "trabajo"],
        "penal": ["penal", "delito"],
        "internacional": ["ue", "europea", "internacional", "eur-lex", "doue"],
        "normativa": ["boe", "ley", "real decreto", "norma", "orden"],
        "jurisprudencia": ["sentencia", "ts", "tribunal", "cgpj"],
        "doctrina": ["artículo", "opinión", "análisis", "confilegal", "legaltoday"],
    }
    for tag, words in mapping.items():
        if any(w in t for w in words):
            tags.append(tag)
    if not tags:
        tags.append("general")
    return sorted(list(set(tags)))

async def fetch_feed(url: str) -> list[dict]:
    items = []
    async with httpx.AsyncClient(timeout=20.0, headers={
        "User-Agent": "Mozilla/5.0 (compatible; MEDIAZION/1.0)"
    }) as client:
        r = await client.get(url)
        r.raise_for_status()
        d = feedparser.parse(r.text)
    for e in d.entries[:30]:
        title = (getattr(e, "title", "") or "").strip()
        summary = (getattr(e, "summary", "") or "").strip()
        link = (getattr(e, "link", "") or "").strip()
        date_raw = getattr(e, "published", None) or getattr(e, "updated", None)
        date_iso = None
        if date_raw:
            try:
                date_iso = dateparser.parse(date_raw).date().isoformat()
            except Exception:
                date_iso = None
        blob = f"{title} {summary}"
        if matches_keywords(blob):
            items.append({"title": title, "summary": summary, "url": link, "date": date_iso})
    return items

import time, asyncio

async def load_all_news() -> list[dict]:
    tasks = [fetch_feed(u) for u in FEEDS.values()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    aggregated = []
    for (source, _), res in zip(FEEDS.items(), results):
        if isinstance(res, Exception):
            print(f"[NEWS] error {source}: {res}")
            continue
        for item in res:
            aggregated.append({
                "title": item["title"],
                "summary": item["summary"],
                "url": item["url"],
                "date": item["date"],
                "source": source,
                "tags": infer_tags(item["title"] + " " + item["summary"]),
            })
    aggregated.sort(key=lambda x: x["date"] or "", reverse=True)
    return aggregated[:120]

@app.get("/news")
async def news(source: str | None = None, tag: str | None = None, q: str | None = None, limit: int = 50):
    now = time.time()
    if now - _news_cache["ts"] > CACHE_TTL or not _news_cache["items"]:
        _news_cache["items"] = await load_all_news()
        _news_cache["ts"] = now

    items = list(_news_cache["items"])
    if source:
        items = [i for i in items if i["source"].lower() == source.lower()]
    if tag:
        items = [i for i in items if tag.lower() in [t.lower() for t in i.get("tags", [])]]
    if q:
        ql = q.lower()
        items = [i for i in items if ql in (i["title"] or "").lower() or ql in (i["summary"] or "").lower()]
    return items[: max(1, min(limit, 200)) ]

# =========================
# Stripe (Checkout)
# =========================

@app.post("/subscribe")
async def subscribe(req: Request):
    if not STRIPE_SECRET:
        raise HTTPException(status_code=500, detail="Stripe no configurado")
    data = await req.json()
    email = (data.get("email") or "").strip()
    price_id = (data.get("priceId") or STRIPE_PRICE_ID or "").strip()
    if not price_id:
        raise HTTPException(status_code=400, detail="Falta STRIPE_PRICE_ID (price_xxx)")
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=email or None,
            allow_promotion_codes=True,
            success_url=SUB_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=SUB_CANCEL_URL,
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create-checkout-session")
async def create_checkout_session(req: Request):
    """PAGO ÚNICO opcional: crea sesión de Checkout con amount en céntimos."""
    if not STRIPE_SECRET:
        raise HTTPException(status_code=500, detail="Stripe no configurado")
    body = await req.json()
    amount = int(body.get("price_cents") or 0)
    currency = body.get("currency") or "eur"
    description = body.get("description") or "Compra MEDIAZION"
    if amount <= 0:
        raise HTTPException(status_code=400, detail="price_cents inválido")
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": currency,
                    "product_data": {"name": description},
                    "unit_amount": amount,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=SUB_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=SUB_CANCEL_URL,
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        else:
            event = stripe.Event.construct_from(await request.json(), stripe.api_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    etype = event["type"]
    data = event["data"]["object"]

    if etype == "checkout.session.completed":
        print("[Stripe] checkout.session.completed", data.get("id"),
              "customer:", data.get("customer"),
              "subscription:", data.get("subscription"))
        # Aquí podrías marcar en tu BD que la suscripción está activa y enviar correo

    elif etype == "invoice.paid":
        print("[Stripe] invoice.paid", data.get("id"))

    elif etype == "invoice.payment_failed":
        print("[Stripe] invoice.payment_failed customer:", data.get("customer"))

    return {"received": True}
