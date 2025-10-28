# app.py — MEDIAZION Backend (FastAPI) — Alta automatizada tras Stripe
import os, sqlite3, secrets, hashlib, datetime, smtplib, ssl, time, asyncio
from email.message import EmailMessage

import stripe, httpx, feedparser
from dateutil import parser as dateparser
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

# ---------- Config ----------
app = FastAPI(title="MEDIAZION Backend", version="1.3.0")

def db(): return sqlite3.connect(os.getenv("DB_PATH", "mediazion.db"), check_same_thread=False)

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

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
    conn.execute("""
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'mediador',
        status TEXT NOT NULL DEFAULT 'pendiente',
        created_at TEXT NOT NULL
      )
    """)
    conn.commit(); conn.close()

ensure_db()

# CORS
def parse_origins(raw: str|None) -> list[str]:
    if not raw: return ["https://mediazion.eu", "https://www.mediazion.eu"]
    return [o.strip() for o in raw.split(",") if o.strip()]

allow_origins = parse_origins(os.getenv("ALLOWED_ORIGINS"))
app.add_middleware(
  CORSMiddleware,
  allow_origins=allow_origins,
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

# SMTP
SMTP_HOST = os.getenv("SMTP_HOST"); SMTP_PORT = int(os.getenv("SMTP_PORT","465"))
SMTP_USER = os.getenv("SMTP_USER"); SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_TLS  = (os.getenv("SMTP_TLS","false").lower() in ("1","true","yes"))
MAIL_FROM = os.getenv("MAIL_FROM") or SMTP_USER
MAIL_TO   = os.getenv("MAIL_TO") or SMTP_USER

def send_email(subject:str, body:str, to_email:str):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS): 
        print("[EMAIL] SMTP no configurado"); return
    msg = EmailMessage(); msg["From"]=MAIL_FROM; msg["To"]=to_email; msg["Subject"]=subject; msg.set_content(body)
    if SMTP_TLS and SMTP_PORT != 465:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.ehlo(); s.starttls(context=ctx); s.login(SMTP_USER, SMTP_PASS); s.send_message(msg)
    else:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=30) as s:
            s.login(SMTP_USER, SMTP_PASS); s.send_message(msg)

# Stripe
STRIPE_SECRET = (os.getenv("STRIPE_SECRET") or os.getenv("STRIPE_SECRET_KEY") or "").strip()
if STRIPE_SECRET:
    stripe.api_key = STRIPE_SECRET
STRIPE_PRICE_ID = (os.getenv("STRIPE_PRICE_ID") or "").strip()
STRIPE_WEBHOOK_SECRET = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
SUB_SUCCESS_URL = os.getenv("SUB_SUCCESS_URL") or "https://mediazion.eu/suscripcion/ok"
SUB_CANCEL_URL  = os.getenv("SUB_CANCEL_URL")  or "https://mediazion.eu/suscripcion/cancel"

# ---------- Salud ----------
@app.get("/health")
def health(): return {"ok":True,"service":"mediazion-backend"}

# ---------- Contacto ----------
@app.post("/contact")
async def contact(req: Request):
    data = await req.json()
    name = (data.get("name") or "").strip(); email = (data.get("email") or "").strip()
    subject = (data.get("subject") or "Mensaje de contacto").strip()
    message = (data.get("message") or "").strip()
    if len(name)<2 or "@" not in email or len(message)<5: raise HTTPException(400,"Datos insuficientes.")
    body = f"Nombre: {name}\nEmail: {email}\nAsunto: {subject}\n\n{message}"
    try: send_email(f"[MEDIAZION] {subject}", body, MAIL_TO or email)
    except Exception as e: print("[EMAIL] aviso:", e)
    return {"ok":True}

# ---------- Alta manual mediadores ----------
def mediator_insert(name:str, email:str):
    temp_pass = secrets.token_urlsafe(9)
    pwd_hash = sha256(temp_pass)
    now = datetime.datetime.utcnow().isoformat()
    conn = db()
    conn.execute(
      "INSERT INTO mediadores (name, email, password_hash, created_at) VALUES (?,?,?,?)",
      (name, email.lower(), pwd_hash, now)
    ); conn.commit(); conn.close()
    # correo al mediador
    body = f"""Hola {name},

Te hemos dado de alta como MEDIADOR en MEDIAZION.

Acceso temporal:
- Usuario (email): {email}
- Contraseña temporal: {temp_pass}

Por seguridad, cambia tu contraseña tras el primer acceso.
"""
    try: send_email("MEDIAZION · Alta provisional de mediador", body, email)
    except Exception as e: print("[EMAIL] aviso:", e)

@app.post("/mediadores/register")
async def mediadores_register(req:Request):
    data = await req.json()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    if len(name)<2 or "@" not in email: raise HTTPException(400,"Nombre o email inválido.")
    try:
        mediator_insert(name, email)
    except sqlite3.IntegrityError:
        raise HTTPException(409,"Ese email ya está registrado.")
    return {"ok":True,"message":"Alta realizada. Revisa tu correo."}

# ---------- Users (alta automática) ----------
def user_get_by_email(email:str):
    conn = db(); cur = conn.execute(
      "SELECT id,email,password_hash,role,status,created_at FROM users WHERE email = ?",
      (email.lower(),)
    ); row = cur.fetchone(); conn.close()
    if row: return {"id":row[0],"email":row[1],"password_hash":row[2],"role":row[3],"status":row[4],"created_at":row[5]}
    return None

def user_create(email:str, role="mediador", status="pendiente"):
    temp_pass = secrets.token_urlsafe(9)
    pwd_hash = sha256(temp_pass)
    now = datetime.datetime.utcnow().isoformat()
    conn = db()
    conn.execute(
      "INSERT INTO users (email,password_hash,role,status,created_at) VALUES (?,?,?,?,?)",
      (email.lower(), pwd_hash, role, status, now)
    ); conn.commit(); conn.close()
    return temp_pass

def user_set_status(email:str, new_status:str):
    conn = db(); conn.execute("UPDATE users SET status=? WHERE email=?",(new_status, email.lower())); conn.commit(); conn.close()

# ---------- Noticias ----------
FEEDS = {
  "BOE":"https://www.boe.es/rss/boe_es.php",
  "CGPJ":"https://www.poderjudicial.es/cgpj/es/Temas/Actualidad/rss/Actualidad",
  "MINISTERIO_JUSTICIA":"https://www.mjusticia.gob.es/es/actualidad/rss",
  "EURLEX_DOUE":"https://eur-lex.europa.eu/rss/es/index.html",
  "CONFILEGAL":"https://confilegal.com/feed/",
  "LEGALTODAY":"https://www.legaltoday.com/feed/",
}
KEYWORDS = ["mediación","mediador","adr","resolución alternativa","acuerdo","conflicto"]
_news_cache={"items":[], "ts":0}; CACHE_TTL=int(os.getenv("NEWS_CACHE_TTL","900"))

def match(t:str)->bool:
    t=(t or "").lower(); return any(k in t for k in KEYWORDS)

async def fetch_feed(url:str)->list[dict]:
    items=[]
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent":"Mozilla/5.0 (MEDIAZION/1.0)"}) as client:
        r=await client.get(url); r.raise_for_status(); d=feedparser.parse(r.text)
    for e in d.entries[:30]:
        title=(getattr(e,"title","") or "").strip()
        summary=(getattr(e,"summary","") or "").strip()
        link=(getattr(e,"link","") or "").strip()
        date_raw=getattr(e,"published",None) or getattr(e,"updated",None)
        date_iso=None
        if date_raw:
            try: date_iso=dateparser.parse(date_raw).date().isoformat()
            except: date_iso=None
        if match(f"{title} {summary}"): items.append({"title":title,"summary":summary,"url":link,"date":date_iso})
    return items

async def load_all()->list[dict]:
    tasks=[fetch_feed(u) for u in FEEDS.values()]
    res=await asyncio.gather(*tasks, return_exceptions=True)
    out=[]
    for (src,_),it in zip(FEEDS.items(),res):
        if isinstance(it,Exception): print("[NEWS] error",src, it); continue
        for x in it:
            out.append({
              "title":x["title"], "summary":x["summary"], "url":x["url"], "date":x["date"],
              "source":src, "tags":[t for t in ["civil","mercantil","laboral","penal","internacional","normativa","jurisprudencia","doctrina"] if t in (x["title"]+" "+x["summary"]).lower()]
            })
    out.sort(key=lambda k: k["date"] or "", reverse=True)
    return out[:120]

@app.get("/news")
async def news(source:str|None=None, tag:str|None=None, q:str|None=None, limit:int=50):
    now=time.time()
    global _news_cache
    if now-_news_cache["ts"]>CACHE_TTL or not _news_cache["items"]:
        _news_cache={"items":await load_all(),"ts":now}
    items=list(_news_cache["items"])
    if source: items=[i for i in items if i["source"].lower()==source.lower()]
    if tag: items=[i for i in items if tag.lower() in [t.lower() for t in i.get("tags",[])]]
    if q: items=[i for i in items if (q.lower() in (i["title"] or "").lower()) or (q.lower() in (i["summary"] or "").lower())]
    return items[: max(1,min(limit,200))]

# ---------- Stripe: Checkout & Webhook ----------
@app.post("/subscribe")
async def subscribe(req:Request):
    if not STRIPE_SECRET: raise HTTPException(500,"Stripe no configurado")
    data=await req.json()
    email=(data.get("email") or "").strip()
    price_id=(data.get("priceId") or STRIPE_PRICE_ID or "").strip()
    if not price_id: raise HTTPException(400,"Falta STRIPE_PRICE_ID")
    try:
        session=stripe.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price":price_id,"quantity":1}],
            customer_email=email or None,
            allow_promotion_codes=True,
            success_url=SUB_SUCCESS_URL+"?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=SUB_CANCEL_URL,
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(500,str(e))

@app.post("/webhook")
async def stripe_webhook(request: Request):
    payload=await request.body(); sig=request.headers.get("stripe-signature")
    try:
        if STRIPE_WEBHOOK_SECRET:
            event=stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        else:
            event=stripe.Event.construct_from(await request.json(), stripe.api_key)
    except Exception as e:
        raise HTTPException(400,str(e))

    etype=event["type"]; data=event["data"]["object"]
    if etype=="checkout.session.completed":
        session=data
        email=session.get("customer_email") or (session.get("customer_details") or {}).get("email")
        if email and not user_get_by_email(email):
            temp=user_create(email, role="mediador", status="pendiente")
            # Email de acceso provisional
            try:
                body=f"""Hola,

Tu suscripción como mediador en MEDIAZION se ha activado.

Acceso provisional:
- Usuario (email): {email}
- Contraseña temporal: {temp}

Estado de tu cuenta: PENDIENTE de validación. Te avisaremos cuando esté ACTIVA.
"""
                send_email("MEDIAZION · Acceso provisional de mediador", body, email)
            except Exception as e:
                print("[EMAIL] aviso (webhook):", e)
        print("[Stripe] checkout.session.completed OK:", email)
        return {"received":True}

    elif etype=="invoice.paid":
        print("[Stripe] invoice.paid", data.get("id")); return {"received":True}
    elif etype=="invoice.payment_failed":
        print("[Stripe] invoice.payment_failed", data.get("customer")); return {"received":True}
    return {"received":True}

# ---------- Admin: validar mediador ----------
@app.post("/admin/mediadores/validar")
async def admin_validar(req:Request):
    body=await req.json()
    email=(body.get("email") or "").strip().lower()
    if not email: raise HTTPException(400,"Falta email")
    if not user_get_by_email(email): raise HTTPException(404,"No existe ese usuario")
    user_set_status(email,"activo")
    try:
        send_email("MEDIAZION · Cuenta validada",
                   "Tu cuenta de mediador ha sido VALIDADA. Ya puedes acceder con normalidad.",
                   email)
    except Exception as e:
        print("[EMAIL] aviso (validación):", e)
    return {"ok":True,"email":email,"status":"activo"}
