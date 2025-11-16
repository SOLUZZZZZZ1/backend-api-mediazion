# mediadores_register_routes.py — Registro real de mediadores
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from db import pg_conn
import bcrypt
from contact_routes import _send_mail  # ya lo tienes en tu backend

register_router = APIRouter()

class MediadorRegister(BaseModel):
    name: str
    email: EmailStr
    phone: str
    provincia: str
    especialidad: str
    dni_cif: str
    tipo: str
    accept: bool

def _hash(pwd: str) -> str:
    return bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

@register_router.post("/mediadores/register")
def register_mediador(body: MediadorRegister):
    if not body.accept:
        raise HTTPException(400, "Debes aceptar la política de privacidad")

    email = body.email.strip().lower()

    # contraseña temporal (8 caracteres)
    temp_pwd = bcrypt.gensalt().decode("utf-8")[:10]
    temp_hash = _hash(temp_pwd)

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            # ¿ya existe?
            cur.execute("SELECT 1 FROM mediadores WHERE LOWER(email)=LOWER(%s);", (email,))
            if cur.fetchone():
                raise HTTPException(409, "Este correo ya está registrado")

            cur.execute("""
                INSERT INTO mediadores
                    (name, email, phone, provincia, especialidad, dni_cif, tipo,
                     password_hash, subscription_status, status, approved, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s,
                        %s, 'none', 'active', TRUE, NOW());
            """, (
                body.name, email, body.phone, body.provincia,
                body.especialidad, body.dni_cif, body.tipo,
                temp_hash
            ))
            cx.commit()

        # enviar correo con contraseña temporal
        html = f"""
        <div style="font-family:system-ui,Segoe UI,Roboto,Arial">
          <h2>¡Bienvenido/a a MEDIAZION!</h2>
          <p>Tu cuenta se ha creado correctamente. Aquí tienes tu contraseña temporal:</p>
          <p><b>{temp_pwd}</b></p>
          <p>Puedes cambiarla desde tu Panel cuando accedas.</p>
        </div>
        """
        _send_mail(email, "Alta de mediador · MEDIAZION", html, email)

        return {"ok": True, "message": "Alta realizada. Revisa tu email con la contraseña temporal."}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error en registro: {e}")
