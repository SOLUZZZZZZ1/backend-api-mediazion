# news_routes.py — Actualidad básica para Mediazion (puedes mejorar fuentes más tarde)
from fastapi import APIRouter

news_router = APIRouter()

@news_router.get("/news")
def list_news():
    """
    De momento devolvemos un listado estático. Más adelante puedes integrar BOE, Confilegal, etc.
    Lo importante ahora es que /api/news deje de dar 404.
    """
    items = [
        {
            "title": "Ejemplo de noticia",
            "summary": "Aquí aparecerá una noticia real cuando conectemos BOE/Confilegal.",
            "url": "https://www.boe.es/",
            "date": "2025-11-13",
            "source": "INTERNAS",
        }
    ]
    return {"ok": True, "items": items}
