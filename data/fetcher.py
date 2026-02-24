"""
fetcher.py
----------
Responsabilidad: descargar datos financieros de Yahoo Finance y coordinar
con el caché local en CSV.

Flujo por ticker:
    1. Verificar si el ticker existe en los CSVs locales
    2. Si existe, consultar a Yahoo el año fiscal más reciente disponible
    3. Si el caché está actualizado  → retornar desde CSV
    4. Si hay nuevo reporte o no existe → descargar, guardar en CSV, retornar
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import yfinance as yf
from data.cache import CacheManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interfaz abstracta del proveedor de datos
# ---------------------------------------------------------------------------

class FinancialDataProvider(ABC):
    """
    Interfaz abstracta para proveedores de datos financieros.

    Permite desacoplar la fuente de datos (Yahoo, API privada,
    base de datos institucional, etc.) del resto del sistema.

    Facilita testing mediante implementación mock.
    """

    @abstractmethod
    def get_income_statement(self, ticker: str) -> pd.DataFrame:
        ...

    @abstractmethod
    def get_balance_sheet(self, ticker: str) -> pd.DataFrame:
        ...

    @abstractmethod
    def get_cash_flow(self, ticker: str) -> pd.DataFrame:
        ...

    @abstractmethod
    def get_market_data(self, ticker: str) -> dict:
        ...

    @abstractmethod
    def get_risk_free_rate(self) -> float:
        ...

    @abstractmethod
    def get_latest_fiscal_year(self, ticker: str) -> Optional[str]:
        """
        Retorna la fecha del reporte anual más reciente disponible en la fuente,
        formato ISO-8601 string (e.g., '2024-09-30').
        Retorna None si no puede determinarse.
        """
        ...


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class CompanyFinancials:
    """
    Contenedor inmutable (dataclass) de información financiera anual.

    Incluye:
        - Estados financieros completos.
        - Métricas de mercado necesarias para Merton.
        - Metadata sectorial para selección del modelo Altman.

    No contiene lógica de cálculo financiero.
    """
    ticker: str
    sector: str
    industry: str
    company_name: str

    income_statement: pd.DataFrame = field(default_factory=pd.DataFrame)
    balance_sheet: pd.DataFrame    = field(default_factory=pd.DataFrame)
    cash_flow: pd.DataFrame        = field(default_factory=pd.DataFrame)

    market_cap: Optional[float]         = None
    shares_outstanding: Optional[float] = None
    current_price: Optional[float]      = None
    beta: Optional[float]               = None

    currency: str        = "USD"
    years_available: int = 0
    fetch_errors: list[str] = field(default_factory=list)

    def is_valid(self) -> bool:
        """
        Determina si existen datos mínimos para análisis.

        Requisito actual:
            - Balance sheet no vacío.
            - Al menos 1 año disponible.
        """
        return not self.balance_sheet.empty and self.years_available >= 1


# ---------------------------------------------------------------------------
# Implementación Yahoo Finance
# ---------------------------------------------------------------------------

class YahooFinanceProvider(FinancialDataProvider):
    """
    Implementación concreta de FinancialDataProvider
    utilizando la librería yfinance.

    Consideraciones:
        - Dependencia externa no garantizada.
        - Se limita el número de años descargados.
        - Se incluye fallback para tasa libre de riesgo.
    """

    _TNX_TICKER = "^TNX"

    def __init__(self, max_years: int = 10):
        self.max_years = max_years

    def get_latest_fiscal_year(self, ticker: str) -> Optional[str]:
        """
        Consulta ligera para detectar nuevo reporte anual.

        Solo descarga el balance sheet y extrae
        la fecha más reciente disponible.

        Optimiza llamadas evitando descargar
        los tres estados financieros completos.
        """
        try:
            bs = yf.Ticker(ticker).balance_sheet
            if bs is None or bs.empty:
                return None
            return str(bs.columns[0].date())
        except Exception as e:
            logger.warning(f"[{ticker}] No se pudo obtener último año fiscal: {e}")
            return None

    def get_income_statement(self, ticker: str) -> pd.DataFrame:
        return self._trim(yf.Ticker(ticker).financials)

    def get_balance_sheet(self, ticker: str) -> pd.DataFrame:
        return self._trim(yf.Ticker(ticker).balance_sheet)

    def get_cash_flow(self, ticker: str) -> pd.DataFrame:
        return self._trim(yf.Ticker(ticker).cashflow)

    def get_market_data(self, ticker: str) -> dict:
        info = yf.Ticker(ticker).info
        return {
            "market_cap":         info.get("marketCap"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "current_price":      info.get("currentPrice") or info.get("regularMarketPrice"),
            "beta":               info.get("beta"),
            "sector":             info.get("sector", "Unknown"),
            "industry":           info.get("industry", "Unknown"),
            "company_name":       info.get("longName", ticker),
            "currency":           info.get("currency", "USD"),
        }

    def get_risk_free_rate(self) -> float:
        try:
            hist = yf.Ticker(self._TNX_TICKER).history(period="5d")
            if hist.empty:
                raise ValueError("Sin datos ^TNX")
            rate = hist["Close"].iloc[-1] / 100.0
            logger.info(f"Risk-free rate (10Y Treasury): {rate:.4f}")
            return rate
        except Exception as e:
            logger.warning(f"No se pudo obtener 10Y Treasury: {e}. Usando fallback 4.5%")
            return 0.045

    def _trim(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Limita el DataFrame al número máximo de años configurado.

        Previene crecimiento innecesario en memoria
        y tamaño de almacenamiento.
        """
        if df is None or df.empty:
            return pd.DataFrame()
        return df.iloc[:, : self.max_years]


# ---------------------------------------------------------------------------
# Fetcher con caché CSV
# ---------------------------------------------------------------------------

class FinancialDataFetcher:
    """
    Orquestador de descarga y sincronización con caché CSV.

    Responsabilidades:
        - Decidir si descargar o usar caché.
        - Coordinar proveedor externo.
        - Persistir datos válidos.
        - Aislar errores de red o parsing.

    No implementa lógica de análisis financiero.
    """

    def __init__(
        self,
        provider: Optional[FinancialDataProvider] = None,
        data_dir: str = "data/",
    ):
        self._provider = provider or YahooFinanceProvider(max_years=10)
        self._cache = CacheManager(data_dir=data_dir)

    # ------------------------------------------------------------------
    # Público
    # ------------------------------------------------------------------

    def fetch(self, ticker: str, force_refresh: bool = False) -> CompanyFinancials:
        """
        Obtiene datos financieros de un ticker.

        Estrategia:
            1. Verificar existencia en caché.
            2. Consultar último FY remoto.
            3. Decidir si actualizar.
            4. Descargar solo si es necesario.
        """
        ticker = ticker.upper().strip()

        if not force_refresh and self._cache.is_cached(ticker):
            latest_fy = self._provider.get_latest_fiscal_year(ticker)
            if not self._cache.is_stale(ticker, latest_fy):
                logger.info(f"[{ticker}] CSV actualizado — sin descarga necesaria.")
                return self._cache.load(ticker)
            logger.info(f"[{ticker}] Nuevo reporte detectado, actualizando CSV.")

        return self._download_and_save(ticker)

    def fetch_multiple(
        self, tickers: list[str], force_refresh: bool = False
    ) -> dict[str, CompanyFinancials]:
        """
        Ejecuta fetch de forma independiente para múltiples tickers.

        No detiene ejecución ante fallos individuales.
        """
        return {t: self.fetch(t, force_refresh=force_refresh) for t in tickers}

    def get_risk_free_rate(self) -> float:
        return self._provider.get_risk_free_rate()

    def list_cached_tickers(self) -> list[str]:
        """Lista los tickers disponibles en los CSVs locales."""
        return self._cache.list_cached_tickers()

    # ------------------------------------------------------------------
    # Privado
    # ------------------------------------------------------------------

    def _download_and_save(self, ticker: str) -> CompanyFinancials:
        """
        Descarga todos los componentes financieros y los encapsula
        en CompanyFinancials.

        Si los datos mínimos no están disponibles,
        no se persisten en caché.
        """
        logger.info(f"[{ticker}] Descargando desde Yahoo Finance.")
        errors: list[str] = []

        market_data = self._safe_fetch("market_data",      ticker, self._provider.get_market_data,      errors, default={})
        balance     = self._safe_fetch("balance_sheet",    ticker, self._provider.get_balance_sheet,    errors, default=pd.DataFrame())
        income      = self._safe_fetch("income_statement", ticker, self._provider.get_income_statement, errors, default=pd.DataFrame())
        cf          = self._safe_fetch("cash_flow",        ticker, self._provider.get_cash_flow,        errors, default=pd.DataFrame())

        company = CompanyFinancials(
            ticker=ticker,
            company_name=market_data.get("company_name", ticker),
            sector=market_data.get("sector", "Unknown"),
            industry=market_data.get("industry", "Unknown"),
            currency=market_data.get("currency", "USD"),
            income_statement=income,
            balance_sheet=balance,
            cash_flow=cf,
            market_cap=market_data.get("market_cap"),
            shares_outstanding=market_data.get("shares_outstanding"),
            current_price=market_data.get("current_price"),
            beta=market_data.get("beta"),
            years_available=balance.shape[1] if not balance.empty else 0,
            fetch_errors=errors,
        )

        if company.is_valid():
            self._cache.save(company)
        else:
            logger.error(f"[{ticker}] Datos insuficientes — no se guardan en CSV.")

        return company

    @staticmethod
    def _safe_fetch(name: str, ticker: str, fn, errors: list, default):
        """
        Wrapper de ejecución segura para llamadas externas.

        Captura excepciones, registra el error
        y retorna valor por defecto sin interrumpir flujo.
        """
        try:
            return fn(ticker)
        except Exception as e:
            msg = f"{name}: {e}"
            errors.append(msg)
            logger.warning(f"[{ticker}] Error en {msg}")
            return default