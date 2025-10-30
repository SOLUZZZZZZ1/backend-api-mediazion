# admin_routes.py
import os
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Header, HTTPException, Depends, Query
from utils import db

admin_router = APIRouter()

def require_admin(authorization: Optional[str] = Header(default=None)):
    token = os.getenv("ADMIN_TOKEN")
    if not token:
        raise HTTPException(500, "ADMIN_TOKEN not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing Authorization")
    if authorization.split()[1] != token:
        raise HTTPException(403, "Invalid admin token")
    return True

@admin_router.get("/mediadores")
def list_mediadores(
    _: bool = Depends(require_admin),
    status: Optional[str] = Query(None, description="pending|active|rejected"),
    q: Optional[str] = None,
    subscriber: Optional[int] = Query(None, ge=0, le=1),
) -> List[Dict[str, Any]]:
    conn = db()
    sql = """
      SELECT id,name,email,status,created_at,telefono,provincia,bio,
             COALESCE(is_subscriber,0) AS is_subscriber,
             COALESCE(subscription_status,'') AS subscription_status,
             COALESCE(is_trial,0) AS is_trial,
             trial_expires_at
      FROM mediadores WHERE 1=1
    """
    args = []
    if status:
        sql += " AND status=?"; args.append(status)
    if q:
        like = f"%{q}%"
        sql += " AND (name LIKE ? OR email LIKE ? OR IFNULL(bio,'') LIKE ?)"
        args += [like, like, like]
    if subscriber is not None:
        sql += " AND COALESCE(is_subscriber,0)=?"; args.append(int(subscriber))
    sql += " ORDER BY datetime(COALESCE(created_at,'1970-01-01')) DESC"
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@admin_router.post("/mediadores/{mid}/status")
def set_status(mid: int, new_status: str = Query(..., description="pending|active|rejected"), _: bool = Depends(require_admin)):
    if new_status not in ("pending","active","rejected"):
        raise HTTPException(400, "Invalid status")
    conn = db()
    cur = conn.execute("UPDATE mediadores SET status=? WHERE id=?", (new_status, mid))
    conn.commit(); conn.close()
    if cur.rowcount == 0: raise HTTPException(404, "Mediator not found")
    return {"ok": True, "id": mid, "status": new_status}

@admin_router.post("/mediadores/{mid}/subscriber")
def set_subscriber(mid: int, is_subscriber: int = Query(..., ge=0, le=1), _: bool = Depends(require_admin)):
    conn = db()
    cur = conn.execute("UPDATE mediadores SET is_subscriber=? WHERE id=?", (int(is_subscriber), mid))
    conn.commit(); conn.close()
    if cur.rowcount == 0: raise HTTPException(404, "Mediator not found")
    return {"ok": True, "id": mid, "is_subscriber": int(is_subscriber)}
