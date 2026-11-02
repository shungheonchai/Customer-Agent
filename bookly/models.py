"""Provider-driven execution, model selection, and optional connection settings."""

import os
from collections.abc import Mapping
from urllib.parse import urlsplit

import httpx
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider


def model_details(model):
    """Public selection metadata only; scripted mode has no live provider or model."""
    if model == "scripted":
        return {"provider": None, "model": None}
    return {"provider": model.system, "model": model.model_name}


def configured_model(
    env: Mapping[str, str] | None = None, *, http_client: httpx.AsyncClient | None = None
):
    values = os.environ if env is None else env
    provider_name = values.get("LLM_PROVIDER", "").strip().lower()
    if not provider_name:
        # Do not construct a provider or inspect its key/URL in fixture mode.
        return "scripted"
    if provider_name not in {"anthropic", "openai", "google"}:
        raise ValueError(
            "LLM_PROVIDER must be anthropic, openai, or google. A gateway is configured with LLM_BASE_URL, not as a provider."
        )
    missing = [name for name in ("LLM_MODEL", "LLM_API_KEY") if not values.get(name, "").strip()]
    if missing:
        raise ValueError("Live LLM configuration is missing: " + ", ".join(missing))
    model_id = values["LLM_MODEL"].strip()
    key = values["LLM_API_KEY"].strip()
    base_url = values.get("LLM_BASE_URL", "").strip().rstrip("/") or None
    if base_url:
        validate_base_url(base_url, provider_name)

    if provider_name == "anthropic":
        return AnthropicModel(
            model_id,
            provider=AnthropicProvider(
                api_key=key,
                base_url=base_url or "https://api.anthropic.com",
                http_client=http_client,
            ),
        )
    if provider_name == "openai":
        from pydantic_ai.models.openai import OpenAIResponsesModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIResponsesModel(
            model_id,
            provider=OpenAIProvider(
                api_key=key,
                base_url=base_url or "https://api.openai.com/v1",
                http_client=http_client,
            ),
        )
    from pydantic_ai.models.google import GoogleModel
    from pydantic_ai.providers.google import GoogleProvider

    return GoogleModel(
        model_id, provider=GoogleProvider(api_key=key, base_url=base_url, http_client=http_client)
    )


def validate_base_url(base_url, provider_name):
    url = urlsplit(base_url)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError(
            "LLM_BASE_URL must be an HTTPS base URL without credentials, query, or fragment."
        )
    if provider_name == "anthropic" and url.path.rstrip("/").endswith(("/v1", "/messages")):
        raise ValueError(
            "LLM_BASE_URL must be the Anthropic gateway prefix, not /v1 or /v1/messages; the SDK appends /v1/messages."
        )
    if provider_name == "openai" and url.path.rstrip("/").endswith(
        ("/responses", "/chat/completions")
    ):
        raise ValueError(
            "LLM_BASE_URL must be an OpenAI-compatible API root, usually ending in /v1, not /responses or /chat/completions."
        )
