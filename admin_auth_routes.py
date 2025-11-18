from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

ADMIN_EMAIL = "admin@mediazion.eu"
ADMIN_PASSWORD = "1234"  # luego lo movemos a variable de Render

router = APIRouter()

class AdminLogin(BaseModel):
    email: str
    password: str

@router.post("/admin/login")
def admin_login(body: AdminLogin):
    if body.email != ADMIN_EMAIL or body.password != ADMIN_PASSWORD:
        raise HTTPException(401, "Credenciales incorrectas")

    return {"ok": True, "token": "admin_ok"}
