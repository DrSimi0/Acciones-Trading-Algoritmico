"""Análisis de estabilidad paramétrica mediante Walk-Forward dentro del bloque In-Sample."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from config.settings import ExitConfig, StrategyConfig
from src.analysis.grid_search import GridSearchAnalyzer
from src.analysis.metrics import compute_portfolio_metrics
from src.backtest.engine import EventBacktestEngine
from src.data.news import NewsDataManager

logger = logging.getLogger(__name__)


class WalkForwardAnalyzer:
    """Evalúa la robustez temporal y estabilidad de hiperparámetros en ventanas rodantes."""

    def __init__(
        self,
        base_config: StrategyConfig,
        news_manager: Optional[NewsDataManager] = None,
    ):
        self.base_cfg = base_config
        self.news_mgr = news_manager

    def run_in_sample_walk_forward(
        self,
        stocks_data: Dict[str, pd.DataFrame],
        train_years: int = 3,
        test_years: int = 1,
        start_year: int = 2010,
        end_year: int = 2019,
    ) -> pd.DataFrame:
        """Ejecuta ventanas rodantes de Walk-Forward dentro del período In-Sample.
        
        Evalúa:
        1. Selección del mejor parámetro en la ventana de entrenamiento.
        2. Desempeño inmediato en la ventana de test fuera de fold.
        3. Walk-Forward Efficiency (WFE = Sharpe_Test / Sharpe_Train).
        """
        records: List[Dict[str, Any]] = []
        grid_analyzer = GridSearchAnalyzer(self.base_cfg, self.news_mgr)

        curr_train_start = start_year
        while curr_train_start + train_years + test_years - 1 <= end_year:
            train_start_d = pd.Timestamp(f"{curr_train_start}-01-01")
            train_end_d = pd.Timestamp(f"{curr_train_start + train_years - 1}-12-31")
            test_start_d = pd.Timestamp(f"{curr_train_start + train_years}-01-01")
            test_end_d = pd.Timestamp(f"{curr_train_start + train_years + test_years - 1}-12-31")

            # Filtrar stocks para train y test
            train_stocks: Dict[str, pd.DataFrame] = {}
            test_stocks: Dict[str, pd.DataFrame] = {}

            for ticker, df in stocks_data.items():
                dates = pd.to_datetime(df["date"] if "date" in df.columns else df.index)
                m_train = (dates >= train_start_d) & (dates <= train_end_d)
                m_test = (dates >= test_start_d) & (dates <= test_end_d)
                if m_train.sum() > 20:
                    train_stocks[ticker] = df.loc[m_train].copy()
                if m_test.sum() > 20:
                    test_stocks[ticker] = df.loc[m_test].copy()

            if not train_stocks or not test_stocks:
                curr_train_start += test_years
                continue

            # 1. Optimizar en Train
            grid_res = grid_analyzer.run_grid(train_stocks)
            best_row = grid_res.iloc[0]
            best_drop = float(best_row["drop_pct"])
            best_rebound = float(best_row["rebound_target"])
            best_time = int(best_row["time_stop_days"])
            train_sharpe = float(best_row["sharpe_annualized"])

            # 2. Evaluar en Test con los parámetros óptimos de Train
            eval_cfg = StrategyConfig(
                universe=self.base_cfg.universe,
                event=self.base_cfg.event,
                news=self.base_cfg.news,
                entry=self.base_cfg.entry,
                exit=ExitConfig(
                    rebound_target_pct=best_rebound,
                    stop_atr_mult=self.base_cfg.exit.stop_atr_mult,
                    stop_max_loss_pct=self.base_cfg.exit.stop_max_loss_pct,
                    time_stop_days=best_time,
                ),
                risk=self.base_cfg.risk,
                cost=self.base_cfg.cost,
                splits=self.base_cfg.splits,
            )
            engine = EventBacktestEngine(eval_cfg, news_manager=self.news_mgr)
            test_res = engine.run(test_stocks, drop_pct_threshold=best_drop)
            test_metrics = compute_portfolio_metrics(test_res)
            test_sharpe = test_metrics["sharpe_annualized"]

            wfe = (test_sharpe / train_sharpe) if train_sharpe > 1e-6 else np.nan

            records.append({
                "window": f"{curr_train_start}-{curr_train_start+train_years-1} -> {test_start_d.year}",
                "train_years": f"{curr_train_start}-{curr_train_start+train_years-1}",
                "test_year": test_start_d.year,
                "best_drop_pct": best_drop,
                "best_rebound_target": best_rebound,
                "best_time_stop": best_time,
                "train_sharpe": train_sharpe,
                "test_sharpe": test_sharpe,
                "test_trades": test_metrics["n_trades"],
                "test_win_rate": test_metrics["win_rate"],
                "test_profit_factor": test_metrics["profit_factor"],
                "test_return_pct": test_metrics["total_return_pct"],
                "wfe_ratio": wfe,
            })

            curr_train_start += test_years

        return pd.DataFrame(records)
