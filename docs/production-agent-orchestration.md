# Proposed Bookly domain orchestration

This is a production proposal. The current app still implements a generalist concierge,
a reading specialist, and operational/retrieval tools. Account mutations and payment
settlement are not implemented.

The reason to split a domain is its ownership, policy, authorization, integrations,
workflow state, and evaluation needs. The reason to add a separate LLM agent is a
sufficiently distinct reasoning task and context/tool contract. These are related
choices, but one does not require the other.

| Option | Structure | Best fit | Tradeoff |
| --- | --- | --- | --- |
| Modular domain workflows | Concierge invokes returns/payments and account services | Known common paths with deterministic rules | Lowest extra model cost, but concierge still interprets intent across domains |
| Supervisor with domain agents | Concierge delegates domain tasks and receives typed results | Exception-heavy returns or recovery with several evidence-dependent decisions | Better prompt/tool separation, but extra latency and delegation failures |
| Routed conversation ownership | A domain agent owns a task until it finishes or hands off | Long domain-specific conversations and human escalation | Fewer supervisor round trips, but explicit ownership and context transfer are essential |

Recommended direction: a hybrid. Establish domain workflows and scoped connectors,
then introduce domain agents where measured task quality justifies another reasoning
loop. The domain agents can initially run in the same service. Container count is a
separate deployment decision.

## Domain contracts

- **Orders/support:** own routine order and delivery guidance. Use the owned order,
  recorded delivery facts and current issue as case context. Curate support/carrier
  playbooks and reviewed delay patterns as domain knowledge. The concierge can use
  this domain without a separate agent for routine reads.
- **Returns/payments:** own the selected purchase, evidence, policy version, return
  proposal, customer confirmation, request receipt, and settlement references. The
  model may interpret an exception and propose a next step. Backend services still
  enforce ownership, amount, idempotency, and payment authorization.
- **Account management:** own verified recovery state and permitted account-change
  steps. The model can select allowed steps or ask a focused question. Identity
  verification and credential changes belong to the identity service. Never put
  passwords or verification secrets in model context.
- **Reading:** own a narrow consultation task and structured recommendations, using
  a scoped view of preferences, reviews, current wishes, behavior, and catalog data.
  The current specialist reads application-managed context rather than maintaining
  a separate durable memory store.

## State and permissions

Keep one durable case and authoritative action log, with domain workflow state and
an explicit active owner. Give each agent a minimal context projection. Shared
business facts should have an authoritative owner, source version, and freshness
rules; copying them into independent agent memories creates consistency problems.

Enforce RBAC and customer/object-level authorization in backend connectors. A domain
agent's prompt or name does not grant or enforce permissions. Handoff and resume
must revalidate identity, ownership and pending actions. Human ownership pauses
agent execution. Confirmed business events override older proposed-action text.

## Why the original demo was small

The two-agent structure demonstrates an inspectable end-to-end journey. The reading
specialist isolates a distinct consultation with constrained tools and output. That
choice does not mean refunds and account management should remain in a broad
concierge as their production scope grows. A separate agent for today's unsupported
account mutations would mostly be an empty wrapper; verified recovery and backend
contracts need implementation first.

Conceptual reference: [Anthropic, Building effective agents](https://www.anthropic.com/research/building-effective-agents).
The article distinguishes workflows from agents and describes customer-support routing.
The Bookly proposal above is an engineering judgment, not a requirement from that source.

## Explicit complexity boundary

Routine reads stay with the concierge when the target is identified, required facts
are available, and an existing tool or approved article fully covers the request.
A basic return is still a consequential action: it stays on the known backend path
with ownership checks, eligibility, paid amount and explicit confirmation.

Delegate a bounded task when a supported request needs domain-specific interpretation,
several evidence-dependent decisions, reconciliation across systems, or sustained
reasoning with a distinct context and tool set. Examples include conflicting delivery
and return records, or choosing among approved account-recovery steps. The specialist
returns evidence, a proposed next step, and blockers to the concierge.

Unsupported actions, missing authorization, identity bypass requests and policy
exceptions requiring discretion do not become permitted by delegation. Use an
approved verification workflow, request blocking information, or transfer ownership
to a human. Do not route based solely on an LLM's self-reported confidence.

The routing policy should define supported intents, required evidence, allowed actions,
exception categories and escalation triggers. Evaluate it using representative cases.
In the default supervisor pattern, the concierge remains the customer-facing owner;
a specialist taking over a whole conversation requires an explicit ownership handoff.

## Shared memory and specialist-owned memory

These are logical ownership and permission boundaries, not necessarily separate
databases or copies of the same facts.

| Layer | Contents | Access/authority |
| --- | --- | --- |
| Shared business and case state | Verified customer identity, order facts, active case owner, action receipts, current goal and unresolved blockers | Authoritative backend records, scoped to customer and task |
| Customer-specific memory | Explicit preferences, original review/feedback, consent, relevant interaction history | Customer-scoped with source and time; current requests take priority |
| Specialist-owned domain memory | Curated domain expertise, approved procedures, reviewed lessons and validated cohort/ranking signals | Owned by each domain, retrieved through a relevant minimal projection |
| Ephemeral working context | Candidate shortlist, supporting evidence and the current consultation plan | Bounded to the active task; not automatically promoted into lasting facts |

A reading specialist can benefit from collective experience. Aggregate outcomes by
relevant signals such as explicitly stated genre interests, prior feedback, region,
and verified loyalty membership. Record source, time window, metric definition,
sample support and limitations. Treat overlapping cohorts as soft priors, not as a
claim about a particular customer's taste.

Use geography primarily for availability, delivery, language and local context.
Regional reading signals can rank suitable books when individual evidence is sparse.
Membership may determine verified program benefits; it should not silently lower
service quality for nonmembers or invent entitlement. Explicit wishes, budget, stock,
customer consent and backend rules remain authoritative over cohort hints.

Past conversations do not automatically update an agent's model or memory. A proposed
learning path is: observed outcomes and volunteered feedback, then validated aggregation
or reviewed domain lessons, then versioned cohort/ranking signals retrieved for future
consultations. Avoid exposing other customers' raw conversations to the current user,
and do not let one interaction silently become a general rule. Evaluate usefulness
against relevant feedback and successful outcomes rather than treating clicks or
purchases alone as proof of satisfaction.

For example, Maya's saved mystery preference and her own optimistic-tone review can
combine with an aggregate signal about readers who explicitly prefer gentle mysteries.
The specialist retrieves that signal to rank eligible candidates. If Maya now asks
for a dark thriller, the current request overrides that prior. The answer should cite
Maya's actual review when referring to what she said and label aggregate conclusions
as inferences, without exposing another customer's private story.

The current demo already has customer reviews/preferences and mock individual activity;
it does not compute cohort learning or persist specialist-specific learning from use.
This section describes a production evolution rather than another backend flow.

Context-design reference: [Anthropic, Effective context engineering for AI agents](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents).
The Bookly layers, routing criteria and cohort design above are proposed engineering choices.

## Publication and improvement of domain memory

Treat learning as an explicit production workflow: collect outcomes and volunteered
feedback, validate aggregates or review proposed lessons, version the result, evaluate
it offline, approve publication, retrieve only relevant permitted knowledge, and monitor
with rollback. Domain owners approve promotion; an individual model turn cannot rewrite
policy or grant itself new permissions. Persist supported findings and source evidence,
not unverified reasoning as fact. This does not imply automatic training of model weights.

Evaluate changes by domain: verified resolution and avoidable escalations for support,
policy/authorization correctness for returns and recovery, and relevant feedback and
satisfaction for reading. Clicks and purchases alone do not establish good advice.
Keep cohort sources, time windows, sample support, expiry and allowed use inspectable.

The five-slide pitch and README summarize this same proposed target. The current
implementation diagram is [bookly-current-architecture.mmd](bookly-current-architecture.mmd);
the target is [bookly-architecture.mmd](bookly-architecture.mmd).

## Production priorities and workflow flexibility

The pitch consolidates production expansion into three priorities:

1. **More flexible specialist workflows.** The current return sequence identifies the
   owned copy, checks eligibility, presents a card and requires confirmation. This fits
   known scenarios and is easy to verify, but cannot discover an unmodeled recovery path.
   Broader cases may let specialists choose evidence, sequence tools and revisit
   hypotheses within approved procedures. Expand autonomy using evaluation and outcome
   evidence; retain permissions, transaction limits, consent and duplicate-action controls.
2. **Connected service with human ownership.** Integrate backend systems through enforced
   RBAC and customer/object authorization. Preserve case context across channels and
   human handoffs, support pause/resume and consent-based proactive outreach.
3. **Specialist memory that improves with outcomes.** Review feedback, evaluate and approve
   versioned lessons, publish scoped knowledge, monitor changes and support rollback.
   Shared customer facts remain authoritative over inferred cohort patterns.

Hybrid describes concierge-led routine tool workflows plus focused domain specialists.
It also combines fixed return stages with flexible reading selection and explanation.
A backend integration itself is a baseline requirement; the design tradeoff is the degree
of freedom allowed in sequencing actions and handling cases outside an explicit workflow.
