"""Tests automatizados para el detector de eventos cuantitativos e idiosincráticos."""
import numpy as np
import pandas as pd
import pytest

from config.settings import EventFilterConfig, UniverseConfig
from src.signals.event_detector import EventDetector


@pytest.fixture
def sample_stock_data():
    """Genera una serie temporal sintética con caídas controladas."""
    dates = pd.date_range("2015-01-01", periods=60, freq="D")
    
    # Precios estables en $50 con volumen normal de 1M ($50M ADV)
    close = np.full(60, 50.0)
    high = close + 1.0
    low = close - 1.0
    volume = np.full(60, 1_000_000.0)
    
    # Día 30: Caída del -12% con volumen 4x (evento válido)
    close[30] = 44.0  # -12%
    high[30] = 50.0
    low[30] = 43.5
    volume[30] = 4_000_000.0  # 4x
    
    # Día 40: Caída del -15% pero con volumen bajo 1.5x (inválido por volumen)
    close[40] = 42.5  # -15%
    high[40] = 50.0
    low[40] = 42.0
    volume[40] = 1_500_000.0  # 1.5x
    
    # Día 50: Caída del -14% con volumen 4x, pero SPY cae -3.0% (inválido por no ser idiosincrático)
    close[50] = 43.0
    high[50] = 50.0
    low[50] = 42.5
    volume[50] = 4_000_000.0
    
    df = pd.DataFrame({
        "date": dates,
        "close": close,
        "high": high,
        "low": low,
        "volume": volume,
    })
    
    df["daily_return"] = df["close"].pct_change()
    df["adv20_usd"] = (df["close"] * df["volume"]).rolling(20, min_periods=5).mean()
    df["avg_vol20"] = df["volume"].rolling(20, min_periods=5).mean()
    df["vol_ratio"] = df["volume"] / df["avg_vol20"]
    df["atr14"] = 2.0
    df["midpoint"] = (df["high"] + df["low"]) / 2.0
    df["beta_spy"] = 1.0
    
    # Retorno de SPY: plano salvo en día 50 donde cae 3%
    df["spy_return"] = 0.0
    df.loc[50, "spy_return"] = -0.030
    df["idiosyncratic_return"] = df["daily_return"] - (df["beta_spy"] * df["spy_return"])
    
    return df


def test_event_detector_valid_event(sample_stock_data):
    detector = EventDetector(
        event_config=EventFilterConfig(min_drop_pct=0.10, max_spy_drop_pct=0.02, min_volume_mult=3.0),
        universe_config=UniverseConfig(min_price=5.0, min_adv20_usd=20_000_000.0),
    )
    candidates = detector.detect_events("TEST", sample_stock_data)
    
    # Debe detectar únicamente el día 30
    assert len(candidates) == 1
    event = candidates[0]
    assert event.ticker == "TEST"
    assert event.event_date == sample_stock_data.iloc[30]["date"]
    assert event.drop_pct == pytest.approx(-0.12, rel=1e-3)
    assert event.volume_ratio >= 3.0


def test_event_detector_rejects_market_wide_drop(sample_stock_data):
    """Verifica que el día 50 no sea detectado porque SPY cayó > 2%."""
    detector = EventDetector(
        event_config=EventFilterConfig(min_drop_pct=0.10, max_spy_drop_pct=0.02, min_volume_mult=3.0)
    )
    candidates = detector.detect_events("TEST", sample_stock_data)
    dates_detected = [c.event_date for c in candidates]
    
    assert sample_stock_data.iloc[50]["date"] not in dates_detected


def test_event_detector_rejects_insufficient_volume(sample_stock_data):
    """Verifica que el día 40 no sea detectado porque el volumen fue solo 1.5x."""
    detector = EventDetector(
        event_config=EventFilterConfig(min_drop_pct=0.10, min_volume_mult=3.0)
    )
    candidates = detector.detect_events("TEST", sample_stock_data)
    dates_detected = [c.event_date for c in candidates]
    
    assert sample_stock_data.iloc[40]["date"] not in dates_detected
