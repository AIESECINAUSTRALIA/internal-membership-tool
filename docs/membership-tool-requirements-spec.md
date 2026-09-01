# Membership / Data Management Platform — Requirements Spec

Status: draft · Owner: Tech Lead · Last updated: 2026-08-31

This is the full requirements reference for the Membership / Data Management Platform.
It describes the long-term product vision. Items that are **not** for this term are
marked **[Phase 2]** — design for them, don't build them yet.

Read `CLAUDE.md` first. The governing constraint for every decision in this document
is **annual turnover**: assume whoever built a thing is gone next year and whoever
maintains it has zero prior context.

`TODO:` callouts mark information the team must obtain before the affected part can be
finalised. Nothing behind a `TODO:` has been guessed or invented.

---

## 1. Overview

### 1.1 Problem

Local Committee (LC) member and productivity data lives in scattered, per-LC
spreadsheets. There is no single source of truth, no consistent access control, no
reliable analytics, and official reports (NAMs, SONA, MTR) are assembled by hand from
inconsistent inputs. Data is manually re-linked between sheets; aggregates are
re-entered rather than computed.

### 1.2 What we're building

A single web application backed by one relational database that is the source of
truth for:

- **People and membership** — who is a member, in which LC, in which position and
  function, over time.
- **Productivity / KPI data** — recorded at a granular grain so every rollup and
  report is a query, never a re-entered number.
- **Access** — a two-dimensional (position × function) permission matrix, stored as
  data.
- **Analytics** — dashboards with arbitrary date-range filtering.
- **Official reporting** — NAMs, SONA, MTR produced from queries against the granular
  data.
- **Privacy** — genuine deletion/anonymisation requests, with an audit trail.

### 1.3 Non-goals

See `CLAUDE.md` → "Explicit non-goals for this term". In short: no Exchange SU
pipeline, no website/membership shared auth, no scheduled/automated report exports, no
mobile/offline, no custom payments. These are **[Phase 2]** and appear in this
document only where the data model must leave room for them.

### 1.4 Success criteria

- One LC's productivity data can be fully migrated off spreadsheets and maintained in
  the tool with no external sheet.
- NAMs / SONA / MTR for that LC can be generated from the tool with no manual
  aggregation.
- A member can be granted exactly the access their position × function implies, with
  no code change — only data.
- A deletion request can be honoured and evidenced, without breaking historical
  reports.
- A new developer can read this spec plus the schema and understand the system
  without talking to anyone.
- An authorised non-technical admin can restructure the org's data — see §1.5 —
  without a developer or a deployment.

### 1.5 Runtime-manageable by design

**The default assumption for every feature is that its underlying data is
created, edited, moved, and removed by authorised users through the app's own
UI — at runtime, with no code change, no migration, and no developer.** This is
a direct consequence of the turnover constraint: next year's team will not be
able to (or want to) edit code to reflect an org restructure.

Concretely, the app must provide managed CRUD for at least:

- **LCs / entities** — add, rename, mark inactive, merge. (Hard-delete only when
  empty; otherwise deactivate — same anonymise-over-delete logic as people.)
- **People** — add, edit, deactivate; anonymise/delete via §8.
- **Memberships** — assign a person to an LC / position / function / term;
  end-date, transfer, or correct an assignment.
- **Teams** — create, rename, disband; move members between teams; reassign a
  team leader; re-parent a team to a different function.
- **Positions & functions** — add, rename, deactivate the lookup values
  themselves (with the `TODO:` authoritative list as the seed, not a ceiling).
- **Metrics / KPIs** — add a new metric, edit its label/validation/unit,
  deactivate a retired one — all via the `attribute` catalog (§4.2), never a
  schema change.
- **Terms / cycles** — define and edit the date boundaries used for scoping.
- **Permission matrix** — edit who-can-do-what (§3.3).
- **Custom fields** — add function-specific attributes to people or memberships
  via the `attribute` catalog.

Design rules that follow from this:

- Anything an admin can create, an admin can also rename and deactivate. Prefer
  **deactivate / soft-delete** for anything referenced by history; reserve
  hard-delete for genuinely unreferenced rows (and privacy requests, §8).
- Renaming or deactivating a lookup value must never break historical records
  that point at it.
- These management screens are themselves permissioned through the matrix
  (§3) — e.g. `resource = lc`, `action = manage` — so the capability is granted
  by position, held by ≥2 people, never hardcoded to a named user.
- Every create / edit / deactivate / move described here is written to the
  audit log (§8.4).
- No feature should require editing a config file, enum, or seed script to
  reflect a normal operational change. If a proposed feature can only be
  reconfigured by a developer, that is a design flag to resolve before build.

The few things that are **not** runtime-editable by admins — and are expected to
need a developer — are the shape of the schema itself, the report layouts
(§7), and the set of protected `resource` / `action` names in the permission
model.

---

## 2. Users & personas

Access and needs are defined by **position × function**, not a flat role. The
positions and functions below are the working set; confirm against the authoritative
list.

`TODO:` Obtain the authoritative list of **positions** (e.g. LCP, LCVP, Team Leader,
Member, and any MC-level equivalents) and **functions** (e.g. oGV, iGV, oGTa/oGET,
iGTe, BD, F&L, MKT, PM&IM/Digital, EwA, MXP) from current national structure docs.
Everything in §3 and §4 depends on it.

| Persona | Position | Typically needs to |
|---|---|---|
| LC President | LCP | See everything for their LC; manage members, positions, teams; read all reports for their LC. |
| LC Vice President | LCVP (per function) | Full read/write on their **own function's** members, teams, and KPI data for their LC; read-only on other functions. |
| Team Leader | Team Leader | Read/write KPI and activity data for **their team's** members; read their function's dashboards. |
| Member | Member | See and update their own record; enter their own activity/KPI contributions where the function allows self-reporting; read dashboards they're granted. |
| MC / National (future) | MC positions | Cross-LC read for reporting and analytics. **[Phase 2]** for write; read-only reporting is in scope this term if data exists. |
| Data / Privacy admin | (assigned) | Process deletion requests, view the deletion-request and audit logs. Should be a **position-linked** capability, not a named person. |

There is no separate "system administrator" account tied to an individual. Elevated
capability (permission-matrix editing, deletion processing) is granted through
position, held by at least two people at all times.

---

## 3. Access control

### 3.1 Model

Access is decided by a **permission matrix stored in the database**, not by
`if`/`else` in code. A permission check answers:

> Given this user's **current memberships** (each a position × function × LC, possibly
> more than one), may they perform **action** on **resource**, scoped to **whose**
> data?

Components:

- **`resource`** — a named thing the app protects, e.g. `member_record`,
  `kpi_record`, `team`, `report.nams`, `permission_matrix`, `deletion_request`.
- **`action`** — `view`, `create`, `edit`, `delete`, `export`, `manage`.
- **`scope`** — how far the grant reaches: `own` (just themselves), `team`,
  `function` (their function within their LC), `lc` (whole LC), `all` (cross-LC).
- **`permission_matrix`** row — `(position, function, resource, action) → max_scope`.
  `function` may be a wildcard for position-only rules (e.g. LCP).

### 3.2 Resolution

1. Resolve the user's authenticated email to a `person` and their **active**
   `membership` rows.
2. For each membership, look up matching `permission_matrix` rows for the requested
   `resource` + `action`.
3. The user's effective grant is the **widest `max_scope`** across their memberships.
4. The application then filters the query to that scope (e.g. `scope = 'function'`
   ⇒ `WHERE lc_id = :lc AND function_id = :fn`).

Deny by default: no matching row ⇒ no access.

### 3.3 Editing the matrix

- Editable in-app by holders of `manage` on `permission_matrix` (a small set of
  positions).
- Every change is written to the audit log (§8.4) with before/after.
- Seed values live in a committed migration / seed file so a fresh environment is
  reproducible and the intended baseline is documented.

`TODO:` Produce the initial permission-matrix seed as a reviewed table
(position × function × resource × action × scope) with the Tech Lead and at least one
LCP before build. This is a data task, not a code task.

---

## 4. Data model

Approach: **hybrid**. Core entities are ordinary relational tables with foreign keys
and constraints — they are queried constantly, appear in every report, and must be
readable by a new developer. The **volatile** parts — which KPIs exist, and any
function-specific custom fields — use an **EAV (entity–attribute–value)** design so a
new metric next term is a row, not a schema migration.

Everything that changes term-to-term (functions, positions, KPI definitions,
permission rules) is a **lookup / config table**, never a hardcoded enum in code.

### 4.1 Core relational tables

| Table | Purpose | Key columns |
|---|---|---|
| `lc` | AIESEC entity / local committee (and MC as a row). | `id`, `name`, `type` (`lc` / `mc`), `active` |
| `term` | A cycle for time-scoping memberships and KPIs. | `id`, `name`, `start_date`, `end_date` |
| `position` | Lookup. | `id`, `key`, `label`, `rank`, `active` |
| `function` | Lookup. | `id`, `key`, `label`, `active` |
| `person` | One human. PII lives **only** here. | `id`, `full_name`, `preferred_name`, `aiesec_email` (unique), `personal_email` (nullable), `phone` (nullable), `join_date`, `status` (`active` / `alumnus` / `inactive` / `anonymised`), `anonymised_at` (nullable) |
| `membership` | A person's assignment. A person may have several concurrent rows. | `id`, `person_id`, `lc_id`, `position_id`, `function_id` (nullable for non-functional positions), `term_id`, `start_date`, `end_date` (nullable = current), `is_primary` |
| `team` | A team inside a function within an LC. | `id`, `lc_id`, `function_id`, `term_id`, `name`, `leader_membership_id` (nullable) |
| `team_member` | Membership ↔ team. | `id`, `team_id`, `membership_id`, `start_date`, `end_date` (nullable) |
| `permission_matrix` | §3. | `id`, `position_id`, `function_id` (nullable = any), `resource`, `action`, `max_scope` |

Notes:

- **Access control reads `membership`**, filtered to rows where
  `start_date <= today AND (end_date IS NULL OR end_date >= today)`. History is kept
  by not deleting old rows.
- `person.aiesec_email` is the join key from the OAuth identity (§7).
- A person with no active membership can still authenticate but resolves to no
  access (e.g. alumni).

### 4.2 EAV: attribute catalog + values

**`attribute`** — the catalog of every custom/volatile field and every KPI. This is a
config table; adding a metric = inserting here.

| Column | Purpose |
|---|---|
| `id` | PK |
| `key` | Stable machine key, e.g. `ol_signups`, `ep_interviews`, `shirt_size` |
| `label` | Human label for the UI |
| `applies_to` | `person` \| `membership` \| `kpi` |
| `data_type` | `text` \| `number` \| `date` \| `boolean` \| `enum` |
| `unit` | Optional display unit (`count`, `AUD`, …) |
| `enum_options` | JSON array when `data_type = enum` |
| `validation` | JSON (min/max, required, regex) applied on write |
| `function_id` | Nullable — set when the attribute only applies to one function |
| `active` | Soft-disable without deleting history |
| `term_introduced` | For provenance / turnover context |

**`attribute_value`** — values for `applies_to IN ('person','membership')` (profile
and function-specific custom fields).

| Column | Purpose |
|---|---|
| `id` | PK |
| `attribute_id` | → `attribute` |
| `entity_type` | `person` \| `membership` |
| `entity_id` | id within that table |
| `value_text` / `value_number` / `value_date` / `value_bool` | **Typed columns** — write the one matching `attribute.data_type`. Typed columns (not a single stringly value) keep reporting queries sane. |
| `recorded_by` | → `membership` |
| `recorded_at` | timestamp |

Unique on `(attribute_id, entity_type, entity_id)` for single-valued attributes.

### 4.3 KPI / productivity records

KPIs are EAV-catalogued (`attribute.applies_to = 'kpi'`) but stored in their **own
table** because they are time-series and drive every date-range dashboard and report.

**`kpi_record`**

| Column | Purpose |
|---|---|
| `id` | PK |
| `attribute_id` | Which KPI (→ `attribute`, `applies_to = 'kpi'`) |
| `membership_id` | Whose contribution (→ `membership`; gives person, LC, function, term) |
| `team_id` | Nullable denormalised team for fast team rollups |
| `value_number` | The measured value (KPIs are numeric) |
| `period_start`, `period_end` | The window this value covers — enables arbitrary date-range filtering |
| `source` | `self` \| `leader` \| `import` \| `system` |
| `note` | Optional free text |
| `recorded_by` | → `membership` |
| `recorded_at` | timestamp |

**Grain rule:** one row per member per KPI per reporting period (or per discrete
event, if the function tracks events). Never store a pre-summed LC total — every
rollup is `SUM(value_number)` grouped by LC / function / team / date bucket at query
time.

`TODO:` For each function, get the actual list of KPIs tracked today (from the
current spreadsheets) and the natural period (weekly / monthly / per-event). This
populates the `attribute` catalog and confirms the grain.

`TODO:` Get a representative sample of current LC spreadsheets to confirm which
columns are **person** attributes, which are **membership** attributes, and which are
**KPIs**, before finalising §4.2–§4.3.

### 4.4 Future: Exchange SU linking **[Phase 2]**

Do **not** build the exchange pipeline this term. Do leave room for it:

- `person` is the anchor a future `sign_up → application → opened_exchange` chain
  will FK into (an EP is a `person`).
- Don't overload `membership` to mean "is an EP". Exchange participation will be its
  own future table referencing `person.id`.
- No exchange columns are added to any table now.

### 4.5 Privacy tables

**`deletion_request`** — tracks the request and the action taken. Stores **no** copy
of the personal data.

| Column | Purpose |
|---|---|
| `id` | PK |
| `subject_person_id` | → `person` (kept even after anonymisation; it's just an id) |
| `requested_at` | timestamp |
| `requested_by` | who lodged it (membership id, or `subject` / `external`) |
| `channel` | how it arrived (`email`, `form`, …) |
| `action_taken` | `anonymised` \| `hard_deleted` \| `rejected` \| `pending` |
| `decided_by` | → `membership` |
| `completed_at` | timestamp, nullable |
| `notes` | rationale / scope, no PII |

**`audit_log`** — §8.4.

---

## 5. Membership & productivity tracking

### 5.1 Membership lifecycle

- **Join** — create `person` + first `membership`.
- **Change position/function/team** — end-date the old `membership` (and
  `team_member`) row, insert a new one. No in-place mutation; history is the point.
- **Leave / term end** — set `end_date`; `person.status` becomes `alumnus` or
  `inactive`. Records remain for historical reporting.
- A person can hold multiple concurrent memberships (e.g. TL in one function, member
  in another). Access is the union (§3.2); reporting attributes each contribution to
  the membership it was recorded under.

### 5.2 Recording KPI data

- **Who can enter** is a permission-matrix decision per function: some functions let
  members self-report (`source = self`), others restrict entry to Team Leaders /
  VPs (`source = leader`).
- Entry UI: pick member (within your scope) → pick KPI → enter value + period.
  Bulk / grid entry for a whole team for a period is expected.
- **Import**: CSV import per function for migration and for functions that will keep
  collecting elsewhere short-term. Imported rows get `source = import` and are
  attributed to the importing membership. Validation from `attribute.validation`
  applies on import too.
- Edits to a `kpi_record` are audit-logged (§8.4).

`TODO:` Confirm per function whether self-reporting is allowed — needed for the
permission-matrix seed and the entry UI.

---

## 6. Analytics dashboards

- **Audience & scope**: a dashboard only ever shows data within the viewer's
  permission scope (§3.2). A Team Leader's "function" dashboard is filtered to their
  team unless they also hold a wider grant.
- **Date range**: an explicit **custom start/end date picker** is required, not just
  fixed presets. Presets (this term, this month, last 30 days) may exist as
  shortcuts, but arbitrary ranges must work.
- **Core views** (subject to the confirmed KPI list):
  - LC overview — headcount by function, KPI totals and trend over the selected
    range.
  - Function view — per-team and per-member breakdown, trend, contribution to LC
    total.
  - Member view — an individual's recorded contributions over time.
  - Comparison — function vs function, or team vs team, within an LC.
- **All numbers are computed by query** from `kpi_record` / `membership` at request
  time. No stored aggregates.
- **Cross-LC / national dashboards** are read-only and depend on multiple LCs having
  migrated. Treat national rollout as **[Phase 2]**; build the queries LC-scoped
  first so widening scope is a filter change, not a rewrite.

`TODO:` Get the specific charts leadership actually wants (and the current "LC
productivity dashboard" spreadsheet, if one exists) to finalise this list.

---

## 7. Reporting (NAMs, SONA, MTR)

- Each report is a **query (or set of queries) against the granular data**, rendered
  to the report's required layout. No separate data entry for reports.
- Reports are **generated on demand** in-app. Automated / scheduled generation and
  push-export are **[Phase 2]**.
- Output format: on-screen table + manual export (CSV/PDF) for submission. The exact
  submission format follows the official template.
- A report run records: who ran it, when, the parameters (LC, date range, term), and
  ideally a stored snapshot for reproducibility.

`TODO:` **Obtain the current official templates** for NAMs, SONA, and MTR — exact
field lists, definitions, date-scoping rules, and submission cadence — **before
finalising the schema in §4.** Per `CLAUDE.md`: don't guess field lists. The KPI
catalog (§4.3) must be checked against these templates so every reported field traces
to granular data.

`TODO:` Confirm which body/level each report is submitted to and whether definitions
differ by LC.

---

## 8. Privacy & deletion

### 8.1 Principle

Honour genuine deletion requests. Where a record has downstream aggregate/reporting
dependencies (KPI history, generated reports), **anonymise rather than hard-delete**
so historical totals stay correct.

### 8.2 Anonymisation

On an `anonymised` decision for a `person`:

- Overwrite `full_name`, `preferred_name`, `personal_email`, `phone` with neutral
  placeholders; null what can be nulled.
- Replace `aiesec_email` with a non-routable tombstone (e.g.
  `anon+<person_id>@invalid`) so the row can't re-link to an identity but stays
  unique.
- Set `status = 'anonymised'`, `anonymised_at = now()`.
- Clear or generalise `attribute_value` rows where `applies_to = 'person'` and the
  attribute is personal (keep non-identifying ones if needed for stats — decide per
  attribute via a flag).
- **Keep** `membership`, `team_member`, `kpi_record` rows and their `person_id` /
  `membership_id` links. Aggregates and past reports are unaffected; the contributor
  is now anonymous.
- Revoke access immediately (no active identity to authenticate).

### 8.3 Hard delete

Only when there is genuinely no downstream dependency (e.g. a person with no KPI
records and not named in any generated report), or when legally required beyond
anonymisation. If required despite dependencies, the cascade must be mapped and
approved by the Tech Lead first.

**Cascade map (to keep current):**

| Deleting a `person` touches | Effect |
|---|---|
| `membership`, `team_member` | Removed → headcount history changes |
| `kpi_record` (via membership) | Removed → historical KPI totals drop |
| Generated reports referencing them | Already-submitted numbers no longer reproduce |
| `deletion_request` | Retained (no PII in it) |
| `audit_log` | Retained; actor references become dangling ids by design |

This is why anonymisation is the default.

### 8.4 Audit trail

**`audit_log`** — append-only:

| Column | Purpose |
|---|---|
| `id` | PK |
| `actor_membership_id` | Who acted (nullable for `system`) |
| `action` | e.g. `kpi_record.edit`, `permission_matrix.update`, `deletion_request.complete` |
| `resource_type`, `resource_id` | What was affected |
| `summary` | Human-readable one-liner |
| `diff` | JSON before/after for config-type changes — **no personal data** |
| `created_at` | timestamp |

Logged at minimum: permission-matrix changes, membership create/close, KPI record
create/edit/delete, all deletion-request state changes, report generation.

`TODO:` A one-off Australian Privacy Act / APP compliance consult (budgeted in
`CLAUDE.md`) should review §8 — retention periods, what "anonymised" must legally
mean, and the deletion-request SLA — before launch.

---

## 9. Authentication

- **OAuth only**, via AIESEC Google Workspace accounts (`@aiesec.net` and any other
  official AIESEC Australia domains). No password auth, no self-service signup, no
  custom auth code.
- Use the platform's managed auth (Supabase Auth or equivalent per `CLAUDE.md`).
- On login: match the verified email to `person.aiesec_email`.
  - **No match** → authenticated but no `person` → no access; show a "ask your VP to
    be added" message. Optionally queue for an admin to link/create.
  - **Match** → load active memberships → resolve permissions (§3.2).
- Sessions handled by the managed auth provider. No long-lived tokens of our own.

`TODO:` Confirm the exact set of official email domains, and whether any legitimate
users (e.g. new members mid-onboarding) won't yet have an `@aiesec.net` address.

---

## 10. Non-functional requirements

Defaults are set in `CLAUDE.md` → "Tech & infra defaults"; the ones that constrain
this product:

- **Turnover-first**: every schema choice, the permission matrix, and the deletion
  logic must be documented in-repo for a zero-context reader. Config in lookup
  tables, not code.
- **Runtime-manageable** (§1.5): every feature's data is admin-editable through the
  UI — add/edit/move/deactivate LCs, people, memberships, teams, positions,
  functions, metrics, terms — with no code change, migration, or deployment.
  A feature only a developer can reconfigure is a design flag.
- **Budget**: combined infra for both projects ≤ ~$500 AUD/yr; target $100–350 using
  managed free/low tiers.
- **Database**: managed Postgres that does not auto-expire data (Supabase or Neon).
- **Hosting**: managed platform (Vercel/Netlify + Supabase). No self-hosted servers.
- **File/image storage**: object storage, never bytes in DB rows. (Applies if member
  photos / document uploads are added.)
- **Access to infra**: ≥2 GitHub org owners, ≥2 people with each critical account;
  access via GitHub Teams by role. No capability held by exactly one person.
- **Security**: OWASP Top 10 as a review checklist; Dependabot + Snyk free tier; one
  pre-launch external security/privacy audit; a one-page incident-response plan.
- **Auditability**: §8.4 covers privacy and config actions.
- **Performance**: dashboards and reports run against one LC's data interactively
  (target < ~2s for a term-range query). Index `kpi_record` on
  `(attribute_id, membership_id, period_start)` and `membership` on
  `(lc_id, function_id, start_date, end_date)`. Revisit only if a real LC's volume
  proves it necessary.
- **Data scale (rough)**: an LC is ~10²–10³ members over its history; KPI records
  ~10⁴–10⁵ per term. Small. Favour clarity over premature optimisation.

---

## 11. Phase 2 / future vision

Specified here so the MVP doesn't foreclose them. **Do not build this term.**

### 11.1 Exchange SU → opened-exchange pipeline

A future subsystem tracking a sign-up through application, acceptance, and opened
exchange, per EP. It will FK into `person` (§4.4). Likely needs its own tables for
opportunity, application, and exchange milestones, plus its own KPIs feeding the same
`kpi_record` mechanism. Reporting (SONA especially) would then pull real exchange
numbers instead of hand-entered ones.

### 11.2 Website integration

If the website replacement (see `CLAUDE.md`) grows dynamic features (EP applications,
event registration, partner forms), those should **write into this platform** rather
than form a separate silo — e.g. a public application form creates a `person` +
exchange application row. Shared auth between the two is **[Phase 2]** and only if the
website project independently needs authenticated users.

### 11.3 National / cross-LC rollout

Once multiple LCs have migrated: cross-LC dashboards and MC-level reporting become
first-class. Because §3 scope already includes `all` and all queries are
scope-filtered, this is mostly a data + permissions rollout, not a rebuild. MC write
access and national KPI targets would be designed then.

### 11.4 Automated reporting

Scheduled generation and push-delivery of NAMs / SONA / MTR on the official cadence,
building on the on-demand generation from §7.

### 11.5 Other

Member self-service profile management beyond the basics, notifications/reminders for
data entry, and document uploads (member agreements, etc.) — each to be scoped
separately if wanted.

---

## 12. Open questions / consolidated TODOs

Everything the team must resolve. Grouped by what it blocks.

**Blocks the schema (§4) — highest priority:**

1. Authoritative list of **positions** and **functions**. (§2, §3)
2. Current official **NAMs / SONA / MTR templates** — exact fields, definitions,
   date rules, cadence, submitting body. (§7)
3. Representative **current LC spreadsheets** — to classify columns into person /
   membership / KPI attributes. (§4.2–§4.3)
4. Per-function **KPI list** and natural reporting **period**. (§4.3)

**Blocks the permission-matrix seed (§3.3):**

5. Reviewed position × function × resource × action × scope table, agreed with a
   Tech Lead + LCP. (§3.3)
6. Per-function: is member **self-reporting** of KPIs allowed? (§5.2)

**Blocks auth (§9):**

7. Exact set of official **email domains**; handling of users without an
   `@aiesec.net` address yet.

**Blocks privacy sign-off (§8):**

8. Australian **Privacy Act / APP** consult — retention periods, legal meaning of
   "anonymised", deletion-request SLA.

**Blocks dashboards (§6):**

9. The specific **charts / comparisons** leadership wants; the current productivity
   dashboard spreadsheet if one exists.

**Process / ownership:**

10. Which **position(s)** hold `manage` on the permission matrix and the ability to
    process deletion requests (must be ≥2 people). (§2, §3.3)
11. Confirm all code and infra accounts are owned by **AIESEC Australia as an
    entity**, in writing. (`CLAUDE.md`)
