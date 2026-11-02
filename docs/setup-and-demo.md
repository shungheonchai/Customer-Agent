# Setup and demo reference

For the shortest startup path and core scenarios, see the [README](../README.md).
This guide contains optional setup details, local development instructions, and a
longer walkthrough. All records and integrations in the demo are fictional.

## Docker setup, ports, logs, and smoke walkthrough

Download/copy this entire repository, including `uv.lock`, and open a terminal in its
root folder. The only runtime prerequisite is **Docker Desktop (or Docker Engine)
with Docker Compose v2**, running. No host Python, uv, Node, API key, corporate network,
Atlas, or dataWarehouse account is needed for the scripted walkthrough.

```sh
docker compose up --build -d --wait
```

Open **http://127.0.0.1:8010**. Compose builds the Python app using the committed
dependency lockfile, starts PostgreSQL, waits for health checks, and seeds fictional
records. The first build downloads public images and Python packages; scripted mode
has no external runtime API or font dependency. Both services run on the laptop;
published ports are bound to loopback. See the detailed walkthrough below to recreate the demo.

If ports 8010 or 5435 are occupied, copy `.env.example` to `.env` and change
`BOOKLY_WEB_PORT` / `BOOKLY_DB_PORT` before starting. Open the configured web port.
On PowerShell, `Copy-Item .env.example .env` performs the copy; on macOS/Linux use
`cp .env.example .env`. Never overwrite an existing `.env` containing credentials.

Stop with `docker compose stop`. Start again with `docker compose up -d --wait`;
cases, returns, and preferences remain in the named PostgreSQL volume. Logs are
available with `docker compose logs web`. To deliberately start from original
fixtures, `docker compose down --volumes` **deletes this Compose project's local
demo database**, then `docker compose up -d --wait` creates it again. A new conversation
alone does not reset purchases or saved preferences.

The initial Docker-only path was verified with a separate fresh project and volume,
not the existing developer database. A credential-free smoke walkthrough is included:

```sh
docker compose exec -T web python - < scripts/smoke.py
```

Run it on fresh fixtures in scripted mode: it creates a return, so it is not a reset-free
repeated benchmark. In PowerShell, use `Get-Content scripts/smoke.py -Raw | docker compose exec -T web python -`.

## Optional local Python development

For editing/reloading Python without rebuilding the image, use Python 3.12+ and `uv`:

```sh
uv sync --frozen
docker compose up -d --wait postgres
uv run uvicorn bookly.app:app --host 127.0.0.1 --port 8010 --reload
```

If the containerized web service is already running, stop it with `docker compose stop web`
before using the same port. Local Python connects to PostgreSQL at loopback port 5435;
the web container connects to the internal `postgres` service. If you changed the
database host port, update `DATABASE_URL` for local Python too. Container configuration
sets its own internal database URL, regardless of that host-side setting.

The app creates missing tables and seeds fictional data on startup. Existing demos receive
missing catalog titles and an initial reading profile without resetting conversations,
purchases, returns, or saved choices.
Dates are anchored at the initial seed or last explicit reset. If rehearsing more
than 30 days later, use Reset demo data to restore fresh fixture dates.

Keep this app local. The customer picker simulates an authenticated customer and
is deliberately not production authentication. All books, customers, purchases,
policies, return requests, and warehouse aggregates are fictional. No money moves,
shipping label is generated, real warehouse queried, or real person contacted.

## Detailed walkthrough

Start as **Maya Chen**. A fresh conversation has no messages, but the customer already
has purchases, saved mystery/paperback preferences, and a dated review praising the
optimistic, small-town feel of *A Map of Sundays*. Theo has a separate profile: hopeful
science fiction in paperback, with a review of *An Orbit of Our Own*.

Starting topics and book cards **only fill the composer**. Edit the draft, then select
the up arrow or press Enter to send; Shift+Enter inserts a newline. The optional guide
drafts follow-ups after successful replies, but never sends them or confirms actions.
You can replace any draft or stop the guide. Live mode shows the configured model in
the header; scripted mode uses deterministic fixture responses and supports the prompts
below and close variations. Arbitrary conversational follow-ups require live mode.

1. **Resolve an ambiguous order question.** Send **“Where is my order?”**, then
   **“The Last Lighthouse.”** The generalist looks up Maya's purchases, clarifies by
   book title, and reports the recorded arrival estimate without promising delivery.
2. **Prepare a taste-related return.** Send **“Return The Midnight Archive. The book
   wasn't for me.”** The agent checks eligibility and prepares the return card while
   asking at most one optional question about what missed the mark. The return does
   not depend on answering. Reply **“It was too dark for me.”** to supply specific
   feedback; the agent uses it in this case without silently saving a lasting preference.
   A genre match does not justify challenging the customer's return decision.
3. **Resume and confirm.** Reload: the conversation and pending card remain. Select
   **Confirm return**. The backend rechecks eligibility and records one return request
   with its reference and next steps. This creates a mock request, not an issued refund.
4. **Invite a better fit.** Send **“Recommend a light mystery under $22.”** The
   generalist delegates to the reading specialist, which uses the current feedback,
   saved preferences, warehouse signals, and catalog. Inspect **Demo lab → Tool
   activity** for `specialist.delegated`, `warehouse.customer_signals`, `catalog.search`,
   and `specialist.recommendations`. The specialist returns at most two eligible books.
5. **Show personalization without repeating tastes.** Select **Start a fresh
   conversation**, choose **Find my next read**, and send **“Can you help me find my
   next read?”** Shared preferences and the earlier review are available immediately.
   Maya's saved mystery taste and the comforting tone she praised inform suggestions;
   she does not need to ask the agent to recall her own history. Mock wishlist activity
   favors *The Orchard House Puzzle*, recent browsing favors *The Lantern Club*, and
   an earlier dismissal excludes *The Teacup Alibi*. The $23 wishlist title drops out
   when she specifies a $22 budget; behavioral hints never relax her constraints.
6. **Inspect the evidence.** Hover, focus, or tap a **review · [date]** reference in
   the recommendation reason or reply. It reveals Maya's verbatim review and the book
   title. Earlier-conversation citations reveal the original customer message. Sources
   within the last 30 days show a full date; older sources show month and year. These
   are stored fictional records, not model-generated quotations. **Wishlist activity**
   and **browsing activity** references show dated observations, separately from reviews.
7. **Change the request.** Send **“Recommend a light mystery under $22”**, then
   **“Recommend a dark mystery under $22.”** The catalog has 24 fictional books—eight
   each in mystery, fiction, and science fiction—priced from $12 to $32, with varied
   settings, pacing, and themes. Current wishes override older tastes. The backend
   enforces stock, genre, mood, budget, and already-purchased-book exclusions.
8. **Explain the fit and save an explicit preference.** Send **“Which of those would
   you pick for me, and why?”**, then **“Remember I like lighter mysteries.”** Only
   clicking **Save preference** persists the new preference across conversations.
   Earlier review text and case-only return feedback remain distinct from saved tastes.
9. **Show continuity and account isolation.** Start a fresh conversation, then open
   **Past conversations** to inspect a recap or resume the original case. Recaps use
   stored messages and recorded actions. Asking **“What did we discuss in our last
   conversation?”** invokes the customer-scoped history tool. Switch to Theo in
   **Demo lab** and ask for a next read to see his separate purchases, review, and
   hopeful science-fiction choices.

For the damage branch, use **“Return The Midnight Archive. It arrived damaged.”** on
fresh fixtures. The agent focuses on the service failure rather than taste discovery.
To replay a completed return, select **Reset demo data** and confirm: it clears both
customers' conversations, returns, custom preferences, recommendations, expert requests,
and tool activity, then restores the catalog, orders, baseline preferences, reviews,
and warehouse snapshots with fresh dates. LLM settings and credentials stay unchanged.
A fresh conversation alone does not reset purchases, returns, or saved preferences.
Reset waits for active writes; reload other open demo tabs afterward.

**Continue this conversation with text messaging · Demo** opens a read-only SMS
preview: no number is collected, no message is sent, and the channel does not change.
**Demo lab → Channel prompts** compares active web-chat instructions with SMS and
voice reference prompts. Web chat is the only connected channel.

Demo lab also exposes the shared case state and actual tool activity. Assistant replies
render safe Markdown; customer messages remain literal text. Backend confirmation
receipts are labeled **Bookly update**, separate from agent replies. Customer selection
simulates sign-in using an HTTP-only, same-site session cookie; it is not production
authentication. All demo records persist in the named PostgreSQL volume.

## Mock help-center retrieval

**General questions** drafts shipping, password, and return-policy questions. Example
queries include “How much does shipping cost?”, “How long does shipping take?”,
“How do I reset my password?”, and “What is your return policy?”. “Do you offer gift
wrapping?” demonstrates the no-match fallback. Inspect `knowledge.retrieved` in Demo
lab to see the actual passage selection; hover, focus, or tap a **help article** citation
to inspect its source text, title, version, and update date.

Approved fictional content is in `bookly/support_articles.json`. Each article has
an ID, version, update timestamp, and passages with retrieval keywords. Bump the
version and update timestamp when changing policy content. Return passages substitute
constants from `bookly/policy.py`, also used by operational return checks. The retriever
uses topic anchors and keyword overlap with a small synonym map, returning up to three
passages. This is mocked local retrieval, not semantic/vector search; unfamiliar
phrasing may need a clearer query. Live mode generates answers from retrieved text;
scripted mode displays selected passages with citations. Neither mode implements real
password resets, reset emails, shipping changes, or payment refunds.

## Execution and LLM configuration

Four settings control the LLM connection. Mode is automatic: an empty or unset
`LLM_PROVIDER` selects credential-free scripted fixtures. A nonempty provider selects
live execution and requires a valid provider, model, and key. Invalid or incomplete
live settings fail explicitly; they never silently select scripted replies.

| Setting | Purpose |
| --- | --- |
| `LLM_PROVIDER` | Empty for scripted; `anthropic`, `openai`, or `google` for live |
| `LLM_MODEL` | Exact model ID available to your account; no provider prefix |
| `LLM_API_KEY` | Key for the selected provider or gateway |
| `LLM_BASE_URL` | Optional compatible gateway/API root; blank uses the public provider |

### New user setup: direct API key

Copy `.env.example` to `.env` if needed. Set the provider and model, and supply
your own key locally:

```dotenv
LLM_PROVIDER=anthropic
LLM_MODEL=your-accessible-model-id
LLM_API_KEY=your-private-key
LLM_BASE_URL=
```

For OpenAI, change `LLM_PROVIDER` to `openai` and provide an OpenAI model ID and key.
For Gemini, use `google` and a Gemini model ID and key. Choose a model supporting
function tools and structured output. All three SDKs are installed in the standard
Docker image. Both the generalist and reading specialist use the selected model;
customer-service procedures and tools remain unchanged.

OpenAI uses the Responses API, Anthropic uses Messages, and Google uses its Gemini
API-key adapter without requiring Vertex/ADC. Keys are passed explicitly to the SDK;
you do not also need provider-specific key variable names. Credentials remain
server-side, consistent with [OpenAI authentication guidance](https://developers.openai.com/api/reference/overview#authentication).

### Optional compatible gateway

A gateway changes the connection, not the provider or execution mode. For an
Anthropic-compatible gateway:

```dotenv
LLM_PROVIDER=anthropic
LLM_MODEL=your-router-model-id
LLM_API_KEY=your-router-key
LLM_BASE_URL=https://your-gateway.example/anthropic
```

These are placeholders, not a required corporate connection. The SDK appends
`/v1/messages`, so use the gateway prefix, not the full endpoint or a trailing `/v1`.
It sends the configured key as `x-api-key` and `anthropic-version: 2023-06-01`.
The installed SDK also appends `?beta=true`; compatibility with a real gateway still
needs a live check. OpenAI-compatible custom connections use the Responses API and
usually have a base URL ending in `/v1`. A gateway must support the selected adapter's
protocol; arbitrary routers are not automatically interchangeable.

### Apply changes and inspect selection

```sh
docker compose up --build -d --force-recreate web --wait
```

For local Python, restart Uvicorn. Start a fresh conversation after switching models:
provider-specific tool history is not guaranteed to be portable. Explicit customer
preferences remain shared across conversations.

- `bookly/models.py:configured_model` selects scripted when the provider is empty; otherwise it constructs the selected
  provider using the model ID, key, and optional URL.
- `bookly/app.py:create_app` constructs the selection once at startup.
- `bookly/agents.py:run_turn` supplies it to the generalist, and the recommendation
  tool supplies the same selection to the reading specialist.

Visit `/api/health` to see `mode`, `provider`, and `model`. Scripted mode reports null
provider/model because no live LLM is selected. Completed turns record these fields
in Demo lab's `agent.turn_completed` events. Keys and client representations are never
included in selection metadata.

There is no separate execution-mode switch. Existing mode variables are ignored;
`LLM_PROVIDER` alone determines scripted versus live. An empty provider ignores unused
model, key, and gateway values. To return to scripted mode, clear `LLM_PROVIDER` and
restart the web service. The top-right **Scripted · enable live** indicator is red;
click it for local configuration steps. No key is collected by the browser.

Missing live settings fail explicitly, and a failed provider request never falls
back to scripted output or a different provider. Protocol tests use mocked requests;
real availability, conversational quality, latency, and cost need live validation
with locally supplied credentials. Never put credentials in source files or chat.

