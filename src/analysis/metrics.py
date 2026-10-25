"""Cálculo riguroso de métricas de portafolio y corrección por comparaciones múltiples (DSR)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from scipy.stats import norm

from src.backtest.engine import BacktestResult

logger = logging.getLogger(__name__)


def compute_deflated_sharpe_ratio(
    observed_sharpe: float,
    all_trial_sharpes: List[float],
    sample_length: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Calcula el Deflated Sharpe Ratio (DSR, Bailey & López de Prado, 2014).
    
    Ajusta el ratio de Sharpe observado considerando el número de pruebas en la grilla (data mining / multiple testing),
    la varianza de los resultados probados, la no-normalidad de los retornos (asimetría y curtosis) y el tamaño muestral.
    
    Returns:
        Valor p / probabilidad acumulada [0.0, 1.0]. Un DSR > 0.95 indica significancia estadística al 95%.
    """
    n_trials = len(all_trial_sharpes)
    if n_trials <= 1 or sample_length <= 2:
        return 0.5

    # Varianza entre los Sharpes probados
    var_sharpe = float(np.var(all_trial_sharpes, ddof=1))
    std_sharpe = np.sqrt(var_sharpe) if var_sharpe > 1e-12 else 0.0

    if std_sharpe == 0.0:
        expected_max_sharpe = 0.0
    else:
        # Constante de Euler-Mascheroni
        euler_mascheroni = 0.5772156649
        # Aproximación del valor esperado máximo de N variables normales
        expected_max_sharpe = std_sharpe * (
            (1.0 - euler_mascheroni) * norm.ppf(1.0 - 1.0 / n_trials)
            + euler_mascheroni * norm.ppf(1.0 - 1.0 / (n_trials * np.e))
        )

    # Varianza asintótica de la estimación del Sharpe ratio (Mertens, 2002)
    # V(SR) = (1 - skew * SR + (kurt - 1)/4 * SR^2) / (T - 1)
    denom_var = 1.0 - (skewness * observed_sharpe) + ((kurtosis - 1.0) / 4.0) * (observed_sharpe**2)
    denom_var = max(1e-6, denom_var)
    std_sr_estimator = np.sqrt(denom_var / max(1, sample_length - 1))

    if std_sr_estimator <= 1e-12:
        return 0.5

    # Estadístico z
    z_stat = (observed_sharpe - expected_max_sharpe) / std_sr_estimator
    dsr_pvalue = float(norm.cdf(z_stat))
    return float(np.clip(dsr_pvalue, 0.0, 1.0))


def compute_portfolio_metrics(
    result: BacktestResult,
    annualization_factor: float = 252.0,
) -> Dict[str, Any]:
    """Calcula todas las métricas de rendimiento y riesgo a nivel de portafolio y por operación."""
    equity_curve = result.equity_curve
    trades = result.trades
    n_trades = len(trades)

    if equity_curve.empty:
        return {
            "n_days": 0,
            "n_trades": 0,
            "total_net_pnl_usd": 0.0,
            "total_return_pct": 0.0,
            "annualized_return_pct": 0.0,
            "max_drawdown_usd": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_annualized": 0.0,
            "sortino_annualized": 0.0,
            "profit_factor": 0.0,
            "win_rate": 0.0,
            "expectancy_usd": 0.0,
            "total_commission_usd": 0.0,
            "total_slippage_usd": 0.0,
            "total_costs_usd": 0.0,
            "worst_trade_pnl_usd": 0.0,
            "best_trade_pnl_usd": 0.0,
            "fraction_positive_years": 0.0,
            "yearly_pnl_usd": {},
        }

    n_days = len(equity_curve)
    init_cap = float(equity_curve["total_equity"].iloc[0])
    final_cap = float(equity_curve["total_equity"].iloc[-1])
    total_net_pnl = final_cap - init_cap
    total_ret_pct = (final_cap / init_cap) - 1.0 if init_cap > 0 else 0.0

    years = n_days / annualization_factor if n_days > 0 else 1.0
    cagr = ((final_cap / init_cap) ** (1.0 / years) - 1.0) if (init_cap > 0 and final_cap > 0 and years > 0) else 0.0

    # Retornos diarios del portafolio
    daily_rets = equity_curve["daily_return"].values
    mean_ret = float(np.mean(daily_rets))
    std_ret = float(np.std(daily_rets, ddof=1)) if n_days > 1 else 0.0

    # Sharpe ratio anualizado convencional
    if std_ret > 1e-12:
        sharpe = float((mean_ret / std_ret) * np.sqrt(annualization_factor))
    else:
        sharpe = 0.0

    # Sortino ratio anualizado
    downside = daily_rets[daily_rets < 0]
    if len(downside) > 1:
        downside_std = float(np.sqrt(np.mean(downside**2)))
        sortino = float((mean_ret / downside_std) * np.sqrt(annualization_factor)) if downside_std > 1e-12 else 0.0
    else:
        sortino = 0.0

    # Drawdown máximo
    max_dd_pct = float(equity_curve["drawdown_pct"].max()) if "drawdown_pct" in equity_curve.columns else 0.0
    cum_eq = equity_curve["total_equity"].values
    peak_eq = np.maximum.accumulate(cum_eq)
    dd_usd = peak_eq - cum_eq
    max_dd_usd = float(np.max(dd_usd)) if len(dd_usd) > 0 else 0.0

    # Métricas de operaciones individuales
    if n_trades > 0:
        trades_df = result.trades_df
        net_pnls = trades_df["net_pnl_usd"].values
        wins = net_pnls > 0
        win_rate = float(np.mean(wins))
        expectancy_usd = float(np.mean(net_pnls))
        expectancy_pct = float(np.mean(trades_df["return_pct"].values))

        pos_sum = float(np.sum(net_pnls[net_pnls > 0]))
        neg_sum = float(np.abs(np.sum(net_pnls[net_pnls < 0])))
        profit_factor = (pos_sum / neg_sum) if neg_sum > 0 else (np.inf if pos_sum > 0 else 0.0)

        total_commission = float(trades_df["total_commission_usd"].sum())
        total_slippage = float(trades_df["total_slippage_usd"].sum())
        total_costs = float(trades_df["total_cost_usd"].sum())

        worst_trade_pnl = float(np.min(net_pnls))
        best_trade_pnl = float(np.max(net_pnls))
        worst_trade_ret = float(trades_df["return_pct"].min())
    else:
        win_rate = 0.0
        expectancy_usd = 0.0
        expectancy_pct = 0.0
        profit_factor = 0.0
        total_commission = 0.0
        total_slippage = 0.0
        total_costs = 0.0
        worst_trade_pnl = 0.0
        best_trade_pnl = 0.0
        worst_trade_ret = 0.0

    # Desglose anual
    if "date" in equity_curve.columns:
        dates = pd.to_datetime(equity_curve["date"])
    else:
        dates = pd.date_range("2010-01-01", periods=n_days, freq="D")

    eq_series = pd.Series(equity_curve["total_equity"].values, index=dates)
    yearly_eq = eq_series.resample("YE").last()
    yearly_prev = yearly_eq.shift(1).fillna(init_cap)
    yearly_rets = (yearly_eq / yearly_prev) - 1.0

    pos_years = int((yearly_rets > 0).sum())
    n_years = len(yearly_rets)
    fraction_pos_years = float(pos_years / n_years) if n_years > 0 else 0.0
    yearly_dict = {str(k.year): float(v) for k, v in yearly_rets.items()}

    return {
        "n_days": n_days,
        "n_trades": n_trades,
        "initial_capital_usd": init_cap,
        "final_capital_usd": final_cap,
        "total_net_pnl_usd": total_net_pnl,
        "total_return_pct": total_ret_pct,
        "cagr_pct": cagr,
        "max_drawdown_usd": max_dd_usd,
        "max_drawdown_pct": max_dd_pct,
        "sharpe_annualized": sharpe,
        "sortino_annualized": sortino,
        "profit_factor": profit_factor,
        "win_rate": win_rate,
        "expectancy_usd_per_trade": expectancy_usd,
        "expectancy_pct_per_trade": expectancy_pct,
        "total_commission_usd": total_commission,
        "total_slippage_usd": total_slippage,
        "total_costs_usd": total_costs,
        "worst_trade_pnl_usd": worst_trade_pnl,
        "worst_trade_return_pct": worst_trade_ret,
        "best_trade_pnl_usd": best_trade_pnl,
        "fraction_positive_years": fraction_pos_years,
        "yearly_returns": yearly_dict,
    }
