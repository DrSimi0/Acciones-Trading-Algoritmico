"""Gestión de portafolio multiactivo, asignación de capital y contabilidad diaria."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from config.settings import LeverageConfig, RiskConfig

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
    exit_reason: str  # 'TAKE_PROFIT', 'STOP_LOSS', 'STOP_LOSS_GAP', 'TIME_STOP', 'MARGIN_CALL'
    days_held: int
    gross_pnl_usd: float
    net_pnl_usd: float
    return_pct: float
    total_commission_usd: float
    total_slippage_usd: float
    total_cost_usd: float


class PortfolioManager:
    """Gestiona el efectivo, deuda de margen, posiciones y control de riesgo dinámico."""

    def __init__(
        self,
        risk_config: Optional[RiskConfig] = None,
        leverage_config: Optional[LeverageConfig] = None,
    ):
        self.risk_cfg = risk_config or RiskConfig()
        self.leverage_cfg = leverage_config or LeverageConfig()
        self.cash: float = self.risk_cfg.initial_capital_usd
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[TradeRecord] = []
        self.equity_peak: float = self.cash
        self.current_drawdown: float = 0.0
        self.is_paused: bool = False
        self.total_margin_interest_paid: float = 0.0

    def get_portfolio_value(self, current_prices: Dict[str, float]) -> float:
        """Calcula el valor neto del portafolio (efectivo/deuda + valor de mercado de posiciones)."""
        pos_val = 0.0
        for ticker, pos in self.positions.items():
            price = current_prices.get(ticker, pos.nominal_entry_price)
            pos_val += pos.shares * price
        return self.cash + pos_val

    def compute_trade_expectancy_stats(self) -> Dict[str, float]:
        """Calcula estadísticas sobre el promedio de cada trade para dimensionamiento dinámico (Kelly)."""
        if len(self.trade_history) < self.leverage_cfg.min_trade_history_for_kelly:
            return {"expectancy_usd": 0.0, "win_rate": 0.5, "payoff_ratio": 1.0, "kelly_f": 0.0}

        pnls = [t.net_pnl_usd for t in self.trade_history]
        wins = [p for p in pnls if p > 0]
        losses = [abs(p) for p in pnls if p < 0]

        win_rate = len(wins) / len(pnls)
        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(np.mean(losses)) if losses else 1.0

        payoff_ratio = (avg_win / avg_loss) if avg_loss > 0 else 1.0
        expectancy_usd = float(np.mean(pnls))

        # Criterio de Kelly: f* = (W * (R + 1) - 1) / R
        if payoff_ratio > 0:
            kelly_f = (win_rate * (payoff_ratio + 1.0) - 1.0) / payoff_ratio
        else:
            kelly_f = 0.0

        return {
            "expectancy_usd": expectancy_usd,
            "win_rate": float(win_rate),
            "payoff_ratio": float(payoff_ratio),
            "kelly_f": float(max(0.0, kelly_f)),
        }

    def update_daily_equity(self, current_date: pd.Timestamp, current_prices: Dict[str, float]) -> Dict[str, float]:
        """Actualiza el equity, deduce interés de margen nocturno si aplica y revisa mantenimiento."""
        # Deducción de intereses de margen si hay saldo deudor nocturno (cash < 0)
        daily_interest = 0.0
        if self.leverage_cfg.enabled and self.cash < 0.0:
            debt = abs(self.cash)
            daily_interest = debt * (self.leverage_cfg.margin_interest_rate_annual / 360.0)
            self.cash -= daily_interest
            self.total_margin_interest_paid += daily_interest

        total_equity = self.get_portfolio_value(current_prices)
        if total_equity > self.equity_peak:
            self.equity_peak = total_equity

        if self.equity_peak > 0:
            self.current_drawdown = (self.equity_peak - total_equity) / self.equity_peak
        else:
            self.current_drawdown = 0.0

        # Disyuntor de riesgo: pausar si supera el umbral de drawdown
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
            "daily_margin_interest": daily_interest,
            "total_margin_interest_paid": self.total_margin_interest_paid,
            "is_paused": self.is_paused,
        }

    def can_open_position(self, ticker: str, current_equity: float, current_gross_pos_val: float) -> bool:
        """Comprueba límites de concurrencia y capacidad de apalancamiento restante."""
        if self.is_paused or current_equity <= 0.0:
            return False
        if ticker in self.positions:
            return False
        if len(self.positions) >= self.risk_cfg.max_concurrent_positions:
            return False

        max_allowed_gross = current_equity * self.risk_cfg.max_gross_exposure_pct
        if current_gross_pos_val >= max_allowed_gross:
            return False

        return True

    def calculate_position_size(
        self,
        entry_price: float,
        stop_price: float,
        current_equity: float,
        current_gross_pos_val: float,
    ) -> int:
        """Calcula tamaño dinámico tomando en cuenta la expectativa/promedio de trades y apalancamiento."""
        stop_distance = entry_price - stop_price
        if stop_distance <= 0 or current_equity <= 0 or entry_price <= 0:
            return 0

        # 1. Determinar porcentaje de riesgo dinámico según promedio de trades (Kelly)
        risk_pct = self.risk_cfg.risk_per_trade_pct
        if self.leverage_cfg.enabled and self.leverage_cfg.use_expectancy_kelly_sizing:
            stats = self.compute_trade_expectancy_stats()
            kelly_f = stats["kelly_f"]
            if stats["expectancy_usd"] > 0 and kelly_f > 0:
                # Escalar agresivamente usando Half-Kelly
                scaled_risk = self.leverage_cfg.base_risk_pct * (1.0 + self.leverage_cfg.kelly_fraction * kelly_f)
                risk_pct = float(np.clip(scaled_risk, self.leverage_cfg.base_risk_pct, self.leverage_cfg.max_risk_pct))
            elif len(self.trade_history) >= self.leverage_cfg.min_trade_history_for_kelly and stats["expectancy_usd"] <= 0:
                # Expectativa negativa o nula: reducir riesgo a la mitad para preservar capital
                risk_pct = self.leverage_cfg.base_risk_pct * 0.50

        risk_usd = current_equity * risk_pct
        shares = int(np.floor(risk_usd / stop_distance))
        if shares <= 0:
            return 0

        # 2. Capacidad de compra considerando margen disponible
        if self.leverage_cfg.enabled:
            max_allowed_gross = current_equity * self.risk_cfg.max_gross_exposure_pct
            remaining_purchasing_power = max(0.0, max_allowed_gross - current_gross_pos_val)
            if shares * entry_price > remaining_purchasing_power:
                shares = int(np.floor(remaining_purchasing_power / entry_price))
        else:
            nominal_cost = shares * entry_price
            if nominal_cost > self.cash:
                shares = int(np.floor(self.cash / entry_price))

        # Límite por posición individual (para mantener diversificación en 5 posiciones)
        max_single_position_notional = current_equity * (self.risk_cfg.max_gross_exposure_pct / self.risk_cfg.max_concurrent_positions)
        if shares * entry_price > max_single_position_notional:
            shares = int(np.floor(max_single_position_notional / entry_price))

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
