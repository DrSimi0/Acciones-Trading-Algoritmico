"""Generador de entorno histórico de mercado reproducible (precios, deslistes y noticias)."""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd

from config.settings import DataSplitsConfig
from src.data.news import NewsArticle, NewsDataManager

logger = logging.getLogger(__name__)


def generate_market_environment(
    start_date: str = "2010-01-01",
    end_date: str = "2026-10-25",
    num_tickers: int = 15,
    seed: int = 42,
) -> Tuple[Dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame, NewsDataManager]:
    """Genera un dataset cuantitativo completo y reproducible para pruebas de rigor.
    
    Incluye:
    1. Benchmark SPY con regímenes de mercado históricos (bull run 2010-2019, crash covid 2020, inflación 2022).
    2. Universo de acciones con sectores diferenciados y metadatos point-in-time (incluyendo empresas deslistadas).
    3. Eventos idiosincráticos con caídas de -10% a -25% y picos de volumen.
    4. Repositorio de noticias con titulares permitidos y excluidos con marcas de tiempo verificables.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start_date, end_date, freq="B")  # Días hábiles
    n_days = len(dates)

    # 1. Simular SPY
    spy_rets = rng.normal(loc=0.0004, scale=0.01, size=n_days)
    # Calibrar eventos macro reales
    for i, d in enumerate(dates):
        if d.year == 2020 and d.month == 3 and d.day in [9, 12, 16]:  # Covid crash
            spy_rets[i] = -0.05
        elif d.year == 2022 and d.month in [1, 5, 6] and d.day in [13, 18]:  # Inflación/tasas
            spy_rets[i] = -0.025

    spy_prices = 100.0 * np.exp(np.cumsum(spy_rets))
    spy_df = pd.DataFrame({
        "date": dates,
        "open": spy_prices * (1 - 0.001),
        "high": spy_prices * (1 + 0.004),
        "low": spy_prices * (1 - 0.004),
        "close": spy_prices,
        "volume": rng.uniform(50_000_000, 100_000_000, size=n_days),
        "spy_return": spy_rets,
    })

    # 2. Generar metadatos de tickers (incluyendo deslistes)
    tickers_list = [f"STK_{i:02d}" for i in range(1, num_tickers + 1)]
    sectors = ["Technology", "Healthcare", "Financials", "Consumer", "Industrials"]
    
    metadata_rows = []
    for i, t in enumerate(tickers_list):
        sec = sectors[i % len(sectors)]
        # STK_03 quebró y se deslistó en 2018
        # STK_07 se deslistó en 2021
        delist = None
        if t == "STK_03":
            delist = pd.Timestamp("2018-09-30")
        elif t == "STK_07":
            delist = pd.Timestamp("2021-12-31")

        metadata_rows.append({
            "ticker": t,
            "sector": sec,
            "listing_date": pd.Timestamp("2009-01-01"),
            "delisting_date": delist,
            "market_cap": float(rng.uniform(3e9, 50e9)),  # > $2B
        })
    metadata_df = pd.DataFrame(metadata_rows)

    # 3. Simular series de precios de cada acción y noticias
    stocks_dict: Dict[str, pd.DataFrame] = {}
    news_records: List[Dict] = []

    # Diccionario de plantillas de noticias
    permitted_templates = [
        "reports quarterly results, quarterly earnings and guidance miss expectations",
        "analyst cut rating with major downgrade on weak outlook and margin compression",
        "cuts full year sales guidance citing product delay and macro headwinds",
        "quarterly earnings miss consensus as operating costs surge",
    ]
    excluded_templates = [
        "files for Chapter 11 bankruptcy protection after creditor dispute",
        "announces stock offering and massive secondary offering dilution",
        "discloses SEC investigation and accounting investigation regarding revenue recognition",
        "receives FDA rejection complete response letter for lead drug candidate",
        "merger terminated following anti-trust challenge by regulator",
    ]

    for meta in metadata_rows:
        t = meta["ticker"]
        beta = float(rng.uniform(0.8, 1.4))
        # Deriva positiva de largo plazo (Equity Risk Premium ~8% anual)
        idiosyncratic_vol = rng.normal(0.00035, 0.016, size=n_days)
        base_rets = beta * spy_rets + idiosyncratic_vol
        
        # Inyectar caídas de evento cada ~75-90 días
        event_indices = list(range(40, n_days - 15, int(rng.integers(70, 90))))
        
        # Volumen líquido: 1M a 3.5M acciones diarias
        volumes = rng.uniform(1_200_000, 3_500_000, size=n_days)
        
        for idx in event_indices:
            event_d = dates[idx]
            # Si ya está deslistada, no inyectar
            if meta["delisting_date"] is not None and event_d > meta["delisting_date"]:
                continue

            # Determinar caída entre -10% y -22%
            drop = float(rng.uniform(-0.22, -0.105))
            base_rets[idx] = drop
            volumes[idx] = volumes[idx] * rng.uniform(3.5, 6.0)  # Pico de volumen 3.5x - 6x

            # Asignar noticia (70% permitidas, 20% excluidas, 10% sin noticias)
            rand_choice = rng.random()
            if rand_choice < 0.70:
                headline = f"{t} {rng.choice(permitted_templates)}"
                news_records.append({
                    "ticker": t,
                    "timestamp": event_d - pd.Timedelta(hours=int(rng.integers(4, 16))),
                    "headline": headline,
                    "body": "Detailed financial release outlining updated guidance and quarterly performance.",
                    "category": "earnings",
                })
                # Rebote en t+1 a t+3 para noticias operacionales sobre-reaccionadas
                if idx + 3 < n_days:
                    base_rets[idx + 1] += abs(drop) * 0.35
                    base_rets[idx + 2] += abs(drop) * 0.25
            elif rand_choice < 0.90:
                headline = f"{t} {rng.choice(excluded_templates)}"
                news_records.append({
                    "ticker": t,
                    "timestamp": event_d - pd.Timedelta(hours=int(rng.integers(4, 16))),
                    "headline": headline,
                    "body": "Regulatory and legal filing disclosing restructuring or offering terms.",
                    "category": "structural",
                })
                # Continuación de caída (post-earnings drift / insolvencia)
                if idx + 3 < n_days:
                    base_rets[idx + 1] -= 0.04
                    base_rets[idx + 2] -= 0.03
            # 10% restante: caída sin noticia (deriva errática)

        # Generar precio
        init_price = float(rng.uniform(30.0, 80.0))
        prices = init_price * np.exp(np.cumsum(base_rets))
        
        df_stk = pd.DataFrame({
            "date": dates,
            "open": prices * (1.0 - rng.uniform(0.001, 0.005, size=n_days)),
            "high": prices * (1.0 + rng.uniform(0.008, 0.020, size=n_days)),
            "low": prices * (1.0 - rng.uniform(0.008, 0.020, size=n_days)),
            "close": prices,
            "volume": volumes,
            "daily_return": base_rets,
        })
        
        # Filtro de desliste
        if meta["delisting_date"] is not None:
            df_stk = df_stk[df_stk["date"] <= meta["delisting_date"]].copy()

        # Enriquecer métricas
        dollar_vol = df_stk["close"] * df_stk["volume"]
        df_stk["adv20_usd"] = dollar_vol.rolling(20, min_periods=5).mean()
        df_stk["avg_vol20"] = df_stk["volume"].rolling(20, min_periods=5).mean()
        df_stk["vol_ratio"] = df_stk["volume"] / df_stk["avg_vol20"]
        df_stk["midpoint"] = (df_stk["high"] + df_stk["low"]) / 2.0
        
        # ATR 14
        tr1 = df_stk["high"] - df_stk["low"]
        tr2 = (df_stk["high"] - df_stk["close"].shift(1)).abs()
        tr3 = (df_stk["low"] - df_stk["close"].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df_stk["atr14"] = tr.rolling(14, min_periods=5).mean()

        # Merge con retorno de SPY
        df_stk = df_stk.merge(spy_df[["date", "spy_return"]], on="date", how="left")
        df_stk["beta_spy"] = beta
        df_stk["idiosyncratic_return"] = df_stk["daily_return"] - (beta * df_stk["spy_return"])

        stocks_dict[t] = df_stk

    news_df = pd.DataFrame(news_records)
    news_mgr = NewsDataManager(news_df)

    return stocks_dict, spy_df, metadata_df, news_mgr
