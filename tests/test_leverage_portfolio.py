"""Tests automatizados para la gestión de apalancamiento, margen y dimensionamiento por expectativa."""
import pandas as pd
import pytest

from config.settings import LeverageConfig, RiskConfig
from src.backtest.portfolio import PortfolioManager, TradeRecord


def test_portfolio_allows_leverage_beyond_cash():
    """Con apalancamiento activado, el portafolio permite compras que superan el efectivo inicial."""
    risk_cfg = RiskConfig(
        initial_capital_usd=100_000.0,
        max_gross_exposure_pct=2.5,  # 2.5x apalancamiento
        max_concurrent_positions=5,
    )
    lev_cfg = LeverageConfig(enabled=True, max_gross_leverage=2.5)
    pm = PortfolioManager(risk_config=risk_cfg, leverage_config=lev_cfg)

    # 1. Abrir posición grande de $80,000
    pm.open_position(
        ticker="STK1",
        shares=1000,
        entry_date=pd.Timestamp("2021-01-04"),
        nominal_entry_price=80.0,
        effective_entry_price=80.0,
        stop_price=75.0,
        target_price=90.0,
        event_date=pd.Timestamp("2021-01-03"),
        drop_magnitude=10.0,
        entry_commission=5.0,
        entry_slippage=10.0,
    )
    # Efectivo restante: 100,000 - 80,005 = 19,995
    assert pm.cash == pytest.approx(19995.0, rel=1e-2)

    # 2. Con apalancamiento, abrir una segunda posición de $50,000 que excede los $19,995 de efectivo
    pm.open_position(
        ticker="STK2",
        shares=1000,
        entry_date=pd.Timestamp("2021-01-04"),
        nominal_entry_price=50.0,
        effective_entry_price=50.0,
        stop_price=45.0,
        target_price=58.0,
        event_date=pd.Timestamp("2021-01-03"),
        drop_magnitude=8.0,
        entry_commission=5.0,
        entry_slippage=10.0,
    )
    # Efectivo ahora es NEGATIVO (deuda de margen): 19,995 - 50,005 = -30,010
    assert pm.cash < 0.0
    assert pm.cash == pytest.approx(-30010.0, rel=1e-2)

    # El valor neto del portafolio (equity) sigue siendo ~100k
    current_prices = {"STK1": 80.0, "STK2": 50.0}
    eq = pm.get_portfolio_value(current_prices)
    assert eq == pytest.approx(99980.0, rel=1e-2)


def test_margin_interest_deduction_overnight():
    """Verifica que el interés por saldo deudor de margen se deduzca en cada cierre diario."""
    risk_cfg = RiskConfig(initial_capital_usd=50_000.0)
    # 6.5% de interés anual
    lev_cfg = LeverageConfig(enabled=True, margin_interest_rate_annual=0.065)
    pm = PortfolioManager(risk_config=risk_cfg, leverage_config=lev_cfg)

    # Forzar deuda de $100,000 (cash = -100,000)
    pm.cash = -100_000.0
    # Interés diario esperado: 100,000 * 0.065 / 360 = $18.0555
    expected_daily_interest = 100_000.0 * (0.065 / 360.0)

    rec = pm.update_daily_equity(pd.Timestamp("2021-01-05"), {})
    assert rec["daily_margin_interest"] == pytest.approx(expected_daily_interest, rel=1e-3)
    assert pm.cash == pytest.approx(-100_000.0 - expected_daily_interest, rel=1e-3)
    assert pm.total_margin_interest_paid == pytest.approx(expected_daily_interest, rel=1e-3)


def test_dynamic_expectancy_kelly_sizing():
    """Verifica que un historial de trades con alta expectativa y win rate escale el tamaño de posición."""
    risk_cfg = RiskConfig(initial_capital_usd=100_000.0)
    lev_cfg = LeverageConfig(
        enabled=True,
        use_expectancy_kelly_sizing=True,
        base_risk_pct=0.02,
        max_risk_pct=0.04,
        min_trade_history_for_kelly=5,
    )
    pm = PortfolioManager(risk_config=risk_cfg, leverage_config=lev_cfg)

    # Sin historial previo: usa base_risk_pct = 2%
    shares_base = pm.calculate_position_size(entry_price=100.0, stop_price=95.0, current_equity=100_000.0, current_gross_pos_val=0.0)
    # Riesgo base = $2,000 / dist($5) = 400 acciones
    assert shares_base == 400

    # Simular 6 trades altamente rentables (Win rate 83%, alta ganancia promedio)
    for i in range(5):
        pm.trade_history.append(
            TradeRecord(
                ticker=f"T{i}",
                entry_date=pd.Timestamp("2021-01-01"),
                exit_date=pd.Timestamp("2021-01-03"),
                shares=100,
                nominal_entry_price=50.0,
                effective_entry_price=50.0,
                nominal_exit_price=55.0,
                effective_exit_price=55.0,
                exit_reason="TAKE_PROFIT",
                days_held=2,
                gross_pnl_usd=500.0,
                net_pnl_usd=480.0,
                return_pct=0.10,
                total_commission_usd=5.0,
                total_slippage_usd=15.0,
                total_cost_usd=20.0,
            )
        )
    # 1 trade perdedor moderado
    pm.trade_history.append(
        TradeRecord(
            ticker="TLoss",
            entry_date=pd.Timestamp("2021-01-01"),
            exit_date=pd.Timestamp("2021-01-03"),
            shares=100,
            nominal_entry_price=50.0,
            effective_entry_price=50.0,
            nominal_exit_price=48.0,
            effective_exit_price=48.0,
            exit_reason="STOP_LOSS",
            days_held=2,
            gross_pnl_usd=-200.0,
            net_pnl_usd=-220.0,
            return_pct=-0.04,
            total_commission_usd=5.0,
            total_slippage_usd=15.0,
            total_cost_usd=20.0,
        )
    )

    stats = pm.compute_trade_expectancy_stats()
    assert stats["expectancy_usd"] > 0
    assert stats["win_rate"] == pytest.approx(5.0 / 6.0, rel=1e-2)
    assert stats["kelly_f"] > 0

    # Ahora con la expectativa positiva calculada sobre los trades, el tamaño debe escalar agresivamente
    shares_scaled = pm.calculate_position_size(entry_price=100.0, stop_price=95.0, current_equity=100_000.0, current_gross_pos_val=0.0)
    assert shares_scaled > shares_base
