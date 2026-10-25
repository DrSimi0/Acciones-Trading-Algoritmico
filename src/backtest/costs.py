"""Modelo de costos para acciones de EE. UU. (comisiones y slippage dinámico con gaps)."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from config.settings import CostConfig


@dataclass(frozen=True)
class TradeCostResult:
    commission_usd: float
    slippage_usd: float
    total_cost_usd: float
    effective_fill_price: float


class EquityCostModel:
    """Calcula comisiones y deslizamiento realista (slippage) para acciones de EE. UU."""

    def __init__(self, config: CostConfig):
        self.config = config

    def calculate_commission(self, shares: int) -> float:
        """Comisión por acción con mínimo por orden."""
        if shares <= 0:
            return 0.0
        comm = shares * self.config.commission_per_share
        return max(comm, self.config.min_commission_usd)

    def calculate_slippage(
        self,
        nominal_price: float,
        shares: int,
        is_event_or_high_vol: bool = False,
        is_buy: bool = True,
    ) -> tuple[float, float]:
        """Calcula el deslizamiento en USD y el precio efectivo de ejecución.
        
        Para compras: fill_price = nominal_price * (1 + slippage_bps)
        Para ventas: fill_price = nominal_price * (1 - slippage_bps)
        """
        if shares <= 0 or nominal_price <= 0:
            return 0.0, nominal_price

        bps = self.config.slippage_bps_event if is_event_or_high_vol else self.config.slippage_bps_normal
        slippage_price_diff = nominal_price * bps
        slippage_usd = slippage_price_diff * shares

        effective_price = (nominal_price + slippage_price_diff) if is_buy else (nominal_price - slippage_price_diff)
        return float(slippage_usd), float(effective_price)

    def execute_order(
        self,
        nominal_price: float,
        shares: int,
        is_buy: bool,
        is_event_day: bool = False,
    ) -> TradeCostResult:
        """Ejecuta una orden registrando comisión y slippage."""
        comm = self.calculate_commission(shares)
        slip_usd, eff_price = self.calculate_slippage(
            nominal_price=nominal_price,
            shares=shares,
            is_event_or_high_vol=is_event_day,
            is_buy=is_buy,
        )
        return TradeCostResult(
            commission_usd=comm,
            slippage_usd=slip_usd,
            total_cost_usd=comm + slip_usd,
            effective_fill_price=eff_price,
        )

    @staticmethod
    def calculate_daily_margin_interest(
        borrowed_amount_usd: float,
        annual_rate: float = 0.065,
    ) -> float:
        """Calcula el costo diario por saldo deudor de margen (overnight margin interest).
        
        Formula: Deuda * (Tasa anual / 360 días bancarios).
        """
        if borrowed_amount_usd <= 0.0:
            return 0.0
        return float(borrowed_amount_usd * (annual_rate / 360.0))
