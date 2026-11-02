from bookly.channel_prompts import CHANNEL_PROMPTS, active_prompt
from tests.conftest import send


def test_saved_conversation_has_grounded_recap_and_can_be_resumed(client, case):
    result = send(client, case, "Where is my order?")
    send(client, case, "The Last Lighthouse")
    fresh = client.post("/api/cases", json={"channel": "chat"}).json()
    saved = next(c for c in client.get("/api/me").json()["cases"] if c["id"] == case["id"])
    assert saved["request"] == "Where is my order?"
    assert "order questions" in saved["text"]
    assert "The Last Lighthouse" in saved["latest_reply"]
    assert saved["message_count"] == 4
    assert saved["method"] == "message_extracts_and_recorded_actions"
    assert fresh["messages"] == []
    resumed = client.get(f"/api/cases/{case['id']}").json()
    assert resumed["messages"][0]["content"] == result["messages"][0]["content"]
    assert resumed["summary"] == saved


def test_recap_distinguishes_proposal_from_recorded_return(client, case):
    prepared = send(client, case, "Return The Midnight Archive. It arrived damaged.")
    assert prepared["summary"]["status"] == "awaiting_confirmation"
    assert "no return request submitted" in prepared["summary"]["outcome"]
    pid = prepared["proposals"][0]["id"]
    confirmed = client.post(f"/api/cases/{case['id']}/returns/{pid}/confirm", json={}).json()
    assert confirmed["summary"]["status"] == "return_requested"
    assert confirmed["receipts"][0]["id"] in confirmed["summary"]["outcome"]
    assert "refund not yet issued" in confirmed["summary"]["outcome"]


def test_agent_can_retrieve_previous_contacts_without_exposing_other_customers(client, case):
    send(client, case, "Where is The Last Lighthouse?")
    client.post("/api/demo/session", json={"customer_id": "theo"})
    theo = client.post("/api/cases", json={"channel": "chat"}).json()
    send(client, theo, "Where is An Orbit of Our Own?")
    client.post("/api/demo/session", json={"customer_id": "maya"})
    fresh = client.post("/api/cases", json={"channel": "chat"}).json()
    result = send(client, fresh, "What did we discuss in our last conversation?")
    assert "The Last Lighthouse" in result["messages"][-1]["content"]
    assert "An Orbit" not in result["messages"][-1]["content"]
    event = next(e for e in result["events"] if e["name"] == "memory.past_conversations")
    assert event["data"]["case_ids"] == [case["id"]]
    assert all(c["id"] != theo["id"] for c in client.get("/api/me").json()["cases"])


def test_channel_prompt_comparison_is_reference_only_except_chat(client):
    data = client.get("/api/demo/channel-prompts").json()
    assert data["active"] == "chat"
    assert {p["channel"]: p["implemented"] for p in data["profiles"]} == {
        "chat": True,
        "sms": False,
        "voice": False,
    }
    assert "plain-text" in CHANNEL_PROMPTS["sms"]
    assert "interrupt" in CHANNEL_PROMPTS["voice"]
    assert active_prompt("async") == CHANNEL_PROMPTS["chat"]


def test_reset_removes_previous_recaps_as_well_as_history(client, case):
    send(client, case, "Where is my order?")
    client.post("/api/demo/reset", json={"confirm": "RESET"})
    assert not any(c["message_count"] for c in client.get("/api/me").json()["cases"])
