"""Pruebas de estrés y robustez: slippage x2, exclusión de 2020, sin top 10 trades y atribución sectorial."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from config.settings import CostConfig, StrategyConfig
from src.analysis.metrics import compute_portfolio_metrics
from src.backtest.engine import BacktestResult, EventBacktestEngine
from src.data.news import NewsDataManager

logger = logging.getLogger(__name__)


class RobustnessAnalyzer:
    """Ejecuta batería rigurosa de pruebas de sensibilidad y estrés."""

    def __init__(
        self,
        config: StrategyConfig,
        news_manager: Optional[NewsDataManager] = None,
    ):
        self.config = config
        self.news_mgr = news_manager

    def evaluate_all_stress_tests(
        self,
        stocks_data: Dict[str, pd.DataFrame],
        metadata_df: Optional[pd.DataFrame] = None,
        drop_pct_threshold: float = 0.10,
    ) -> Dict[str, Any]:
        """Ejecuta:
        1. Caso Base.
        2. Estrés de Slippage x2.
        3. Exclusión de 2020 (año covid).
        4. Exclusión de los 10 mejores trades.
        5. Atribución de rendimiento por Sector.
        6. Desglose anual.
        """
        results: Dict[str, Any] = {}

        # 1. Caso Base
        engine_base = EventBacktestEngine(self.config, news_manager=self.news_mgr)
        res_base = engine_base.run(stocks_data, drop_pct_threshold=drop_pct_threshold)
        metrics_base = compute_portfolio_metrics(res_base)
        results["base_case"] = metrics_base

        # 2. Sensibilidad al Slippage x2
        stressed_cost_cfg = CostConfig(
            commission_per_share=self.config.cost.commission_per_share,
            min_commission_usd=self.config.cost.min_commission_usd,
            slippage_bps_normal=self.config.cost.slippage_bps_normal * 2.0,
            slippage_bps_event=self.config.cost.slippage_bps_event * 2.0,
        )
        stressed_cfg = StrategyConfig(
            universe=self.config.universe,
            event=self.config.event,
            news=self.config.news,
            entry=self.config.entry,
            exit=self.config.exit,
            risk=self.config.risk,
            cost=stressed_cost_cfg,
            splits=self.config.splits,
        )
        engine_stress = EventBacktestEngine(stressed_cfg, news_manager=self.news_mgr)
        res_stress = engine_stress.run(stocks_data, drop_pct_threshold=drop_pct_threshold)
        results["slippage_x2"] = compute_portfolio_metrics(res_stress)

        # 3. Exclusión de 2020
        stocks_no_2020: Dict[str, pd.DataFrame] = {}
        for ticker, df in stocks_data.items():
            dates = pd.to_datetime(df["date"] if "date" in df.columns else df.index)
            stocks_no_2020[ticker] = df.loc[dates.dt.year != 2020].copy()

        res_no_2020 = engine_base.run(stocks_no_2020, drop_pct_threshold=drop_pct_threshold)
        results["excluding_2020"] = compute_portfolio_metrics(res_no_2020)

        # 4. Exclusión de las 10 mejores operaciones
        trades_df = res_base.trades_df
        if len(trades_df) > 10:
            top_10_indices = trades_df.nlargest(10, "net_pnl_usd").index
            trades_no_top10 = trades_df.drop(index=top_10_indices)

            net_pnls = trades_no_top10["net_pnl_usd"].values
            pos_sum = float(np.sum(net_pnls[net_pnls > 0]))
            neg_sum = float(np.abs(np.sum(net_pnls[net_pnls < 0])))
            pf_ex_top10 = (pos_sum / neg_sum) if neg_sum > 0 else 0.0

            results["excluding_top_10_trades"] = {
                "remaining_trades": len(trades_no_top10),
                "total_net_pnl_usd": float(np.sum(net_pnls)),
                "profit_factor": float(pf_ex_top10),
                "win_rate": float(np.mean(net_pnls > 0)),
                "avg_trade_net_usd": float(np.mean(net_pnls)),
            }
        else:
            results["excluding_top_10_trades"] = {"note": "Menos de 10 operaciones en total para excluir."}

        # 5. Atribución por Sector
        if metadata_df is not None and not metadata_df.empty and not trades_df.empty:
            sector_map = metadata_df.set_index("ticker")["sector"].to_dict()
            trades_df_sec = trades_df.copy()
            trades_df_sec["sector"] = trades_df_sec["ticker"].map(sector_map).fillna("Unknown")

            sector_summary = {}
            for sec, grp in trades_df_sec.groupby("sector"):
                pnls = grp["net_pnl_usd"].values
                p_sum = float(np.sum(pnls[pnls > 0]))
                n_sum = float(np.abs(np.sum(pnls[pnls < 0])))
                pf = (p_sum / n_sum) if n_sum > 0 else (np.inf if p_sum > 0 else 0.0)

                sector_summary[sec] = {
                    "n_trades": len(grp),
                    "total_net_pnl_usd": float(np.sum(pnls)),
                    "win_rate": float(np.mean(pnls > 0)),
                    "profit_factor": float(pf),
                }
            results["sector_breakdown"] = sector_summary
        else:
            results["sector_breakdown"] = {}

        # 6. Desglose anual
        results["yearly_breakdown"] = metrics_base.get("yearly_returns", {})

        return results
