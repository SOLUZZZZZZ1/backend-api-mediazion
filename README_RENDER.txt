Start: uvicorn app:app --host 0.0.0.0 --port 10000
Env: ALLOWED_ORIGINS, NEWS_CACHE_TTL
Endpoints: /news, /tasks/news-refresh, /health
