# Design: recovering admin access when every admin is locked out

**Status:** draft for the Tech Lead's review. Not built yet. Ticket: DEV-66.
**Date:** 2026-11-16
**Resolves:** spec §12 #21 ("admin lockout recovery: approach still to be chosen").
**Becomes:** admin guide 9 (spec §10A), once the admin guide folder lands (DEV-67).
**Builds on:** `2026-11-09-gcp-deployment-design.md` §5.3 (Cloud SQL) and §10 (IAM and
access), which DEV-78 sets up.

Written for a reader with no prior context. Anything marked **[verify]** is a behaviour or
name taken from documentation or a guess. Check it before relying on it.

---

## 1. The problem

Admin access to the Membership Tool comes from a **membership**, not from an account
(spec §2A.2, §5.3). A person gets into the Admin console because they hold an MC (or
admin) position for a term, and the access ends on that membership's `end_date`, without
anyone removing it.

That's deliberate, but it creates a failure mode an ordinary app doesn't have. At the end
of a term, **every** admin membership can expire on the same day. A misconfiguration
(wrong date, wrong position) can do the same thing at any time. Once that happens, nobody
can fix it through the app, because fixing memberships is itself an admin task.

Separately, the people who can reach the database (the tech leads) also turn over every
year. If they leave before their successors get access, the database fix isn't available
either.

This is a pre-launch blocker (spec §10A guide 9). It needs a written procedure that works
for someone who has never seen the system.

## 2. Goals, non-goals, anti-goals

**Goals**
- Two recovery paths, covering the two ways this goes wrong:
  1. **App lockout:** every admin membership has expired or is wrong. Fix it in the
     database.
  2. **Infrastructure lockout:** the people with GCP access have left. Get access back
     through the break-glass account, `hello@aiesecaustralia.org`.
- Each path can be carried out by **at least two people independently** (`CLAUDE.md`: no
  single point of failure).
- Every use leaves a trace: an `audit_log` entry for the data change, and an incident-log
  entry for the whole event.
- Copy-paste SQL that is **tested in CI**, so it can't quietly break as the schema changes.

**Non-goals**
- New app code. Recovery uses the database and GCP access the deployment design already
  provides.
- Automatic alerts when admin memberships are about to expire. Useful, but **Phase 2**
  (§9).
- Recovering a lost EXPA account. That belongs to AIESEC International.
- Restoring lost data. That is guide 8 (restoring from a backup).

**Anti-goals (it fails even if it "works" if…)**
- …recovery depends on one specific person still being around.
- …it adds a permanent back door: a hidden super-admin account, a bypass flag, or a
  master password.
- …the tech team uses it to give *itself* admin access to member data, instead of giving
  access back to the rightful admin.
- …it changes data without an `audit_log` entry, or writes personal data into the log.
- …it hands out access that never ends.

## 3. What exists today (checked in the repo, 2026-11-16)

- **Who counts as an admin.** Admin-console permissions are still hardcoded: the MC
  positions `mcd`, `mcvp`, `mcp`, plus an `admin` position that isn't seeded yet
  (`backend/app/core/permissions.py`: `MC_POSITIONS`, `ADMIN_POSITIONS`). The
  `admin_console` resource (spec §2A.2) and the database-backed permission matrix aren't
  built yet. Recovery therefore restores an **MC-level membership**. That gives access
  today, and will keep doing so once the matrix exists, as long as the chosen position
  holds `admin_console` (§8).
- **Memberships.** `membership` has `person_id`, `lc_id`, `position_id`, `function_id`
  (nullable), `term_id`, `start_date`, `end_date` (nullable today; spec §12 #22 makes it
  required for new rows) and `is_primary`. A membership is active when `start_date <=
  today` and `end_date` is null or `>= today`
  (`repositories/membership.py::get_active_memberships_for_person`). The MC is the `lc`
  row with `type = 'MC'`.
- **Extending is a normal edit.** The app's own "extend term" sets a later `end_date` on
  the existing row and logs `membership.extend_term` with
  `diff = {"before": "<old date>", "after": "<new date>"}`. Adding a membership logs
  `membership.create` with `diff = {"after": {...ids and dates...}}`. The recovery SQL
  writes the **same actions and diff shapes**, so its entries look like any other change
  in the Auditing tab.
- **The audit log.** `audit_log` is append-only, enforced by triggers that reject every
  `UPDATE`, `DELETE` and `TRUNCATE` whichever database user is connected. The actor
  columns are nullable: a null actor means a system action, which is what a recovery is.
- **Seeds.** The baseline seeds don't create the MC row or any terms. On a real or demo
  database those exist. On a fresh local database you need to add them before you can
  rehearse.
- **Not set up yet** (DEV-78 and later): `infra/`, the Workspace groups
  (`mt-tech-leads@`, `gcp-org-admins@`), `docs/incident-response.md`,
  `docs/access-and-ownership.md`. This design describes the setup as the deployment
  design intends it. The pre-launch checklist (§7) confirms it actually exists.

## 4. Decision

### 4.1 Chosen: two tiers, using existing access

```text
Can an admin sign in to the Admin console?
├── yes ─────────────► not a lockout. Use guide 2 / 3 in the console.
└── no
    Is anyone in mt-tech-leads@ still available?
    ├── yes ─────────► TIER 1: database fix (§5)
    └── no ──────────► TIER 2: hello@ break-glass (§6), which ends in TIER 1
```

- **Tier 1, database fix.** A member of `mt-tech-leads@` connects to the prod database
  through the Cloud SQL Auth Proxy. They extend an expired MC membership, or create one,
  with a single SQL transaction that also writes the `audit_log` entry. The restored
  admin then does the proper handover in the Admin console.
- **Tier 2, break-glass.** An MC member opens `hello@aiesecaustralia.org` from Bitwarden,
  uses it to give two people GCP access again, and those people carry out Tier 1.

### 4.2 Rejected alternatives

| Alternative | Why not |
|---|---|
| A reserved super-admin account in the app | An admin account tied to an individual, which spec §2A.2 rules out. It's also custom auth, which the project doesn't build, and a permanent target for attackers to protect something that happens about once a year. |
| A "recovery mode" flag or environment variable that skips the admin check | A back door with no audit trail of who used it. Anyone who can change Cloud Run settings could switch it on quietly. |
| Admin memberships with no end date | Breaks spec §5.3 ("access follows the dates") and leaves people with admin access after they've left. |
| Rely only on handover being done properly | Prevention helps (§9), but the ticket asks for a fix that works when prevention has failed. |

The database fix needs no new code, uses access the tech leads must have anyway (to run
migrations and the manual deletion procedure), and every connection is visible in Cloud
Audit Logs.

## 5. Tier 1: fix it in the database

### 5.1 Who and where

- **Who:** any member of `mt-tech-leads@` (Tech Lead and a senior dev, at least 2 people).
  Each can do it alone.
- **Where:** **Google Cloud Shell** in the `aiesec-au-mt-prod` project. It already has
  `gcloud` and `psql` **[verify: and `cloud-sql-proxy`]**, needs no install, and nothing
  is copied to a personal laptop.
- **Rehearse on dev first** if there's time: the same steps on `membership_dev` with
  `mt_app_dev`. Dev only holds demo data.

### 5.2 Which database login

The deployment design defines two Postgres users per environment: `mt_migrator_<env>`
(owns the schema) and `mt_app_<env>` (the app's runtime login). It doesn't define a login
for people.

**Decision: use `mt_app_prod`.** It's the least-privileged user that can do the job:
- It can change rows in `membership`, through the shared `mt_runtime` role.
- It can only `INSERT` and `SELECT` on `audit_log`, and the triggers block edits whoever
  is connected.
- It can't change the schema.

Its password is in Secret Manager, which tech leads can already read (`roles/owner` on
prod). The weakness is a shared password, but who connected is still recorded: the Auth
Proxy only lets people in with their own Google identity, and Cloud Audit Logs records
each one. Changing the password is already on the offboarding checklist (deployment
design §10, step 5).

**Follow-up (separate ticket, not a blocker):** Cloud SQL IAM group authentication, so
people log in to Postgres as themselves with no shared password **[verify: supported for
Postgres 16 on shared-core]**.

### 5.3 Connecting

```bash
# 1. In Cloud Shell, check you're signed in as yourself and on the prod project.
gcloud config set project aiesec-au-mt-prod
gcloud auth list

# 2. Start the Auth Proxy in the background. INSTANCE_NAME is in infra/ (DEV-78).
cloud-sql-proxy "aiesec-au-mt-prod:australia-southeast1:INSTANCE_NAME" --port 5433 &

# 3. Connect. psql asks for the password: paste it from Secret Manager
#    (Cloud console → Secret Manager → the mt_app_prod secret, name in infra/).
#    Never put the password in the command itself, or it lands in your shell history.
psql "host=127.0.0.1 port=5433 dbname=membership_prod user=mt_app_prod"
```

### 5.4 Step 1: look before changing anything

Read-only. It shows who holds an MC or admin membership and whether it's active today.
It shows only ids, positions and dates, not names.

<!-- recovery-sql: look -->
```sql
SELECT m.id          AS membership_id,
       m.person_id,
       pos.key       AS position,
       m.start_date,
       m.end_date,
       (m.start_date <= CURRENT_DATE
        AND (m.end_date IS NULL OR m.end_date >= CURRENT_DATE)) AS active_today
FROM membership m
JOIN lc       ON lc.id  = m.lc_id
JOIN position pos ON pos.id = m.position_id
WHERE lc.type = 'MC' OR pos.key IN ('mcd', 'mcvp', 'mcp', 'admin')
ORDER BY m.end_date DESC NULLS FIRST
LIMIT 20;
```

If any row shows `active_today = t`, this isn't a lockout. Find out why that person can't
sign in before changing anything.

Then look up the ids you'll need. Replace `AIESEC_EMAIL` with the AIESEC email of the
person whose access you're restoring:

<!-- recovery-sql: lookup -->
```sql
SELECT id AS person_id, status FROM person WHERE aiesec_email = 'AIESEC_EMAIL';
SELECT id AS mc_lc_id FROM lc WHERE type = 'MC';
SELECT id AS position_id, key FROM position WHERE key IN ('mcp', 'mcvp', 'mcd', 'admin') AND active;
SELECT id AS term_id, name, start_date, end_date FROM term
WHERE CURRENT_DATE BETWEEN start_date AND end_date;
```

- The person must already exist and have status `ACTIVE`. If they don't exist, restore
  someone who does (usually the outgoing admin), and let them add the new person in the
  Admin console. This design deliberately doesn't add people with SQL, because that
  means typing personal data into a terminal.
- If there's no MC row or no current term, this isn't a lockout but an unfinished setup.
  Stop and treat it as a data problem.
- The term query can return more than one row, because terms can overlap. Pick the term
  the restored membership belongs to (usually the one the MC term is named after). The
  dates decide access, not the term (spec §5.3), so a close choice is harmless.

### 5.5 Who to restore, and until when

Restore the **rightful admin**: the current or outgoing MCP, or the MC VP who runs the
tool. Don't restore a tech lead, unless they really hold that position. The point is to
hand control back to the MC, not to give the tech team admin access to member data.

| Situation | What to do | End date |
|---|---|---|
| The **current** admin's membership is wrong (wrong date, ended early by mistake) | Case A: extend it | Their real term end |
| The term ended and nobody added the successor; you restore the **outgoing** admin so they can do the handover | Case A if their old MC membership exists, otherwise case B | **14 days from today.** Their term is over, so they get just long enough to add the incoming admin in the console, and the access ends by itself |
| The current admin never had an MC membership | Case B: create one | Their real term end |

Always set an end date. Never pick today: the database's `CURRENT_DATE` is in UTC, while
the app checks terms in the person's own timezone (spec §5.3).

### 5.6 Step 2, case A: extend an existing membership

Replace `MEMBERSHIP_ID` (from step 1), `NEW_END_DATE` (as `YYYY-MM-DD`) and `INCIDENT_ID`
(from the incident log, §5.8). Copy everything else exactly.

<!-- recovery-sql: extend -->
```sql
BEGIN;

WITH old AS (
    SELECT id, end_date
    FROM membership
    WHERE id = MEMBERSHIP_ID
    FOR UPDATE
), changed AS (
    UPDATE membership m
    SET end_date = DATE 'NEW_END_DATE'
    FROM old
    WHERE m.id = old.id
      AND DATE 'NEW_END_DATE' > CURRENT_DATE
    RETURNING m.id, old.end_date AS old_end, m.end_date AS new_end
)
INSERT INTO audit_log (action, resource_type, resource_id, summary, diff)
SELECT 'membership.extend_term',
       'membership',
       id,
       'Admin lockout recovery (guide 9), incident INCIDENT_ID: extended term of membership ' || id,
       jsonb_build_object('before', old_end::text, 'after', new_end::text)
FROM changed
RETURNING id AS audit_log_id, resource_id AS membership_id;

COMMIT;
```

You should see **exactly one row** returned (an `audit_log_id` and a `membership_id`),
followed by `INSERT 0 1`. If you see `(0 rows)` and `INSERT 0 0`, the id was wrong or the
date wasn't in the future, and nothing was changed: check step 1 and try again.

How it works, for the developer reading this: `old` reads the end date *before* the
change. That's needed because Postgres 16 can't return old values from `UPDATE`. `changed`
does the update, and the `INSERT` writes one log row per changed membership. It's a single
statement inside one transaction, so the change and its log entry are saved together or
not at all, exactly like `record_audit` in the app. A placeholder you forget to replace
(`MEMBERSHIP_ID`, `DATE 'NEW_END_DATE'`) is a syntax error, so it fails safely.

### 5.7 Step 2, case B: create a new membership

Replace `PERSON_ID`, `MC_LC_ID`, `POSITION_ID`, `TERM_ID` (all from step 1),
`NEW_END_DATE` and `INCIDENT_ID`.

<!-- recovery-sql: create -->
```sql
BEGIN;

WITH created AS (
    INSERT INTO membership
        (person_id, lc_id, position_id, function_id, term_id, start_date, end_date, is_primary)
    VALUES
        (PERSON_ID, MC_LC_ID, POSITION_ID, NULL, TERM_ID, CURRENT_DATE, DATE 'NEW_END_DATE', false)
    RETURNING id, lc_id, position_id, start_date, end_date
)
INSERT INTO audit_log (action, resource_type, resource_id, summary, diff)
SELECT 'membership.create',
       'membership',
       id,
       'Admin lockout recovery (guide 9), incident INCIDENT_ID: added membership ' || id,
       jsonb_build_object('after', jsonb_build_object(
           'lc_id', lc_id,
           'position_id', position_id,
           'start_date', start_date::text,
           'end_date', end_date::text))
FROM created
RETURNING id AS audit_log_id, resource_id AS membership_id;

COMMIT;
```

You should see exactly one row returned, followed by `INSERT 0 1`.

### 5.8 Step 3: check it worked, and log it

1. Run step 1 again. The membership should show `active_today = t`.
2. Ask the restored admin to sign in at `/admin/sign-in`. **This is the real check.** If
   they still can't get in, the problem isn't the membership: check their sign-in in the
   audit log and the runbook's "everyone gets not-allocated" entry.
3. Write the incident-log entry (`docs/incident-response.md` holds the template once it's
   written; until then, a document in the MC shared drive). Record:
   - incident id, date and time
   - who ran it, and which tier
   - why: what caused the lockout
   - the `membership_id` and `audit_log_id` from step 2
   - the end date chosen, and why
   - follow-ups: the handover to do in the console, any temporary GCP access to remove
     (§6), anything to fix so it doesn't happen again
4. If the restored admin was the outgoing one, check before their 14 days run out that
   the incoming admin can sign in. If the window runs out first, repeat Tier 1. That's
   quick, but it means a second incident entry.

## 6. Tier 2: break-glass through `hello@`

Use this only when **nobody in `mt-tech-leads@` is available**.

### 6.1 Who

Any MC member with access to the Bitwarden item holding `hello@aiesecaustralia.org` and
its 2FA backup codes (at least 2 people, by position). They don't need to be technical.
Tier 2 only restores access, and the technical step (Tier 1) is done by the people it
restores.

### 6.2 The gap this has to handle

The deployment design puts `hello@` in `gcp-org-admins@`, which grants GCP **Organization
Admin**. That role can change who has access to GCP projects. But **the groups
themselves are Google Workspace groups**, and adding people to them is a Workspace admin
job (super admin or Groups Admin, at admin.google.com), not a GCP one. The deployment
design notes the same uncertainty (§10: "If `hello@` isn't a super admin…").

So which steps work depends on what `hello@` is:

| `hello@` is… | Steps |
|---|---|
| **A Workspace super admin** (preferred) | 1. Sign in to admin.google.com as `hello@`. 2. **Groups** → `mt-tech-leads@` → add the two people now holding the Tech Lead and senior dev roles. 3. They carry out Tier 1. 4. Nothing to undo: the groups are now correct. |
| **Only a GCP Organization Admin** | 1. Sign in to console.cloud.google.com as `hello@`. 2. **IAM** on project `aiesec-au-mt-prod` → grant `roles/owner` directly to two people's `aiesecaustralia.org` accounts **[verify: Org Admin can set project IAM through inheritance]**. 3. They carry out Tier 1. 4. Get a Workspace super admin to fix the groups. 5. **Remove the direct grants** within 7 days, and note the removal in the incident log. Direct grants to named people break the group rule, so they are temporary. |

The pre-launch checklist (§7) asks for `hello@` to be a Workspace super admin, alongside
at least one other super admin. That makes the first row the normal case.

### 6.3 If `hello@` itself is lost

If the password and the 2FA backup codes are both lost:
1. Another Workspace super admin resets the `hello@` password.
2. If there's no other super admin, use Google Workspace's account recovery for the
   domain. It proves domain ownership with a DNS record, and DNS is on Cloudflare, which
   the national team owns **[verify: current recovery process]**. This is slow (days),
   and it's why §7 asks for two super admins.

## 7. Pre-launch checklist (DEV-68's security audit ticks these)

The recovery paths only exist if the setup does. Before launch, confirm:

- [ ] `mt-tech-leads@` exists and has at least 2 members, by role.
- [ ] Each member can connect to `membership_prod` through the Auth Proxy (§5.3).
- [ ] `hello@` is a member of `gcp-org-admins@`.
- [ ] `hello@` is a Workspace super admin, and there's at least one other super admin.
- [ ] The Bitwarden item for `hello@` (password and 2FA backup codes) is shared with at
      least 2 MC positions.
- [ ] At least two people hold an active MC membership with admin access, and the
      incoming MC's memberships are added before the outgoing ones end (§9).
- [ ] The recovery SQL test (§8) is in CI and runs on changes to guide 9.
- [ ] A dev rehearsal of Tier 1 has been done, with the date written in
      `docs/runbook.md`.
- [ ] The Tech Lead has reviewed this design and guide 9.

## 8. Keeping it working

**A test that runs the guide's SQL.** `backend/tests/test_lockout_recovery_sql.py`:
- Reads the SQL blocks out of the markdown file, finding them by their
  `<!-- recovery-sql: NAME -->` markers. It reads this design until guide 9 exists, then
  the guide.
- Sets up an expired MC membership, fills in the placeholders, and runs the `look`,
  `extend` and `create` blocks.
- Checks that each one changes exactly one membership, writes exactly one `audit_log`
  row with the expected action and diff, and puts no names or emails in the log.
- Checks that an end date in the past changes nothing.
- Checks that every position key the SQL uses is still one that grants admin access
  (today `MC_POSITIONS | ADMIN_POSITIONS`; once it exists, a position holding
  `admin_console` in the matrix).

The test drops the `BEGIN;` and `COMMIT;` lines, because the `db_session` fixture already
wraps each test in a transaction that's rolled back.

**When it lands: with guide 9, not with this design.** The test should check the SQL that
admins actually copy, and that will be the guide. This design is a snapshot of the
decision, and may still change in review. The same PR needs two setup fixes:
- **CI path filter.** `.github/workflows/backend.yml` only runs on changes under
  `backend/**`. Add `docs/admin-guide/09-*.md` to its `paths:` lists, or a PR that edits
  only the guide's SQL won't run the test.
- **Local test runs.** The backend container only mounts `./backend`
  (`docker-compose.yml`), so `make test` can't see `docs/`. Either mount `docs/`
  read-only, or have the test skip with a clear message when the file is missing. The
  skip must never happen in CI.

Why it's worth having: this SQL might be used once a year, by someone who's never seen
it, during an incident. The schema is about to change (spec §12 #22: `end_date` required,
`position.level`, `audit_log.actor_person_id`, the permission matrix). Without a test,
the guide breaks quietly. With it, CI fails on the PR that breaks it, and that PR updates
the guide.

**A rehearsal once per term**, alongside the restore test (deployment design §13): run
Tier 1 on dev and write the date in `docs/runbook.md`. The test checks the SQL; only a
rehearsal checks the Auth Proxy, the login, and that people still have access.

## 9. Prevention (cheap, and partly Phase 2)

Prevention lowers how often this happens. It doesn't replace the procedure.

- **This term:** guide 3 (term handover) says the incoming MCP is added *before* the
  outgoing MC's memberships end. Spec §2 already allows two presidents to overlap. The
  §7 checklist asks for at least two people with admin access.
- **Phase 2 (flag, don't build):** an email to `mt-alerts@` when fewer than two admin
  memberships will be active 30 days from now. It's one scheduled query, but scheduled
  jobs are out of scope this term.

## 10. Files to change (after approval)

| File | Change |
|---|---|
| `docs/admin-guide/09-recovering-admin-access.md` | **New**, once DEV-67 lands. The plain-language version of §4–§6, written to the README's rules for emergency guides: each command in its own box, placeholders in `CAPITALS`, who can run it and where, how to check it worked |
| `docs/admin-guide/README.md` | Guide 9 status → Written |
| `docs/membership-tool-requirements-spec.md` | §12 #21 → resolved, pointing to guide 9 and this design |
| `docs/superpowers/specs/2026-11-09-gcp-deployment-design.md` | §10: note that re-adding people to Workspace groups needs a Workspace admin, and that `hello@` should be a super admin. §5.3: people log in to Postgres as `mt_app_<env>` through the Auth Proxy until IAM DB auth exists |
| `backend/tests/test_lockout_recovery_sql.py` | **New**, the test in §8, in the same PR as guide 9 |
| `.github/workflows/backend.yml`, `docker-compose.yml` | The path filter and local mount fixes in §8, also in the guide 9 PR |

## 11. Decisions recorded and open items

**Decided in this design (for the Tech Lead to confirm):**
- Two tiers using existing access. No app code, and no super-admin account.
- People log in to Postgres as `mt_app_prod` for now. IAM DB auth is a follow-up ticket.
- End date: the real term end when fixing the current admin; 14 days when restoring the
  outgoing admin for a handover.
- Restore the rightful MC admin, not the tech team.
- The SQL is tested in CI, and Tier 1 is rehearsed on dev once per term.

**Open:**
- Is `hello@` a Workspace super admin today? Whoever runs Workspace for the national team
  can check. §6.2 covers both answers.
- Where the incident log lives, until `docs/incident-response.md` is written.
- The Secret Manager secret name and the Cloud SQL instance name: set by DEV-78 in
  `infra/`.
- Which positions hold `admin_console` once the matrix exists (spec §12 #13, #19). The
  test in §8 makes sure the SQL keeps up.

**Checked locally (2026-11-16, Postgres 16 in Docker Compose, at migration head):** the
four SQL blocks, taken straight from this file, were run against a throwaway MC row, MCP
position, term, person and expired MC membership. Each scenario ran inside a transaction
that was rolled back afterwards. Results:
- **Look and lookup:** they showed the expired membership (`active_today = f`) and every
  id needed. The term query returned two overlapping terms, hence the note in §5.4.
- **Case A, extend:** one membership changed, now `active_today = t`. One
  `membership.extend_term` row, with `diff = {"before": "<old>", "after": "<new>"}`, a
  null actor, and no names or emails.
- **Case A with a past date:** `(0 rows)`, `INSERT 0 0`, and neither the membership nor
  the log changed.
- **Case B, create:** one new active membership and one `membership.create` row, with the
  same diff shape the app uses.
- **Tampering:** an `UPDATE` on the new log row was rejected by the append-only trigger.
- **Forgotten placeholder:** an unreplaced `NEW_END_DATE` failed with a syntax error
  before anything changed.

This was a one-off check. The CI test in §8 is what keeps it true.
