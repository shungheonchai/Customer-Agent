"""Delivery instructions. Only web chat is connected in this prototype."""

CHANNEL_PROMPTS = {
    "chat": """Web chat: keep replies brief and scannable. Use short paragraphs, occasional bold emphasis, and at most one focused question. Use the displayed confirmation cards for consequential actions. Provide verified links only when available. Do not repeat information already provided. Preserve context when the customer resumes this saved conversation.""",
    "sms": """SMS design example: use one or two short plain-text sentences per message, without Markdown, tables, or web UI references. Ask one focused question. After a long gap, give a short recap before continuing. Do not assume the customer can reply immediately. A production SMS adapter must provide verified identity and an explicit text-confirmation mechanism before actions; never invent that authorization. This template is not connected to message delivery in the demo.""",
    "voice": """Voice design example: speak in short, natural sentences and ask one question at a time. Read amounts and dates clearly; do not read Markdown, URLs, or internal IDs aloud unless needed. Allow the caller to interrupt. Restate the material terms before requesting explicit confirmation, and announce outcomes only after backend confirmation. This template has no audio transport in the demo.""",
}


def prompt_profiles():
    return {
        "active": "chat",
        "profiles": [
            {"channel": channel, "implemented": channel == "chat", "instructions": prompt}
            for channel, prompt in CHANNEL_PROMPTS.items()
        ],
    }


def active_prompt(channel):
    # Legacy async case records remain resumable as web chat. No UI channel switch.
    return CHANNEL_PROMPTS["chat"]
