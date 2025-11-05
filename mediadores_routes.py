# mediadores_routes.py — Alta completa + trial 7 días + status + password temporal (bcrypt)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta, timezone
from db import pg_conn
from contact_routes import _send_mail, MAIL_TO_DEFAULT
import secrets, bcrypt

mediadores_router = APIRouter(prefix="/mediadores", tags=["mediadores"])

TRIAL_DAYS = 7
PANEL_URL = "https://mediazion.eu/panel-mediador"
SUBSCRIBE_CTA_URL = "https://mediazion.eu/suscripcion/ok?start=1"  # CTA para abrir Checkout desde UI

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

    # Bloqueo de duplicados por email (case-insensitive)
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT id FROM mediadores WHERE email = LOWER(%s)", (email,))
            if cur.fetchone():
                raise HTTPException(409, "Este correo ya está registrado")

    # Generar password temporal y hash
    temp_password = secrets.token_urlsafe(6)[:10]
    pwd_hash = bcrypt.hashpw(temp_password.encode("utf-8"), bcrypt.gensalt()).decode()

    # Trial window
    trial_start = datetime.now(timezone.utc)
    trial_end   = trial_start + timedelta(days=TRIAL_DAYS)

    # Insertar registro y COMMIT antes de enviar correo
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("""
                INSERT INTO mediadores (
                    name, email, phone, provincia, especialidad,
                    dni_cif, tipo,
                    approved, status, subscription_status, trial_used,
                    trial_start, trial_end,
                    password_hash
                )
                VALUES (%s, LOWER(%s), %s, %s, %s,
                        %s, %s,
                        TRUE, 'active', 'trialing', FALSE,
                        %s, %s,
                        %s)
            """, (name, email, data.phone, data.provincia, data.especialidad,
                  data.dni_cif.strip(), data.tipo.strip(),
                  trial_start, trial_end, pwd_hash))
        cx.commit()

    # Correo al usuario + copia interna (soft-fail si SMTP cae)
    user_html = f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,Arial">
      <p>Hola {name},</p>
      <p>Tu alta en <strong>MEDIAZION</strong> está activa en <strong>modo PRO (7 días gratis)</strong>.</p>
      <p><strong>Tipo:</strong> {data.tipo} &nbsp;&nbsp; <strong>DNI/CIF:</strong> {data.dni_cif}</p>
      <p><strong>Contraseña temporal:</strong> <code>{temp_password}</code></p>
      <p>Puedes acceder a tu panel desde aquí:
        <a href="{PANEL_URL}">{PANEL_URL}</a>
      </p>
      <p>Tu periodo de prueba termina el <strong>{trial_end.strftime('%d/%m/%Y')}</strong>. Después seguirás en modo BÁSICO si no activas la suscripción.</p>
      <p>
        <a href="{SUBSCRIBE_CTA_URL}" style="display:inline-block;background:#0ea5e9;color:#fff;padding:10px 14px;border-radius:8px;text-decoration:none">Activar suscripción definitiva</a>
      </p>
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
        <li><strong>Trial hasta:</strong> {trial_end.strftime('%d/%m/%Y')}</li>
      </ul>
    </div>
    """
    try:
        _send_mail(email, "Alta PRO (7 días) · MEDIAZION", user_html, name)
        _send_mail(MAIL_TO_DEFAULT, f"[Alta Mediador] {name} <{email}>", info_html, "MEDIAZION")
    except Exception:
        pass

    return {"ok": True, "message": "Alta realizada. Revisa tu correo con la contraseña temporal y el enlace al panel."}

@mediadores_router.get("/status")
def status(email: str):
    """Devuelve estado de suscripción y días restantes de trial."""
    e = email.lower().strip()
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("""
                SELECT id, approved, status, subscription_status, trial_used, trial_start, trial_end
                  FROM mediadores
                 WHERE email = LOWER(%s)
            """, (e,))
            row = cur.fetchone()
            if not row:
                return {"exists": False}
            cols = [d[0] for d in cur.description]
            data = {cols[i]: row[i] for i in range(len(cols))}
            data["exists"] = True
            # calcular días restantes si hay trial
            days_left = None
            if data.get("subscription_status") == "trialing" and data.get("trial_end"):
                delta = (data["trial_end"] - datetime.now(timezone.utc)).days
                days_left = max(0, delta)
            data["trial_days_left"] = days_left
            return data
