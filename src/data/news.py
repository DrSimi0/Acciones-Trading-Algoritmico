"""Gestión y filtrado temporal de noticias con marcas de tiempo auditables."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import logging
from typing import Dict, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewsArticle:
    ticker: str
    timestamp: pd.Timestamp
    headline: str
    body: str = ""
    category: str = "general"
    source: str = ""


class NewsDataManager:
    """Gestiona el repositorio de noticias históricas con estricta prevención de look-ahead."""

    def __init__(self, news_df: Optional[pd.DataFrame] = None):
        self.articles_by_ticker: Dict[str, List[NewsArticle]] = {}
        if news_df is not None and not news_df.empty:
            self.load_from_dataframe(news_df)

    def load_from_dataframe(self, df: pd.DataFrame) -> None:
        """Carga artículos desde un DataFrame que contenga columnas:
        ticker, timestamp, headline, [body, category, source].
        """
        df_copy = df.copy()
        df_copy["timestamp"] = pd.to_datetime(df_copy["timestamp"])
        df_copy = df_copy.sort_values("timestamp")

        for _, row in df_copy.iterrows():
            ticker = str(row["ticker"]).upper()
            art = NewsArticle(
                ticker=ticker,
                timestamp=row["timestamp"],
                headline=str(row["headline"]),
                body=str(row.get("body", "")),
                category=str(row.get("category", "general")),
                source=str(row.get("source", "")),
            )
            if ticker not in self.articles_by_ticker:
                self.articles_by_ticker[ticker] = []
            self.articles_by_ticker[ticker].append(art)

    def get_news_for_event(
        self,
        ticker: str,
        event_date: pd.Timestamp,
        lookback_hours: float = 36.0,
    ) -> List[NewsArticle]:
        """Obtiene las noticias para `ticker` dentro de la ventana del evento:
        - Desde la noche anterior (lookback_hours antes de la apertura de t+1).
        - Estricto corte temporal (no look-ahead): nunca noticias posteriores a las 09:30 AM de t+1.
        """
        ticker = ticker.upper()
        if ticker not in self.articles_by_ticker:
            return []

        # El evento ocurre en el día `event_date` (t).
        # La noche anterior a t corresponde a t-1 después del cierre (ej. ~16:00).
        # La decisión de entrada es al open de t+1 (09:30 AM).
        # Ventana permitida: [event_date - 1 día a las 16:00, event_date a las 23:59 o t+1 09:15 AM].
        cutoff_start = (pd.to_datetime(event_date) - pd.Timedelta(hours=lookback_hours))
        # Hard cutoff en el cierre del día del evento o antes de la apertura de t+1
        cutoff_end = pd.to_datetime(event_date) + pd.Timedelta(days=1, hours=9, minutes=15)

        matched: List[NewsArticle] = []
        for art in self.articles_by_ticker[ticker]:
            ts = art.timestamp
            # Normalizar timezone si corresponde
            if ts.tz is not None and cutoff_start.tz is None:
                ts = ts.tz_localize(None)
            elif ts.tz is None and cutoff_start.tz is not None:
                cutoff_start = cutoff_start.tz_localize(None)
                cutoff_end = cutoff_end.tz_localize(None)

            if cutoff_start <= ts <= cutoff_end:
                matched.append(art)

        return matched
