# mediadores_password_routes.py — Cambio de contraseña real para mediadores
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from db import pg_conn
import bcrypt

router = APIRouter(prefix="/mediadores", tags=["mediadores-password"])


class ChangePasswordIn(BaseModel):
    email: EmailStr
    old_password: str
    new_password: str


@router.post("/change-password")
def change_password(body: ChangePasswordIn):
    """
    Permite a un mediador cambiar su contraseña usando:
    - email
    - contraseña actual
    - nueva contraseña
    """
    email = body.email.strip().lower()

    with pg_conn() as cx, cx.cursor() as cur:
        # 1) buscar mediador
        cur.execute(
            "SELECT id, password_hash FROM mediadores WHERE LOWER(email)=LOWER(%s);",
            (email,),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Mediador no encontrado")

        mediador_id, pwd_hash = row

        # 2) comprobar contraseña actual
        try:
            ok = bcrypt.checkpw(body.old_password.encode("utf-8"), pwd_hash.encode("utf-8"))
        except Exception:
            ok = False

        if not ok:
            raise HTTPException(status_code=400, detail="La contraseña actual no es correcta")

        # 3) generar hash de la nueva contraseña
        new_hash = bcrypt.hashpw(
            body.new_password.encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")

        # 4) actualizar en BD
        cur.execute(
            "UPDATE mediadores SET password_hash=%s WHERE id=%s;",
            (new_hash, mediador_id),
        )
        cx.commit()

    return {"ok": True, "message": "Contraseña actualizada correctamente."}
