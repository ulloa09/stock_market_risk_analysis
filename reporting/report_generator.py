"""
report_generator.py
-------------------
Genera el reporte integral en Markdown a partir de los
resultados de evaluación crediticia.

Responsabilidades:
    - Construcción estructurada por secciones.
    - Integración de tablas y visualizaciones.
    - Preparación para conversión posterior a PDF.

No ejecuta cálculos financieros.
Actúa como capa de presentación.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from evaluation.credit_evaluator import CompanyEvaluation
from models.altman_zscore import AltmanZScore
from models.merton import MertonModel

logger = logging.getLogger(__name__)

# Directorio por defecto para reportes generados.
_DEFAULT_OUTPUT = Path("outputs/reports")

# Diccionario manual para evitar dependencia del local del sistema.
_MESES_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}

# Mapeo de decisiones operativas a etiquetas HTML estilizadas para PDF.
_DECISION_LABEL = {
    "APROBAR":       '<span class="decision-aprobar">APROBADO</span>',
    "ZONA GRIS":     '<span class="decision-zona-gris">ZONA GRIS</span>',
    "RECHAZAR":      '<span class="decision-rechazar">RECHAZADO</span>',
    "INCALCULABLE":  '<span class="decision-incalculable">INCALCULABLE</span>',
}

_WARNING_LABEL  = '<span class="label-advertencia">ADVERTENCIA</span>'
_SAFE_LABEL     = '<span class="decision-aprobar">Safe Zone</span>'
_GREY_LABEL     = '<span class="decision-zona-gris">Grey Zone</span>'
_DISTRESS_LABEL = '<span class="decision-rechazar">Distress Zone</span>'


def _fecha_es(dt: datetime) -> str:
    # Formateo de fecha en español independiente del entorno del sistema.
    return f"{dt.day} de {_MESES_ES[dt.month]} de {dt.year}"


class ReportGenerator:
    """
    Construye el documento final de evaluación crediticia.

    Orquesta múltiples secciones:
        - Portada
        - Descripción metodológica
        - Resultados individuales
        - Tabla comparativa
        - Visualizaciones
        - Conclusiones
        - Bibliografía

    Diseñado para producir Markdown compatible con conversión
    posterior a HTML/PDF mediante WeasyPrint.
    """
    def __init__(self, output_dir: str = str(_DEFAULT_OUTPUT)):
        # Se almacenan descripciones una sola vez para evitar recalcular.
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._altman_description = AltmanZScore().describe()
        self._merton_description = MertonModel().describe()

    def generate(
        self,
        evaluations: dict[str, CompanyEvaluation],
        summary_df: pd.DataFrame,
        plot_paths: Optional[dict[str, Path]] = None,
        filename: str = "credit_report.md",
    ) -> Path:
        plot_paths = plot_paths or {}
        sections = [
            self._section_cover(evaluations),
            self._section_model_intro(),
            self._section_methodology(),
            self._section_results_per_company(evaluations),
            self._section_summary_table(summary_df),
            self._section_visualizations(plot_paths),
            self._section_conclusions(evaluations, summary_df),
            self._section_bibliography(),
        ]
        content = "\n\n---\n\n".join(sections)
        path = self.output_dir / filename
        path.write_text(content, encoding="utf-8")
        logger.info(f"Reporte generado: {path}")
        return path

    # ── Secciones ──────────────────────────────────────────────────────────

    # Sección: Portada
    def _section_cover(self, evaluations: dict[str, CompanyEvaluation]) -> str:
        tickers  = list(evaluations.keys())
        date_str = _fecha_es(datetime.now())
        return f"""# Evaluación Crediticia: Altman Z-score y Modelo de Merton

**Fecha de generación:** {date_str}
**Empresas evaluadas:** {len(tickers)}
**Tickers:** {", ".join(tickers)}

## Propósito

Este reporte aplica dos modelos cuantitativos de riesgo crediticio para determinar
la viabilidad de otorgar crédito. Altman analiza la salud financiera contable;
Merton modela la probabilidad de default desde la teoría de opciones sobre activos.

La decisión consolidada requiere que ambos modelos coincidan en APROBAR.
Un rechazo en cualquiera de los dos es suficiente para escalar o rechazar."""

    # Sección: Descripción de Modelos
    def _section_model_intro(self) -> str:
        return f"""## Modelos Utilizados

### Altman Z-score

{self._altman_description}

### Modelo de Merton (1974)

{self._merton_description}"""

    # Sección: Metodología y Justificación de Variables
    def _section_methodology(self) -> str:
        return """\
## Metodología y Fuentes de Datos

### Fuente de datos financieros: Yahoo Finance vía `yfinance`

Los estados financieros se obtienen a través de la librería `yfinance`, que expone
la API no oficial de Yahoo Finance y provee hasta 10 años de información anual auditada
por empresa pública. Se utiliza esta fuente porque es de acceso abierto, cubre la
mayoría de empresas listadas en mercados regulados, y sus datos provienen de los
reportes SEC (10-K) o equivalentes internacionales. A continuación se justifica
la elección de cada variable que alimenta el modelo de Merton:

---

#### V_A — Valor de los activos: `Total Assets`

`Total Assets` es la suma de todos los activos de la empresa en el balance sheet.
En el modelo estructural de Merton (1974), V_A representa el valor de mercado de los
activos de la firma, que sigue un proceso de difusión geométrico browniano. Dado que
el valor de mercado de los activos no se observa directamente (solo se observa el
equity en bolsa), en la versión de balance sheet se usa `Total Assets` como proxy
del valor contable de los activos. Esta aproximación es estándar en implementaciones
académicas sin acceso al sistema iterativo KMV.

Fuente en `yfinance`: campo `Total Assets` del `balance_sheet` (DataFrame de Yahoo Finance).

---

#### D — Punto de default: `Total Liabilities`

El punto de default D es el umbral de valor de activos a partir del cual se produce
incumplimiento técnico (V_A < D al tiempo T). La especificación canónica del punto
de default proviene de Crosbie y Bohn (2003) en el framework KMV de Moody's:

```
D_KMV = Deuda de Corto Plazo (STD) + 0.5 × Deuda de Largo Plazo (LTD)
```

Esta fórmula refleja el argumento económico de que solo la deuda de corto plazo
presiona la liquidez en el horizonte T = 1 año, mientras que la deuda de largo plazo
pondera al 50% porque representa obligaciones futuras que el mercado descuenta pero
que no vencen en el horizonte inmediato.

**Por qué no se usa D_KMV en este sistema:**
Yahoo Finance reporta `Current Debt` y `Long Term Debt` de manera inconsistente entre
tickers: algunos incluyen arrendamientos capitalizados, otros los excluyen; en empresas
de sectores no financieros frecuentemente aparecen valores nulos o combinados bajo
etiquetas como `Current Debt And Capital Lease Obligation`. Aplicar D_KMV con datos
parciales o inconsistentes produce un punto de default artificialmente bajo y, por tanto,
un DD sobreoptimista que no refleja el riesgo real.

La literatura académica de crédito (Bharath & Shumway, 2008; Hillegeist et al., 2004)
valida el uso de `Total Liabilities` como punto de default conservador cuando no se
dispone del desglose STD/LTD confiable. Esta especificación es más estricta que D_KMV
(D_TL ≥ D_KMV para cualquier empresa con deuda de largo plazo), lo que resulta en un
DD menor y una PD mayor. En un contexto de análisis crediticio, el sesgo conservador
es preferible a subestimar el riesgo.

Fuente en `yfinance`: campo `Total Liabilities Net Minority Interest` del `balance_sheet`.

---

#### σ_A — Volatilidad de los activos: desviación estándar de log-retornos históricos

El modelo de Merton asume que el valor de activos sigue:

```
dV_A = μ · V_A · dt + σ_A · V_A · dW_t
```

Donde σ_A es la volatilidad anual del proceso log-normal. Se estima como la
desviación estándar muestral (ddof=1) de los log-retornos anuales de Total Assets:

```
log_return_t = ln(V_A(t) / V_A(t-1))
σ_A = std({ log_return_t }, ddof=1)
```

Se usan log-retornos porque son consistentes con el supuesto de proceso log-normal:
si V_A es log-normal, entonces ln(V_A(t)/V_A(t-1)) es normal con media (μ - σ²/2)·Δt
y varianza σ²·Δt.

Fuente en `yfinance`: serie histórica de `Total Assets` (hasta 10 años).
Con menos de 5 observaciones, σ_A es un estimador ruidoso — el reporte lo señala
explícitamente como advertencia.

---

#### r — Tasa libre de riesgo: rendimiento del Treasury a 10 años

La tasa libre de riesgo r se obtiene en tiempo real del ticker `^TNX` de Yahoo Finance,
que corresponde al rendimiento del bono del Tesoro de Estados Unidos a 10 años.
Se usa como parámetro de drift bajo la medida risk-neutral Q, consistente con la
valoración Black-Scholes sobre la que se fundamenta Merton (1974).

En la fórmula de Distance to Default implementada:

```
DD = [ln(V_A / D) + (r - σ_A² / 2) · T] / (σ_A · √T)
```

El drift del numerador es `(r - σ_A²/2)`, correspondiente a la medida de valoración
risk-neutral (Merton, 1974, eq. 12), en la que el drift esperado de los activos bajo Q
es igual a r.

Fuente en `yfinance`: ticker `^TNX` (CBOE Interest Rate 10-Year T-Note), obtenido el
día de la ejecución del análisis.

---

#### T — Horizonte temporal: 1 año

T = 1 año es el horizonte estándar en análisis de crédito a corto plazo. Crosbie y Bohn
(2003) lo justifican como el horizonte de revisión crediticia típico de bancos y agencias
de rating. Altman y Saunders (1998) señalan que horizontes mayores aumentan la
incertidumbre de los parámetros sin mejorar la capacidad predictiva para decisiones
de otorgamiento de crédito. T es un parámetro fijo del modelo configurable en el
constructor de `MertonModel`.

---

### Selección automática de versión de Z-score

El sistema detecta el sector e industria de cada empresa vía Yahoo Finance y aplica
la versión correcta del Z-score sin intervención del usuario (Z original, Z' o Z'')."""

    # Sección: Resultados Detallados por Empresa
    def _section_results_per_company(self, evaluations: dict[str, CompanyEvaluation]) -> str:
        sections = ["## Resultados por Empresa"]
        for ev in evaluations.values():
            sections.append(self._company_block(ev))
        return "\n\n".join(sections)

    def _company_block(self, ev: CompanyEvaluation) -> str:
        decision_label = _DECISION_LABEL.get(ev.consolidated_decision, ev.consolidated_decision)

        lines = [
            f"### {ev.ticker} — {ev.company_name}",
            f"**Sector:** {ev.sector} | **Industria:** {ev.industry}",
            f"**Decisión Consolidada:** {decision_label}",
            f"**Razonamiento:** {ev.consolidated_reasoning}",
            "",
            "#### Altman Z-score",
        ]

        if ev.altman_result and ev.altman_result.is_calculable():
            ar = ev.altman_result
            zona_label = self._zona_altman_label(ar.risk_zone)
            lines += [
                f"- **Modelo aplicado:** {ar.model_name}",
                f"- **Score:** {ar.score}",
                f"- **Zona:** {zona_label}",
                f"- **Decisión:** {_DECISION_LABEL.get(ar.credit_decision, ar.credit_decision)}",
                "", "**Componentes:**", "",
                "| Ratio | Valor |", "|-------|-------|",
            ]
            for k, v in ar.components.items():
                lines.append(f"| {k} | {v} |")
            if ar.warnings:
                lines += ["", "**Advertencias:**"]
                for w in ar.warnings:
                    lines.append(f"- {_WARNING_LABEL} {w}")
        else:
            error = ev.altman_result.error if ev.altman_result else "Sin datos"
            lines.append(f'- <span class="decision-rechazar">No calculable:</span> {error}')

        lines += ["", "#### Modelo de Merton"]

        if ev.merton_result and ev.merton_result.is_calculable():
            mr = ev.merton_result
            zona_label = self._zona_merton_label(mr.risk_zone)
            lines += [
                f"- **Distance to Default (DD):** {mr.score}",
                f"- **Probabilidad de Default (PD):** {mr.probability_of_default:.4%}",
                f"- **Zona:** {zona_label}",
                f"- **Decisión:** {_DECISION_LABEL.get(mr.credit_decision, mr.credit_decision)}",
                f"- **Años de datos usados:** {mr.years_used}",
                "", "**Componentes:**", "",
                "| Parámetro | Valor |", "|-----------|-------|",
            ]
            for k, v in mr.components.items():
                lines.append(f"| {k} | {v} |")
            if mr.warnings:
                lines += ["", "**Advertencias:**"]
                for w in mr.warnings:
                    lines.append(f"- {_WARNING_LABEL} {w}")
        else:
            error = ev.merton_result.error if ev.merton_result else "Sin datos"
            lines.append(f'- <span class="decision-rechazar">No calculable:</span> {error}')

        return "\n".join(lines)

    @staticmethod
    def _zona_altman_label(risk_zone: str) -> str:
        rz = risk_zone.lower()
        if "safe" in rz:
            return _SAFE_LABEL
        if "grey" in rz or "gray" in rz or "gris" in rz:
            return _GREY_LABEL
        if "distress" in rz:
            return _DISTRESS_LABEL
        return risk_zone

    @staticmethod
    def _zona_merton_label(risk_zone: str) -> str:
        rz = risk_zone.lower()
        if "investment grade" in rz or "aprobar" in rz:
            return _SAFE_LABEL
        if "sub-investment" in rz or "gris" in rz or "grey" in rz:
            return _GREY_LABEL
        if "distress" in rz or "high yield" in rz or "rechazar" in rz:
            return _DISTRESS_LABEL
        return risk_zone

    # Sección: Tabla Comparativa Resumida
    def _section_summary_table(self, summary_df: pd.DataFrame) -> str:
        """
        Tabla comparativa — 6 columnas para caber en A4 vertical.
        Se omiten Empresa y Sector (ya están en la sección por empresa).
        """
        cols_map = {
            "Ticker": "Ticker",
            "Z-score": "Z-score",
            "Zona Z-score": "Zona Altman",
            "DD (Merton)": "DD (Merton)",
            "PD (Merton)": "PD (Merton)",
            "Decisión Consolidada": "Decisión",
        }

        available = {k: v for k, v in cols_map.items() if k in summary_df.columns}
        df_slim = summary_df[list(available.keys())].copy()
        df_slim.columns = list(available.values())

        if "Z-score" in df_slim.columns:
            df_slim["Z-score"] = df_slim["Z-score"].apply(
                lambda x: f"{x:.4f}" if pd.notna(x) else "—"
            )
        if "DD (Merton)" in df_slim.columns:
            df_slim["DD (Merton)"] = df_slim["DD (Merton)"].apply(
                lambda x: f"{x:.4f}" if pd.notna(x) else "—"
            )
        if "PD (Merton)" in df_slim.columns:
            df_slim["PD (Merton)"] = df_slim["PD (Merton)"].apply(
                lambda x: f"{x:.4%}" if pd.notna(x) else "—"
            )
        if "Zona Altman" in df_slim.columns:
            df_slim["Zona Altman"] = df_slim["Zona Altman"].apply(
                lambda v: ReportGenerator._zona_altman_label(str(v)) if pd.notna(v) else "—"
            )
        if "Decisión" in df_slim.columns:
            df_slim["Decisión"] = df_slim["Decisión"].map(
                lambda v: _DECISION_LABEL.get(str(v), str(v))
            )

        table_md = df_slim.to_markdown(index=False)
        return (
            "## Tabla Comparativa de Resultados\n\n"
            '<div class="table-summary" markdown="1">\n\n'
            f"{table_md}\n\n"
            "</div>"
        )

    # Sección: Visualizaciones Gráficas
    def _section_visualizations(self, plot_paths: dict[str, Path]) -> str:
        if not plot_paths:
            return "## Visualizaciones\n\n*Gráficos no generados.*"

        descriptions = {
            "zscore_comparison": (
                "### Altman Z-score por Empresa\n"
                "Barras coloreadas por zona de riesgo con umbrales del modelo aplicado."
            ),
            "zscore_original": (
                "### Altman Z-score Original (1968) — Empresas Manufactureras\n"
                "Zonas: Safe > 2.99 | Grey 1.81–2.99 | Distress < 1.81."
            ),
            "zscore_prime": (
                "### Altman Z'-score (1983) — Manufactureras Privadas\n"
                "Zonas: Safe > 2.90 | Grey 1.23–2.90 | Distress < 1.23."
            ),
            "zscore_double_prime": (
                "### Altman Z''-score (1995) — No Manufactureras / Servicios\n"
                "Zonas: Safe > 2.60 | Grey 1.10–2.60 | Distress < 1.10."
            ),
            "merton_dd": (
                "### Merton — Distance to Default (DD)\n"
                "DD = cuántas desviaciones estándar separan V_A del punto de default (V_A = D). "
                "DD negativo indica que los activos ya están por debajo de la deuda."
            ),
            "merton_pd": (
                "### Merton — Probabilidad de Default (%)\n"
                "PD = N(−DD). Barras ordenadas de mayor a menor riesgo. "
                "Umbrales: 1% (Aprobar) y 5% (Rechazar)."
            ),
            "risk_heatmap": (
                "### Mapa de Riesgo Combinado — Z-score vs PD Merton\n"
                "Cada punto es una empresa. Esquina inferior derecha = menor riesgo. "
                "Las líneas dividen los cuadrantes por modelo."
            ),
        }

        lines = ["## Visualizaciones"]
        for key, path in plot_paths.items():
            desc = descriptions.get(key, f"### {key}")
            rel_path = Path("../plots") / path.name
            lines += [desc, f"![{key}]({rel_path})", ""]

        return "\n\n".join(lines)

    # Sección: Conclusiones del Portafolio
    def _section_conclusions(
        self,
        evaluations: dict[str, CompanyEvaluation],
        summary_df: pd.DataFrame,
    ) -> str:
        total     = len(evaluations)
        aprobadas = sum(1 for ev in evaluations.values() if ev.consolidated_decision == "APROBAR")
        rechazadas= sum(1 for ev in evaluations.values() if ev.consolidated_decision == "RECHAZAR")
        zona_gris = sum(1 for ev in evaluations.values() if ev.consolidated_decision == "ZONA GRIS")

        aprobadas_list  = [t for t, ev in evaluations.items() if ev.consolidated_decision == "APROBAR"]
        rechazadas_list = [t for t, ev in evaluations.items() if ev.consolidated_decision == "RECHAZAR"]
        zona_gris_list  = [t for t, ev in evaluations.items() if ev.consolidated_decision == "ZONA GRIS"]

        lines = [
            "## Conclusiones del Portafolio",
            "",
            f"De las **{total}** empresas evaluadas:",
            f'- {_DECISION_LABEL["APROBAR"]} **Aprobadas:** {aprobadas} — {", ".join(aprobadas_list) if aprobadas_list else "ninguna"}',
            f'- {_DECISION_LABEL["ZONA GRIS"]} **Zona Gris:** {zona_gris} — {", ".join(zona_gris_list) if zona_gris_list else "ninguna"}',
            f'- {_DECISION_LABEL["RECHAZAR"]} **Rechazadas:** {rechazadas} — {", ".join(rechazadas_list) if rechazadas_list else "ninguna"}',
            "",
            "### Observaciones",
        ]

        for ticker, ev in evaluations.items():
            if ev.consolidated_decision != "INCALCULABLE":
                lines.append(f"- **{ticker}:** {ev.consolidated_reasoning}")

        lines += [
            "",
            "---",
            "*Reporte generado automáticamente. Los resultados son orientativos y no "
            "sustituyen el análisis cualitativo del analista de crédito.*",
        ]
        return "\n".join(lines)

    # Sección: Referencias Académicas
    def _section_bibliography(self) -> str:
        return """\
## Bibliografía

Altman, E. I. (2000). *Predicting financial distress of companies: Revisiting the
Z-score and ZETA models* (Working Paper). NYU Stern School of Business.
https://pages.stern.nyu.edu/~ealtman/Zscores.pdf

Altman, E. I. (1983). *Corporate financial distress: A complete guide to predicting,
avoiding, and dealing with bankruptcy*. Wiley.

Altman, E. I., & Saunders, A. (1998). Credit risk measurement: Developments over the
last 20 years. *Journal of Banking & Finance, 21*(11–12), 1721–1742.
https://doi.org/10.1016/S0378-4266(97)00036-8

Bharath, S. T., & Shumway, T. (2008). Forecasting default with the Merton distance
to default model. *The Review of Financial Studies, 21*(3), 1339–1369.
https://doi.org/10.1093/rfs/hhn044

Black, F., & Scholes, M. (1973). The pricing of options and corporate liabilities.
*Journal of Political Economy, 81*(3), 637–654.
https://doi.org/10.1086/260062

Crosbie, P., & Bohn, J. (2003). *Modeling default risk* (Technical Report).
Moody's KMV. https://business.illinois.edu/gpennacc/MoodysKMV.pdf

Hillegeist, S. A., Keating, E. K., Cram, D. P., & Lundstedt, K. G. (2004).
Assessing the probability of bankruptcy. *Review of Accounting Studies, 9*(1), 5–34.
https://doi.org/10.1023/B:RAST.0000013627.90884.b7

Merton, R. C. (1974). On the pricing of corporate debt: The risk structure of interest
rates. *The Journal of Finance, 29*(2), 449–470.
https://doi.org/10.1111/j.1540-6261.1974.tb03058.x"""