"""
pdf_converter.py
----------------
Convierte el reporte Markdown generado por ReportGenerator a PDF.

Pipeline de conversión:
    1. Lee el archivo .md
    2. Convierte a HTML con la librería `markdown` (extensión extra: md_in_html
       para renderizar divs con contenido Markdown dentro)
    3. Resuelve rutas de imágenes relativas → base64 embebido en el HTML
       (necesario para que WeasyPrint encuentre las imágenes sin servidor)
    4. Aplica CSS de estilo profesional inline
    5. Renderiza el HTML a PDF con WeasyPrint

Por qué WeasyPrint sobre pdfkit/wkhtmltopdf:
    - No requiere binarios externos instalados en el sistema
    - Maneja CSS moderno correctamente
    - Embebe imágenes base64 sin problemas
    - Output consistente cross-platform

Clases CSS disponibles para usar en el Markdown (via HTML inline):
    .decision-aprobar      — texto verde, negrita (APROBADO)
    .decision-rechazar     — texto rojo, negrita (RECHAZADO)
    .decision-zona-gris    — texto amarillo/ámbar, negrita (ZONA GRIS)
    .decision-incalculable — texto gris, negrita
    .label-advertencia     — badge amarillo pequeño (ADVERTENCIA)
    .table-wide            — div wrapper que permite tabla con font-size reducido
                             y word-break agresivo para que no se corte en A4
"""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ── CSS ────────────────────────────────────────────────────────────────────
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
    Convierte un archivo Markdown a PDF.

    Parámetros:
        md_path:  Path del archivo .md generado por ReportGenerator
        pdf_path: Path donde se guardará el .pdf resultante

    Retorna:
        pdf_path si la conversión fue exitosa.

    Lanza:
        RuntimeError si la conversión falla.
    """
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

    # 1. Leer Markdown
    md_content = md_path.read_text(encoding="utf-8")

    # 2. Markdown → HTML
    # md_in_html permite que divs con clase (e.g. <div class="table-wide">)
    # procesen su contenido interno como Markdown.
    html_body = md_lib.markdown(
        md_content,
        extensions=["tables", "fenced_code", "toc", "nl2br", "md_in_html"],
    )

    # 3. Resolver imágenes locales → base64
    html_body = _embed_images(html_body, md_path.parent)

    # 4. Envolver la sección de bibliografía en .bibliography para sangría francesa.
    # La sección empieza en <h2>Bibliografía</h2> y va hasta el fin del documento.
    html_body = _wrap_bibliography(html_body)

    # 5. HTML completo con CSS
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

    # 6. WeasyPrint: HTML → PDF
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
    Reemplaza rutas de imágenes relativas en el HTML por data URIs base64.

    El Markdown generado por ReportGenerator usa rutas relativas como:
        ../plots/decision_summary.png

    WeasyPrint necesita rutas absolutas o base64 para resolverlas correctamente
    cuando el HTML se pasa como string (sin base_url confiable).
    """
    img_pattern = re.compile(
        r'<img([^>]*?)src=["\']([^"\']+)["\']([^>]*?)/?>', re.IGNORECASE
    )

    def replace_img(match):
        before = match.group(1)
        src    = match.group(2)
        after  = match.group(3)

        # Solo procesar rutas locales (no http/https/data)
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
    Envuelve la sección de bibliografía en un div.bibliography para aplicar
    la sangría francesa (padding-left: 2em; text-indent: -2em) vía CSS.

    Detecta el h2 con texto "Bibliografía" y envuelve toodo lo que sigue
    hasta el fin del body en <div class="bibliography">...</div>.
    """
    # Busca h2 con contenido "Bibliografía" (con o sin tilde)
    pattern = re.compile(
        r'(<h2[^>]*>Bibliograf[íi]a</h2>)(.*?)$',
        re.DOTALL | re.IGNORECASE,
    )

    def wrap(m):
        return m.group(1) + '<div class="bibliography">' + m.group(2) + "</div>"

    return pattern.sub(wrap, html)