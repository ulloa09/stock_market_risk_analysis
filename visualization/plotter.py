"""
plotter.py
----------
Genera gráficos con estilo oscuro consistente con la UI:

    1. zscore_comparison   — Altman Z-score por empresa con zonas
    2. merton_dd           — Distance to Default por empresa
    3. merton_pd           — Probabilidad de Default (%) por empresa
    4. risk_heatmap        — Scatter Z-score vs PD (mapa combinado)

"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from evaluation.credit_evaluator import CompanyEvaluation

logger = logging.getLogger(__name__)

# ── Paleta principal ────────────────────────────────────────────────────────
_BG        = "#111111"
_SURFACE   = "#1a1a1a"
_BORDER    = "#2a2a2a"
_TEXT      = "#e8e4de"
_MUTED     = "#666666"
_GRID      = "#222222"

_C = {
    "APROBAR":      "#22c55e",   # verde
    "ZONA GRIS":    "#eab308",   # amarillo
    "RECHAZAR":     "#ef4444",   # rojo
    "INCALCULABLE": "#4b5563",   # gris
}

_DEFAULT_OUTPUT_DIR = Path("outputs/plots")


def _apply_dark_style(fig, axes):
    """Aplica estilo oscuro a figura y lista de ejes."""
    fig.patch.set_facecolor(_BG)
    for ax in (axes if isinstance(axes, (list, tuple)) else [axes]):
        ax.set_facecolor(_SURFACE)
        ax.tick_params(colors=_MUTED, labelsize=9)
        ax.xaxis.label.set_color(_MUTED)
        ax.yaxis.label.set_color(_MUTED)
        ax.title.set_color(_TEXT)
        for spine in ax.spines.values():
            spine.set_edgecolor(_BORDER)
        ax.grid(color=_GRID, linewidth=0.6, linestyle="-")
        ax.set_axisbelow(True)


def _save(fig, path: Path, dpi: int) -> Path:
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor=_BG)
    plt.close(fig)
    logger.info(f"Guardado: {path}")
    return path


class CreditPlotter:

    def __init__(self, output_dir: str = str(_DEFAULT_OUTPUT_DIR), dpi: int = 150):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dpi = dpi

        plt.rcParams.update({
            "font.family":       "DejaVu Sans",
            "font.size":         10,
            "figure.facecolor":  _BG,
            "axes.facecolor":    _SURFACE,
            "axes.edgecolor":    _BORDER,
            "axes.labelcolor":   _MUTED,
            "xtick.color":       _MUTED,
            "ytick.color":       _MUTED,
            "text.color":        _TEXT,
            "grid.color":        _GRID,
            "grid.linewidth":    0.6,
            "axes.grid":         True,
            "axes.spines.top":   False,
            "axes.spines.right": False,
            "legend.facecolor":  _SURFACE,
            "legend.edgecolor":  _BORDER,
            "legend.labelcolor": _TEXT,
            "legend.fontsize":   8,
        })

    # ── Punto de entrada ────────────────────────────────────────────────────

    def plot_all(
        self,
        evaluations: dict[str, CompanyEvaluation],
        summary_df: pd.DataFrame,
    ) -> dict[str, Path]:
        paths = {}
        # Z-score: puede generar 1 o más gráficas dependiendo de cuántos modelos se usaron
        zscore_paths = self.plot_zscore(summary_df, evaluations)
        paths.update(zscore_paths)
        paths["merton_dd"]    = self.plot_merton_dd(summary_df)
        paths["merton_pd"]    = self.plot_merton_pd(summary_df)
        paths["risk_heatmap"] = self.plot_risk_heatmap(summary_df)
        logger.info(f"Gráficos generados en: {self.output_dir}")
        return paths

    # ── Gráfico 1: Z-score (una gráfica por modelo si hay más de uno) ──────────

    # Umbrales por modelo (safe, distress)
    _ZSCORE_THRESHOLDS = {
        "original": (2.99, 1.81, "Z ≥ 2.99", "Z < 1.81"),
        "prime":    (2.90, 1.23, "Z' ≥ 2.90", "Z' < 1.23"),
        "double_prime": (2.60, 1.10, "Z'' ≥ 2.60", "Z'' < 1.10"),
    }

    @staticmethod
    def _model_key(model_name: str) -> str:
        """Mapea el model_name del ModelResult al key de umbrales."""
        n = model_name.lower()
        if "z''" in n or "double" in n or "1995" in n or "no manuf" in n:
            return "double_prime"
        if "z'" in n or "prime" in n or "1983" in n or "privad" in n:
            return "prime"
        return "original"

    def plot_zscore(
        self,
        summary_df: pd.DataFrame,
        evaluations: dict[str, CompanyEvaluation] | None = None,
    ) -> dict[str, Path]:
        """
        Genera una gráfica de Z-score por cada modelo Altman usado.
        Si solo hay un modelo → dict con key 'zscore_comparison'.
        Si hay varios → 'zscore_original', 'zscore_prime', 'zscore_double_prime'.
        Si no se pasan evaluations → comportamiento anterior (un solo gráfico).
        """
        df = summary_df.dropna(subset=["Z-score"]).copy()
        if df.empty:
            return {"zscore_comparison": self._empty("zscore_comparison", "Sin datos de Z-score")}

        # Agrupar tickers por modelo usando evaluations
        groups: dict[str, list[str]] = {}  # model_key → [tickers]
        if evaluations:
            for ticker in df["Ticker"]:
                ev = evaluations.get(ticker)
                if ev and ev.altman_result and ev.altman_result.is_calculable():
                    key = self._model_key(ev.altman_result.model_name)
                    groups.setdefault(key, []).append(ticker)
        # Si no hay evaluations o todos caen en un grupo → un solo gráfico
        if not groups or len(groups) == 1:
            key = list(groups.keys())[0] if groups else "double_prime"
            path = self._plot_zscore_group(df, df["Ticker"].tolist(), key, "zscore_comparison")
            return {"zscore_comparison": path}

        # Varios modelos → una gráfica por modelo
        paths = {}
        for model_key, tickers in groups.items():
            file_key = f"zscore_{model_key}"
            path = self._plot_zscore_group(df, tickers, model_key, file_key)
            paths[file_key] = path
        return paths

    def _plot_zscore_group(
        self,
        df: pd.DataFrame,
        tickers: list[str],
        model_key: str,
        file_key: str,
    ) -> Path:
        sub = df[df["Ticker"].isin(tickers)].sort_values("Z-score", ascending=False)
        scores = sub["Z-score"].tolist()
        tick_labels = sub["Ticker"].tolist()
        colors = [_C.get(d, _C["INCALCULABLE"]) for d in sub["Decisión Z-score"]]
        n = len(tick_labels)

        safe_val, dist_val, safe_label, dist_label = self._ZSCORE_THRESHOLDS.get(
            model_key, self._ZSCORE_THRESHOLDS["double_prime"]
        )

        # Título por modelo
        titles = {
            "original":     "Altman Z-score — Original (1968, Manufactureras)",
            "prime":        "Altman Z'-score — (1983, Manufactureras Privadas)",
            "double_prime": "Altman Z''-score — (1995, No Manufactureras / Servicios)",
        }
        title = titles.get(model_key, "Altman Z-score por Empresa")

        fig, ax = plt.subplots(figsize=(max(7, n * 1.1), 5))
        _apply_dark_style(fig, ax)

        bars = ax.bar(tick_labels, scores, color=colors, edgecolor=_BG,
                      width=0.55, linewidth=0.8, zorder=3)

        ax.axhline(safe_val, color=_C["APROBAR"],  linestyle="--", linewidth=1.2,
                   alpha=0.7, label=f"Safe  {safe_label}", zorder=4)
        ax.axhline(dist_val, color=_C["RECHAZAR"], linestyle="--", linewidth=1.2,
                   alpha=0.7, label=f"Distress  {dist_label}", zorder=4)
        ax.axhspan(dist_val, safe_val, color=_C["ZONA GRIS"], alpha=0.04, zorder=2)

        y_min = min(min(scores) - 0.5, 0)
        for bar, score in zip(bars, scores):
            ypos = bar.get_height() + 0.06 if score >= 0 else bar.get_height() - 0.25
            ax.text(
                bar.get_x() + bar.get_width() / 2, ypos,
                f"{score:.2f}", ha="center", va="bottom",
                fontsize=8, fontweight="bold", color=_TEXT
            )

        ax.set_ylabel("Z-score", fontsize=10)
        ax.set_title(title, fontsize=12, fontweight="bold", pad=14)
        ax.set_ylim(bottom=y_min)
        ax.legend(loc="upper right")
        plt.xticks(rotation=30 if n > 5 else 0, ha="right")
        plt.tight_layout(pad=1.5)
        return _save(fig, self.output_dir / f"{file_key}.png", self.dpi)

    # ── Gráfico 2: Distance to Default ──────────────────────────────────────

    def plot_merton_dd(self, summary_df: pd.DataFrame) -> Path:
        """
        Barras verticales del DD. Rojo = empresa en distress (DD < 0).
        Línea horizontal en DD=0 (punto de default técnico).
        """
        df = summary_df.dropna(subset=["DD (Merton)"]).copy()
        if df.empty:
            return self._empty("merton_dd", "Sin datos de Merton DD")

        df = df.sort_values("DD (Merton)", ascending=False)
        tickers = df["Ticker"].tolist()
        dds     = df["DD (Merton)"].tolist()
        colors  = [_C.get(d, _C["INCALCULABLE"]) for d in df["Decisión Merton"]]
        n = len(tickers)

        fig, ax = plt.subplots(figsize=(max(7, n * 1.1), 5))
        _apply_dark_style(fig, ax)

        bars = ax.bar(tickers, dds, color=colors, edgecolor=_BG,
                      width=0.55, linewidth=0.8, zorder=3)

        ax.axhline(0, color=_C["RECHAZAR"], linestyle="-", linewidth=1.2,
                   alpha=0.8, label="Default técnico (DD = 0)", zorder=4)

        # Etiquetas
        for bar, dd in zip(bars, dds):
            offset = 0.08 if dd >= 0 else -0.25
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                dd + offset,
                f"{dd:.2f}",
                ha="center", va="bottom", fontsize=8,
                fontweight="bold", color=_TEXT
            )

        ax.set_ylabel("Distance to Default (DD)", fontsize=10)
        ax.set_title("Merton — Distance to Default por Empresa",
                     fontsize=12, fontweight="bold", pad=14)
        ax.legend(loc="upper right")
        plt.xticks(rotation=30 if n > 5 else 0, ha="right")
        plt.tight_layout(pad=1.5)
        return _save(fig, self.output_dir / "merton_dd.png", self.dpi)

    # ── Gráfico 3: Probabilidad de Default ──────────────────────────────────

    def plot_merton_pd(self, summary_df: pd.DataFrame) -> Path:
        """
        Barras horizontales de PD (%) ordenadas de mayor a menor riesgo.
        Líneas verticales en los umbrales 1% y 5%.
        """
        df = summary_df.dropna(subset=["PD (Merton)"]).copy()
        if df.empty:
            return self._empty("merton_pd", "Sin datos de Merton PD")

        df = df.sort_values("PD (Merton)", ascending=True)   # mayor riesgo arriba
        tickers = df["Ticker"].tolist()
        pds     = (df["PD (Merton)"] * 100).tolist()
        colors  = [_C.get(d, _C["INCALCULABLE"]) for d in df["Decisión Merton"]]
        n = len(tickers)

        fig, ax = plt.subplots(figsize=(8, max(4, n * 0.65)))
        _apply_dark_style(fig, ax)

        bars = ax.barh(tickers, pds, color=colors, edgecolor=_BG,
                       height=0.55, linewidth=0.8, zorder=3)

        # Umbrales
        ax.axvline(1.0, color=_C["APROBAR"],  linestyle="--", linewidth=1.2,
                   alpha=0.8, label="1% — umbral Aprobar", zorder=4)
        ax.axvline(5.0, color=_C["RECHAZAR"], linestyle="--", linewidth=1.2,
                   alpha=0.8, label="5% — umbral Rechazar", zorder=4)

        # Zona gris sombreada
        ax.axvspan(1.0, 5.0, color=_C["ZONA GRIS"], alpha=0.05, zorder=2)

        # Etiquetas al final de la barra
        x_max = max(pds) if pds else 10
        for bar, pd_val in zip(bars, pds):
            ax.text(
                pd_val + x_max * 0.015,
                bar.get_y() + bar.get_height() / 2,
                f"{pd_val:.2f}%",
                ha="left", va="center", fontsize=8,
                fontweight="bold", color=_TEXT
            )

        ax.set_xlabel("Probabilidad de Default (%)", fontsize=10)
        ax.set_title("Merton — Probabilidad de Default por Empresa",
                     fontsize=12, fontweight="bold", pad=14)
        ax.set_xlim(right=x_max * 1.18)
        ax.legend(loc="lower right")
        plt.tight_layout(pad=1.5)
        return _save(fig, self.output_dir / "merton_pd.png", self.dpi)

    # ── Gráfico 4: Mapa de riesgo combinado ─────────────────────────────────

    def plot_risk_heatmap(self, summary_df: pd.DataFrame) -> Path:
        """
        Scatter Z-score (X) vs PD% (Y). Cada punto = empresa.
        Límites calculados para que los puntos no queden pegados a los bordes.
        Leyenda fuera del área de datos (esquina superior izquierda exterior).
        """
        df = summary_df.dropna(subset=["Z-score", "PD (Merton)"]).copy()
        if df.empty:
            return self._empty("risk_heatmap", "Sin datos suficientes para mapa")

        x_vals = df["Z-score"].values
        y_vals = (df["PD (Merton)"] * 100).values

        # Límites con padding proporcional — los datos siempre quedan centrados
        x_range = max(x_vals) - min(x_vals) if len(x_vals) > 1 else 2.0
        y_range = max(y_vals) - min(y_vals) if len(y_vals) > 1 else 5.0
        pad_x = max(x_range * 0.20, 0.5)
        pad_y = max(y_range * 0.20, 1.0)

        x_lo = min(x_vals) - pad_x
        x_hi = max(x_vals) + pad_x
        y_lo = 0.0
        y_hi = max(y_vals) + pad_y * 2.5   # espacio extra arriba para etiquetas

        # Figura más ancha para que la leyenda quepa a la derecha sin tapar puntos
        fig, ax = plt.subplots(figsize=(10, 6))
        _apply_dark_style(fig, ax)

        # Zonas de fondo (solo si los umbrales caen dentro del rango visible)
        if x_hi > 2.60:
            ax.fill_between([max(2.60, x_lo), x_hi], y_lo, min(1.0, y_hi),
                            color=_C["APROBAR"], alpha=0.05, zorder=1)
        if x_lo < 1.10 and y_hi > 5.0:
            ax.fill_between([x_lo, min(1.10, x_hi)], max(5.0, y_lo), y_hi,
                            color=_C["RECHAZAR"], alpha=0.05, zorder=1)

        # Líneas de umbral
        if x_lo < 2.60 < x_hi:
            ax.axvline(2.60, color=_C["APROBAR"],  linestyle="--",
                       linewidth=0.9, alpha=0.6, label="Z = 2.60 (Safe)")
        if x_lo < 1.10 < x_hi:
            ax.axvline(1.10, color=_C["RECHAZAR"], linestyle="--",
                       linewidth=0.9, alpha=0.6, label="Z = 1.10 (Distress)")
        if y_lo < 1.0 < y_hi:
            ax.axhline(1.0, color=_C["APROBAR"],  linestyle=":",
                       linewidth=0.9, alpha=0.6, label="PD = 1%")
        if y_lo < 5.0 < y_hi:
            ax.axhline(5.0, color=_C["RECHAZAR"], linestyle=":",
                       linewidth=0.9, alpha=0.6, label="PD = 5%")

        # Puntos
        for _, row in df.iterrows():
            color = _C.get(row["Decisión Consolidada"], _C["INCALCULABLE"])
            ax.scatter(
                row["Z-score"], row["PD (Merton)"] * 100,
                color=color, s=120, edgecolors=_BG,
                linewidth=1.2, zorder=5
            )
            ax.annotate(
                row["Ticker"],
                (row["Z-score"], row["PD (Merton)"] * 100),
                textcoords="offset points", xytext=(8, 6),
                fontsize=8.5, color=_TEXT, fontweight="bold",
                zorder=6
            )

        ax.set_xlabel("Altman Z-score", fontsize=10)
        ax.set_ylabel("Probabilidad de Default Merton (%)", fontsize=10)
        ax.set_title("Mapa de Riesgo Combinado — Z-score vs PD Merton",
                     fontsize=12, fontweight="bold", pad=14)
        ax.set_xlim(x_lo, x_hi)
        ax.set_ylim(y_lo, y_hi)

        # Leyenda fuera del área de datos — a la derecha
        decision_patches = [
            mpatches.Patch(color=_C[d], label=d)
            for d in ["APROBAR", "ZONA GRIS", "RECHAZAR", "INCALCULABLE"]
        ]
        threshold_lines, threshold_labels = ax.get_legend_handles_labels()
        ax.legend(
            handles=decision_patches + threshold_lines,
            labels=[p.get_label() for p in decision_patches] + threshold_labels,
            loc="upper left",
            bbox_to_anchor=(1.01, 1.0),
            borderaxespad=0,
            fontsize=8,
            framealpha=0.9,
        )

        plt.tight_layout(pad=1.5)
        return _save(fig, self.output_dir / "risk_heatmap.png", self.dpi)

    # ── Fallback ────────────────────────────────────────────────────────────

    def _empty(self, name: str, message: str) -> Path:
        fig, ax = plt.subplots(figsize=(8, 4))
        _apply_dark_style(fig, ax)
        ax.text(0.5, 0.5, message, ha="center", va="center",
                fontsize=12, color=_MUTED, transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])
        path = self.output_dir / f"{name}.png"
        return _save(fig, path, self.dpi)