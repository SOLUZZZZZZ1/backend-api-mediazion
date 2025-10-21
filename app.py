from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="MEDIAZION Backend (minimal)", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True, "service": "mediazion-backend"}

@app.post("/contact")
async def contact(req: Request):
    data = await req.json()
    return {"ok": True, "received": data}
