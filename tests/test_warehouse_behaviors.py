"""Behavioral activity changes ranking, respects constraints, and has traceable evidence."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace

from bookly import service
from bookly.agents import Dependencies, Pick, ReadingAdvice, recommend_books
from bookly.db import WarehouseSnapshot, now
from bookly.fixtures import seed
from bookly.warehouse import MockDataWarehouse
from tests.conftest import send


def test_wishlist_and_browsing_change_order_and_dismissal_removes_book(client, case):
    result = send(client, case, "Can you help me find my next read?")
    books = result["state"]["recommendations"]
    assert [b["id"] for b in books] == ["orchard", "lantern"]
    search = next(e["data"] for e in result["events"] if e["name"] == "catalog.search")
    assert "teacup" not in {b["id"] for b in search["candidates"]}
    assert "wishlist activity ·" in books[0]["reason_html"]
    assert "browsing activity ·" in books[1]["reason_html"]
    assert "Added The Orchard House Puzzle to the wishlist." in books[0]["reason_html"]
    assert "Viewed The Lantern Club 3 time(s)" in books[1]["reason_html"]
    assert "<q>Added" not in books[0]["reason_html"]  # Telemetry isn't a customer quote.
    followup = send(client, case, "Which of those would you pick for me, and why?")
    assert "wishlist activity ·" in followup["messages"][-1]["html"]


def test_budget_and_mood_override_wishlist_and_typical_spend_is_not_budget(client, case):
    cheap = send(client, case, "Recommend a light mystery under $19")
    assert [b["id"] for b in cheap["state"]["recommendations"]] == ["marigold"]
    dark = send(client, case, "Recommend a dark mystery under $22")
    assert [b["id"] for b in dark["state"]["recommendations"]] == ["glass"]
    client.post("/api/demo/session", json={"customer_id": "theo"})
    theo = client.post("/api/cases", json={}).json()
    result = send(client, theo, "Can you help me find my next read?")
    assert [b["id"] for b in result["state"]["recommendations"]] == ["seedship", "signal"]
    assert result["state"]["recommendations"][0]["price_cents"] == 3200  # Typical spend is $21.


def test_removing_behavior_changes_results_without_changing_preferences(client, case, app):
    original = send(client, case, "Can you help me find my next read?")
    with app.state.factory.begin() as db:
        snapshot = db.get(WarehouseSnapshot, "maya")
        snapshot.signals = {
            **snapshot.signals,
            "wishlist_items": [],
            "recently_viewed": [],
            "dismissed_recommendations": [],
        }
    updated = send(client, case, "Can you help me find my next read?")
    assert [b["id"] for b in updated["state"]["recommendations"]] == ["teacup", "marigold"]
    assert (
        updated["state"]["customer_context"]["explicit_preferences"]
        == original["state"]["customer_context"]["explicit_preferences"]
    )


def test_backend_rejects_dismissed_book_even_if_specialist_selects_it(
    client, case, app, monkeypatch
):
    async def invalid_pick(*args, **kwargs):
        return SimpleNamespace(
            output=ReadingAdvice(picks=[Pick(book_id="teacup", reason="A cheap mystery.")], note="")
        )

    monkeypatch.setattr("bookly.agents.specialist.run", invalid_pick)
    with app.state.factory.begin() as db:
        owned = service.case_for(db, "maya", case["id"])
        deps = Dependencies(db, owned, "scripted", MockDataWarehouse())
        result = asyncio.run(
            recommend_books(SimpleNamespace(deps=deps), request="Find my next read")
        )
        assert result["books"] == []


def test_stale_snapshot_does_not_exclude_or_promote_books(client, case, app):
    with app.state.factory.begin() as db:
        db.get(WarehouseSnapshot, "maya").refreshed_at = now() - timedelta(days=8)
    result = send(client, case, "Can you help me find my next read?")
    assert [b["id"] for b in result["state"]["recommendations"]] == ["teacup", "marigold"]
    snapshot = next(
        e["data"]["warehouse"]
        for e in result["events"]
        if e["name"] == "warehouse.customer_signals"
    )
    assert snapshot["available"] is False and snapshot["signals"] == {}
    assert "seven days" in snapshot["reason"]


def test_expired_malformed_future_and_unknown_activity_is_ignored(client, app):
    with app.state.factory.begin() as db:
        snapshot = db.get(WarehouseSnapshot, "maya")
        snapshot.signals = {
            "wishlist_items": [
                {"book_id": "unknown", "recorded_at": now().isoformat()},
                {"book_id": "orchard", "recorded_at": "bad-date"},
            ],
            "recently_viewed": [
                {"book_id": "lantern", "recorded_at": (now() - timedelta(days=31)).isoformat()}
            ],
            "dismissed_recommendations": [
                {"book_id": "teacup", "recorded_at": (now() + timedelta(days=1)).isoformat()},
                {"book_id": "marigold", "recorded_at": (now() - timedelta(days=91)).isoformat()},
            ],
        }
        assert MockDataWarehouse().customer_signals(db, "maya")["behavioral_evidence"] == []


def test_upgrade_is_once_only_and_preserves_explicit_empty_lists(client, app):
    with app.state.factory.begin() as db:
        snapshot = db.get(WarehouseSnapshot, "maya")
        snapshot.signals = {"wishlist_items": [], "custom_signal": "keep"}
        seed(db)
        assert snapshot.signals["wishlist_items"] == []
        assert snapshot.signals["recently_viewed"]
        assert snapshot.signals["custom_signal"] == "keep"
        snapshot.signals = {**snapshot.signals, "recently_viewed": []}
        seed(db)
        assert snapshot.signals["recently_viewed"] == []


def test_behavior_sources_cannot_cross_customer_boundary(client, case, app):
    with app.state.factory.begin() as db:
        owned = service.case_for(db, "maya", case["id"])
        sources = service.context_sources(db, owned)
        assert "activity-maya-wishlist-orchard" in sources
        assert "activity-theo-wishlist-seedship" not in sources
        service.add_message(
            db,
            owned,
            "cross-customer-activity",
            "assistant",
            "Evidence [[source:activity-theo-wishlist-seedship]]",
        )
    result = client.get(f"/api/cases/{case['id']}").json()
    assert "source unavailable" in result["messages"][-1]["html"]


def test_one_adapter_read_is_shared_across_a_consultation(client, case, app):
    class CountingWarehouse(MockDataWarehouse):
        calls = 0

        def customer_signals(self, *args):
            self.calls += 1
            return super().customer_signals(*args)

    app.state.warehouse = CountingWarehouse()
    send(client, case, "Can you help me find my next read?")
    assert app.state.warehouse.calls == 1
