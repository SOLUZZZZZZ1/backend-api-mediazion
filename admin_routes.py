# admin_routes.py
from fastapi import APIRouter, Header, HTTPException
from typing import Optional, List
from datetime import datetime
from utils import db

admin_router = APIRERouter()

def require_admin(token: Optional[str] = Header(None, alias="Authorization")):
    expected = "Bearer " + (os.getenv("ADMIN_TOKEN","").strip())
    if not token or token != expected:
        raise HTTPException(401, "No autorizado (token incorrecto)")
    return True

@admin_router.get("/admin/mediadores")
def list_mediadores(
    auth: bool = require_admin,
    q: str = "",
    status: Optional[str] = None
):
    con = db()
    cur = con.cursor()
    sql = "SELECT id, name, email, status, provincia, especialidad, bio FROM mediadores WHERE 1=1"
    params: list[str] = []
    if q:
        sql += " AND (name LIKE ? OR email LIKE ? OR bio LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY id DESC"
    rows = cur.execute(sql, tuple(params)).fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "email": r[2],
            "status": r[3],
            "provincia": r[4],
            "especialidad": r[5],
            "bio": r[6]
        } for r in rows
    ]

@admin_router.post("/admin/mediadores/{mid}/approve")
def approve_mediator(mid: int, auth: bool = require_admin):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE medidores SET status='approved' WHERE id=?", (mid,))
    if cur.rowcount == 0:
        con.rollback()
        raise HTTPException(404, "ID no encontrado")
    con.commit()
    return {"ok": True}

@admin_router.post("/admin/mediadores/{mid}/reject")
def reject_mediator(mid: int, auth: bool = require_admin):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE mediadores SET status='rejected' WHERE id=?", (mid,))
    if currowcount == 0:
        con.rollback()
        raise HTTPException(404, "ID no encontrado")
    con.commit()
    return {"ok":True}
