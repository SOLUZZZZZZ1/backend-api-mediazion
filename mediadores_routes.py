# mediadores_routes.py — Alta completa + DNI/CIF + clave temporal + trial 7 días + correo con enlaces
from datetime import datetime, timedelta, timezone
import secrets
import bcrypt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from db import pg_conn
from contact_routes import _send_mail, MAIL_TO_DEFAULT

mediadores_router = APIRouter(prefix="/mediadores", tags=["mediadores"])

TRIAL_DAYS = 7  # días de prueba PRO
PANEL_URL = "https://mediazion.eu/panel-mediador"
CTA_SUBSCRIBE_URL = "https://mediazion.eu/suscripcion/ok?start=1"  # CTA para iniciar/animar a suscripción

class MediadorIn(BaseModel):
    name: str
    email: EmailStr
    phone: str
    provincia: str
    especialidad: str
    dni_cif: str
    tipo: str                  # "física" | "empresa"
    accept: bool

@mediadores_router.post("/register")
def register(data: MediadorIn):
    if not data.accept:
        raise HTTPException(400, "Debes aceptar la política de privacidad.")

    email = data.email.lower().strip()
    name  = data.name.strip()

    # Bloqueo de correos ya registrados
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute("SELECT id FROM mediadores WHERE email = LOWER(%s)", (email,))
            if cur.fetchone():
                raise HTTPException(409, "Este correo ya está registrado")

    # Generar contraseña temporal + hash bcrypt
    temp_password = secrets.token_urlsafe(6)[:10]
    pwd_hash = bcrypt.hashpw(temp_password.encode("utf-8"), bcrypt.gensalt()).decode()

    # Marcar alta en modo PRO (trialing) durante 7 días
    trial_start = datetime.now(timezone.utc)
    trial_end   = trial_start + timedelta(days=TRIAL_DAYS)

    # Insertar y COMMIT antes de enviar correos (para no perder el alta si falla SMTP)
    with pg_conn() as cx:
        with cx.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mediadores (
                    name, email, phone, provincia, especialidad,
                    dni_cif, tipo,
                    approved, status, subscription_status, trial_used,
                    trial_start, trial_end,
                    password_hash, created_at
                ) VALUES (
                    %s, LOWER(%s), %s, %s, %s,
                    %s, %s,
                    TRUE, 'active', 'trialing', FALSE,
                    %s, %s,
                    %s, NOW()
                )
                """,
                (
                    name, email, data.phone, data.provincia, data.especialidad,
                    data.dni_cif.strip(), data.tipo.strip(),
                    trial_start, trial_end,
                    pwd_hash
                )
            )
        cx.commit()

    # ----- CORREOS (soft-fail: no rompen el flujo si fallan) -----
    user_html = f"""
    <div style="font-family:system-ui,Segoe UI,Roboto,Arial">
      <p>Hola {name},</p>
      <p>Tu alta en <strong>MEDIAZION</strong> está activa en <strong>modo PRO (7 días gratis)</strong>.</p>
      <p><strong>Tipo:</strong> {data.tipo} &nbsp;&nbsp; <strong>DNI/CIF:</strong> {data.dni_cif}</p>
      <p><strong>Contraseña temporal:</strong> <code>{temp_password}</code></p>
      <p>Puedes acceder al panel desde aquí:
        <a href="{PANEL_URL}">{PANEL_URL}</a>
      </p>
      <p>Tu periodo de prueba termina el <strong>{trial_end.strftime('%d/%m/%Y')}</strong>. Después seguirás en modo BÁSICO si no activas la suscripción.</p>
      <p>
        <a href="{CTA_SUBSCRIBE_URL}"
           style="display:inline-block;background:#0ea5e9;color:#fff;padding:10px 14px;border-radius:8px;text-decoration:none">
           Activar suscripción definitiva
        </a>
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
        <li><strong>Trial:</strong> {trial_start.strftime('%d/%m/%Y')} → {trial_end.strftime('%d/%m/%Y')}</li>
      </ul>
    </div>
    """

    try:
        _send_mail(email, "Alta registrada · Acceso PRO 7 días · MEDIAZION", user_html, name)
        _send_mail(MAIL_TO_DEFAULT, f"[Alta Mediador] {name} <{email}>", info_html, "MEDIAZION")
    except Exception:
        pass
    # -------------------------------------------------------------

    return {"ok": True, "message": "Alta realizada. Revisa tu correo con la contraseña temporal y el enlace al panel."}

# Endpoint para que el frontend consulte el estado y pinte el CTA correcto
class StatusOut(BaseModel):
    exists: bool
    id: int | None = None
    approved: bool | None = None
    status: str | None = None            # active | disabled | canceled
    subscription_status: str | None = None  # none | trialing | active | expired
    trial_used: bool | None = None
    trial_days_left: int | None = None
    trial_end: str | None = None

@mediadores_router.get("/status", response_model=StatusOut)
def status(email: str):
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
            # calcular días restantes de trial
            t_end = data.get("trial_end")
            days_left = None
            t_end_str = None
            if t_end:
                # t_end es datetime
                t_end_str = t_end.strftime("%Y-%m-%d")
                now = datetime.now(timezone.utc)
                delta = (t_end - now).days
                days_left = max(delta, 0)

            return {
                "exists": True,
                "id": data.get("id"),
                "approved": data.get("approved"),
                "status": data.get("status"),
                "subscription_status": data.get("subscription_status"),
                "trial_used": data.get("trial_used"),
                "trial_days_left": days_left,
                "trial_end": t_end_str
            }
