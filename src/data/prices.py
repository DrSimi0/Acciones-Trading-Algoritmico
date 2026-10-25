"""Gestión y enriquecimiento de datos de precios con estricto aislamiento temporal."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from config.settings import DataSplitsConfig

logger = logging.getLogger(__name__)


def compute_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Calcula el Average True Range (ATR) de Wilder."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=period).mean()
    return atr


def compute_rolling_beta(
    stock_returns: pd.Series,
    market_returns: pd.Series,
    window: int = 60,
) -> pd.Series:
    """Calcula la beta móvil contra el índice de referencia (SPY).
    
    beta = Cov(R_i, R_m) / Var(R_m)
    """
    cov = stock_returns.rolling(window=window, min_periods=max(20, window // 2)).cov(market_returns)
    var = market_returns.rolling(window=window, min_periods=max(20, window // 2)).var()
    beta = cov / var
    # Para valores iniciales o varianza nula, usar beta = 1.0 como fallback neutral
    return beta.fillna(1.0)


class PriceDataManager:
    """Carga, valida y enriquece series de precios garantizando aislamiento temporal."""

    def __init__(self, splits_config: Optional[DataSplitsConfig] = None):
        self.splits = splits_config or DataSplitsConfig()

    def filter_by_split(
        self,
        df: pd.DataFrame,
        split_name: str,
        date_col: str = "date",
    ) -> pd.DataFrame:
        """Filtra el DataFrame según el bloque temporal requerido:
        - 'in_sample': [in_sample_start, in_sample_end]
        - 'validation': [validation_start, validation_end]
        - 'oos': [oos_start, oos_end] (lanza excepción si allow_oos_access es False)
        """
        if df.empty:
            return df

        if date_col in df.columns:
            dates = pd.to_datetime(df[date_col])
        elif isinstance(df.index, pd.DatetimeIndex):
            dates = df.index
        else:
            raise ValueError(f"Columna de fecha '{date_col}' no encontrada en el DataFrame.")

        if split_name == "in_sample":
            start = pd.to_datetime(self.splits.in_sample_start)
            end = pd.to_datetime(self.splits.in_sample_end)
            mask = (dates >= start) & (dates <= end)
            return df.loc[mask].copy()

        elif split_name == "validation":
            start = pd.to_datetime(self.splits.validation_start)
            end = pd.to_datetime(self.splits.validation_end)
            mask = (dates >= start) & (dates <= end)
            return df.loc[mask].copy()

        elif split_name == "oos":
            if not self.splits.allow_oos_access:
                raise PermissionError(
                    "VIOLACIÓN DE PROTOCOLO: El acceso al conjunto Out-of-Sample está estrictamente bloqueado "
                    "hasta completar y registrar la congelación de parámetros de la estrategia."
                )
            start = pd.to_datetime(self.splits.oos_start)
            end = pd.to_datetime(self.splits.oos_end)
            mask = (dates >= start) & (dates <= end)
            return df.loc[mask].copy()

        else:
            raise ValueError(f"Nombre de bloque desconocido: {split_name}. Use 'in_sample', 'validation' o 'oos'.")

    def enrich_stock_data(
        self,
        stock_df: pd.DataFrame,
        spy_df: pd.DataFrame,
        beta_lookback: int = 60,
    ) -> pd.DataFrame:
        """Calcula todas las métricas técnicas necesarias para la estrategia sobre datos diarios:
        - daily_return: caída de cierre a cierre (Close_t / Close_{t-1} - 1)
        - adv20_usd: volumen medio en dólares a 20 días
        - avg_vol20: volumen medio de acciones a 20 días
        - vol_ratio: volume_t / avg_vol20
        - atr14: Average True Range de 14 períodos
        - beta_spy: beta móvil de 60 días contra SPY
        - spy_return: retorno diario de SPY
        - idiosyncratic_return: daily_return - (beta_spy * spy_return)
        - midpoint: (high + low) / 2
        """
        df = stock_df.copy()
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
        else:
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()

        # Retorno diario de la acción
        df["daily_return"] = df["close"].pct_change()

        # Dollar volume y promedio móvil de 20 días
        dollar_vol = df["close"] * df["volume"]
        df["adv20_usd"] = dollar_vol.rolling(20, min_periods=5).mean()
        df["avg_vol20"] = df["volume"].rolling(20, min_periods=5).mean()
        df["vol_ratio"] = df["volume"] / df["avg_vol20"]

        # ATR 14
        df["atr14"] = compute_atr(df["high"], df["low"], df["close"], period=14)

        # Punto medio del rango diario
        df["midpoint"] = (df["high"] + df["low"]) / 2.0

        # Alinear con retornos de SPY para calcular beta e idiosyncratic return
        spy = spy_df.copy()
        if "date" in spy.columns:
            spy["date"] = pd.to_datetime(spy["date"])
            spy = spy.sort_values("date").set_index("date")
        elif not isinstance(spy.index, pd.DatetimeIndex):
            spy.index = pd.to_datetime(spy.index)

        spy["spy_return"] = spy["close"].pct_change()

        # Merge de spy_return
        if "date" in df.columns:
            merged = df.merge(spy[["spy_return"]], left_on="date", right_index=True, how="left")
            merged["spy_return"] = merged["spy_return"].fillna(0.0)
            merged["beta_spy"] = compute_rolling_beta(merged["daily_return"], merged["spy_return"], window=beta_lookback)
            merged["idiosyncratic_return"] = merged["daily_return"] - (merged["beta_spy"] * merged["spy_return"])
            return merged
        else:
            df["spy_return"] = spy["spy_return"].reindex(df.index).fillna(0.0)
            df["beta_spy"] = compute_rolling_beta(df["daily_return"], df["spy_return"], window=beta_lookback)
            df["idiosyncratic_return"] = df["daily_return"] - (df["beta_spy"] * df["spy_return"])
            return df
