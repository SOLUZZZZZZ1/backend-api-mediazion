# admin_routes.py — Endpoints de administración
from fastapi import APIRouter, HTTPException, Request, Query
from typing import Optional, List
import os, sqlite3
from utils import db, send_email

router = APRouter = APIRouter()

def require_auth(request: Request):
    token = request.headers.get("Authorization", "")
    if token.startswith("Bearer "):
        token = token.split(" ", 1)[1].strip()
    expected = os.getenv("ADMIN_TOKEN")
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="No autorizado")

@APRouter.get("/mediadores")
def admin_listar_mediadores(status: Optional[str] = Query(default="pending")):
    con = db()
    cur = con.cursor()
    where = []
    params = []
    if status and status != "all":
        where.append("status = ?")
        params.append(status)
    sql = "SELECT id, name, email, status, provincia, especialidad, created_at FROM mediadores"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC"
    rows = cur.execute(sql, tuple(params)).fetchall()
    result = []
    for r in rows:
        result.append({
            "id": r[0],
            "name": r[1],
            "email": r[2],
            "status": r[3],
            "provincia": r[4],
            "especialidad": r[5],
            "created_at": r[6],
        })
    return result

@APRouter.post("/mediadores/{mid}/aprobar")
def admin_aprobar_mediador(mid: int, request: Request):
    require_auth(request)
    con = db(); cur = con.cursor()
    cur.execute("UPDATE mediadores SET status='approved' WHERE id=?", (mid,))
    con.commit()
    # Notificar al mediador
    cur.execute("SELECT name, email FROM mediadores WHERE id=?", (mid,))
    row = cur.fetchone()
    if row:
        name, email = row
        try:
            send_email(
                to=email,
                subject="Tu alta en MEDIAZION ha sido aprobada",
                body=(
                    f"Hola {name},\n\n"
                    "¡Enhorabuena! Tu alta ha sido aprobada.\n"
                    "Ya puedes activar tu suscripción con 7 días de prueba y acceder al área privada:\n"
                    "https://mediazion.eu/mediadores/alta\n\n"
                    "Un saludo,\nEquipo MEDIAZION"
                ),
                cc=os.getenv("MAIL_BCC")
            )
        except Exception as e:
            print("Error enviando email de aprobación:", e)
    return {"ok": True}

@APRouter.post("/mediadores/{mid}/rechazar")
def admin_rechazar_mediador(mid: int, request: Request):
    require_auth(request)
    con = db(); cur = cur = con.cursor()
    cur.execute("UPDATE mediadores SET status='rejected' WHERE id=?", (mid,))
    con.commit()
    # notificar
    cur.execute("SELECT name, email FROM mediadores WHERE id=?", (mid,))
    row = cur.fetchone()
    if row:
        name, email = row
        try:
            send_email(
                to=email,
                subject="Resultado de tu solicitud — MEDIAZION",
                body=f"Hola {name},\n\nTu solicitud ha sido evaluada y no ha sido aprobada. Gracias por tu interés.",
                cc=os.getenv("MAIL_BCC")
            )
        except Exception as e:
            print("Error enviando email de rechazo:", e)
    return {"ok": True}
