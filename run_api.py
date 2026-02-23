"""
run_api.py
----------
Entry point para arrancar el servidor FastAPI.

Uso:
    python run_api.py

Equivalente a:
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

El flag --reload es útil en desarrollo: recarga el servidor al guardar cambios.
En producción quitar --reload y ajustar workers.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )