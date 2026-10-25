"""Tests unitarios para el cálculo de costos, métricas de portafolio y Sharpe Deflactado."""
import numpy as np
import pandas as pd
import pytest

from config.settings import CostConfig, StrategyConfig
from src.analysis.metrics import compute_deflated_sharpe_ratio, compute_portfolio_metrics
from src.backtest.costs import EquityCostModel
from src.backtest.engine import BacktestResult
from src.backtest.portfolio import TradeRecord


def test_equity_cost_model_commission_and_slippage():
    cfg = CostConfig(
        commission_per_share=0.005,
        min_commission_usd=1.00,
        slippage_bps_normal=0.0010,  # 10 pb
        slippage_bps_event=0.0030,   # 30 pb
    )
    model = EquityCostModel(cfg)

    # 1. Compra pequeña: 50 acciones a $20 -> comisión $0.25 < $1.00 min -> cobra $1.00
    res_buy_small = model.execute_order(nominal_price=20.0, shares=50, is_buy=True, is_event_day=False)
    assert res_buy_small.commission_usd == 1.00
    # Slippage normal (10 pb): 20 * 0.0010 = 0.02 $/acción -> fill = 20.02
    assert res_buy_small.effective_fill_price == pytest.approx(20.02, rel=1e-4)

    # 2. Compra en día de evento: 1000 acciones a $50 -> comisión $5.00
    # Slippage de evento (30 pb): 50 * 0.0030 = 0.15 $/acción -> fill = 50.15
    res_buy_event = model.execute_order(nominal_price=50.0, shares=1000, is_buy=True, is_event_day=True)
    assert res_buy_event.commission_usd == 5.00
    assert res_buy_event.slippage_usd == pytest.approx(150.0, rel=1e-4)
    assert res_buy_event.effective_fill_price == pytest.approx(50.15, rel=1e-4)

    # 3. Venta normal: 1000 acciones a $52
    res_sell = model.execute_order(nominal_price=52.0, shares=1000, is_buy=False, is_event_day=False)
    # Slippage normal (10 pb): 52 * 0.0010 = 0.052 $/acción -> fill = 51.948
    assert res_sell.effective_fill_price == pytest.approx(51.948, rel=1e-4)


def test_compute_portfolio_metrics_accuracy():
    dates = pd.date_range("2021-01-01", periods=10, freq="D")
    equity_vals = [100000.0, 100500.0, 101000.0, 100200.0, 100800.0, 101500.0, 101200.0, 102000.0, 102500.0, 103000.0]
    
    eq_df = pd.DataFrame({"date": dates, "total_equity": equity_vals})
    eq_df["daily_return"] = eq_df["total_equity"].pct_change().fillna(0.0)
    eq_df["drawdown_pct"] = (np.maximum.accumulate(equity_vals) - equity_vals) / np.maximum.accumulate(equity_vals)

    trades = [
        TradeRecord(
            ticker="ABC",
            entry_date=dates[1],
            exit_date=dates[3],
            shares=100,
            nominal_entry_price=50.0,
            effective_entry_price=50.1,
            nominal_exit_price=55.0,
            effective_exit_price=54.9,
            exit_reason="TAKE_PROFIT",
            days_held=2,
            gross_pnl_usd=500.0,
            net_pnl_usd=470.0,
            return_pct=0.095,
            total_commission_usd=10.0,
            total_slippage_usd=20.0,
            total_cost_usd=30.0,
        ),
        TradeRecord(
            ticker="XYZ",
            entry_date=dates[3],
            exit_date=dates[5],
            shares=100,
            nominal_entry_price=40.0,
            effective_entry_price=40.1,
            nominal_exit_price=38.0,
            effective_exit_price=37.9,
            exit_reason="STOP_LOSS",
            days_held=2,
            gross_pnl_usd=-200.0,
            net_pnl_usd=-230.0,
            return_pct=-0.055,
            total_commission_usd=10.0,
            total_slippage_usd=20.0,
            total_cost_usd=30.0,
        ),
    ]

    res = BacktestResult(
        equity_curve=eq_df,
        trades=trades,
        trades_df=pd.DataFrame([t.__dict__ for t in trades]),
        config=StrategyConfig(),
    )

    metrics = compute_portfolio_metrics(res)
    assert metrics["n_trades"] == 2
    assert metrics["win_rate"] == 0.50
    assert metrics["total_net_pnl_usd"] == pytest.approx(3000.0, rel=1e-2)
    # Profit factor: 470 / 230 = 2.043
    assert metrics["profit_factor"] == pytest.approx(470.0 / 230.0, rel=1e-2)
    assert metrics["total_costs_usd"] == pytest.approx(60.0, rel=1e-2)


def test_deflated_sharpe_ratio_penalizes_multiple_trials():
    """Con muchas pruebas en la grilla y alta varianza, el DSR debe penalizar fuertemente."""
    trials_low = [0.8, 0.9, 1.0]
    dsr_few = compute_deflated_sharpe_ratio(
        observed_sharpe=1.2,
        all_trial_sharpes=trials_low,
        sample_length=1000,
    )

    # Misma estrategia observada (1.2), pero en un contexto de 50 pruebas con alta dispersión
    trials_many = list(np.random.RandomState(42).normal(loc=0.5, scale=0.6, size=50))
    trials_many.append(1.2)
    dsr_many = compute_deflated_sharpe_ratio(
        observed_sharpe=1.2,
        all_trial_sharpes=trials_many,
        sample_length=1000,
    )

    # Con 50 pruebas, la probabilidad de que el Sharpe sea pura suerte aumenta, por lo que DSR cae
    assert dsr_few > dsr_many
