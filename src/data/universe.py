"""Gestión del universo dinámico point-in-time sin sesgo de supervivencia."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set
import numpy as np
import pandas as pd

from config.settings import UniverseConfig

logger = logging.getLogger(__name__)


class PointInTimeUniverse:
    """Gestiona la composición histórica del universo de acciones elegibles.
    
    Asegura que en cada fecha `t` solo se utilicen acciones activas en esa fecha,
    incluyendo aquellas que posteriormente salieron de bolsa o quebraron,
    y que cumplan los filtros cuantitativos calculados con datos hasta `t`.
    """

    def __init__(
        self,
        config: Optional[UniverseConfig] = None,
        metadata_df: Optional[pd.DataFrame] = None,
    ):
        self.config = config or UniverseConfig()
        self.metadata = metadata_df if metadata_df is not None else pd.DataFrame()

    def filter_active_tickers_on_date(self, current_date: pd.Timestamp) -> Set[str]:
        """Devuelve los tickers que estaban cotizando activamente en `current_date`."""
        if self.metadata.empty or not self.config.point_in_time_enforced:
            return set()

        df = self.metadata
        mask = pd.Series(True, index=df.index)
        if "listing_date" in df.columns:
            mask &= pd.to_datetime(df["listing_date"]) <= current_date
        if "delisting_date" in df.columns:
            # Si no tiene fecha de desliste (NaT), sigue activa
            delist = pd.to_datetime(df["delisting_date"])
            mask &= delist.isna() | (delist >= current_date)

        return set(df.loc[mask, "ticker"].unique())

    def compute_daily_universe_mask(
        self,
        prices_df: pd.DataFrame,
        current_date: pd.Timestamp,
    ) -> pd.Series:
        """Determina la elegibilidad para cada acción en `current_date`.
        
        Criterios:
        1. Precio de cierre > min_price ($5).
        2. Volumen medio en dólares (ADV20) > min_adv20 ($20M).
        3. Capitalización bursátil > min_market_cap ($2B).
        4. Ticker activo según metadatos históricos (evita sesgo de supervivencia).
        """
        # Filtrar datos de la fecha específica
        if "date" in prices_df.columns:
            daily_data = prices_df[prices_df["date"] == current_date].copy()
        elif isinstance(prices_df.index, pd.DatetimeIndex):
            daily_data = prices_df.loc[prices_df.index == current_date].copy()
        else:
            daily_data = prices_df.copy()

        if daily_data.empty:
            return pd.Series(dtype=bool)

        # Regla 1: Precio > $5
        cond_price = daily_data["close"] > self.config.min_price

        # Regla 2: ADV20 en dólares > $20M
        if "adv20_usd" in daily_data.columns:
            cond_adv = daily_data["adv20_usd"] >= self.config.min_adv20_usd
        elif "dollar_volume" in daily_data.columns:
            cond_adv = daily_data["dollar_volume"] >= self.config.min_adv20_usd
        else:
            # Si no viene precalculado, estimar con close * volume
            cond_adv = (daily_data["close"] * daily_data["volume"]) >= self.config.min_adv20_usd

        # Regla 3: Capitalización > $2B
        if "market_cap" in daily_data.columns:
            cond_mcap = daily_data["market_cap"] >= self.config.min_market_cap_usd
        else:
            cond_mcap = pd.Series(True, index=daily_data.index)

        # Regla 4: Filtro de supervivencia
        active_tickers = self.filter_active_tickers_on_date(current_date)
        if active_tickers:
            cond_pit = daily_data["ticker"].isin(active_tickers)
        else:
            cond_pit = pd.Series(True, index=daily_data.index)

        eligible = cond_price & cond_adv & cond_mcap & cond_pit
        return eligible
