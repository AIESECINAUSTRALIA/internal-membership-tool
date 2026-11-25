# 6. Processing a deletion request

**What this is for:** someone has asked us to delete the personal data the Membership Tool
holds about them. This guide takes you from "the request arrived" to "the requester has
been told it's done", and leaves a record of what was done that contains no personal data.

**Who can do this:** members of the **`mt-tech-leads@aiesecaustralia.org`** Google group
(the Tech Lead and at least one senior developer). Membership of that group is what gives
access to the production database. It always has at least two people, so a request never
depends on one person being available. Every request needs **two** of them: one to carry
it out (the **operator**) and one to check it (the **reviewer**).

**Where:** the production database, reached through the Cloud SQL Auth Proxy. There is no
screen for this yet.

> **Applies until** the in-app deletion-request workflow is built. That's a Phase 2
> feature (spec §8). Until then, every genuine request is handled by hand with this guide.
>
> **Why this guide contains SQL:** the admin guide normally has no code (see
> [README](README.md)). This is one of the exceptions, like guides 8 and 9, because no
> screen can do it yet. Every command is given in full. You only change the values in
> `CAPITALS`, and you copy everything else exactly.

---

## The rules, and why they exist

| Rule | Why |
|---|---|
| **Anonymise by default. Hard delete only in the narrow cases in Step 3.** | Anonymising removes who the person is but keeps the numbers they contributed, so past KPI totals and submitted reports stay correct. Deleting changes those numbers forever. |
| **Two people for every request.** The reviewer checks before anything is saved. | One mistyped number would wipe the wrong person, and nothing in this guide can be undone. |
| **Record the action, never the data.** | The audit log can never be edited or deleted, not even by us. Anything personal written into it stays there forever. Records about the request use the person's **id number** and a **request reference**, never their name or email. |
| **Ask for as little as possible to verify someone.** | Collecting ID documents to delete data would mean holding *more* personal data. |
| **Answer within 30 days.** | See "Timelines" below. |

---

## Before you start

### Timelines

- **Acknowledge** the request within **5 business days**.
- **Finish** the request, and tell the requester, within **30 calendar days** of receiving
  it. This follows the usual practice under the Australian Privacy Principles (APP 12/13)
  and matches the one-month limit in the EU's GDPR.

> `TODO (Tech Lead):` these timings are provisional until the one-off Australian privacy
> (APP) consult (spec §8, §12 #8) confirms them. Update this section afterwards.

### The deletion-request register

Every request gets one row in the **deletion-request register**:

- a spreadsheet in a shared drive owned by `mt-tech-leads@`, never in a personal drive
- shared with that group only
- not kept in Slack or a chat channel

> `TODO (Tech Lead):` create the register and put its link here.

Each row has these columns, and **nothing that identifies the requester**:

| Column | Example |
|---|---|
| Request reference | `DR-2026-001` (year, then a running number) |
| Date received | 2026-11-25 |
| How it arrived | email to hello@ |
| How identity was verified | reply confirmed from AIESEC email on record |
| Person id | `1234` (from Step 2) |
| Decision | anonymised / hard-deleted / not found / declined (and why) |
| Operator, reviewer | by position, e.g. "Tech Lead; senior dev" |
| Date completed | 2026-11-27 |
| Date requester told | 2026-11-27 |

The emails exchanged with the requester stay in the mailbox they arrived in. They aren't
copied into the register.

### What you need

1. You're a member of `mt-tech-leads@` and can connect to the **production** database. Do
   that through the Cloud SQL Auth Proxy, following `docs/database-changes.md`. In short:

   1. Sign in to Google Cloud with your `aiesecaustralia.org` account: `gcloud auth login`.
   2. Start the proxy for the production instance (instance name in `infra/env.sh`):
      `cloud-sql-proxy INSTANCE_CONNECTION_NAME --port 5434`
   3. In a second terminal, open `psql` on `membership_prod`.

   > `TODO (DEV-81):` `docs/database-changes.md` is written as part of the deployment
   > work and is the source of truth for connecting. If these short steps ever disagree
   > with it, follow that page and fix this one.

2. **The reviewer** is available for about 20 minutes, on a call where they can see your
   screen.
3. **First time?** Rehearse the whole procedure on your own computer first, against the
   local database filled with made-up people: `make bootstrap`, then `make psql`. It
   behaves the same and nothing real is at risk.

---

## Step 1: Receive and verify the request

A request can arrive any way (email, Slack, in person). It doesn't need to use any
particular words. "Please delete my data" or "remove me from your system" counts.

1. **Give it a reference** (`DR-YEAR-NUMBER`) and add a row to the register with the date
   and how it arrived.
2. **Acknowledge it** within 5 business days, from a shared address (e.g.
   `hello@aiesecaustralia.org`), not your personal one:

   > Hi, we've received your request to delete your data from the AIESEC Australia
   > Membership Tool (reference DR-2026-001). We'll confirm it's you, then complete it
   > within 30 days. We'll let you know when it's done.

3. **Verify it's really them.** Pick the first option that works:

   | Situation | How to verify |
   |---|---|
   | The request came **from** their AIESEC email address | Reply to that address and ask them to confirm. Their confirmation reply is the verification. |
   | It came from somewhere else, and they still use their AIESEC email | Send a message **to** their AIESEC email (the one in the tool) asking them to confirm. Don't use the address it arrived from. |
   | They **no longer have access** to their AIESEC email (common for alumni) | Ask someone who knows them personally (e.g. their former LCP or team leader) to confirm on a video call that the requester is that person. Write down only *how* it was verified, e.g. "confirmed on video by former LCP". |
   | Someone is asking **on their behalf** (a parent, lawyer, etc.) | Don't act. Pass it to the Tech Lead, who decides what written authority is needed. |
   | You can't verify them | Don't act. Tell them what you need. If they don't respond within 30 days, record "declined: identity not verified". |

   Don't ask for photo ID or other documents.

4. Record **how** it was verified in the register.

> **If they're a current member:** anonymising someone stops them using the tool for
> good. If they still hold a membership this term, tell them this and ask them to confirm
> before you go on.

---

## Step 2: Find the person and check what's linked to them

Connect to the production database (see "What you need") and run these. Before each one,
change the value in `CAPITALS`.

**2a. Find their id.** Change `THEIR.EMAIL@aiesec.net` to the AIESEC email you verified:

```sql
SELECT id, full_name, status, (expa_id IS NOT NULL) AS linked_to_expa
  FROM person
 WHERE lower(aiesec_email) = lower('THEIR.EMAIL@aiesec.net');
```

- **One row:** note the `id`. From now on, refer to them only by this id. Write it in the
  register's **Person id** column, but not their name or email.
- **No rows:** we hold no data about them. Record "not found" in the register, tell them,
  and stop.
- **`status` already says `ANONYMISED`:** it has already been done. Record that, tell
  them, and stop.

**2b. Save the values you'll use.** Change the three values in `CAPITALS`. `psql` then
fills them into every command below, so you never retype the id:

```sql
\set person_id        PERSON_ID
\set request_ref      'DR-YEAR-NUMBER'
\set my_membership_id YOUR_MEMBERSHIP_ID
```

`YOUR_MEMBERSHIP_ID` is **your own** membership, so the audit log shows who acted. To find
it, change `YOUR.EMAIL@aiesec.net` to your own email and use the top row's `id`:

```sql
SELECT m.id, m.is_primary, m.start_date, m.end_date
  FROM membership m
  JOIN person p ON p.id = m.person_id
 WHERE lower(p.aiesec_email) = lower('YOUR.EMAIL@aiesec.net')
   AND (m.end_date IS NULL OR m.end_date >= current_date)
 ORDER BY m.is_primary DESC, m.start_date DESC;
```

**2c. Check what's linked to them.** Copy this exactly:

```sql
SELECT
  (SELECT count(*) FROM membership
    WHERE person_id = :person_id)                                    AS memberships,
  (SELECT count(*) FROM membership
    WHERE person_id = :person_id
      AND (end_date IS NULL OR end_date >= current_date))            AS current_memberships,
  (SELECT count(*) FROM kpi_record k
     JOIN membership m ON m.id = k.membership_id
    WHERE m.person_id = :person_id)                                  AS kpi_records,
  (SELECT count(*) FROM kpi_record k
     JOIN membership m ON m.id = k.recorded_by
    WHERE m.person_id = :person_id
      AND k.membership_id NOT IN
          (SELECT id FROM membership WHERE person_id = :person_id))  AS kpis_they_entered_for_others,
  (SELECT count(*) FROM kpi_record
    WHERE note ILIKE '%' || (SELECT full_name FROM person
                              WHERE id = :person_id) || '%')         AS notes_mentioning_their_name;
```

Write the numbers in your working notes for the reviewer (just the numbers).

---

## Step 3: Decide: anonymise or hard delete

| Situation | Do this |
|---|---|
| `memberships` is **more than 0** (almost everyone) | **Anonymise** (Step 4A). |
| `memberships` is **0** (added to the tool but never given a membership) | **Hard delete** (Step 4B). There is nothing to keep, so nothing is lost. |
| A legal obligation requires deletion beyond anonymisation, even though `memberships` is more than 0 | **Stop and pass it to the Tech Lead.** See "Hard delete despite memberships" below. |
| You're not sure | **Anonymise.** |

### Hard delete despite memberships (Tech Lead only)

This is rare and has no copy-and-paste script, on purpose. It removes the person's KPI
records and membership history, so **past KPI totals and headcounts change and submitted
reports no longer match the database**. The Tech Lead writes a one-off script for that
case, has it reviewed, and records the decision in the register. The script must handle,
in this order:

1. KPI records this person **entered for other people** (`kpi_record.recorded_by`) and
   custom-field values they entered (`attribute_value.recorded_by`). These point at the
   person's membership and would block the delete. Decide whether to keep them by
   re-attributing them or remove them. Never fake who entered them without writing that
   down.
2. Teams they lead (`team.leader_membership_id`): set to empty.
3. Their `kpi_record`, `team_member` and membership-level `attribute_value` rows.
4. Their `membership` rows, then person-level `attribute_value` rows, then the `person`
   row. Their sessions are removed automatically with the person row.
5. The audit entry (`person.delete`), as in Step 4B.

Spec §8.3 holds the full cascade map.

---

## Step 4: Run it, with the reviewer watching

Before you run anything, share your screen with the reviewer. The reviewer checks:

- [ ] `:person_id` matches the id in the register for this request reference.
- [ ] The Step 2 numbers support the choice made in Step 3.
- [ ] The commands are copied exactly, with only the `CAPITALS` values changed.

Then paste the script for your path. **It doesn't save anything by itself.** It ends with
a check, and you only save once the check is right.

> [!CAUTION]
> Once you type `COMMIT`, this **can't be undone** in the tool. The only way back is
> restoring a backup (guide 8), which would also undo everyone else's changes since then.

### Step 4A: Anonymise (the usual path)

```sql
BEGIN;

-- 1. Clear free-text KPI notes that may identify them: notes on their own KPI
--    entries, and anyone's notes that mention their full name.
--    The KPI numbers themselves are kept.
UPDATE kpi_record
   SET note = NULL
 WHERE note IS NOT NULL
   AND (membership_id IN (SELECT id FROM membership WHERE person_id = :person_id)
        OR note ILIKE '%' || (SELECT full_name FROM person WHERE id = :person_id) || '%');

-- 2. Remove their custom-field values (about them, and about their memberships).
DELETE FROM attribute_value
 WHERE (entity_type = 'PERSON'     AND entity_id = :person_id)
    OR (entity_type = 'MEMBERSHIP' AND entity_id IN
          (SELECT id FROM membership WHERE person_id = :person_id));

-- 3. Remove who they are from their person record.
--    The email becomes "anon+<id>@invalid": unique, but can never be a real address.
--    expa_id is cleared so the record no longer points to their EXPA profile.
UPDATE person
   SET full_name      = 'Anonymised person',
       preferred_name = NULL,
       aiesec_email   = 'anon+' || id || '@invalid',
       personal_email = NULL,
       phone          = NULL,
       expa_id        = NULL,
       status         = 'ANONYMISED',
       anonymised_at  = now() AT TIME ZONE 'UTC'
 WHERE id = :person_id
   AND status <> 'ANONYMISED';

-- 4. Sign them out everywhere, straight away.
UPDATE user_session
   SET revoked_at = now()
 WHERE person_id = :person_id
   AND revoked_at IS NULL;

-- 5. Record what was done: the id and the request reference only.
INSERT INTO audit_log (actor_membership_id, action, resource_type, resource_id, summary)
VALUES (:my_membership_id, 'person.anonymise', 'person', :person_id,
        'Anonymised under deletion request ' || :'request_ref');

-- 6. Check: this must show ONE row matching "Expected" below.
SELECT p.status,
       p.expa_id IS NULL AS expa_cleared,
       p.aiesec_email,
       (SELECT count(*) FROM user_session s
         WHERE s.person_id = p.id AND s.revoked_at IS NULL) AS open_sessions,
       (SELECT count(*) FROM attribute_value
         WHERE (entity_type = 'PERSON' AND entity_id = p.id)
            OR (entity_type = 'MEMBERSHIP' AND entity_id IN
                  (SELECT id FROM membership WHERE person_id = p.id))) AS custom_values_left,
       (SELECT count(*) FROM audit_log a
         WHERE a.resource_type = 'person' AND a.resource_id = p.id
           AND a.action = 'person.anonymise') AS audit_entries
  FROM person p
 WHERE p.id = :person_id;
```

**What you should see, line by line:**

- After 3 (`UPDATE person`): **`UPDATE 1`**. Anything else (especially `UPDATE 0`) means
  stop: type `ROLLBACK;`.
- After 1, 2 and 4: any number, including 0, is fine.
- After 5: `INSERT 0 1`.
- **Expected** check (step 6):

  | status | expa_cleared | aiesec_email | open_sessions | custom_values_left | audit_entries |
  |---|---|---|---|---|---|
  | ANONYMISED | t | anon+PERSON_ID@invalid | 0 | 0 | 1 |

If the line and the reviewer both agree it's right, type:

```sql
COMMIT;
```

**What's kept:** their memberships, team history and KPI numbers, now linked to an
anonymous record. Past totals and reports don't change.

### Step 4B: Hard delete (only when `memberships` was 0)

```sql
BEGIN;

-- 1. Record what was done FIRST, while the record still exists.
INSERT INTO audit_log (actor_membership_id, action, resource_type, resource_id, summary)
VALUES (:my_membership_id, 'person.delete', 'person', :person_id,
        'Deleted under deletion request ' || :'request_ref');

-- 2. Clear anyone's KPI notes that mention their full name.
UPDATE kpi_record
   SET note = NULL
 WHERE note ILIKE '%' || (SELECT full_name FROM person WHERE id = :person_id) || '%';

-- 3. Remove their custom-field values.
DELETE FROM attribute_value
 WHERE entity_type = 'PERSON'
   AND entity_id   = :person_id;

-- 4. Delete the person. Their sign-in sessions are deleted with it automatically.
--    The NOT EXISTS line makes this do nothing if they have a membership after all.
DELETE FROM person
 WHERE id = :person_id
   AND NOT EXISTS (SELECT 1 FROM membership WHERE person_id = :person_id);

-- 5. Check: both numbers must be 0.
SELECT (SELECT count(*) FROM person       WHERE id = :person_id)        AS person_left,
       (SELECT count(*) FROM user_session WHERE person_id = :person_id) AS sessions_left;
```

**What you should see:** `INSERT 0 1`, then any number for step 2 and 3, then **`DELETE 1`**
for step 4 (`DELETE 0` means stop: type `ROLLBACK;`), then `0 | 0` for the check. If it's
all right and the reviewer agrees:

```sql
COMMIT;
```

---

## Step 5: Close the request

1. **Update the register:** decision, operator and reviewer (by position), and date completed.
2. **Tell the requester**, from the same shared address:

   > Hi, your deletion request (DR-2026-001) is complete. Your name, email and other
   > personal details have been removed from the AIESEC Australia Membership Tool, and you
   > can no longer sign in to it. *[If anonymised:]* Activity numbers you contributed
   > while a member are kept without your name, so past totals stay correct.
   >
   > Our database backups are kept for 7 days, so your details will be gone from every
   > backup by **DATE + 7 DAYS**.
   >
   > This covers the Membership Tool only. Your EXPA account is run by AIESEC
   > International, so contact them to delete it. Spreadsheets, chats or other records
   > kept by your LC are separate. Let us know if you'd like us to pass the request on.

3. **Record the date you told them** in the register.

### Where else their data lives (and doesn't)

| Place | What happens |
|---|---|
| **Database backups** | Kept 7 days (Cloud SQL automatic backups, DEV-65/DEV-80). Their data is gone from all backups 7 days after Step 4. On-demand backups taken before a release are deleted on a schedule after 7 days too. Never restore an old backup just to "check something" from before the request. |
| **Audit log** | Kept. It should contain only ids, never names or emails, and its entries can't be changed. Older entries about this person now point to an anonymous or missing record, which is expected. If you ever find personal data in it, tell the Tech Lead. |
| **Google Cloud application logs** | Kept for 30 days, then deleted automatically. They shouldn't contain names or emails. If you find any, tell the Tech Lead. |
| **EXPA** | Run by AIESEC International, not us. The requester asks them directly. |
| **LC spreadsheets, Slack, email** | Outside the tool. Mention them to the requester (see the message above). |

---

## Check it worked

- The register row has every column filled in, and contains no name or email.
- **Anonymised:** running the 2a query with their old email returns **no rows**, and the
  step 6 check showed `ANONYMISED`, `t`, `0`, `0`, `1`.
- **Hard-deleted:** the step 5 check showed `0 | 0`.
- The requester has been told, within 30 days of the request arriving.

## If something goes wrong

| You see | What it means | What to do |
|---|---|---|
| `ERROR: …` on any line, then `current transaction is aborted` | One command failed, so nothing after it ran and nothing is saved | Type `ROLLBACK;`. Read the first error, fix it, and start Step 4 again. |
| `UPDATE 0` after the `person` update, or `DELETE 0` after the `person` delete | Wrong id, already anonymised, or (hard delete) they have a membership | `ROLLBACK;`. Re-run Step 2 and check the id. |
| `ERROR: … :person_id …` or `syntax error at or near ":"` | The `\set` values from 2b were lost, e.g. you reconnected | Re-run the three `\set` lines, then start Step 4 again. |
| `violates foreign key constraint` during a hard delete | They have a membership or other linked records | `ROLLBACK;`. Anonymise instead (Step 4A). |
| `audit_log is append-only` | Something tried to change the audit log | `ROLLBACK;`. This guide never does that, so check you copied the commands exactly. |
| The connection drops before `COMMIT` | Nothing was saved | Reconnect, redo 2b, start Step 4 again. |
| You committed the wrong person | — | Tell the Tech Lead **immediately**. Recovery means a restore (guide 8) and is time-sensitive. |

## Quick checklist

- [ ] Reference given, register row started, acknowledged within 5 business days
- [ ] Identity verified; *how* recorded in the register
- [ ] Current member? They confirmed they understand they'll lose access
- [ ] Person id found (2a); values set (2b); links checked (2c)
- [ ] Path chosen: anonymise / hard delete / passed to Tech Lead
- [ ] Reviewer checked the id and the commands before running
- [ ] Check row matched "Expected"; reviewer agreed; `COMMIT`
- [ ] Register updated; requester told (including the 7-day backup date); date recorded
- [ ] All done within 30 days of the request arriving

## Related guides

- [README](README.md): the rules for these guides, including when code is allowed.
- 8. Restoring from a backup (not written yet): the only way to undo a mistake here.
- 10. Who holds which accounts (not written yet): who is in `mt-tech-leads@`.
- Developer background: spec §8 (privacy and deletion), `docs/data-model.md` (the tables
  used here), `docs/auth.md` (why anonymised people can't sign in).
