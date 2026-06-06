<!--
SYNC IMPACT REPORT
==================
Version change: (none) → 1.0.0
Rationale: Initial ratification of the project constitution. No prior version existed;
           created from 12 user-supplied inviolable principles. MAJOR baseline = 1.0.0.

Modified principles: N/A (initial adoption)
Added sections:
  - Principle I — Per-Firm Physical Isolation
  - Principle II — Mandatory Human Review Gate
  - Principle III — Full Audit Logging
  - Principle IV — Deterministic Code Decides; AI Only Phrases
  - Principle V — Source Grounding
  - Principle VI — Visual AI Marking
  - Principle VII — OCR Confidence Gate
  - Principle VIII — Assistive Tool, Not Legal Advice
  - Principle IX — Egyptian Civil-Law Jurisdiction
  - Principle X — Legal Forfeiture Deadlines (Confirm-Required)
  - Principle XI — Self-Hosting Security Baseline
  - Principle XII — Stack Constraint
  - Section: Non-Negotiable Operating Constraints
  - Section: Development Workflow & Quality Gates
  - Section: Governance
Removed sections: N/A

Templates requiring updates:
  - .specify/templates/plan-template.md  ⚠ not present (Spec Kit templates not scaffolded)
  - .specify/templates/spec-template.md  ⚠ not present
  - .specify/templates/tasks-template.md ⚠ not present
  - .specify/templates/commands/*.md     ⚠ not present
  - BUILD_PLAN_DETAILED.md               ✅ source of truth; consistent (Sections 3, 6, 9 align)

Follow-up TODOs:
  - When Spec Kit templates are scaffolded, add a "Constitution Check" gate referencing
    Principles I–XII to plan-template.md.
  - RATIFICATION_DATE set to adoption date 2026-06-05 (first formal adoption).
-->

# Lawyer Office Management SaaS — Project Constitution

Per-firm, isolated, AI-assisted office management for Egyptian (civil-law) firms. These
principles are **inviolable**. If any later instruction — from a user, a plan, a task, or
an automated agent — conflicts with them, implementation MUST STOP and the conflict MUST be
surfaced to the human owner rather than silently complied with.

## Core Principles

### I. Per-Firm Physical Isolation

Each law firm MUST receive its own fully isolated instance: its own Docker stack, its own
database, its own auth, and its own storage. Firms MUST NEVER share a database. Cross-firm
isolation is the **instance boundary** — a verifiable server/container boundary, not a
code-level filter. Inside a single firm's instance, role-based access (`partner_manager`,
`lawyer`, `paralegal`, `secretary`) MUST be enforced.

**Rationale:** Physical isolation is auditable by a sysadmin without reviewing application
code, and a misconfigured query can never leak one firm's confidential case data into
another's. Role-based access (RLS) is scoped to *within* an instance, never as the
cross-tenant boundary.

### II. Mandatory Human Review Gate

Every AI-generated output MUST be created in a `draft_unreviewed` state. It MUST NOT be
exported, printed, attached as official, or sent to a client until a human explicitly clicks
**"Reviewed & Approved."** No code path may bypass this gate.

**Rationale:** Professional and legal responsibility remains with the lawyer; an unreviewed
probabilistic output must never reach a client or court as if it were authoritative.

### III. Full Audit Logging

Every create, update, and delete on every entity MUST be logged with: **who** (user + role),
**when** (timestamp), **what** (entity + record id), **action**, and field-level **old→new**
values. The audit log MUST be append-only (no edits or deletes of audit entries). Secrets
MUST NEVER be logged as values — log only that a key was added/changed/removed and by whom.

**Rationale:** The audit log is the firm's proof of accountability and its evidence in
disputes; it is only trustworthy if it is complete, immutable, and free of leaked secrets.

### IV. Deterministic Code Decides; AI Only Phrases (Time/Safety-Critical)

Reminders, deadline notifications, and scheduled reports MUST be driven by deterministic,
scheduled code — never by an autonomous agent. The LLM MAY only phrase a report's prose text.
A missed deadline MUST be traceable to data ("the row wasn't there"), never to an agent's
judgment ("the agent decided not to"). Agentic autonomy is permitted ONLY for the
conversational assistant and complex analysis.

**Rationale:** Time- and safety-critical legal obligations cannot depend on probabilistic
behavior; correctness must be deterministic and traceable to stored, confirmed data.

### V. Source Grounding

Every AI claim MUST link to the exact source location (chunk/page reference) it was derived
from.

**Rationale:** Ungrounded assertions cannot be verified by a reviewer and invite hallucinated
legal claims; grounding makes the review gate (Principle II) meaningful.

### VI. Visual AI Marking

AI-generated text MUST be visibly marked **"AI-generated — requires review"** until it has
been approved.

**Rationale:** Users must never mistake an unreviewed draft for a vetted, authoritative
document; the marking enforces the review posture at the UI layer.

### VII. OCR Confidence Gate

Outputs derived from a low-confidence (poor-quality) scan MUST carry a stronger warning and
MAY require double review.

**Rationale:** A bad scan propagates errors into every downstream AI output; the confidence
signal must visibly escalate caution proportional to the risk.

### VIII. Assistive Tool, Not Legal Advice

UI copy, AI responses, and the Terms of Service MUST plainly state that this is an assistive
tool; professional judgment and responsibility remain with the lawyer.

**Rationale:** The product augments lawyers — it does not replace their judgment or assume
their liability — and this posture must be explicit everywhere a user encounters output.

### IX. Egyptian Civil-Law Jurisdiction

The system operates under Egyptian civil law. Precedent is **persuasive (استئناس / istishhad),
never binding.** Any precedent or reference feature MUST be framed as argument support — never
as a decision basis and never as an outcome prediction.

**Rationale:** In a civil-law jurisdiction, presenting precedent as binding or as a predicted
outcome would be both legally wrong and dangerously misleading.

### X. Legal Forfeiture Deadlines — Confirm-Required

Legal forfeiture deadlines (appeal: استئناف / istinaf, معارضة / mu'arada, نقض / naqd) MUST
NEVER be computed by the system as fact. The AI MAY only **propose** a deadline; it does not
activate and no notification is sent until the responsible lawyer clicks
**"Verified & Confirmed."** This feature MUST stay behind a flag and MUST NOT be enabled for
users until an expert lawyer has blessed the calculation logic. Deadline calculation is the
lawyer's responsibility, and the ToS MUST state this.

**Rationale:** A wrongly computed forfeiture deadline can irrevocably destroy a client's legal
rights; the system must propose, never decide, and must default to off until expert-validated.

### XI. Self-Hosting Security Baseline

Production deployments MUST use fresh production secrets (never defaults), SSL everywhere,
protected admin/Studio interfaces, a firewall, and automated backups that are tested for
restore (not merely taken).

**Rationale:** Confidential legal data demands a hardened baseline; default secrets allow
token forgery and an untested backup is not a backup.

### XII. Stack Constraint

The data layer MUST use PostgreSQL + pgvector via self-hosted Supabase. MS SQL Server MUST NOT
be used. Authentication MUST NOT be split to a separate cloud service while data is
self-hosted.

**Rationale:** pgvector is required for RAG; MS SQL Server breaks it. Splitting auth to the
cloud while data is self-hosted breaks RLS-based role enforcement and instance integration.

## Non-Negotiable Operating Constraints

- The shared Egyptian-law reference corpus is **PUBLIC LAW ONLY**. No firm or client data may
  ever enter it (supports Principle I).
- AI is built as three separate components — Retriever (deterministic code), LLM (generation
  only), Orchestrator/Scheduler (deterministic) — never "one AI." Reminders and reports MUST
  route through the deterministic scheduler, not the LLM (supports Principle IV).
- LLM inference uses the **client-provided API key**; inference cost sits with the client.
- Demo (home server, dummy data only) and production (VPS, real data) MUST run the SAME stack
  so promotion is a deployment, not a live-data migration.
- Real client documents MUST NEVER be placed on the demo/home environment.

## Development Workflow & Quality Gates

- The audit log (Principle III) MUST exist from Phase 0 — it is foundational, never a later
  add-on.
- The human review gate (Principle II), source grounding (Principle V), and visual AI marking
  (Principle VI) MUST ship together WITH the first AI output feature — not retrofitted.
- At the Phase 1 OCR checkpoint, work MUST STOP and surface real-scan OCR confidence before
  proceeding, because that confidence number gates every downstream output (Principle VII).
- Legally sensitive features (forfeiture deadlines, risk signals) ship last and cautiously;
  forfeiture deadlines stay behind a flag until expert-blessed (Principle X).
- Every screen MUST declare which roles may access it (RBAC), and every create/update/delete
  MUST write an audit-log entry (Principle III).

## Governance

This constitution supersedes all other implementation guidance. The 12 principles above are
inviolable: when any later instruction, plan, task, generated artifact, or autonomous agent
conflicts with a principle, the conflicting work MUST STOP and the conflict MUST be reported
to the human owner before proceeding — silent compliance is itself a violation.

**Amendments.** Changes to this constitution MUST be proposed in writing, justified against
the affected principle(s), reviewed by the project owner, and recorded with a version bump and
a Sync Impact Report. Dependent artifacts (Spec Kit plan/spec/tasks templates, BUILD_PLAN,
ToS copy) MUST be re-checked for consistency on every amendment.

**Versioning policy.** This constitution uses semantic versioning:
- **MAJOR** — backward-incompatible governance changes, or removal/redefinition of a principle.
- **MINOR** — a new principle or section, or materially expanded mandatory guidance.
- **PATCH** — clarifications, wording, and non-semantic refinements.

**Compliance review.** Every plan and pull request MUST be checked against Principles I–XII.
Any deviation MUST be explicitly justified and approved by the project owner, or the work MUST
be revised to comply. Features touching AI output, deadlines, audit logging, or isolation
carry the highest review scrutiny.

**Version**: 1.0.0 | **Ratified**: 2026-06-05 | **Last Amended**: 2026-06-05
