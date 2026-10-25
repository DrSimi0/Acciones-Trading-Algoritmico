"""Configuración centralizada y tipada de la estrategia de Rebote tras Caída por Noticia."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set
import os


@dataclass(frozen=True)
class UniverseConfig:
    min_price: float = 5.0
    min_adv20_usd: float = 20_000_000.0  # 20 millones USD de volumen promedio diario
    min_market_cap_usd: float = 2_000_000_000.0  # 2 billones USD (2B USD)
    point_in_time_enforced: bool = True


@dataclass(frozen=True)
class EventFilterConfig:
    min_drop_pct: float = 0.10  # 10% de caída por defecto (evaluable en {10%, 15%, 20%, 25%})
    max_spy_drop_pct: float = 0.02  # Descartar si SPY cae > 2% ese día
    min_volume_mult: float = 3.0  # Volumen >= 3x el promedio de 20 días
    beta_lookback_days: int = 60  # Días para estimar beta contra SPY


@dataclass(frozen=True)
class NewsFilterConfig:
    enabled: bool = True
    permitted_keywords: tuple[str, ...] = (
        "earnings", "guidance", "quarterly results", "revenue miss", "sales miss",
        "profit miss", "downgrade", "price target cut", "weak outlook", "forecast cut",
        "margin compression", "product delay", "sector downgrade", "analyst cut"
    )
    excluded_keywords: tuple[str, ...] = (
        "bankruptcy", "chapter 11", "fraud", "accounting investigation", "sec investigation",
        "going concern", "delisting", "stock offering", "secondary offering", "dilution",
        "fda rejection", "clinical trial failure", "complete response letter",
        "merger terminated", "deal collapse", "doj probe", "restatement"
    )
    max_hours_before_open: float = 36.0  # Ventana temporal (noche anterior y día del evento)


@dataclass(frozen=True)
class EntryConfig:
    max_gap_down_additional_pct: float = 0.05  # Cancelar si t+1 abre > 5% por debajo del cierre de t
    require_midpoint_cross: bool = False  # Variante: abrir por encima de (High_t + Low_t)/2


@dataclass(frozen=True)
class ExitConfig:
    rebound_target_pct: float = 0.50  # 50% de recuperación de la caída de cierre a cierre (variante: 75%)
    stop_atr_mult: float = 1.5  # -1.5 x ATR(14)
    stop_max_loss_pct: float = 0.08  # Máximo -8%
    time_stop_days: int = 5  # Cierre del día 5 (variante: día 3)


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade_pct: float = 0.01  # 1% del capital por operación
    max_concurrent_positions: int = 5
    max_gross_exposure_pct: float = 1.0  # 100% de exposición máxima (sin apalancamiento)
    drawdown_circuit_breaker_pct: float = 0.15  # Pausa si drawdown acumulado > 15%
    initial_capital_usd: float = 100_000.0


@dataclass(frozen=True)
class CostConfig:
    commission_per_share: float = 0.005  # $0.005 por acción
    min_commission_usd: float = 1.00     # Mínimo $1 por orden
    slippage_bps_normal: float = 0.0010   # 10 puntos básicos (0.10%)
    slippage_bps_event: float = 0.0030    # 30 puntos básicos (0.30%) en día del evento / t+1


@dataclass(frozen=True)
class DataSplitsConfig:
    in_sample_start: str = "2010-01-01"
    in_sample_end: str = "2019-12-31"
    validation_start: str = "2020-01-01"
    validation_end: str = "2022-12-31"
    oos_start: str = "2023-01-01"
    oos_end: str = "2026-10-25"
    allow_oos_access: bool = False  # Guarda de protección: prohíbe cargar OOS hasta fase final


@dataclass
class StrategyConfig:
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    event: EventFilterConfig = field(default_factory=EventFilterConfig)
    news: NewsFilterConfig = field(default_factory=NewsFilterConfig)
    entry: EntryConfig = field(default_factory=EntryConfig)
    exit: ExitConfig = field(default_factory=ExitConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    splits: DataSplitsConfig = field(default_factory=DataSplitsConfig)
