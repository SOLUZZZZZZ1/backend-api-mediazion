# admin_routes.py — gestión de mediadores y panel admin (listado + acciones)
import os
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Request
from sqlite3 import Row
from utils import db

admin_router = APIRouter()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "DEV_CHANGE_ME")  # Pónlo en Render → Environment

def _require_admin(request: Request):
    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = auth.split(" ", 1)[1].strip()
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token")

def _mediadores_columns() -> List[str]:
    con = db()
    con.row_factory = None
    cur = con.execute("PRAGMA table_info(mediadores)")
    cols = [r[1] for r in cur.fetchall()]
    con.close()
    return cols

@admin_router.get("/mediadores")
def listar_mediadores(request: Request,
                      q: Optional[str] = None,
                      status: Optional[str] = None,
                      subscriber: Optional[int] = None) -> List[Dict[str, Any]]:
    _require_admin(request)
    cols = _mediadores_columns()
    con = db()
    con.row_factory = Row
    base_cols = ["id","name","email"]
    optional = ["status","created_at","telefono","bio","provincia","especialidad","web","linkedin","photo_url","cv_url","is_subscriber","subscription_status","is_trial","trial_expires_at"]
    select_cols = [c for c in base_cols if c in cols] + [c for c in optional if c in cols]
    if not select_cols:
        raise HTTPException(500, "Tabla 'mediadores' sin columnas detectables")
    sql = f"SELECT {', '.join(select_cols)} FROM mediadores WHERE 1=1"
    params: List[Any] = []
    if q:
        if "name" in cols or "email" in cols or "bio" in cols:
            sql += " AND ("
            parts = []
            if "name" in cols: parts.append("name LIKE ?")
            if "email" in cols: parts.append("email LIKE ?")
            if "bio" in cols:   parts.append("bio LIKE ?")
            sql += " OR ".join(parts) + ")"
            w = f"%{q}%"
            for _ in range(len(parts)): params.append(w)
    if status and "status" in cols:
        sql += " AND status = ?"
        params.append(status)
    if subscriber is not None and "is_multiplier" in cols:
        # fallback si usaste otro nombre
        pass
    if subscriber is not None and "is_subscriber" in cols:
        sql += " AND COALESCE(is_subscriber,0) = ?"
        params.append(int(bool(int(subscriber))))
    sql += " ORDER BY id DESC"
    rows = con.execute(sql, params).fetchall()
    con.close()
    return [dict(r) for r in rows]

@admin_router.post("/mediadores/{mid}/status")
def set_status(mid: int, request: Request, value: str):
    _require_admin(request)
    if value not in ("pending","approved","rejected"):
        raise HTTPException(400, "value must be one of: pending|approved|rejected")
    cols = _mediadores_columns()
    if "status" not in cols:
        raise Exception("Column 'status' not found in mediadores")
    con = db()
    cur = con.execute("UPDATE mediadores SET status=? WHERE id=?", (value, mid))
    if cur.rowcount == 0:
        con.rollback()
        raise HTTPException(404, "mediador not found")
    con.commit(); con.close()
    return {"ok": True, "id": mid, "status": value}

@admin_router.post("/mediadores/{mid}/subscriber")
def set_subscriber(mid: int, request: Request, value: int):
    _require_admin(request)
    v = 1 if int(value) else 0
    cols = _mediadores_columns()
    con = db()
    cur = con.cursor()
    if "is_subscriber" not in cols:
        # agrega columna si no existe
        cur.execute("ALTER TABLE mediadores ADD COLUMN is_subscriber INTEGER DEFAULT 0")
        con.commit()
    cur.execute("UPDATE mediadores SET is_subscriber=? WHERE id=?", (v, mid))
    if cur.rowcount == 0:
        con.rollback()
        raise HTTPException(404, "mediador not found")
    con.commit(); con.close()
    return {"ok": True, "id": mid, "is_subscriber": v}
