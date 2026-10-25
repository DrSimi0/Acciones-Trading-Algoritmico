"""Tests unitarios para las 10 métricas de riesgo avanzadas."""
import numpy as np
import pandas as pd
import pytest

from src.analysis.risk_metrics import (
    compute_calmar_ratio,
    compute_daily_worst_and_sharpe,
    compute_drawdown_metrics,
    run_block_bootstrap,
    run_monte_carlo_permutation_test,
)


def test_compute_drawdown_metrics():
    # Serie con pico en 100k, caída a 90k (DD 10k, 10%), luego recuperación en 4 días
    dates = pd.date_range("2021-01-01", periods=8, freq="D")
    eq_vals = [100000.0, 105000.0, 95000.0, 94500.0, 98000.0, 106000.0, 104000.0, 107000.0]
    eq_s = pd.Series(eq_vals, index=dates)

    res = compute_drawdown_metrics(eq_s, initial_capital=100000.0)
    # Pico fue 105,000, punto más bajo 94,500 -> DD monetario = 10,500 USD
    assert res["max_drawdown_usd"] == pytest.approx(10500.0, rel=1e-3)
    # Porcentual sobre capital inicial fijo 100k: 10.5%
    assert res["max_drawdown_pct"] == pytest.approx(10.5, rel=1e-3)
    # Duración de días bajo el agua en ese ciclo: días 2, 3, 4 (3 días)
    assert res["max_drawdown_duration_days"] == 3


def test_compute_daily_worst_and_sharpe():
    # 5 días de PnL
    pnl_s = pd.Series([1000.0, -1500.0, 2000.0, -500.0, 3000.0])
    res = compute_daily_worst_and_sharpe(pnl_s, initial_capital=100000.0)

    assert res["worst_day_usd"] == -1500.0
    assert res["best_day_usd"] == 3000.0
    assert res["sharpe_daily"] > 0.0


def test_compute_calmar_ratio():
    cagr = 25.0  # 25% anual
    max_dd = 10.0  # 10% max DD
    calmar = compute_calmar_ratio(cagr, max_dd)
    assert calmar == pytest.approx(2.5, rel=1e-3)


def test_run_monte_carlo_permutation_test():
    # 20 trades con fuerte sesgo ganador
    trade_pnls = [500.0] * 18 + [-200.0] * 2
    res = run_monte_carlo_permutation_test(trade_pnls, n_iterations=1000, random_seed=42)

    assert res["real_pnl"] == 8600.0
    assert res["p_value"] < 0.01  # Estadísticamente muy significativo
    assert res["z_score"] > 3.0
    assert res["is_statistically_significant_99"] is True


def test_run_block_bootstrap():
    daily_pnl = pd.Series(np.random.RandomState(42).normal(loc=100.0, scale=300.0, size=50))
    res = run_block_bootstrap(daily_pnl, initial_capital=50000.0, block_size=10, n_resamples=500)

    sh_low, sh_high = res["sharpe_ci95"]
    pnl_low, pnl_high = res["pnl_ci95"]

    assert sh_low < sh_high
    assert pnl_low < pnl_high
