"""API do PokerLab — expõe o backend Python (poker_coach/) pro frontend
React (pokerlab-ai-coach/) via HTTP/JSON.

Rodar:
    cd poker_coach && .venv/bin/uvicorn api.main:app --reload --port 8000

Docs interativas (Swagger, testa direto no navegador): http://localhost:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import favorites, hands, icm, imports, pushfold, replayer, tags

app = FastAPI(
    title="PokerLab API",
    description="Backend do PokerLab — Push/Fold (Nash), ICM (Malmuth-Harville), "
                 "Replayer, hand history, tags e favoritos.",
    version="0.1.0",
)

# CORS permissivo — uso local/dev (Vite/TanStack Start rodando em porta
# variável). Restringir origem antes de qualquer deploy público.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pushfold.router)
app.include_router(icm.router)
app.include_router(replayer.router)
app.include_router(hands.router)
app.include_router(tags.router)
app.include_router(favorites.router)
app.include_router(imports.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
