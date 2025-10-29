# app.py — MEDIAZION Backend (FastAPI)
import os, sqlite3, secrets, hashlib, datetime, smtplib, ssl, time, asyncio, json, re
from email.message import EmailMessage
from typing import Optional, Dict, Any

import stripe, httpx, feedparser
from dateutil import parser as dateparser
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

app = FastAPI(title="MEDIAZION Backend", version="2.0.0")

# ---------------------- DB ----------------------
def db():
    return sqlite3.connect(os.getenv("DB_PATH", "mediazion.db"), check_same_thread=False)

def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def ensure_db():
    conn = db()
    # Tabla mediadores (alta web)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS mediadores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL,
        -- extras
        telefono TEXT,
        documento TEXT,
        num_registro TEXT,
        provincia TEXT,
        especialidad TEXT,
        bio TEXT,
        web TEXT,
        linkedin TEXT,
        acepta_politica INTEGER DEFAULT 0,
        is_subscriber INTEGER DEFAULT 0,
        stripe_customer_id TEXT,
        stripe_subscription_id TEXT,
        subscription_status TEXT,
        photo_url TEXT,
        cv_url TEXT
    )
    """)
    # Usuarios (login del panel)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'mediador',
        status TEXT NOT NULL DEFAULT 'pendiente',
        must_change_password INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """)
    # Sesiones (tokens)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    conn.commit(); conn.close()

ensure_db()

def safe_alter(sql: str):
    try:
        conn = db(); conn.execute(sql); conn.commit(); conn.close()
    except Exception:
        pass

# columnas extra idempotentes
for stmt in [
    "ALTER TABLE mediadores ADD COLUMN telefono TEXT",
    "ALTER TABLE mediadores ADD COLUMN documento TEXT",
    "ALTER TABLE mediadores ADD COLUMN num_registro TEXT",
    "ALTER TABLE mediadores ADD COLUMN provincia TEXT",
    "ALTER TABLE mediadores ADD COLUMN especialidad TEXT",
    "ALTER TABLE mediadores ADD COLUMN bio TEXT",
    "ALTER TABLE mediadores ADD COLUMN web TEXT",
    "ALTER TABLE mediadores ADD COLUMN linkedin TEXT",
    "ALTER TABLE mediadores ADD COLUMN acepta_politica INTEGER DEFAULT 0",
    "ALTER TABLE mediadores ADD COLUMN is_subscriber INTEGER DEFAULT 0",
    "ALTER TABLE mediadores ADD COLUMN stripe_customer_id TEXT",
    "ALTER TABLE mediadores ADD COLUMN stripe_subscription_id TEXT",
    "ALTER TABLE mediadores ADD COLUMN subscription_status TEXT",
    "ALTER TABLE mediadores ADD COLUMN photo_url TEXT",
    "ALTER TABLE mediadores ADD COLUMN cv_url TEXT",
    "ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0"
]:
    safe_alter(stmt)

# ---------------------- CORS ----------------------
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

# ---------------------- SMTP ----------------------
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_TLS  = (os.getenv("SMTP_TLS", "false").lower() in ("1","true","yes"))
MAIL_FROM = os.getenv("MAIL_FROM") or SMTP_USER
MAIL_TO   = os.getenv("MAIL_TO") or SMTP_USER

def send_email(subject: str, body: str, to_email: str):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        print("[EMAIL] SMTP no configurado"); return
    msg = EmailMessage()
    msg["From"] = MAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    if SMTP_TLS and SMTP_PORT != 465:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.ehlo(); s.starttls(context=ctx); s.login(SMTP_USER, SMTP_PASS); s.send_message(msg)
    else:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=30) as s:
            s.login(SMTP_USER, SMTP_PASS); s.send_message(msg)

# ---------------------- Stripe ----------------------
STRIPE_SECRET = (os.getenv("STRIPE_SECRET") or os.getenv("STRIPE_SECRET_KEY") or "").strip()
if STRIPE_SECRET:
    stripe.api_key = STRIPE_SECRET
STRIPE_PRICE_ID = (os.getenv("STRIPE_PRICE_ID") or "").strip()
STRIPE_WEBHOOK_SECRET = (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()
SUB_SUCCESS_URL = os.getenv("SUB_SUCCESS_URL") or "https://mediazion.eu/suscripcion/ok"
SUB_CANCEL_URL  = os.getenv("SUB_CANCEL_URL")  or "https://mediazion.eu/suscripcion/cancel"

# ---------------------- Util users/sessions ----------------------
def user_get_by_email(email: str):
    conn = db()
    row = conn.execute("SELECT id,email,password_hash,role,status,must_change_password FROM users WHERE email=?", (email.lower(),)).fetchone()
    conn.close()
    if row:
        return {"id":row[0],"email":row[1],"password_hash":row[2],"role":row[3],"status":row[4],"must_change_password":bool(row[5])}
    return None

def user_create(email: str, role="mediador", status="pendiente"):
    temp_pass = secrets.token_urlsafe(9)
    pwd_hash = sha256(temp_pass)
    now = datetime.datetime.utcnow().isoformat()
    conn = db()
    conn.execute("""
        INSERT INTO users (email,password_hash,role,status,created_at,must_change_password)
        VALUES (?,?,?,?,?,1)
    """, (email.lower(), pwd_hash, role, status, now))
    conn.commit(); conn.close()
    return temp_pass

def issue_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.datetime.utcnow()
    exp = now + datetime.timedelta(days=7)
    conn = db()
    conn.execute("INSERT INTO sessions (token,user_id,created_at,expires_at) VALUES (?,?,?,?)",
                 (token, user_id, now.isoformat(), exp.isoformat()))
    conn.commit(); conn.close()
    return token

def get_user_from_token(request: Request) -> Dict[str, Any]:
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Falta token")
    token = auth.split()[1]
    conn = db()
    row = conn.execute("SELECT user_id,expires_at FROM sessions WHERE token=?", (token,)).fetchone()
    if not row:
        conn.close(); raise HTTPException(401, "Token inválido")
    user_id, expires = row
    # (opcional) validar expiración
    row = conn.execute("SELECT id,email,role,status,must_change_password FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if not row: raise HTTPException(401,"Sesión no válida")
    return {"id":row[0], "email":row[1], "role":row[2], "status":row[3], "must_change_password":bool(row[4])}

# ---------------------- Salud/Contacto ----------------------
@app.get("/health")
def health(): return {"ok": True, "service": "mediazion-backend"}

@app.post("/contact")
async def contact(req: Request):
    data = await req.json()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    subject = (data.get("subject") or "Mensaje de contacto").strip()
    message = (data.get("message") or "").strip()
    if len(name)<2 or "@" not in email or len(message)<5:
        raise HTTPException(400, "Datos insuficientes.")
    body = f"Nombre: {name}\nEmail: {email}\nAsunto: {subject}\n\n{message}"
    try: send_email(f"[MEDIAZION] {subject}", body, MAIL_TO or email)
    except Exception as e: print("[EMAIL] aviso:", e)
    return {"ok": True}

# ---------------------- Alta Mediadores (extendido) ----------------------
@app.post("/mediadores/register")
async def mediadores_register(req: Request):
    data = await req.json()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    hp = (data.get("hp") or "").strip()
    if hp: raise HTTPException(400, "Spam detectado")
    if len(name)<2 or "@" not in email: raise HTTPException(400, "Nombre o email inválido.")

    telefono = (data.get("telefono") or "").strip()
    documento = (data.get("documento") or "").strip()
    num_registro = (data.get("num_registro") or "").strip()
    provincia = (data.get("provincia") or "").strip()
    especialidad = data.get("especialidad") or []
    if isinstance(especialidad, list):
        especialidad_json = json.dumps(especialidad)
    else:
        especialidad_json = json.dumps([])
    bio = (data.get("bio") or "").strip()
    web = (data.get("web") or "").strip()
    linkedin = (data.get("linkedin") or "").strip()
    acepta_politica = 1 if data.get("acepta_politica") else 0

    temp_pass = secrets.token_urlsafe(9)
    pwd_hash = sha256(temp_pass)
    now = datetime.datetime.utcnow().isoformat()

    try:
        conn = db()
        conn.execute("""
          INSERT INTO mediadores
            (name,email,password_hash,status,created_at,telefono,documento,num_registro,provincia,especialidad,bio,web,linkedin,acepta_politica)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (name, email, pwd_hash, "pending", now, telefono, documento, num_registro, provincia, especialidad_json, bio, web, linkedin, acepta_politica))
        conn.commit(); conn.close()
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Ese email ya está registrado.")

    # Aviso admin
    try:
        body_admin = f"""Nueva alta de mediador (pendiente):

Nombre: {name}
Email: {email}
Teléfono: {telefono}
Documento: {documento}
Nº Registro: {num_registro}
Provincia: {provincia}
Especialidad: {", ".join(especialidad)}
Bio: {bio}
Web: {web}
LinkedIn: {linkedin}
Acepta política: {bool(acepta_politica)}
"""
        send_email("MEDIAZION · Nueva alta de mediador (pendiente)", body_admin, MAIL_TO or email)
    except Exception as e:
        print("[EMAIL admin] aviso:", e)

    # Correo mediador
    try:
        body = f"""Hola {name},

Tu alta en MEDIAZION ha sido registrada correctamente.

Acceso temporal:
- Usuario (email): {email}
- Contraseña temporal: {temp_pass}

Estado: PENDIENTE de validación.
El Centro revisará tus datos y te avisará por correo cuando tu cuenta esté ACTIVA.

Un saludo,
MEDIAZION — Centro de Mediación y Resolución de Conflictos
"""
        send_email("MEDIAZION · Alta provisional de mediador", body, email)
    except Exception as e:
        print("[EMAIL mediador] aviso:", e)

    return {"ok": True, "message": "Alta realizada. Revisa tu correo."}

# ---------------------- LOGIN / LOGOUT / ME ----------------------
@app.post("/users/login")
async def users_login(req: Request):
    data = await req.json()
    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    if not email or not password: raise HTTPException(400, "Faltan credenciales")

    u = user_get_by_email(email)
    if not u:
        # Si no existe en users, pero está en mediadores, permite primer login con su temp (migración)
        conn = db()
        row = conn.execute("SELECT password_hash,status FROM mediadores WHERE email=?", (email,)).fetchone()
        if not row:
            conn.close(); raise HTTPException(401, "Credenciales inválidas")
        mh, mstatus = row
        if mh != sha256(password):
            conn.close(); raise HTTPException(401, "Credenciales inválidas")
        # Crea usuario en users con ese hash y obliga cambio contraseña
        now = datetime.datetime.utcnow().isoformat()
        conn.execute("INSERT INTO users (email,password_hash,role,status,created_at,must_change_password) VALUES (?,?,?,?,?,1)",
                     (email, mh, "mediador", "pendiente", now))
        conn.commit()
        uid = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]
        conn.close()
        token = issue_token(uid)
        return {"token": token, "role": "mediador", "status": "pendiente", "must_change_password": True}

    # users existe
    if u["password_hash"] != sha256(password):
        raise HTTPException(401, "Credenciales inválidas")

    token = issue_token(u["id"])
    return {"token": token, "role": u["role"], "status": u["status"], "must_change_password": u["must_change_password"]}

@app.get("/me")
async def me_endpoint(request: Request):
    u = get_user_from_token(request)
    return {"email": u["email"], "role": u["role"], "status": u["status"], "must_change_password": u["must_change_password"]}

@app.post("/users/change_password")
async def change_password(req: Request):
    u = get_user_from_token(req)
    data = await req.json()
    current = (data.get("current_password") or "").strip()
    newpwd  = (data.get("new_password") or "").strip()
    if not current or not newpwd: raise HTTPException(400, "Faltan datos")

    conn = db()
    row = conn.execute("SELECT password_hash FROM users WHERE id=?", (u["id"],)).fetchone()
    if not row: conn.close(); raise HTTPException(404, "Usuario no encontrado")
    if row[0] != sha256(current): conn.close(); raise HTTPException(401, "Contraseña actual incorrecta")

    conn.execute("UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?", (sha256(newpwd), u["id"]))
    conn.commit(); conn.close()
    return {"ok": True, "message": "Contraseña actualizada"}

# ---------------------- Perfil Panel Mediador ----------------------
@app.get("/panel/profile")
async def get_profile(request: Request):
    u = get_user_from_token(request)
    conn = db()
    row = conn.execute("""
        SELECT name, telefono, bio, provincia, especialidad, web, linkedin, photo_url, cv_url, subscription_status
        FROM mediadores WHERE email=?
    """, (u["email"],)).fetchone()
    mediador = {}
    if row:
        esp = []
        if row[4]:
            try:
                esp = json.loads(row[4]) if row[4].strip().startswith("[") else [s.strip() for s in row[4].split(",") if s.strip()]
            except Exception:
                esp = [s.strip() for s in row[4].split(",") if s.strip()]
        mediador = {
            "name": row[0] or "", "telefono": row[1] or "", "bio": row[2] or "", "provincia": row[3] or "",
            "especialidad": esp, "web": row[5] or "", "linkedin": row[6] or "",
            "photo_url": row[7] or "", "cv_url": row[8] or "", "subscription_status": row[9] or ""
        }
    # status del user
    us = conn.execute("SELECT status FROM users WHERE email=?", (u["email"],)).fetchone()
    conn.close()
    return {"user": {"email": u["email"], "status": (us[0] if us else u["status"])}, "mediador": mediador}

@app.put("/panel/profile")
async def update_profile(request: Request):
    u = get_user_from_token(request)
    data = await request.json()
    name = (data.get("name") or "").strip()
    telefono = (data.get("telefono") or "").strip()
    bio = (data.get("bio") or "").strip()
    provincia = (data.get("provincia") or "").strip()
    web = (data.get("web") or "").strip()
    linkedin = (data.get("linkedin") or "").strip()
    especialidad = data.get("especialidad") or []
    if not isinstance(especialidad, list):
        raise HTTPException(400, "especialidad debe ser lista")
    esp_csv = ",".join(sorted(set([str(e).strip() for e in especialidad if e])))

    conn = db()
    row = conn.execute("SELECT id FROM mediadores WHERE email=?", (u["email"],)).fetchone()
    if row:
        conn.execute("""
            UPDATE mediadores
            SET name=?, telefono=?, bio=?, provincia=?, especialidad=?, web=?, linkedin=?
            WHERE email=?
        """, (name, telefono, bio, provincia, esp_csv, web, linkedin, u["email"]))
    else:
        now = datetime.datetime.utcnow().isoformat()
        conn.execute("""
            INSERT INTO mediadores (name,email,telefono,bio,provincia,especialidad,web,linkedin,created_at,status)
            VALUES (?,?,?,?,?,?,?,?,?, 'pending')
        """, (name, u["email"], telefono, bio, provincia, esp_csv, web, linkedin, now))
    conn.commit(); conn.close()
    return {"ok": True}

# -------- Uploads
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

def _sanitize(filename: str) -> str:
    base = os.path.basename(filename)
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base) or "file.bin"

@app.post("/upload/file")
async def upload_file(request: Request, file: UploadFile = File(...), kind: Optional[str] = "photo"):
    if kind not in ("photo","cv"): raise HTTPException(400, "kind inválido")
    u = get_user_from_token(request)
    content = await file.read()
    if len(content) > 10*1024*1024: raise HTTPException(400, "Archivo >10MB")
    fname = _sanitize(file.filename or f"{kind}.bin")
    user_dir = os.path.join("uploads", str(u["id"]))
    os.makedirs(user_dir, exist_ok=True)
    path = os.path.join(user_dir, f"{kind}_{int(time.time())}_{fname}")
    with open(path, "wb") as f:
        f.write(content)
    url = f"/uploads/{u['id']}/{os.path.basename(path)}"
    col = "photo_url" if kind=="photo" else "cv_url"
    conn = db()
    conn.execute(f"UPDATE mediadores SET {col}=? WHERE email=?", (url, u["email"]))
    conn.commit(); conn.close()
    return {"ok": True, "url": url}

# ---------------------- News (feeds corregidos) ----------------------
FEEDS = {
    "BOE": "https://www.boe.es/rss/boe.xml",
    "CONFILEGAL": "https://confilegal.com/feed/",
    "LEGALTODAY": "https://www.legaltoday.com/feed/",
    # Añade RSS específicos del CGPJ si lo deseas
}
KEYWORDS = ["mediación","mediador","adr","resolución alternativa","acuerdo","conflicto"]
_news_cache={"items":[], "ts":0}; CACHE_TTL=int(os.getenv("NEWS_CACHE_TTL","900"))

async def fetch_feed(url: str) -> list[dict]:
    items=[]
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent":"Mozilla/5.0 (MEDIAZION/1.0)"}) as client:
        r=await client.get(url)
        r.raise_for_status()
        d=feedparser.parse(r.text)
    for e in d.entries[:40]:
        title=(getattr(e,"title","") or "").strip()
        summary=(getattr(e,"summary","") or "").strip()
        link=(getattr(e,"link","") or "").strip()
        date_raw=getattr(e,"published",None) or getattr(e,"updated",None)
        date_iso=None
        if date_raw:
            try: date_iso=dateparser.parse(date_raw).date().isoformat()
            except: date_iso=None
        if any(k in f"{title} {summary}".lower() for k in KEYWORDS):
            items.append({"title":title,"summary":summary,"url":link,"date":date_iso})
    return items

async def load_all_feeds()->list[dict]:
    tasks=[fetch_feed(u) for u in FEEDS.values()]
    res=await asyncio.gather(*tasks, return_exceptions=True)
    out=[]
    for (src,_),it in zip(FEEDS.items(),res):
        if isinstance(it,Exception): print("[NEWS] error",src,it); continue
        for x in it:
            # etiquetas simples
            txt=(x["title"]+" "+x["summary"]).lower()
            tags=[t for t in ["civil","mercantil","laboral","penal","internacional","normativa","jurisprudencia","doctrina"] if t in txt]
            out.append({"title":x["title"],"summary":x["summary"],"url":x["url"],"date":x["date"],"source":src,"tags":tags})
    out.sort(key=lambda k: k["date"] or "", reverse=True)
    return out[:120]

@app.get("/news")
async def news(source: Optional[str]=None, tag: Optional[str]=None, q: Optional[str]=None, limit:int=50):
    now=time.time()
    global _news_cache
    if now-_news_cache["ts"]>CACHE_TTL or not _news_cache["items"]:
        _news_cache={"items":await load_all_feeds(),"ts":now}
    items=list(_news_cache["items"])
    if source: items=[i for i in items if i["source"].lower()==source.lower()]
    if tag: items=[i for i in items if tag.lower() in [t.lower() for t in i.get("tags",[])]]
    if q: items=[i for i in items if (q.lower() in (i["title"] or "").lower()) or (q.lower() in (i["summary"] or "").lower())]
    return items[:max(1,min(limit,200))]

# ---------------------- Stripe ----------------------
@app.post("/subscribe")
async def subscribe(req: Request):
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
    payload=await request.body()
    sig=request.headers.get("stripe-signature")
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
        cust_id=session.get("customer"); sub_id=session.get("subscription")
        if email:
            conn=db()
            conn.execute("""
              UPDATE mediadores SET is_subscriber=1, stripe_customer_id=?, stripe_subscription_id=?, subscription_status='active'
              WHERE email=?
            """,(cust_id, sub_id, email.lower()))
            conn.commit(); conn.close()
            # crea user si no existe
            if not user_get_by_email(email):
                temp=user_create(email, role="mediador", status="pendiente")
                try:
                    body=f"""Hola,

Tu suscripción como mediador en MEDIAZION se ha activado.

Acceso provisional:
- Usuario (email): {email}
- Contraseña temporal: {temp}

Estado: PENDIENTE de validación. Cambia tu contraseña en el primer acceso.
"""
                    send_email("MEDIAZION · Acceso provisional de mediador", body, email)
                except Exception as e:
                    print("[EMAIL] webhook aviso:", e)
        return {"received":True}

    elif etype=="invoice.paid":
        return {"received":True}
    elif etype=="invoice.payment_failed":
        return {"received":True}
    return {"received":True}
