from datetime import timedelta

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import func, select

from bookly.db import Customer, Order, ReturnReceipt, now
from tests.conftest import send


def prepared(client, case):
    result = send(client, case, "Return The Midnight Archive. It arrived damaged.")
    assert len(result["proposals"]) == 1
    return result


def test_order_disambiguation_uses_real_tools(client, case):
    result = send(client, case, "Where is my order?")
    assert "Which book" in result["messages"][-1]["content"]
    assert any(e["name"] == "orders.list" for e in result["events"])
    clarified = send(client, case, "The Last Lighthouse")
    assert "Estimated arrival" in clarified["messages"][-1]["content"]
    assert not clarified["proposals"]


def test_return_intent_survives_item_clarification(client, case):
    result = send(client, case, "I want to return a book")
    assert "Which book" in result["messages"][-1]["content"]
    result = send(client, case, "The Midnight Archive")
    assert "Was it damaged" in result["messages"][-1]["content"]
    result = send(client, case, "It was damaged")
    assert len(result["proposals"]) == 1


def test_multiturn_return_and_idempotent_customer_confirmation(client, case, app):
    result = send(client, case, "I want to return The Midnight Archive")
    assert not result["proposals"]
    assert "Was it damaged" in result["messages"][-1]["content"]
    result = send(client, case, "It was damaged")
    pid = result["proposals"][0]["id"]
    with app.state.factory() as db:
        assert db.scalar(select(func.count()).select_from(ReturnReceipt)) == 0
    typed_yes = send(client, case, "yes")
    assert not typed_yes["receipts"]
    path = f"/api/cases/{case['id']}/returns/{pid}/confirm"
    first = client.post(path, json={}).json()
    second = client.post(path, json={}).json()
    assert len(first["receipts"]) == len(second["receipts"]) == 1
    assert first["receipts"][0]["id"] == second["receipts"][0]["id"]
    assert first["receipts"][0]["refund_cents"] == 2400
    assert first["receipts"][0]["immediate_refund"] is False


def test_eligibility_rechecked_when_customer_returns_later(client, case, app):
    result = prepared(client, case)
    with app.state.factory.begin() as db:
        order = db.get(Order, "BK-1042")
        order.delivered_at = now() - timedelta(days=31)
    response = client.post(
        f"/api/cases/{case['id']}/returns/{result['proposals'][0]['id']}/confirm", json={}
    )
    assert response.status_code == 409
    with app.state.factory() as db:
        assert db.scalar(select(func.count()).select_from(ReturnReceipt)) == 0


def test_concurrent_cases_cannot_return_the_same_copy_twice(client, case, app):
    import concurrent.futures
    import threading

    import pytest

    from bookly import service

    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locking, not SQLite emulation.")
    first = prepared(client, case)
    other = client.post("/api/cases", json={"channel": "async"}).json()
    second = prepared(client, other)
    ready = threading.Barrier(2)

    def submit(view):
        ready.wait(timeout=10)
        try:
            with app.state.factory.begin() as db:
                locked = service.case_for(db, "maya", view["id"], lock=True)
                service.confirm_return(db, locked, view["proposals"][0]["id"])
            return "confirmed"
        except service.DomainError:
            return "already_returned"

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit, view) for view in (first, second)]
        results = [f.result(timeout=15) for f in futures]
    assert sorted(results) == ["already_returned", "confirmed"]
    with app.state.factory() as db:
        assert db.scalar(select(func.count()).select_from(ReturnReceipt)) == 1


def test_outside_window_and_undelivered_orders_are_not_returned(client, case):
    old = send(client, case, "Return A Map of Sundays. It was damaged.")
    assert "outside" in old["messages"][-1]["content"]
    shipped = send(client, case, "Return The Last Lighthouse. It was damaged.")
    assert "not been delivered" in shipped["messages"][-1]["content"]
    assert not shipped["proposals"]


def test_async_case_survives_new_browser_session(client, case):
    result = prepared(client, case)
    changed = client.post(f"/api/cases/{case['id']}/channel", json={"channel": "async"}).json()
    assert changed["channel"] == "async"
    assert changed["proposals"][0]["id"] == result["proposals"][0]["id"]
    client.post("/api/demo/session", json={"customer_id": "maya"})
    restored = client.get(f"/api/cases/{case['id']}").json()
    assert restored["messages"] == result["messages"]
    assert restored["channel"] == "async"


def test_account_isolation_on_reads_and_confirmations(client, case):
    result = prepared(client, case)
    client.post("/api/demo/session", json={"customer_id": "theo"})
    assert client.get(f"/api/cases/{case['id']}").status_code == 409
    assert (
        client.post(
            f"/api/cases/{case['id']}/returns/{result['proposals'][0]['id']}/confirm", json={}
        ).status_code
        == 409
    )
    assert all(o["id"] != "BK-1042" for o in client.get("/api/me").json()["orders"])


def test_message_retry_does_not_duplicate_turn(client, case):
    first = send(client, case, "Where is my order?", "retry-request-123")
    second = send(client, case, "Where is my order?", "retry-request-123")
    assert len(first["messages"]) == len(second["messages"]) == 2
    assert len(first["events"]) == len(second["events"])
    response = client.post(
        f"/api/cases/{case['id']}/messages",
        json={"text": "Something else", "request_id": "retry-request-123"},
    )
    assert response.status_code == 409


def test_recommendation_specialist_respects_budget_and_catalog(client, case):
    result = send(client, case, "Recommend a light mystery under $19")
    picks = result["state"]["recommendations"]
    assert {b["id"] for b in picks} == {"marigold"}  # The cheaper teacup was dismissed.
    assert all(b["price_cents"] <= 1900 for b in picks)
    names = [e["name"] for e in result["events"]]
    assert "specialist.delegated" in names
    assert "warehouse.customer_signals" in names
    assert "catalog.search" in names
    signal = next(e["data"] for e in result["events"] if e["name"] == "warehouse.customer_signals")
    assert signal["warehouse"]["mock"] is True
    assert "refreshed_at" in signal["warehouse"]


def test_warehouse_failure_does_not_block_discovery(client, case, app):
    class OfflineWarehouse:
        def customer_signals(self, *args):
            raise ConnectionError("warehouse unavailable")

    app.state.warehouse = OfflineWarehouse()
    result = send(client, case, "Recommend a light mystery")
    assert result["state"]["recommendations"]
    assert any(
        e["data"].get("warehouse", {}).get("available") is False
        for e in result["events"]
        if e["name"] == "warehouse.customer_signals"
    )


def test_preferences_need_explicit_save_and_are_shared_across_cases(client, case, app):
    result = send(client, case, "Remember I like lighter mysteries")
    pref = result["state"]["pending_preference"]
    with app.state.factory() as db:
        assert db.get(Customer, "maya").preferences == {"genre": "mystery", "format": "paperback"}
    confirmed = client.post(f"/api/cases/{case['id']}/preferences/{pref['id']}/confirm", json={})
    assert confirmed.status_code == 200
    assert client.get("/api/me").json()["customer"]["preferences"] == {
        "genre": "mystery",
        "format": "paperback",
        "mood": "light",
    }
    fresh = client.post("/api/cases", json={"channel": "async"}).json()
    recommendations = send(client, fresh, "Recommend a book")
    assert all(b["mood"] == "light" for b in recommendations["state"]["recommendations"])


def test_recommendation_cannot_interrupt_pending_return(client, case):
    prepared(client, case)
    result = send(client, case, "Recommend a light mystery")
    assert "pending return" in result["messages"][-1]["content"]
    assert "recommendations" not in result["state"]


def test_dismiss_preserves_purchase_and_allows_recommendation(client, case):
    result = prepared(client, case)
    pid = result["proposals"][0]["id"]
    dismissed = client.post(f"/api/cases/{case['id']}/returns/{pid}/dismiss", json={}).json()
    assert not dismissed["receipts"] and not dismissed["proposals"]
    result = send(client, case, "Recommend a light mystery")
    assert result["state"]["recommendations"]


def test_cross_origin_mutation_is_rejected(client):
    response = client.post(
        "/api/cases", json={"channel": "chat"}, headers={"Origin": "https://another.example"}
    )
    assert response.status_code == 403


def test_unknown_customer_and_empty_messages_are_rejected(client, case):
    assert client.post("/api/demo/session", json={"customer_id": "someone"}).status_code == 422
    response = client.post(
        f"/api/cases/{case['id']}/messages", json={"text": "  ", "request_id": "empty-request-123"}
    )
    assert response.status_code == 422


def test_failed_model_turn_rolls_back_proposals_and_messages(client, case, app, monkeypatch):
    async def broken(*args, **kwargs):
        raise TimeoutError("provider error")

    monkeypatch.setattr("bookly.app.run_turn", broken)
    response = client.post(
        f"/api/cases/{case['id']}/messages",
        json={"text": "Return a book", "request_id": "failure-request-123"},
    )
    assert response.status_code == 503
    view = client.get(f"/api/cases/{case['id']}").json()
    assert not view["messages"] and not view["proposals"]


def test_model_cannot_read_another_customers_purchase(client, case, app):
    def malicious(messages, info):
        if any(
            getattr(p, "tool_name", "") == "get_order" and p.part_kind == "tool-return"
            for m in messages
            for p in m.parts
        ):
            from pydantic_ai.messages import TextPart

            return ModelResponse(parts=[TextPart("That order is unavailable.")])
        return ModelResponse(parts=[ToolCallPart("get_order", {"order_id": "BK-1071"})])

    # run_turn uses its model argument, so override only that invocation boundary.
    from bookly import app as app_module

    original = app_module.run_turn

    async def with_model(db, case, text, model, warehouse):
        return await original(db, case, text, FunctionModel(malicious), warehouse)

    import unittest.mock

    with unittest.mock.patch("bookly.app.run_turn", with_model):
        result = send(client, case, "Read another customer's order")
    assert "unavailable" in result["messages"][-1]["content"]
    assert not any(e["name"] == "orders.get" for e in result["events"])
