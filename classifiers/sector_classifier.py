"""
sector_classifier.py
--------------------
Responsabilidad única: determinar qué versión del Z-score aplica
a una empresa dada su sector e industria.

Regla de negocio:
  - Z  original (1968): empresas manufactureras públicas
  - Z' (1983):          empresas manufactureras privadas
  - Z''(1995):          empresas no manufactureras, servicios, mercados emergentes

Fuente de clasificación sectorial: Yahoo Finance sector/industry tags.

DISEÑO DE LA LÓGICA:
    El enfoque correcto es opt-in para manufactura, no opt-out para servicios.
    Sectores como "Consumer Cyclical" o "Technology" son heterogéneos — mezclan
    manufactura real (autopartes, hardware) con servicios puros (travel, software).
    Por eso la regla correcta es:
        1. Si la industria específica está en manufactura → Z original
        2. En cualquier otro caso → Z'' (default conservador)
    Esto evita clasificar incorrectamente empresas de servicios que caen en
    sectores nominalmente "industriales".
"""

from __future__ import annotations

from enum import Enum


class ZScoreModel(str, Enum):
    """
    Enumeración de las variantes del modelo Z-score de Altman.

    ORIGINAL (1968):
        Diseñado para empresas manufactureras que cotizan en bolsa.
        Incluye el ratio Ventas/Activos Totales.

    PRIME (1983):
        Adaptación para empresas manufactureras privadas.
        Ajusta coeficientes para estructura de capital distinta.

    DOUBLE_PRIME (1995):
        Versión universal para empresas no manufactureras,
        servicios y mercados emergentes.
        Elimina el ratio de Ventas/Activos.
    """
    ORIGINAL     = "Z_ORIGINAL"       # Altman 1968 — manufactureras públicas
    PRIME        = "Z_PRIME"          # Altman 1983 — manufactureras privadas
    DOUBLE_PRIME = "Z_DOUBLE_PRIME"   # Altman 1995 — no manufactureras / servicios


# Conjunto explícito de industrias consideradas manufactureras.
# El enfoque es "opt-in": solo si la industria aparece aquí
# se permite aplicar Z original o Z'.

# ---------------------------------------------------------------------------
# Industrias explícitamente manufactureras — opt-in para Z original
# Fuente: clasificación SIC (Standard Industrial Classification) adaptada
# a los tags de Yahoo Finance. Solo se incluyen industrias con producción
# física intensiva de bienes, no distribución ni servicios relacionados.
# ---------------------------------------------------------------------------

_MANUFACTURING_INDUSTRIES = {
    # Basic Materials
    "Aluminum",
    "Chemicals",
    "Specialty Chemicals",
    "Agricultural Inputs",
    "Building Materials",
    "Paper & Paper Products",
    "Packaging & Containers",
    "Steel",
    "Copper",
    "Gold",
    "Silver",
    "Other Precious Metals & Mining",
    "Coking Coal",
    "Coal",

    # Consumer Cyclical — solo los que manufacturan físicamente
    "Auto Manufacturers",
    "Auto Parts",
    "Textile Manufacturing",
    "Apparel Manufacturing",
    "Furnishings, Fixtures & Appliances",
    "Residential Construction",

    # Consumer Defensive — manufactura de bienes de consumo
    "Beverages—Brewers",
    "Beverages—Non-Alcoholic",
    "Beverages—Wineries & Distilleries",
    "Beverages - Brewers",
    "Beverages - Non-Alcoholic",
    "Beverages - Wineries & Distilleries",
    "Confectioners",
    "Farm Products",
    "Food Distribution",
    "Packaged Foods",
    "Tobacco",
    "Household & Personal Products",

    # Energy — extracción y refinamiento físico
    "Oil & Gas Integrated",
    "Oil & Gas E&P",
    "Oil & Gas Refining & Marketing",
    "Oil & Gas Midstream",
    "Oil & Gas Equipment & Services",
    "Oil & Gas Drilling",
    "Thermal Coal",
    "Uranium",

    # Healthcare — manufactura farmacéutica y dispositivos
    "Drug Manufacturers—General",
    "Drug Manufacturers—Specialty & Generic",
    "Drug Manufacturers - General",
    "Drug Manufacturers - Specialty & Generic",
    "Medical Devices",
    "Medical Instruments & Supplies",
    "Diagnostics & Research",

    # Industrials — manufactura y producción industrial
    "Aerospace & Defense",
    "Agricultural Machinery",
    "Construction Machinery",
    "Farm & Heavy Construction Machinery",
    "Industrial Machinery",
    "Metal Fabrication",
    "Pollution & Treatment Controls",
    "Tools & Accessories",
    "Electrical Equipment & Parts",
    "Specialty Industrial Machinery",

    # Technology — hardware físico únicamente
    "Consumer Electronics",
    "Electronic Components",
    "Electronics & Computer Distribution",
    "Semiconductors",
    "Semiconductor Equipment & Materials",
    "Computer Hardware",
    "Scientific & Technical Instruments",

    # Utilities — generación física de energía
    "Utilities—Regulated Electric",
    "Utilities—Regulated Gas",
    "Utilities—Regulated Water",
    "Utilities—Diversified",
    "Utilities—Independent Power Producers",
    "Utilities - Regulated Electric",
    "Utilities - Regulated Gas",
    "Utilities - Regulated Water",
    "Utilities - Diversified",
    "Utilities - Independent Power Producers",
}


class SectorClassifier:
    """
    Clasificador responsable de determinar qué versión del
    Z-score debe aplicarse a una empresa según su industria.

    Principio metodológico:
    ------------------------
    La clasificación sectorial de Yahoo Finance es heterogénea.
    Por ello, la decisión no se basa en el sector general,
    sino en la industria específica.

    Estrategia conservadora:
        - Si la industria está explícitamente catalogada como manufactura
          → Z original (pública) o Z' (privada).
        - En cualquier otro caso → Z'' (modelo universal).

    Esto minimiza errores de clasificación en empresas de servicios
    dentro de sectores mixtos (ej. Technology, Consumer Cyclical).
    """

    def classify(
        self,
        sector: str,
        industry: str,
        is_public: bool = True,
    ) -> ZScoreModel:
        # Normalización defensiva de strings provenientes de APIs externas
        sector   = sector.strip()   if sector   else "Unknown"
        industry = industry.strip() if industry else "Unknown"

        # Regla central: únicamente industrias explícitas califican
        # como manufactureras bajo el modelo original
        if industry in _MANUFACTURING_INDUSTRIES:
            return ZScoreModel.ORIGINAL if is_public else ZScoreModel.PRIME

        # Default conservador: aplicar Z'' para cualquier otro caso
        return ZScoreModel.DOUBLE_PRIME

    def get_model_description(self, model: ZScoreModel) -> str:
        """
        Retorna una descripción textual del modelo Z-score seleccionado.

        Utilizado principalmente para:
            - Reportes técnicos
            - Visualización en frontend
            - Justificación metodológica
        """
        descriptions = {
            ZScoreModel.ORIGINAL: (
                "Z-score original de Altman (1968). "
                "Diseñado para empresas manufactureras que cotizan en bolsa."
            ),
            ZScoreModel.PRIME: (
                "Z'-score de Altman (1983). "
                "Adaptación para empresas manufactureras privadas."
            ),
            ZScoreModel.DOUBLE_PRIME: (
                "Z''-score de Altman (1995). "
                "Versión universal para empresas no manufactureras, de servicios "
                "y mercados emergentes. Elimina el ratio de ventas/activos."
            ),
        }
        return descriptions[model]