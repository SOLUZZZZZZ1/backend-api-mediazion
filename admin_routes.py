# admin_routes.py
import os
from fastapi import APIRouter, Header, HTTPException, status

admin_router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or "cambia-este-token-en-produccion"

def _require(token_from_header: str | None):
    if not token_from_header or token_from_header != ADMIN_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")

@admin_router.get("/health")
def admin_health(x_admin_token: str | None = Header(default=None)):
    _require(x_admin_token)
    return {"ok": True}
