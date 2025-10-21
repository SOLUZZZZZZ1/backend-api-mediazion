from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
import os, smtplib, ssl, time, asyncio
from email.message import EmailMessage

# --- News deps ---
import httpx, feedparser
from dateutil import parser as dateparser

app = FastAPI(title="MEDIAZION Backend (contact + news)", version="1.0.0")

# ===== CORS =====
ALLOWED = os.getenv("ALLOWED_ORIGINS", "*")
allow_origins = [o.strip() for o in ALLOWED.split(",")] if ALLOWED and ALLOWED != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== Health =====
@app.get("/health")
def health():
    return {"ok": True, "service": "mediazion-backend"}

# ===== Email (contact) =====
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

    if port == 465 and not use_tls:
        # SSL directo
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            server.login(user, password)
            server.send_message(msg)
    else:
        # STARTTLS
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.login(user, password)
            server.send_message(msg)

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
        return {"ok": False, "error": str(e)}

# ===== News (auto-aggregator) =====

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
CACHE_TTL = int(os.getenv("NEWS_CACHE_TTL", "900"))  # 15 min por defecto

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
        items = [i for i in items if tag
