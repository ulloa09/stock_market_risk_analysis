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
    ORIGINAL     = "Z_ORIGINAL"       # Altman 1968 — manufactureras públicas
    PRIME        = "Z_PRIME"          # Altman 1983 — manufactureras privadas
    DOUBLE_PRIME = "Z_DOUBLE_PRIME"   # Altman 1995 — no manufactureras / servicios


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
    Determina el modelo Z-score apropiado para una empresa.

    Lógica (opt-in para manufactura):
        1. Si la industria está en _MANUFACTURING_INDUSTRIES → Z original (pública)
        2. En cualquier otro caso → Z'' (default conservador y universal)

    Esta lógica es más robusta que filtrar por sector porque los sectores de
    Yahoo Finance son heterogéneos. "Consumer Cyclical" incluye tanto
    Auto Manufacturers (manufactura real) como Travel Services (servicio puro).
    Solo la industria específica permite distinguirlos correctamente.
    """

    def classify(
        self,
        sector: str,
        industry: str,
        is_public: bool = True,
    ) -> ZScoreModel:
        sector   = sector.strip()   if sector   else "Unknown"
        industry = industry.strip() if industry else "Unknown"

        # Regla única: opt-in a manufactura por industria específica
        if industry in _MANUFACTURING_INDUSTRIES:
            return ZScoreModel.ORIGINAL if is_public else ZScoreModel.PRIME

        # Default: Z'' — cubre servicios, tech, finanzas, retail, travel, etc.
        return ZScoreModel.DOUBLE_PRIME

    def get_model_description(self, model: ZScoreModel) -> str:
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