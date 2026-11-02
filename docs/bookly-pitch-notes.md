# Bookly pitch: speaker notes

Five slides. Open `output/bookly-pitch.html` and use the arrow keys to present. Press N for notes.

## Slide 1: Thesis

My belief is that a great CX agent should resolve issues with little effort and use proactive engagement to improve the next experience and increase loyalty. Proactive engagement means offering timely, relevant help based on known context, with respect for the customer’s preferences. For the customer, that means no repeated information or required feedback survey. For Bookly, it creates a way to understand a mismatch and give customers a reason to return.

In the demo, “The book wasn't for me” is already enough to prepare a return. One optional question can uncover “too dark,” but the customer can confirm without answering. An invited recommendation can then use that feedback, saved tastes, a prior review and dated activity. The demo demonstrates contextual, optional engagement within a conversation. Outbound proactive outreach is a production proposal. Increased loyalty and revenue are intended outcomes, not measured results.

Implementation sources: bookly/procedures/service.md; bookly/service.py; bookly/agents.py.

## Slide 2: Architecture

The web UI sends a message to FastAPI, which resolves the selected customer and case. The generalist owns the conversation. Its instructions combine a readable service procedure, channel guidance and fresh case context. Pydantic AI manages the model/tool loop and provider integration. I implement the tool contracts, delegation, data access, business rules and state.

Operational questions go through typed tools. General shipping, policy and password questions retrieve approved local passages. Invited discovery calls a separate reading specialist with a narrow tool set and structured output. Backend checks validate its catalog choices, budget and exclusions before the generalist responds.

PostgreSQL holds purchases, case state, history, explicit preferences, reviews, action events and mock warehouse snapshots. Confirmation bypasses the model: a separate customer click invokes a transactional endpoint. The next model turn receives the database-confirmed receipt in both current context and history, preventing an old pending tool result from becoming the source of truth.

Both agents live inside web-1 and use the same configured model through separate runs. postgres-1 is the database. External business data and integrations are mocked, while live mode makes actual model-provider calls. The customer picker simulates identity. The complete Mermaid source is docs/bookly-architecture.mmd.

Implementation sources: bookly/app.py; bookly/agents.py; bookly/models.py; bookly/service.py; compose.yaml.

## Slide 3: Key decisions: authority and grounded context

Decision 1: Put authority for consequential actions in backend code. The model can select an owned item and propose a return, but it has no tool to confirm or choose a refund amount. The confirmation endpoint rechecks ownership, delivery, return window and duplicates, then derives the amount from the purchased copy's paid price. A $24 copy produces a $24 return request. Transactions and unique constraints protect repeat submission. This adds integration work and a confirmation step, but gives a stronger action boundary than an instruction telling the model to obey policy. The current customer picker is a demo identity, not production authentication.

Decision 2: Ground knowledge and distinguish kinds of context. General support uses bounded keyword retrieval over versioned help articles. Personal explanations cite reviews, actual customer messages or observed activity, with dated source previews. Current constraints and explicit feedback take precedence over behavioral hints. Shared return-policy constants reduce drift between help text and execution.

The tradeoff is curated content and a limited retriever that can miss unfamiliar phrasing. Sources need versions, freshness and maintenance. In return, explanations are inspectable and unknown topics can fail honestly. Citations improve auditability, but they do not by themselves guarantee every generated sentence is correct. Backend validation remains necessary for actions.

Implementation sources: bookly/policy.py; bookly/knowledge.py; bookly/support_articles.json; bookly/warehouse.py; bookly/presentation.py; bookly/service.py.

## Slide 4: Key decision: bounded delegation

Decision 3: Keep one customer-facing concierge and delegate only a bounded reading task. This keeps the customer in one conversation while giving the reading specialist a specific responsibility and small tool surface. The specialist receives relevant preferences, reviews, current feedback and validated behavioral evidence, searches eligible catalog books and returns at most two structured picks. It cannot execute account actions. The generalist receives the validated result and responds.

The cost is another model run, more latency and a context contract between the agents. I accepted that cost because the recommendation task benefits from richer context and distinct reasoning, while order and return work should remain focused on service and deterministic rules. Both agents run in one web service, since the demo does not need independent scaling.

This is selective delegation. Help-center retrieval and order reads remain tools rather than separate agents. Adding an agent only makes sense when its task, permissions and output boundary justify the extra coordination.

Implementation sources: bookly/agents.py, especially recommend_books, reading_candidates and the specialist tool definitions.

## Slide 5: Production priorities

My first product change would be durable case ownership and a real human handoff, rather than simply adding a live-chat button. A handoff needs an owner, a reason, a concise evidence-backed summary, pending action state and a clear indication of what the human or customer must do next. When a human takes over, the agent must pause and stop competing writes. Resume should reload current business state and revalidate pending actions.

That same durable case model supports asynchronous interactions, channel changes and proactive outreach. Chat, SMS and voice should share a verified customer identity and case, with channel-specific prompts and explicit authorization mechanisms. Moving from chat to SMS must not lose an already completed return or silently reuse web-button consent. Useful outreach could notify an opted-in customer about a delivery delay or a return milestone, or offer relevant reading updates when requested. Use approved business-event triggers, consent, channel preferences, frequency limits and a clear opt-out. The demo currently implements only web chat. SMS and voice are design previews, expert requests do not contact real staff, and no outbound outreach occurs.

I would then integrate the necessary backend systems, such as CRM/support, order management, fulfillment, payments and identity, with explicit role-based access control (RBAC). Enforce customer and object-level authorization in each connector, scoped service credentials, and an audit trail for reads and actions. A reading specialist should access permitted catalog and reading context, while a support role can inspect owned orders and propose permitted actions. Payment execution requires a separately authorized backend path. Recheck permissions when ownership changes or a paused case resumes.

These integrations should provide authoritative business context with owned, versioned policies and a freshness/refresh strategy. Customer context should distinguish statements from inferred behavior. Give each agent the task-specific context projection and permissions it needs. Confirmed action events must stay authoritative across pauses, human ownership and channels.

Verified authentication and real backend integrations are release prerequisites. I would evaluate successful resolution, unnecessary repeated questions and handoff completion before claiming gains in retention or revenue. These are proposed production changes, not current capabilities.

Implementation sources for current boundaries: bookly/app.py; bookly/channel_prompts.py; bookly/agents.py; docs/architecture.md.

## Mermaid architecture

The editable source is [bookly-architecture.mmd](bookly-architecture.mmd).
