"""Filtro determinista de noticias sin look-ahead para validar la causa del evento."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import List, Optional, Set, Tuple
import pandas as pd

from config.settings import NewsFilterConfig
from src.data.news import NewsArticle
from src.signals.event_detector import EventCandidate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewsFilterResult:
    is_approved: bool
    status: str  # 'APPROVED', 'REJECTED_EXCLUDED', 'REJECTED_NO_PERMITTED', 'REJECTED_NO_NEWS', 'BYPASSED'
    reason: str
    matched_permitted: tuple[str, ...] = field(default_factory=tuple)
    matched_excluded: tuple[str, ...] = field(default_factory=tuple)
    articles_analyzed: int = 0


class NewsClassifier:
    """Clasifica el contexto noticioso de una caída de forma determinista y auditable."""

    def __init__(self, config: Optional[NewsFilterConfig] = None):
        self.config = config or NewsFilterConfig()
        # Precompilar regex de palabras clave completas
        self._permitted_patterns = [
            (kw, re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE))
            for kw in self.config.permitted_keywords
        ]
        self._excluded_patterns = [
            (kw, re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE))
            for kw in self.config.excluded_keywords
        ]

    def evaluate_candidate(
        self,
        candidate: EventCandidate,
        articles: List[NewsArticle],
    ) -> NewsFilterResult:
        """Evalúa las noticias asociadas a un candidato a evento.
        
        Reglas estrictas:
        1. Si el filtro de noticias está deshabilitado en config (para benchmark comparativo), aprueba directamente.
        2. Debe existir al menos un artículo dentro de la ventana del evento.
        3. Si CUALQUIER artículo contiene una palabra clave de exclusión (quiebra, fraude, etc.), se descarta de inmediato.
        4. Debe contener al menos una palabra clave permitida (resultados, guidance, downgrade, etc.).
        5. Jamás utiliza información posterior a la decisión de entrada.
        """
        if not self.config.enabled:
            return NewsFilterResult(
                is_approved=True,
                status="BYPASSED",
                reason="Filtro de noticias deshabilitado (modo comparativo).",
                articles_analyzed=len(articles),
            )

        if not articles:
            return NewsFilterResult(
                is_approved=False,
                status="REJECTED_NO_NEWS",
                reason="No se encontraron noticias con timestamp válido en la ventana del evento.",
                articles_analyzed=0,
            )

        # Concatenar titulares y textos de la ventana
        combined_texts: List[str] = []
        for art in articles:
            text = f"{art.headline} {art.body}".lower()
            combined_texts.append(text)

        full_text = " ".join(combined_texts)

        # 1. Chequeo de exclusiones (máxima prioridad de descarte)
        matched_excluded: List[str] = []
        for kw, pat in self._excluded_patterns:
            if pat.search(full_text):
                matched_excluded.append(kw)

        if matched_excluded:
            return NewsFilterResult(
                is_approved=False,
                status="REJECTED_EXCLUDED",
                reason=f"Evento asociado a noticia prohibida/estructural: {matched_excluded}",
                matched_excluded=tuple(matched_excluded),
                articles_analyzed=len(articles),
            )

        # 2. Chequeo de causas permitidas
        matched_permitted: List[str] = []
        for kw, pat in self._permitted_patterns:
            if pat.search(full_text):
                matched_permitted.append(kw)

        if matched_permitted:
            return NewsFilterResult(
                is_approved=True,
                status="APPROVED",
                reason=f"Evento validado por noticia operacional/financiera: {matched_permitted}",
                matched_permitted=tuple(matched_permitted),
                articles_analyzed=len(articles),
            )

        # 3. Noticia encontrada pero sin causa permitida
        return NewsFilterResult(
            is_approved=False,
            status="REJECTED_NO_PERMITTED",
            reason="Existen noticias en la ventana pero no encajan en las causas permitidas predefinidas.",
            articles_analyzed=len(articles),
        )
