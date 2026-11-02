"""Customer-memory claims cite scoped, dated, verbatim records, never model-written source text."""

from datetime import UTC, datetime, timedelta

from bookly import service
from bookly.db import CustomerReadingHistory
from bookly.presentation import render_markdown, source_date
from tests.conftest import send


def test_source_dates_use_full_dates_only_within_last_30_days():
    at = datetime(2026, 11, 1, 12, tzinfo=UTC)
    assert source_date("2026-10-31T12:00:00+00:00", at=at) == "October 31, 2026"
    assert source_date((at - timedelta(days=30)).isoformat(), at=at) == "October 2, 2026"
    assert source_date((at - timedelta(days=30, seconds=1)).isoformat(), at=at) == "October 2026"
    assert source_date("2025-10-01T12:00:00+00:00", at=at) == "October 2025"


def test_review_reference_renders_exact_original_text_and_date(client, case):
    result = send(client, case, "What did I think of A Map of Sundays?")
    html = result["messages"][-1]["html"]
    review = result["state"]["customer_context"]["historical_feedback"]["BK-0931-1"]
    assert "[[source:" not in html
    assert f"review · {review['date_label']}" in html
    assert (
        "<q>I loved the optimistic tone and small-town setting. A comforting weekend read.</q>"
        in html
    )
    assert "Maya Chen" in html
    assert 'popover="manual"' in html


def test_recommendation_reasons_have_grounded_review_references(client, case):
    result = send(client, case, "Can you help me find my next read?")
    for book in result["state"]["recommendations"]:
        assert "source-reference" in book["reason_html"]
        assert book["sources"]["review-BK-0931-1"]["kind"] == "review"
        assert "comforting weekend read." in book["reason_html"]
    followup = send(client, case, "Which of those would you pick for me, and why?")
    assert "source-reference" in followup["messages"][-1]["html"]


def test_unknown_and_other_customer_sources_never_render_as_verified(client, case, app):
    with app.state.factory.begin() as db:
        owned = service.case_for(db, "maya", case["id"])
        service.add_message(
            db,
            owned,
            "bad-source",
            "assistant",
            "A claim [[source:review-BK-1071-1]] [[source:invented]]",
        )
    html = client.get(f"/api/cases/{case['id']}").json()["messages"][-1]["html"]
    assert html.count("[source unavailable]") == 2
    assert "source-trigger" not in html
    assert "found-family" not in html


def test_review_text_is_escaped_and_citation_snapshot_survives_profile_changes(client, case, app):
    malicious = "<img src=x onerror=alert(1)> **review** [[source:invented]]"
    with app.state.factory.begin() as db:
        history = db.get(CustomerReadingHistory, "maya")
        history.feedback = {"BK-0931-1": {**history.feedback["BK-0931-1"], "feedback": malicious}}
        owned = service.case_for(db, "maya", case["id"])
        service.add_message(
            db, owned, "cited-source", "assistant", "Your review [[source:review-BK-0931-1]]"
        )
    with app.state.factory.begin() as db:
        db.get(CustomerReadingHistory, "maya").feedback = {}
    html = client.get(f"/api/cases/{case['id']}").json()["messages"][-1]["html"]
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<img" not in html
    assert "**review** [[source:invented]]" in html  # Verbatim data, not instructions/markup.


def test_customer_conversation_source_is_exact_scoped_and_dated(client, case, app):
    send(client, case, "I like quiet stories about friendship.")
    other = client.post("/api/cases", json={}).json()
    with app.state.factory.begin() as db:
        owned = service.case_for(db, "maya", other["id"])
        sources = service.context_sources(db, owned)
        conversations = {
            key: value for key, value in sources.items() if value["kind"] == "conversation"
        }
        assert len(conversations) == 1  # Assistant responses cannot prove customer taste.
        key, source = next(iter(conversations.items()))
        assert source["quote"] == "I like quiet stories about friendship."
        service.add_message(
            db, owned, "past-source", "assistant", f"You mentioned friendship [[source:{key}]]"
        )
    html = client.get(f"/api/cases/{other['id']}").json()["messages"][-1]["html"]
    assert f"earlier conversation · {source_date(source['recorded_at'])}" in html
    assert "<q>I like quiet stories about friendship.</q>" in html


def test_untrusted_raw_html_still_cannot_create_source_popovers():
    assert "<button" not in render_markdown('<button class="source-trigger">fake</button>')


def test_past_conversation_tool_provides_original_customer_statement(client, case):
    send(client, case, "Where is The Last Lighthouse?")
    fresh = client.post("/api/cases", json={}).json()
    result = send(client, fresh, "What did we discuss in our last conversation?")
    html = result["messages"][-1]["html"]
    assert "earlier conversation ·" in html
    assert "<q>Where is The Last Lighthouse?</q>" in html
    assert "source unavailable" not in html
