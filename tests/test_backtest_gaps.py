"""Tests automatizados para el motor de backtest, modelado de gaps y reglas de salida."""
import pandas as pd
import pytest

from config.settings import CostConfig, EntryConfig, ExitConfig, RiskConfig, StrategyConfig
from src.backtest.engine import EventBacktestEngine
from src.data.news import NewsArticle, NewsDataManager


@pytest.fixture
def synthetic_stock_environment():
    """Genera datos sintéticos con 1 acción y SPY para probar ejecuciones exactas."""
    dates = pd.date_range("2015-01-01", periods=15, freq="D")
    
    # Precios base en $100
    opens = [100.0] * 15
    highs = [101.0] * 15
    lows = [99.0] * 15
    closes = [100.0] * 15
    volumes = [1_000_000.0] * 15

    # Día 5: Evento de caída del 15% con volumen 4x
    closes[5] = 85.0
    highs[5] = 100.0
    lows[5] = 84.0
    volumes[5] = 4_000_000.0

    # Día 6 (t+1): Apertura normal en 85.0 (entra posición)
    opens[6] = 85.0
    highs[6] = 86.0
    lows[6] = 84.5
    closes[6] = 85.5

    stock_df = pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })
    stock_df["daily_return"] = stock_df["close"].pct_change()
    stock_df["adv20_usd"] = 100_000_000.0
    stock_df["avg_vol20"] = 1_000_000.0
    stock_df["vol_ratio"] = stock_df["volume"] / stock_df["avg_vol20"]
    stock_df["atr14"] = 3.0
    stock_df["midpoint"] = (stock_df["high"] + stock_df["low"]) / 2.0
    stock_df["beta_spy"] = 1.0
    stock_df["spy_return"] = 0.0
    stock_df["idiosyncratic_return"] = stock_df["daily_return"]

    # Noticia válida para el evento
    news_df = pd.DataFrame([{
        "ticker": "XYZ",
        "timestamp": "2015-01-06 08:00:00",
        "headline": "XYZ reports earnings miss and lowers full-year guidance",
    }])

    return {"XYZ": stock_df}, NewsDataManager(news_df)


def test_gap_down_stop_loss_fills_at_open(synthetic_stock_environment):
    """Verifica que si en t+2 el precio abre con un gap por debajo del stop,
    el stop loss se ejecute al precio real de apertura y NO al precio teórico del stop.
    """
    stocks, news_mgr = synthetic_stock_environment
    stock_df = stocks["XYZ"]

    # En t+1 (índice 6) entra a 85.0.
    # Stop loss: min(1.5 * ATR(3.0) = 4.5, 8% de 85 = 6.8) -> Stop en 85 - 4.5 = 80.5
    # Forzar un GAP BAJISTA violento en t+2 (índice 7) abriendo en 72.0 (< 80.5):
    stock_df.loc[7, "open"] = 72.0
    stock_df.loc[7, "high"] = 73.0
    stock_df.loc[7, "low"] = 70.0
    stock_df.loc[7, "close"] = 71.0

    cfg = StrategyConfig()
    engine = EventBacktestEngine(cfg, news_manager=news_mgr)
    result = engine.run(stocks, drop_pct_threshold=0.10)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "STOP_LOSS_GAP"
    # El precio nominal de salida debe ser 72.0 (el open real), NO el stop de 80.5
    assert trade.nominal_exit_price == pytest.approx(72.0, rel=1e-3)
    assert trade.net_pnl_usd < 0


def test_cancels_entry_when_t1_gaps_down_more_than_5_pct(synthetic_stock_environment):
    """Verifica que si la apertura de t+1 cae > 5% adicional respecto al cierre de t, se cancela la entrada."""
    stocks, news_mgr = synthetic_stock_environment
    stock_df = stocks["XYZ"]

    # Cierre de t (índice 5) fue 85.0. Una caída > 5% adicional es abrir por debajo de 85 * 0.95 = 80.75
    # Forzar open en t+1 (índice 6) a 79.0 (-7% adicional)
    stock_df.loc[6, "open"] = 79.0

    cfg = StrategyConfig()
    engine = EventBacktestEngine(cfg, news_manager=news_mgr)
    result = engine.run(stocks, drop_pct_threshold=0.10)

    # Debe cancelar la orden y registrar 0 operaciones
    assert len(result.trades) == 0


def test_take_profit_rebound_execution(synthetic_stock_environment):
    """Verifica que si el precio rebota y alcanza el 50% de la caída, ejecuta Take Profit."""
    stocks, news_mgr = synthetic_stock_environment
    stock_df = stocks["XYZ"]

    # Caída observada: 100 - 85 = 15.0. 50% de rebote = 7.5.
    # Target de precio = 85 + 7.5 = 92.5.
    # Forzar que en día 7 el High toque 93.0
    stock_df.loc[7, "open"] = 86.0
    stock_df.loc[7, "high"] = 93.0
    stock_df.loc[7, "low"] = 85.5
    stock_df.loc[7, "close"] = 91.0

    cfg = StrategyConfig()
    engine = EventBacktestEngine(cfg, news_manager=news_mgr)
    result = engine.run(stocks, drop_pct_threshold=0.10)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "TAKE_PROFIT"
    assert trade.nominal_exit_price == pytest.approx(92.5, rel=1e-3)
    assert trade.net_pnl_usd > 0


def test_time_stop_exit_at_day_5(synthetic_stock_environment):
    """Verifica que si no toca TP ni SL, la posición se cierre al 5º día al precio de cierre."""
    stocks, news_mgr = synthetic_stock_environment
    stock_df = stocks["XYZ"]

    # Mantener precios en rango neutral (85.0 - 86.0) sin tocar target 92.5 ni stop 80.5
    for i in range(7, 14):
        stock_df.loc[i, "open"] = 85.0
        stock_df.loc[i, "high"] = 86.0
        stock_df.loc[i, "low"] = 84.5
        stock_df.loc[i, "close"] = 85.2

    cfg = StrategyConfig(exit=ExitConfig(time_stop_days=5))
    engine = EventBacktestEngine(cfg, news_manager=news_mgr)
    result = engine.run(stocks, drop_pct_threshold=0.10)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "TIME_STOP"
    assert trade.days_held == 5
    assert trade.nominal_exit_price == pytest.approx(85.2, rel=1e-3)

