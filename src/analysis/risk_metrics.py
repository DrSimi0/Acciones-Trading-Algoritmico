"""Módulo unificado de Métricas de Riesgo Avanzadas para Portafolios Cuantitativos.
Implementa:
1. Max Drawdown en USD (max_drawdown_usd)
2. Max Drawdown Porcentual sobre capital inicial (max_drawdown_pct)
3. Duración máxima y media del Drawdown en días (drawdown_duration_days)
4. Peor Día Intradía / Pérdida Diaria Máxima (worst_day_usd)
5. Sharpe Ratio Diario Anualizado (sharpe_daily)
6. Ratio Calmar (calmar_ratio = CAGR / Max DD %)
7. Test de Permutación Monte Carlo de 10,000 iteraciones (p-value, z-score)
8. Deflated Sharpe Ratio (DSR de Bailey & López de Prado)
9. Intervalos de Confianza al 95% por Bootstrap de Bloques de 10 días (sharpe_ci95, pnl_ci95)
10. Sensibilidad al Deslizamiento y Fricción (slippage_sensitivity x1, x2, x3)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.stats import norm

from src.backtest.engine import BacktestResult

logger = logging.getLogger(__name__)


def compute_drawdown_metrics(
    equity_series: pd.Series,
    initial_capital: float = 100_000.0,
) -> Dict[str, float]:
    """Calcula Max Drawdown monetario, porcentual y duración en días."""
    if equity_series.empty:
        return {
            "max_drawdown_usd": 0.0,
            "max_drawdown_pct": 0.0,
            "max_drawdown_duration_days": 0,
            "avg_drawdown_duration_days": 0.0,
        }

    eq = equity_series.values
    peaks = np.maximum.accumulate(eq)
    dd_usd_arr = peaks - eq
    max_dd_usd = float(np.max(dd_usd_arr)) if len(dd_usd_arr) > 0 else 0.0

    # Drawdown porcentual sobre capital inicial fijo
    max_dd_pct = (max_dd_usd / initial_capital) * 100.0 if initial_capital > 0 else 0.0

    # Duración del drawdown (días continuos bajo el pico)
    in_dd = dd_usd_arr > 1e-4
    dd_durations: List[int] = []
    cur_dur = 0
    for val in in_dd:
        if val:
            cur_dur += 1
        else:
            if cur_dur > 0:
                dd_durations.append(cur_dur)
            cur_dur = 0
    if cur_dur > 0:
        dd_durations.append(cur_dur)

    max_dd_days = int(max(dd_durations)) if dd_durations else 0
    avg_dd_days = float(np.mean(dd_durations)) if dd_durations else 0.0

    return {
        "max_drawdown_usd": max_dd_usd,
        "max_drawdown_pct": max_dd_pct,
        "max_drawdown_duration_days": max_dd_days,
        "avg_drawdown_duration_days": avg_dd_days,
    }


def compute_daily_worst_and_sharpe(
    daily_pnl_series: pd.Series,
    initial_capital: float = 100_000.0,
    annualization_factor: float = 252.0,
) -> Dict[str, float]:
    """Calcula la máxima pérdida diaria (worst_day_usd) y el Sharpe Ratio diario anualizado."""
    if daily_pnl_series.empty:
        return {
            "worst_day_usd": 0.0,
            "best_day_usd": 0.0,
            "sharpe_daily": 0.0,
        }

    pnls = daily_pnl_series.values
    worst_day = float(np.min(pnls))
    best_day = float(np.max(pnls))

    daily_rets = pnls / initial_capital if initial_capital > 0 else np.zeros_like(pnls)
    mean_ret = float(np.mean(daily_rets))
    std_ret = float(np.std(daily_rets, ddof=1)) if len(daily_rets) > 1 else 0.0

    sharpe_daily = (mean_ret / std_ret * np.sqrt(annualization_factor)) if std_ret > 1e-9 else 0.0

    return {
        "worst_day_usd": worst_day,
        "best_day_usd": best_day,
        "sharpe_daily": sharpe_daily,
    }


def compute_calmar_ratio(
    cagr_pct: float,
    max_drawdown_pct: float,
) -> float:
    """Calcula el Calmar Ratio = CAGR % / Max Drawdown %."""
    if max_drawdown_pct <= 1e-6:
        return 0.0
    return float(cagr_pct / max_drawdown_pct)


def run_monte_carlo_permutation_test(
    trades_pnl: List[float],
    n_iterations: int = 10_000,
    random_seed: int = 42,
) -> Dict[str, Any]:
    """Test de permutación Monte Carlo de 10,000 iteraciones contrastando el PnL real contra combinaciones aleatorias.
    
    Evalúa la probabilidad (p-value) de que el PnL total acumulado sea producto del azar permutando los signos
    y órdenes de los retornos bajo la hipótesis nula de habilidad cero.
    """
    if not trades_pnl:
        return {"p_value": 1.0, "real_pnl": 0.0, "mean_rand": 0.0, "z_score": 0.0}

    real_pnl = float(np.sum(trades_pnl))
    n = len(trades_pnl)
    arr = np.asarray(trades_pnl, dtype=float)

    rng = np.random.default_rng(random_seed)
    random_totals = np.zeros(n_iterations)

    # Permutación con asignación aleatoria de signos (Rademacher / Coin-flip null hypothesis)
    for i in range(n_iterations):
        random_signs = rng.choice([-1.0, 1.0], size=n)
        random_totals[i] = np.sum(arr * random_signs)

    # p-value empírico: fracción de simulaciones aleatorias que igualan o superan el PnL real
    p_value = float(np.mean(random_totals >= real_pnl))
    mean_rand = float(np.mean(random_totals))
    std_rand = float(np.std(random_totals, ddof=1)) if len(random_totals) > 1 else 1.0
    z_score = float((real_pnl - mean_rand) / std_rand) if std_rand > 1e-9 else 0.0

    return {
        "real_pnl": real_pnl,
        "n_iterations": n_iterations,
        "p_value": p_value,
        "mean_rand": mean_rand,
        "std_rand": std_rand,
        "z_score": z_score,
        "is_statistically_significant_99": bool(p_value < 0.01),
        "is_statistically_significant_95": bool(p_value < 0.05),
    }


def run_block_bootstrap(
    daily_pnl_series: pd.Series,
    initial_capital: float = 100_000.0,
    block_size: int = 10,
    n_resamples: int = 2000,
    random_seed: int = 42,
) -> Dict[str, Tuple[float, float]]:
    """Calcula intervalos de confianza del 95% para Sharpe y PnL mediante Bootstrap de Bloques (10 días)."""
    if len(daily_pnl_series) < block_size * 2:
        return {
            "sharpe_ci95": (0.0, 0.0),
            "pnl_ci95": (0.0, 0.0),
        }

    vals = daily_pnl_series.values
    n = len(vals)
    n_blocks = int(np.ceil(n / block_size))

    # Construir todos los bloques continuos de tamaño 10 días
    all_blocks = [vals[i : i + block_size] for i in range(n - block_size + 1)]
    m = len(all_blocks)

    rng = np.random.default_rng(random_seed)
    boot_sharpes = np.zeros(n_resamples)
    boot_pnls = np.zeros(n_resamples)

    for r in range(n_resamples):
        rand_idx = rng.integers(0, m, size=n_blocks)
        sampled = np.concatenate([all_blocks[idx] for idx in rand_idx])[:n]

        sampled_rets = sampled / initial_capital
        m_r = np.mean(sampled_rets)
        s_r = np.std(sampled_rets, ddof=1)
        sh = (m_r / s_r * np.sqrt(252.0)) if s_r > 1e-9 else 0.0

        boot_sharpes[r] = sh
        boot_pnls[r] = np.sum(sampled)

    sh_low, sh_high = np.percentile(boot_sharpes, [2.5, 97.5])
    pnl_low, pnl_high = np.percentile(boot_pnls, [2.5, 97.5])

    return {
        "sharpe_ci95": (float(sh_low), float(sh_high)),
        "pnl_ci95": (float(pnl_low), float(pnl_high)),
    }


def compute_comprehensive_risk_profile(
    backtest_result: BacktestResult,
    initial_capital: float = 100_000.0,
    trials_sharpes: Optional[List[float]] = None,
    mc_iterations: int = 10_000,
    bootstrap_resamples: int = 2000,
) -> Dict[str, Any]:
    """Compila las 10 métricas de riesgo completas y detalladas."""
    equity_df = backtest_result.equity_curve
    trades_df = backtest_result.trades_df

    if equity_df.empty:
        return {}

    # Serie diaria de PnL y de Equity
    equity_series = pd.Series(equity_df["total_equity"].values, index=pd.to_datetime(equity_df["date"]))
    daily_pnl = equity_series.diff().fillna(0.0)

    # 1, 2, 3: Drawdown en USD, %, duración
    dd_metrics = compute_drawdown_metrics(equity_series, initial_capital=initial_capital)

    # 4, 5: Peor día y Sharpe diario anualizado
    daily_metrics = compute_daily_worst_and_sharpe(daily_pnl, initial_capital=initial_capital)

    # 6: Ratio Calmar
    n_days = len(equity_series)
    years = max(n_days / 252.0, 0.1)
    final_eq = float(equity_series.iloc[-1])
    cagr_pct = ((final_eq / initial_capital) ** (1.0 / years) - 1.0) * 100.0 if (initial_capital > 0 and final_eq > 0) else 0.0
    calmar = compute_calmar_ratio(cagr_pct, dd_metrics["max_drawdown_pct"])

    # 7: Test de Permutación Monte Carlo 10k
    trade_pnls = trades_df["net_pnl_usd"].tolist() if not trades_df.empty else []
    mc_results = run_monte_carlo_permutation_test(trade_pnls, n_iterations=mc_iterations)

    # 8: Deflated Sharpe Ratio
    observed_sharpe = daily_metrics["sharpe_daily"]
    trials = trials_sharpes if trials_sharpes else [observed_sharpe * 0.7, observed_sharpe * 0.9, observed_sharpe]
    from src.analysis.metrics import compute_deflated_sharpe_ratio
    dsr_prob = compute_deflated_sharpe_ratio(
        observed_sharpe=observed_sharpe,
        all_trial_sharpes=trials,
        sample_length=n_days,
    )

    # 9: Bootstrap de Bloques (10 días, CI 95%)
    bootstrap_ci = run_block_bootstrap(
        daily_pnl_series=daily_pnl,
        initial_capital=initial_capital,
        block_size=10,
        n_resamples=bootstrap_resamples,
    )

    # 10: Sensibilidad a la fricción y slippage
    total_commission = float(trades_df["total_commission_usd"].sum()) if not trades_df.empty else 0.0
    total_slippage = float(trades_df["total_slippage_usd"].sum()) if not trades_df.empty else 0.0
    real_net_pnl = float(trades_df["net_pnl_usd"].sum()) if not trades_df.empty else 0.0

    slip_sensitivity = {
        "baseline_slippage_usd": total_slippage,
        "commission_usd": total_commission,
        "pnl_baseline_usd": real_net_pnl,
        "pnl_slippage_x2_usd": real_net_pnl - total_slippage,
        "pnl_slippage_x3_usd": real_net_pnl - 2.0 * total_slippage,
        "degradation_x2_pct": (total_slippage / real_net_pnl * 100.0) if real_net_pnl > 0 else 0.0,
        "degradation_x3_pct": (2.0 * total_slippage / real_net_pnl * 100.0) if real_net_pnl > 0 else 0.0,
    }

    return {
        # 1. Max Drawdown en USD
        "max_drawdown_usd": dd_metrics["max_drawdown_usd"],
        # 2. Max Drawdown Porcentual
        "max_drawdown_pct": dd_metrics["max_drawdown_pct"],
        # 3. Duración del Drawdown (en días)
        "drawdown_duration_days": dd_metrics["max_drawdown_duration_days"],
        "avg_drawdown_duration_days": dd_metrics["avg_drawdown_duration_days"],
        # 4. Peor Día Intradía
        "worst_day_usd": daily_metrics["worst_day_usd"],
        "best_day_usd": daily_metrics["best_day_usd"],
        # 5. Sharpe Ratio Diario Anualizado
        "sharpe_daily": daily_metrics["sharpe_daily"],
        # 6. Ratio Calmar
        "cagr_pct": cagr_pct,
        "calmar_ratio": calmar,
        # 7. Permutación Monte Carlo 10k
        "monte_carlo_permutation_10k": mc_results,
        # 8. Deflated Sharpe Ratio
        "deflated_sharpe_ratio": dsr_prob,
        # 9. Bootstrap de Bloques (CI 95%)
        "sharpe_ci95": bootstrap_ci["sharpe_ci95"],
        "pnl_ci95": bootstrap_ci["pnl_ci95"],
        # 10. Sensibilidad al Deslizamiento
        "slippage_sensitivity": slip_sensitivity,
    }
