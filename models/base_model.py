"""
base_model.py
-------------
Define las abstracciones fundamentales del sistema de riesgo crediticio.

Contiene:
    - ModelResult → estructura estándar de salida para cualquier modelo.
    - CreditModel → interfaz abstracta que garantiza consistencia
      entre implementaciones (Altman, Merton u otros futuros).

Principios de diseño aplicados:
    - Open/Closed: nuevos modelos se agregan mediante subclases.
    - Liskov Substitution: cualquier CreditModel puede utilizarse
      indistintamente por el evaluador.
    - Single Responsibility: este módulo solo define contratos,
      no contiene lógica financiera.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelResult:
    """
    Estructura uniforme de salida para modelos cuantitativos de riesgo.

    Permite desacoplar:
        - Cálculo financiero (modelo).
        - Evaluación consolidada.
        - Generación de reportes.

    Campos clave:
        score → métrica principal (Z-score o Distance to Default).
        probability_of_default → PD explícita (solo Merton).
        credit_decision → decisión operativa normalizada.
        components → métricas intermedias para auditoría técnica.

    El diseño facilita trazabilidad, comparabilidad y extensibilidad.
    """
    ticker: str
    model_name: str                  # e.g., "Altman Z-score (Z'')", "Merton"

    # Métrica cuantitativa principal del modelo.
    score: Optional[float] = None    # Z-score o Distance to Default

    # Probabilidad de default (0-1). Merton la calcula directamente.
    # Altman no produce PD, se deja None.
    probability_of_default: Optional[float] = None

    # Decisión crediticia
    credit_decision: str = "INCALCULABLE"  # "APROBAR" | "RECHAZAR" | "ZONA GRIS" | "INCALCULABLE"
    risk_zone: str = ""                    # descripción de la zona (e.g., "Distress", "Safe")

    # Diccionario con variables internas relevantes para análisis técnico y auditoría.
    # (ratios para Z-score, V_A / sigma_A para Merton, etc.)
    components: dict = field(default_factory=dict)

    # Años de datos usados efectivamente en el cálculo
    years_used: int = 0

    # Advertencias no fatales (e.g., "Solo 3 años disponibles, se esperaban 10")
    warnings: list[str] = field(default_factory=list)

    # Mensaje de error si el cálculo falló completamente
    error: Optional[str] = None

    def is_calculable(self) -> bool:
        """
        Indica si el modelo produjo un resultado válido.

        Un resultado es calculable si:
            - Existe score numérico.
            - No se registró error crítico.
        """
        return self.score is not None and self.error is None


class CreditModel(ABC):
    """
    Contrato formal para cualquier modelo cuantitativo de riesgo.

    Tod0 modelo debe:
        1. Exponer un nombre legible.
        2. Implementar calculate().
        3. Proveer descripción metodológica.

    El evaluador depende únicamente de esta interfaz
    (principio de inversión de dependencias).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre legible del modelo. e.g., 'Altman Z-score (Original 1968)'"""
        ...

    @abstractmethod
    def calculate(self, company) -> ModelResult:
        """
        Ejecuta el modelo sobre los datos de una empresa.

        Parámetros:
            company: CompanyFinancials con los datos de la empresa

        Retorna:
            ModelResult con score, decisión y componentes intermedios.
            Nunca lanza excepción — errores van dentro de ModelResult.error.
        """
        ...

    @abstractmethod
    def describe(self) -> str:
        """
        Descripción del modelo para incluir en el reporte:
        origen, supuestos, variables, zonas de interpretación
        y por qué se eligió esta fuente.
        """
        ...

    def safe_calculate(self, company) -> ModelResult:
        """
        Wrapper defensivo que encapsula excepciones inesperadas.

        Garantiza que el flujo batch nunca se interrumpa
        por errores individuales de cálculo.
        """
        try:
            return self.calculate(company)
        except Exception as e:
            return ModelResult(
                ticker=company.ticker,
                model_name=self.name,
                error=f"Error inesperado en {self.name}: {e}",
            )