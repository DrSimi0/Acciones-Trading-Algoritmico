"""Detector cuantitativo de eventos de caídas abruptas e idiosincráticas."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import List, Optional
import numpy as np
import pandas as pd

from config.settings import EventFilterConfig, UniverseConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventCandidate:
    ticker: str
    event_date: pd.Timestamp
    close_prev: float
    close_event: float
    high_event: float
    low_event: float
    drop_pct: float
    spy_drop_pct: float
    beta_spy: float
    idiosyncratic_drop_pct: float
    volume_event: float
    avg_vol20: float
    volume_ratio: float
    adv20_usd: float
    atr14: float
    midpoint: float


class EventDetector:
    """Detecta caídas diarias anormales e idiosincráticas con alto volumen."""

    def __init__(
        self,
        event_config: Optional[EventFilterConfig] = None,
        universe_config: Optional[UniverseConfig] = None,
    ):
        self.event_cfg = event_config or EventFilterConfig()
        self.univ_cfg = universe_config or UniverseConfig()

    def detect_events(
        self,
        ticker: str,
        df: pd.DataFrame,
        drop_pct_threshold: Optional[float] = None,
    ) -> List[EventCandidate]:
        """Escanea una serie temporal enriquecida para identificar días de evento (t).
        
        Criterios obligatorios:
        1. Caída cierre a cierre <= -X (donde X en [0.10, 0.25]).
        2. Idiosincrático: SPY no cae > 2% ese día (SPY return > -0.02).
        3. Caída ajustada por beta <= -X.
        4. Volumen del día >= 3x promedio de 20 días.
        5. Filtros de universo: Precio de cierre anterior > $5 y ADV20 > $20M.
        """
        threshold = drop_pct_threshold if drop_pct_threshold is not None else self.event_cfg.min_drop_pct
        candidates: List[EventCandidate] = []

        if len(df) < 2:
            return candidates

        df_sorted = df.copy()
        if "date" in df_sorted.columns:
            df_sorted["date"] = pd.to_datetime(df_sorted["date"])
            df_sorted = df_sorted.sort_values("date").reset_index(drop=True)
        else:
            df_sorted.index = pd.to_datetime(df_sorted.index)
            df_sorted = df_sorted.sort_index()

        n = len(df_sorted)
        dates = pd.to_datetime(df_sorted["date"] if "date" in df_sorted.columns else df_sorted.index).values
        closes = df_sorted["close"].values
        highs = df_sorted["high"].values
        lows = df_sorted["low"].values
        volumes = df_sorted["volume"].values
        daily_returns = df_sorted["daily_return"].values
        spy_returns = df_sorted["spy_return"].values if "spy_return" in df_sorted.columns else np.zeros(n)
        idio_returns = df_sorted["idiosyncratic_return"].values if "idiosyncratic_return" in df_sorted.columns else daily_returns
        vol_ratios = df_sorted["vol_ratio"].values if "vol_ratio" in df_sorted.columns else np.zeros(n)
        adv20s = df_sorted["adv20_usd"].values if "adv20_usd" in df_sorted.columns else np.full(n, 1e9)
        betas = df_sorted["beta_spy"].values if "beta_spy" in df_sorted.columns else np.ones(n)
        atr14s = df_sorted["atr14"].values if "atr14" in df_sorted.columns else (highs - lows)
        midpoints = df_sorted["midpoint"].values if "midpoint" in df_sorted.columns else (highs + lows) / 2.0
        avg_vol20s = df_sorted["avg_vol20"].values if "avg_vol20" in df_sorted.columns else volumes

        for i in range(1, n):
            drop_pct = daily_returns[i]
            if np.isnan(drop_pct) or drop_pct > -threshold:
                continue

            spy_ret = spy_returns[i]
            if np.isnan(spy_ret) or spy_ret < -self.event_cfg.max_spy_drop_pct:
                continue

            idio_ret = idio_returns[i]
            if np.isnan(idio_ret) or idio_ret > -threshold:
                continue

            v_ratio = vol_ratios[i]
            if np.isnan(v_ratio) or v_ratio < self.event_cfg.min_volume_mult:
                continue

            prev_close = closes[i - 1]
            if prev_close < self.univ_cfg.min_price:
                continue

            adv = adv20s[i]
            if np.isnan(adv) or adv < self.univ_cfg.min_adv20_usd:
                continue

            cand = EventCandidate(
                ticker=ticker.upper(),
                event_date=pd.to_datetime(dates[i]),
                close_prev=float(prev_close),
                close_event=float(closes[i]),
                high_event=float(highs[i]),
                low_event=float(lows[i]),
                drop_pct=float(drop_pct),
                spy_drop_pct=float(spy_ret),
                beta_spy=float(betas[i]),
                idiosyncratic_drop_pct=float(idio_ret),
                volume_event=float(volumes[i]),
                avg_vol20=float(avg_vol20s[i]),
                volume_ratio=float(v_ratio),
                adv20_usd=float(adv),
                atr14=float(atr14s[i]),
                midpoint=float(midpoints[i]),
            )
            candidates.append(cand)

        return candidates
