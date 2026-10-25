"""Motor de backtesting multiactivo con ejecución diaria estricta, gaps y costos."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd

from config.settings import StrategyConfig
from src.backtest.costs import EquityCostModel
from src.backtest.portfolio import PortfolioManager, TradeRecord
from src.data.news import NewsDataManager
from src.signals.event_detector import EventCandidate, EventDetector
from src.signals.news_filter import NewsClassifier

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: List[TradeRecord]
    trades_df: pd.DataFrame
    config: StrategyConfig


class EventBacktestEngine:
    """Simulador de eventos cuantitativos para portafolios de acciones de EE. UU."""

    def __init__(
        self,
        config: StrategyConfig,
        news_manager: Optional[NewsDataManager] = None,
    ):
        self.config = config
        self.cost_model = EquityCostModel(config.cost)
        self.news_manager = news_manager or NewsDataManager()
        self.news_classifier = NewsClassifier(config.news)
        self.event_detector = EventDetector(config.event, config.universe)

    def run(
        self,
        stocks_data: Dict[str, pd.DataFrame],
        drop_pct_threshold: Optional[float] = None,
        bypass_news_filter: bool = False,
        random_entry_mode: bool = False,
        random_seed: int = 42,
        cached_price_lookup: Optional[Dict[Tuple[str, pd.Timestamp], Dict[str, float]]] = None,
        cached_sorted_dates: Optional[List[pd.Timestamp]] = None,
    ) -> BacktestResult:
        """Ejecuta el backtest cronológico multiactivo.
        
        Args:
            stocks_data: Diccionario con DataFrames enriquecidos indexados por ticker.
            drop_pct_threshold: Umbral X de caída (ej. 0.10, 0.15, 0.20, 0.25).
            bypass_news_filter: Si es True, no evalúa noticias (para comparativo a).
            random_entry_mode: Si es True, genera entradas aleatorias con misma salida y exposición (comparativo c).
            random_seed: Semilla para reproducibilidad.
            cached_price_lookup: Cache opcional de precios O(1) para acelerar grillas.
            cached_sorted_dates: Cache opcional de fechas ordenadas.
        """
        rng = np.random.default_rng(random_seed)
        portfolio = PortfolioManager(self.config.risk, getattr(self.config, "leverage", None))
        threshold = drop_pct_threshold if drop_pct_threshold is not None else self.config.event.min_drop_pct

        # 1. Detectar candidatos en todas las acciones
        candidates_by_date: Dict[pd.Timestamp, List[EventCandidate]] = {}
        all_dates_set: Set[pd.Timestamp] = set()

        if cached_price_lookup is not None and cached_sorted_dates is not None:
            price_lookup = cached_price_lookup
            sorted_dates = cached_sorted_dates
            for ticker, df in stocks_data.items():
                if df.empty:
                    continue
                cands = self.event_detector.detect_events(ticker, df, drop_pct_threshold=threshold)
                for c in cands:
                    d = pd.to_datetime(c.event_date)
                    if d not in candidates_by_date:
                        candidates_by_date[d] = []
                    candidates_by_date[d].append(c)
        else:
            # Indexar datos de precios por (ticker, fecha) para acceso rápido O(1) con numpy arrays
            price_lookup: Dict[Tuple[str, pd.Timestamp], Dict[str, float]] = {}

            for ticker, df in stocks_data.items():
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

                # Detectar candidatos del ticker
                cands = self.event_detector.detect_events(ticker, df_std, drop_pct_threshold=threshold)
                for c in cands:
                    d = pd.to_datetime(c.event_date)
                    if d not in candidates_by_date:
                        candidates_by_date[d] = []
                    candidates_by_date[d].append(c)

            sorted_dates = sorted(list(all_dates_set))
        daily_records: List[Dict] = []

        # Para seguimiento de eventos del día anterior (t) que entran en (t+1)
        pending_orders: List[EventCandidate] = []

        for current_date in sorted_dates:
            # Diccionario de precios actuales para valuación de cartera
            current_prices: Dict[str, float] = {}
            for t in list(portfolio.positions.keys()):
                row_t = price_lookup.get((t, current_date))
                if row_t is not None:
                    current_prices[t] = float(row_t["close"])

            # -------------------------------------------------------------
            # PASO A: Gestión y salidas de posiciones existentes
            # -------------------------------------------------------------
            active_tickers = list(portfolio.positions.keys())
            for ticker in active_tickers:
                pos = portfolio.positions.get(ticker)
                if pos is None:
                    continue

                row = price_lookup.get((ticker, current_date))
                if row is None:
                    continue

                open_p = float(row["open"])
                high_p = float(row["high"])
                low_p = float(row["low"])
                close_p = float(row["close"])

                pos.days_held += 1
                exit_triggered = False
                exit_nominal_price = 0.0
                exit_reason = ""
                is_gap_stop = False

                # 1. Take Profit por gap alcista de apertura
                if open_p >= pos.target_price:
                    exit_triggered = True
                    exit_nominal_price = open_p
                    exit_reason = "TAKE_PROFIT_GAP"

                # 2. Stop Loss por gap bajista de apertura (MODELADO CRÍTICO DE GAPS)
                elif open_p <= pos.stop_price:
                    exit_triggered = True
                    exit_nominal_price = open_p  # Ejecución real al precio de apertura, no al stop
                    exit_reason = "STOP_LOSS_GAP"
                    is_gap_stop = True

                # 3. Take Profit intradía
                elif high_p >= pos.target_price:
                    exit_triggered = True
                    exit_nominal_price = pos.target_price
                    exit_reason = "TAKE_PROFIT"

                # 4. Stop Loss intradía
                elif low_p <= pos.stop_price:
                    exit_triggered = True
                    exit_nominal_price = pos.stop_price
                    exit_reason = "STOP_LOSS"

                # 5. Time Stop (cierre del día configurado)
                elif pos.days_held >= self.config.exit.time_stop_days:
                    exit_triggered = True
                    exit_nominal_price = close_p
                    exit_reason = "TIME_STOP"

                if exit_triggered:
                    exec_res = self.cost_model.execute_order(
                        nominal_price=exit_nominal_price,
                        shares=pos.shares,
                        is_buy=False,
                        is_event_day=is_gap_stop,
                    )
                    portfolio.close_position(
                        ticker=ticker,
                        exit_date=current_date,
                        nominal_exit_price=exit_nominal_price,
                        effective_exit_price=exec_res.effective_fill_price,
                        exit_reason=exit_reason,
                        exit_commission=exec_res.commission_usd,
                        exit_slippage=exec_res.slippage_usd,
                    )
                    if ticker in current_prices:
                        del current_prices[ticker]

            # -------------------------------------------------------------
            # PASO B: Ejecución de órdenes de entrada en t+1
            # -------------------------------------------------------------
            # Si se especificó random_entry_mode para control (c), generar entradas aleatorias
            if random_entry_mode and pending_orders:
                # Filtrar aleatoriamente con la misma probabilidad/frecuencia
                rng.shuffle(pending_orders)

            for cand in pending_orders:
                ticker = cand.ticker
                row_t1 = price_lookup.get((ticker, current_date))
                if row_t1 is None:
                    continue

                open_t1 = float(row_t1["open"])

                # Regla de entrada 1: Cancelar si cae > 5% adicional respecto al cierre de t
                pct_gap_t1 = (open_t1 / cand.close_event) - 1.0
                if pct_gap_t1 < -self.config.entry.max_gap_down_additional_pct:
                    continue  # Caída sigue acelerando

                # Variante: entrar solo si supera el punto medio del rango de t
                if self.config.entry.require_midpoint_cross and open_t1 < cand.midpoint:
                    continue

                # Regla de riesgo: límites de concurrencia y disyuntor
                current_total_equity = portfolio.get_portfolio_value(current_prices)
                current_gross_val = sum(pos.shares * current_prices.get(t, pos.nominal_entry_price) for t, pos in portfolio.positions.items())

                if not portfolio.can_open_position(ticker, current_total_equity, current_gross_val):
                    continue

                # Cálculo de niveles de salida
                # Take profit: recuperar el 50% (o 75%) de la caída observada en t
                drop_amount = cand.close_prev - cand.close_event
                target_p = cand.close_event + (self.config.exit.rebound_target_pct * drop_amount)

                # Stop loss: el más estrecho entre -1.5 ATR(14) y -8%
                atr_dist = self.config.exit.stop_atr_mult * cand.atr14
                max_pct_dist = self.config.exit.stop_max_loss_pct * open_t1
                stop_dist = min(atr_dist, max_pct_dist)
                stop_p = open_t1 - stop_dist

                # Dimensionamiento de posición (position sizing con Kelly / expectativa de trade)
                shares = portfolio.calculate_position_size(
                    entry_price=open_t1,
                    stop_price=stop_p,
                    current_equity=current_total_equity,
                    current_gross_pos_val=current_gross_val,
                )

                if shares <= 0:
                    continue

                # Ejecución de compra en la apertura de t+1 (con slippage de evento: 30 pb)
                exec_buy = self.cost_model.execute_order(
                    nominal_price=open_t1,
                    shares=shares,
                    is_buy=True,
                    is_event_day=True,
                )

                portfolio.open_position(
                    ticker=ticker,
                    shares=shares,
                    entry_date=current_date,
                    nominal_entry_price=open_t1,
                    effective_entry_price=exec_buy.effective_fill_price,
                    stop_price=stop_p,
                    target_price=target_p,
                    event_date=cand.event_date,
                    drop_magnitude=drop_amount,
                    entry_commission=exec_buy.commission_usd,
                    entry_slippage=exec_buy.slippage_usd,
                )
                current_prices[ticker] = float(row_t1["close"])

            # -------------------------------------------------------------
            # PASO C: Preparar candidatos detectados en current_date (t) para entrar en (t+1)
            # -------------------------------------------------------------
            pending_orders = []
            cands_today = candidates_by_date.get(current_date, [])
            for cand in cands_today:
                if bypass_news_filter or not self.config.news.enabled:
                    pending_orders.append(cand)
                else:
                    # Filtro de noticias estricto
                    articles = self.news_manager.get_news_for_event(cand.ticker, cand.event_date)
                    eval_res = self.news_classifier.evaluate_candidate(cand, articles)
                    if eval_res.is_approved:
                        pending_orders.append(cand)

            # -------------------------------------------------------------
            # PASO D: Valuación y registro diario del portafolio
            # -------------------------------------------------------------
            equity_rec = portfolio.update_daily_equity(current_date, current_prices)
            daily_records.append(equity_rec)

        # Generar resultados consolidados
        equity_df = pd.DataFrame(daily_records)
        if not equity_df.empty:
            equity_df["daily_return"] = equity_df["total_equity"].pct_change().fillna(0.0)

        trades_list = portfolio.trade_history
        if trades_list:
            trades_df = pd.DataFrame([t.__dict__ for t in trades_list])
        else:
            trades_df = pd.DataFrame()

        return BacktestResult(
            equity_curve=equity_df,
            trades=trades_list,
            trades_df=trades_df,
            config=self.config,
        )
