# Bookly pitch: speaker notes

Five slides. Open `output/bookly-pitch.html` and use the arrow keys to present. Press N for notes.

## Slide 1: Thesis

My belief is that a great CX agent should resolve issues with little effort and use proactive engagement to improve the next experience and increase loyalty. Proactive engagement means offering timely, relevant help based on known context, with respect for the customer’s preferences. For the customer, that means no repeated information or required feedback survey. For Bookly, it creates a way to understand a mismatch and give customers a reason to return.

In the demo, “The book wasn't for me” is already enough to prepare a return. One optional question can uncover “too dark,” but the customer can confirm without answering. An invited recommendation can then use that feedback, saved tastes, a prior review and dated activity. The demo demonstrates contextual, optional engagement within a conversation. Outbound proactive outreach is a production proposal. Increased loyalty and revenue are intended outcomes, not measured results.

Implementation sources: bookly/procedures/service.md; bookly/service.py; bookly/agents.py.

## Slide 2: Hybrid orchestration and delegation triggers

This slide shows the proposed hybrid target, not an implemented expansion of the runtime. The current app has the orders/support concierge and reading specialist. Returns/payments and account-management specialists are production proposals.

The web chat sends a request to FastAPI, which establishes identity and case scope. The generalist handles known supported paths using typed tools and approved help retrieval: order reads, general questions, and standard return proposals. A basic return is still a consequential action requiring backend eligibility, paid-amount checks and explicit confirmation. General account guidance is different from an account mutation.

The trigger is coverage by a supported procedure and sufficient evidence, not a model confidence score. Missing customer information gets one clarifying question. Conflicting return/fulfillment/payment evidence or a supported exception needing investigation goes to a returns/payments specialist. Evidence-dependent choices within an approved recovery process go to an account specialist. An invited reading consultation routes directly to reading expertise even when it is easy. Unsupported requests, identity bypasses and exceptions requiring discretionary authority go to approved verification or a human; delegation cannot authorize an override.

Specialists return evidence, proposed next steps and blockers to the concierge. The concierge normally retains conversational ownership. A full conversation handoff is explicit and durable, including a pause when a human owns the case. Customer confirmation and backend writes remain outside model authority.

Prompts and context are task-scoped. The generalist receives service procedure, channel rules and fresh case facts. A specialist receives its domain procedure and permitted tools, plus a minimal shared/customer view and retrieved domain-owned knowledge. Agents can call the configured provider API for LLM inference; shared provider access does not imply shared memory. Concierge tools are a separate path for grounded retrieval and backend-validated actions, not a specialist agent. A logical specialist does not require another container.

Sources for implemented behavior: bookly/app.py; bookly/agents.py; bookly/service.py; bookly/knowledge.py. Proposed routing and memory contracts: docs/production-agent-orchestration.md. Mermaid target: docs/bookly-architecture.mmd.

## Slide 3: Hybrid design choices and tradeoffs

Hybrid means one concierge handles routine support while domain specialists handle focused reasoning. Within that architecture, returns follow fixed steps and reading recommendations allow model judgment. Three choices define the design. First, keep routine supported work on the concierge/tool path and invoke specialists for task fit or domain interpretation. This avoids a specialist round trip for every order lookup, but introduces routing policy, delegation errors, model latency and a need for explicit ownership on longer tasks. Reading is a domain route rather than an exception route.

Second, share authoritative business and customer/case facts while assigning domain knowledge to a clear owner. This preserves continuity without giving every agent every conversation. The tradeoff is context contracts, retrieval, freshness, versioning and controlled promotion of new lessons. Unique memory is a logical namespace and ownership boundary, not necessarily another database. Customer-specific preferences are distinct from aggregate cohort priors. Current wishes and explicit evidence remain authoritative over inferred group signals.

Third, the return workflow uses explicit stages: identify the owned copy, check eligibility, prepare a confirmation card, and confirm through the application. Compared with flexible tool sequencing, this is easier to inspect and verify but cannot discover an unmodeled recovery path. It fits the narrow demo scenarios; broader production cases need more flexible planning and human review while retaining transaction invariants.

Curated RAG passages and source previews make explanations inspectable. Keyword retrieval can miss unfamiliar phrasing, and citations do not guarantee that every generated claim is correct. Evaluate routing, grounded answers, authority boundaries, cost and latency together rather than optimizing for the largest number of agents.

Implementation sources: bookly/service.py; bookly/app.py; bookly/agents.py; bookly/knowledge.py; bookly/presentation.py. Hybrid extensions are proposed.

## Slide 4: Domains and memory ownership

Each domain needs a purpose, a task-specific view of context and a clear owner for its expertise. It does not automatically need its own model loop.

Orders/support remains concierge-led for routine service. Its current-case view includes the owned order, delivery record and current question. A future domain knowledge store could own carrier playbooks and reviewed delay patterns. General help retrieval is a tool used across these domains, not another autonomous agent.

Returns/payments owns exception investigation. Its case context includes the purchase, paid amount, policy version, eligibility evidence, proposal, consent, receipt and payment references where supported. Unique domain knowledge contains approved exception procedures and reviewed resolution lessons. A specialist can investigate evidence; the backend still determines allowed amounts and execution.

Account management owns approved recovery. Its shared view contains verified identity status, allowed recovery stage and unresolved blockers, never passwords, reset links or verification secrets. Domain knowledge contains approved recovery procedures and reviewed failure patterns. Identity verification and credential changes belong to the authorized backend. These operational capabilities are future work, not current demo actions.

Reading/discovery owns personalized guidance. It sees the customer's current wishes, original reviews, explicit preferences, budget and eligible catalog. Domain-owned memory includes curated book knowledge, validated ranking lessons and aggregate cohort priors. Cohorts can combine genre interest, relevant geography and verified loyalty membership, but do not determine an individual's taste or override a current request. Membership benefits must be backed by policy and backend facts.

The memory architecture has four logical layers. Shared business/case state keeps authoritative facts, identity scope, owner, goals and confirmed actions. Customer-specific memory keeps personal preferences, reviews and consent within that customer's scope. Domain-owned memory keeps expertise and reviewed learning across permitted interactions. Ephemeral working context keeps the current shortlist and reasoning evidence, without automatic promotion to durable facts. Shared does not mean unrestricted: backend RBAC, object-level authorization and minimal projections apply.

The current reading specialist consumes application-managed context. It does not automatically learn or maintain an independent durable memory store. These logical layers can coexist in PostgreSQL or other governed stores without copying authoritative facts into inconsistent agent memories.

Sources: docs/production-agent-orchestration.md; current context implementation in bookly/agents.py and bookly/service.py. Conceptual background: https://www.anthropic.com/research/effective-context-engineering-for-ai-agents

## Slide 5: Production priorities

The slide groups production work into three priorities, in order: more flexible specialist workflows; connected service with human ownership; and specialist memory that improves with outcomes. Fixed workflows fit the narrow demo; broader cases need room to choose evidence and tool sequences, with permissions, transaction limits and consent still enforced.

Connected service requires durable case ownership with real human handoff and pause/resume. Persist the owner, handoff reason, evidence and pending actions. Stop competing agent writes while a human owns the case. Resume against current facts and revalidate identity, permissions and pending actions.

Then connect channels and backend systems. One verified customer and case should span chat, SMS and voice, with channel-specific instructions and explicit consent/confirmation mechanisms. Proactive outreach can use approved business-event triggers and opt-in preferences, with frequency limits and opt-out. Connect CRM/support, orders, fulfillment, payments and identity through least-privilege credentials, enforced RBAC and customer/object authorization. A prompt or an agent name is not a security boundary.

The current scenarios are narrow and well understood, so deterministic workflow constraints are a sensible starting point. In production, broader ambiguous cases may need specialists to select evidence, sequence tools, revisit hypotheses and choose among approved recovery paths instead of following one fixed sequence. Relax orchestration constraints deliberately as outcome evidence supports it, while retaining enforceable permissions, refund limits, consent and duplicate-action protection. This trades predictable execution for broader coverage and requires stronger evaluation, tracing and risk-based human review. Greater flexibility does not require removing all deterministic controls.

Expand specialist-owned memory through a controlled learning cycle: observed outcomes and volunteered feedback; validated aggregation or reviewed domain lessons; versioning and offline evaluation; approved publication and staged release; monitoring and rollback. Preserve source, time window, sample support, allowed use and expiry. A single conversation must not silently become a general policy, and a model does not automatically update its knowledge merely because it encountered a case.

For reading, aggregate cohorts may help when individual evidence is sparse, but they are soft priors. The current request, customer-specific feedback, budget and eligibility constraints come first. Geography should primarily support availability, language and local context. Loyalty membership should activate documented benefits rather than lower basic service quality for nonmembers. Do not expose other customers' raw conversations as evidence. Measure relevant satisfaction and successful outcomes, not only clicks or purchases.

Keep the stores distinct in responsibility: shared facts are authoritative, customer-specific memory is scoped, domain memory is curated/learned under review, and working context is temporary. Better domain memory may come from an analytics or recommendation service accessed by tools rather than dumping histories into prompts. There is no cohort-learning pipeline in the current mock demo.

Verified authentication, real backend integrations and operational evaluation are prerequisites for rollout. The demo implements web chat and fictional business data. SMS/voice, real human ownership, outbound outreach and the additional domain specialists remain proposals. Loyalty and revenue improvement remain hypotheses.

Sources: docs/production-agent-orchestration.md; current boundaries in bookly/app.py, bookly/agents.py and bookly/channel_prompts.py. Conceptual background: https://www.anthropic.com/research/effective-context-engineering-for-ai-agents

## Mermaid architecture

The editable source is [bookly-architecture.mmd](bookly-architecture.mmd).
