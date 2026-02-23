"""
download.py
-----------
Ruta para descargar el reporte en PDF.

    GET /api/download/{job_id}/pdf  → FileResponse del PDF generado
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
    Descarga el reporte PDF del análisis indicado.
    El job debe estar en estado 'done' y el PDF debe existir en disco.
    """
    job = job_manager.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' no encontrado.")

    if job.status != "done":
        raise HTTPException(
            status_code=409,
            detail=f"Análisis no completado. Estado: {job.status}",
        )

    pdf_path: Path | None = job.result.get("pdf_path") if job.result else None

    if pdf_path is None or not pdf_path.exists():
        raise HTTPException(
            status_code=404,
            detail="PDF no disponible. Puede que la conversión haya fallado.",
        )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"credit_report_{job_id[:8]}.pdf",
        headers={"Content-Disposition": f'attachment; filename="credit_report_{job_id[:8]}.pdf"'},
    )