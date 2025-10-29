# app.py — MEDIAZION Backend (FastAPI) — Alta automatizada tras Stripe + Admin + Directorio
import os, sqlite3, secrets, hashlib, datetime, smtplib, ssl, time, asyncio, json
from email.message import EmailMessage
from typing import Optional

import stripe, httpx, feedparser
from dateutil import parser as dateparser
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# -----------------------------------------------------------------------------
# Configuración básica
# -----------------------------------------------------------------------------
app = FastAPI(title="MEDIAZION Backend", version="1.4.0")

def db():
    return sqlite3.connect(os.getenv("DB_PATH", "mediazion.db"), check_same_thread=False)

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

# -----------------------------------------------------------------------------
# Base de datos: tablas y columnas
# -----------------------------------------------------------------------------
def ensure_db():
    conn = db()

    # Alta manual de mediadores (registro desde la web)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS mediadores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        status TEXT DEFAULT 'pending',             -- pending | approved | rejected
        is_subscriber INTEGER DEFAULT 0,           -- 0/1
        stripe_customer_id TEXT,
        stripe_subscription_id TEXT,
        subscription_status TEXT,
        provincia TEXT,
        especialidad TEXT,                         -- CSV o JSON
        bio TEXT,
        foto_url TEXT,
        cv_url TEXT,
        created_at TEXT NOT NULL
      )
    """)

    # Usuarios (alta automática al completarse Stripe)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'mediador',     -- mediador | admin | staff
        status TEXT NOT NULL DEFAULT 'pendiente',  -- pendiente | activo | bloqueado
        created_at TEXT NOT NULL
      )
    """)

    # Asegurar columnas si la tabla ya existía (ALTER TABLE safe)
    def safe_alter(sql):
        try:
            conn.execute(sql)
            conn.commit()
        except Exception:
            pass

    for coldef in [
        "ALTER TABLE mediadores ADD COLUMN status TEXT DEFAULT 'pending'",
        "ALTER TABLE mediadores ADD COLUMN is_subscriber INTEGER DEFAULT 0",
        "ALTER TABLE mediadores ADD COLUMN stripe_customer_id TEXT",
        "ALTER TABLE mediadores ADD COLUMN stripe_subscription_id TEXT",
        "ALTER TABLE mediadores ADD COLUMN subscription_status TEXT",
        "ALTER TABLE mediadores ADD COLUMN provincia TEXT",
        "ALTER TABLE mediadores ADD COLUMN especialidad TEXT",
        "ALTER TABLE mediadores ADD COLUMN bio TEXT",
        "ALTER TABLE mediadores ADD COLUMN foto_url TEXT",
        "ALTER TABLE mediadores ADD COLUMN cv_url TEXT",
    ]:
        safe_alter(coldef)

    conn.close()

ensure_db()

# -----------------------------------------------------------------------------
# CORS
# -----------------------------------------------------------------------------
def parse_origins(raw: Optional[str]) -> list[str]:
    if not raw:
        return ["https://mediazion.eu", "https://www.mediazion.eu"]
    return [o.strip() for o in raw.split(",") if o.strip()]

allow_origins = parse_origins(os.getenv("ALLOWED_ORIGINS"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# SMTP / Correo
# -----------------------------------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_TLS  = (os.getenv("SMTP_TLS", "false").lower() in ("1", "true", "yes"))
MAIL_FROM = os.getenv("MAIL_FROM") or SMTP_USER
MAIL_TO   = os.getenv("MAIL_TO") or SMTP_USER

def send_email(subject: str, body: str, to_email: str):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        print("[EMAIL] SMTP no configurado")
        return
    msg = EmailMessage()
    msg["From"] = MAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    if SMTP_TLS and SMTP_PORT != 465:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.ehlo()
            s.starttls(context=ctx)
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
    else:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=30) as s:
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)

# -----------------------------------------------------------------------------
# Stripe
# -----------------------------------------------------------------------------
STRIPE_SECRET = (os.getenv("STRIPE_SECRET") or os.getenv("STRIPE_SECRET_KEY") or "").strip()
if STRIPE_SECRET:
    stripe.api_key = STRIPE_SECRET

STRIPE_PRICE_ID = (os.getenv("STRIPE_PRICE_ID") or "").strip()
STRIPE_WEBHOOK_SECRET = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
SUB_SUCCESS_URL = os.getenv("SUB_SUCCESS_URL") or "https://mediazion.eu/suscripcion/ok"
SUB_CANCEL_URL  = os.getenv("SUB_CANCEL_URL")  or "https://mediazion.eu/suscripcion/cancel"

# -----------------------------------------------------------------------------
# Salud
# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"ok": True, "service": "mediazion-backend"}

# -----------------------------------------------------------------------------
# Contacto
# -----------------------------------------------------------------------------
@app.post("/contact")
async def contact(req: Request):
    data = await req.json()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    subject = (data.get("subject") or "Mensaje de contacto").strip()
    message = (data.get("message") or "").strip()
    if len(name) < 2 or "@" not in email or len(message) < 5:
        raise HTTPException(400, "Datos insuficientes.")
    body = f"Nombre: {name}\nEmail: {email}\nAsunto: {subject}\n\n{message}"
    try:
        send_email(f"[MEDIAZION] {subject}", body, MAIL_TO or email)
    except Exception as e:
        print("[EMAIL] aviso:", e)
    return {"ok": True}

# -----------------------------------------------------------------------------
# Alta manual de mediadores (form web)
# -----------------------------------------------------------------------------
def mediator_insert(name: str, email: str):
    temp_pass = secrets.token_urlsafe(9)
    pwd_hash = sha256(temp_pass)
    now = datetime.datetime.utcnow().isoformat()
    conn = db()
    conn.execute("""
      INSERT INTO mediadores
        (name, email, password_hash, status, created_at)
      VALUES (?,?,?,?,?)
    """, (name, email.lower(), pwd_hash, "pending", now))
    conn.commit()
    conn.close()

    body = f"""Hola {name},

Te hemos dado de alta como MEDIADOR en MEDIAZION.

Acceso temporal:
- Usuario (email): {email}
- Contraseña temporal: {temp_pass}

Estado actual: PENDIENTE de validación.
La central revisará tu perfil y te confirmará por correo.
"""
    try:
        send_email("MEDIAZION · Alta provisional de mediador", body, email)
    except Exception as e:
        print("[EMAIL] aviso:", e)

@app.post("/mediadores/register")
async def mediadores_register(req: Request):
    data = await req.json()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    if len(name) < 2 or "@" not in email:
        raise HTTPException(400, "Nombre o email inválido.")
    try:
        mediator_insert(name, email)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Ese email ya está registrado.")
    return {"ok": True, "message": "Alta realizada. Revisa tu correo."}

# -----------------------------------------------------------------------------
# Noticias (RSS + filtros + caché)
# -----------------------------------------------------------------------------
FEEDS = {
  "BOE": "https://www.boe.es/rss/boe.xml",  # antes boe_es.php -> 404
  # CGPJ: elige uno o varios de la página RSS oficial:
  # Ejemplos (ajusta a tu preferencia):
  # "CGPJ_TS": "https://www.poderjudicial.es/cgpj/es/Poder-Judicial/Tribunal-Supremo/Noticias-Judiciales/_.rss",
  # "CGPJ_Noticias": "https://www.poderjudicial.es/cgpj/es/Poder-Judicial/Noticias-Judiciales/_.rss",
  "CONFILEGAL": "https://confilegal.com/feed/",
  "LEGALTODAY": "https://www.legaltoday.com/feed/",
  # "EURLEX_DOUE": "..."  # comentar si da 404
}

KEYWORDS = ["mediación", "mediador", "adr", "resolución alternativa", "acuerdo", "conflicto"]
_news_cache = {"items": [], "ts": 0}
CACHE_TTL = int(os.getenv("NEWS_CACHE_TTL", "900"))

def match_kw(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in KEYWORDS)

async def fetch_feed(url: str) -> list[dict]:
    items = []
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": "Mozilla/5.0 (MEDIAZION/1.0)"}) as client:
        r = await client.get(url)
        r.raise_for_status()
        d = feedparser.parse(r.text)
    for e in d.entries[:40]:
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
        if match_kw(f"{title} {summary}"):
            items.append({"title": title, "summary": summary, "url": link, "date": date_iso})
    return items

async def load_all_feeds() -> list[dict]:
    tasks = [fetch_feed(u) for u in FEEDS.values()]
    res = await asyncio.gather(*tasks, return_exceptions=True)
    out = []
    for (src, _), it in zip(FEEDS.items(), res):
        if isinstance(it, Exception):
            print("[NEWS] error", src, it); continue
        for x in it:
            tags = []
            text = (x["title"] or "") + " " + (x["summary"] or "")
            for tg in ["civil", "mercantil", "laboral", "penal", "internacional", "normativa", "jurisprudencia", "doctrina"]:
                if tg in text.lower():
                    tags.append(tg)
            out.append({
                "title": x["title"], "summary": x["summary"], "url": x["url"], "date": x["date"],
                "source": src, "tags": tags
            })
    out.sort(key=lambda k: k["date"] or "", reverse=True)
    return out[:150]

@app.get("/news")
async def news(source: Optional[str] = None, tag: Optional[str] = None, q: Optional[str] = None, limit: int = 50):
    now = time.time()
    global _news_cache
    if (now - _news_cache["ts"] > CACHE_TTL) or (not _news_cache["items"]):
        _news_cache = {"items": await load_all_feeds(), "ts": now}
    items = list(_news_cache["items"])
    if source:
        items = [i for i in items if i["source"].lower() == source.lower()]
    if tag:
        items = [i for i in items if tag.lower() in [t.lower() for t in i.get("tags", [])]]
    if q:
        items = [i for i in items if (q.lower() in (i["title"] or "").lower()) or (q.lower() in (i["summary"] or "").lower())]
    return items[: max(1, min(limit, 200))]

# -----------------------------------------------------------------------------
# Stripe: Checkout y Webhook
# -----------------------------------------------------------------------------
@app.post("/subscribe")
async def subscribe(req: Request):
    if not STRIPE_SECRET:
        raise HTTPException(500, "Stripe no configurado")
    data = await req.json()
    email = (data.get("email") or "").strip()
    price_id = (data.get("priceId") or STRIPE_PRICE_ID or "").strip()
    if not price_id:
        raise HTTPException(400, "Falta STRIPE_PRICE_ID")
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
        raise HTTPException(500, str(e))

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
        raise HTTPException(400, str(e))

    etype = event["type"]
    data = event["data"]["object"]

    if etype == "checkout.session.completed":
        session = data
        email = session.get("customer_email") or (session.get("customer_details") or {}).get("email")
        cust_id = session.get("customer")
        sub_id = session.get("subscription")

        if email:
            # Marcar mediador como suscriptor si existe
            conn = db()
            conn.execute("""
              UPDATE mediadores
              SET is_subscriber=1, stripe_customer_id=?, stripe_subscription_id=?, subscription_status='active'
              WHERE email=?
            """, (cust_id, sub_id, email.lower()))
            conn.commit()
            conn.close()

            # Crear usuario si no existía
            u = user_get_by_email(email)
            if not u:
                temp =
