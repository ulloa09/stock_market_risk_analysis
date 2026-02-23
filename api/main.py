"""
api/main.py
-----------
Aplicación FastAPI principal.

Responsabilidades:
    - Crear la instancia de FastAPI
    - Registrar los routers
    - Configurar CORS
    - Servir la UI estática en GET /
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes.analyze import router as analyze_router
from api.routes.download import router as download_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Credit Risk Analysis API",
    description="API para evaluación crediticia con modelos Altman Z-score y Merton.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS — permite que el frontend (mismo origen o localhost) consuma la API
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # En producción restringir a dominio específico
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(analyze_router,  prefix="/api", tags=["Analysis"])
app.include_router(download_router, prefix="/api", tags=["Download"])

# ---------------------------------------------------------------------------
# Archivos estáticos de outputs (plots accesibles por URL si se necesita)
# ---------------------------------------------------------------------------

_outputs_dir = Path("outputs")
_outputs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(_outputs_dir)), name="outputs")

# ---------------------------------------------------------------------------
# Servir la UI
# ---------------------------------------------------------------------------

_ui_dir = Path("ui")

@app.get("/", include_in_schema=False)
async def serve_ui():
    """Sirve el frontend single-page."""
    index = _ui_dir / "index.html"
    if not index.exists():
        return {"error": "UI no encontrada. Verifica que ui/index.html existe."}
    return FileResponse(str(index))