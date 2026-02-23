"""
schemas.py
----------
Modelos Pydantic que definen el contrato de entrada/salida de la API.

Regla: el frontend solo conoce estos schemas. Nada de tipos internos
del pipeline (CompanyEvaluation, ModelResult, etc.) sale crudo a la UI.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    """Payload del POST /api/analyze"""
    tickers: list[str]
    force_refresh: bool = False

    @field_validator("tickers")
    @classmethod
    def validate_tickers(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("Debes enviar al menos un ticker.")
        if len(v) > 20:
            raise ValueError("Máximo 20 tickers por análisis.")
        cleaned = [t.strip().upper() for t in v if t.strip()]
        if not cleaned:
            raise ValueError("Ningún ticker válido recibido.")
        return cleaned


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class JobCreatedResponse(BaseModel):
    """Respuesta del POST /api/analyze"""
    job_id: str
    message: str = "Análisis iniciado."


class JobStatusResponse(BaseModel):
    """Respuesta del GET /api/status/{job_id}"""
    job_id: str
    status: str        # queued | running | done | error
    progress: str
    error: Optional[str] = None


class TickerRow(BaseModel):
    """Una fila de la tabla comparativa de resultados."""
    ticker: str
    company_name: str
    sector: str
    zscore: Optional[float]
    zscore_zone: str
    altman_decision: str
    distance_to_default: Optional[float]
    probability_of_default: Optional[float]
    merton_decision: str
    consolidated_decision: str
    consolidated_reasoning: str


class DataWarning(BaseModel):
    """Advertencia de datos para un ticker específico."""
    ticker: str
    issues: list[str]


class ResultsResponse(BaseModel):
    """Respuesta del GET /api/results/{job_id}"""
    job_id: str
    tickers_analyzed: list[str]
    table: list[TickerRow]
    # Gráficos como PNG en base64 — el frontend los renderiza con <img src="data:...">
    plots: dict[str, str]   # {"zscore_comparison": "data:image/png;base64,...", ...}
    # Advertencias por ticker: datos faltantes, cálculos parciales, etc.
    data_warnings: list[DataWarning] = []