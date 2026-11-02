# Bookly Concierge

A local bookstore support demo with order assistance, returns, and personalized book
recommendations. Two Pydantic AI agents share customer context through a FastAPI app
and PostgreSQL database.

## Get started

Install and start **Docker Desktop** (or Docker Engine with Compose v2). Open a
terminal in this repository and run:

```sh
docker compose up --build -d --wait
```

Open **http://127.0.0.1:8010**. A fresh installation defaults to **scripted mode** and
needs no API key. Mode is automatic: an empty `LLM_PROVIDER` selects scripted replies;
a configured provider selects live replies and requires a model and API key. The red
**Scripted · enable live** indicator opens setup instructions. For details, follow [New user setup](docs/setup-and-demo.md#new-user-setup-direct-api-key).
Scripted mode supports the scenario prompts below; arbitrary follow-ups require live mode.

Stop with `docker compose stop`; restart with `docker compose up -d --wait`.
Saved conversations and demo records persist between runs.

Keep this demo local: the customer picker simulates sign-in. Books, purchases,
returns, and dataWarehouse activity are fictional; no real refund or message is sent.

## Try the scenarios

Start as **Maya Chen**. Topic suggestions fill an editable draft; press **Enter** or
select Send to submit it. Confirmation cards always require a separate click.

### Find an order

Send **“Where is my order?”**, then **“The Last Lighthouse.”** The agent clarifies
which purchase you mean and gives its recorded arrival estimate.

### Return a book and find a better fit

1. Send **“Return The Midnight Archive. The book wasn't for me.”** The agent checks
   eligibility and prepares a return card. Answering the optional feedback question
   is not required to proceed.
2. Reply **“It was too dark for me.”** Reload to see that the conversation and pending
   card persist, then click **Confirm return**. This records a mock return request.
3. Send **“Recommend a light mystery under $22.”** The generalist delegates to the
   reading specialist, using the feedback to find a better fit.

### Ask a general support question

Choose **General questions**, then ask **“How much does shipping cost?”**, **“How do
I reset my password?”**, or **“What is your return policy?”** The agent retrieves mock
help-center passages before answering. Open a **help article** reference to inspect
the source and version. Ask **“Do you offer gift wrapping?”** to see the no-match fallback.
Password guidance is informational; this demo cannot send reset emails or change credentials.

### Find my next read

1. Select **Start a fresh conversation**, then send **“Can you help me find my next
   read?”** Maya already has saved preferences, a prior review, and mock wishlist,
   browsing, and dismissal activity; she does not need to repeat her tastes.
2. Hover, focus, or tap a **review** or **activity** reference to inspect its dated
   source. Wishlist and browsing signals favor relevant books; dismissed suggestions
   are excluded.
3. Send **“Recommend a light mystery under $22”**, then **“Recommend a dark mystery
   under $22.”** Current requests override older tastes, and budget and purchase
   exclusions still apply across the 24-book catalog.
4. Ask **“Which of those would you pick for me, and why?”**, then say **“Remember I
   like lighter mysteries.”** Click **Save preference** to share that preference
   across future conversations.

Open **Past conversations** to resume a saved case. In **Demo lab**, inspect tool
activity and shared state, or switch to **Theo Brooks** for a separate customer profile
and hopeful science-fiction recommendations.

To replay from the baseline, click **Reset demo data** and confirm. This clears both
customers' demo history and restores fixtures with fresh dates; LLM settings stay
unchanged. Starting a fresh conversation alone does not undo returns or saved preferences.

## Architecture and database decisions

The app contains **two Pydantic AI agents running inside one web service**. Both are
defined in [bookly/agents.py](bookly/agents.py), with different instructions, tool
permissions, and responsibilities. An agent does not require its own Python file,
process, or Docker container.

| Agent | Responsibility | Tools and output |
| --- | --- | --- |
| Generalist concierge | Owns the customer conversation, resolves order/return requests, retrieves context and help articles, and delegates invited discovery | Account-scoped order, eligibility, return-proposal, feedback, history, support-knowledge retrieval, preference-proposal, and mock expert-request tools; customer-facing replies |
| Reading specialist | Consults on the customer's next read without taking over the conversation | `get_reading_context` and `find_catalog_books`; structured `ReadingAdvice` with at most two book IDs, reasons, and a note; no account-action tools |

```text
web-1: FastAPI + web UI + both Pydantic AI agents
  Customer message
    → generalist concierge
        ├─ order / eligibility / return-proposal tools
        ├─ history / feedback / preference-proposal tools
        ├─ search_support_knowledge() → approved local help passages
        └─ recommend_books()
             → reading specialist
                 ├─ get_reading_context(): preferences, reviews, feedback, warehouse
                 └─ find_catalog_books(): eligible, unpurchased catalog candidates
             ← structured recommendations
             → backend validates selected books
        ← validated tool result
    ← generalist customer-facing reply

  Customer confirmation click
    → account-scoped endpoint → eligibility recheck + transactional action

postgres-1: persistent operational records, customer context, and mock warehouse snapshots
```

`recommend_books()` calls `specialist.run()` as a nested agent run and returns the
validated result to the generalist. This is on-demand delegation, not an autonomous
background worker or a handoff of the customer session. Both agents use the same
configured LLM in live mode, through separate runs. Scripted mode substitutes separate
deterministic fixture models while exercising the same tools and business operations.
The two containers represent infrastructure: `web-1` hosts the application and agent
workflows; `postgres-1` hosts their database. Separate agent services would add deployment
and coordination overhead without a requirement for independent scaling in this demo.

PostgreSQL fits the transactional relationships between customers, orders, purchased
copies, proposals, and return receipts. Foreign keys enforce ownership relationships;
transactions, row locks, and unique constraints protect confirmation and duplicate
requests. Prices use integer USD cents. Flexible preferences, case state, model history,
review records, and warehouse signals use JSON alongside the relational operational
records. The LLM selects tools and proposes actions; backend code owns authorization,
return eligibility, catalog validation, and confirmation-gated account actions.

Saved preferences and prior reviews are customer-scoped and shared across cases;
newly volunteered reading feedback stays in its current case unless the customer
explicitly saves a preference. Both agents receive the relevant shared context. Claims
about earlier feedback cite actual stored reviews or customer messages, with escaped
verbatim text and dated previews. Customer-visible cited messages retain source
snapshots; an unavailable citation is labeled rather than rendered as a verified source.

[bookly/warehouse.py](bookly/warehouse.py) is a read-only data adapter, not a third
agent. `MockDataWarehouse.customer_signals()` reads a PostgreSQL fixture containing genre
purchase counts, a typical purchase price, provenance, a refresh timestamp, and dated
wishlist, browsing, and dismissal records. It makes no external dataWarehouse network call. Among books matching the current request and
explicit feedback, wishlist activity gets priority, then recent browsing. The backend
excludes dismissed titles and rechecks the specialist's selections against that same
candidate set. A wishlist is not purchase consent, and a page view does not prove taste.
Historical spending never imposes a hidden budget.

Mock behavior records live in `WarehouseSnapshot.signals` under `wishlist_items`,
`recently_viewed`, and `dismissed_recommendations`. Each record has a catalog `book_id`
and `recorded_at`; browsing also has `view_count`. Startup fills missing behavior
fixtures once without overwriting existing lists, including intentionally empty lists.
Reset restores the demo baseline. These fixtures simulate collected activity; the UI
does not yet collect real browsing, wishlist, or dismissal events.

The adapter ignores snapshots older than seven days, malformed/future activity,
browsing older than 30 days, and dismissals older than 90 days. Wishlist entries stay
active while present in a fresh snapshot. Missing, stale, or unavailable warehouse
signals do not block discovery; preferences, reviews, and eligible catalog books remain
available. Activity claims have dated source previews labeled as observations. A real
warehouse query and event ingestion remain future integrations.

General support uses a small mock RAG pipeline in [bookly/knowledge.py](bookly/knowledge.py):
keyword retrieval over three versioned help articles, bounded to three passages per query.
The generalist calls `search_support_knowledge`, then answers from the returned text
with article citations. No embeddings, vector database, or external knowledge service
is used. Unknown topics return no matches. Shipping rules are fictional; return text
uses the same constants as backend enforcement. Retrieved policy explains the rules
but cannot authorize actions, change refund amounts, or bypass identity checks.

The 24-book catalog uses ordinary SQL filtering and model-assisted selection; it does
not require embeddings or a vector database. Startup adds missing catalog titles and
initial customer context without resetting existing demo records. Explicit reset
restores the baseline. Table creation uses SQLAlchemy `create_all`; production schema
changes would require versioned migrations.

See [docs/architecture.md](docs/architecture.md) for the original design notes and
production considerations. The active natural-language service procedure is
[bookly/procedures/service.md](bookly/procedures/service.md). This is an independent
prototype informed by natural-language workflow principles, not an implementation
of Decagon's proprietary AOP runtime. Orders, payments, warehouse data, expert requests,
and delivery integrations remain mocked; SMS/voice remain design previews.

## Optional reference

See [Setup and demo reference](docs/setup-and-demo.md) for ports, logs, local Python
development, live-model and gateway configuration, the detailed walkthrough, and
SMS/voice design previews.
