"""
base_model.py
-------------
Define el contrato que tocho modelo de riesgo crediticio debe cumplir.

Principio: Open/Closed — el sistema está abierto a nuevos modelos
(agregar un modelo nuevo = crear una subclase) sin modificar nada existente.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModelResult:
    """
    Contenedor estándar de resultados para cualquier modelo.
    Todos los modelos retornan este mismo objeto — facilita
    comparación, reporte y visualización uniforme.
    """
    ticker: str
    model_name: str                  # e.g., "Altman Z-score (Z'')", "Merton"

    # Puntuación principal del modelo
    score: Optional[float] = None    # Z-score o Distance to Default

    # Probabilidad de default (0-1). Merton la calcula directamente.
    # Altman no produce PD, se deja None.
    probability_of_default: Optional[float] = None

    # Decisión crediticia
    credit_decision: str = "INCALCULABLE"  # "APROBAR" | "RECHAZAR" | "ZONA GRIS" | "INCALCULABLE"
    risk_zone: str = ""                    # descripción de la zona (e.g., "Distress", "Safe")

    # Componentes intermedios usados en el cálculo
    # (ratios para Z-score, V_A / sigma_A para Merton, etc.)
    components: dict = field(default_factory=dict)

    # Años de datos usados efectivamente en el cálculo
    years_used: int = 0

    # Advertencias no fatales (e.g., "Solo 3 años disponibles, se esperaban 10")
    warnings: list[str] = field(default_factory=list)

    # Mensaje de error si el cálculo falló completamente
    error: Optional[str] = None

    def is_calculable(self) -> bool:
        return self.score is not None and self.error is None


class CreditModel(ABC):
    """
    Interfaz que toodo modelo de riesgo crediticio debe implementar.

    Métodos obligatorios:
        calculate(company) → ModelResult
        describe()         → str   (introducción del modelo para el reporte)
        name               → str   (identificador legible)
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
        Wrapper que garantiza que calculate() nunca propague una excepción.
        Úsalo desde el evaluador en lugar de llamar calculate() directamente.
        """
        try:
            return self.calculate(company)
        except Exception as e:
            return ModelResult(
                ticker=company.ticker,
                model_name=self.name,
                error=f"Error inesperado en {self.name}: {e}",
            )