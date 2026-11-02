"""The expanded catalog varies with constraints and upgrades existing demos safely."""

from collections import Counter

from sqlalchemy import delete, func, select

from bookly import service
from bookly.db import Book, Customer, Order
from bookly.fixtures import CATALOG, seed
from tests.conftest import send


def test_catalog_has_varied_choices_and_exposes_more_than_cheapest_six(client, case, app):
    assert len(CATALOG) == 24
    assert Counter(b["genre"] for b in CATALOG) == {
        "mystery": 8,
        "fiction": 8,
        "science fiction": 8,
    }
    with app.state.factory() as db:
        owned = service.case_for(db, "maya", case["id"])
        books = service.catalog_candidates(db, owned)
        assert len(books) == 21
        assert "seedship" in {b["id"] for b in books}  # Premium titles remain discoverable.
        assert {"midnight", "sundays", "lighthouse"}.isdisjoint(b["id"] for b in books)


def test_startup_adds_missing_books_without_resetting_customer_or_stock(client, app):
    with app.state.factory.begin() as db:
        db.execute(delete(Book).where(Book.id == "seedship"))
        db.get(Book, "teacup").price_cents = 1600
        db.get(Book, "teacup").in_stock = False
        db.get(Customer, "maya").preferences = {"mood": "dark"}
        old_date = db.get(Order, "BK-1042").placed_at
    with app.state.factory.begin() as db:
        seed(db)
        db.flush()
        assert db.scalar(select(func.count()).select_from(Book)) == 24
        assert db.get(Book, "teacup").price_cents == 1600
        assert db.get(Book, "teacup").in_stock is False
        assert db.get(Customer, "maya").preferences == {"mood": "dark"}
        assert db.get(Order, "BK-1042").placed_at == old_date
        seed(db)
        db.flush()
        assert db.scalar(select(func.count()).select_from(Book)) == 24


def test_changing_mood_changes_recommendations_without_recommending_owned_books(client, case):
    light = send(client, case, "Recommend a light mystery under $22")["state"]["recommendations"]
    dark = send(client, case, "Recommend a dark mystery under $22")["state"]["recommendations"]
    assert light and dark
    assert {b["id"] for b in light}.isdisjoint(b["id"] for b in dark)
    assert all(b["mood"] == "dark" and b["price_cents"] <= 2200 for b in dark)


def test_theo_has_new_hopeful_science_fiction_choices(client):
    client.post("/api/demo/session", json={"customer_id": "theo"})
    case = client.post("/api/cases", json={}).json()
    books = send(client, case, "Can you help me find my next read?")["state"]["recommendations"]
    assert len(books) == 2
    assert all(b["genre"] == "science fiction" and b["mood"] == "hopeful" for b in books)
    assert all(b["id"] != "orbit" for b in books)


def test_reset_restores_expanded_catalog(client):
    assert client.post("/api/demo/reset", json={"confirm": "RESET"}).status_code == 200
    case = client.post("/api/cases", json={}).json()
    result = send(client, case, "Recommend a hopeful science fiction book under $25")
    assert len(result["state"]["recommendations"]) == 2
