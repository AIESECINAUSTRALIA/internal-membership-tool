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

## Foreign keys and what deleting protects against

None of the foreign keys in this migration cascade on delete. Concretely,
you cannot delete an `lc`, `position`, `function`, `term`, or `person` row
while any `membership` still points at it — the database will reject it.
This is deliberate: it's the enforcement mechanism behind spec §1.5's rule
that lookup values and entities are *deactivated*, never deleted, once they
have history. If a table genuinely needs to disappear (e.g. an LC created by
mistake, with zero memberships), delete it directly; the FK constraint only
blocks the case where doing so would silently corrupt historical records.

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

## Repository layer

`backend/app/repositories/membership.py` holds query functions over
`membership`, starting with `get_active_memberships_for_person`. As more
tickets add read patterns (e.g. "all memberships for an LC", "who leads this
team"), add functions here rather than writing ad-hoc queries in API route
handlers — keeps query logic in one place and testable independent of
FastAPI.

Tests (`backend/tests/test_membership_repository.py`) run against the real
migrated schema via `app.db.session.engine`, each wrapped in a transaction
that's rolled back afterwards (`backend/tests/conftest.py::db_session`) so
tests don't leave data behind or depend on each other.
