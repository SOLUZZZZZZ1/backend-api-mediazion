# mediadores_routes.py — alta/login/perfil/uploads + Stripe con trial 7 días (robusto form/JSON)
import os, secrets, json, time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Header, Depends, UploadFile, File, Request
from pydantic import BaseModel, EmailStr
from utils import db, sha256, now_iso, send_email

mediadores_router = APIRouter()

# ---------- Sesiones ----------
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL", "2592000"))  # 30 días

def issue_session_token(user_id: int) -> str:
    token = secrets.token_hex(32)
    conn = db()
    expires = (datetime.utcnow() + timedelta(seconds=SESSION_TTL_SECONDS)).strftime("%Y-%m-%dT%H:%M:%S")
    conn.execute("INSERT INTO sessions (token,user_id,expires_at) VALUES (?,?,?)", (token, user_id, expires))
    conn.commit(); conn.close()
    return token

def get_current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing token")
    token = authorization.split()[1]
    conn = db()
    row = conn.execute("""
        SELECT s.expires_at, u.id, u.email, u.status
        FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?
    """, (token,)).fetchone()
    if not row: conn.close(); raise HTTPException(401, "Invalid token")
    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        conn.execute("DELETE FROM sessions WHERE token=?", (token,)); conn.commit(); conn.close()
        raise HTTPException(401, "Session expired")
    conn.close()
    return {"id": row["id"], "email": row["email"], "status": row["status"]}

# Gateo: suscriptor activo o trial vigente
def has_active_access(email: str) -> bool:
    conn = db()
    row = conn.execute("""
      SELECT COALESCE(is_subscriber,0) AS is_subscriber,
             COALESCE(is_trial,0)      AS is_trial,
             trial_expires_at
      FROM mediadores WHERE email=?
    """, (email.lower(),)).fetchone()
    conn.close()
    if not row: return False
    if row["is_subscriber"] == 1: return True
    if row["is_trial"] == 1 and row["trial_expires_at"]:
        try:
            return datetime.utcnow() < datetime.fromisoformat(row["trial_expires_at"])
        except Exception:
            return False
    return False

# ---------- Alta de mediador (robusta: JSON o FORM) ----------
def _get_str(raw: Dict[str, Any], key: str) -> str:
    """Devuelve valor string normalizado desde raw (acepta list/None)."""
    v = raw.get(key, "")
    if isinstance(v, list):  # starlette FormData puede devolver listas
        v = v[0] if v else ""
    if v is None:
        v = ""
    return str(v).strip()

@mediadores_router.post("/mediadores/register")
async def mediador_register(request: Request):
    """
    Acepta:
      - JSON: application/json
      - Form: multipart/form-data o application/x-www-form-urlencoded
    """
    ctype = (request.headers.get("content-type") or "").lower()
    try:
        if ctype.startswith("application/json"):
            raw = await request.json()
        elif ctype.startswith("multipart/") or ctype.startswith("application/x-www-form-urlencoded"):
            form = await request.form()
            raw = dict(form)
        else:
            # fallback: intentar json
            try:
                raw = await request.json()
            except Exception:
                form = await request.form()
                raw = dict(form)
    except Exception:
        raise HTTPException(400, "Cuerpo de solicitud inválido")

    name        = _get_str(raw, "name") or _get_str(raw, "nombre")
    email       = _get_str(raw, "email").lower()
    telefono    = _get_str(raw, "telefono")
    bio         = _get_str(raw, "bio")
    provincia   = _get_str(raw, "provincia")
    especialidad= _get_str(raw, "especialidad")  # CSV opcional
    web         = _get_str(raw, "web")
    linkedin    = _get_str(raw, "linkedin")

    if not name or not email:
        raise HTTPException(422, "Faltan nombre o email")

    # Password temporal y alta
    temp_pwd = secrets.token_urlsafe(10)
    pwd_hash = sha256(temp_pwd)
    created  = now_iso()
    conn = db()
    try:
        conn.execute("""
          INSERT INTO mediadores (name,email,password_hash,status,created_at,telefono,bio,provincia,especialidad,web,linkedin)
          VALUES (?,?,?,'pending',?,?,?,?,?,?)
        """, (name, email, pwd_hash, created, telefono, bio, provincia, especialidad, web, linkedin))
        conn.execute("""
          INSERT OR IGNORE INTO users (email,password_hash,status,created_at)
          VALUES (?,?, 'pending', ?)
        """, (email, pwd_hash, created))
        conn.commit()
    except Exception as ex:
        conn.rollback(); raise HTTPException(400, f"No se pudo registrar: {ex}")
    finally:
        conn.close()

    # Email de acceso
    try:
        send_email(
            email,
            "MEDIAZION · Acceso de mediador",
            f"Hola {name}\n\nUsuario: {email}\nContraseña temporal: {temp_pwd}\n\nPanel: https://mediazion.eu/panel-mediador\nEstado: PENDIENTE"
        )
    except Exception as e:
        print("[email] aviso:", e)

    return {"ok": True, "message": "Alta registrada. Revisa tu correo."}

# ---------- Login ----------
class LoginIn(BaseModel):
    email: EmailStr
    password: str

@mediadores_router.post("/auth/login")
def auth_login(body: LoginIn):
    conn = db()
    row = conn.execute("SELECT id,email,password_hash,status FROM users WHERE email=?", (body.email.lower(),)).fetchone()
    if not row: conn.close(); raise HTTPException(401, "Usuario no encontrado")
    if row["status"] == "disabled": conn.close(); raise HTTPException(403, "Cuenta deshabilitada")
    if sha256(body.password) != row["password_hash"]: conn.close(); raise HTTPException(401, "Credenciales inválidas")
    token = issue_session_token(row["id"]); conn.close()
    return {"ok": True, "token": token, "user": {"id": row["id"], "email": row["email"], "status": row["status"]}}

# ---------- Cambio de contraseña ----------
class ChangePwdIn(BaseModel):
    current_password: str
    new_password: str

@mediadores_router.post("/users/change_password")
def change_password(body: ChangePwdIn, user=Depends(get_current_user)):
    conn = db()
    row = conn.execute("SELECT password_hash FROM users WHERE id=?", (user["id"],)).fetchone()
    if not row: conn.close(); raise HTTPException(404, "Usuario no encontrado")
    if sha256(body.current_password) != row["password_hash"]:
        conn.close(); raise HTTPException(401, "Contraseña actual incorrecta")
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (sha256(body.new_password), user["id"]))
    conn.commit(); conn.close()
    return {"ok": True, "message": "Contraseña actualizada"}

# ---------- Perfil & acceso ----------
@mediadores_router.get("/panel/profile")
def get_profile(user=Depends(get_current_user)):
    conn = db()
    m = conn.execute("""
      SELECT name,telefono,bio,provincia,especialidad,web,linkedin,photo_url,cv_url,
             COALESCE(is_subscriber,0) AS is_subscriber,
             COALESCE(subscription_status,'') AS subscription_status,
             COALESCE(is_trial,0) AS is_trial,
             trial_expires_at
      FROM mediadores WHERE email=?
    """, (user["email"],)).fetchone()
    conn.close()
    mediador = dict(m) if m else {}
    mediador["has_access"] = has_active_access(user["email"])
    return {"user": user, "mediador": mediador}

class ProfileUpdateIn(BaseModel):
    name: Optional[str] = None
    telefono: Optional[str] = None
    bio: Optional[str] = None
    provincia: Optional[str] = None
    especialidad: Optional[str] = None
    web: Optional[str] = None
    linkedin: Optional[str] = None

@mediadores_router.put("/panel/profile")
def update_profile(body: ProfileUpdateIn, user=Depends(get_current_user)):
    conn = db()
    row = conn.execute("SELECT id FROM mediadores WHERE email=?", (user["email"],)).fetchone()
    if not row: conn.close(); raise HTTPException(404, "Mediador no encontrado")
    fields, vals = [], []
    for col, val in body.dict().items():
        if val is not None:
            fields.append(f"{col}=?"); vals.append(val)
    if fields:
        vals.append(user["email"])
        conn.execute(f"UPDATE mediadores SET {', '.join(fields)} WHERE email=?", tuple(vals))
        conn.commit()
    conn.close()
    return {"ok": True}

# ---------- Uploads (photo, cv, doc para IA) ----------
from fastapi import UploadFile
@mediadores_router.post("/upload/file")
def upload_file(kind: str, file: UploadFile = File(...), user=Depends(get_current_user)):
    if kind not in ("photo","cv","doc"):
        raise HTTPException(400, "kind inválido")
    uid = str(user["id"])
    folder = os.path.join("uploads", uid)
    os.makedirs(folder, exist_ok=True)
    ext = ".bin"
    if file.filename and "." in file.filename:
        ext = "." + file.filename.rsplit(".",1)[-1].lower()
    fname = f"{kind}_{int(time.time())}{ext}"
    path = os.path.join(folder, fname)
    with open(path, "wb") as f:
        f.write(file.file.read())
    url = f"/uploads/{uid}/{fname}"
    col = "photo_url" if kind=="photo" else ("cv_url" if kind=="cv" else "doc_url")
    conn = db()
    try:
        conn.execute("ALTER TABLE mediadores ADD COLUMN doc_url TEXT")
    except Exception:
        pass
    conn.execute(f"UPDATE mediadores SET {col}=? WHERE email=?", (url, user["email"]))
    conn.commit(); conn.close()
    return {"ok": True, "url": url}

# ---------- Stripe con trial 7d ----------
import stripe as _stripe

def stripe_client():
    key = os.getenv("STRIPE_SECRET") or os.getenv("STRIPE_SECRET_KEY")
    if not key: raise HTTPException(500, "Stripe secret missing")
    _stripe.api_key = key
    return _stripe

class SubscribeIn(BaseModel):
    email: EmailStr
    priceId: Optional[str] = None

@mediadores_router.post("/subscribe")
def subscribe(body: SubscribeIn):
    client = stripe_client()
    price_id = body.priceId or os.getenv("STRIPE_PRICE_ID")
    if not price_id: raise HTTPException(400, "Missing STRIPE_PRICE_ID")
    try:
        session = client.checkout.Session.create(
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            customer_email=body.email,
            subscription_data={"trial_period_days": 7},
            allow_promotion_codes=True,
            success_url="https://mediazion.eu/suscripcion/ok",
            cancel_url="https://mediazion.eu/suscripcion/cancel",
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(500, f"Stripe error: {e}")

@mediadores_router.post("/webhook")
async def webhook(req: Request):
    client = stripe_client()
    payload = await req.body()
    sig = req.headers.get("stripe-signature")
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    try:
        event = client.Webhook.construct_event(payload, sig, secret) if secret else json.loads(payload.decode())
    except Exception as e:
        raise HTTPException(400, f"Webhook error: {e}")

    et = event.get("type")
    data = event.get("data",{}).get("object",{})

    if et == "checkout.session.completed":
        email = data.get("customer_email") or (data.get("customer_details") or {}).get("email")
        if email:
            expires = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
            conn = db()
            conn.execute("""
              UPDATE mediadores
              SET subscription_status='trialing', is_trial=1, trial_expires_at=?, is_subscriber=0
              WHERE email=?
            """, (expires, email.lower()))
            # asegura user
            row = conn.execute("SELECT id FROM users WHERE email=?", (email.lower(),)).fetchone()
            if not row:
                conn.execute("INSERT INTO users (email,password_hash,status,created_at) VALUES (?,?,?,?)",
                             (email.lower(), sha256(secrets.token_urlsafe(8)), "pending", now_iso()))
            conn.commit(); conn.close()
        return {"received": True}

    if et == "customer.subscription.updated":
        status = data.get("status")            # trialing|active|canceled|...
        conn = db()
        if status == "active":
            conn.execute("""
              UPDATE mediadores SET subscription_status='active', is_subscriber=1, is_trial=0
              WHERE subscription_status!='active'
            """)
        elif status == "canceled":
            conn.execute("""
              UPDATE mediadores SET subscription_status='canceled', is_subscriber=0, is_trial=0
            """)
        else:
            conn.execute("UPDATE mediadores SET subscription_status=?", (status,))
        conn.commit(); conn.close()
        return {"received": True}

    return {"received": True}
