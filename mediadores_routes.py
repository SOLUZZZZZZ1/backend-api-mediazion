# mediadores_routes.py — Alta de Mediadores completa
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from db import pg_conn
from contact_routes import _send_mail, MAIL_TO_DEFAULT

mediadores_router = APIRouter(prefix="/mediadores")

class MediadorIn(BaseModel):
    name: str
    email: EmailStr
    phone: str
    provincia: str
    especialidad: str
    accept: bool

@mediadores_router.post("/register")
def register(data: MediadorIn):
    if not data.accept:
        raise HTTPException(400, "Debes aceptar la política de privacidad.")

    email = data.email.lower().strip()
    name  = data.name.strip()

    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("""
                INSERT INTO mediadores (name,email,phone,provincia,especialidad,approved,status,subscription_status,trial_used)
                VALUES (%s, LOWER(%s), %s, %s, %s, TRUE, 'active', 'none', FALSE)
                ON CONFLICT (email) DO UPDATE
                SET name=EXCLUDED.name,
                    phone=EXCLUDED.phone,
                    provincia=EXCLUDED.provincia,
                    especialidad=EXCLUDED.especialidad,
                    approved=TRUE,
                    status='active'
            """, (name, email, data.phone, data.provincia, data.especialidad))
            cx.commit()

    user_html = f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,Arial">
      <p>Hola {name},</p>
      <p>Tu alta como mediador en <strong>MEDIAZION</strong> se ha registrado correctamente.</p>
      <p>Puedes acceder a tu panel desde la web.</p>
      <p>Un saludo,<br/>Equipo MEDIAZION</p>
    </div>
    """
    info_html = f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,Arial">
      <p>Nuevo alta de mediador:</p>
      <ul>
        <li><strong>Nombre:</strong> {name}</li>
        <li><strong>Email:</strong> {email}</li>
        <li><strong>Teléfono:</strong> {data.phone}</li>
        <li><strong>Provincia:</strong> {data.provincia}</li>
        <li><strong>Especialidad:</strong> {data.especialidad}</li>
      </ul>
    </div>
    """
    _send_mail(email, "Alta registrada · MEDIAZION", user_html, name)
    _send_mail(MAIL_TO_DEFAULT, f"[Alta Mediador] {name} <{email}>", info_html, "MEDIAZION")

    return {"ok": True, "message": "Alta realizada. Revisa tu correo."}
