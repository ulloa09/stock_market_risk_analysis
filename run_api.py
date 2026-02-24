"""
run_api.py
----------
Punto de entrada para ejecutar el servidor FastAPI del sistema
"Stock Market Risk Analysis".

Este script encapsula la ejecución de Uvicorn para facilitar:
    - Arranque rápido en entorno de desarrollo.
    - Configuración controlada de host, puerto y recarga automática.

Equivalente en línea de comandos:
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

Notas operativas:
    - reload=True activa auto-recarga ante cambios en código.
    - En producción se recomienda:
        * Desactivar reload.
        * Configurar múltiples workers.
        * Ejecutar detrás de un reverse proxy (ej. Nginx).
"""

import uvicorn

if __name__ == "__main__":
    # Ejecución directa mediante Uvicorn (servidor ASGI).
    uvicorn.run(
        # Ruta de importación del objeto FastAPI (formato: modulo:instancia).
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        # Auto-recarga activa solo en entorno de desarrollo.
        reload=True,
        # Directorios monitoreados para detectar cambios de código.
        reload_dirs=["api"],
        log_level="info",
    )