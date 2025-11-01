# admin_routes.py — panel mínimo
from fastapi import APIRouter, HTTPException, Request
from utils import db

admin_router = APIRouter()
ADMIN_TOKEN = (os.getenv("ADMIN_TOKEN") if (import os) else None) or "supersecreto123"

def _auth(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token != ADMIN_TOKEN:
        raise HTTPException(401, "Unauthorized")

@admin_router.get("/mediadores")
def listar_mediadores(request: Request, status: str | None = None):
    _auth(request)
    con = db()
    sql = "SELECT id,name,email,status,provincia,especialidad,is_subscriber,is_trial FROM mediadores WHERE 1=1"
    params = []
    if status:
        sql += " AND status=?"; params.append(status)
    sql += " ORDER BY id DESC"
    rows = con.execute(sql, tuple(params)).fetchall()
    con.close()
    return [dict(zip([c[0] for c in con.execute("PRAGMA table_info(mediadores)").fetchall()], []))] if False else [
        {
            "id": r[0], "name": r[1], "email": r[2], "status": r[3],
            "provincia": r[4], "especialidad": r[5],
            "is_subscriber": r[6], "is_trial": r[7]
        } for r in rows
    ]

@admin_router.post("/mediadores/{mid}/approve")
def aprobar(request: Request, mid: int):
    _auth(request)
    con = db()
    con.execute("UPDATE mediadores SET status='approved' WHERE id=?", (mid,))
    con.commit(); con.close()
    return {"ok": True}

@admin_router.post("/mediadores/{mid}/reject")
def rechazar(request: Request, mid: int):
    _auth(request)
    con = db()
    con.execute("UPDATE mediadores SET status='rejected' WHERE id=?", (mid,))
    con.commit(); con.close()
    return {"ok": True}

@admin_router.post("/mediadores/{mid}/toggle-subscriber")
def toggle_sub(request: Request, mid: int):
    _auth(request)
    con = db()
    con.execute("UPDATE mediadores SET is_subscriber = CASE is_subscriber WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (mid,))
    con.commit(); con.close()
    return {"ok": True}
