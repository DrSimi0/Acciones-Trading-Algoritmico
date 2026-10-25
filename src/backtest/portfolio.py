"""Gestión de portafolio multiactivo, asignación de capital y contabilidad diaria."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from config.settings import RiskConfig

logger = logging.getLogger(__name__)


@dataclass
class Position:
    ticker: str
    shares: int
    entry_date: pd.Timestamp
    nominal_entry_price: float
    effective_entry_price: float
    stop_price: float
    target_price: float
    event_date: pd.Timestamp
    drop_magnitude: float
    days_held: int = 0
    entry_commission: float = 0.0
    entry_slippage: float = 0.0


@dataclass(frozen=True)
class TradeRecord:
    ticker: str
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    shares: int
    nominal_entry_price: float
    effective_entry_price: float
    nominal_exit_price: float
    effective_exit_price: float
    exit_reason: str  # 'TAKE_PROFIT', 'STOP_LOSS', 'STOP_LOSS_GAP', 'TIME_STOP'
    days_held: int
    gross_pnl_usd: float
    net_pnl_usd: float
    return_pct: float
    total_commission_usd: float
    total_slippage_usd: float
    total_cost_usd: float


class PortfolioManager:
    """Gestiona el efectivo, las posiciones abiertas y el control de riesgo global."""

    def __init__(self, risk_config: Optional[RiskConfig] = None):
        self.risk_cfg = risk_config or RiskConfig()
        self.cash: float = self.risk_cfg.initial_capital_usd
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[TradeRecord] = []
        self.equity_peak: float = self.cash
        self.current_drawdown: float = 0.0
        self.is_paused: bool = False

    def get_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        """Calcula el valor total del portafolio (efectivo + valor de mercado de posiciones)."""
        pos_val = 0.0
        for ticker, pos in self.positions.items():
            price = current_prices.get(ticker, pos.nominal_entry_price)
            pos_val += pos.shares * price
        return self.cash + pos_val

    def update_daily_equity(self, current_date: pd.Timestamp, current_prices: Dict[str, float]) -> Dict[str, float]:
        """Actualiza el equity al cierre del día y evalúa el drawdown acumulado."""
        total_equity = self.get_portfolio_value(current_prices)
        if total_equity > self.equity_peak:
            self.equity_peak = total_equity

        if self.equity_peak > 0:
            self.current_drawdown = (self.equity_peak - total_equity) / self.equity_peak
        else:
            self.current_drawdown = 0.0

        # Disyuntor de riesgo: pausar si supera el 15% de drawdown
        if self.current_drawdown >= self.risk_cfg.drawdown_circuit_breaker_pct:
            self.is_paused = True

        gross_pos_val = sum(pos.shares * current_prices.get(t, pos.nominal_entry_price) for t, pos in self.positions.items())
        gross_exposure_pct = (gross_pos_val / total_equity) if total_equity > 0 else 0.0

        return {
            "date": current_date,
            "cash": self.cash,
            "positions_value": gross_pos_val,
            "total_equity": total_equity,
            "gross_exposure_pct": gross_exposure_pct,
            "drawdown_pct": self.current_drawdown,
            "open_positions": len(self.positions),
            "is_paused": self.is_paused,
        }

    def can_open_position(self, ticker: str) -> bool:
        """Comprueba si se cumplen los límites de riesgo para abrir una nueva posición."""
        if self.is_paused:
            return False
        if ticker in self.positions:
            return False
        if len(self.positions) >= self.risk_cfg.max_concurrent_positions:
            return False
        return True

    def calculate_position_size(
        self,
        entry_price: float,
        stop_price: float,
        current_equity: float,
    ) -> int:
        """Calcula el número de acciones a comprar según el riesgo por operación (0.5% - 1%).
        
        Formula:
        Riesgo USD = Equity * risk_per_trade_pct
        Distancia al stop = entry_price - stop_price
        Acciones = Riesgo USD / Distancia al stop
        Ajustado por el efectivo disponible y el límite de exposición bruta.
        """
        stop_distance = entry_price - stop_price
        if stop_distance <= 0:
            return 0

        risk_usd = current_equity * self.risk_cfg.risk_per_trade_pct
        shares = int(np.floor(risk_usd / stop_distance))

        if shares <= 0:
            return 0

        # Límite por efectivo disponible
        nominal_cost = shares * entry_price
        if nominal_cost > self.cash:
            shares = int(np.floor(self.cash / entry_price))

        # Límite de exposición máxima del portafolio (100% bruto)
        max_position_cost = current_equity * (self.risk_cfg.max_gross_exposure_pct / self.risk_cfg.max_concurrent_positions)
        if shares * entry_price > max_position_cost:
            shares = int(np.floor(max_position_cost / entry_price))

        return max(0, shares)

    def open_position(
        self,
        ticker: str,
        shares: int,
        entry_date: pd.Timestamp,
        nominal_entry_price: float,
        effective_entry_price: float,
        stop_price: float,
        target_price: float,
        event_date: pd.Timestamp,
        drop_magnitude: float,
        entry_commission: float,
        entry_slippage: float,
    ) -> None:
        """Registra la apertura de posición y descuenta el desembolso de efectivo."""
        total_outflow = (shares * effective_entry_price) + entry_commission
        self.cash -= total_outflow
        self.positions[ticker] = Position(
            ticker=ticker,
            shares=shares,
            entry_date=entry_date,
            nominal_entry_price=nominal_entry_price,
            effective_entry_price=effective_entry_price,
            stop_price=stop_price,
            target_price=target_price,
            event_date=event_date,
            drop_magnitude=drop_magnitude,
            days_held=0,
            entry_commission=entry_commission,
            entry_slippage=entry_slippage,
        )

    def close_position(
        self,
        ticker: str,
        exit_date: pd.Timestamp,
        nominal_exit_price: float,
        effective_exit_price: float,
        exit_reason: str,
        exit_commission: float,
        exit_slippage: float,
    ) -> TradeRecord:
        """Cierra una posición abierta, actualiza el efectivo y crea el registro de trade."""
        pos = self.positions.pop(ticker)
        shares = pos.shares

        total_inflow = (shares * effective_exit_price) - exit_commission
        self.cash += total_inflow

        gross_pnl = (nominal_exit_price - pos.nominal_entry_price) * shares
        total_comm = pos.entry_commission + exit_commission
        total_slip = pos.entry_slippage + exit_slippage
        total_costs = total_comm + total_slip
        net_pnl = (effective_exit_price - pos.effective_entry_price) * shares - total_comm

        ret_pct = ((effective_exit_price / pos.effective_entry_price) - 1.0) if pos.effective_entry_price > 0 else 0.0

        trade = TradeRecord(
            ticker=ticker,
            entry_date=pos.entry_date,
            exit_date=exit_date,
            shares=shares,
            nominal_entry_price=pos.nominal_entry_price,
            effective_entry_price=pos.effective_entry_price,
            nominal_exit_price=nominal_exit_price,
            effective_exit_price=effective_exit_price,
            exit_reason=exit_reason,
            days_held=pos.days_held,
            gross_pnl_usd=float(gross_pnl),
            net_pnl_usd=float(net_pnl),
            return_pct=float(ret_pct),
            total_commission_usd=float(total_comm),
            total_slippage_usd=float(total_slip),
            total_cost_usd=float(total_costs),
        )
        self.trade_history.append(trade)
        return trade
