\
# instituciones_login_routes.py — Login real para instituciones contra instituciones_usuarios
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db import pg_conn
import bcrypt

router = APIRouter(prefix="/api/instituciones", tags=["instituciones"])

class InstitucionLoginIn(BaseModel):
    email: str
    password: str

class InstitucionLoginOut(BaseModel):
    email: str
    institucion: str
    tipo: str
    cargo: str
    nombre: str
    provincia: Optional[str] = None
    estado: str
    fecha_expiracion: Optional[str] = None
    token: str

@router.post("/login", response_model=InstitucionLoginOut)
def instituciones_login(body: InstitucionLoginIn):
    email = body.email.strip()
    password = body.password.strip()

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email y contraseña son obligatorios.")

    try:
        with pg_conn() as cx:
            with cx.cursor() as cur:
                cur.execute(
                    '''
                    SELECT email,
                           password_hash,
                           institucion,
                           tipo,
                           cargo,
                           nombre,
                           provincia,
                           estado,
                           fecha_expiracion
                      FROM instituciones_usuarios
                     WHERE LOWER(email) = LOWER(%s)
                    ''',
                    (email,),
                )
                row = cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error de base de datos: {e}")

    if not row:
        raise HTTPException(status_code=401, detail="Credenciales no válidas.")

    (
        db_email,
        db_password_hash,
        db_institucion,
        db_tipo,
        db_cargo,
        db_nombre,
        db_provincia,
        db_estado,
        db_fecha_expiracion,
    ) = row

    # Comprobamos estado
    if db_estado not in ("activo", "activo ".strip()):
        # Puedes matizar mensajes según 'caducado' / 'suspendido', etc.
        raise HTTPException(status_code=403, detail=f"Cuenta institucional no activa (estado: {db_estado}).")

    # Comprobamos contraseña
    if not db_password_hash:
        raise HTTPException(status_code=401, detail="Credenciales no válidas.")

    try:
        ok = bcrypt.checkpw(password.encode("utf-8"), db_password_hash.encode("utf-8"))
    except Exception:
        ok = False

    if not ok:
        raise HTTPException(status_code=401, detail="Credenciales no válidas.")

    # Token sencillo para sesión (si luego quieres JWT, aquí se genera)
    session_token = f"inst-{db_email}"

    fecha_expiracion_str = None
    if db_fecha_expiracion is not None:
        # Lo devolvemos en ISO para que el frontend lo pueda usar directamente
        try:
            fecha_expiracion_str = db_fecha_expiracion.isoformat()
        except Exception:
            fecha_expiracion_str = str(db_fecha_expiracion)

    return {
        "email": db_email,
        "institucion": db_institucion,
        "tipo": db_tipo or "",
        "cargo": db_cargo or "",
        "nombre": db_nombre or "",
        "provincia": db_provincia or "",
        "estado": db_estado or "",
        "fecha_expiracion": fecha_expiracion_str,
        "token": session_token,
    }
