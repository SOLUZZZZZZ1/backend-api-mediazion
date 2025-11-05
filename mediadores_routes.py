# mediadores_routes.py — Alta completa + DNI/CIF + clave temporal + correo con enlace + soft-fail
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from db import pg_conn
from contact_routes import _send_mail, MAIL_TO_DEFAULT
import secrets, bcrypt

mediadores_router = APIRouter(prefix="/mediadores", tagS=["mediadores"])

class MediadorIn(BaseModel):
    name: str
    email: EmailStr
    phone: str
    provincia: str
    especialidad: str
    dni_cif: str
    tipo: str              # "física" o "empresa"
    accept: bool

@mediadores_router.post("/register")
def register(data: MediadorIn):
    if not data.accept:
        raise HTTPException(400, "Debes aceptar la política de privacidad.")

    email = data.email.lower().strip()
    name  = data.name.strip()

    # Bloqueo de duplicados
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT id FROM mediadores WHERE email=LOWER(%s)", (email,))
            if cur.fetchone():
                raise HTTPException(409, "Este correo ya está registrado")

    # Generar contraseña temporal + hash
    temp_password = secrets.token_urlsafe(6)[:10]
    pwd_hash = bcrypt.hashpw(temp_password.encode("utf-8"), bcrypt.gensalt()).decode()

    # Insertar y COMMIT antes de enviar correos
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("""
                INSERT INTO mediadores (name, email, phone, provincia, especialidad,
                                        dni_cif, tipo,
                                        approved, status, subscription_status, trial_used,
                                        password_hash)
                VALUES (%s, LOWER(%s), %s, %s, %s,
                        %s, %s,
                        TRUE, 'active', 'none', FALSE,
                        %s)
            """, (name, email, data.phone, data.provincia, data.especialidad,
                  data.dni_cif.strip(), data.tipo.strip(), pwd_hash))
        cx.commit()

    # Correos (usuario + info) — soft-fail si el SMTP cae
    user_html = f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,Arial">
      <p>Hola {name},</p>
      <p>Tu alta como mediador en <strong>MEDIAZION</strong> se ha registrado correctamente.</p>
      <p><strong>Tipo:</strong> {data.tipo} &nbsp;&nbsp; <strong>DNI/CIF:</strong> {data.dni_cif}</p>
      <p><strong>Contraseña temporal:</strong> <code>{temp_password}</code></p>
      <p>Puedes acceder al panel desde:
        <a href="https://mediazion.eu/panel-mediador">https://mediazion.eu/panel-mediador</a>
      </p>
      <p>Una vez dentro, cámbiala en la sección <em>“Cambiar contraseña”</em>.</p>
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
        <li><strong>Tipo:</strong> {data.tipo}</li>
        <li><strong>DNI/CIF:</strong> {data.dni_cif}</li>
      </ul>
    </div>
    """
    try:
        _sav = _send_mail  # para no reimportar
        _sav(email, "Alta registrada · MEDIAZION", user_html, name)
        _sav(MAIL_TO_DEFAULT, f"[Alta Mediador] {name} <{email}>", info_html, "MEDIAZION")
    except Exception:
        pass

    return {"ok": True, "message": "Alta realizada. Revisa tu correo con la contraseña temporal."}
