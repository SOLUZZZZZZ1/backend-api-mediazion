# admin_routes.py — gestión de mediadores (listado + acciones)
import os
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Request
from sqlite3 import Row
from utils import db

admin_router = APIRouter()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "DEV_CHANGE_ME")  # ponlo en Render

def _require_admin(request: Request):
    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Authorization header")
    token = auth.split(" ", 1)[1].strip()
    if token != ADMIN_TOKEN:
        raise HTTPException(403, "Invalid admin token")

def _cols() -> List[str]:
    con = db(); cur = con.execute("PRAGMA table_info(mediadores)")
    cols = [r[1] for r in cur.fetchall()]; con.close()
    return cols

@admin_router.get("/mediadores")
def listar_mediadores(request: Request) -> List[Dict[str, Any]]:
    _require_admin(request)
    cols = _cols()
    con = db(); con.row_factory = Row
    vis = [c for c in ["id","name","email","status","created_at","provincia","especialidad","is_subscriber","is_trial","trial_expires_at"] if c in cols]
    rows = con.execute(f"SELECT {', '.join(vis)} FROM mediadores ORDER BY id DESC").fetchall()
    con.close()
    return [dict(r) for r in rows]

@admin_router.post("/mediadores/{mid}/status")
def set_status(mid: int, request: Request, value: str):
    _require_admin(request)
    if value not in ("pending","approved","rejected"):
        raise HTTPException(400, "value must be pending|approved|rejected")
    con = db()
    cur = con.execute("UPDATE mediadores SET status=? WHERE id=?", (value, mid))
    if cur.rowcount == 0:
        con.rollback(); raise HTTPException(404, "mediador not found")
    con.commit(); con.close()
    return {"ok": True}

@admin_router.post("/mediadores/{mid}/subscriber")
def set_subscriber(mid: int, request: Request, value: int):
    _require_admin(request)
    v = 1 if int(value) else 0
    con = db()
    cur = con.execute("UPDATE mediadores SET is_subscriber=? WHERE id=?", (v, mid))
    if cur.rowcount == 0:
        con.rollback(); raise HTTPException(404, "mediador not found")
    con.commit(); con.close()
    return {"ok": True, "is_subscriber": v}
