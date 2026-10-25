"""Comparativas obligatorias: Sin filtro de noticias, Buy & Hold SPY y Entradas Aleatorias."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from config.settings import StrategyConfig
from src.analysis.metrics import compute_portfolio_metrics
from src.backtest.engine import BacktestResult, EventBacktestEngine
from src.data.news import NewsDataManager

logger = logging.getLogger(__name__)


class BenchmarkComparisons:
    """Ejecuta los tres benchmarks obligatorios para contrastar la hipótesis de la estrategia."""

    def __init__(
        self,
        config: StrategyConfig,
        news_manager: Optional[NewsDataManager] = None,
    ):
        self.config = config
        self.news_mgr = news_manager

    def run_all_comparatives(
        self,
        stocks_data: Dict[str, pd.DataFrame],
        spy_df: pd.DataFrame,
        drop_pct_threshold: float = 0.10,
        n_random_simulations: int = 5,
        random_seed: int = 42,
    ) -> Dict[str, Dict[str, Any]]:
        """Ejecuta:
        1. Estrategia Base (con filtro de noticia estricto).
        2. Comparativo (a): Misma caída X% SIN filtro de noticia (bypassed).
        3. Comparativo (b): Buy & Hold SPY (en el mismo período).
        4. Comparativo (c): Entradas aleatorias con idéntica regla de salida y gestión de riesgo.
        """
        results: Dict[str, Dict[str, Any]] = {}

        # 1. Estrategia Completa
        engine_main = EventBacktestEngine(self.config, news_manager=self.news_mgr)
        res_main = engine_main.run(stocks_data, drop_pct_threshold=drop_pct_threshold, bypass_news_filter=False)
        metrics_main = compute_portfolio_metrics(res_main)
        results["strategy_with_news"] = metrics_main

        # 2. Comparativo (a): Sin filtro de noticias
        res_no_news = engine_main.run(stocks_data, drop_pct_threshold=drop_pct_threshold, bypass_news_filter=True)
        metrics_no_news = compute_portfolio_metrics(res_no_news)
        results["control_a_no_news_filter"] = metrics_no_news

        # 3. Comparativo (b): Buy & Hold SPY
        if not spy_df.empty:
            spy_sorted = spy_df.sort_values("date").reset_index(drop=True)
            init_spy = float(spy_sorted["close"].iloc[0])
            final_spy = float(spy_sorted["close"].iloc[-1])
            spy_ret = (final_spy / init_spy) - 1.0
            daily_spy_rets = spy_sorted["spy_return"].values if "spy_return" in spy_sorted.columns else spy_sorted["close"].pct_change().fillna(0.0).values
            mean_spy = float(np.mean(daily_spy_rets))
            std_spy = float(np.std(daily_spy_rets, ddof=1)) if len(daily_spy_rets) > 1 else 0.0
            sharpe_spy = float((mean_spy / std_spy) * np.sqrt(252.0)) if std_spy > 1e-12 else 0.0

            # Drawdown SPY
            cum_spy = spy_sorted["close"].values
            peak_spy = np.maximum.accumulate(cum_spy)
            dd_spy = (peak_spy - cum_spy) / peak_spy
            max_dd_spy = float(np.max(dd_spy))

            results["benchmark_b_spy_buy_and_hold"] = {
                "total_return_pct": spy_ret,
                "sharpe_annualized": sharpe_spy,
                "max_drawdown_pct": max_dd_spy,
                "n_days": len(spy_sorted),
            }

        # 4. Comparativo (c): Entradas aleatorias (promedio sobre n_random_simulations)
        random_sharpes = []
        random_returns = []
        random_pfs = []
        random_trades_count = []

        for i in range(n_random_simulations):
            res_rand = engine_main.run(
                stocks_data,
                drop_pct_threshold=drop_pct_threshold,
                bypass_news_filter=True,
                random_entry_mode=True,
                random_seed=random_seed + i * 101,
            )
            m_rand = compute_portfolio_metrics(res_rand)
            random_sharpes.append(m_rand["sharpe_annualized"])
            random_returns.append(m_rand["total_return_pct"])
            random_pfs.append(m_rand["profit_factor"] if not np.isinf(m_rand["profit_factor"]) else 0.0)
            random_trades_count.append(m_rand["n_trades"])

        results["control_c_random_entry"] = {
            "mean_sharpe_annualized": float(np.mean(random_sharpes)),
            "mean_total_return_pct": float(np.mean(random_returns)),
            "mean_profit_factor": float(np.mean(random_pfs)),
            "mean_trades": float(np.mean(random_trades_count)),
        }

        # Comprobar valor añadido del filtro de noticias
        news_sharpe = metrics_main["sharpe_annualized"]
        no_news_sharpe = metrics_no_news["sharpe_annualized"]
        news_adds_value = news_sharpe > no_news_sharpe

        results["news_filter_added_value_check"] = {
            "adds_value": news_adds_value,
            "sharpe_difference": float(news_sharpe - no_news_sharpe),
            "comment": (
                "El filtro de noticias supera al caso sin filtro, confirmando su aporte de valor."
                if news_adds_value else
                "RESULTADO NEGATIVO: El filtro de noticias no mejoró el resultado cuantitativo bruto."
            ),
        }

        return results
