"""Búsqueda en grilla pequeña pre-registrada con penalización por comparaciones múltiples."""
from __future__ import annotations

from dataclasses import dataclass
import itertools
import logging
from typing import Any, Dict, List, Optional
import pandas as pd

from config.settings import ExitConfig, StrategyConfig
from src.analysis.metrics import compute_deflated_sharpe_ratio, compute_portfolio_metrics
from src.backtest.engine import BacktestResult, EventBacktestEngine
from src.data.news import NewsDataManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GridParamCombination:
    drop_pct_threshold: float
    rebound_target_pct: float
    time_stop_days: int


class GridSearchAnalyzer:
    """Ejecuta una grilla de parámetros acotada y auditable sobre el bloque In-Sample."""

    def __init__(
        self,
        base_config: StrategyConfig,
        news_manager: Optional[NewsDataManager] = None,
    ):
        self.base_cfg = base_config
        self.news_mgr = news_manager

    def run_grid(
        self,
        stocks_in_sample: Dict[str, pd.DataFrame],
        drop_thresholds: tuple[float, ...] = (0.10, 0.15, 0.20),
        rebound_targets: tuple[float, ...] = (0.50, 0.75),
        time_stops: tuple[int, ...] = (3, 5),
    ) -> pd.DataFrame:
        """Prueba exhaustivamente la grilla pre-registrada y registra métricas y DSR."""
        combinations = list(itertools.product(drop_thresholds, rebound_targets, time_stops))
        n_trials = len(combinations)
        results_list: List[Dict[str, Any]] = []
        all_sharpes: List[float] = []
        raw_results: List[Tuple[GridParamCombination, BacktestResult, Dict[str, Any]]] = []

        # Precomputar cache de precios O(1) una sola vez para toda la grilla
        price_lookup: Dict[Tuple[str, pd.Timestamp], Dict[str, float]] = {}
        all_dates_set = set()
        for ticker, df in stocks_in_sample.items():
            if df.empty:
                continue
            df_std = df.copy()
            if "date" in df_std.columns:
                df_std["date"] = pd.to_datetime(df_std["date"])
                df_std = df_std.sort_values("date").reset_index(drop=True)
            else:
                df_std.index = pd.to_datetime(df_std.index)
                df_std["date"] = df_std.index
                df_std = df_std.sort_index().reset_index(drop=True)

            dates_arr = pd.to_datetime(df_std["date"]).values
            opens_arr = df_std["open"].values
            highs_arr = df_std["high"].values
            lows_arr = df_std["low"].values
            closes_arr = df_std["close"].values

            for i in range(len(df_std)):
                d = pd.to_datetime(dates_arr[i])
                all_dates_set.add(d)
                price_lookup[(ticker, d)] = {
                    "open": float(opens_arr[i]),
                    "high": float(highs_arr[i]),
                    "low": float(lows_arr[i]),
                    "close": float(closes_arr[i]),
                }

        sorted_dates = sorted(list(all_dates_set))

        # Paso 1: Ejecutar simulaciones
        for drop_th, rebound_tp, t_stop in combinations:
            cfg = StrategyConfig(
                universe=self.base_cfg.universe,
                event=self.base_cfg.event,
                news=self.base_cfg.news,
                entry=self.base_cfg.entry,
                exit=ExitConfig(
                    rebound_target_pct=rebound_tp,
                    stop_atr_mult=self.base_cfg.exit.stop_atr_mult,
                    stop_max_loss_pct=self.base_cfg.exit.stop_max_loss_pct,
                    time_stop_days=t_stop,
                ),
                risk=self.base_cfg.risk,
                cost=self.base_cfg.cost,
                splits=self.base_cfg.splits,
            )
            engine = EventBacktestEngine(cfg, news_manager=self.news_mgr)
            res = engine.run(
                stocks_in_sample,
                drop_pct_threshold=drop_th,
                cached_price_lookup=price_lookup,
                cached_sorted_dates=sorted_dates,
            )
            metrics = compute_portfolio_metrics(res)

            param_tuple = GridParamCombination(
                drop_pct_threshold=drop_th,
                rebound_target_pct=rebound_tp,
                time_stop_days=t_stop,
            )
            all_sharpes.append(metrics["sharpe_annualized"])
            raw_results.append((param_tuple, res, metrics))

        # Paso 2: Calcular Sharpe Deflactado (DSR) considerando los n_trials
        for param_tuple, res, metrics in raw_results:
            sample_len = metrics["n_days"]
            dsr = compute_deflated_sharpe_ratio(
                observed_sharpe=metrics["sharpe_annualized"],
                all_trial_sharpes=all_sharpes,
                sample_length=sample_len,
            )

            rec = {
                "drop_pct": param_tuple.drop_pct_threshold,
                "rebound_target": param_tuple.rebound_target_pct,
                "time_stop_days": param_tuple.time_stop_days,
                "n_trades": metrics["n_trades"],
                "win_rate": metrics["win_rate"],
                "profit_factor": metrics["profit_factor"],
                "total_return_pct": metrics["total_return_pct"],
                "cagr_pct": metrics["cagr_pct"],
                "max_drawdown_pct": metrics["max_drawdown_pct"],
                "sharpe_annualized": metrics["sharpe_annualized"],
                "sortino_annualized": metrics["sortino_annualized"],
                "expectancy_usd": metrics["expectancy_usd_per_trade"],
                "total_costs_usd": metrics["total_costs_usd"],
                "deflated_sharpe_prob": dsr,
            }
            results_list.append(rec)

        df_grid = pd.DataFrame(results_list)
        df_grid = df_grid.sort_values("sharpe_annualized", ascending=False).reset_index(drop=True)
        return df_grid
