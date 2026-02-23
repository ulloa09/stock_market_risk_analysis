"""
credit_evaluator.py
-------------------
Responsabilidad única: ejecutar ambos modelos (Altman y Merton) sobre
un conjunto de empresas y consolidar los resultados en una estructura
uniforme lista para reporte y visualización.

Este módulo no contiene lógica de modelos ni de descarga de datos.
Orquesta — recibe datos ya descargados y modelos ya instanciados.

Introducción al evaluador:
    El evaluador crediticio aplica dos marcos analíticos complementarios
    a cada empresa: el Z-score de Altman (modelo contable-discriminante)
    y el modelo de Merton (modelo estructural de opciones). La combinación
    de ambos permite triangular la decisión: una empresa puede pasar el
    filtro contable de Altman pero mostrar alta PD en Merton si su
    volatilidad de activos es elevada, o viceversa.

    La decisión final consolidada requiere que AMBOS modelos aprueben
    para emitir "APROBAR". Si alguno rechaza, la decisión consolidada
    es conservadora.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from models.base_model import CreditModel, ModelResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Contenedor de resultado por empresa
# ---------------------------------------------------------------------------

@dataclass
class CompanyEvaluation:
    """
    Resultado completo de la evaluación crediticia de una empresa.
    Contiene los resultados individuales de cada modelo y la decisión consolidada.
    """
    ticker: str
    company_name: str
    sector: str
    industry: str

    # Resultados por modelo
    altman_result: Optional[ModelResult] = None
    merton_result: Optional[ModelResult] = None

    # Decisión consolidada (lógica conservadora: ambos deben aprobar)
    consolidated_decision: str = "INCALCULABLE"
    consolidated_reasoning: str = ""

    def is_fully_calculable(self) -> bool:
        """True si ambos modelos pudieron calcularse."""
        return (
            self.altman_result is not None and self.altman_result.is_calculable()
            and self.merton_result is not None and self.merton_result.is_calculable()
        )

    def to_summary_dict(self) -> dict:
        """
        Retorna un diccionario plano para construir el DataFrame
        de resumen comparativo.
        """
        return {
            "Ticker":               self.ticker,
            "Empresa":              self.company_name,
            "Sector":               self.sector,
            "Modelo Z-score":       self.altman_result.model_name if self.altman_result else "N/A",
            "Z-score":              self.altman_result.score if self.altman_result else None,
            "Zona Z-score":         self.altman_result.risk_zone if self.altman_result else "N/A",
            "Decisión Z-score":     self.altman_result.credit_decision if self.altman_result else "INCALCULABLE",
            "DD (Merton)":          self.merton_result.score if self.merton_result else None,
            "PD (Merton)":          self.merton_result.probability_of_default if self.merton_result else None,
            "Decisión Merton":      self.merton_result.credit_decision if self.merton_result else "INCALCULABLE",
            "Decisión Consolidada": self.consolidated_decision,
            "Razonamiento":         self.consolidated_reasoning,
        }


# ---------------------------------------------------------------------------
# Evaluador principal
# ---------------------------------------------------------------------------

class CreditEvaluator:
    """
    Ejecuta los modelos de crédito sobre múltiples empresas y consolida
    los resultados.

    Uso:
        evaluator = CreditEvaluator(altman_model, merton_model)
        evaluations = evaluator.evaluate_all(companies_dict)
        summary_df  = evaluator.summary_dataframe(evaluations)
    """

    def __init__(self, altman_model: CreditModel, merton_model: CreditModel):
        self._altman = altman_model
        self._merton = merton_model

    # ------------------------------------------------------------------
    # Público
    # ------------------------------------------------------------------

    def evaluate(self, company) -> CompanyEvaluation:
        """
        Evalúa una empresa con ambos modelos.

        Introduce el proceso:
            1. Ejecuta Altman Z-score (versión auto-seleccionada por sector)
            2. Ejecuta Merton para obtener DD y PD
            3. Consolida ambas decisiones con lógica conservadora
            4. Registra advertencias de datos insuficientes

        Retorna:
            CompanyEvaluation con resultados de ambos modelos y decisión final.
        """
        ticker = company.ticker
        logger.info(f"[{ticker}] Evaluando con Altman y Merton.")

        altman_result = self._altman.safe_calculate(company)
        merton_result = self._merton.safe_calculate(company)

        evaluation = CompanyEvaluation(
            ticker=ticker,
            company_name=company.company_name,
            sector=company.sector,
            industry=company.industry,
            altman_result=altman_result,
            merton_result=merton_result,
        )

        evaluation.consolidated_decision, evaluation.consolidated_reasoning = (
            self._consolidate(altman_result, merton_result)
        )

        self._log_result(evaluation)
        return evaluation

    def evaluate_all(
        self, companies: dict
    ) -> dict[str, CompanyEvaluation]:
        """
        Evalúa un diccionario de empresas {ticker: CompanyFinancials}.

        Conclusión del métoodo:
            Procesa cada empresa de forma independiente. Si una empresa
            no tiene datos suficientes para algún modelo, ese modelo
            retorna INCALCULABLE sin interrumpir la evaluación de las demás.

        Retorna:
            {ticker: CompanyEvaluation}
        """
        results = {}
        for ticker, company in companies.items():
            if not company.is_valid():
                logger.warning(f"[{ticker}] Datos insuficientes — omitiendo evaluación.")
                results[ticker] = CompanyEvaluation(
                    ticker=ticker,
                    company_name=company.company_name,
                    sector=company.sector,
                    industry=company.industry,
                    consolidated_decision="INCALCULABLE",
                    consolidated_reasoning="Datos financieros insuficientes para modelar.",
                )
                continue
            results[ticker] = self.evaluate(company)
        return results

    def summary_dataframe(
        self, evaluations: dict[str, CompanyEvaluation]
    ) -> pd.DataFrame:
        """
        Construye un DataFrame comparativo con una fila por empresa.
        Útil para visualización y reporte.
        """
        rows = [ev.to_summary_dict() for ev in evaluations.values()]
        df = pd.DataFrame(rows)

        # Ordenar: primero APROBAR, luego ZONA GRIS, luego RECHAZAR
        order = {"APROBAR": 0, "ZONA GRIS": 1, "RECHAZAR": 2, "INCALCULABLE": 3}
        df["_sort"] = df["Decisión Consolidada"].map(order).fillna(3)
        df = df.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)

        return df

    def approved(
        self, evaluations: dict[str, CompanyEvaluation]
    ) -> list[CompanyEvaluation]:
        """Filtra empresas con decisión consolidada APROBAR."""
        return [e for e in evaluations.values() if e.consolidated_decision == "APROBAR"]

    def rejected(
        self, evaluations: dict[str, CompanyEvaluation]
    ) -> list[CompanyEvaluation]:
        """Filtra empresas con decisión consolidada RECHAZAR."""
        return [e for e in evaluations.values() if e.consolidated_decision == "RECHAZAR"]

    def grey_zone(
        self, evaluations: dict[str, CompanyEvaluation]
    ) -> list[CompanyEvaluation]:
        """Filtra empresas en ZONA GRIS — requieren análisis adicional."""
        return [e for e in evaluations.values() if e.consolidated_decision == "ZONA GRIS"]

    # ------------------------------------------------------------------
    # Privado
    # ------------------------------------------------------------------

    @staticmethod
    def _consolidate(
        altman: ModelResult, merton: ModelResult
    ) -> tuple[str, str]:
        """
        Lógica conservadora de consolidación:

        Regla 1: Si algún modelo no pudo calcularse → INCALCULABLE
        Regla 2: Si alguno RECHAZA → decisión consolidada RECHAZAR
        Regla 3: Si alguno es ZONA GRIS y el otro APRUEBA → ZONA GRIS
        Regla 4: Solo si AMBOS APRUEBAN → APROBAR

        Esta lógica refleja la práctica bancaria: en due diligence crediticio
        una señal de alerta en cualquier modelo es suficiente para escalar
        el análisis o rechazar. La aprobación requiere consenso.
        """
        # Regla 1
        altman_ok = altman.is_calculable()
        merton_ok = merton.is_calculable()

        if not altman_ok and not merton_ok:
            return "INCALCULABLE", "Ambos modelos fallaron — datos insuficientes."
        if not altman_ok:
            return "INCALCULABLE", f"Altman no calculable: {altman.error}"
        if not merton_ok:
            return "INCALCULABLE", f"Merton no calculable: {merton.error}"

        decisions = {altman.credit_decision, merton.credit_decision}

        # Regla 2
        if "RECHAZAR" in decisions:
            rechazado_por = []
            if altman.credit_decision == "RECHAZAR":
                rechazado_por.append(f"Altman ({altman.risk_zone}, Z={altman.score})")
            if merton.credit_decision == "RECHAZAR":
                rechazado_por.append(f"Merton (PD={merton.probability_of_default:.2%}, DD={merton.score})")
            return "RECHAZAR", "Rechazado por: " + " | ".join(rechazado_por)

        # Regla 3
        if "ZONA GRIS" in decisions:
            gris_por = []
            if altman.credit_decision == "ZONA GRIS":
                gris_por.append(f"Altman ({altman.risk_zone}, Z={altman.score})")
            if merton.credit_decision == "ZONA GRIS":
                gris_por.append(f"Merton (PD={merton.probability_of_default:.2%}, DD={merton.score})")
            return "ZONA GRIS", "Zona gris en: " + " | ".join(gris_por)

        # Regla 4
        return (
            "APROBAR",
            f"Altman: {altman.risk_zone} (Z={altman.score}) | "
            f"Merton: PD={merton.probability_of_default:.2%}, DD={merton.score}",
        )

    @staticmethod
    def _log_result(ev: CompanyEvaluation) -> None:
        logger.info(
            f"[{ev.ticker}] "
            f"Altman: {ev.altman_result.credit_decision if ev.altman_result else 'N/A'} | "
            f"Merton: {ev.merton_result.credit_decision if ev.merton_result else 'N/A'} | "
            f"Consolidado: {ev.consolidated_decision}"
        )