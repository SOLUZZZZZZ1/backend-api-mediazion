# instituciones_routes.py — Endpoints públicos para instituciones (registro + emails)
from fastapi import APIRouter, HTTPException
from db import pg_conn

# Reutilizamos el mismo SMTP y helper que contacto
from contact_routes import _send_mail, MAIL_TO_DEFAULT, MAIL_FROM_NAME, MAIL_FROM

instituciones_router = APIRouter(prefix="/instituciones", tags=["instituciones"])


@instituciones_router.post("/registro")
def registro_institucion(body: dict):
    """
    Recibe el formulario de registro institucional,
    lo guarda en la tabla instituciones_registro
    y envía dos correos:
      - uno interno a MEDIAZION (MAIL_TO_DEFAULT)
      - otro a la institución confirmando la solicitud.
    """
    campos_oblig = ["tipo", "institucion", "cargo", "nombre", "email"]
    for c in campos_oblig:
        if not body.get(c):
            raise HTTPException(400, f"Falta el campo obligatorio: {c}")

    tipo = body.get("tipo", "").strip()
    institucion = body.get("institucion", "").strip()
    cargo = body.get("cargo", "").strip()
    nombre = body.get("nombre", "").strip()
    email = body.get("email", "").strip()
    telefono = (body.get("telefono") or "").strip()
    provincia = (body.get("provincia") or "").strip()
    comentarios = (body.get("comentarios") or "").strip()

    # 1) Guardar en BD
    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute(
                """
                INSERT INTO instituciones_registro
                (tipo, institucion, cargo, nombre, email, telefono, provincia, comentarios)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    tipo,
                    institucion,
                    cargo,
                    nombre,
                    email,
                    telefono,
                    provincia,
                    comentarios,
                ),
            )
            cx.commit()
    except Exception as e:
        raise HTTPException(500, f"Error registrando institución: {e}")

    # 2) Email interno a MEDIAZION (como contacto)
    try:
        asunto_admin = f"[Mediazion] Nueva solicitud institucional: {institucion}"
        info_html = f"""
        <div style="font-family:system-ui,Segoe UI,Roboto,Arial">
          <p>Se ha recibido una nueva solicitud de ALTA INSTITUCIONAL:</p>
          <ul>
            <li><strong>Tipo:</strong> {tipo}</li>
            <li><strong>Institución:</strong> {institucion}</li>
            <li><strong>Cargo:</strong> {cargo}</li>
            <li><strong>Nombre:</strong> {nombre}</li>
            <li><strong>Email:</strong> {email}</li>
            <li><strong>Teléfono:</strong> {telefono or '-'}</li>
            <li><strong>Provincia:</strong> {provincia or '-'}</li>
          </ul>
          <p><strong>Comentarios:</strong></p>
          <p>{comentarios or '-'}</p>
        </div>
        """
        _send_mail(
            MAIL_TO_DEFAULT,
            asunto_admin,
            info_html,
            "MEDIAZION",
        )
    except Exception as e:
        # No queremos romper el flujo si el correo falla
        print(f"[AVISO] Error enviando correo interno instituciones: {e}")

    # 3) Email de confirmación a la institución
    try:
        asunto_inst = "Mediazion · Confirmación de solicitud institucional"
        user_html = f"""
        <div style="font-family:system-ui,Segoe UI,Roboto,Arial; white-space:pre-wrap">
Hola {nombre},

Gracias por tu interés en Mediazion. Hemos recibido la solicitud de:

· Tipo de institución: {tipo}
· Institución: {institucion}
· Cargo: {cargo}
· Email de contacto: {email}
· Teléfono: {telefono or '-'}
· Provincia: {provincia or '-'}

Nuestro equipo revisará la información y se pondrá en contacto contigo
para explicarte los siguientes pasos y, en su caso, activar el acceso
institucional (piloto o plan anual/semestral).

Un saludo,
Mediazion
{MAIL_TO_DEFAULT}
        </div>
        """
        _send_mail(
            email,
            asunto_inst,
            user_html,
            nombre,
        )
    except Exception as e:
        print(f"[AVISO] Error enviando correo a institución: {e}")

    return {"ok": True}
