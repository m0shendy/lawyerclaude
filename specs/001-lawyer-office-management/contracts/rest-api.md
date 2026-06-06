# REST API Contract (FastAPI)

**Plan**: [../plan.md](../plan.md) · **Data model**: [../data-model.md](../data-model.md)

Conventions: JSON over HTTPS; auth via Supabase GoTrue JWT (Bearer); server resolves
user + role from the token; all mutations are audited; RBAC enforced server-side. Errors use a
consistent `{ "error": { "code", "message" } }` envelope. Roles: `partner_manager` (manager),
`lawyer`, `paralegal`, `secretary`.

## Auth & session
| Method | Path | Roles | Notes |
|---|---|---|---|
| POST | `/auth/login` | all | GoTrue; per-instance users only. Inactive users rejected. |
| POST | `/auth/logout` | all | |
| GET | `/me` | all | profile + role + assigned cases |

## Cases & assignments
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/cases` | all | role-scoped list |
| POST | `/cases` | manager, lawyer | create (audited) |
| GET | `/cases/{id}` | assigned/manager | detail: documents, ai_outputs, deadlines, tasks, assignments |
| PATCH | `/cases/{id}` | manager, assigned lawyer | update (audited, field old→new) |
| DELETE | `/cases/{id}` | manager | delete (audited snapshot) |
| POST | `/cases/{id}/assignments` | manager, lawyer | assign user (audited) |
| DELETE | `/cases/{id}/assignments/{userId}` | manager, lawyer | unassign (audited) |

## Documents & pipeline
| Method | Path | Roles | Notes |
|---|---|---|---|
| POST | `/cases/{id}/documents` | manager, lawyer, paralegal, secretary | upload → Storage, row `pending` (audited) |
| GET | `/documents/{id}` | assigned/manager | status lifecycle, ocr_confidence |
| GET | `/documents/{id}/status` | assigned/manager | `pending`→`processing`→`ready`/`low_confidence`/`failed` |
| GET | `/documents/{id}/chunks` | assigned/manager | grounding source refs |

*Pipeline is async (background worker); upload returns immediately with `pending`.*

## AI outputs & review gate  **[C-II][C-V][C-VI]**
| Method | Path | Roles | Notes |
|---|---|---|---|
| POST | `/documents/{id}/summarize` | assigned, manager | creates `summary` + `extraction`, `draft_unreviewed`, grounded |
| POST | `/documents/{id}/analyze-contract` | assigned, manager | `analysis`/`clause_flag` outputs (P4) |
| POST | `/documents/{id}/risk-signals` | assigned, manager | `risk_signal` outputs, posture text (P5) |
| GET | `/ai-outputs?state=draft_unreviewed` | assigned/manager | review queue |
| GET | `/ai-outputs/{id}` | assigned/manager | content + source_links + AI marking + low_confidence_flag |
| POST | `/ai-outputs/{id}/approve` | **assigned lawyer or manager only** | sets `approved` + approved_by/at/version (audited high-value). Paralegal/secretary → 403 (FR-018) |
| POST | `/ai-outputs/{id}/export` | assigned/manager | **403 unless `approved`** (no bypass, R7) |

## Deadlines  (incl. confirm-required appeal types **[C-X]**)
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/cases/{id}/deadlines` | assigned/manager | general + appeal suggestions |
| POST | `/cases/{id}/deadlines` | manager, assigned lawyer | general deadline (audited) |
| PATCH | `/deadlines/{id}` | manager, assigned lawyer | update (audited) |
| DELETE | `/deadlines/{id}` | manager, assigned lawyer | delete (audited) |
| POST | `/deadlines/{id}/confirm` | **responsible lawyer** | appeal suggestion → `confirmed=true`; only now do reminders schedule. Gated by `feature_appeal_deadlines` |
| (suggest) | *internal, flag-gated* | system | appeal suggestion created `confirmed=false`, no notification |

## Tasks
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET/POST | `/cases/{id}/tasks` | manager, lawyer, paralegal | CRUD + assign + due_date (audited) |
| PATCH/DELETE | `/tasks/{id}` | manager, assignee | (audited) |

## Assistant (also available over WhatsApp — see whatsapp.md)
| Method | Path | Roles | Notes |
|---|---|---|---|
| POST | `/assistant/query` | all (scoped) | RAG over private+shared; grounded; scoped to caller's assigned cases; official artifacts created `draft_unreviewed` |

## Reports (manager only)
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/reports/daily` | **manager** | "what happened today" / "tomorrow's tasks"; items reconcile to audited data |

## Settings / Users / Audit (manager only)
| Method | Path | Roles | Notes |
|---|---|---|---|
| GET | `/settings` | manager | secrets returned **masked** |
| PATCH | `/settings` | manager | key add/edit logged as **action + who**, never the value (**[C-III]**) |
| GET/POST | `/users` | manager | CRUD users + assign roles (audited) |
| PATCH/DELETE | `/users/{id}` | manager | (audited); deactivating blocks login + assistant |
| GET | `/audit-log` | manager | **read-only** change history |

## Standard responses
- `200/201` success · `400` validation · `401` unauthenticated · `403` RBAC/review-gate violation
  · `404` not found/out-of-scope · `409` invalid state transition (e.g., approve already-approved).
