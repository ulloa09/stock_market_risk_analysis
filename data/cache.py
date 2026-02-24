"""
cache.py
--------
Responsabilidad única: persistir y recuperar datos financieros en CSV locales.

Estructura de archivos:
    data/
    ├── companies.csv       — metadata por ticker (sector, nombre, última descarga)
    ├── balance_sheet.csv   — long format: ticker, concept, date, value
    ├── income_stmt.csv     — igual
    ├── cash_flow.csv       — igual
    └── market_data.csv     — métricas de mercado por ticker

Por qué long-format:
    Un balance sheet tiene N conceptos × M años × K tickers.
    Aplanarlo en wide-format haría columnas dinámicas imposibles de mantener.
    Long-format es estable: siempre las mismas 4 columnas sin importar
    cuántos tickers o años se agreguen.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Nombres de archivos
_FILES = {
    "companies":     "companies.csv",
    "balance_sheet": "balance_sheet.csv",
    "income_stmt":   "income_stmt.csv",
    "cash_flow":     "cash_flow.csv",
    "market_data":   "market_data.csv",
}

# Columnas esperadas por archivo — para crear archivos vacíos con esquema correcto
_SCHEMAS = {
    "companies":     ["ticker", "company_name", "sector", "industry",
                      "currency", "last_fetched_at", "last_fiscal_year"],
    "balance_sheet": ["ticker", "concept", "date", "value"],
    "income_stmt":   ["ticker", "concept", "date", "value"],
    "cash_flow":     ["ticker", "concept", "date", "value"],
    "market_data":   ["ticker", "market_cap", "shares_outstanding",
                      "current_price", "beta", "fetched_at"],
}


class CacheManager:
    """
    Gestor de persistencia en CSV para datos financieros descargados.

    Principios de diseño:
    ---------------------
    1. Single Responsibility: únicamente maneja I/O local.
    2. Formato long estable para estados financieros.
    3. Estrategia upsert por ticker para evitar duplicados.

    No contiene lógica financiera ni validaciones de negocio.
    Actúa como capa de infraestructura entre el proveedor externo
    (Yahoo Finance) y el dominio del modelo (Altman/Merton).
    """

    def __init__(self, data_dir: str = "data/"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._init_files()

    # ------------------------------------------------------------------
    # Público
    # ------------------------------------------------------------------

    def is_cached(self, ticker: str) -> bool:
        """
        Verifica si el ticker existe en companies.csv.

        No valida vigencia ni integridad de datos,
        únicamente presencia en caché.
        """
        df = self._read("companies")
        return ticker in df["ticker"].values

    def is_stale(self, ticker: str, latest_fiscal_year: Optional[str]) -> bool:
        """
        Determina si el caché local está desactualizado.

        Criterio:
            latest_fiscal_year (fuente externa)
            > last_fiscal_year (almacenado en CSV)

        La comparación es lexicográfica porque se utiliza
        formato ISO-8601 (YYYY-MM-DD), que preserva orden temporal.
        """
        if not self.is_cached(ticker):
            return True
        if latest_fiscal_year is None:
            return False

        df = self._read("companies")
        row = df[df["ticker"] == ticker]
        cached_fy = row["last_fiscal_year"].iloc[0] if not row.empty else None

        if pd.isna(cached_fy) or cached_fy is None:
            return True

        # Comparación lexicográfica válida para fechas ISO-8601
        stale = str(latest_fiscal_year) > str(cached_fy)
        if stale:
            logger.info(f"[{ticker}] Nuevo reporte: {latest_fiscal_year} > {cached_fy}")
        return stale

    def save(self, company) -> None:
        """
        Persiste un objeto CompanyFinancials en los CSVs locales.

        Operación tipo upsert:
            - Elimina filas previas del ticker.
            - Inserta los datos más recientes.

        Se separan:
            - Metadata (companies.csv)
            - Estados financieros (long-format)
            - Métricas de mercado (market_data.csv)
        """
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        last_fy = None
        if not company.balance_sheet.empty:
            last_fy = str(company.balance_sheet.columns[0].date())

        # 1. companies.csv
        self._upsert_row(
            "companies",
            key_col="ticker",
            key_val=company.ticker,
            row={
                "ticker":           company.ticker,
                "company_name":     company.company_name,
                "sector":           company.sector,
                "industry":         company.industry,
                "currency":         company.currency,
                "last_fetched_at":  now,
                "last_fiscal_year": last_fy,
            },
        )

        # 2. Estados financieros
        for file_key, df in [
            ("balance_sheet", company.balance_sheet),
            ("income_stmt",   company.income_statement),
            ("cash_flow",     company.cash_flow),
        ]:
            if not df.empty:
                self._upsert_financial_df(file_key, company.ticker, df)

        # 3. market_data.csv
        self._upsert_row(
            "market_data",
            key_col="ticker",
            key_val=company.ticker,
            row={
                "ticker":             company.ticker,
                "market_cap":         company.market_cap,
                "shares_outstanding": company.shares_outstanding,
                "current_price":      company.current_price,
                "beta":               company.beta,
                "fetched_at":         now,
            },
        )

        logger.info(f"[{company.ticker}] Guardado en CSV. Último FY: {last_fy}")

    def load(self, ticker: str):
        """
        Reconstruye un objeto CompanyFinancials desde almacenamiento local.

        Proceso:
            1. Leer metadata.
            2. Reconstruir estados financieros (long → wide).
            3. Restaurar métricas de mercado.

        No realiza validaciones de consistencia externa.
        """
        from data.fetcher import CompanyFinancials

        if not self.is_cached(ticker):
            return None

        # Metadata
        companies_df = self._read("companies")
        meta = companies_df[companies_df["ticker"] == ticker].iloc[0]

        # Market data
        mkt_df = self._read("market_data")
        mkt_row = mkt_df[mkt_df["ticker"] == ticker]
        mkt = mkt_row.iloc[0] if not mkt_row.empty else None

        # Estados financieros
        bs  = self._load_financial_df("balance_sheet", ticker)
        inc = self._load_financial_df("income_stmt",   ticker)
        cf  = self._load_financial_df("cash_flow",     ticker)

        company = CompanyFinancials(
            ticker=ticker,
            company_name=meta["company_name"],
            sector=meta["sector"],
            industry=meta["industry"],
            currency=meta["currency"],
            balance_sheet=bs,
            income_statement=inc,
            cash_flow=cf,
            market_cap=float(mkt["market_cap"])          if mkt is not None and pd.notna(mkt["market_cap"])          else None,
            shares_outstanding=float(mkt["shares_outstanding"]) if mkt is not None and pd.notna(mkt["shares_outstanding"]) else None,
            current_price=float(mkt["current_price"])    if mkt is not None and pd.notna(mkt["current_price"])    else None,
            beta=float(mkt["beta"])                      if mkt is not None and pd.notna(mkt["beta"])              else None,
            years_available=bs.shape[1] if not bs.empty else 0,
        )

        logger.info(f"[{ticker}] Cargado desde CSV.")
        return company

    def list_cached_tickers(self) -> list[str]:
        df = self._read("companies")
        return sorted(df["ticker"].tolist())

    def get_latest_fiscal_year_cached(self, ticker: str) -> Optional[str]:
        if not self.is_cached(ticker):
            return None
        df = self._read("companies")
        row = df[df["ticker"] == ticker]
        val = row["last_fiscal_year"].iloc[0] if not row.empty else None
        return None if pd.isna(val) else str(val)

    # ------------------------------------------------------------------
    # Privado — I/O
    # ------------------------------------------------------------------

    def _path(self, key: str) -> Path:
        return self.data_dir / _FILES[key]

    def _init_files(self) -> None:
        """
        Inicializa los CSVs con su esquema base si no existen.

        Garantiza que la estructura de columnas sea estable
        incluso antes de la primera descarga.
        """
        for key, columns in _SCHEMAS.items():
            path = self._path(key)
            if not path.exists():
                pd.DataFrame(columns=columns).to_csv(path, index=False)
                logger.debug(f"Creado {path}")

    def _read(self, key: str) -> pd.DataFrame:
        """
        Lee un CSV y retorna DataFrame.

        Si el archivo está vacío o corrupto parcialmente,
        retorna DataFrame vacío con esquema esperado.
        """
        path = self._path(key)
        try:
            df = pd.read_csv(path)
            return df if not df.empty else pd.DataFrame(columns=_SCHEMAS[key])
        except pd.errors.EmptyDataError:
            return pd.DataFrame(columns=_SCHEMAS[key])

    def _write(self, key: str, df: pd.DataFrame) -> None:
        df.to_csv(self._path(key), index=False)

    def _upsert_row(self, key: str, key_col: str, key_val: str, row: dict) -> None:
        """
        Inserta o reemplaza una fila identificada por clave primaria lógica.

        Estrategia:
            1. Filtrar filas con misma key.
            2. Concatenar nueva fila.
            3. Persistir archivo completo.
        """
        df = self._read(key)
        # Eliminar fila existente si hay
        df = df[df[key_col] != key_val]
        new_row = pd.DataFrame([row])
        df = pd.concat([df, new_row], ignore_index=True)
        self._write(key, df)

    def _upsert_financial_df(
        self, key: str, ticker: str, df_wide: pd.DataFrame
    ) -> None:
        """
        Convierte un DataFrame wide (formato yfinance)
        a long-format y realiza upsert por ticker.

        Justificación:
            El long-format evita columnas dinámicas por fecha
            y mantiene el esquema estable en CSV.
        """
        # Leer existente y eliminar filas del ticker para reemplazar
        existing = self._read(key)
        existing = existing[existing["ticker"] != ticker]

        # Convertir wide → long
        rows = []
        for concept in df_wide.index:
            for col in df_wide.columns:
                value = df_wide.loc[concept, col]
                date_str = str(col.date()) if hasattr(col, "date") else str(col)
                val = float(value) if pd.notna(value) else None
                rows.append({
                    "ticker":  ticker,
                    "concept": str(concept),
                    "date":    date_str,
                    "value":   val,
                })

        new_rows = pd.DataFrame(rows, columns=_SCHEMAS[key])
        combined = pd.concat([existing, new_rows], ignore_index=True)
        self._write(key, combined)

    def _load_financial_df(self, key: str, ticker: str) -> pd.DataFrame:
        """
        Reconstruye un DataFrame wide desde long-format almacenado.

        Pasos:
            - Filtrar por ticker.
            - Pivot (concept × date).
            - Convertir columnas a Timestamp.
            - Ordenar cronológicamente descendente.
        """
        df = self._read(key)
        df_ticker = df[df["ticker"] == ticker].copy()

        if df_ticker.empty:
            return pd.DataFrame()

        # Pivot: filas=concept, columnas=date, valores=value
        df_wide = df_ticker.pivot(index="concept", columns="date", values="value")

        # Convertir columnas string → Timestamps (consistencia con yfinance)
        df_wide.columns = pd.to_datetime(df_wide.columns)
        # Ordenar de más reciente a más antiguo
        df_wide = df_wide.sort_index(axis=1, ascending=False)
        df_wide.index.name = None
        df_wide.columns.name = None

        return df_wide