"""
altman_zscore.py
----------------
Implementación de las tres versiones del Z-score de Altman con
selección automática del modelo según sector e industria.

Fuentes primarias:
    - Altman, E.I. (1968). "Financial Ratios, Discriminant Analysis and
      the Prediction of Corporate Bankruptcy." Journal of Finance, 23(4).
    - Altman, E.I. (1983). "Corporate Financial Distress." Wiley.
    - Altman, E.I. (1995). "Predicting Financial Distress of Companies:
      Revisiting the Z-Score and Zeta Models."

Por qué estas fuentes:
    Los papers originales de Altman son la referencia canónica usada por
    bancos, agencias de rating y reguladores. Damodaran y otros autores
    reproducen los coeficientes sin modificación. Usar los papers originales
    evita errores de transcripción de fuentes secundarias.

Diferencias entre modelos:
    Z  (1968): manufactureras públicas. Usa valor de mercado del equity en X4.
    Z' (1983): manufactureras privadas. Reemplaza market value por book value
               en X4 y recalibra coeficientes.
    Z''(1995): universal. Elimina X5 (ventas/activos) para neutralizar sesgos
               sectoriales por intensidad de activos. Más conservador.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from models.base_model import CreditModel, ModelResult
from classifiers.sector_classifier import SectorClassifier, ZScoreModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Zonas de decisión por modelo
# ---------------------------------------------------------------------------

# Z original (1968)
_ZONES_ORIGINAL = [
    (2.99, float("inf"), "Safe Zone",     "APROBAR"),
    (1.81, 2.99,         "Grey Zone",     "ZONA GRIS"),
    (float("-inf"), 1.81,"Distress Zone", "RECHAZAR"),
]

# Z' (1983)
_ZONES_PRIME = [
    (2.90, float("inf"), "Safe Zone",     "APROBAR"),
    (1.23, 2.90,         "Grey Zone",     "ZONA GRIS"),
    (float("-inf"), 1.23,"Distress Zone", "RECHAZAR"),
]

# Z'' (1995)
_ZONES_DOUBLE_PRIME = [
    (2.60, float("inf"), "Safe Zone",     "APROBAR"),
    (1.10, 2.60,         "Grey Zone",     "ZONA GRIS"),
    (float("-inf"), 1.10,"Distress Zone", "RECHAZAR"),
]


def _get_zone(score: float, zones: list) -> tuple[str, str]:
    for low, high, label, decision in zones:
        if low <= score < high:
            return label, decision
    return "Distress Zone", "RECHAZAR"


# ---------------------------------------------------------------------------
# Extractor robusto de conceptos contables
# ---------------------------------------------------------------------------

class _BalanceExtractor:
    """
    Adaptador de datos contables provenientes de yfinance.

    Resuelve inconsistencias en nomenclatura mediante
    búsqueda por aliases.

    Aísla la lógica de extracción de datos del modelo financiero,
    siguiendo el principio de separación de responsabilidades.
    """

    # Aliases por concepto — se prueban en orden, se usa el primero encontrado
    _ALIASES = {
        "total_assets": [
            "Total Assets", "TotalAssets", "totalAssets",
        ],
        "total_liabilities": [
            "Total Liabilities Net Minority Interest",
            "Total Liabilities",
            "TotalLiabilitiesNetMinorityInterest",
            "totalLiabilities",
        ],
        "current_assets": [
            "Current Assets", "TotalCurrentAssets",
            "currentAssets", "Total Current Assets",
        ],
        "current_liabilities": [
            "Current Liabilities", "TotalCurrentLiabilities",
            "currentLiabilities", "Total Current Liabilities",
        ],
        "retained_earnings": [
            "Retained Earnings", "RetainedEarnings",
            "retainedEarnings", "Retained Earnings (Deficit)",
        ],
        "ebit": [
            "EBIT", "Ebit", "Operating Income",
            "OperatingIncome", "operatingIncome",
        ],
        "revenue": [
            "Total Revenue", "TotalRevenue", "Revenue",
            "totalRevenue", "revenue",
        ],
        "book_equity": [
            "Stockholders Equity", "Total Stockholder Equity",
            "StockholdersEquity", "Common Stock Equity",
            "CommonStockEquity", "stockholdersEquity",
            "Total Equity Gross Minority Interest",
        ],
        "interest_expense": [
            "Interest Expense", "InterestExpense", "interestExpense",
        ],
    }

    def __init__(self, balance_sheet: pd.DataFrame, income_stmt: pd.DataFrame):
        self.bs = balance_sheet
        self.inc = income_stmt

    def get(self, concept: str, df_override: Optional[pd.DataFrame] = None) -> Optional[float]:
        """
        Retorna el valor más reciente del concepto.
        df_override permite buscar en income_stmt en lugar del balance sheet.
        """
        aliases = self._ALIASES.get(concept, [concept])
        df = df_override if df_override is not None else self.bs

        for alias in aliases:
            if alias in df.index:
                val = df.loc[alias].iloc[0]  # columna más reciente
                if pd.notna(val):
                    return float(val)
        return None

    def get_income(self, concept: str) -> Optional[float]:
        return self.get(concept, df_override=self.inc)


# ---------------------------------------------------------------------------
# Modelo principal
# ---------------------------------------------------------------------------

class AltmanZScore(CreditModel):
    """
    Implementación integral del modelo discriminante de Altman.

    Integra automáticamente tres versiones históricas:
        - Z (1968) → manufactureras públicas
        - Z' (1983) → manufactureras privadas
        - Z'' (1995) → no manufactureras / servicios

    El modelo aplica análisis discriminante múltiple sobre
    ratios contables normalizados.

    No produce probabilidad explícita de default;
    genera un score continuo clasificado en zonas de riesgo.
    """

    def __init__(self):
        self._classifier = SectorClassifier()

    @property
    def name(self) -> str:
        return "Altman Z-score"

    def calculate(self, company) -> ModelResult:
        """
        Punto de entrada principal del modelo Altman.

        Flujo:
            1. Validar disponibilidad de estados financieros.
            2. Determinar versión aplicable vía SectorClassifier.
            3. Delegar al métod0 específico (Z, Z' o Z'').

        El usuario no necesita seleccionar manualmente la versión.
        """
        ticker = company.ticker

        # Validar datos mínimos
        if company.balance_sheet.empty:
            return ModelResult(
                ticker=ticker,
                model_name=self.name,
                error="Balance sheet no disponible.",
            )

        # Determinar versión
        zscore_model = self._classifier.classify(
            sector=company.sector,
            industry=company.industry,
            is_public=True,
        )

        ext = _BalanceExtractor(company.balance_sheet, company.income_statement)

        # Despachar al métoodo correcto
        if zscore_model == ZScoreModel.ORIGINAL:
            return self._calculate_original(company, ext)
        elif zscore_model == ZScoreModel.PRIME:
            return self._calculate_prime(company, ext)
        else:
            return self._calculate_double_prime(company, ext)

    # ------------------------------------------------------------------
    # Z original (1968) — manufactureras públicas
    # ------------------------------------------------------------------

    def _calculate_original(self, company, ext: _BalanceExtractor) -> ModelResult:
        """
        Implementación de Z (1968) para manufactureras públicas.

        Incluye X4 basado en Market Capitalization,
        lo que introduce sensibilidad a precios bursátiles.

        X1 = Working Capital / Total Assets
        X2 = Retained Earnings / Total Assets
        X3 = EBIT / Total Assets
        X4 = Market Cap / Total Liabilities
        X5 = Revenue / Total Assets
        """
        model_name = "Altman Z-score (Original 1968)"
        warnings = []

        total_assets      = ext.get("total_assets")
        total_liabilities = ext.get("total_liabilities")
        current_assets    = ext.get("current_assets")
        current_liab      = ext.get("current_liabilities")
        retained_earnings = ext.get("retained_earnings")
        ebit              = ext.get_income("ebit")
        revenue           = ext.get_income("revenue")
        market_cap        = company.market_cap

        # Validar denominadores críticos
        if not total_assets:
            return ModelResult(ticker=company.ticker, model_name=model_name,
                               error="Total Assets no disponible.")
        if not market_cap:
            warnings.append("Market Cap no disponible — usando Book Equity como proxy (reduce precisión).")
            market_cap = ext.get("book_equity") or 0.0

        working_capital = (current_assets or 0) - (current_liab or 0)
        if not current_assets or not current_liab:
            warnings.append("Working Capital calculado con datos parciales.")

        # Cálculo de ratios financieros normalizados por Total Assets.
        # Cada ratio representa una dimensión económica distinta:
        # liquidez, rentabilidad acumulada, eficiencia operativa,
        # apalancamiento de mercado y rotación de activos.
        x1 = working_capital / total_assets
        x2 = (retained_earnings or 0) / total_assets
        x3 = (ebit or 0) / total_assets
        x4 = market_cap / (total_liabilities or 1)
        x5 = (revenue or 0) / total_assets

        z = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
        zone, decision = _get_zone(z, _ZONES_ORIGINAL)

        return ModelResult(
            ticker=company.ticker,
            model_name=model_name,
            score=round(z, 4),
            credit_decision=decision,
            risk_zone=zone,
            years_used=1,
            warnings=warnings,
            components={
                "X1_working_capital_to_assets": round(x1, 4),
                "X2_retained_earnings_to_assets": round(x2, 4),
                "X3_ebit_to_assets": round(x3, 4),
                "X4_market_cap_to_liabilities": round(x4, 4),
                "X5_revenue_to_assets": round(x5, 4),
            },
        )

    # ------------------------------------------------------------------
    # Z' (1983) — manufactureras privadas
    # ------------------------------------------------------------------

    def _calculate_prime(self, company, ext: _BalanceExtractor) -> ModelResult:
        """
        Implementación de Z' (1983) para manufactureras privadas.

        Sustituye Market Cap por Book Equity en X4
        y recalibra coeficientes.
        """
        model_name = "Altman Z'-score (1983, Privadas)"
        warnings = []

        total_assets      = ext.get("total_assets")
        total_liabilities = ext.get("total_liabilities")
        current_assets    = ext.get("current_assets")
        current_liab      = ext.get("current_liabilities")
        retained_earnings = ext.get("retained_earnings")
        ebit              = ext.get_income("ebit")
        revenue           = ext.get_income("revenue")
        book_equity       = ext.get("book_equity")

        if not total_assets:
            return ModelResult(ticker=company.ticker, model_name=model_name,
                               error="Total Assets no disponible.")

        working_capital = (current_assets or 0) - (current_liab or 0)
        if not current_assets or not current_liab:
            warnings.append("Working Capital calculado con datos parciales.")

        x1 = working_capital / total_assets
        x2 = (retained_earnings or 0) / total_assets
        x3 = (ebit or 0) / total_assets
        x4 = (book_equity or 0) / (total_liabilities or 1)
        x5 = (revenue or 0) / total_assets

        z = 0.717*x1 + 0.847*x2 + 3.107*x3 + 0.420*x4 + 0.998*x5
        zone, decision = _get_zone(z, _ZONES_PRIME)

        return ModelResult(
            ticker=company.ticker,
            model_name=model_name,
            score=round(z, 4),
            credit_decision=decision,
            risk_zone=zone,
            years_used=1,
            warnings=warnings,
            components={
                "X1_working_capital_to_assets": round(x1, 4),
                "X2_retained_earnings_to_assets": round(x2, 4),
                "X3_ebit_to_assets": round(x3, 4),
                "X4_book_equity_to_liabilities": round(x4, 4),
                "X5_revenue_to_assets": round(x5, 4),
            },
        )

    # ------------------------------------------------------------------
    # Z'' (1995) — no manufactureras / servicios / emergentes
    # ------------------------------------------------------------------

    def _calculate_double_prime(self, company, ext: _BalanceExtractor) -> ModelResult:
        """
        Implementación de Z'' (1995) para empresas no manufactureras.

        Elimina X5 (Ventas/Activos) para evitar sesgo sectorial
        por intensidad de activos
        Recalibra coeficientes para el universo no-manufacturero.
        X4 usa Book Equity (no Market Cap) para hacerlo más estable y universal.
        """
        model_name = "Altman Z''-score (1995, No Manufactureras)"
        warnings = []

        total_assets      = ext.get("total_assets")
        total_liabilities = ext.get("total_liabilities")
        current_assets    = ext.get("current_assets")
        current_liab      = ext.get("current_liabilities")
        retained_earnings = ext.get("retained_earnings")
        ebit              = ext.get_income("ebit")
        book_equity       = ext.get("book_equity")

        if not total_assets:
            return ModelResult(ticker=company.ticker, model_name=model_name,
                               error="Total Assets no disponible.")

        working_capital = (current_assets or 0) - (current_liab or 0)
        if not current_assets or not current_liab:
            warnings.append("Working Capital calculado con datos parciales.")

        if not book_equity:
            warnings.append("Book Equity no disponible — X4 se calcula como 0.")

        # Ratios contables normalizados por activos.
        # Versión más conservadora y universal del modelo Altman.
        x1 = working_capital / total_assets
        x2 = (retained_earnings or 0) / total_assets
        x3 = (ebit or 0) / total_assets
        x4 = (book_equity or 0) / (total_liabilities or 1)

        z = 6.56*x1 + 3.26*x2 + 6.72*x3 + 1.05*x4
        zone, decision = _get_zone(z, _ZONES_DOUBLE_PRIME)

        return ModelResult(
            ticker=company.ticker,
            model_name=model_name,
            score=round(z, 4),
            credit_decision=decision,
            risk_zone=zone,
            years_used=1,
            warnings=warnings,
            components={
                "X1_working_capital_to_assets": round(x1, 4),
                "X2_retained_earnings_to_assets": round(x2, 4),
                "X3_ebit_to_assets": round(x3, 4),
                "X4_book_equity_to_liabilities": round(x4, 4),
            },
        )

    def describe(self) -> str:
        return """
## Altman Z-score

### Origen y fuente
Desarrollado por Edward I. Altman (1968) en la NYU Stern School of Business.
Extendido en 1983 (Z') para empresas privadas y en 1995 (Z'') para empresas
no manufactureras y mercados emergentes. Se usan los papers originales de
Altman como fuente primaria para evitar errores de transcripción de fuentes
secundarias.

### Por qué Altman
El Z-score es el modelo de predicción de quiebra más citado en finanzas
corporativas. Bancos comerciales, agencias de rating (Moody's, S&P) y
reguladores lo usan como screening inicial de crédito. Su fortaleza es la
interpretabilidad: cada ratio tiene significado económico claro.

### Las tres versiones

**Z original (1968)** — empresas manufactureras que cotizan en bolsa.
Usa cinco ratios ponderados. El ratio X4 incorpora el valor de mercado
del equity, lo que lo hace sensible a variaciones de precio bursátil.
Zonas: Safe > 2.99 | Grey 1.81–2.99 | Distress < 1.81

**Z' (1983)** — empresas manufactureras privadas.
Reemplaza el valor de mercado por el valor en libros del equity en X4,
recalibrando los coeficientes. Aplicable a empresas sin cotización pública.
Zonas: Safe > 2.90 | Grey 1.23–2.90 | Distress < 1.23

**Z'' (1995)** — empresas no manufactureras, servicios, mercados emergentes.
Elimina el ratio Ventas/Activos (X5) porque en empresas de servicios este
ratio refleja el modelo de negocio, no la salud financiera. Es el modelo
más universal y conservador de los tres.
Zonas: Safe > 2.60 | Grey 1.10–2.60 | Distress < 1.10

### Selección automática
El sistema detecta el sector e industria de Yahoo Finance y aplica el modelo
correspondiente sin intervención del usuario.

### Limitaciones
- Calibrado con datos de empresas de los años 60-90. Algunos sectores modernos
  (SaaS, fintech, biotech) pueden producir scores distorsionados.
- Z-score es un modelo estático: usa datos de un solo período fiscal.
- No produce probabilidad de default directamente.
"""