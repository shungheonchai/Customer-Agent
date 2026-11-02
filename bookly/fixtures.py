"""Fictional catalog, initial seed, and explicit restoration with fresh relative dates."""

from datetime import timedelta

from sqlalchemy import delete, select

from bookly.db import (
    Base,
    Book,
    Customer,
    CustomerReadingHistory,
    Order,
    OrderItem,
    WarehouseSnapshot,
    now,
)

CUSTOMER_PREFERENCES = {
    "maya": {"genre": "mystery", "format": "paperback"},
    "theo": {"genre": "science fiction", "format": "paperback", "mood": "hopeful"},
}


def seed_reading_history(db):
    """Add the demo baseline once, including to existing installs; preserve saved choices."""
    for cid, item_id, title, feedback, days_ago in [
        (
            "maya",
            "BK-0931-1",
            "A Map of Sundays",
            "I loved the optimistic tone and small-town setting. A comforting weekend read.",
            45,
        ),
        (
            "theo",
            "BK-1071-1",
            "An Orbit of Our Own",
            "I enjoyed the hopeful tone and found-family crew. I'd read more like this.",
            1,
        ),
    ]:
        customer = db.get(Customer, cid)
        if not customer:
            continue
        existing = db.get(CustomerReadingHistory, cid)
        if existing:
            # Give the original demo notes explicit review provenance without changing their text/date.
            entry = existing.feedback.get(item_id)
            if entry and entry.get("source") == "mock_prior_customer_feedback":
                existing.feedback = {
                    **existing.feedback,
                    item_id: {
                        **entry,
                        "source": "mock_customer_review",
                        "resource_type": "customer_review",
                    },
                }
            continue
        customer.preferences = {**CUSTOMER_PREFERENCES[cid], **customer.preferences}
        db.add(
            CustomerReadingHistory(
                customer_id=cid,
                feedback={
                    item_id: {
                        "item_id": item_id,
                        "title": title,
                        "feedback": feedback,
                        "source": "mock_customer_review",
                        "resource_type": "customer_review",
                        "scope": "customer_history",
                        "recorded_at": (now() - timedelta(days=days_ago)).isoformat(),
                    }
                },
            )
        )


CATALOG = [
    dict(
        id="midnight",
        title="The Midnight Archive",
        author="Elena Vale",
        genre="mystery",
        mood="dark",
        description="A tense literary mystery through a city's forgotten archives.",
        price_cents=2400,
        color="#374e5e",
    ),
    dict(
        id="marigold",
        title="Murder at the Marigold",
        author="June Bell",
        genre="mystery",
        mood="light",
        description="A funny, gentle village mystery with a florist turned sleuth.",
        price_cents=1800,
        color="#b46842",
    ),
    dict(
        id="lantern",
        title="The Lantern Club",
        author="Ada Moss",
        genre="mystery",
        mood="light",
        description="Warm friendships and a puzzle at a seaside book club.",
        price_cents=2000,
        color="#727c50",
    ),
    dict(
        id="lighthouse",
        title="The Last Lighthouse",
        author="Rowan Ellis",
        genre="fiction",
        mood="reflective",
        description="A tender story of starting over on a remote coastline.",
        price_cents=2200,
        color="#617f82",
    ),
    dict(
        id="sundays",
        title="A Map of Sundays",
        author="Nora Finch",
        genre="fiction",
        mood="light",
        description="An optimistic journey through small towns and second chances.",
        price_cents=1900,
        color="#b39156",
    ),
    dict(
        id="orbit",
        title="An Orbit of Our Own",
        author="Sam Avery",
        genre="science fiction",
        mood="hopeful",
        description="A hopeful found-family adventure aboard a wandering station.",
        price_cents=2100,
        color="#64617f",
    ),
]

# Enough distinct settings, pacing, and price points for an invited consultation
# to change with the reader's wishes. All titles and authors are fictional.
CATALOG += [
    dict(
        id=bid,
        title=title,
        author=author,
        genre=genre,
        mood=mood,
        description=description,
        price_cents=price,
        color=color,
    )
    for bid, title, author, genre, mood, description, price, color in [
        (
            "teacup",
            "The Teacup Alibi",
            "Iris Wren",
            "mystery",
            "light",
            "A quick, witty village whodunit: a retired baker solves a theft at the annual tea fair. Gentle stakes and no graphic violence.",
            1400,
            "#a8755d",
        ),
        (
            "orchard",
            "The Orchard House Puzzle",
            "Cleo Hart",
            "mystery",
            "light",
            "A leisurely autumn mystery at a family orchard, with warm neighbors, dry humor, and a missing heirloom.",
            2300,
            "#8b754c",
        ),
        (
            "museum",
            "A Most Curious Curator",
            "Felix Reed",
            "mystery",
            "light",
            "A fast, playful city-museum caper featuring rival curators and a forged painting. Clever clues and comic misunderstandings.",
            2700,
            "#88718d",
        ),
        (
            "glass",
            "The Glass Witness",
            "Mara Quinn",
            "mystery",
            "dark",
            "A fast-paced psychological mystery about an unreliable witness and a vanished neighbor. Menacing atmosphere and morally ambiguous characters.",
            2100,
            "#485769",
        ),
        (
            "letters",
            "Letters from Blackwater",
            "Eden Shaw",
            "mystery",
            "reflective",
            "A slow-burn historical mystery told through family letters, exploring memory, grief, and a decades-old disappearance.",
            1900,
            "#727c75",
        ),
        (
            "bookshop",
            "The Bookshop on Willow Lane",
            "Lena Park",
            "fiction",
            "light",
            "A comforting small-town story about reopening a bookshop, unlikely friendships, and second chances. Gentle pacing and a hopeful ending.",
            1600,
            "#8a9263",
        ),
        (
            "postcards",
            "Postcards from Somewhere",
            "Nina Wells",
            "fiction",
            "light",
            "A brisk, funny road-trip novel about two estranged sisters reconnecting through small-town mishaps and handwritten postcards.",
            2000,
            "#bd895d",
        ),
        (
            "garden",
            "The Garden Between Us",
            "Amelia Stone",
            "fiction",
            "reflective",
            "A quiet, character-driven novel about neighbors restoring a community garden while navigating grief and reconciliation.",
            1800,
            "#648471",
        ),
        (
            "winter",
            "Winter at the Listening House",
            "Owen Lake",
            "fiction",
            "reflective",
            "A contemplative coastal family story about a musician returning home to care for her father. Lyrical prose and a bittersweet ending.",
            2800,
            "#657b8a",
        ),
        (
            "tomorrow",
            "A Table for Tomorrow",
            "Esme Brooks",
            "fiction",
            "hopeful",
            "Neighbors from different generations build a community kitchen after a storm. An uplifting ensemble story about rebuilding and belonging.",
            2200,
            "#b68a4f",
        ),
        (
            "hollow",
            "The Hollow Season",
            "Jules Arden",
            "fiction",
            "dark",
            "An intense literary family drama about ambition, betrayal, and secrets in a declining industrial town. Bleak tone and an unresolved ending.",
            2500,
            "#725a60",
        ),
        (
            "wayfarer",
            "The Wayfarer Kitchen",
            "Alex Rivera",
            "science fiction",
            "hopeful",
            "A gentle, character-driven space adventure about a cook joining a mismatched freighter crew. Found family, shared meals, and low-stakes exploration.",
            1700,
            "#ad7852",
        ),
        (
            "signal",
            "A Signal for Tomorrow",
            "Robin Hale",
            "science fiction",
            "hopeful",
            "A fast-paced first-contact adventure in which a diverse rescue crew learns to cooperate across species. Optimistic teamwork with real danger.",
            2400,
            "#57828b",
        ),
        (
            "seedship",
            "The Seedship Promise",
            "Dara Sun",
            "science fiction",
            "hopeful",
            "An expansive generation-ship adventure about botanists building a future together. Found-family bonds, ecological puzzles, and an uplifting resolution.",
            3200,
            "#6f8265",
        ),
        (
            "memory",
            "The Memory Observatory",
            "Taylor Finch",
            "science fiction",
            "reflective",
            "A quiet, philosophical novella about an archivist preserving the memories of a fading moon colony. Identity, loss, and patient character development.",
            1200,
            "#7a7394",
        ),
        (
            "tides",
            "Tides of Europa",
            "Morgan Ash",
            "science fiction",
            "reflective",
            "A scientifically grounded ocean expedition beneath Europa's ice. Measured pacing, ethical dilemmas, and an ambiguous discovery.",
            2600,
            "#567b8e",
        ),
        (
            "blackout",
            "Blackout Protocol",
            "Kai Mercer",
            "science fiction",
            "dark",
            "A tense cyberpunk thriller about a courier hunted by a surveillance corporation. Rapid action, systemic injustice, and a grim urban setting.",
            2300,
            "#615c79",
        ),
        (
            "lostplanet",
            "The Lost Planet Help Desk",
            "Jamie Bell",
            "science fiction",
            "light",
            "A short comic space adventure about an overwhelmed help-desk team rerouting a misplaced planet. Workplace humor, quirky aliens, and gentle stakes.",
            1500,
            "#8b8d5a",
        ),
    ]
]


def seed_catalog(db):
    """Add missing titles without changing existing stock, prices, or purchases."""
    existing = set(db.scalars(select(Book.id)))
    db.add_all(Book(**book) for book in CATALOG if book["id"] not in existing)


def seed_warehouse_behaviors(db):
    """Add a once-only analytics baseline without replacing existing behavioral choices."""
    for snapshot in db.scalars(select(WarehouseSnapshot)):
        fixture = {
            "maya": ("orchard", "lantern", "teacup"),
            "theo": ("seedship", "signal", "wayfarer"),
        }.get(snapshot.customer_id)
        if not fixture or snapshot.signals.get("behavior_fixture_version") == 1:
            continue
        wishlist, viewed, dismissed = fixture
        at = snapshot.refreshed_at
        additions = {
            "wishlist_items": [
                {"book_id": wishlist, "recorded_at": (at - timedelta(days=3)).isoformat()}
            ],
            "recently_viewed": [
                {
                    "book_id": viewed,
                    "view_count": 3,
                    "recorded_at": (at - timedelta(days=1)).isoformat(),
                }
            ],
            "dismissed_recommendations": [
                {"book_id": dismissed, "recorded_at": (at - timedelta(days=2)).isoformat()}
            ],
        }
        snapshot.signals = {**additions, **snapshot.signals, "behavior_fixture_version": 1}
        if snapshot.source.startswith("mock_"):
            snapshot.source = "mock_dataWarehouse.customer_reading_signals_v2"


def seed(db, *, restore=False):
    if not restore and db.scalar(select(Customer.id).limit(1)):
        seed_catalog(db)
        seed_reading_history(db)
        seed_warehouse_behaviors(db)
        return
    at = now()
    for cid, name, preferences in [
        ("maya", "Maya Chen", CUSTOMER_PREFERENCES["maya"]),
        ("theo", "Theo Brooks", CUSTOMER_PREFERENCES["theo"]),
    ]:
        customer = db.get(Customer, cid)
        if customer:
            customer.name, customer.preferences = name, preferences
        else:
            db.add(Customer(id=cid, name=name, preferences=preferences))
    seed_catalog(db)
    db.flush()
    orders = [
        ("BK-1042", "maya", "delivered", 9, 6, None, "midnight", 2400),
        (
            "BK-1086",
            "maya",
            "shipped",
            2,
            None,
            (at + timedelta(days=2)).date().isoformat(),
            "lighthouse",
            2200,
        ),
        ("BK-0931", "maya", "delivered", 53, 48, None, "sundays", 1900),
        ("BK-1071", "theo", "delivered", 6, 3, None, "orbit", 2100),
    ]
    for oid, cid, status, age, delivered, eta, bid, paid in orders:
        db.add(
            Order(
                id=oid,
                customer_id=cid,
                status=status,
                placed_at=at - timedelta(days=age),
                delivered_at=at - timedelta(days=delivered) if delivered else None,
                estimated_arrival=eta,
            )
        )
        db.flush()
        db.add(OrderItem(id=f"{oid}-1", order_id=oid, book_id=bid, paid_cents=paid))
    seed_reading_history(db)
    db.add_all(
        [
            WarehouseSnapshot(
                customer_id="maya",
                source="mock_dataWarehouse.customer_reading_signals_v1",
                refreshed_at=at - timedelta(hours=12),
                signals={
                    "genre_affinities": [
                        {"genre": "mystery", "purchase_count": 5},
                        {"genre": "fiction", "purchase_count": 3},
                    ],
                    "typical_price_cents": 2200,
                    "basis": "Fictional aggregate of prior purchases; not an explicit preference.",
                },
            ),
            WarehouseSnapshot(
                customer_id="theo",
                source="mock_dataWarehouse.customer_reading_signals_v1",
                refreshed_at=at - timedelta(hours=12),
                signals={
                    "genre_affinities": [{"genre": "science fiction", "purchase_count": 4}],
                    "typical_price_cents": 2100,
                    "basis": "Fictional aggregate of prior purchases; not an explicit preference.",
                },
            ),
        ]
    )
    seed_warehouse_behaviors(db)


def reset_demo(db):
    """Restore all fictional fixtures transactionally; preserve customer selection cookies."""
    for table in reversed(Base.metadata.sorted_tables):
        if table.name not in {"customers", "demo_sessions"}:
            db.execute(delete(table))
    seed(db, restore=True)
    db.flush()
