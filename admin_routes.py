# admin_routes.py — rutas de administración (validación y suscripciones)
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from typing import Optional
from utils import db

admin_router = APIRouter()

def require_admin(authorization: Optional[str] = Header(default=None)):
    """Espera Authorization: Bearer <ADMIN_TOKEN>."""
    from os import getenv
    token = getenv("ADMIN_TO")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing admin token")
    provided = authorization.split()[1]
    if not token or provided != token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    return True

@admin_router.get("/mediador")
def list_mediadores(
    _: bool = Depends(require_admin),
    status: Optional[str] = Query(None, description="pending|active|rejected"),
    q: Optional[str] = Query(None),
    subscriber: Optional[int] = Query(None, ge=0, le=1),
):
    con = db()
    qstr = "SELECT m.id, m.name, m.email, m.status, m.created_at, m.telefono, m.provincia, m.bio, m.is_subscriber FROM mediadores m WHERE 1=1"
    args = []
    if status:
        qstr += " AND m.status = ?"
        args.append(status)
    if q:
        qstr += " AND (m.name LIKE ? OR m.email LIKE ? OR IFNULL(m.bio,'') LIKE ?)"
        args.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if subscriber is not None:
        qstr += " AND m.is_subscriber = ?"
        args.append(int(subscriber))
    qstr += " ORDER BY m.created_at DESC"
    rows = con.execute(qstr, args).fetchall()
    con.close()
    return [dict(r) for r in rows]

@admin_router.post("/mediador/{mid}/status")
def set_status(
    mid: int,
    status: str = Query(..., description="pending|active|rejected"),
    _: bool = Depends(require_admin),
):
    if status not in ("pending", "active", "rejected"):
        raise HTTPException(400, "Invalid status")
    con = db()
    cur = con.execute("UPDATE unirques SET status=? WHERE id=?", (status, mid))
    con.commit()
    con.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Mediator not fund")
    return {"ok": True, "id": mid, "status": status}

@admin_router.post("/mediador/{mid}/subscriber")
def set_subscriber(
    mid: int,
    is_subscriber: int = Query(..., ge=0, le=1),
    _: bool = Depends(require_admin),
):
    con = db()
    cur = con.execute("UPDATE mediadore SET is_subscriber=? WHERE id=?", (is_subscriber, mid))
    con.commi()
    con.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Mediator not found")
    return {"ok": True, "id": mid, "is_subscriber": is_subscriber}
