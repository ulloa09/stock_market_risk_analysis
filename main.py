"""
main.py
-------
Orquestador principal del pipeline de evaluación crediticia.

Responsabilidades:
    1. Obtener datos financieros.
    2. Ejecutar modelos (Altman + Merton).
    3. Ejecutar evaluación consolidada.
    4. Generar visualizaciones.
    5. Construir reporte final.

Diseñado para:
    - Ejecución CLI.
    - Integración como backend para API FastAPI.

Cada etapa está desacoplada para mantener robustez y trazabilidad.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)


def run_pipeline(
    tickers: list[str],
    force_refresh: bool = False,
    output_dir: str = "outputs",          # ← NUEVO: cada job de API pasa su propio path
) -> dict:
    """
    Ejecuta el flujo completo de análisis crediticio.

    Parámetros:
        tickers        → lista de símbolos bursátiles.
        force_refresh  → ignora caché local si es True.
        output_dir     → directorio raíz para artefactos generados.

    Retorna:
        Diccionario con:
            - evaluations
            - summary_df
            - plot_paths
            - report_path

    Esta función es el punto de integración central
    entre dominio financiero, visualización y reporte.
    """
    from data.fetcher import FinancialDataFetcher
    from models.altman_zscore import AltmanZScore
    from models.merton import MertonModel
    from evaluation.credit_evaluator import CreditEvaluator
    from visualization.plotter import CreditPlotter
    from reporting.report_generator import ReportGenerator

    # Construcción dinámica de estructura de salida por ejecución.
    base = Path(output_dir)
    plots_dir   = str(base / "plots")
    reports_dir = str(base / "reports")

    logger.info("=" * 60)
    logger.info(f"Iniciando evaluación para: {', '.join(tickers)}")
    logger.info(f"Output dir: {base}")
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # 1. Descarga de datos
    # ------------------------------------------------------------------
    logger.info("PASO 1 — Descarga / caché de datos financieros")
    # Capa de adquisición de datos (infraestructura).
    fetcher = FinancialDataFetcher(data_dir="data/")
    companies = fetcher.fetch_multiple(tickers, force_refresh=force_refresh)

    risk_free_rate = fetcher.get_risk_free_rate()
    logger.info(f"Tasa libre de riesgo (10Y Treasury): {risk_free_rate:.4f}")

    invalid = [t for t, c in companies.items() if not c.is_valid()]
    if invalid:
        logger.warning(f"Sin datos suficientes para: {', '.join(invalid)}")

    # ------------------------------------------------------------------
    # 2. Modelos
    # ------------------------------------------------------------------
    logger.info("PASO 2 — Instanciando modelos")
    # Modelos cuantitativos (capa de dominio financiero).
    altman = AltmanZScore()
    merton = MertonModel(risk_free_rate=risk_free_rate, T=1.0)

    # ------------------------------------------------------------------
    # 3. Evaluación crediticia
    # ------------------------------------------------------------------
    logger.info("PASO 3 — Evaluación crediticia")
    # Evaluador consolidado que aplica reglas de decisión conjunta.
    evaluator  = CreditEvaluator(altman_model=altman, merton_model=merton)
    evaluations = evaluator.evaluate_all(companies)
    summary_df  = evaluator.summary_dataframe(evaluations)

    _print_summary(evaluations, summary_df)

    # ------------------------------------------------------------------
    # 4. Visualizaciones
    # ------------------------------------------------------------------
    logger.info("PASO 4 — Generando gráficos")
    # Generación de visualizaciones (capa de presentación gráfica).
    plotter    = CreditPlotter(output_dir=plots_dir)
    plot_paths = plotter.plot_all(evaluations, summary_df)

    # ------------------------------------------------------------------
    # 5. Reporte Markdown
    # ------------------------------------------------------------------
    logger.info("PASO 5 — Generando reporte Markdown")
    # Generación de reporte final en Markdown.
    reporter    = ReportGenerator(output_dir=reports_dir)
    report_path = reporter.generate(
        evaluations=evaluations,
        summary_df=summary_df,
        plot_paths=plot_paths,
    )
    logger.info(f"Reporte guardado en: {report_path}")
    logger.info("=" * 60)
    logger.info("Pipeline completado.")
    logger.info("=" * 60)

    return {
        "evaluations": evaluations,
        "summary_df":  summary_df,
        "plot_paths":  plot_paths,
        "report_path": report_path,
    }


def _print_summary(evaluations, summary_df) -> None:
    """
    Imprime en consola un resumen detallado por empresa.

    Incluye:
        - Modelo Altman utilizado.
        - Componentes internos (ratios / variables).
        - DD y PD de Merton.
        - Decisión consolidada y justificación.

    Diseñado para debugging y revisión manual.
    """
    print("\n" + "=" * 70)
    print("  RESUMEN DE EVALUACIÓN CREDITICIA")
    print("=" * 70)

    for ticker, ev in evaluations.items():
        print(f"\n{'─' * 70}")
        print(f"  {ticker} — {ev.company_name}")
        print(f"  Sector: {ev.sector} | Industria: {ev.industry}")
        print(f"{'─' * 70}")

        ar = ev.altman_result
        if ar and ar.is_calculable():
            print(f"  [ALTMAN] Modelo: {ar.model_name}")
            print(f"  [ALTMAN] Score: {ar.score} | Zona: {ar.risk_zone} | Decisión: {ar.credit_decision}")
            print(f"  [ALTMAN] Componentes:")
            for k, v in ar.components.items():
                print(f"           {k}: {v}")
            for w in ar.warnings:
                print(f"  [ALTMAN] ⚠️  {w}")
        else:
            print(f"  [ALTMAN] ❌ No calculable: {ar.error if ar else 'Sin datos'}")

        mr = ev.merton_result
        if mr and mr.is_calculable():
            print(f"  [MERTON] DD: {mr.score} | PD: {mr.probability_of_default:.6f} ({mr.probability_of_default:.4%}) | Decisión: {mr.credit_decision}")
            print(f"  [MERTON] Componentes:")
            for k, v in mr.components.items():
                print(f"           {k}: {v}")
            for w in mr.warnings:
                print(f"  [MERTON] ⚠️  {w}")
        else:
            print(f"  [MERTON] ❌ No calculable: {mr.error if mr else 'Sin datos'}")

        decision_icons = {"APROBAR": "✅", "ZONA GRIS": "⚠️ ", "RECHAZAR": "❌", "INCALCULABLE": "❓"}
        icon = decision_icons.get(ev.consolidated_decision, "❓")
        print(f"  CONSOLIDADO: {icon} {ev.consolidated_decision}")
        print(f"  Razón: {ev.consolidated_reasoning}")

    print("\n" + "=" * 70)
    aprobadas  = summary_df[summary_df["Decisión Consolidada"] == "APROBAR"]
    rechazadas = summary_df[summary_df["Decisión Consolidada"] == "RECHAZAR"]
    gris       = summary_df[summary_df["Decisión Consolidada"] == "ZONA GRIS"]
    print(f"  ✅ Aprobadas  ({len(aprobadas)}): {', '.join(aprobadas['Ticker'].tolist()) or 'Ninguna'}")
    print(f"  ⚠️  Zona Gris  ({len(gris)}):  {', '.join(gris['Ticker'].tolist()) or 'Ninguna'}")
    print(f"  ❌ Rechazadas ({len(rechazadas)}): {', '.join(rechazadas['Ticker'].tolist()) or 'Ninguna'}")
    print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# Entrada por consola
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python main.py TICKER1 TICKER2 ...")
        print("Ejemplo: python main.py AAPL F ADBE MSFT")
        sys.exit(1)

    tickers_input = [t.upper().strip() for t in sys.argv[1:]]

    force = "--force" in tickers_input
    if force:
        tickers_input.remove("--force")

    run_pipeline(tickers=tickers_input, force_refresh=force)