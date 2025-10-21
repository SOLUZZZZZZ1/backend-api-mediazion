from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
import os, smtplib, ssl, time, asyncio, sqlite3, secrets, hashlib, datetime, logging
from email.message import EmailMessage

# --- News deps ---
import httpx, feedparser
from dateutil import parser as dateparser

app = FastAPI(title="MEDIAZION Backend (contact + news + mediadores)", version="1.1.0")

# ========= CORS (cerrado por defecto, configurable por env) =========
# Pon aquí tu dominio de Vercel si cambia. Puedes usar ALLOWED_ORIGINS env para sobreescribir.
DEFAULT_ALLOWED = [
    "https://mediazion.eu",
    # sustituye por tu URL actual de Vercel (producción)
    "https://mediazion-frontend-a0692vjfn-soluzzzs-projects.vercel.app",
]
allowed_env = os.getenv("ALLOWED_ORIGINS", "")
if allowed_env.strip() and allowed_env.strip() != "*":
    allow_origins = [o.strip() for o in allowed_env.split(",") if o.strip()]
elif allowed_env.strip() == "*":
    allow_origins = ["*"]
else:
    allow_origins = DEFAULT_ALLOWED

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========= Logging sencillo =========
logger = logging.getLogger("mediazion")
logging.basicConfig(level=logging.INFO)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    origin = request.headers.get("origin")
    logger.info(f"[REQ] {request.method} {request.url.path}  origin={origin}")
    # respuesta OPTIONS (preflight) explícita para ver CORS
    if request.method == "OPTIONS":
        resp = await call_next(request)
        logger.info(f"[CORS] preflight path={request.url.path} status={resp.status_code} allow_origins={allow_origins}")
        return resp
    response = await call_next(request)
    logger.info(f"[RESP] {request.method} {request.url.path} -> {response.status_code}")
    return response

# ========= Health =========
@app.get("/health")
def health():
    return {"ok": True, "service": "mediazion-backend"}

# ========= Ping de contacto (para probar CORS desde el navegador) =========
@app.get("/contact/ping")
def contact_ping():
    return {"ok": True, "message": "CONTACT PING OK"}

# ========= Email helper (SMTP Nominalia) =========
def send_email_smtp(subject: str, body: str, mail_from: str, mail_to: str):
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    use_tls = os.getenv("SMTP_TLS", "false").lower() in ("1", "true", "yes")
    if not host or not user or not password or not mail_to:
        raise RuntimeError("SMTP not configured (check SMTP_HOST/USER/PASS and MAIL_TO).")

    msg = EmailMessage()
    msg["From"] = mail_from or user
    msg["To"] = mail_to
    bcc = os.getenv("MAIL_BCC", "").strip()
    if bcc:
        msg["Bcc"] = bcc
    msg["Subject"] = subject
    msg.set_content(body)

    # 465: SSL directo ; 587: STARTTLS
    if port == 465 and not use_tls:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            server.login(user, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.login(user, password)
            server.send_message(msg)

# ========= /contact =========
@app.post("/contact")
async def contact(req: Request):
    data = await req.json()
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip()
    subject = str(data.get("subject", "")).strip() or "Mensaje de contacto"
    message = str(data.get("message", "")).strip()
    if len(name) < 2 or "@" not in email or len(message) < 5:
        raise HTTPException(status_code=400, detail="Datos insuficientes.")

    mail_from = os.getenv("MAIL_FROM") or os.getenv("SMTP_USER")
    mail_to = os.getenv("MAIL_TO") or os.getenv("SMTP_USER")

    body = f"""Nuevo mensaje desde MEDIAZION
----------------------------------------
Nombre: {name}
Email:  {email}
Asunto: {subject}

Mensaje:
{message}
"""
    try:
        send_email_smtp(subject=f"[MEDIAZION] {subject}", body=body, mail_from=mail_from, mail_to=mail_to)
        return {"ok": True}
    except Exception as e:
        logger.error(f"[EMAIL] Error enviando correo: {e}")
        return {"ok": False, "error": str(e)}

# ========= /news (agregador) =========
FEEDS: Dict[str, str] = {
    "BOE": "https://www.boe.es/rss/boe_es.php",
    "CGPJ": "https://www.poderjudicial.es/cgpj/es/Temas/Actualidad/rss/Actualidad",
    "MINISTERIO_JUSTICIA": "https://www.mjusticia.gob.es/es/actualidad/rss",
    "EURLEX_DOUE": "https://eur-lex.europa.eu/rss/es/index.html",
    "CONFILEGAL": "https://confilegal.com/feed/",
    "LEGALTODAY": "https://www.legaltoday.com/feed/",
}
KEYWORDS = ["mediación", "mediador", "adr", "resolución alternativa", "acuerdo", "conflicto"]

_news_cache: Dict[str, Any] = {"items": [], "ts": 0}
CACHE_TTL = int(os.getenv("NEWS_CACHE_TTL", "900"))  # 15 min

async def fetch_feed(url: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=15.0) as client:
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
        items.append({"title": title, "summary": summary, "url": link, "date": date_iso})
    return items

def matches_keywords(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in KEYWORDS)

def infer_tags(text: str) -> List[str]:
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

async def load_all_news() -> List[Dict[str, Any]]:
    tasks = [fetch_feed(u) for u in FEEDS.values()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    aggregated: List[Dict[str, Any]] = []
    for (source, _), res in zip(FEEDS.items(), results):
        if isinstance(res, Exception):
            continue
        for item in res:
            blob = f"{item.get('title','')} {item.get('summary','')}".lower()
            if matches_keywords(blob):
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

@app.post("/tasks/news-refresh")
async def refresh_news():
    _news_cache["items"] = await load_all_news()
    _news_cache["ts"] = time.time()
    return {"ok": True, "count": len(_news_cache["items"])}

# ========= Alta Mediadores (SQLite) =========
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

    mail_from = os.getenv("MAIL_FROM") or os.getenv("SMTP_USER")
    subject = "Tu acceso a MEDIAZION (Mediadores)"
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
        send_email_smtp(subject=subject, body=body, mail_from=mail_from, mail_to=email)
    except Exception as e:
        logger.error(f"[EMAIL] No se pudo enviar el email automático: {e}")
        return {"ok": True, "warning": f"No se pudo enviar el email automático: {e}"}

    return {"ok": True}
