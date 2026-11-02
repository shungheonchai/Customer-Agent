# Architecture decisions — initial local milestone

This file describes the implemented demo. For the proposed hybrid specialist and
memory architecture, see [the production proposal](production-agent-orchestration.md)
and [the README](../README.md#architecture-and-database-decisions).

## Thesis and scope

Resolve accurately with low customer effort, then offer optional reading guidance.
The prototype covers order status, return requests, reading recommendations, explicit
preference memory, and a mock expert request. Web chat is the only connected channel.
Saved case history and recaps support resumption; SMS and voice instructions can be
compared in Demo lab as design examples, and the SMS continuation button is a preview.
Voice/audio, real human takeover, commerce checkout, author appointments, and actual
refund settlement are outside this milestone.

## Why PostgreSQL

Customers own orders; orders contain purchased copies; returns refer to a specific
purchased copy and its paid amount. Foreign keys, transactions, row locks, unique
constraints, and explicit action records fit that structure. Prices use integer USD
cents. Customer preferences and case/history payloads use JSON; core purchases and
actions remain relational. A case belongs to a customer, not a channel session.

Initial tables:

| Table | Ownership / purpose |
| --- | --- |
| `customers` | Identity fixture and explicitly saved preferences |
| `books` | Fictional catalog, stock, price, genre, mood |
| `orders`, `order_items` | Owned purchases; one physical copy per line in this demo |
| `cases` | Channel, workflow state, serialized Pydantic AI message history |
| `messages` | Customer-visible transcript, including server-recorded outcomes |
| `events` | Tool activity, procedure version, usage, and consent/action provenance |
| `return_proposals` | Prepared terms awaiting explicit confirmation |
| `return_receipts` | Unique return request per purchased copy; no actual refund |
| `warehouse_snapshots` | Read-only fixture representing analytical aggregates |
| `demo_sessions` | Mock customer selection bound to a random browser cookie |

Bootstrap uses `metadata.create_all` for a fresh demo database. It is not a migration
system: future schema changes should use versioned migrations before persistent
deployments. Initial fixtures seed only when the customer table is empty. There is
no automatic destructive migration. An explicit, confirmation-gated local demo reset
restores fixture data; it is not a production database administration endpoint.

## Why no vector database yet

Twenty-four catalog books and a compact policy can be retrieved using explicit fields and
ordinary SQL. Semantic retrieval would become relevant for a larger catalog or
unstructured knowledge corpus. Keep a catalog/retrieval boundary so MongoDB Atlas can be
evaluated later without moving operational return/case state. No embeddings or MongoDB
Atlas connection is required for this milestone.

## Mock support RAG

The generalist's `search_support_knowledge` tool retrieves up to three approved local
passages from `bookly/support_articles.json` via `bookly/knowledge.py`. Three versioned
articles cover shipping, returns/refunds, and safe password-reset guidance. Topic
anchors, normalized keywords, and deterministic scoring select passages; no embedding
service or vector database is involved. Retrieval results are logged as
`knowledge.retrieved`; only passages retrieved in the current case can resolve as
help-article citations. Dated previews show source text and version, and cited replies
retain source snapshots. Missing matches produce an explicit unknown rather than an
invented policy. Live answer quality still needs conversational rehearsal.

Return-policy text substitutes the shared constants in `bookly/policy.py`. Retrieval
is informational and grants no account access or action permissions. Account-specific
order/return questions still use operational tools; password recovery has no executing
tool or email provider. All shipping terms and help content are fictional demo policy.

## Mock warehouse boundary

`MockDataWarehouse.customer_signals` returns a fixture snapshot from PostgreSQL; it does
not execute SQL against dataWarehouse or pretend a network call occurred. It is a
replaceable adapter for a future read-only, parameterized warehouse lookup.

The payload contains aggregate genre purchase counts, typical book price, source,
refresh timestamp, and an explicit label that these are inferred signals. Historical
purchases do not prove reading preferences. Current requests and explicit preferences
take precedence. The adapter also validates dated `wishlist_items`, `recently_viewed`, and
`dismissed_recommendations`. Among eligible books, wishlist activity is prioritized,
then recent browsing; dismissed titles are removed before the specialist sees them
and again when its selections are validated. Current genre/mood/budget, stock, and
purchase exclusions remain authoritative. Typical spend is not a hard budget.
The same rules run in scripted and live modes; the live specialist can prefer a
stronger match to the customer's stated goal over a soft activity signal.

Snapshots expire after seven days; browsing signals after 30 days and dismissal
signals after 90 days. Invalid/future activity is ignored. Wishlist entries remain
active while present in a fresh snapshot. Activity explanations cite dated source
records as observations, not customer quotations. Fixtures seed these behaviors once
for existing demos without replacing saved lists; no UI telemetry ingestion or real
warehouse connection is implemented.

The warehouse is consulted for invited discovery, not for order truth or return
eligibility. Missing/unavailable warehouse data yields generic catalog guidance.
There is no writeback to dataWarehouse. A real deployment still needs provider timeouts,
verified customer identity mapping, event ingestion, and operational refresh scheduling.

## Agent versus workflow

`bookly/models.py` checks `LLM_PROVIDER`: empty or unset selects scripted execution
without constructing a provider. A nonempty provider selects live execution and
requires `LLM_MODEL` and `LLM_API_KEY`. `LLM_BASE_URL` is optional: blank uses the provider's public endpoint;
a supplied compatible API root changes the connection without changing the provider.
Anthropic uses Messages, OpenAI uses Responses, and Google uses the Gemini API-key
adapter. A gateway is a route, not a fourth provider. No provider is chosen by the
presence of a particular credential. Both agents receive the same configured model.
A mock transport verifies provider endpoints, authentication, and the Anthropic
request/tool-result loop. This does not establish live provider access or a gateway's
support for the SDK's beta query.

At completed Anthropic turn boundaries, stored history omits thinking blocks whose
signatures bind them to an earlier system prompt. Case context can change between
turns. User messages, assistant text, tool calls, and tool results are preserved;
thinking stays intact inside the active tool loop. Dynamic system instructions are
snapshotted per turn, so tool-driven case updates cannot invalidate the active loop's
signatures; current tool results still provide fresh facts. The same cleanup applies when
loading older history, so an affected conversation can resume without a reset.

Pydantic AI manages the model/tool loop. Decorated tools accept trusted customer/case
dependencies from the application, not customer IDs supplied by the model. Order
lookup and return policy are deterministic functions. Reading discovery is a delegated
agent with a distinct task, tools, and validated output. It returns to the generalist;
it never takes ownership of the customer conversation or gains refund permissions.

Both agents have bounded model requests. Recommendation IDs, stock, budget, genre,
mood, and purchased-book exclusions are checked against operational catalog results.
Explanations are model-authored in live mode and need conversational evaluation.
Natural-language prompts do not themselves prove hallucination resistance.

## Customer experience and service recovery

Resolve first, then make the next experience more useful. A vague taste return
("the book wasn't for me") maps to `changed_mind` without another policy-category
question. An eligible return card appears alongside one optional question about
what missed the mark. Confirmation never depends on an answer. Already-specific
feedback, a refusal, a request for only a refund, or a hurry skips that question.
Damage and wrong-item cases focus on the service failure rather than book discovery.

`record_reading_feedback` validates purchase ownership and records volunteered words
in case state and an `experience.reading_feedback` event. The reading specialist
receives this context if the customer later invites recommendations. This does not
write profile preferences; those still require a separate Save preference click.
Feedback events could inform future analysis, but the demo does not aggregate them,
measure customer satisfaction or retention, or claim a recommendation generated sales.
Evaluate live transcripts for immediate progress, one useful question, no repeated
diagnosis, respect for refusal, and recommendations grounded in the stated mismatch.

The Anthropic reading specialist uses Pydantic AI's `PromptedOutput`: JSON is parsed
and validated against `ReadingAdvice` with bounded retries, avoiding forced
structured-output tool selection rejected by some compatible models. Catalog, price,
stock, and preference checks still run in backend code. This trades provider-enforced
output structure for compatibility; invalid output fails rather than bypassing checks.

## Consent, idempotency, and persistence

The model may prepare a return, but has no tool for confirming it. Only a separate
customer click submits it. The backend rechecks customer ownership, current delivery
status, return window, proposal age, policy version, and prior return state. Row locks
serialize return submissions for the same physical copy. Unique constraints on item
and proposal prevent duplicate receipts. A repeated successful confirmation returns
the existing receipt. The recorded outcome says return requested, not refund issued.

Before each model turn, pending/recorded return status is rebuilt from database records.
Confirmation receipts are replayed once into model history as authoritative application
events, including for older conversations whose history omitted the button action.
`get_return_status` gives the generalist a fresh case-scoped status check. These records
override earlier awaiting-confirmation tool results. Completed receipt cards are
attached to their Bookly confirmation message rather than appended after later replies.
Client message IDs cannot use the reserved application-update prefixes.

Pending preference proposals are case-local. Only an explicit Save click updates the
shared profile; an event records consent provenance. Recommendation requests cannot
automatically overwrite that profile with warehouse inferences.

Each turn and its proposals/history are committed as one transaction; provider errors
roll back the turn. Client-generated request IDs deduplicate message retries. The
frontend preserves a retry ID after transport errors. The browser loads messages
and case state from the server on return; local storage holds only the selected case
ID. Resuming an earlier case restores its transcript and workflow state. The UI no
longer switches channels. Legacy async case records remain resumable as web chat;
the legacy API field is retained for compatibility, not as an implemented channel.

Conversation recaps are computed from customer message extracts, actual tool topics,
and recorded return outcomes. They require no schema migration or extra inference.
History reads and the `get_past_conversations` agent tool use server-bound customer
identity; historical summaries are context, not instructions or proof of current
eligibility. The original transcript remains available when a case is reopened.

`bookly/channel_prompts.py` separates web chat, SMS, and voice delivery instructions
from shared business policy. Only the chat profile is active. The SMS preview does
not change case state, collect phone numbers, call a provider, or simulate consent.

## Customer interaction and demo reset

Suggested prompts are editable drafts and never submit themselves. Only form submission
(the send button or Enter) starts an agent turn. A fresh case has no assistant greeting
or canned conversation. Browser reloads restore saved history; resetting is explicit.
Assistant Markdown is rendered on the server with raw HTML and images disabled.
Programmatic receipts are labeled as application updates, not model-generated messages.

The local `/api/demo/reset` endpoint requires a selected demo customer, same-origin
requests, and an explicit confirmation value. It transactionally clears dependent
records, restores fixtures and dates, resets custom profile preferences, and creates
a fresh case. It preserves demo sign-in sessions and the already-configured LLM.
The UI clears old selected-case IDs and drafts after success; a failed reset retains
the current screen. A reseed failure rolls back the entire reset.

Within a worker, mutation requests are serialized with an async lock. PostgreSQL
transactions take a shared advisory lock for ordinary writes and an exclusive lock
for reset, so active turns finish before reset removes their state across workers.
This avoids a slow model response restoring old records after reset. The reset
controls are intended only for this explicitly local, fictional demo.

## Limits and first production changes

The Docker-only distribution runs both app and database locally, installs locked
dependencies inside the image, excludes environment files from the build context,
and keeps the credential-free scripted walkthrough as a reproducible baseline.
Corporate gateway access is an optional configuration, not a reviewer prerequisite.

This is a single-worker local demo with synchronous database calls. It holds the case
transaction while the agent runs to keep state consistent. For production concurrency,
move to async data access and short transactions with case leases/version checks;
bound queues and retries explicitly. Process-local case locks are not a distributed
queue; PostgreSQL supplies the database locking boundary.

The first production requirement is real authentication/authorization and identity
mapping across channels. Next: versioned schema migrations, expiring/revocable demo
sessions replaced with actual sessions, message retention, bounded history and audited
memory edits, webhook delivery, provider/behavior evaluations, and durable execution
for warehouse/fulfillment/human events. Account management remains unsupported until
appropriate verification is implemented.

Refund settlement and shipping labels need real integrations with external idempotency
keys and outcome reconciliation. A database commit alone cannot guarantee an external
payment operation occurred exactly once. Similarly, a mock expert request is not a
human handoff: real staffing needs availability, ownership, notification, and service
expectations before the agent offers it as a real service.

Revenue and retention improvement are hypotheses. This prototype provides no measured
conversion, loyalty, or revenue uplift and does not record a recommendation as a sale.
