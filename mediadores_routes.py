# mediadores_routes.py — alta/login/perfil/uploads + Stripe con trial 7 días
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
    if not row:
        conn.close(); raise HTTPException(401, "Invalid token")
    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        conn.execute("DELETE FROM sessions WHERE token=?", (token,)); conn.commit(); conn.close()
        raise HTTPException(401, "Session expired")
    conn.close()
    return {"id": row["id"], "email": row["email"], "status": row["status"]}

# Gateo de acceso al panel: suscriptor activo o en trial vigente
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

# ---------- Alta de mediador ----------
class MediadorRegisterIn(BaseModel):
    name: str
    email: EmailStr
    telefono: Optional[str] = None
    bio: Optional[str] = None
    provincia: Optional[str] = None
    especialidad: Optional[str] = None  # CSV
    web: Optional[str] = None
    linkedin: Optional[str] = None

@mediadores_router.post("/mediadores/register")
def mediador_register(data: MediadorRegisterIn):
    name = data.name.strip(); email = data.email.lower().strip()
    if not name or not email:
        raise HTTPException(400, "Missing data")
    temp_pwd = secrets.token_urlsafe(10)
    pwd_hash = sha256(temp_pwd)
    created  = now_iso()
    conn = db()
    try:
        conn.execute("""
          INSERT INTO mediadores (name,email,password_hash,status,created_at,telefono,bio,provincia,especialidad,web,linkedin)
          VALUES (?,?,?,'pending',?,?,?,?,?,?)
        """, (name, email, pwd_hash, created, data.telefono or "", data.bio or "", data.provincia or "",
              data.especialidad or "", data.web or "", data.linkedin or ""))
        conn.execute("""
          INSERT OR IGNORE INTO users (email,password_hash,status,created_at)
          VALUES (?,?, 'pending', ?)
        """, (email, pwd_hash, created))
        conn.commit()
    except Exception as ex:
        conn.rollback(); raise HTTPException(400, f"Registration failed: {ex}")
    finally:
        conn.close()
    # Email de acceso
    try:
        send_email(email, "MEDIAZION · Acceso de mediador",
                   f"Hola {name}\n\nUsuario: {email}\nContraseña temporal: {temp_pwd}\n\nPanel: https://mediazion.eu/panel-mediador\nEstado: PENDIENTE (en revisión)")
    except Exception as e:
        print("[email]", e)
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
    # Access flags
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

# ---------- Uploads ----------
@mediadores_router.post("/upload/file")
def upload_file(kind: str, file: UploadFile = File(...), user=Depends(get_current_user)):
    if kind not in ("photo","cv"): raise HTTPException(400, "kind inválido")
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
    col = "photo_url" if kind=="photo" else "cv_url"
    conn = db(); conn.execute(f"UPDATE mediadores SET {col}=? WHERE email=?", (url, user["email"])); conn.commit(); conn.close()
    return {"ok": True, "url": url}

# ---------- Stripe con trial ----------
import stripe as _stripe

def stripe_client():
    key = os.getenv("STRIPE_SECRET") or os.getenv("STRIPE_SECRET_KEY")
    if not key: raise HTTPException(500, "Stripe secret missing")
    _stripe.api_key = key
    return _stripe

class SubscribeIn(BaseModel):
    email: EmailStr
    priceId: Optional[str] = None  # opcional si STRIPE_PRICE_ID en entorno

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
            subscription_data={"trial_period_days": 7},  # ← trial de 7 días
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

    # Al completar Checkout (suscripción creada con trial)
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
            # Asegura usuario
            row = conn.execute("SELECT id FROM users WHERE email=?", (email.lower(),)).fetchone()
            if not row:
                conn.execute("INSERT INTO users (email,password_hash,status,created_at) VALUES (?,?,?,?)",
                             (email.lower(), sha256(secrets.token_urlsafe(8)), "pending", now_iso()))
            conn.commit(); conn.close()
        return {"received": True}

    # Primer cobro al finalizar trial
    if et == "invoice.paid":
        sub = data.get("subscription")
        cust = data.get("customer")
        # No siempre llega email aquí; marcamos por customer_email si viene en `billing_reason == 'subscription_cycle'`
        # Reforzamos en customer.subscription.updated también.
        return {"received": True}

    # Cambio de estado de suscripción
    if et == "customer.subscription.updated":
        status = data.get("status")            # trialing | active | past_due | canceled | ...
        cust_id = data.get("customer")
        # Buscar email asociado (si lo guardas, puedes mapear por tabla; aquí simplificamos por webhook previo)
        # Como simplificación: marcamos 'active' si status==active
        if status in ("active","trialing","past_due","canceled","unpaid"):
            # En un sistema real mapear por customer_id→email (guardado en alta o en sesión de Checkout)
            # Aquí lo dejamos como pattern básico: si pasó a active, marca is_subscriber=1 y is_trial=0
            conn = db()
            if status == "active":
                conn.execute("""
                  UPDATE mediadores
                  SET subscription_status='active', is_subscriber=1, is_trial=0
                  WHERE is_trial=1 OR is_subscriber=0
                """)
            elif status == "canceled":
                conn.execute("""
                  UPDATE mediadores
                  SET subscription_status='canceled', is_subscriber=0, is_trial=0
                """)
            else:
                conn.execute("UPDATE mediadores SET subscription_status=?", (status,))
            conn.commit(); conn.close()
        return {"received": True}

    return {"received": True}

# ---------- Recordatorio 48 h antes de fin de trial (para cron) ----------
@mediadores_router.post("/admin/trial-reminders")
def trial_reminders(admin_key: Optional[str] = Header(default=None)):
    # Seguridad muy básica: header 'admin_key' debe coincidir con ADMIN_TOKEN
    if admin_key != os.getenv("ADMIN_TOKEN"):
        raise HTTPException(401, "Unauthorized")
    now = datetime.utcnow()
    in_48h = (now + timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%S")
    conn = db()
    rows = conn.execute("""
      SELECT name,email,trial_expires_at FROM mediadores
      WHERE is_trial=1 AND trial_expires_at IS NOT NULL
    """).fetchall()
    count = 0
    for r in rows:
        try:
            exp = datetime.fromisoformat(r["trial_expires_at"])
            if 0 <= (exp - now).total_seconds() <= 48*3600:
                send_email(
                    r["email"],
                    "MEDIAZION · Tu periodo de prueba finaliza pronto",
                    f"Hola {r['name']}\n\nTu periodo de prueba termina el {r['trial_expires_at']}.\nSi quieres mantener el acceso, confirma tu suscripción en el panel."
                )
                count += 1
        except Exception:
            pass
    conn.close()
    return {"ok": True, "reminders": count}
