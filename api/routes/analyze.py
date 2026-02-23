"""
analyze.py
----------
Rutas principales del pipeline:

    POST /api/analyze            → lanza el análisis en background, retorna job_id
    GET  /api/status/{job_id}    → estado del job (polling desde el frontend)
    GET  /api/results/{job_id}   → resultados completos cuando status == "done"
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.schemas import (
    AnalyzeRequest,
    DataWarning,
    JobCreatedResponse,
    JobStatusResponse,
    ResultsResponse,
    TickerRow,
)
from api.services.job_manager import job_manager
from api.services.pdf_converter import convert_md_to_pdf

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# POST /api/analyze
# ---------------------------------------------------------------------------

@router.post("/analyze", response_model=JobCreatedResponse, status_code=202)
async def start_analysis(payload: AnalyzeRequest, background_tasks: BackgroundTasks):
    """
    Recibe la lista de tickers y lanza el pipeline en background.
    Retorna inmediatamente con el job_id para que el frontend empiece polling.
    """
    job = job_manager.create_job()
    background_tasks.add_task(
        _run_pipeline_task,
        job_id=job.job_id,
        tickers=payload.tickers,
        force_refresh=payload.force_refresh,
        output_dir=str(job.output_dir),
    )
    return JobCreatedResponse(job_id=job.job_id)


# ---------------------------------------------------------------------------
# GET /api/status/{job_id}
# ---------------------------------------------------------------------------

@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_status(job_id: str):
    """Retorna el estado actual del job. El frontend hace polling cada 2s."""
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' no encontrado.")
    return JobStatusResponse(**job.to_status_dict())


# ---------------------------------------------------------------------------
# GET /api/results/{job_id}
# ---------------------------------------------------------------------------

@router.get("/results/{job_id}", response_model=ResultsResponse)
async def get_results(job_id: str):
    """
    Retorna los resultados completos del análisis.
    Solo disponible cuando status == "done".
    """
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' no encontrado.")
    if job.status != "done":
        raise HTTPException(
            status_code=409,
            detail=f"Job aún no completado. Estado actual: {job.status}",
        )

    result = job.result
    evaluations = result["evaluations"]
    summary_df  = result["summary_df"]
    plot_paths  = result["plot_paths"]

    # Construir tabla de resultados
    import math

    def _clean_float(val) -> float | None:
        """Convierte nan/inf a None para que JSON no explote."""
        if val is None:
            return None
        try:
            f = float(val)
            return None if (math.isnan(f) or math.isinf(f)) else f
        except (TypeError, ValueError):
            return None

    table_rows = []
    data_warnings = []   # tickers con problemas de datos

    for _, row in summary_df.iterrows():
        ticker = row["Ticker"]
        ev     = evaluations.get(ticker)
        ar     = ev.altman_result if ev else None
        mr     = ev.merton_result if ev else None

        # Detectar tickers con errores de datos y reportarlos
        if ev:
            issues = []
            if ar and not ar.is_calculable():
                issues.append(f"Altman: {ar.error}")
            if mr and not mr.is_calculable():
                issues.append(f"Merton: {mr.error}")
            if ar and ar.warnings:
                issues.extend([f"Altman ⚠ {w}" for w in ar.warnings])
            if mr and mr.warnings:
                issues.extend([f"Merton ⚠ {w}" for w in mr.warnings])
            if issues:
                data_warnings.append({"ticker": ticker, "issues": issues})

        table_rows.append(TickerRow(
            ticker=ticker,
            company_name=row.get("Empresa", ticker),
            sector=row.get("Sector", "—"),
            zscore=_clean_float(row.get("Z-score")),
            zscore_zone=(ar.risk_zone if ar and ar.is_calculable() else None) or "—",
            altman_decision=row.get("Decisión Altman") or "INCALCULABLE",
            distance_to_default=_clean_float(row.get("DD (Merton)")),
            probability_of_default=_clean_float(row.get("PD (Merton)")),
            merton_decision=row.get("Decisión Merton") or "INCALCULABLE",
            consolidated_decision=row.get("Decisión Consolidada") or "INCALCULABLE",
            consolidated_reasoning=ev.consolidated_reasoning if ev else "—",
        ))

    # Convertir plots a base64
    plots_b64 = {}
    for key, path in plot_paths.items():
        if isinstance(path, Path) and path.exists():
            b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
            plots_b64[key] = f"data:image/png;base64,{b64}"

    return ResultsResponse(
        job_id=job_id,
        tickers_analyzed=list(evaluations.keys()),
        table=table_rows,
        plots=plots_b64,
        data_warnings=data_warnings,
    )


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

def _run_pipeline_task(
    job_id: str,
    tickers: list[str],
    force_refresh: bool,
    output_dir: str,
) -> None:
    """
    Ejecuta el pipeline completo en un thread de background.
    Actualiza el estado del job en cada paso.
    """
    try:
        from main import run_pipeline

        job_manager.set_running(job_id, "Descargando datos financieros...")
        logger.info(f"[{job_id}] Iniciando pipeline para: {tickers}")

        # Paso 1-3: pipeline principal
        job_manager.set_progress(job_id, "Ejecutando modelos Altman y Merton...")
        result = run_pipeline(
            tickers=tickers,
            force_refresh=force_refresh,
            output_dir=output_dir,
        )

        # Paso extra: generar PDF a partir del MD
        job_manager.set_progress(job_id, "Generando PDF del reporte...")
        md_path  = result["report_path"]
        pdf_path = md_path.with_suffix(".pdf")
        try:
            convert_md_to_pdf(md_path=md_path, pdf_path=pdf_path)
            result["pdf_path"] = pdf_path
        except Exception as pdf_err:
            logger.warning(f"[{job_id}] PDF no generado: {pdf_err}")
            result["pdf_path"] = None

        job_manager.set_done(job_id, result)
        logger.info(f"[{job_id}] Pipeline completado.")

    except Exception as e:
        logger.exception(f"[{job_id}] Error en pipeline: {e}")
        job_manager.set_error(job_id, str(e))