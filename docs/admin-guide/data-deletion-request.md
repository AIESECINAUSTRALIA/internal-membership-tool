# 6. Processing a Deletion Request

> **Applies until** the in-app deletion-request workflow is built (Phase 2, spec §8).
> Until then, genuine requests are handled manually using this procedure.

This guide walks an authorised person through receiving, verifying, and
carrying out a data-deletion request against the membership tool's database.
It is written for someone with database access (e.g. via `psql`, Supabase SQL
Editor, or a similar tool) but does not assume deep SQL expertise — every
command you need to run is provided as a ready-to-use template.

---

## Key rules (from spec §8 and CLAUDE.md)

| Rule | Why |
|---|---|
| **Anonymise by default, hard-delete only when appropriate** | Anonymisation preserves historical KPI totals and report accuracy. Hard delete changes them. |
| **Two authorised people** — never one acting alone | No single point of failure (CLAUDE.md). One person processes; the other reviews before the final commit. |
| **Log the action taken, never the deleted data** | The audit log is append-only and can never be edited. If a name or email ends up in it, the leak is permanent. |
| **Revoke access immediately** | An anonymised or deleted person must not be able to sign in. |

---

## Before you start

### Who is authorised

At least **two people** must hold the ability to process deletion requests at
all times (spec §12 #10, CLAUDE.md). This is a position-based permission, not
tied to a named individual. The current authorised positions are recorded in
the permission matrix — check with the Tech Lead if you are unsure whether
your position qualifies.

### What you need

- **Database access** — either `psql` connected to the production database, or
  the Supabase SQL Editor. You need `SELECT`, `INSERT`, and `UPDATE` privileges
  on the tables below (the application's database role has these).
- **A second authorised person** available to review your work before you
  commit.

---

## Step 1 — Receive and verify the request

A deletion request may arrive by any channel (email, Slack, in person). Before
acting on it you must verify that the request is **genuine** — that is, it was
actually made by the person whose data would be affected, or by someone with
legal authority to make it on their behalf.

1. **Confirm the requester's identity.** The request must come from the
   person's `@aiesec.net` email address or Google Workspace account (the same
   identity used to sign in to the tool). If it comes from another channel,
   reply to their AIESEC email to confirm.
2. **Record the request.** Create a brief written record (e.g. a note in a
   shared doc or a message in the team's admin channel) with:
   - The date the request was received.
   - How the requester's identity was verified.
   - The person's `id` in the database (**not** their name or email — the
     record itself must not contain personal data).

   To look up the person's id:

   ```sql
   SELECT id, full_name, aiesec_email, status
     FROM person
    WHERE aiesec_email = 'their.name@aiesec.net';
   ```

   Note the `id` value. From this point forward, refer to the person **only by
   id** in all written records, audit entries, and communications about this
   request.

---

## Step 2 — Decide: anonymise or hard-delete

### Choose anonymisation (the default) when:

- The person has **any** memberships, KPI records, or team assignments — which
  is the case for almost everyone who has ever used the tool.
- You are unsure.

### Choose hard delete only when **all** of the following are true:

- The person has **no** memberships, **no** KPI records, and is **not**
  referenced in any generated report.
- **Or** a legal obligation requires deletion beyond anonymisation (e.g. a
  formal request under the Australian Privacy Act that anonymisation does not
  satisfy). In this case the cascade must be reviewed and approved by the Tech
  Lead first.

To check for dependencies:

```sql
-- Replace 42 with the person's actual id throughout this guide.

-- Memberships
SELECT count(*) AS membership_count
  FROM membership
 WHERE person_id = 42;

-- KPI records (linked via membership)
SELECT count(*) AS kpi_count
  FROM kpi_record kr
  JOIN membership m ON m.id = kr.membership_id
 WHERE m.person_id = 42;

-- Team assignments (linked via membership)
SELECT count(*) AS team_member_count
  FROM team_member tm
  JOIN membership m ON m.id = tm.membership_id
 WHERE m.person_id = 42;

-- Person-level attribute values
SELECT count(*) AS attribute_count
  FROM attribute_value
 WHERE entity_type = 'person'
   AND entity_id = 42;
```

If **all** counts are zero, hard delete is safe. Otherwise, anonymise.

---

## Step 3A — Anonymise (default path)

Run the following statements **inside a single transaction**. Do not commit
until Step 4 (peer review).

```sql
BEGIN;

-- 3A-1. Anonymise the person record.
UPDATE person
   SET full_name      = 'Anonymised Person',
       preferred_name = NULL,
       aiesec_email   = 'anon+' || id::text || '@invalid',
       personal_email = NULL,
       phone          = NULL,
       status         = 'ANONYMISED',
       anonymised_at  = now()
 WHERE id = 42;

-- 3A-2. Clear person-level attribute values that may contain personal data.
--        (Non-personal attributes used for aggregate stats can be kept —
--         if in doubt, clear them; totals are safer than a data leak.)
UPDATE attribute_value
   SET value = NULL
 WHERE entity_type = 'person'
   AND entity_id   = 42;

-- 3A-3. Record an audit entry.
--        IMPORTANT: the summary must NOT contain the person's name or email.
INSERT INTO audit_log (action, resource_type, resource_id, summary)
VALUES (
  'person.anonymise',
  'person',
  42,
  'Person 42 anonymised per manual deletion request'
);

-- Do NOT commit yet — go to Step 4.
```

> **What this preserves:** all `membership`, `team_member`, and `kpi_record`
> rows remain intact. The person's contribution to historical KPI totals and
> reports is unchanged — but the contributor is now anonymous.

> **What this removes:** the person's name, email addresses, phone number, and
> preferred name. The `aiesec_email` is replaced with a non-routable tombstone
> (`anon+42@invalid`) so the unique constraint is maintained and no one can
> re-link the row to a real identity.

---

## Step 3B — Hard delete (only if Step 2 confirmed zero dependencies)

Run the following statements **inside a single transaction**. Do not commit
until Step 4 (peer review).

```sql
BEGIN;

-- 3B-1. Record the audit entry FIRST — before the person row is gone.
--        IMPORTANT: the summary must NOT contain the person's name or email.
INSERT INTO audit_log (action, resource_type, resource_id, summary)
VALUES (
  'person.delete',
  'person',
  42,
  'Person 42 hard-deleted per manual deletion request (no downstream dependencies)'
);

-- 3B-2. Remove person-level attribute values.
DELETE FROM attribute_value
 WHERE entity_type = 'person'
   AND entity_id   = 42;

-- 3B-3. Delete the person row.
--        (This will fail if any membership still references the person —
--         the database has no cascading deletes, which is deliberate.)
DELETE FROM person WHERE id = 42;

-- Do NOT commit yet — go to Step 4.
```

### If hard delete is legally required despite dependencies

This is rare. The cascade must be mapped and approved by the Tech Lead first
(spec §8.3). The order of deletion matters because of foreign keys:

```
team_member  →  (depends on membership)
kpi_record   →  (depends on membership)
membership   →  (depends on person)
person
```

You must delete in leaf-to-root order:

```sql
BEGIN;

-- Audit entry first.
INSERT INTO audit_log (action, resource_type, resource_id, summary)
VALUES (
  'person.delete',
  'person',
  42,
  'Person 42 hard-deleted with cascade per Tech Lead approval (legal requirement)'
);

-- Clear team leader references that point at this person's memberships.
UPDATE team
   SET leader_membership_id = NULL
 WHERE leader_membership_id IN (
       SELECT id FROM membership WHERE person_id = 42
       );

-- Delete in leaf-to-root order.
DELETE FROM attribute_value
 WHERE entity_type = 'person' AND entity_id = 42;

DELETE FROM attribute_value
 WHERE entity_type = 'membership'
   AND entity_id IN (SELECT id FROM membership WHERE person_id = 42);

DELETE FROM kpi_record
 WHERE membership_id IN (SELECT id FROM membership WHERE person_id = 42);

DELETE FROM team_member
 WHERE membership_id IN (SELECT id FROM membership WHERE person_id = 42);

DELETE FROM membership WHERE person_id = 42;

DELETE FROM person WHERE id = 42;

-- Do NOT commit yet — go to Step 4.
```

> [!CAUTION]
> A cascading hard delete **permanently changes historical KPI totals and
> headcount numbers**. Reports generated before this point will no longer
> reproduce from the database. This is why it requires Tech Lead approval.

---

## Step 4 — Peer review (mandatory)

Before committing the transaction, a **second authorised person** must review
what you are about to do. Show them:

1. The request record from Step 1 (with person id, not name/email).
2. The dependency check results from Step 2.
3. The SQL statements you ran (still uncommitted).

You can verify the uncommitted changes inside the same session:

```sql
-- Should show the anonymised/deleted state:
SELECT id, full_name, aiesec_email, status, anonymised_at
  FROM person
 WHERE id = 42;

-- Should show the new audit entry:
SELECT id, action, resource_type, resource_id, summary, created_at
  FROM audit_log
 WHERE resource_type = 'person'
   AND resource_id = 42
 ORDER BY created_at DESC
 LIMIT 5;
```

Once the second person confirms:

```sql
COMMIT;
```

If anything looks wrong:

```sql
ROLLBACK;
```

Then investigate before starting again.

---

## Step 5 — Verify and close

After committing:

1. **Verify access is revoked.** The person can no longer sign in because
   their `aiesec_email` is either deleted or replaced with a non-routable
   tombstone (`anon+<id>@invalid`). No further action is needed for access
   revocation — the authentication system matches on `aiesec_email`.

2. **Update your request record** (the note from Step 1) to show:
   - The action taken: "anonymised" or "hard-deleted".
   - The person id (not their name or email).
   - The date the action was completed.
   - Who processed it and who reviewed it (by position, not personal name —
     e.g. "processed by MCVP IT, reviewed by MCP").

3. **Notify the requester** that their request has been fulfilled. Do not
   describe the technical steps taken — a simple confirmation is enough.

---

## What about the audit log?

The `audit_log` table is **append-only**. Database triggers block all updates,
deletes, and truncations — even with elevated privileges. This is by design
(spec §8.4).

- Existing audit entries that reference the person by `actor_person_id` or
  `actor_membership_id` are **retained**. These become dangling references
  (the person row they point to is gone or anonymised), which is expected.
- The audit log never contains names or emails (the application enforces this),
  so retaining it does not leak personal data.
- **Do not attempt to modify or delete audit log entries.** The database will
  reject it.

---

## Quick-reference checklist

- [ ] Requester's identity verified (from their AIESEC email / Workspace account).
- [ ] Person id noted; no name or email written in any working record.
- [ ] Dependencies checked (memberships, KPIs, team assignments, attributes).
- [ ] Path chosen: anonymise (default) or hard delete (zero dependencies / legal).
- [ ] SQL run inside a transaction, **not yet committed**.
- [ ] Second authorised person reviewed and approved.
- [ ] Transaction committed.
- [ ] Person can no longer sign in (verified).
- [ ] Request record updated with action taken, date, and who was involved.
- [ ] Requester notified.
