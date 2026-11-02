from datetime import timedelta

import pytest
from sqlalchemy import func, select

from bookly.db import Case, Customer, Event, Message, Order, ReturnReceipt, now
from bookly.presentation import render_markdown
from tests.conftest import send


def test_reset_restores_fixtures_and_clears_all_customer_history(client, case, app):
    result = send(client, case, "Return The Midnight Archive. It arrived damaged.")
    pid = result["proposals"][0]["id"]
    assert client.post(f"/api/cases/{case['id']}/returns/{pid}/confirm", json={}).status_code == 200
    with app.state.factory.begin() as db:
        db.get(Customer, "maya").preferences = {"mood": "dark"}
        db.get(Customer, "theo").preferences = {"genre": "mystery"}
        db.get(Order, "BK-1042").delivered_at = now() - timedelta(days=100)
    result = client.post("/api/demo/reset", json={"confirm": "RESET", "channel": "async"})
    assert result.status_code == 200
    fresh = result.json()
    assert fresh["id"] != case["id"]
    assert fresh["channel"] == "async"
    assert not fresh["messages"] and not fresh["events"] and not fresh["receipts"]
    assert client.get(f"/api/cases/{case['id']}").status_code == 409
    assert client.get("/api/me").status_code == 200  # same customer cookie still works
    with app.state.factory() as db:
        assert db.get(Customer, "maya").preferences == {"genre": "mystery", "format": "paperback"}
        assert db.get(Customer, "theo").preferences == {
            "genre": "science fiction",
            "format": "paperback",
            "mood": "hopeful",
        }
        assert db.scalar(select(func.count()).select_from(ReturnReceipt)) == 0
        assert db.scalar(select(func.count()).select_from(Message)) == 0
        assert db.scalar(select(func.count()).select_from(Event)) == 0
        assert db.scalar(select(func.count()).select_from(Case)) == 1
    repeated = send(client, fresh, "Return The Midnight Archive. It arrived damaged.")
    assert repeated["proposals"][0]["eligible"] is True


def test_reset_requires_explicit_confirmation_and_same_origin(client, case):
    assert client.post("/api/demo/reset", json={}).status_code == 422
    assert client.post("/api/demo/reset", json={"confirm": "yes"}).status_code == 422
    assert (
        client.post(
            "/api/demo/reset",
            json={"confirm": "RESET"},
            headers={"Origin": "https://elsewhere.example"},
        ).status_code
        == 403
    )
    assert client.get(f"/api/cases/{case['id']}").status_code == 200


def test_reset_rolls_back_if_reseeding_fails(client, case, monkeypatch):
    send(client, case, "Where is my order?")
    original = client.get(f"/api/cases/{case['id']}").json()
    from bookly import fixtures

    def fail(*args, **kwargs):
        raise RuntimeError("test fixture failure")

    monkeypatch.setattr(fixtures, "seed", fail)
    with pytest.raises(RuntimeError):
        client.post("/api/demo/reset", json={"confirm": "RESET"})
    restored = client.get(f"/api/cases/{case['id']}").json()
    assert restored["messages"] == original["messages"]
    assert restored["events"] == original["events"]


def test_reset_waits_for_inflight_turn_before_clearing_it(client, case, app, monkeypatch):
    import asyncio
    import concurrent.futures
    import threading

    from bookly import fixtures

    entered, release, resetting = threading.Event(), threading.Event(), threading.Event()
    original_reset = fixtures.reset_demo

    async def slow_turn(*args, **kwargs):
        entered.set()
        await asyncio.to_thread(release.wait, 5)
        return "This response must be cleared by reset."

    def observed_reset(db):
        resetting.set()
        return original_reset(db)

    monkeypatch.setattr("bookly.app.run_turn", slow_turn)
    monkeypatch.setattr("bookly.app.reset_demo", observed_reset)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        turn = pool.submit(
            client.post,
            f"/api/cases/{case['id']}/messages",
            json={"text": "Where is my order?", "request_id": "reset-race-test"},
        )
        assert entered.wait(timeout=5)
        reset = pool.submit(client.post, "/api/demo/reset", json={"confirm": "RESET"})
        try:
            assert not resetting.wait(timeout=0.1)
        finally:
            release.set()
        assert turn.result(timeout=10).status_code == 200
        assert reset.result(timeout=10).status_code == 200
    with app.state.factory() as db:
        assert db.scalar(select(func.count()).select_from(Message)) == 0


def test_formatted_assistant_messages_and_plain_user_messages(client, case, app):
    from bookly.service import add_message, case_for

    with app.state.factory.begin() as db:
        owned = case_for(db, "maya", case["id"])
        add_message(db, owned, "format-request", "user", "**My words**")
        add_message(
            db,
            owned,
            "format-request",
            "assistant",
            "**Your return**\n\n- First step\n- Second step",
        )
    messages = client.get(f"/api/cases/{case['id']}").json()["messages"]
    assert messages[0]["html"] is None
    assert "<strong>Your return</strong>" in messages[1]["html"]
    assert "<ul>" in messages[1]["html"] and "<li>First step</li>" in messages[1]["html"]


@pytest.mark.parametrize(
    "text",
    [
        '<script>alert("x")</script>',
        "<img src=x onerror=alert(1)>",
        "[unsafe](javascript:alert(1))",
        "![tracking](https://tracking.example/image.png)",
    ],
)
def test_markdown_does_not_execute_html_or_load_images(text):
    result = render_markdown(text)
    assert "<script" not in result and "<img" not in result
    assert 'href="javascript:' not in result


def test_markdown_formats_code_and_safe_links():
    result = render_markdown("Use `RET-123` and [instructions](https://example.com/returns).")
    assert "<code>RET-123</code>" in result
    assert 'href="https://example.com/returns"' in result
