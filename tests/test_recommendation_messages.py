"""Recommendation cards stay with their originating reply across topic changes."""

from tests.conftest import send


def test_policy_question_does_not_repeat_recommendation_cards(client, case):
    recommended = send(client, case, "Can you help me find my next read?")
    reply = recommended["messages"][-1]
    assert reply["recommendations"] == recommended["state"]["recommendations"]
    result = send(client, case, "What is your return policy?")
    assert result["messages"][-1]["recommendations"] == []
    assert result["messages"][-1]["content"] != reply["content"]
    original = next(m for m in result["messages"] if m["id"] == reply["id"])
    assert original["recommendations"] == reply["recommendations"]
    assert (
        result["state"]["recommendations"] == reply["recommendations"]
    )  # Follow-ups retain context.
    reloaded = client.get(f"/api/cases/{case['id']}").json()
    assert reloaded["messages"] == result["messages"]


def test_new_recommendations_keep_both_sets_with_their_own_replies(client, case):
    light = send(client, case, "Recommend a light mystery under $22")
    first = light["messages"][-1]
    dark = send(client, case, "Recommend a dark mystery under $22")
    second = dark["messages"][-1]
    assert all(b["mood"] == "dark" for b in second["recommendations"])
    assert all(
        b["mood"] == "light"
        for b in next(m for m in dark["messages"] if m["id"] == first["id"])["recommendations"]
    )
    assert not dark["messages"][-2]["recommendations"]  # User message has no attachments.


def test_followup_can_reference_books_without_duplicating_cards(client, case):
    original = send(client, case, "Can you help me find my next read?")
    followup = send(client, case, "Which of those would you pick for me, and why?")
    assert original["state"]["recommendations"][0]["title"] in followup["messages"][-1]["content"]
    assert followup["messages"][-1]["recommendations"] == []
    assert sum(bool(m["recommendations"]) for m in followup["messages"]) == 1
