"""Exercise a fresh scripted installation through HTTP, using only Python's stdlib.

Run inside the web container with: python - < scripts/smoke.py
Creates fictional records in that installation. It does not reset data.
"""

import json
import os
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor, Request, build_opener
from uuid import uuid4

base = os.getenv("BOOKLY_SMOKE_URL", "http://127.0.0.1:8010").rstrip("/")
client = build_opener(HTTPCookieProcessor(CookieJar()))


def request(path, data=None):
    payload = json.dumps(data).encode() if data is not None else None
    with client.open(
        Request(base + path, data=payload, headers={"Content-Type": "application/json"}), timeout=65
    ) as response:
        return json.load(response)


health = request("/api/health")
assert health["mode"] == "scripted", "Smoke walkthrough requires scripted mode, not paid inference."
request("/api/demo/session", {"customer_id": "maya"})
case = request("/api/cases", {"channel": "chat"})
path = f"/api/cases/{case['id']}"


def say(text):
    return request(path + "/messages", {"text": text, "request_id": uuid4().hex})


status = say("Where is my order?")
assert "Which book" in status["messages"][-1]["content"]
proposed = say("Return The Midnight Archive. It arrived damaged.")
assert proposed["proposals"], (
    "Use a fresh seeded volume; the walkthrough copy may already be returned."
)
pid = proposed["proposals"][0]["id"]
restored = request(path)
assert restored["channel"] == "chat" and restored["proposals"][0]["id"] == pid
confirmed = request(path + f"/returns/{pid}/confirm", {})
repeated = request(path + f"/returns/{pid}/confirm", {})
assert len(confirmed["receipts"]) == len(repeated["receipts"]) == 1
assert confirmed["receipts"][0]["id"] == repeated["receipts"][0]["id"]
discovery = say("Recommend a light mystery under $22")
assert discovery["state"]["recommendations"]
assert all(b["price_cents"] <= 2200 for b in discovery["state"]["recommendations"])
assert any(e["name"] == "warehouse.customer_signals" for e in discovery["events"])
print(
    "PASS: fresh HTTP install, clarification, return, retry, saved-case resume, and specialist discovery."
)
