"""Account-scoped business operations. Models cannot confirm consequential actions."""

from datetime import UTC, timedelta
from uuid import uuid4

from sqlalchemy import select

from bookly.db import (
    Book,
    Case,
    Customer,
    CustomerReadingHistory,
    Event,
    Message,
    Order,
    OrderItem,
    ReturnProposal,
    ReturnReceipt,
    now,
)
from bookly.knowledge import article_sources
from bookly.policy import POLICY, RETURN_WINDOW_DAYS, TERMS
from bookly.presentation import SOURCE_MARKER, plain_excerpt, render_markdown, source_date
from bookly.warehouse import MockDataWarehouse, behavioral_sources


class DomainError(Exception):
    pass


def uid(prefix):
    return f"{prefix}-{uuid4().hex[:12]}"


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def record(db, case, name, data):
    db.add(Event(id=uid("evt"), case_id=case.id, name=name, data=data))
    db.flush()
    return data


def case_for(db, customer_id, case_id, *, lock=False):
    query = select(Case).where(Case.id == case_id, Case.customer_id == customer_id)
    if lock:
        query = query.with_for_update()
    case = db.scalar(query)
    if not case:
        raise DomainError("This case is unavailable for the selected demo customer.")
    return case


def orders_for(db, customer_id):
    orders = db.scalars(
        select(Order).where(Order.customer_id == customer_id).order_by(Order.placed_at.desc())
    ).all()
    result = []
    for order in orders:
        items = db.execute(
            select(OrderItem, Book)
            .join(Book, Book.id == OrderItem.book_id)
            .where(OrderItem.order_id == order.id)
        ).all()
        result.append(
            {
                "id": order.id,
                "status": order.status,
                "placed_at": order.placed_at.isoformat(),
                "estimated_arrival": order.estimated_arrival,
                "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
                "items": [
                    {
                        "id": item.id,
                        "book_id": book.id,
                        "title": book.title,
                        "author": book.author,
                        "paid_cents": item.paid_cents,
                        "color": book.color,
                    }
                    for item, book in items
                ],
            }
        )
    return result


def owned_item(db, case, item_id, *, lock=False):
    query = (
        select(OrderItem, Order)
        .join(Order, Order.id == OrderItem.order_id)
        .where(OrderItem.id == item_id, Order.customer_id == case.customer_id)
    )
    if lock:
        query = query.with_for_update(of=OrderItem)
    row = db.execute(query).first()
    if not row:
        raise DomainError("That purchase is unavailable for this customer.")
    return row


def eligibility(db, case, item_id):
    item, order = owned_item(db, case, item_id)
    receipt = db.scalar(select(ReturnReceipt).where(ReturnReceipt.item_id == item_id))
    reason = None
    if receipt:
        reason = "A return request already exists for this copy."
    elif order.status != "delivered" or not order.delivered_at:
        reason = "This copy has not been delivered. A shipped order needs a delivery investigation."
    elif now() > aware(order.delivered_at) + timedelta(days=RETURN_WINDOW_DAYS):
        reason = f"This copy is outside the fictional {RETURN_WINDOW_DAYS}-day return window."
    book = db.get(Book, item.book_id)
    return {
        "eligible": reason is None,
        "reason": reason,
        "item_id": item_id,
        "title": book.title,
        "refund_cents": item.paid_cents,
        "policy_version": POLICY,
        "terms": TERMS,
        "return_required": True,
        "action": "create_return_request",
        "immediate_refund": False,
    }


def record_reading_feedback(db, case, item_id, feedback):
    item, _ = owned_item(db, case, item_id)
    feedback = feedback.strip()
    if not feedback or len(feedback) > 1000:
        raise DomainError("Book feedback must be between 1 and 1000 characters.")
    entry = {
        "item_id": item.id,
        "title": db.get(Book, item.book_id).title,
        "feedback": feedback,
        "source": "customer_stated",
        "scope": "conversation_only",
    }
    statement = db.scalar(
        select(Message)
        .where(Message.case_id == case.id, Message.role == "user")
        .order_by(Message.created_at.desc(), Message.id)
        .limit(1)
    )
    if statement and feedback in statement.content:
        entry.update(
            {
                "source_id": f"conversation-{statement.id}",
                "recorded_at": aware(statement.created_at).isoformat(),
                "date_label": source_date(aware(statement.created_at).isoformat()),
            }
        )
    existing = case.state.get("reading_feedback", {})
    if existing.get(item_id) == entry:
        return entry
    case.state = {**case.state, "reading_feedback": {**existing, item_id: entry}}
    return record(db, case, "experience.reading_feedback", entry)


def prepare_return(db, case, item_id, reason):
    if reason not in {"damaged", "wrong_item", "changed_mind"}:
        raise DomainError("Choose damaged, wrong_item, or changed_mind.")
    check = eligibility(db, case, item_id)
    if not check["eligible"]:
        return check
    pending = db.scalar(
        select(ReturnProposal).where(
            ReturnProposal.case_id == case.id, ReturnProposal.status == "pending"
        )
    )
    if pending and pending.item_id != item_id:
        raise DomainError(
            "Finish or dismiss the pending return card before selecting another item."
        )
    if pending and now() > aware(pending.created_at) + timedelta(hours=24):
        pending.status = "expired"
        pending = None
    if not pending:
        pending = ReturnProposal(
            id=uid("proposal"),
            case_id=case.id,
            item_id=item_id,
            reason=reason,
            policy_version=POLICY,
        )
        db.add(pending)
        db.flush()
    case.state = {**case.state, "selected_item_id": item_id, "pending_return_id": pending.id}
    return {
        **check,
        "proposal_id": pending.id,
        "status": "awaiting_customer_confirmation",
        "confirmation": "Click Confirm return on the displayed card. No return submitted yet.",
    }


def confirm_return(db, case, proposal_id):
    proposal = db.scalar(
        select(ReturnProposal)
        .where(ReturnProposal.id == proposal_id, ReturnProposal.case_id == case.id)
        .with_for_update()
    )
    if not proposal:
        raise DomainError("Return proposal not found for this case.")
    existing = db.scalar(select(ReturnReceipt).where(ReturnReceipt.proposal_id == proposal_id))
    if existing:
        return receipt_view(db, existing)
    if proposal.status != "pending":
        raise DomainError("This return proposal is no longer pending.")
    if proposal.policy_version != POLICY or now() > aware(proposal.created_at) + timedelta(
        hours=24
    ):
        raise DomainError("These terms expired. Please ask for a fresh return check.")
    # Serialize submissions for the same physical copy, even across different cases.
    owned_item(db, case, proposal.item_id, lock=True)
    check = eligibility(db, case, proposal.item_id)
    if not check["eligible"]:
        raise DomainError(check["reason"])
    receipt = ReturnReceipt(
        id=uid("RET").upper(),
        proposal_id=proposal_id,
        item_id=proposal.item_id,
        refund_cents=check["refund_cents"],
    )
    db.add(receipt)
    proposal.status = "confirmed"
    case.state = {**case.state, "pending_return_id": None, "last_return_id": receipt.id}
    db.flush()
    return record(db, case, "return_confirmed_by_customer", receipt_view(db, receipt))


def receipt_view(db, receipt):
    item = db.get(OrderItem, receipt.item_id)
    return {
        "id": receipt.id,
        "title": db.get(Book, item.book_id).title,
        "refund_cents": receipt.refund_cents,
        "status": "return_requested",
        "terms": TERMS,
        "instructions": "Demo only: package the book and bring it to the fictional Bookly returns desk. No label was purchased or generated.",
        "immediate_refund": False,
    }


def propose_preference(db, case, field, value):
    allowed = {
        "genre": {"mystery", "fiction", "science fiction"},
        "mood": {"light", "dark", "reflective", "hopeful"},
        "format": {"paperback", "hardcover"},
    }
    if field not in allowed or value not in allowed[field]:
        raise DomainError("That preference is not supported in this small demo catalog.")
    proposal = {"id": uid("memory"), "field": field, "value": value}
    case.state = {**case.state, "pending_preference": proposal}
    return {**proposal, "status": "awaiting_explicit_save", "saved": False}


def confirm_preference(db, case, proposal_id):
    proposal = case.state.get("pending_preference")
    if not proposal or proposal["id"] != proposal_id:
        raise DomainError("That preference card is no longer pending.")
    customer = db.scalar(select(Customer).where(Customer.id == case.customer_id).with_for_update())
    customer.preferences = {**customer.preferences, proposal["field"]: proposal["value"]}
    case.state = {**case.state, "pending_preference": None}
    return record(
        db,
        case,
        "preference_saved_by_customer",
        {
            "field": proposal["field"],
            "value": proposal["value"],
            "source": "explicit_customer_confirmation",
            "saved_at": now().isoformat(),
        },
    )


def add_message(db, case, request_id, role, content):
    message = Message(
        id=uid("msg"), case_id=case.id, request_id=request_id, role=role, content=content
    )
    db.add(message)
    db.flush()
    if role == "assistant" and SOURCE_MARKER.search(content):
        available = context_sources(db, case)
        cited = {key: available[key] for key in SOURCE_MARKER.findall(content) if key in available}
        record(db, case, "grounding.message_sources", {"message_id": message.id, "sources": cited})
    return message


def book_view(book):
    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "genre": book.genre,
        "mood": book.mood,
        "description": book.description,
        "price_cents": book.price_cents,
        "color": book.color,
    }


def catalog_candidates(db, case, genre=None, mood=None, budget_cents=None):
    purchased = select(OrderItem.book_id).join(Order).where(Order.customer_id == case.customer_id)
    query = select(Book).where(Book.in_stock.is_(True), Book.id.not_in(purchased))
    if genre:
        query = query.where(Book.genre == genre)
    if mood:
        query = query.where(Book.mood == mood)
    if budget_cents is not None:
        query = query.where(Book.price_cents <= budget_cents)
    # Keep the full demo selection visible to the specialist, including premium
    # and unusual titles that a cheapest-six cutoff would hide from broad requests.
    return [book_view(b) for b in db.scalars(query.order_by(Book.price_cents, Book.id).limit(30))]


def customer_context(db, case):
    """Read the shared customer baseline fresh, never copy it into mutable case state."""
    history = db.get(CustomerReadingHistory, case.customer_id)
    # Only expose feedback linked to this customer's actual purchases.
    owned_ids = {
        item["id"] for order in orders_for(db, case.customer_id) for item in order["items"]
    }
    return {
        "explicit_preferences": db.get(Customer, case.customer_id).preferences,
        "historical_feedback": {
            key: {
                **value,
                "source_id": f"review-{key}",
                "date_label": source_date(value["recorded_at"]),
            }
            for key, value in (history.feedback if history else {}).items()
            if key in owned_ids
        },
        "source": "fictional_demo_customer_profile",
    }


def context_sources(db, case):
    """Resolve only this customer's actual reviews and verbatim customer messages."""
    customer = db.get(Customer, case.customer_id)
    feedback = customer_context(db, case)["historical_feedback"]
    sources = {
        entry["source_id"]: {
            "kind": "review",
            "author": customer.name,
            "title": entry["title"],
            "quote": entry["feedback"],
            "recorded_at": entry["recorded_at"],
        }
        for entry in feedback.values()
    }
    messages = db.scalars(
        select(Message)
        .join(Case)
        .where(Case.customer_id == case.customer_id, Message.role == "user")
        .order_by(Message.created_at.desc(), Message.id)
        .limit(50)
    )
    for message in messages:
        sources[f"conversation-{message.id}"] = {
            "kind": "conversation",
            "author": customer.name,
            "title": "Your message to Bookly",
            "quote": message.content,
            "recorded_at": aware(message.created_at).isoformat(),
            "case_id": message.case_id,
        }
    sources.update(behavioral_sources(MockDataWarehouse().customer_signals(db, case.customer_id)))
    retrieved = db.scalars(
        select(Event)
        .where(Event.case_id == case.id, Event.name == "knowledge.retrieved")
        .order_by(Event.created_at.desc(), Event.id)
        .limit(20)
    )
    for event in retrieved:
        for key, value in article_sources(event.data).items():
            sources.setdefault(key, value)
    return sources


def shared_case_state(db, case):
    return {
        **case.state,
        **return_context(db, case),
        "customer_context": customer_context(db, case),
    }


def return_context(db, case):
    """Derive action status from owned database records, never conversational history."""
    receipts = db.scalars(
        select(ReturnReceipt)
        .join(ReturnProposal)
        .where(ReturnProposal.case_id == case.id)
        .order_by(ReturnReceipt.created_at, ReturnReceipt.id)
    ).all()
    recorded = [
        {
            **receipt_view(db, r),
            "item_id": r.item_id,
            "proposal_id": r.proposal_id,
            "recorded_at": aware(r.created_at).isoformat(),
        }
        for r in receipts
    ]
    pending = []
    for proposal in db.scalars(
        select(ReturnProposal)
        .where(ReturnProposal.case_id == case.id, ReturnProposal.status == "pending")
        .order_by(ReturnProposal.created_at, ReturnProposal.id)
    ):
        check = eligibility(db, case, proposal.item_id)
        expired = proposal.policy_version != POLICY or now() > aware(
            proposal.created_at
        ) + timedelta(hours=24)
        pending.append(
            {
                "proposal_id": proposal.id,
                "item_id": proposal.item_id,
                "title": check["title"],
                "can_confirm": check["eligible"] and not expired,
                "status": "expired"
                if expired
                else "awaiting_confirmation"
                if check["eligible"]
                else "ineligible",
            }
        )
    return {
        "pending_return_id": next((p["proposal_id"] for p in pending if p["can_confirm"]), None),
        "last_return_id": recorded[-1]["id"] if recorded else None,
        "return_status": {"recorded_returns": recorded, "pending_returns": pending},
    }


def case_view(db, case):
    messages = db.scalars(
        select(Message).where(Message.case_id == case.id).order_by(Message.created_at, Message.id)
    ).all()
    events = db.scalars(
        select(Event).where(Event.case_id == case.id).order_by(Event.created_at, Event.id)
    ).all()
    proposals = db.scalars(
        select(ReturnProposal).where(
            ReturnProposal.case_id == case.id, ReturnProposal.status == "pending"
        )
    ).all()
    receipts = db.scalars(
        select(ReturnReceipt).join(ReturnProposal).where(ReturnProposal.case_id == case.id)
    ).all()
    message_sources = {
        e.data["message_id"]: e.data["sources"]
        for e in events
        if e.name == "grounding.message_sources"
    }
    # Cards belong to the reply that produced them, not to the current end of chat.
    # Existing tool events also let old conversations use this layout without a reset.
    recommendation_messages = {}
    receipt_messages = {f"confirm-{r.proposal_id}": receipt_view(db, r) for r in receipts}
    assistant_messages = [m for m in messages if m.role == "assistant"]
    for event in events:
        if event.name != "specialist.recommendations":
            continue
        reply = next(
            (m for m in assistant_messages if aware(m.created_at) >= aware(event.created_at)), None
        )
        if reply:
            recommendation_messages[reply.id] = event.data["books"]
    return {
        "id": case.id,
        "channel": case.channel,
        "state": shared_case_state(db, case),
        "summary": case_summary(db, case),
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "recommendations": recommendation_messages.get(m.id, []),
                "return_receipt": receipt_messages.get(m.request_id)
                if m.role == "assistant"
                else None,
                "html": render_markdown(m.content, message_sources.get(m.id))
                if m.role == "assistant"
                else None,
                "source": (
                    "customer"
                    if m.role == "user"
                    else "application"
                    if m.request_id.startswith(("confirm-", "memory-"))
                    else "agent"
                ),
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
        "events": [
            {"id": e.id, "name": e.name, "data": e.data, "created_at": e.created_at.isoformat()}
            for e in events
        ],
        "proposals": [
            {
                **eligibility(db, case, p.item_id),
                "id": p.id,
                "reason_code": p.reason,
                "expired": now() > aware(p.created_at) + timedelta(hours=24),
            }
            for p in proposals
        ],
        "receipts": [receipt_view(db, r) for r in receipts],
    }


def case_summary(db, case):
    """Grounded recap: message extracts plus recorded outcomes, no extra LLM request."""
    messages = db.scalars(
        select(Message).where(Message.case_id == case.id).order_by(Message.created_at, Message.id)
    ).all()
    asks = [m for m in messages if m.role == "user"]
    replies = [m for m in messages if m.role == "assistant"]
    names = set(db.scalars(select(Event.name).where(Event.case_id == case.id)))
    topics = []
    for prefix, label in [
        ("orders.", "order questions"),
        ("returns.", "returns"),
        ("specialist.", "book discovery"),
        ("memory.proposed", "reading preferences"),
        ("memory.past_conversations", "previous contacts"),
        ("human.", "an expert request"),
    ]:
        if any(name.startswith(prefix) for name in names):
            topics.append(label)
    receipt = db.scalar(
        select(ReturnReceipt).join(ReturnProposal).where(ReturnProposal.case_id == case.id).limit(1)
    )
    pending = db.scalar(
        select(ReturnProposal.id)
        .where(ReturnProposal.case_id == case.id, ReturnProposal.status == "pending")
        .limit(1)
    )
    if receipt:
        status, outcome = (
            "return_requested",
            f"Return request {receipt.id} recorded; refund not yet issued.",
        )
    elif pending:
        status, outcome = (
            "awaiting_confirmation",
            "Return terms proposed; no return request submitted.",
        )
    else:
        status, outcome = "open", "Conversation saved for follow-up."
    request = plain_excerpt(asks[0].content) if asks else ""
    return {
        "id": case.id,
        "channel": "chat",
        "message_count": len(messages),
        "title": plain_excerpt(asks[0].content, 65) if asks else "New conversation",
        "request": request,
        "latest_reply": plain_excerpt(replies[-1].content) if replies else "",
        "text": ("Discussed " + ", ".join(topics) + ". " if topics else "") + outcome,
        "status": status,
        "outcome": outcome,
        "method": "message_extracts_and_recorded_actions",
        "updated_at": (messages[-1].created_at if messages else case.created_at).isoformat(),
    }


def past_conversations(db, customer_id, *, exclude=None, limit=5):
    latest = (
        select(Message.created_at)
        .where(Message.case_id == Case.id)
        .order_by(Message.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    query = select(Case).where(
        Case.customer_id == customer_id, Case.id.in_(select(Message.case_id))
    )
    if exclude:
        query = query.where(Case.id != exclude)
    return [
        case_summary(db, case)
        for case in db.scalars(query.order_by(latest.desc()).limit(min(max(limit, 1), 50)))
    ]
