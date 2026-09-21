# Data model

Explains the tables introduced in the initial schema migration
(`backend/migrations/versions/0b11f06365cd_initial_schema.py`), for a reader
with no prior context. See `docs/membership-tool-requirements-spec.md` §4.1
for the source requirements — this doc explains the *implementation*, the
spec explains the *why* at a product level.

Every table lives in a SQLAlchemy model under `backend/app/models/`:

| File | Tables |
|---|---|
| `org.py` | `lc`, `term`, `position`, `function` |
| `person.py` | `person` |
| `membership.py` | `membership`, `team`, `team_member` |
| `attribute.py` | `attribute`, `attribute_value` |
| `kpi.py` | `kpi_record` |

This grouping isn't enforced by anything — it's a convention matching the
spec's own section breakdown (org-structural lookups vs. the person record
vs. the membership lifecycle). If you add a table, put it in whichever file
groups it with tables it's most related to, and update this doc.

## The tables

### `lc`

One row per AIESEC entity — a Local Committee, or the MC itself (`type =
'MC'`). Both share a table because most of the schema (memberships, teams,
KPIs) applies identically to either; `type` is just a filter. Stored values
are uppercase (`'LC'` / `'MC'`), enforced by a `CHECK` constraint generated
from `LCType` in `app/models/org.py`.

- `name` is unique — two entities can't share a display name.
- `active` is a soft-disable flag. An LC is never hard-deleted once it has
  any history (memberships, teams, KPI records) pointing at it — see spec
  §1.5.

### `term`

A cycle (e.g. a semester or year) used to time-scope memberships and, later,
KPI data. Just a name and a date range — nothing else references a business
meaning into this table.

### `position` / `function`

Lookup tables for "what role" (LCP, LCVP, Team Leader, Member) and "which
function" (BD, MKT, oGV, …) a membership represents. Deliberately plain
lookup tables, not a hardcoded enum in code, so a non-technical admin can add,
rename, or deactivate one at runtime (spec §1.5) without a developer touching
code or writing a migration.

- `key` is the stable, machine-readable identifier code refers to (e.g. when
  checking the permission matrix in a later ticket). It's unique and never
  changes.
- `label` is what's shown in the UI. It can be renamed freely — nothing else
  in the schema references it.
- `position.rank` is a plain integer used only for UI ordering (lower number
  = more senior, by convention — not enforced by the schema). It has no
  effect on access control.
- `active` soft-disables a lookup value without breaking historical rows
  that already reference it (spec §1.5: "renaming or deactivating a lookup
  value must never break historical records that point at it").

Seeded from `backend/app/seeds/seed_lookups.py` with a **working baseline**,
not the authoritative list — see "Seed data" below.

### `person`

One row per human. **This is the only table allowed to hold PII** (spec
§4.1) — full name, email addresses, phone number. Every other table refers
to a person only indirectly, through `membership`.

- `aiesec_email` is unique and is the join key used when someone logs in via
  OAuth (spec §9): the verified email from the identity provider is matched
  against this column to resolve who's signed in.
- `status` (`ACTIVE` / `ALUMNUS` / `INACTIVE` / `ANONYMISED`) is a fixed
  lifecycle state, not an admin-editable lookup like `position`/`function` —
  it's structural to how the app behaves (e.g. an `ANONYMISED` person can no
  longer authenticate), so it's a constrained column (enforced by a `CHECK`
  constraint, not just at the Python/ORM level) rather than a lookup table.
- `anonymised_at` is set when a deletion request results in anonymisation
  (spec §8.2). The actual deletion-request workflow is a separate ticket;
  this column exists now because it's part of the `person` table's shape per
  spec §4.1.

### `membership`

The record of a person's assignment to an LC, in a position (and usually a
function), for a term. This is the table every other feature — access
control, KPI attribution, reporting — ultimately joins through.

**A `membership` row is never edited to reflect a change.** If someone
changes position, changes function, moves LC, or leaves:

1. The old `membership` row gets an `end_date`.
2. A new `membership` row is inserted for the new assignment.

History is the point — spec §5.1 is explicit that this is "no in-place
mutation." This is also why there's no `is_current` boolean column: a stored
flag could drift out of sync with reality if someone forgot to flip it.
Instead, "is this membership current" is answered by a query:

```sql
start_date <= :as_of AND (end_date IS NULL OR end_date >= :as_of)
```

implemented in
`backend/app/repositories/membership.py::get_active_memberships_for_person`.
A person can have **more than one** concurrent `membership` row (e.g. Team
Leader in one function, ordinary Member in another) — the repository
function returns all of them.

- `function_id` is nullable because some positions (e.g. LCP) aren't tied to
  one function.
- `is_primary` flags which concurrent membership is a person's "main" one,
  for anywhere the UI needs to pick just one (e.g. a default landing
  dashboard). Not used for access control — per spec §3.2, access is the
  union across *all* active memberships.

### `team`

A team within one function within one LC, for one term. `leader_membership_id`
points at the `membership` row of whoever leads it (nullable — a team can
exist before a leader is assigned).

### `team_member`

Join table between `membership` and `team`. Time-scoped the same way as
`membership` (`start_date`/`end_date`, no in-place mutation) so team history
is preserved the same way membership history is.

## EAV: `attribute` + `attribute_value`

Everything else in this schema so far is an ordinary relational table: fixed columns,
real foreign keys, one migration per shape change. `attribute` / `attribute_value`
deliberately break that pattern — this is the **only** EAV (entity–attribute–value)
part of the schema, and it's worth being explicit about why.

**Why EAV, and why only here.** Custom person/membership fields (e.g. shirt size,
dietary requirements) and KPI definitions are the one part of this domain that
genuinely changes term-to-term, in ways nobody can predict in advance (spec §4). A
new function might introduce a new metric mid-term; a new committee might want a new
custom field. Spec §1.5 requires that adding one of these be a runtime admin action —
insert a row — never a migration. A fixed-column table can't do that: adding a field
would mean `ALTER TABLE` plus a code change, exactly what the turnover constraint says
to avoid. EAV trades that flexibility for weaker guarantees (see "What's given up"
below), which is why it's reserved for genuinely volatile data. Every other table
(`lc`, `person`, `membership`, `team`, …) is structural — it doesn't change shape
term-to-term — so it stays a plain table with real columns and constraints, which are
easier to read, query, and reason about for a new developer.

**`attribute`** — the catalog. One row per custom field *or* per KPI definition
(`applies_to = 'kpi'`); adding either is an insert here, not a migration. `data_type`
says which single typed column on `attribute_value` (or, for a KPI attribute,
`kpi_record.value_number` — see below) a value gets written to. `validation` is a
small JSON contract applied on write by `app/repositories/attribute.py`, not a DB
constraint — the shape of "valid" depends on `data_type`, which varies per row, so no
single CHECK constraint on the values table could express it:

| Key | Applies to | Meaning |
|---|---|---|
| `required` | any | value must not be `None` |
| `min` / `max` | `number`, `date` | inclusive bound (a `date` bound is an ISO string, e.g. `"2026-01-01"`, since JSON has no date type) |
| `regex` | `text` | value must fully match |

`enum`-typed attributes are validated against `attribute.enum_options` instead (not
`validation`) and stored as their option string in `value_text`.

`function_id` scopes an attribute to one function (null = every function).
`term_introduced_id` is provenance only (which `term` this was first tracked in) — it
is an FK to `term` rather than a free-text field, to stay consistent with every other
term-scoping column in the schema, and it never gates reads or writes.

**`attribute_value`** — one row per `(attribute, entity)` for `applies_to IN
('person', 'membership')`. `entity_id` is a **polymorphic reference**: it means a
`person.id` or a `membership.id` depending on `entity_type`, and a single column
cannot be a real foreign key to two different tables. This is the concrete cost of
using EAV here — the database cannot enforce that `entity_id` actually points at an
existing row, unlike every FK elsewhere in this schema. `app/repositories/attribute.py`
is the only place that should write an `attribute_value` row precisely because of
this: it's where that missing guarantee is compensated for (the application always
has a real `Person`/`Membership` object in hand before calling it, never a bare id
typed in from elsewhere).

The unique constraint on `(entity_type, entity_id, attribute_id)` enforces that every
attribute here is single-valued — setting a value for an entity that already has one
overwrites it (`set_attribute_value`'s upsert), it never inserts a second row. That
column order also makes the same index serve "every attribute value for this person"
lookups, not just the uniqueness check.

**What's given up, concretely, versus a normal table:** no DB-level referential
integrity on `entity_id`; no per-attribute DB type constraint (a bug in
`app/repositories/attribute.py` could in principle write a mismatched column, whereas
a real column's type is enforced by Postgres itself); reporting queries over custom
fields need an extra join through `attribute` to know which typed column to read,
rather than referencing a plain column by name. This is the deliberate trade for not
needing a migration every time a new field or metric appears — acceptable because
`attribute_value` rows are individually small and low-volume compared to `membership`
or `kpi_record`, and because the single write path keeps the missing guarantees to a
short, testable list rather than scattering `INSERT`s across the codebase.

## `kpi_record`

KPIs are catalogued in `attribute` like any other volatile field (`applies_to =
'kpi'`), but their **values** live in their own table, not `attribute_value`. A KPI is
recorded once per member *per reporting period* — many rows over time for the same
`(attribute, member)` pair — which doesn't fit `attribute_value`'s one-row-per-entity,
uniqueness-enforced shape at all. `kpi_record` is an ordinary time-series table, not
EAV, aside from `attribute_id` naming which metric.

**Grain rule: one row per member per KPI per reporting period** (or per discrete
event, for functions that track events rather than periods). This is a convention
enforced by `app/repositories/kpi.py::record_kpi` being the only write path, not a DB
constraint — a hard uniqueness constraint on `(attribute_id, membership_id,
period_start, period_end)` would incorrectly block a function logging more than one
event-based record in the same window. **Never store a pre-summed total**: every
LC/function/team/date-range rollup is a `SUM(value_number)` computed at query time
(`app/repositories/kpi.py::sum_by_function`), never a maintained aggregate.

- `attribute_id` must reference an `attribute` row with `applies_to = 'kpi'`. A plain
  FK can't express that condition (it can only say "some row in `attribute` exists"),
  so `record_kpi` checks it explicitly on every write instead.
- `membership_id` is the only person/org link this table needs — it gives the
  contributor's person, LC, function, and term transitively through `membership`, so
  none of those are duplicated here.
- `team_id` is a **deliberate denormalisation** for fast team rollups (spec §4.3): the
  team the member belonged to *as of `period_start`*, resolved once by `record_kpi`
  and never rewritten afterwards. A later team move does not update past
  `kpi_record` rows — this matches the append-only history convention `membership` /
  `team_member` already use, and means a team's historical KPI rollup reflects who was
  actually on it at the time, not who's on it now.
- Rollup queries (`sum_by_function`) use **overlap** semantics against the requested
  date range (`period_start <= :range_end AND period_end >= :range_start`), not
  "fully contained in the range" — a dashboard's arbitrary custom range (spec §6)
  won't usually line up exactly with recorded periods, and excluding a record just
  because it straddles the range boundary would silently under-report.

**Indexes (spec §10):** `kpi_record(attribute_id, membership_id, period_start)` for a
date-range rollup of one KPI scoped to a member, and `membership(lc_id, function_id,
start_date, end_date)` for resolving a scope's active memberships — both added in the
`kpi_record` migration, since `kpi_record` is what starts actually querying
`membership` that way.

## Foreign keys and what deleting protects against

None of the foreign keys in this migration cascade on delete. Concretely,
you cannot delete an `lc`, `position`, `function`, `term`, or `person` row
while any `membership` still points at it — the database will reject it.
This is deliberate: it's the enforcement mechanism behind spec §1.5's rule
that lookup values and entities are *deactivated*, never deleted, once they
have history. If a table genuinely needs to disappear (e.g. an LC created by
mistake, with zero memberships), delete it directly; the FK constraint only
blocks the case where doing so would silently corrupt historical records.
The same applies to `attribute` and `kpi_record`: you cannot delete an
`attribute` row while any `attribute_value` or `kpi_record` still references
it — deactivate it instead (`attribute.active = false`). `attribute_value`
is the one exception to "every FK here is enforced": `entity_id` cannot be a
real FK at all (see "EAV" above), so that particular link relies on
`app/repositories/attribute.py` being the only write path rather than on the
database.

## Seed data

`backend/app/seeds/seed_lookups.py` seeds `position` and `function` with the
**working set** listed in spec §2 — it is explicitly **not** the
authoritative list. Spec §2 and §12 (item 1) mark the real list as a
`TODO:`, pending confirmation against AIESEC Australia's current national
structure docs. Positions/functions are runtime-editable (spec §1.5), so
once the authoritative list is confirmed, correcting the seeded rows is an
admin task done through the app — not a new migration or a code change.

The seed script is idempotent (checks existing `key`s before inserting), so
running `make seed` more than once is safe.

`backend/app/seeds/seed_attributes.py` seeds a small **placeholder**
`attribute` catalog the same way — a handful of non-KPI custom fields and a
handful of KPIs, explicitly **not** the real classification. Spec §12 items 3
and 4 mark "classify current LC spreadsheet columns into person / membership
/ KPI attributes" and "per-function KPI list + natural period" as open
`TODO:`s; nobody has supplied that source data into this repo yet. This seed
exists so the `attribute` / `attribute_value` / `kpi_record` mechanism could
be built and tested now rather than blocking on that TODO. Like
`position`/`function`, both tables are runtime-editable (spec §1.5), so
replacing the placeholder rows with the real catalog — once it's confirmed —
is an admin task through the app, not a new migration.

## Repository layer

`backend/app/repositories/membership.py` holds query functions over
`membership`, starting with `get_active_memberships_for_person`.
`backend/app/repositories/attribute.py` is the write/read path for
`attribute_value` (`set_attribute_value`, `get_attribute_value`,
`validate_and_coerce`) — see "EAV" above for why writes must go through here
rather than constructing rows directly. `backend/app/repositories/kpi.py`
is the write path and rollup query for `kpi_record` (`record_kpi`,
`sum_by_function`). As more tickets add read patterns (e.g. "all memberships
for an LC", "who leads this team"), add functions to the relevant file
rather than writing ad-hoc queries in API route handlers — keeps query logic
in one place and testable independent of FastAPI.

Tests (`backend/tests/test_membership_repository.py`,
`test_attribute_repository.py`, `test_kpi_repository.py`) run against the
real migrated schema via `app.db.session.engine`, each wrapped in a
transaction that's rolled back afterwards
(`backend/tests/conftest.py::db_session`) so tests don't leave data behind or
depend on each other.
