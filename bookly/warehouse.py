"""Read-only mock analytics adapter and bounded behavioral recommendation rules."""

from datetime import UTC, datetime, timedelta

from bookly.db import Book, WarehouseSnapshot, now

BEHAVIOR_FIELDS = {
    "wishlist_items": ("wishlist", None),
    "recently_viewed": ("browsing", 30),
    "dismissed_recommendations": ("dismissal", 90),
}


class MockDataWarehouse:
    def customer_signals(self, db, customer_id):
        snapshot = db.get(WarehouseSnapshot, customer_id)
        if not snapshot:
            return {"available": False, "source": "mock_dataWarehouse", "signals": {}}
        refreshed = snapshot.refreshed_at
        if refreshed.tzinfo is None:
            refreshed = refreshed.replace(tzinfo=UTC)
        at = now()
        fresh = at - timedelta(days=7) <= refreshed <= at
        signals = snapshot.signals if isinstance(snapshot.signals, dict) else {}
        result = {
            "available": fresh,
            "source": snapshot.source,
            "mock": True,
            "refreshed_at": refreshed.isoformat(),
            "signals": {key: value for key, value in signals.items() if key not in BEHAVIOR_FIELDS}
            if fresh
            else {},
            "behavioral_evidence": [],
            "usage": "Observed activity is not a stated taste. Current requests, explicit preferences, and reviews take precedence. Typical price is not a budget.",
        }
        if not fresh:
            result["reason"] = (
                "Snapshot is older than seven days or has a future refresh timestamp."
            )
            return result
        for field, (kind, window_days) in BEHAVIOR_FIELDS.items():
            entries = signals.get(field, [])
            if not isinstance(entries, list):
                continue
            seen = set()
            for entry in entries[:100]:
                if not isinstance(entry, dict) or not isinstance(entry.get("book_id"), str):
                    continue
                book_id = entry["book_id"]
                if book_id in seen:
                    continue
                try:
                    recorded = datetime.fromisoformat(entry["recorded_at"])
                    if recorded.tzinfo is None:
                        recorded = recorded.replace(tzinfo=UTC)
                except (KeyError, TypeError, ValueError):
                    continue
                if recorded > refreshed or (
                    window_days and recorded < at - timedelta(days=window_days)
                ):
                    continue
                book = db.get(Book, book_id)
                if not book:
                    continue
                count = entry.get("view_count", 1)
                if kind == "browsing" and (type(count) is not int or not 1 <= count <= 10000):
                    continue
                observation = {
                    "wishlist": f"Added {book.title} to the wishlist.",
                    "browsing": f"Viewed {book.title} {count} time(s) in the recorded browsing window.",
                    "dismissal": f"Dismissed a recommendation for {book.title}.",
                }[kind]
                result["behavioral_evidence"].append(
                    {
                        "source_id": f"activity-{customer_id}-{kind}-{book_id}",
                        "kind": kind,
                        "book_id": book_id,
                        "title": book.title,
                        "recorded_at": recorded.isoformat(),
                        "observation": observation,
                        "view_count": count if kind == "browsing" else None,
                    }
                )
                seen.add(book_id)
            # Expose only validated activity, not malformed/expired raw telemetry.
            result["signals"][field] = [
                entry for entry in result["behavioral_evidence"] if entry["kind"] == kind
            ]
        return result


def apply_behavioral_signals(candidates, snapshot):
    """Rank already-eligible books; exclude dismissed titles without relaxing constraints."""
    evidence = snapshot.get("behavioral_evidence", []) if snapshot.get("available") else []
    dismissed = {e["book_id"] for e in evidence if e["kind"] == "dismissal"}
    result = []
    for book in candidates:
        if book["id"] in dismissed:
            continue
        notes = [e for e in evidence if e["book_id"] == book["id"] and e["kind"] != "dismissal"]
        priority = 0 if any(e["kind"] == "wishlist" for e in notes) else 1 if notes else 2
        result.append({**book, "behavioral_priority": priority, "behavioral_evidence": notes})
    return sorted(result, key=lambda b: (b["behavioral_priority"], b["price_cents"], b["id"]))


def behavioral_sources(snapshot):
    """Source records describe telemetry as observations, never as customer quotations."""
    if not snapshot.get("available"):
        return {}
    return {
        e["source_id"]: {
            "kind": e["kind"],
            "author": "Bookly activity · fictional demo record",
            "title": e["title"],
            "quote": e["observation"],
            "recorded_at": e["recorded_at"],
        }
        for e in snapshot.get("behavioral_evidence", [])
    }
