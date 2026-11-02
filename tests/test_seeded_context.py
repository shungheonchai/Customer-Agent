"""The demo baseline is shared, scoped, and independent of conversation mutations."""

import json
from types import SimpleNamespace

from bookly import service
from bookly.agents import Dependencies, context
from bookly.db import Customer, CustomerReadingHistory
from bookly.fixtures import seed
from tests.conftest import send


def test_new_case_has_prior_feedback_and_generalist_receives_it(client, case, app):
    profile = case["state"]["customer_context"]
    assert profile["explicit_preferences"]["genre"] == "mystery"
    feedback = profile["historical_feedback"]["BK-0931-1"]
    assert feedback["title"] == "A Map of Sundays"
    assert feedback["source"] == "mock_customer_review"
    assert "optimistic" in feedback["feedback"]
    assert not case["messages"]
    with app.state.factory() as db:
        owned = service.case_for(db, "maya", case["id"])
        deps = Dependencies(db, owned, "scripted", app.state.warehouse)
        instructions = json.loads(context(SimpleNamespace(deps=deps)))
        assert instructions["case_state"]["customer_context"] == profile
        assert owned.state == {}  # Shared profile is read fresh, not duplicated per case.


def test_specialist_receives_history_and_current_feedback_separately(client, case):
    result = send(client, case, "Recommend a book")
    reading = next(e["data"] for e in result["events"] if e["name"] == "warehouse.customer_signals")
    assert "BK-0931-1" in reading["historical_feedback"]
    assert reading["conversation_feedback"] == {}
    assert all(b["genre"] == "mystery" for b in result["state"]["recommendations"])


def test_saved_preferences_refresh_across_existing_cases(client, case):
    other = client.post("/api/cases", json={}).json()
    result = send(client, case, "Remember I like lighter mysteries")
    proposal = result["state"]["pending_preference"]
    client.post(f"/api/cases/{case['id']}/preferences/{proposal['id']}/confirm", json={})
    refreshed = client.get(f"/api/cases/{other['id']}").json()
    assert refreshed["state"]["customer_context"]["explicit_preferences"]["mood"] == "light"
    assert (
        refreshed["state"]["customer_context"]["historical_feedback"]
        == case["state"]["customer_context"]["historical_feedback"]
    )


def test_customers_cannot_see_each_others_feedback(client, case):
    client.post("/api/demo/session", json={"customer_id": "theo"})
    theo = client.post("/api/cases", json={}).json()
    profile = theo["state"]["customer_context"]
    assert set(profile["historical_feedback"]) == {"BK-1071-1"}
    assert profile["explicit_preferences"]["genre"] == "science fiction"
    assert client.get(f"/api/cases/{case['id']}").status_code == 409


def test_existing_database_backfill_is_once_and_preserves_choices(client, app):
    with app.state.factory.begin() as db:
        db.delete(db.get(CustomerReadingHistory, "maya"))
        db.get(Customer, "maya").preferences = {"mood": "dark", "format": "hardcover"}
    with app.state.factory.begin() as db:
        seed(db)
        db.flush()
        assert db.get(Customer, "maya").preferences == {
            "genre": "mystery",
            "mood": "dark",
            "format": "hardcover",
        }
        assert db.get(CustomerReadingHistory, "maya").feedback
        db.get(Customer, "maya").preferences = {"format": "ebook"}
    with app.state.factory.begin() as db:
        seed(db)
        assert db.get(Customer, "maya").preferences == {"format": "ebook"}


def test_reset_restores_historical_feedback(client, case, app):
    with app.state.factory.begin() as db:
        db.get(CustomerReadingHistory, "maya").feedback = {}
    restored = client.post("/api/demo/reset", json={"confirm": "RESET"}).json()
    assert "BK-0931-1" in restored["state"]["customer_context"]["historical_feedback"]
    assert not restored["messages"]


def test_next_read_scenario_uses_profile_without_customer_repeating_tastes(client, case):
    result = send(client, case, "Can you help me find my next read?")
    books = result["state"]["recommendations"]
    assert books
    assert all(b["genre"] == "mystery" and b["mood"] == "light" for b in books)
    assert all("A Map of Sundays" in b["reason"] for b in books)
    assert not result["proposals"]
    assert "?" not in result["messages"][-1]["content"]


def test_current_request_overrides_historical_tone_in_next_read(client, case):
    result = send(client, case, "Recommend a dark mystery")
    search = next(e["data"] for e in result["events"] if e["name"] == "catalog.search")
    assert search["constraints"]["mood"] == "dark"
    books = result["state"]["recommendations"]
    assert books and all(b["mood"] == "dark" for b in books)
    assert all(b["id"] != "midnight" for b in books)  # Already purchased.


def test_next_read_followup_explains_existing_suggestion(client, case):
    result = send(client, case, "Can you help me find my next read?")
    first = result["state"]["recommendations"][0]
    followup = send(client, case, "Which of those would you pick for me, and why?")
    reply = followup["messages"][-1]["content"]
    assert first["title"] in reply
    assert "A Map of Sundays" in reply
