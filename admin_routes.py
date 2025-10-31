# admin_routes.py — panel mínimo admin
from fastapi import APIRouter, HTTPException, Request
from sqlite3 import Row
from utils import db, send_mail

ADMIN_TOKEN = "supersecreto123"  # cámbialo en entorno
admin_router = APIRouter()

def _auth(request: Request):
    token = (request.headers.get("Authorization","").replace("Bearer ","")).strip()
    if token != ADMIN_TOKEN:
        raise HTTPException(401, "No autorizado")

@admin_router.get("/mediadores")
def listar_mediadores(request: Request, status: str = "pending"):
    _auth(request)
    con = db(); con.row_factory = Row
    rows = con.execute("SELECT * FROM mediadores WHERE status=?", (status,)).fetchall()
    con.close()
    return [dict(r) for r in rows]

@admin_router.post("/mediadores/{mid}/approve")
def aprobar_mediador(mid: int, request: Request):
    _auth(request)
    con = db(); cur = con.execute("SELECT name,email FROM mediadores WHERE id=?", (mid,))
    row = cur.fetchone()
    if not row: 
        con.close(); raise HTTPException(404, "No existe")
    con.execute("UPDATE mediadores SET status='approved' WHERE id=?", (mid,))
    con.commit(); con.close()
    # notifica
    try:
        send_mail(row[1], "Aprobado en MEDIAZION", f"Hola {row[0]}, tu alta ha sido aprobada.")
    except Exception:
        pass
    return {"ok": True}

@admin_router.post("/mediadores/{mid}/reject")
def rechazar_mediador(mid: int, request: Request):
    _auth(request)
    con = db(); cur = con.execute("SELECT email FROM mediadores WHERE id=?", (mid,))
    row = cur.fetchone()
    if not row: 
        con.close(); raise HTTPException(404, "No existe")
    con.execute("UPDATE mediadores SET status='rejected' WHERE id=?", (mid,))
    con.commit(); con.close()
    return {"ok": True}
