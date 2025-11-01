# admin_routes.py — Rutas administrativas MEDIAZION (alineado con app.py que usa prefix="/admin")
import os
from fastapi import APIRouter, Header, HTTPException, status

# OJO: aquí NO ponemos prefix="/admin" porque ya se aplica en app.py
admin_router = APIRouter(tags=["admin"])

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or "cambia-este-token-en-produccion"

def _require(token_from_header: str | None):
    if not token_from_header or token_from_header != ADMIN_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")

@admin_router.get("/health")
def admin_health(x_admin_token: str | None = Header(default=None)):
    """Comprobación de salud del área admin. Usa cabecera x-admin-token."""
    _require(x_admin_token)
    return {"ok": True, "scope": "admin"}

@admin_router.post("/approve/{mediador_id}")
def approve_mediador(mediador_id: int, x_admin_token: str | None = Header(default=None)):
    """Stub para aprobar un mediador (extiende con tu lógica de BD)."""
    _require(x_admin_token)
    return {"ok": True, "approved_id": mediador_id}

@admin_router.post("/revoke/{mediador_id}")
def revoke_mediador(mediador_id: int, x_admin_token: str | None = Header(default=None)):
    """Stub para revocar un mediador (extiende con tu lógica de BD)."""
    _require(x_admin_token)
    return {"ok": True, "revoked_id": mediador_id}
