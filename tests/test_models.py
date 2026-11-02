import asyncio
import json

import httpx
import pytest

from bookly.agents import run_turn
from bookly.models import configured_model, model_details
from bookly.service import case_for
from bookly.warehouse import MockDataWarehouse


def gateway_env():
    return {
        "LLM_PROVIDER": "anthropic",
        "LLM_BASE_URL": "https://gateway.example.test/anthropic",
        "LLM_API_KEY": "test-gateway-key-not-a-secret",
        "LLM_MODEL": "gateway-test-model",
    }


def test_anthropic_specialist_validates_json_without_forced_tool_choice(client, case, app):
    from types import SimpleNamespace

    from bookly.agents import Dependencies, recommend_books

    requests = []

    async def transport(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body.get("tool_choice", {}).get("type", "auto") == "auto"
        assert not any(t["name"] == "final_result" for t in body.get("tools", []))
        if len(requests) <= 2:
            content = [
                {
                    "type": "tool_use",
                    "id": f"call-{len(requests)}",
                    "name": "get_reading_context" if len(requests) == 1 else "find_catalog_books",
                    "input": {},
                }
            ]
            stop = "tool_use"
        else:
            content = [
                {
                    "type": "text",
                    "text": json.dumps(
                        {"picks": [], "note": "No suitable candidates in this fixture."}
                    ),
                }
            ]
            stop = "end_turn"
        return httpx.Response(
            200,
            json={
                "id": f"msg-{len(requests)}",
                "type": "message",
                "role": "assistant",
                "model": "gateway-test-model",
                "content": content,
                "stop_reason": stop,
                "usage": {"input_tokens": 5, "output_tokens": 5},
            },
        )

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http_client:
            model = configured_model(gateway_env(), http_client=http_client)
            with app.state.factory.begin() as db:
                deps = Dependencies(
                    db, case_for(db, "maya", case["id"]), model, MockDataWarehouse()
                )
                result = await recommend_books(
                    SimpleNamespace(deps=deps), "A lighter mystery", mood="light"
                )
                assert result == {"books": [], "note": "No suitable candidates in this fixture."}

    asyncio.run(exercise())
    assert len(requests) == 3


def test_scripted_startup_needs_no_corporate_access_or_key():
    assert configured_model({}) == "scripted"


@pytest.mark.parametrize("provider", ["", " ", "\t\n"])
def test_empty_provider_selects_scripted_and_ignores_unused_settings(provider):
    assert (
        configured_model(
            {
                "LLM_PROVIDER": provider,
                "LLM_MODEL": "unused",
                "LLM_API_KEY": "",
                "LLM_BASE_URL": "not-a-url",
            }
        )
        == "scripted"
    )
    assert model_details("scripted") == {"provider": None, "model": None}


def test_legacy_mode_cannot_override_a_configured_provider():
    model = configured_model({**gateway_env(), "BOOKLY_MODE": "scripted"})
    assert model_details(model)["provider"] == "anthropic"
    assert configured_model({"BOOKLY_MODE": "live", "LLM_PROVIDER": ""}) == "scripted"


@pytest.mark.parametrize("provider", ["unknown", "live", "gateway"])
def test_invalid_nonempty_provider_fails_instead_of_falling_back(provider):
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        configured_model({**gateway_env(), "LLM_PROVIDER": provider})


def test_gateway_is_a_connection_not_a_provider():
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        configured_model({**gateway_env(), "LLM_PROVIDER": "anthropic-gateway"})


@pytest.mark.parametrize("missing", ["LLM_MODEL", "LLM_API_KEY"])
def test_live_requires_separate_settings(missing):
    env = gateway_env()
    del env[missing]
    with pytest.raises(ValueError, match=missing):
        configured_model(env)


@pytest.mark.parametrize(
    "provider",
    [
        "anthropic",
        "openai",
        "google",
    ],
)
def test_live_provider_requires_selected_connection_key(provider):
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        configured_model({"LLM_PROVIDER": provider, "LLM_MODEL": "test-model"})


@pytest.mark.parametrize("provider", ["anthropic", "openai", "google"])
@pytest.mark.parametrize("custom_connection", [False, True])
def test_provider_and_connection_wire_contract(provider, custom_connection):
    from pydantic_ai import Agent

    async def exercise():
        seen = []

        async def transport(request):
            seen.append(request)
            assert request.url.scheme == "https"
            body = json.loads(request.content)
            if provider == "anthropic":
                assert request.url.host == (
                    "gateway.example.test" if custom_connection else "api.anthropic.com"
                )
                assert request.headers["x-api-key"] == "anthropic-test-key"
                assert body["model"] == "test-model"
                response = {
                    "id": "msg-1",
                    "type": "message",
                    "role": "assistant",
                    "model": "test-model",
                    "content": [{"type": "text", "text": "Hello"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 5, "output_tokens": 2},
                }
            elif provider == "openai":
                assert request.url.host == (
                    "gateway.example.test" if custom_connection else "api.openai.com"
                )
                assert request.url.path == (
                    "/openai/v1/responses" if custom_connection else "/v1/responses"
                )
                assert request.headers["authorization"] == "Bearer openai-test-key"
                assert body["model"] == "test-model"
                response = {
                    "id": "resp-1",
                    "object": "response",
                    "created_at": 1,
                    "status": "completed",
                    "model": "test-model",
                    "output": [
                        {
                            "id": "msg-1",
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [
                                {"type": "output_text", "text": "Hello", "annotations": []}
                            ],
                        }
                    ],
                    "usage": {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
                }
            else:
                assert request.url.host == (
                    "gateway.example.test"
                    if custom_connection
                    else "generativelanguage.googleapis.com"
                )
                assert request.url.path.endswith("/models/test-model:generateContent")
                assert request.headers["x-goog-api-key"] == "google-test-key"
                response = {
                    "candidates": [
                        {
                            "content": {"role": "model", "parts": [{"text": "Hello"}]},
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 5,
                        "candidatesTokenCount": 2,
                        "totalTokenCount": 7,
                    },
                    "modelVersion": "test-model",
                }
            return httpx.Response(200, json=response)

        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            env = {
                **gateway_env(),
                "LLM_PROVIDER": provider,
                "LLM_MODEL": "test-model",
                "LLM_BASE_URL": (
                    {
                        "anthropic": "https://gateway.example.test/anthropic",
                        "openai": "https://gateway.example.test/openai/v1",
                        "google": "https://gateway.example.test/gemini",
                    }[provider]
                    if custom_connection
                    else ""
                ),
                "LLM_API_KEY": f"{provider}-test-key",
            }
            model = configured_model(env, http_client=client)
            assert model_details(model) == {"provider": provider, "model": "test-model"}
            result = await Agent(model).run("Hello")
            assert result.output == "Hello"
        assert len(seen) == 1

    asyncio.run(exercise())


def test_gateway_requires_explicit_configuration_without_leaking_key():
    values = gateway_env()
    del values["LLM_MODEL"]
    with pytest.raises(ValueError, match="LLM_MODEL") as error:
        configured_model(values)
    assert values["LLM_API_KEY"] not in str(error.value)


@pytest.mark.parametrize("suffix", ["/v1", "/v1/messages", "/messages"])
def test_gateway_rejects_endpoint_instead_of_base_url(suffix):
    values = gateway_env()
    values["LLM_BASE_URL"] += suffix
    with pytest.raises(ValueError, match="SDK appends"):
        configured_model(values)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/anthropic",
        "https://key@example.com/anthropic",
        "https://example.com/anthropic?key=secret",
    ],
)
def test_gateway_rejects_insecure_or_credential_bearing_urls(url):
    values = {**gateway_env(), "LLM_BASE_URL": url}
    with pytest.raises(ValueError, match="HTTPS base URL"):
        configured_model(values)


def test_gateway_wire_contract_and_real_generalist_tool_loop(client, case, app, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "wrong-key-do-not-use")
    requests = []

    async def transport(request):
        assert request.method == "POST"
        assert request.url.scheme == "https"
        assert request.url.host == "gateway.example.test"
        assert request.url.path == "/anthropic/v1/messages"
        assert request.headers["x-api-key"] == "test-gateway-key-not-a-secret"
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert request.headers["content-type"].startswith("application/json")
        body = json.loads(request.content)
        assert body["model"] == "gateway-test-model"
        requests.append(body)
        if len(requests) == 1:
            assert "get_order" in [tool["name"] for tool in body["tools"]]
            content = [
                {
                    "type": "tool_use",
                    "id": "tool-order-1",
                    "name": "get_order",
                    "input": {"order_id": "BK-1086"},
                }
            ]
            stop = "tool_use"
        else:
            results = [
                part
                for message in body["messages"]
                if isinstance(message["content"], list)
                for part in message["content"]
                if part.get("type") == "tool_result"
            ]
            assert results and "The Last Lighthouse" in str(results[-1])
            content = [{"type": "text", "text": "Your copy of The Last Lighthouse has shipped."}]
            stop = "end_turn"
        return httpx.Response(
            200,
            json={
                "id": f"msg-test-{len(requests)}",
                "type": "message",
                "role": "assistant",
                "model": "gateway-test-model",
                "content": content,
                "stop_reason": stop,
                "stop_sequence": None,
                "usage": {"input_tokens": 20, "output_tokens": 10},
            },
        )

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http_client:
            model = configured_model(gateway_env(), http_client=http_client)
            with app.state.factory.begin() as db:
                owned = case_for(db, "maya", case["id"])
                reply = await run_turn(
                    db, owned, "Where is The Last Lighthouse?", model, MockDataWarehouse()
                )
                assert "has shipped" in reply

    asyncio.run(exercise())
    assert len(requests) == 2
