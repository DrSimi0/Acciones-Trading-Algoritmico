"""Tests automatizados para el filtro de noticias y prevención de look-ahead."""
from datetime import datetime
import pandas as pd
import pytest

from config.settings import NewsFilterConfig
from src.data.news import NewsArticle, NewsDataManager
from src.signals.event_detector import EventCandidate
from src.signals.news_filter import NewsClassifier


@pytest.fixture
def dummy_candidate():
    return EventCandidate(
        ticker="AAPL",
        event_date=pd.Timestamp("2018-05-10"),
        close_prev=100.0,
        close_event=85.0,
        high_event=100.0,
        low_event=84.0,
        drop_pct=-0.15,
        spy_drop_pct=0.005,
        beta_spy=1.0,
        idiosyncratic_drop_pct=-0.155,
        volume_event=10_000_000.0,
        avg_vol20=2_000_000.0,
        volume_ratio=5.0,
        adv20_usd=200_000_000.0,
        atr14=3.5,
        midpoint=92.0,
    )


def test_news_filter_approves_permitted_earnings(dummy_candidate):
    classifier = NewsClassifier()
    articles = [
        NewsArticle(
            ticker="AAPL",
            timestamp=pd.Timestamp("2018-05-10 08:00:00"),
            headline="AAPL reports quarterly results, quarterly earnings and guidance miss expectations",
            body="Revenue was below street consensus...",
        )
    ]
    result = classifier.evaluate_candidate(dummy_candidate, articles)
    assert result.is_approved is True
    assert result.status == "APPROVED"
    assert "guidance" in result.matched_permitted or "earnings" in result.matched_permitted


def test_news_filter_rejects_excluded_bankruptcy(dummy_candidate):
    classifier = NewsClassifier()
    articles = [
        NewsArticle(
            ticker="AAPL",
            timestamp=pd.Timestamp("2018-05-10 07:30:00"),
            headline="Company files for Chapter 11 bankruptcy protection",
            body="Debt restructuring underway following insolvency...",
        )
    ]
    result = classifier.evaluate_candidate(dummy_candidate, articles)
    assert result.is_approved is False
    assert result.status == "REJECTED_EXCLUDED"
    assert "chapter 11" in result.matched_excluded or "bankruptcy" in result.matched_excluded


def test_news_filter_rejects_excluded_even_with_earnings(dummy_candidate):
    """Si contiene resultados pero también fraude/investigación contable, debe prevalecer la exclusión."""
    classifier = NewsClassifier()
    articles = [
        NewsArticle(
            ticker="AAPL",
            timestamp=pd.Timestamp("2018-05-10 07:30:00"),
            headline="Earnings delayed as SEC investigation and accounting investigation launched",
            body="Auditors withdraw opinion citing fraud concerns...",
        )
    ]
    result = classifier.evaluate_candidate(dummy_candidate, articles)
    assert result.is_approved is False
    assert result.status == "REJECTED_EXCLUDED"
    assert any(k in result.matched_excluded for k in ["sec investigation", "fraud", "accounting investigation"])


def test_news_filter_rejects_when_no_news(dummy_candidate):
    classifier = NewsClassifier()
    result = classifier.evaluate_candidate(dummy_candidate, [])
    assert result.is_approved is False
    assert result.status == "REJECTED_NO_NEWS"


def test_news_filter_no_lookahead_timing():
    """Verifica que el gestor de noticias descarte artículos posteriores a la apertura de t+1."""
    event_date = pd.Timestamp("2018-05-10")
    articles_df = pd.DataFrame([
        {
            "ticker": "AAPL",
            "timestamp": "2018-05-09 18:00:00",  # Noche previa a t (válida)
            "headline": "Pre-event guidance update",
        },
        {
            "ticker": "AAPL",
            "timestamp": "2018-05-10 12:00:00",  # Día de t (válida)
            "headline": "Earnings miss announced",
        },
        {
            "ticker": "AAPL",
            "timestamp": "2018-05-11 08:30:00",  # Pre-apertura de t+1 (válida)
            "headline": "Analyst downgrade",
        },
        {
            "ticker": "AAPL",
            "timestamp": "2018-05-11 11:00:00",  # Intradía posterior de t+1 (PROHIBIDA - LOOKAHEAD)
            "headline": "Post-market recovery comment",
        },
        {
            "ticker": "AAPL",
            "timestamp": "2018-05-15 10:00:00",  # Días después (PROHIBIDA - LOOKAHEAD)
            "headline": "Later rebound analysis",
        },
    ])
    mgr = NewsDataManager(articles_df)
    filtered = mgr.get_news_for_event("AAPL", event_date)
    
    headlines = [a.headline for a in filtered]
    assert "Pre-event guidance update" in headlines
    assert "Earnings miss announced" in headlines
    assert "Analyst downgrade" in headlines
    assert "Post-market recovery comment" not in headlines
    assert "Later rebound analysis" not in headlines
