"""
schemas.py
----------

Definición de los modelos de datos (schemas) utilizados por la API
mediante Pydantic.

Este módulo establece el contrato formal de comunicación entre:
    - Backend (pipeline cuantitativo Altman + Merton)
    - Frontend (UI)

Principios:
-----------
- Aislamiento de modelos internos del dominio (CompanyEvaluation, etc.).
- Validación estricta de entrada.
- Serialización segura de salida.
- Tipado explícito para documentación automática (OpenAPI).

Nota:
Estos modelos representan únicamente estructuras de transporte (DTOs),
no contienen lógica financiera.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    """
    Modelo de entrada para POST /api/analyze.

    Atributos:
    ----------
    tickers : list[str]
        Lista de símbolos bursátiles a analizar.
    force_refresh : bool
        Si es True, ignora caché y fuerza nueva descarga de datos.

    Validaciones:
    -------------
    - Al menos un ticker.
    - Máximo 20 tickers por ejecución (control de carga).
    - Normalización a mayúsculas y eliminación de espacios.
    """
    tickers: list[str]
    force_refresh: bool = False

    # Validador personalizado para garantizar integridad y normalización del input
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
    """
    Respuesta inmediata tras crear un job asíncrono.

    Se retorna antes de ejecutar el pipeline completo,
    permitiendo al frontend iniciar polling por estado.
    """
    job_id: str
    message: str = "Análisis iniciado."


class JobStatusResponse(BaseModel):
    """
    Modelo de respuesta para monitoreo de estado del job.

    status:
        - queued
        - running
        - done
        - error

    progress:
        Mensaje descriptivo del paso actual del pipeline.
    """
    job_id: str
    status: str        # queued | running | done | error
    progress: str
    error: Optional[str] = None


class TickerRow(BaseModel):
    """
    Representa una fila consolidada de resultados por ticker.

    Contiene métricas derivadas de:
        - Modelo Z-Score de Altman
        - Modelo estructural de Merton (basado en Black-Scholes)

    Todos los valores numéricos pueden ser None si el cálculo
    no pudo realizarse por falta de datos.
    """
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
    """
    Advertencias asociadas a problemas de datos o cálculos parciales.

    Ejemplos:
        - Estados financieros incompletos.
        - Volatilidad no estimable.
        - Deuda no disponible.
    """
    ticker: str
    issues: list[str]


class ResultsResponse(BaseModel):
    """
    Respuesta final consolidada del análisis crediticio.

    Incluye:
    - Lista de tickers analizados.
    - Tabla estructurada de resultados.
    - Gráficos codificados en base64 (PNG).
    - Advertencias de calidad de datos.

    Este modelo es consumido directamente por la UI.
    """
    job_id: str
    tickers_analyzed: list[str]
    table: list[TickerRow]
    # Gráficos como PNG en base64 — el frontend los renderiza con <img src="data:...">
    plots: dict[str, str]   # {"zscore_comparison": "data:image/png;base64,...", ...}
    # Advertencias por ticker: datos faltantes, cálculos parciales, etc.
    data_warnings: list[DataWarning] = []