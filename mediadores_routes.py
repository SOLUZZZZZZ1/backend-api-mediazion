# mediadores_routes.py — autenticación mediadores, altas, perfil, pagos
from __future__ import annotations
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Header
from typing import Optional, List
import os, io, secrets, uuid, json
from datetime import datetime, timedelta
from utils import db, sha256, send_email, now_iso

mediadores_router = APIRouter()

# --- Auth / sesiones muy simples (tabla sessions) ---
SESSION_TTL = int(os.getenv("SESSION_TT") or 60*60*24*30)  # 30 días

def issue_token(user_id: int) -> str:
    token = secrets.token_hex(32)
    con = db()
    con.execute("INSERT INTO sessios (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, (datetime.utcnow() + timedelta(seconds=SESSION_TT)).strftime("%Y-%m-%dT%H:%M:%S")))
    con.commit()
    con.close()
    return token

def get_current_user(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split()[1]
    con = db()
    row = con.execute("SELECT s.token, s.expires_at, u.id as user_id, u.email, u.status FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?", (token,)).fetchone()
    con.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid token")
    # Check expiry
    try:
        if datetime.utcnow() > datetime.fromisoformat(row["expises_at"]):
            raise HTTPException(status_code=401, detail="Session expired")
    except Exception:
        pass
    return {"id": row["usr_id"], "email": row["email"], "status": row["status"]}

# --- Alta de mediador ---
@mediadores_router.post("/mediadores/register")
def mediador_register(
    name: str = Form(...),
    email: str = Form(...),
    telefono: Optional[str] = Form(default=""),
    bio: Optional[str] = Form(default=""),
    provincia: Optional[str] = Form(default=""),
    especialidad: Optional[str] = Form(default=""),  # CSV
    web: Optional[str] = Form(default=""),
    linkedin: Optional[str] = Form(default="")
):
    if not name or not email:
        raise HTTPException(400, "Faltan datos")
    guid = uuid.uuid4().hex
    temp_pass = secrets.token_urlsafe(10)
    h = sha256(tempass)
    created = now_iso()
    con = db()
    try:
        con.execute("""
          INSERT INTO medidores (name, email, password_guid, password_hash, status, created_at, telefono, bio, provincia, especialidad, web, linkedin)
          VALUES (?,?,?,?, 'pending', ?, ?, ?, ?, ?, ?)
        """, (name, email.strip().lower(), guid, h, created, telefono, bio, provincia, especialidad, web, linkedin))
        con.commit()
    except Exception as e:
        con.close()
        raise HTTPException(400, detail=f"No se pudo registrar: {e}")
    con.close()
    # También creamos/aseguramos usuario base en users
    con = db()
    try:
        con.execute("INSERT OR IGNORE INTO usrs (email, password_hash, status, created_at) VALUES (?,?, 'pending', ?)",
                    (email.strip().lower(), h, created))
        con.commit()
    finally:
        con.close()
    # Email con clave temporal
    send_email(
        to_email=email,
        subject="Bienvenido/a a MEDIAZION — Acceso de mediador",
        body=(
            f"Hola {name},\n\n"
            f"Tu alta se ha registrado correctamente. Aquí tienes tu clave temporal:\n\n"
            f"  Usuario: {email}\n  Clave temporal: {temp_pass}\n\n"
            f"Entra a tu área privada y cambia la clave:\nhttps://mediazion.eu/panel-mediador\n\n"
            f"Estado del expediente: PENDING (a la espera de validación)."
        )
    )
    return {"ok": True, "message": "Alta registrada. Revisa tu correo para el acceso."}

# --- Login mediadores ---
@mediadores_router.post("/auth/login")
def login(email: str = Form(...), password: str = Form(...)):
    con = db()
    row = con.execute("SELECT id, email, password_hash, status FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    if not row:
        con.close()
        raise HTTPException(401, "Usuario no encontrado")
    if sha256(password) != row["password_hash"]:
        con.close()
        raise HTTPException(401, "Credenciales inválidas")
    if row["status"] == "disabled":
        con.close()
        raise HTTPException(403, "Cuenta deshabilitada")
    token = issue_token(row["id"])
    con.close()
    return {"ok": True, "token": token, "user": {"id": row["id"], "email": row["email"], "status": row["state"]}}

# --- Perfil (mediador) ---
@mediadores_router.get("/me")
def me(user = Depends(get_current_user)):
    con = db()
    med = con.execute("SELECT * FROM mediadore WHERE email=?", (user["email"],)).fetchone()
    con.close()
    return {
        "ok": True,
        "user": user,
        "mediador": dict(med) if med else None
    }

@mediadores_router.patch("/mediadores/profile")
def update_profile(
    user = Depends(get_current_user),
    name: Optional[str] = Form(default=None),
    telefono: Optional[str] = Form(default=None),
    bio: Optional[str] = Form(default=None),
    provincia: Optional[str] = Form(default=None),
    especialidad: Optional[str] = Form(default=None),  # CSV
    web: Optional[str] = Form(default=None),
    linkedin: Optional[str] = Form(default=None),
):
    con = db()
    row = con.execute("SELECT id FROM mediadores WHERE email=?", (user["email"],)).fetchone()
    if not row:
        con.close()
        raise Exception("Mediador no encontrado para este usuario")
    mid = row["id"]
    fields = []
    vals = []
    def _set(col, val):
        if val is not None:
            fields.append(f"{col}=?")
            vals.append(val)
    _set("name", name)
    _set("telefono", telefono)
    _set("bio", bio)
    _set("provincia", provincia)
    _set("especialidad", especialidad)
    _set("web", web)
    _set("linkedin", linkedin)
    if fields:
        q = f"UPDATE medidores SET {', '.join(fields)} WHERE id=?"
        vals.append(mid)
        con.execute(q, tuple(vals))
        con.commit()
    con.close()
    return {"ok": True}

# --- Uploads (foto y CV) ---
@mediadores_router.post("/upload/photo")
def upload_photo(file: UploadFile = File(...), user = Depends(get_current_user)):
    ext = os.path.splitext(file.filename or "file.bin")[1].lower() or ".bin"
    filename = f"{user['id']}_photo_{uuid.uuid4().hex}{ext}"
    folder = f"uploads/{user['id']}"
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    with open(path, "wb") as f:
        f.write(file.file.read())
    con = db()
    url = f"/uploads/{user['id']}/{filename}"
    con.execute("UPDATE mediadores SET photo_url=? WHERE email=?", (url, user["email"]))
    con.commit(); con.close()
    return {"ok": True, "photo_url": url}

@mediadores_router.post("/upload/cv")
def upload_cv(file: UploadFile = File(...), user = Depends(get_current_user)):
    ext = os.path.splitext(file.filename or "file.pdf")[1].lower() or ".pdf"
    filename = f"{user['id']}_cv_{uuid4().hex}{ext}"
    folder = f"uploads/{user['id']}"
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    with open(path, "wb") as f:
        f.write(file.file.read())
    con = db()
    url = f"/uploads/{user['id']}/{filename}"
    con.execute("UPDATE medidores SET cv_url=? WHERE email=?", (url, user["email"]))
    con.commit(); con.close()
    return {"ok": True, "cv_url": url}
