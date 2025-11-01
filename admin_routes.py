# admin_routes.py — versión corregida y segura
import os
from fastapi import APIRouter, Header, HTTPException

admin_router = APIRouter(prefix="/admin")

# Token admin desde env (fallback seguro)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN") or "supersecreto123"

def check_admin(token: str | None):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

@admin_router.get("/health")
def health(x_admin_token: str | None = Header(None)):
    # salud simple: si no viene token devuelve 401, si viene y correcto devuelve ok
    if x_admin_token is None:
        raise HTTPException(status_code=401, detail="Missing token")
    check_admin(x_admin_token)
    return {"ok": True}

# Endpoints de administración sencillos (stubs — conectarlos a BD)
@admin_router.post("/approve/{mediador_id}")
def approve_mediador(mediador_id: str, x_admin_token: str | None = Header(None)):
    check_admin(x_admin_token)
    # TODO: actualizar en BD: approved = True
    return {"ok": True, "id": mediador_id, "action": "approved"}

@admin_router.post("/disable/{mediador_id}")
def disable_mediador(mediador_id: str, x_admin_token: str | None = Header(None)):
    check_admin(x_admin_token)
    # TODO: actualizar en BD: approved = False / status = disabled
    return {"ok": True, "id": mediador_id, "action": "disabled"}
