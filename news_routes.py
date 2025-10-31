# news_routes.py — stub simple (fuentes pueden fallar 404)
from fastapi import APIRouter

news_router = APIRouter()

@news_router.get("/news")
def news():
    # Deja algo estable para no romper si el feed externa cae
    return {"items": []}
