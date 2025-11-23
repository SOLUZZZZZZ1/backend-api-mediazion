# instituciones_routes.py — Endpoints públicos para instituciones
from fastapi import APIRouter, HTTPException
from db import pg_conn

instituciones_router = APIRouter(prefix="/api/instituciones", tags=["instituciones"])

@instituciones_router.post("/registro")
def registro_institucion(body: dict):
    """
    Recibe el formulario de registro institucional y lo guarda en instituciones_registro.
    """
    campos_oblig = ["tipo", "institucion", "cargo", "nombre", "email"]
    for c in campos_oblig:
        if not body.get(c):
            raise HTTPException(400, f"Falta el campo obligatorio: {c}")

    try:
        with pg_conn() as cx, cx.cursor() as cur:
            cur.execute("""
                INSERT INTO instituciones_registro
                (tipo, institucion, cargo, nombre, email, telefono, provincia, comentarios)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                body.get("tipo"),
                body.get("institucion"),
                body.get("cargo"),
                body.get("nombre"),
                body.get("email"),
                body.get("telefono"),
                body.get("provincia"),
                body.get("comentarios"),
            ))
            cx.commit()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, f"Error registrando institución: {e}")
