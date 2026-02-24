"""
download.py
-----------

Endpoint encargado de exponer el reporte final en formato PDF
generado por el pipeline de análisis de riesgo crediticio.

Responsabilidad:
- Validar que el job haya finalizado correctamente.
- Verificar existencia física del archivo en disco.
- Retornar FileResponse con headers adecuados para descarga forzada.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from api.services.job_manager import job_manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/download/{job_id}/pdf")
async def download_pdf(job_id: str):
    """
    Endpoint: GET /api/download/{job_id}/pdf

    Permite descargar el reporte técnico en PDF correspondiente
    al análisis de Altman + Merton.

    Requisitos:
    - El job debe estar en estado 'done'.
    - El archivo PDF debe existir en el directorio de salida.

    Responde con:
    - application/pdf
    - Content-Disposition: attachment
    """
    # Recuperar información del job desde el gestor centralizado
    job = job_manager.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' no encontrado.")

    if job.status != "done":
        raise HTTPException(
            status_code=409,
            detail=f"Análisis no completado. Estado: {job.status}",
        )

    # Extraer ruta del PDF previamente almacenada en el resultado del job
    pdf_path: Path | None = job.result.get("pdf_path") if job.result else None

    if pdf_path is None or not pdf_path.exists():
        raise HTTPException(
            status_code=404,
            detail="PDF no disponible. Puede que la conversión haya fallado.",
        )

    # Enviar archivo como descarga forzada al cliente
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"credit_report_{job_id[:8]}.pdf",
        headers={"Content-Disposition": f'attachment; filename="credit_report_{job_id[:8]}.pdf"'},
    )