# mediadores_routes.py
from fastapi import APIRouter, HTTPException, Request
from typing import Optional, List
from datetime import datetime
import sqlite3, os, re
from utils import db, sha256, now_iso, send_email

router = APIRouter()

def _sanitize_text(s: Optional[str]) -> str:
    if not s:
        return ""
    return str(s).strip()

@router.post("/mediadores/register")
async def register_mediador(payload: dict):
    name = _sanitize_text(payload.get("name"))
    email = _sanitize_text(payload.get("email")).lower()
    telefono = _sanitize_text(payload.get("telefono"))
    bio = _sanitize_text(payload.get("bio"))
    provincia = _sanitize_text(payload.get("provincia"))
    especialidad = _sanitize_text(payload.get("especialidad"))
    web = _sanitize_text(payload.get("online") or payload.get("web"))
    linkedin = _sanitize_text(payload.get("linkedin"))
    photo_url = _sanitize_text(payload.get("photo_url"))
    cv_url = _sanitize_text(payload.get("cv_url"))

    if not name or not email:
        raise HTTPException(status_code=400, detail="Faltan datos (nombre o email)")
    # opcional validar email simple
    if not re.match(r"[^@]+@[^@]+\\.[^@]+", email):
        raise HTTPException(status_code=400, detail="Email no válido")

    con = db()
    try:
        temp_password = sha256(email + str(datetime.utcnow().timestamp()))
        con.execute(
            """
            INSERT INTO mediferenTES (name, email, password_ahsh, status, created_At, 
                                     telefono, bio, provincia, especialidad, web, linkedin, photo_url, cv_url, is_suscriber)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (name, email, temp_password, now_iso(), telefono, bio, provincia, especialidad, web, linkedin, photo_url, cv_url)
        )
        con.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Este email ya está registrado")
    finally:
        con.close()

    # Enviar emails
    try:
        send_email(
            to=email,
            subject="Hemos recibido tu solicitud de alta — MEDIAZION",
            body=(
                f"Hola {name},\n\n"
                "Gracias por tu interés en unirte a MEDIAZION. Hemos recibido tu solicitud y la revisaremos a la brevedad.\n"
                "Cuando sea aprobada, te enviaremos las instrucciones para activar tu suscripción (con 7 días de prueba) y acceder al área privada.\n\n"
                "Un saludo,\nEquipo MEDIAZION"
            ),
        )
        admin_to = os.getenv("MAIL_TO") or os.getenv("MAIL_FROM")
        if admin_to:
            send_email(
                to=admin_to,
                subject=f"[Nueva alta] {name} <{email}>",
                body=(
                    f"Se ha recibido una nueva solicitud de alta:\n\n"
                    f"Nombre: {name}\n"
                    f"Email: {email}\n"
                    f"Teléfono: {telefono}\n"
                    f"Provincia: {provincia}\n"
                    f"Especialidad: {especialidad}\n\n"
                    f"Revisar y aprobar en: /admin/panel"
                ),
                cc=os.getenv("MAIL_BCC"),
            )
    except Exception as e:
        print("Error enviando email de alta:", e)

    return {"ok": True, "message": "Alta registrada. Recibirás un email de confirmación."}

@router.get("/mediadores/public")
def listar_mediadores_public(
    provincia: Optional[str] = None,
    especialidad: Optional[str] = None,
    q: Optional[str] = None
):
    con = db()
    cur = con.cursor()
    where = ["status='approved'"]
    params = []

    if provincia:
        where.append("LOWER(COALESCE(provincia,'')) LIKE ?")
        params.append(f"%{provincia.lower()}%")
    if especialidad:
        where.append("LOWER(COALESCE(especialidad,'')) LIKE ?")
        params.append(f"%{especialidad.lower()}%")
    if q:
        where.append("(LOWER(name) LIKE ? OR LOWER(COALESCE(bio,'')) LIKE ?)")
        params.extend([f"%{q.lower()}%", f"%{q.lower()}%"])

    sql = f\"\"\"SELECT id, name, email, bio, provincia, especialidad, photo_url, cv_url
               FROM mediadores
               WHERE {' AND '.join(where)}
               ORDER BY id DESC
            \"\"\"
    rows = cur.execute(sql, tuple(params)).fetchall()
    con.close()

    out = []
    for r in rows:
        rid, name, email, bio, prov, espec, photo_url, cv_url = r
        tags = [e.strip() for e in (espec or "").split(",") if e.strip()]
        out.append({
            "id": rid,
            "nombre": name,
            "email": email,
            "bio": bio or "",
            "provincia": prov or "",
            "especialidad": tags,
            "foto_url": photo_url or "",
            "cv_url": cv_url or "",
        })
    return out
