# Stock Market Risk Analysis — Z-Score & Modelo de Merton

> Motor cuantitativo de riesgo crediticio que evalúa la probabilidad de insolvencia corporativa combinando el Z-Score de Altman (1968/1983/1995) con el Modelo Estructural de Merton (1974), ejecutado desde una interfaz web local con generación automática de reportes en PDF.

**Autor:** Mauricio Martínez Ulloa  
**Diagrama de arquitectura:** [Ver arquitectura del sistema](https://ulloa09.github.io/stock_market_risk_analysis/)
**Acceso al reporte ejecutivo en formato DOCX (Exclusivo para comunidad ITESO):**
[Ver reporte ejecutivo]
(https://iteso01-my.sharepoint.com/:w:/g/personal/mauricio_martinezu_iteso_mx/IQBRM82ZCPLZQonGqP_lUsEVARAc8oejKg9iqF9KI6HlSg0?e=PRFUOm)
---

## Tabla de Contenidos

- [Descripción general](#descripción-general)
- [Modelos](#modelos)
- [Arquitectura](#arquitectura)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Uso](#uso)
- [Resultados y salidas](#resultados-y-salidas)
- [Limitaciones](#limitaciones)
- [Aviso legal](#aviso-legal)

---

## Descripción general

Esta herramienta ejecuta un pipeline completo de análisis de riesgo crediticio sobre empresas que cotizan en bolsa, usando únicamente su símbolo de ticker de Yahoo Finance como entrada. Descarga automáticamente los estados financieros, clasifica cada empresa por sector para seleccionar la variante correcta del Z-Score de Altman, ejecuta ambos modelos y produce una decisión crediticia consolidada por ticker.

Todo el proceso corre localmente en tu máquina a través de una interfaz web en el navegador — sin nube, sin API keys, sin suscripciones de datos de pago.

**Recomendado:** 5–6 tickers por ejecución para rendimiento óptimo y mejor calidad del reporte.  
**Máximo:** 20 tickers por ejecución (sujeto a disponibilidad de datos y restricciones de visualización — ver [Limitaciones](#limitaciones)).

---

## Modelos

### Altman Z-Score

El modelo de análisis discriminante lineal de Edward Altman predice la probabilidad de quiebra a partir de cinco razones financieras contables (X1–X5). La variante aplicada depende del sector de la empresa, detectado automáticamente desde Yahoo Finance:

| Variante | Año | Aplicación |
|---|---|---|
| Z original | 1968 | Manufactureras que cotizan en bolsa |
| Z' | 1983 | Empresas privadas |
| Z'' | 1995 | No manufactureras / empresas de servicios |

**Fórmula Z'':**  
`Z'' = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4`

| Zona | Umbral Z'' |
|---|---|
| Segura | > 2.60 |
| Gris | 1.10 – 2.60 |
| Distress | < 1.10 |

Razones utilizadas: Capital de Trabajo/Activos, Utilidades Retenidas/Activos, EBIT/Activos, Capital Contable/Pasivo Total.

### Modelo de Merton (1974)

El modelo estructural de Robert Merton trata al capital contable como una opción de compra sobre los activos de la empresa. Deriva el valor de los activos (V_A) y su volatilidad (σ_A) a partir de datos de mercado observables, y calcula:

**Distancia al Default:**  
`DD = [ln(V_A / D) + (r − σ²/2)·T] / (σ·√T)`

**Probabilidad de Default:**  
`PD = N(−DD)`

Donde D = pasivo total, r = tasa libre de riesgo (Bono del Tesoro a 10 años, `^TNX`), T = 1 año, y σ_A es la desviación estándar anualizada de los log-retornos.

### Lógica de decisión consolidada

| Decisión | Condición |
|---|---|
| ✅ Aprobada | Altman en Zona Segura Y Merton PD < 1% |
| ⚠️ Zona Gris | Algún modelo en Zona Gris, ninguno en Distress |
| ❌ Rechazada | Altman en Distress O Merton PD > 5% |
| ⛔ Incalculable | Datos financieros insuficientes para ejecutar los modelos |

---

## Arquitectura

El proyecto está construido con **principios de POO** y **diseño SOLID** en capas claramente separadas:

```
ui/                    → Frontend de página única (SPA)
api/
  main.py              → App FastAPI, CORS, archivos estáticos
  routes/
    analyze.py         → POST /api/analyze, GET /api/results/{job_id}
    download.py        → GET /download/pdf, GET /download/md
  services/
    job_manager.py     → Ciclo de vida del job en memoria (queued → running → done | error)
    pdf_converter.py   → MD → HTML → imágenes base64 → WeasyPrint → PDF
  schemas.py           → Contratos I/O con Pydantic
data/
  fetcher.py           → Descargador yfinance con caché CSV
  cache.py             → Gestión de caché
classifiers/
  sector_classifier.py → Detección de sector + selección de variante Z-Score
models/
  altman_zscore.py     → Clase AltmanZScore
  merton.py            → Clase MertonModel
evaluation/
  credit_evaluator.py  → CreditEvaluator — consolida ambos modelos
visualization/         → 5 gráficas matplotlib (PNG)
reporting/
  report_generator.py  → Reporte Markdown con tablas, colores y bibliografía
outputs/               → Artefactos del job (gráficas, reportes, CSVs)
```

Diagrama interactivo completo: [https://ulloa09.github.io/stock_market_risk_analysis/](https://ulloa09.github.io/stock_market_risk_analysis/)

---

## Requisitos

- Python **3.10 o superior**
- pip
- Conexión a internet (para descargar datos de Yahoo Finance en la primera ejecución; las siguientes usan caché CSV local)

**Dependencias Python** (instaladas vía `requirements.txt`):

```
fastapi
uvicorn[standard]
yfinance
pandas
numpy
scipy
matplotlib
markdown
weasyprint
pydantic
```

> **Dependencias del sistema para WeasyPrint** — necesarias para generar el PDF:
>
> | Sistema operativo | Comando |
> |---|---|
> | Ubuntu / Debian | `sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info` |
> | macOS (Homebrew) | `brew install pango cairo libffi gdk-pixbuf` |
> | Windows | Instalar el [runtime GTK3](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases) — descargar y ejecutar el instalador `.exe` más reciente |

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/ulloa09/stock_market_risk_analysis.git
cd stock_market_risk_analysis
```

### 2. Crear y activar un entorno virtual

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows:**
```cmd
python -m venv venv
venv\Scripts\activate
```

### 3. Instalar dependencias del sistema para WeasyPrint

Seguir la tabla de la sección [Requisitos](#requisitos) según tu sistema operativo antes de continuar.

### 4. Instalar dependencias Python

```bash
pip install -r requirements.txt
```

### 5. Iniciar el servidor

```bash
python run_api.py
```

La API quedará disponible en `http://localhost:8000`.

### 6. Abrir la interfaz web

Abrir el navegador y navegar a:

```
http://localhost:8000
```

---

## Uso

1. Ingresar entre 1 y 20 símbolos de ticker en el campo de texto (ej. `AAPL, MSFT, JPM, TSLA, KO`).
2. Hacer clic en **Ejecutar Análisis**.
3. La interfaz consulta el estado del job automáticamente. Esperar a que el pipeline complete — el tiempo de ejecución escala con el número de tickers y la disponibilidad de datos.
4. Revisar la tabla de resultados y las gráficas directamente en el navegador.
5. Descargar el reporte PDF generado.

**Tamaño de lote recomendado:** 5–6 tickers por ejecución.

**Formato de ticker:** Símbolos estándar de Yahoo Finance (ej. `AAPL`, `MSFT`, `BRK-B`). Tickers no estadounidenses pueden requerir el sufijo de la bolsa (ej. `BIMBOA.MX`, `AMXL.MX`).

---

## Resultados y salidas

### Tabla de resultados

La interfaz muestra una tabla resumen por cada ticker analizado con los siguientes campos:

| Columna | Descripción |
|---|---|
| Ticker | Símbolo de la empresa |
| Altman Z-Score | Puntaje calculado con badge de zona (Segura / Gris / Distress) |
| Merton DD | Distancia al Default |
| Merton PD | Probabilidad de Default (%) |
| Decisión | Decisión crediticia consolidada (Aprobada / Zona Gris / Rechazada / Incalculable) |

Los tickers se agrupan por resultado de decisión.

### Gráficas

Se generan cinco gráficas por ejecución:

- **Z-Score (variante original)** — gráfica de barras de puntajes Z vs. umbrales de zona
- **Z-Score (variante Z'')** — igual que la anterior para clasificación no manufacturera
- **Merton — Distancia al Default** — DD por empresa
- **Merton — Probabilidad de Default** — PD (%) por empresa
- **Mapa de riesgo combinado** — mapa de calor cruzando ambos modelos

### Reporte PDF

Se genera automáticamente un `credit_report.pdf` descargable (~19 páginas para 5 activos, formato A4/Carta). Contiene:

- Descripción metodológica del Z-Score de Altman y el Modelo de Merton
- Resultados e interpretación por empresa
- Tabla comparativa consolidada (Z-Score, Merton DD, Merton PD, Decisión)
- Las 5 gráficas embebidas
- Advertencias de datos (ej. historial insuficiente, capital de trabajo incompleto)
- Bibliografía

El reporte también se genera como `credit_report.md` y se guarda dentro de `outputs/jobs/{uuid}/reports`para posible procesamiento adicional.

---

## Limitaciones

| Restricción | Detalle |
|---|---|
| Disponibilidad de datos | Yahoo Finance puede devolver estados financieros incompletos o faltantes para algunos tickers, especialmente empresas fuera de EE.UU. o de baja capitalización. Estos se marcan como `Incalculable`. |
| Precisión de σ_A | La volatilidad del Modelo de Merton se calcula con log-retornos. Si hay menos de 5 años de datos de precios disponibles, se genera una advertencia y la estimación es menos confiable. |
| Lote > 6 tickers | Ejecuciones con 7–20 tickers pueden enfrentar tasas de descarga más lentas en Yahoo Finance, mayor tiempo de procesamiento y gráficas más densas y difíciles de leer. |
| Lote > 20 tickers | No soportado. El esquema Pydantic valida y rechaza solicitudes con más de 20 tickers. |
| Generación de PDF | WeasyPrint requiere librerías nativas del sistema (ver Requisitos). Si no se instalan, falla únicamente la generación del PDF sin afectar los resultados en la interfaz web. |
| Caché | Los datos se almacenan en CSV por ticker en `outputs/`. Para forzar una descarga nueva, eliminar los archivos de caché correspondientes o pasar `force_refresh=True` vía la API. |

---

## Aviso legal

Esta herramienta es únicamente para **fines educativos y de investigación**. No constituye asesoría financiera. Los resultados de los modelos dependen completamente de la calidad y completitud de los datos obtenidos desde Yahoo Finance. Consultar siempre a un profesional financiero calificado antes de tomar decisiones de préstamo o inversión.

---
*Desarrollado con FastAPI · yfinance · WeasyPrint · matplotlib · Pydantic · Principios SOLID y POO*
