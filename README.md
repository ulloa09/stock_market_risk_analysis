# Stock Market Risk Analysis

Herramienta de evaluación crediticia cuantitativa basada en **Altman Z-score** y **Modelo de Merton**.
Incluye API REST (FastAPI) e interfaz web con tema oscuro/claro.

---

## Requisitos previos

### 1. Python
- Python **3.10 o superior**

### 2. Dependencias de sistema (requeridas por WeasyPrint para generar PDFs)

WeasyPrint necesita librerías nativas del sistema operativo (Pango, GObject, Cairo).
**Estas no se instalan con pip** — deben instalarse con el gestor del SO.

#### macOS
```bash
brew install pango
```
> Si no tienes Homebrew: https://brew.sh

Después de instalar, agrega las librerías al path de Python. **Esto es necesario — sin este paso WeasyPrint no encuentra las librerías aunque estén instaladas.**

```bash
# Apple Silicon (M1/M2/M3)
echo 'export DYLD_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_LIBRARY_PATH"' >> ~/.zshrc
source ~/.zshrc

# Intel Mac
echo 'export DYLD_LIBRARY_PATH="/usr/local/lib:$DYLD_LIBRARY_PATH"' >> ~/.zshrc
source ~/.zshrc
```

Verifica que funciona:
```bash
python -c "from weasyprint import HTML; print('WeasyPrint OK')"
```

#### Ubuntu / Debian
```bash
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 libffi-dev shared-mime-info
```

#### Windows
Instala GTK3 runtime:
https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone <url-del-repo>
cd stock_market_risk_analysis

# 2. Crear entorno virtual (recomendado)
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# 3. Instalar dependencias Python
pip install -r requirements.txt
```

---

## Uso

### Interfaz web (recomendado)
```bash
python run_api.py
```
Abre http://localhost:8000 en tu navegador.

### CLI directo
```bash
python main.py --tickers AAPL MSFT TSLA
```

---

## Stack

| Capa | Tecnología |
|------|-----------|
| Backend | FastAPI + Uvicorn |
| Datos | yfinance (Yahoo Finance) |
| Modelos | Altman Z-score, Merton Model |
| Gráficas | Matplotlib (backend Agg) |
| PDF | WeasyPrint |
| Frontend | HTML + CSS + JS vanilla |

---

## Estructura

```
stock_market_risk_analysis/
├── main.py                  # Pipeline principal
├── run_api.py               # Entrada del servidor
├── requirements.txt         # Dependencias Python
├── api/                     # FastAPI — rutas y servicios
│   ├── main.py
│   ├── schemas.py
│   ├── routes/
│   └── services/
├── models/                  # Altman Z-score y Merton
├── evaluation/              # Evaluador y consolidación
├── data/                    # Descarga y caché de datos
├── visualization/           # Generación de gráficas
├── reporting/               # Generación de reporte MD
├── classifiers/             # Clasificador de sector
├── ui/                      # Frontend (index.html)
└── outputs/                 # Resultados generados (gitignored)
```