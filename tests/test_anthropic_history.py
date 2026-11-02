import asyncio
import json

import httpx
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ThinkingPart, UserPromptPart

from bookly.agents import run_turn
from bookly.models import configured_model
from bookly.service import case_for
from bookly.warehouse import MockDataWarehouse


def test_signed_thinking_stays_inside_tool_turn_but_is_not_replayed_next_turn(client, case, app):
    requests = []

    async def transport(request):
        body = json.loads(request.content)
        requests.append(body)
        thinking = [
            p
            for m in body["messages"]
            if isinstance(m["content"], list)
            for p in m["content"]
            if p.get("type") == "thinking"
        ]
        if len(requests) == 1:
            content = [
                {
                    "type": "thinking",
                    "thinking": "Fixture reasoning",
                    "signature": "signed-tool-turn",
                },
                {
                    "type": "tool_use",
                    "id": "order-call",
                    "name": "check_return_eligibility",
                    "input": {"item_id": "BK-1042-1"},
                },
            ]
            stop = "tool_use"
        elif len(requests) == 2:
            # The live tool loop must keep signatures unchanged inside this turn.
            assert thinking[0]["signature"] == "signed-tool-turn"
            assert body["system"] == requests[0]["system"]
            content = [
                {
                    "type": "thinking",
                    "thinking": "Fixture final reasoning",
                    "signature": "signed-completed-turn",
                },
                {"type": "text", "text": "Which order did you mean?"},
            ]
            stop = "end_turn"
        else:
            # Reproduce the gateway's signature rejection if old thinking survives.
            if thinking:
                return httpx.Response(
                    400,
                    json={
                        "type": "error",
                        "error": {
                            "type": "invalid_request_error",
                            "message": "Invalid signature in thinking block: system prompt differs.",
                        },
                    },
                )
            assert body["system"] != requests[0]["system"]
            assert "Which order did you mean?" in str(body["messages"])
            assert "tool_result" in str(body["messages"])
            content = [{"type": "text", "text": "The Last Lighthouse has shipped."}]
            stop = "end_turn"
        return httpx.Response(
            200,
            json={
                "id": f"msg-{len(requests)}",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5-5",
                "content": content,
                "stop_reason": stop,
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http_client:
            model = configured_model(
                {
                    "LLM_PROVIDER": "anthropic",
                    "LLM_MODEL": "claude-sonnet-5-5",
                    "LLM_API_KEY": "fixture-key",
                    "LLM_BASE_URL": "https://gateway.example.test/anthropic",
                },
                http_client=http_client,
            )
            with app.state.factory.begin() as db:
                owned = case_for(db, "maya", case["id"])
                assert await run_turn(db, owned, "Where is my order?", model, MockDataWarehouse())
                # A meaningful dynamic context update changes the next system prompt.
                owned.state = {**owned.state, "selected_item_id": "BK-1086-1"}
                reply = await run_turn(
                    db, owned, "I mean The Last Lighthouse.", model, MockDataWarehouse()
                )
                assert "has shipped" in reply
                assert not any(
                    p["part_kind"] == "thinking" for m in owned.model_history for p in m["parts"]
                )

    asyncio.run(exercise())
    assert len(requests) == 3


def test_legacy_thinking_removal_preserves_messages_and_other_provider_history():
    from bookly.agents import completed_turn_history

    history = [
        ModelRequest(parts=[UserPromptPart("Where is my order?")]),
        ModelResponse(
            parts=[
                ThinkingPart(
                    "Private fixture reasoning", signature="legacy", provider_name="anthropic"
                ),
                TextPart("Which book?"),
            ],
            provider_name="anthropic",
        ),
        ModelResponse(
            parts=[ThinkingPart("Only thinking", signature="legacy-2", provider_name="anthropic")]
        ),
    ]

    class Anthropic:
        system = "anthropic"

    class Other:
        system = "openai"

    cleaned = completed_turn_history(history, Anthropic())
    assert len(cleaned) == 2
    assert cleaned[0] is history[0]
    assert [p.content for p in cleaned[1].parts] == ["Which book?"]
    assert len(history[1].parts) == 2  # original loaded history is not mutated
    assert completed_turn_history(history, Other()) == history
