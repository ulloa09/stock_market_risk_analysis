"""
api/main.py
-----------

Punto de entrada de la aplicación FastAPI.

Responsabilidades principales:
    - Inicializar la aplicación.
    - Configurar middlewares (CORS).
    - Registrar routers de análisis y descarga.
    - Exponer archivos estáticos y frontend.
    - Centralizar configuración de metadatos OpenAPI.

Este módulo no contiene lógica financiera.
Actúa únicamente como capa de orquestación HTTP.
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
# Inicialización de la aplicación con metadatos visibles en Swagger/OpenAPI
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Credit Risk Analysis API",
    description="API para evaluación crediticia con modelos Altman Z-score y Merton.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configuración de CORS
# ---------------------
# Permite que clientes web (ej. frontend en localhost o dominio externo)
# puedan consumir la API sin restricciones del navegador.
# En entorno productivo se recomienda restringir allow_origins.

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # En producción restringir a dominio específico
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registro de routers
# --------------------
# Se separan responsabilidades por dominio:
# - Analysis  → ejecución del pipeline cuantitativo
# - Download  → descarga de reportes generados

app.include_router(analyze_router,  prefix="/api", tags=["Analysis"])
app.include_router(download_router, prefix="/api", tags=["Download"])

# Directorio de salida
# ---------------------
# Se expone la carpeta "outputs" para permitir acceso HTTP
# a gráficos o archivos generados dinámicamente.

_outputs_dir = Path("outputs")
_outputs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(_outputs_dir)), name="outputs")

# Servicio del frontend
# ----------------------
# Si existe ui/index.html, se sirve como aplicación SPA.
# Esto permite desplegar backend + frontend en un mismo servidor.

_ui_dir = Path("ui")

@app.get("/", include_in_schema=False)
async def serve_ui():
    """
    Endpoint raíz (GET /).

    Retorna el archivo index.html del frontend si está disponible.
    En caso contrario, informa error de configuración.
    """
    index = _ui_dir / "index.html"
    if not index.exists():
        return {"error": "UI no encontrada. Verifica que ui/index.html existe."}
    return FileResponse(str(index))