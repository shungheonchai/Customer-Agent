import pytest

from bookly import service
from bookly.db import Customer
from tests.conftest import send


def test_vague_taste_return_progresses_while_asking_one_optional_question(client, case):
    send(client, case, "I want to return The Midnight Archive")
    result = send(client, case, "The book wasn't for me.")
    reply = result["messages"][-1]["content"]
    assert len(result["proposals"]) == 1
    assert "confirm without sharing" in reply
    assert reply.count("?") == 1
    assert not result["receipts"]
    # Feedback is optional: confirmation works with no diagnostic answer.
    confirmed = client.post(
        f"/api/cases/{case['id']}/returns/{result['proposals'][0]['id']}/confirm", json={}
    )
    assert confirmed.status_code == 200
    assert len(confirmed.json()["receipts"]) == 1


def test_feedback_informs_invited_specialist_without_becoming_profile_memory(client, case, app):
    send(client, case, "Return The Midnight Archive. The book wasn't for me.")
    feedback = "It was too dark for me. I prefer light mysteries."
    result = send(client, case, feedback)
    assert result["state"]["reading_feedback"]["BK-1042-1"]["feedback"] == feedback
    assert "?" not in result["messages"][-1]["content"]
    assert "recommendations" not in result["state"]
    client.post(f"/api/cases/{case['id']}/returns/{result['proposals'][0]['id']}/confirm", json={})
    result = send(client, case, "Recommend a light mystery under $22")
    context = next(e["data"] for e in result["events"] if e["name"] == "warehouse.customer_signals")
    assert context["conversation_feedback"]["BK-1042-1"]["feedback"] == feedback
    assert result["state"]["recommendations"]
    assert all(b["mood"] == "light" for b in result["state"]["recommendations"])
    with app.state.factory() as db:
        assert db.get(Customer, "maya").preferences == {"genre": "mystery", "format": "paperback"}


def test_specific_feedback_is_not_asked_again_and_refusal_stops_questions(client, case):
    result = send(client, case, "Return The Midnight Archive. It was too dark for me.")
    assert len(result["proposals"]) == 1
    assert "?" not in result["messages"][-1]["content"]
    result = send(client, case, "No thanks, just the return.")
    assert "?" not in result["messages"][-1]["content"]
    assert len(result["proposals"]) == 1
    assert "recommendations" not in result["state"]


def test_refund_only_request_skips_diagnosis_and_discovery(client, case):
    result = send(
        client,
        case,
        "Return The Midnight Archive. It wasn't for me. Just the refund, I'm in a hurry.",
    )
    assert len(result["proposals"]) == 1
    assert "?" not in result["messages"][-1]["content"]
    assert "reading_feedback" not in result["state"]
    assert "recommendations" not in result["state"]


def test_feedback_cannot_attach_another_customers_purchase(client, case, app):
    with app.state.factory.begin() as db:
        owned = service.case_for(db, "maya", case["id"])
        with pytest.raises(service.DomainError):
            service.record_reading_feedback(db, owned, "BK-1071-1", "Not my taste")
        assert "reading_feedback" not in owned.state
