"""Explicit offline fixture model. Exercises Pydantic AI tools, not real language reasoning.

This mode is intentionally limited. Set LLM_PROVIDER to enable live conversations.
"""

import re

from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel

from bookly.knowledge import is_general_support_question


def say(text):
    return ModelResponse(parts=[TextPart(text)])


def call(name, **args):
    return ModelResponse(parts=[ToolCallPart(name, args)])


def current_turn(messages):
    text, results = "", []
    for message in messages:
        for part in message.parts:
            if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                text, results = part.content, []
            elif isinstance(part, ToolReturnPart):
                results.append((part.tool_name, part.content))
    return text, results


def generalist_model(deps):
    def respond(messages, info):
        text, results = current_turn(messages)
        lower = text.lower()
        returning = any(
            w in lower for w in ["return", "refund", "damaged", "wrong book", "changed my mind"]
        )
        prompts = [
            p.content
            for m in messages
            for p in m.parts
            if isinstance(p, UserPromptPart) and isinstance(p.content, str)
        ]
        previous_text = [
            p.content for m in messages[:-1] for p in m.parts if isinstance(p, TextPart)
        ]
        if len(prompts) >= 2 and previous_text and "Which book" in previous_text[-1]:
            returning = returning or any(w in prompts[-2].lower() for w in ("return", "refund"))
        reason = (
            "damaged"
            if "damag" in lower
            else "wrong_item"
            if "wrong" in lower
            else "changed_mind"
            if any(
                w in lower
                for w in [
                    "changed",
                    "didn't like",
                    "too dark",
                    "too slow",
                    "don't like",
                    "wasn't for me",
                    "not for me",
                ]
            )
            else None
        )
        state = deps.case.state
        details = any(w in lower for w in ["too dark", "too slow", "too violent", "too sad"])
        skip_feedback = any(
            w in lower
            for w in [
                "just the return",
                "just a refund",
                "just the refund",
                "no thanks",
                "in a hurry",
                "rather not",
            ]
        )
        if state.get("selected_item_id") and reason:
            returning = True
        if results:
            name, data = results[-1]
            if isinstance(data, dict) and data.get("error"):
                return say(data["error"])
            if name == "get_return_status":
                if data["recorded_returns"]:
                    receipt = data["recorded_returns"][-1]
                    return say(
                        f"Your return request {receipt['id']} for {receipt['title']} is recorded. No further confirmation is needed. The refund has not been issued yet."
                    )
                if any(p["can_confirm"] for p in data["pending_returns"]):
                    return say(
                        "Your return has not been recorded yet. Review the pending card and select Confirm return when you're ready."
                    )
                return say(
                    "I don't have a recorded return request or a valid pending return card in this conversation."
                )
            if name == "search_support_knowledge":
                if not data.get("passages"):
                    return say(
                        "I couldn't find that information in Bookly's mock help center, so I can't confirm the answer."
                    )
                passages = data["passages"]
                selected = passages[:2] if passages[0]["article_id"] == "password" else passages[:1]
                return say(
                    "\n\n".join(f"{p['text']} [[source:{p['source_id']}]]" for p in selected)
                )
            if name == "get_past_conversations":
                if not data:
                    return say(
                        "I don’t have an earlier saved conversation for this demo customer yet."
                    )
                recap = data[0]
                statement = next(iter(recap.get("customer_statements", [])), None)
                evidence = (
                    f' You wrote: "{statement["quote"]}" [[source:{statement["source_id"]}]]'
                    if statement
                    else ""
                )
                return say(
                    f"Your latest earlier conversation was about: {recap['request']} {recap['outcome']}{evidence} Would you like to continue that issue?"
                )
            if name == "list_orders":
                matches = [
                    order
                    for order in data
                    if order["id"].lower() in lower
                    or any(
                        item["title"].lower() in lower or item["book_id"] in lower
                        for item in order["items"]
                    )
                ]
                selected = state.get("selected_item_id")
                if returning and selected and not matches:
                    matches = [o for o in data if any(i["id"] == selected for i in o["items"])]
                if len(matches) == 1 or len(data) == 1:
                    order = (matches or data)[0]
                    item = order["items"][0]
                    if returning:
                        return call("check_return_eligibility", item_id=item["id"])
                    if order["status"] == "shipped":
                        return say(
                            f"Your copy of {item['title']} has shipped. Estimated arrival: {order['estimated_arrival']}."
                        )
                    return say(
                        f"Your copy of {item['title']} was delivered on {order['delivered_at'][:10]}. What would you like help with?"
                    )
                choices = "; ".join(f"{o['items'][0]['title']} ({o['status']})" for o in data)
                return say(f"I found these purchases: {choices}. Which book do you mean?")
            if name == "check_return_eligibility":
                if not data.get("eligible"):
                    return say(data.get("reason", "That purchase is unavailable."))
                if reason:
                    if details:
                        return call(
                            "record_reading_feedback", item_id=data["item_id"], feedback=text
                        )
                    return call("prepare_return", item_id=data["item_id"], reason=reason)
                return say(
                    f"{data['title']} is within the return window. Was it damaged, the wrong book, or a change of mind?"
                )
            if name == "prepare_return":
                optional = (
                    " You can confirm without sharing more. If you're open to sharing, what didn't work for you about the book?"
                    if reason == "changed_mind" and not details and not skip_feedback
                    else ""
                )
                return say(
                    f"I’ve prepared the return for {data['title']}. Review the amount and terms below, then select Confirm return. Nothing has been submitted yet."
                    + optional
                )
            if name == "record_reading_feedback":
                if state.get("pending_return_id") or state.get("last_return_id"):
                    return say(
                        "Thanks for explaining what missed the mark. I'll use that context here; I haven't saved a lasting preference. Your return can continue without any more feedback."
                    )
                return call("prepare_return", item_id=data["item_id"], reason="changed_mind")
            if name == "recommend_books":
                if not data["books"]:
                    return say(
                        "I couldn’t find a match in our small demo catalog. Would you like to broaden the genre or budget?"
                    )
                intro = (
                    "Here are two possibilities"
                    if len(data["books"]) == 2
                    else "Here's a possibility"
                )
                return say(
                    f"{intro} from our catalog. The cards explain the fit; you can take your time choosing."
                )
            if name == "offer_preference":
                return say(
                    f"I can remember your {data['field']} preference: {data['value']}. Select Save preference below if you want it used in future conversations."
                )
            if name == "request_reading_expert":
                return say(
                    "I’ve recorded a demo request for a reading expert. No real person has been contacted, and author availability is not connected in this prototype."
                )
        if any(
            phrase in lower
            for phrase in [
                "return status",
                "return id",
                "is my return",
                "did my return",
                "still waiting",
                "already confirmed",
                "clicked confirm",
                "clicked process",
                "confirmed it",
                "confirmed the return",
                "need to confirm",
                "did that go through",
            ]
        ):
            return call("get_return_status")
        if is_general_support_question(text):
            return call("search_support_knowledge", query=text)
        if skip_feedback and state.get("pending_return_id"):
            return say(
                "Of course. Select Confirm return on the card whenever you're ready; no more feedback is needed."
            )
        if (
            details
            and state.get("selected_item_id")
            and (state.get("pending_return_id") or state.get("last_return_id"))
        ):
            return call("record_reading_feedback", item_id=state["selected_item_id"], feedback=text)
        if any(
            phrase in lower
            for phrase in [
                "last conversation",
                "previous conversation",
                "last time",
                "earlier chat",
            ]
        ):
            return call("get_past_conversations")
        if "remember" in lower or "save my" in lower:
            field, value = (
                ("mood", "light")
                if any(w in lower for w in ["light", "funny", "cozy"])
                else ("genre", "mystery")
            )
            return call("offer_preference", field=field, value=value)
        if any(w in lower for w in ["human", "expert", "author"]):
            return call("request_reading_expert", question=text)
        if "what did i think" in lower:
            from bookly.service import customer_context

            history = customer_context(deps.db, deps.case)["historical_feedback"]
            match = next((v for v in history.values() if v["title"].lower() in lower), None)
            if match:
                return say(
                    f'In your review, you wrote: "{match["feedback"]}" [[source:{match["source_id"]}]]'
                )
            return say("I don't have a recorded review for that book.")
        if "which of those" in lower and state.get("recommendations"):
            pick = state["recommendations"][0]
            return say(f"I'd start with {pick['title']}. {pick['reason']}")
        if any(
            w in lower
            for w in [
                "recommend",
                "suggest",
                "something light",
                "something funny",
                "read next",
                "next read",
            ]
        ):
            genre = (
                "science fiction"
                if any(w in lower for w in ["sci-fi", "science fiction"])
                else "mystery"
                if any(w in lower for w in ["mystery", "cozy"])
                else None
            )
            mood = next((m for m in ["dark", "reflective", "hopeful"] if m in lower), None)
            if any(w in lower for w in ["light", "funny", "cozy"]):
                mood = "light"
            budget = re.search(r"(?:under|below|budget|\$)\s*\$?(\d+(?:\.\d{1,2})?)", lower)
            return call(
                "recommend_books",
                request=text,
                genre=genre,
                mood=mood,
                budget_cents=round(float(budget.group(1)) * 100) if budget else None,
            )
        if returning or any(
            w in lower
            for w in ["order", "where", "arriv", "midnight", "lighthouse", "sundays", "orbit"]
        ):
            return call("list_orders")
        if lower.strip(".! ") in {"yes", "confirm", "please do"} and state.get("pending_return_id"):
            return say(
                "Please select Confirm return on the card so your decision is recorded. No return has been submitted yet."
            )
        return say(
            "I can help with an order, arrange a return, or find your next read. What would you like to do?"
        )

    return FunctionModel(respond, model_name="bookly-scripted-generalist")


def reading_model():
    def respond(messages, info):
        _, results = current_turn(messages)
        done = dict(results)
        if "get_reading_context" not in done:
            return call("get_reading_context")
        if "find_catalog_books" not in done:
            return call("find_catalog_books")
        context = done["get_reading_context"]
        candidates = done["find_catalog_books"]
        affinities = context.get("warehouse", {}).get("signals", {}).get("genre_affinities", [])
        preferred = [a["genre"] for a in affinities]
        # Deliberately narrow fixture mapping, not general sentiment inference.
        history = context.get("historical_feedback", {}).get("BK-0931-1", {})
        use_comfort = (
            "optimistic tone" in history.get("feedback", "")
            and not context.get("conversation_feedback")
            and not context.get("current_constraints", {}).get("mood")
            and not context.get("explicit_preferences", {}).get("mood")
        )
        ranked = sorted(
            candidates,
            key=lambda b: (
                0 if use_comfort and b["mood"] == "light" else 1,
                b.get("behavioral_priority", 2),
                preferred.index(b["genre"]) if b["genre"] in preferred else 99,
                b["price_cents"],
            ),
        )
        picks = []
        for b in ranked[:2]:
            parts = []
            if use_comfort and b["mood"] == "light":
                parts.append(
                    f"You liked {history['title']} [[source:{history['source_id']}]]; this light {b['genre']} may fit."
                )
            evidence = b.get("behavioral_evidence", [])
            if evidence:
                entry = next((e for e in evidence if e["kind"] == "wishlist"), evidence[0])
                label = "On your wishlist" if entry["kind"] == "wishlist" else "Recently viewed"
                parts.append(f"{label} [[source:{entry['source_id']}]].")
            parts.append(b["description"])
            reason = " ".join(parts)
            picks.append({"book_id": b["id"], "reason": reason[:240]})
        return call(
            info.output_tools[0].name,
            picks=picks,
            note="Suggestions from the fictional catalog; purchase patterns are hints, not saved preferences.",
        )

    return FunctionModel(respond, model_name="bookly-scripted-reading-specialist")
