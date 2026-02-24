"""
merton.py
---------
Implementación del modelo de Merton (1974) para probabilidad de default
usando datos históricos del balance sheet (hasta 10 años).

Fuente primaria:
    Merton, R.C. (1974). "On the Pricing of Corporate Debt: The Risk Structure
    of Interest Rates." Journal of Finance, 29(2), 449-470.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import norm

from models.base_model import CreditModel, ModelResult

logger = logging.getLogger(__name__)


class MertonModel(CreditModel):
    """
    Implementación estructural del modelo de Merton (1974).

    Marco conceptual:
    -----------------
    El equity se modela como una opción call europea sobre el valor total
    de los activos de la firma (V_A), con precio de ejercicio igual al
    valor nominal de la deuda (D).

    Supuestos estructurales:
        - V_A sigue un proceso log-normal (Geometric Brownian Motion).
        - Estructura de capital simple: Activos = Deuda + Equity.
        - Default ocurre si V_A < D al horizonte T.
        - Mercados sin fricciones y tasa libre de riesgo constante.

    Esta implementación utiliza una aproximación basada en balance sheet,
    estimando la volatilidad de activos (σ_A) mediante log-retornos
    históricos de Total Assets. No implementa la versión KMV iterativa.
    """
    def __init__(self, risk_free_rate: float = 0.045, T: float = 1.0):
        self.r = risk_free_rate
        self.T = T

    @property
    def name(self) -> str:
        return "Merton Model (1974)"

    def calculate(self, company) -> ModelResult:
        """
        Estima Distance to Default (DD) y Probabilidad de Default (PD).

        Procedimiento:
            1. Extraer V_A (Total Assets más reciente).
            2. Definir D como proxy del default point.
            3. Estimar σ_A con log-retornos históricos anuales.
            4. Aplicar fórmula cerrada de DD.
            5. Transformar DD en PD usando la CDF normal estándar.

        Retorna:
            ModelResult con métricas cuantitativas y decisión crediticia.
        """
        ticker = company.ticker
        warnings = []

        if company.balance_sheet.empty:
            return ModelResult(
                ticker=ticker,
                model_name=self.name,
                error="Balance sheet no disponible.",
            )

        assets_series = self._extract_series(company.balance_sheet, [
            "Total Assets", "TotalAssets", "totalAssets",
        ])
        std_series = self._extract_series(company.balance_sheet, [
            "Current Debt",
            "Current Debt And Capital Lease Obligation",
            "Short Term Debt",
            "ShortTermDebt",
            "shortTermDebt",
            "Current Portion Of Long Term Debt",
            "Current Capital Lease Obligation",
        ])
        ltd_series = self._extract_series(company.balance_sheet, [
            "Long Term Debt",
            "LongTermDebt",
            "longTermDebt",
            "Long Term Debt And Capital Lease Obligation",
        ])
        liabilities_series = self._extract_series(company.balance_sheet, [
            "Total Liabilities Net Minority Interest",
            "Total Liabilities",
            "TotalLiabilitiesNetMinorityInterest",
            "totalLiabilities",
        ])

        if assets_series is None or len(assets_series) < 2:
            return ModelResult(
                ticker=ticker,
                model_name=self.name,
                error="Se necesitan mínimo 2 años de Total Assets para calcular σ_A.",
            )

        if std_series is None and ltd_series is None and liabilities_series is None:
            return ModelResult(
                ticker=ticker,
                model_name=self.name,
                error="No se encontró información de deuda en el balance.",
            )

        years_used = len(assets_series)
        if years_used < 5:
            warnings.append(
                f"Solo {years_used} años disponibles. "
                f"Con menos de 5 años, σ_A tiene mayor incertidumbre."
            )

        V_A = float(assets_series.iloc[0])
        D = float(liabilities_series.iloc[0]) if liabilities_series is not None and len(liabilities_series) > 0 else 0.0
        debt_method = "Total Liabilities"

        if D <= 0:
            return ModelResult(
                ticker=ticker,
                model_name=self.name,
                error="Default point es cero o negativo — modelo no aplicable.",
            )

        assets_chrono = assets_series.iloc[::-1].values.astype(np.float64)

        # Estimación de volatilidad de activos (σ_A)
        # Se utilizan log-retornos anuales y desviación estándar muestral (ddof=1).
        log_returns   = np.diff(np.log(assets_chrono))
        sigma_A       = float(np.std(log_returns, ddof=1))

        if sigma_A <= 0:
            return ModelResult(
                ticker=ticker,
                model_name=self.name,
                error="σ_A = 0 — activos sin variación histórica, datos insuficientes.",
            )

        ln_ratio = np.log(V_A / D)
        drift    = (self.r - 0.5 * sigma_A**2) * self.T
        denom    = sigma_A * np.sqrt(self.T)

        # Fórmula cerrada de Distance to Default:
        # DD = [ ln(V_A / D) + (r - 0.5σ_A²)T ] / (σ_A √T)
        DD = (ln_ratio + drift) / denom

        # Probabilidad de default bajo distribución normal estándar:
        # PD = 1 - N(DD)
        PD = float(1 - norm.cdf(DD))

        decision, zone = self._credit_decision(PD, DD)

        return ModelResult(
            ticker=ticker,
            model_name=self.name,
            score=round(DD, 4),
            probability_of_default=round(PD, 6),
            credit_decision=decision,
            risk_zone=zone,
            years_used=years_used,
            warnings=warnings,
            components={
                "V_A_total_assets_current":     round(V_A, 2),
                "D_default_point_KMV":          round(D, 2),
                "D_method":                     debt_method,
                "sigma_A_log_returns":          round(sigma_A, 6),
                "leverage_D_over_VA":           round(D / V_A, 4),
                "ln_VA_over_D":                 round(ln_ratio, 6),
                "distance_to_default_DD":       round(DD, 4),
                "probability_of_default_PD":    round(PD, 6),
                "risk_free_rate_r":             round(self.r, 4),
                "horizon_T_years":              self.T,
                "years_of_data_used":           years_used,
            },
        )

    @staticmethod
    def _extract_series(df: pd.DataFrame, aliases: list[str]) -> Optional[pd.Series]:
        """
        Busca un concepto contable dentro del DataFrame
        utilizando múltiples posibles aliases.

        Retorna:
            Serie ordenada en orden descendente (año más reciente primero).
        """
        for alias in aliases:
            if alias in df.index:
                series = df.loc[alias].dropna()
                if len(series) > 0:
                    return series.sort_index(ascending=False)
        return None

    @staticmethod
    def _credit_decision(PD: float, DD: float) -> tuple[str, str]:
        """
        Traduce métricas cuantitativas (PD, DD)
        a una decisión crediticia operativa.

        Los umbrales son heurísticos y pueden
        ajustarse según política interna.
        """
        if PD < 0.01:
            return "APROBAR", f"Investment Grade (PD={PD:.2%}, DD={DD:.2f})"
        elif PD < 0.05:
            return "ZONA GRIS", f"Sub-Investment Grade (PD={PD:.2%}, DD={DD:.2f})"
        else:
            return "RECHAZAR", f"Distress / High Yield (PD={PD:.2%}, DD={DD:.2f})"

    def describe(self) -> str:
        return """\

## Modelo de Merton (1974)

### Origen y fuente
Desarrollado por Robert C. Merton (1974) como extensión del modelo de
Black-Scholes para valorar deuda corporativa con riesgo de default.
Merton recibió el Premio Nobel de Economía en 1997 en parte por este trabajo.
Fuente primaria: Merton (1974), *Journal of Finance*, 29(2), 449–470.

### Fundamento teórico
El equity de una empresa es conceptualizado como un call option europeo
sobre sus activos totales, con precio de ejercicio igual al valor facial
de la deuda al vencimiento T:

```
E = V_A · N(d1) - D · e^(-rT) · N(d2)
```

El default ocurre cuando V_A < D al tiempo T. La probabilidad de default
es la probabilidad de que el valor de activos caiga por debajo de la deuda.

### Implementación: versión de balance sheet
En lugar de la versión KMV (que requiere precios de mercado y resolución
iterativa del sistema de ecuaciones), se usan datos del balance directamente:

| Parámetro | Definición | Fuente |
|-----------|------------|--------|
| V_A | Total Assets — año más reciente | `yfinance` balance_sheet |
| D | Total Liabilities — año más reciente | `yfinance` balance_sheet |
| σ_A | Std. dev. de log-retornos históricos anuales de V_A | Serie histórica Total Assets |
| r | Rendimiento del Treasury a 10 años | `yfinance` ticker ^TNX |
| T | Horizonte temporal = 1 año | Parámetro fijo del modelo |

### Fórmulas

**Distance to Default:**

```
DD = [ ln(V_A / D) + (r - σ_A² / 2) · T ] / (σ_A · √T)
```

**Probabilidad de Default:**

```
PD = N(−DD) = 1 − N(DD)
```

donde N(·) es la función de distribución acumulada de la normal estándar.

### Interpretación del DD
DD representa cuántas desviaciones estándar separan el valor actual de
activos del punto de quiebra técnica (V_A = D). Un DD de 2.0 significa
que el valor de activos tendría que caer 2 desviaciones estándar para
alcanzar el nivel de default.

### Decisión crediticia

| Umbral PD | Zona | Decisión |
|-----------|------|----------|
| PD < 1% | <span class="decision-aprobar">Safe Zone</span> — equivalente aproximado a Investment Grade | APROBAR |
| PD 1–5% | <span class="decision-zona-gris">Grey Zone</span> — Sub-investment, requiere análisis adicional | ZONA GRIS |
| PD > 5% | <span class="decision-rechazar">Distress Zone</span> — High Yield / Distress | RECHAZAR |

### Diferencia con Altman
Altman clasifica mediante análisis discriminante sobre ratios contables.
Merton modela el proceso estocástico del valor de activos y deriva la PD
desde primeros principios de la teoría de opciones. Merton produce una
probabilidad continua (0–100%); Altman produce un score de clasificación.

### Limitaciones
- Con pocos años de datos (< 5), σ_A es una estimación ruidosa.
- Asume que V_A sigue un proceso log-normal — puede no cumplirse en crisis.
- No captura deuda estructurada, covenants, ni garantías colaterales.
- Los umbrales de PD son orientativos; en la práctica bancaria varían
  por política interna, sector y ciclo económico."""