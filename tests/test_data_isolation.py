"""Tests para verificar el aislamiento estricto de particiones temporales (In-Sample, Validación, OOS)."""
import pandas as pd
import pytest

from config.settings import DataSplitsConfig
from src.data.prices import PriceDataManager


def test_oos_access_blocked_by_default():
    """El intento de acceder a datos OOS sin desbloqueo formal debe levantar PermissionError."""
    config = DataSplitsConfig(allow_oos_access=False)
    manager = PriceDataManager(splits_config=config)
    
    dates = pd.date_range("2010-01-01", "2024-12-31", freq="D")
    df = pd.DataFrame({"date": dates, "close": 100.0})
    
    with pytest.raises(PermissionError) as exc_info:
        manager.filter_by_split(df, "oos")
        
    assert "VIOLACIÓN DE PROTOCOLO" in str(exc_info.value)


def test_in_sample_and_validation_splits_non_overlapping():
    """Los bloques In-Sample y Validación no deben solaparse ni filtrar datos incorrectos."""
    config = DataSplitsConfig()
    manager = PriceDataManager(splits_config=config)
    
    dates = pd.date_range("2009-01-01", "2023-01-01", freq="D")
    df = pd.DataFrame({"date": dates, "close": 100.0})
    
    df_is = manager.filter_by_split(df, "in_sample")
    df_val = manager.filter_by_split(df, "validation")
    
    assert df_is["date"].min() >= pd.to_datetime(config.in_sample_start)
    assert df_is["date"].max() <= pd.to_datetime(config.in_sample_end)
    
    assert df_val["date"].min() >= pd.to_datetime(config.validation_start)
    assert df_val["date"].max() <= pd.to_datetime(config.validation_end)
    
    # Cero intersección
    overlap = set(df_is["date"]).intersection(set(df_val["date"]))
    assert len(overlap) == 0
