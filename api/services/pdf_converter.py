"""
pdf_converter.py
----------------
Módulo responsable de la conversión del reporte técnico generado
por el pipeline cuantitativo (Altman + Merton) desde Markdown a PDF.

Contexto dentro del sistema:
----------------------------
El ReportGenerator produce un archivo .md estructurado con:
    - Resultados de Z-Score (Altman)
    - Métricas estructurales de Merton (DD y PD)
    - Tablas comparativas
    - Gráficos exportados como PNG
    - Bibliografía académica

Este módulo transforma dicho documento en un PDF profesional listo
para descarga desde la API.

Pipeline de conversión:
    1. Lectura del archivo Markdown.
    2. Conversión a HTML mediante la librería `markdown`.
    3. Embebido de imágenes locales en formato base64.
    4. Aplicación de CSS corporativo inline.
    5. Renderizado final a PDF usando WeasyPrint.

Decisión tecnológica:
----------------------
Se utiliza WeasyPrint porque:
    - No depende de binarios externos (wkhtmltopdf).
    - Soporta CSS moderno.
    - Permite renderizado consistente cross-platform.
    - Maneja correctamente data URIs (base64).
"""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Hoja de estilos global aplicada al PDF.
# Define tipografía, tablas financieras, etiquetas de decisión
# y formato de bibliografía académica.

_PDF_CSS = """
@page {
    size: A4;
    margin: 2cm 2.5cm;
    @bottom-right {
        content: "Página " counter(page) " de " counter(pages);
        font-size: 9pt;
        color: #888;
    }
}

body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #1a1a2e;
    background: white;
}

h1 {
    font-size: 22pt;
    color: #1a1a2e;
    border-bottom: 3px solid #4f46e5;
    padding-bottom: 8px;
    margin-top: 30px;
}

h2 {
    font-size: 16pt;
    color: #2d2d6e;
    border-bottom: 1px solid #e0e0f0;
    padding-bottom: 4px;
    margin-top: 24px;
}

h3 {
    font-size: 13pt;
    color: #4f46e5;
    margin-top: 18px;
}

h4 {
    font-size: 11pt;
    color: #1a1a2e;
    margin-top: 14px;
    font-weight: 700;
}

/* ── Tablas estándar ── */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-size: 10pt;
}

th {
    background-color: #4f46e5;
    color: white;
    padding: 8px 12px;
    text-align: left;
    font-weight: 600;
}

td {
    padding: 7px 12px;
    border-bottom: 1px solid #e8e8f0;
    word-break: break-word;
    overflow-wrap: anywhere;
}

tr:nth-child(even) td {
    background-color: #f5f5ff;
}

/* ── Tabla comparativa ancha (wrapper .table-wide) ──
   Reduce el font-size para que quepa en A4 sin cortarse.
   word-break: break-all asegura que los valores numéricos largos hagan wrap. */
.table-wide table {
    font-size: 8.5pt;
    table-layout: fixed;
}

.table-wide th,
.table-wide td {
    padding: 5px 7px;
    word-break: break-all;
    overflow-wrap: anywhere;
    hyphens: auto;
}

/* ── Tabla resumen — 6 columnas, A4 vertical ── */
.table-summary table {
    font-size: 8pt;
    table-layout: fixed;
    width: 100%;
}

.table-summary th:nth-child(1) { width: 10%; }   /* Ticker */
.table-summary th:nth-child(2) { width: 14%; }   /* Z-score */
.table-summary th:nth-child(3) { width: 18%; }   /* Zona Altman */
.table-summary th:nth-child(4) { width: 14%; }   /* DD */
.table-summary th:nth-child(5) { width: 14%; }   /* PD */
.table-summary th:nth-child(6) { width: 30%; }   /* Decisión */

.table-summary th,
.table-summary td {
    padding: 5px 6px;
    word-break: break-word;
    overflow-wrap: anywhere;
}

/* ── Código ── */
code {
    background: #f0f0f8;
    padding: 2px 5px;
    border-radius: 3px;
    font-size: 9.5pt;
    font-family: 'Courier New', monospace;
}

pre {
    background: #f0f0f8;
    padding: 12px;
    border-radius: 6px;
    border-left: 4px solid #4f46e5;
    overflow-x: auto;
    font-size: 9pt;
    font-family: 'Courier New', monospace;
    white-space: pre-wrap;
    word-break: break-all;
}

pre code {
    background: none;
    padding: 0;
    font-size: inherit;
}

blockquote {
    border-left: 4px solid #4f46e5;
    margin: 0;
    padding: 8px 16px;
    color: #555;
    background: #f8f8ff;
}

img {
    max-width: 100%;
    height: auto;
    margin: 12px 0;
    border-radius: 6px;
}

p {
    margin: 8px 0;
}

hr {
    border: none;
    border-top: 1px solid #ddd;
    margin: 20px 0;
}

/* ── Etiquetas de decisión crediticia ──────────────────────────────────── */

.decision-aprobar {
    color: #15803d;          /* verde oscuro, legible en blanco */
    font-weight: 700;
    font-size: 10pt;
}

.decision-rechazar {
    color: #b91c1c;          /* rojo oscuro */
    font-weight: 700;
    font-size: 10pt;
}

.decision-zona-gris {
    color: #b45309;          /* ámbar oscuro — visible sin fondo */
    font-weight: 700;
    font-size: 10pt;
}

.decision-incalculable {
    color: #6b7280;          /* gris */
    font-weight: 700;
    font-size: 10pt;
}

/* Badge pequeño para advertencias en línea */
.label-advertencia {
    background-color: #fef3c7;
    color: #92400e;
    font-weight: 700;
    font-size: 8.5pt;
    padding: 1px 5px;
    border-radius: 3px;
    border: 1px solid #f59e0b;
}

/* ── Bibliografía — sangría francesa ── */
#bibliografía + p,
h2 + p {
    text-indent: 0;
}

/* Párrafos de bibliografía (cada referencia es un párrafo en el MD) */
.bibliography p {
    padding-left: 2em;
    text-indent: -2em;
    margin-bottom: 10px;
    font-size: 10pt;
    line-height: 1.5;
}
"""


def convert_md_to_pdf(md_path: Path, pdf_path: Path) -> Path:
    """
    Convierte un archivo Markdown a PDF mediante renderizado HTML intermedio.

    Flujo técnico:
    --------------
    1. Validación de dependencias (markdown, weasyprint).
    2. Lectura del contenido Markdown.
    3. Transformación a HTML estructurado.
    4. Embebido de imágenes locales como data URIs.
    5. Aplicación de CSS profesional.
    6. Renderizado final a PDF.

    Parámetros:
    -----------
    md_path : Path
        Ruta del archivo Markdown generado por el pipeline.
    pdf_path : Path
        Ruta destino donde se escribirá el PDF.

    Retorna:
    --------
    Path
        Ruta final del PDF generado.

    Lanza:
    ------
    RuntimeError si ocurre un fallo en dependencias o renderizado.
    """
    # Import dinámico para evitar dependencia obligatoria
    # si el módulo no es utilizado en tiempo de ejecución
    try:
        import markdown as md_lib
        from weasyprint import HTML, CSS
    except ImportError as e:
        raise RuntimeError(
            f"Dependencia faltante: {e}. "
            "Ejecuta: pip install markdown weasyprint"
        )

    if not md_path.exists():
        raise FileNotFoundError(f"Archivo Markdown no encontrado: {md_path}")

    logger.info(f"Convirtiendo {md_path.name} → PDF")

    # Lectura completa del archivo Markdown en UTF-8
    md_content = md_path.read_text(encoding="utf-8")

    # Conversión Markdown → HTML con extensiones necesarias
    # tables: tablas comparativas financieras
    # fenced_code: bloques de código
    # toc: tabla de contenidos
    # nl2br: saltos de línea explícitos
    # md_in_html: permite procesar Markdown dentro de divs HTML
    html_body = md_lib.markdown(
        md_content,
        extensions=["tables", "fenced_code", "toc", "nl2br", "md_in_html"],
    )

    # Embebido de imágenes locales para evitar dependencias externas
    html_body = _embed_images(html_body, md_path.parent)

    # Aplicación de formato especial a sección de bibliografía
    html_body = _wrap_bibliography(html_body)

    # Construcción del documento HTML completo con CSS inline
    full_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Reporte de Evaluación Crediticia</title>
    <style>{_PDF_CSS}</style>
</head>
<body>
    {html_body}
</body>
</html>"""

    # Renderizado final HTML → PDF utilizando motor WeasyPrint
    try:
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        HTML(string=full_html, base_url=str(md_path.parent)).write_pdf(
            str(pdf_path),
            stylesheets=[CSS(string=_PDF_CSS)],
        )
        logger.info(f"PDF generado: {pdf_path}")
        return pdf_path

    except Exception as e:
        raise RuntimeError(f"WeasyPrint falló al generar PDF: {e}") from e


def _embed_images(html: str, base_dir: Path) -> str:
    """
    Convierte rutas de imágenes locales en data URIs base64.

    Motivación:
    -----------
    Cuando el HTML se renderiza desde un string, WeasyPrint puede
    no resolver correctamente rutas relativas. Embebiendo las imágenes
    se garantiza portabilidad y consistencia del PDF.

    Solo procesa imágenes locales (no http/https/data).
    """
    # Expresión regular que captura etiquetas <img> y su atributo src
    img_pattern = re.compile(
        r'<img([^>]*?)src=["\']([^"\']+)["\']([^>]*?)/?>', re.IGNORECASE
    )

    def replace_img(match):
        before = match.group(1)
        src    = match.group(2)
        after  = match.group(3)

        # Ignorar imágenes externas o ya embebidas
        if src.startswith(("http://", "https://", "data:")):
            return match.group(0)

        img_path = (base_dir / src).resolve()
        if not img_path.exists():
            logger.warning(f"Imagen no encontrada: {img_path}")
            return match.group(0)

        suffix   = img_path.suffix.lower().lstrip(".")
        mime     = f"image/{'jpeg' if suffix == 'jpg' else suffix}"
        b64_data = base64.b64encode(img_path.read_bytes()).decode("utf-8")
        data_uri = f"data:{mime};base64,{b64_data}"

        return f'<img{before}src="{data_uri}"{after}/>'

    return img_pattern.sub(replace_img, html)


def _wrap_bibliography(html: str) -> str:
    """
    Encapsula la sección de Bibliografía dentro de un contenedor
    con clase CSS específica para aplicar sangría francesa.

    Esto replica el formato académico estándar (APA/Chicago-like)
    mediante CSS (padding-left + text-indent negativo).
    """
    # Busca h2 con contenido "Bibliografía" (con o sin tilde)
    pattern = re.compile(
        r'(<h2[^>]*>Bibliograf[íi]a</h2>)(.*?)$',
        re.DOTALL | re.IGNORECASE,
    )

    def wrap(m):
        return m.group(1) + '<div class="bibliography">' + m.group(2) + "</div>"

    return pattern.sub(wrap, html)