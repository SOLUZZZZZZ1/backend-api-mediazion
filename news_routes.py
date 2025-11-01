# news_routes.py — stub estable para evitar 404 de fuentes
from fastapi import APIRouter, Query

news_router = APIRouter()

@news_router.get("/news")
def news(limit: int = Query(50, ge=1, le=200), source: str | None = None, tag: str | None = None, q: str | None = None):
    # Devuelve lista simulada si las fuentes fallan
    return [
        {
            "title": "Actualidad de mediación",
            "summary": "Notas y resoluciones recientes de tribunales y medios jurídicos.",
            "url": "https://mediazion.eu/actualidad",
            "date": "2025-10-27",
            "source": "MEDIAZION",
            "tags": ["civil","jurisprudencia"]
        }
    ][:limit]
