# Changing the database schema (Supabase)

What to do when a pull request changes the database structure: a new table, a new
column, a renamed or removed one. Written for someone with no prior context.

**Why this exists.** Merging code does **not** change the Supabase database.
CI only tests against a throwaway Postgres it builds from scratch, and migrations
are never run automatically (see `CLAUDE.md`, "Running it"). Someone has to apply
each migration to Supabase by hand, in the right order. This page is that
procedure. If it is ever automated (a GitHub Actions job on merge), update this
page to say so.

> **Status:** until the backend is deployed and ticket 2 has realigned the seed
> data, Supabase is only used for sign-in. Nothing here is urgent yet. Follow it
> once the Supabase database is in use.

---

## When this applies

Use this page whenever a PR touches `backend/migrations/versions/` (a new Alembic
migration file). If a PR changes only code, you do not need it.

Two kinds of change are **not** migrations but also need a manual step:

- **New reference data** (new positions, functions, attributes) loaded by a seed
  script, not by the admin UI: run the seed against Supabase too (step 7).
- **New environment variables**: add them to wherever the backend is hosted, not
  just to `.env.example` (see `docs/local-development.md`).

---

## Before you start

You need:

1. The **Supabase database password** (the Postgres one, not your Supabase login).
   It lives in the team's shared password manager. Never ask for it in chat and
   never commit it. If it is lost, an owner can reset it under *Project Settings →
   Database → Reset database password*.
2. The **Session pooler** connection string, from the Supabase dashboard's
   **Connect** button. Use *Session pooler* (port 5432), not *Direct connection*
   (IPv6-only, fails from most laptops and Docker) and not *Transaction pooler*
   (port 6543, breaks migrations). It looks like:

   ```
   postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```

   The backend needs it as `postgresql+psycopg://...`, with the real password.
   URL-encode special characters in the password (`@` becomes `%40`, `/` becomes
   `%2F`, `#` becomes `%23`).
3. Docker running locally (the commands below run Alembic inside the backend
   container).

---

## Procedure

### 1. Write and test the migration locally

On your branch, against the **local** Docker database:

```bash
make migration name="short description"   # generates the file, then read it
make migrate                              # applies it locally
make test                                 # must be green
```

Always open the generated file and read it. Alembic's autogenerate can miss things
(renames look like a drop plus an add, which destroys data).

### 2. Make the migration safe to run before the new code

Supabase is updated **before** the new code goes live, so for a short time the
*old* code runs against the *new* schema. Write migrations so that is harmless:

- **Adding** a table or a nullable column: safe.
- **Adding a required column**: give it a default, or add it nullable first and
  tighten it in a later release.
- **Removing or renaming** a column or table: do it in two releases. Release one
  stops using it; release two drops it.
- **Never edit a migration that has already been applied to Supabase.** Add a new
  one on top.

### 3. Lock down any new table (row-level security)

Supabase exposes every table in the `public` schema through its own REST API, and
the publishable key in the frontend config can use it. A table without row-level
security (RLS) can be read or written directly, bypassing this backend, including
member data.

Every migration that creates a table must also enable RLS on it:

```python
op.execute("ALTER TABLE my_new_table ENABLE ROW LEVEL SECURITY")
```

Add no policies. With none, the REST API is denied and the backend (which connects
as the `postgres` role and ignores RLS) keeps working.

### 4. Merge the PR

CI must be green. Merge to `main` as usual. This does **not** touch Supabase.

### 5. Back up, then check where Supabase is

1. In the Supabase dashboard, confirm a recent backup exists (*Database → Backups*),
   or take a manual one if your plan allows. The spec requires backups at least
   every 24 hours (§10).
2. Check which migration Supabase is currently on. Start a hidden password prompt,
   then run the command (one line, no line breaks):

   ```bash
   read -s DBPASS
   ```
   ```bash
   docker compose run --rm -e DATABASE_URL="postgresql+psycopg://postgres.<project-ref>:${DBPASS}@aws-0-<region>.pooler.supabase.com:5432/postgres" backend uv run alembic current
   ```

   It prints a revision id. Compare it with `alembic heads` (run locally with
   `make migrate` output, or `docker compose run --rm backend uv run alembic heads`).
   If they differ, the new migration is what is pending.

### 6. Apply the migration to Supabase

Same `DBPASS` as above, on one line:

```bash
docker compose run --rm -e DATABASE_URL="postgresql+psycopg://postgres.<project-ref>:${DBPASS}@aws-0-<region>.pooler.supabase.com:5432/postgres" backend uv run alembic upgrade head
```

Expected: a few `Running upgrade ... -> ...` lines and no error. Run
`alembic current` again and confirm it now matches the latest revision.

### 7. Load reference data, if the PR needs it

Only if the PR added or changed seed data. Run the seed scripts the same way:

```bash
docker compose run --rm -e DATABASE_URL="postgresql+psycopg://postgres.<project-ref>:${DBPASS}@aws-0-<region>.pooler.supabase.com:5432/postgres" backend uv run python -m app.seeds.seed_lookups
```

(`app.seeds.seed_attributes` loads placeholder KPI data. Do not run it against the
real database.)

### 8. Deploy the new code

Only now deploy the backend (and frontend, if it changed). Order matters:
**database first, code second.**

### 9. Check it worked

- *Supabase → Table Editor* shows the new table or column.
- The new table shows **RLS enabled** (a padlock or "RLS enabled" badge). If it does
  not, run `ALTER TABLE <name> ENABLE ROW LEVEL SECURITY;` in the SQL editor now.
- Call a backend endpoint that uses the change, and check the logs for errors.

---

## If something goes wrong

**The migration fails partway.** Alembic runs each migration in a transaction on
Postgres, so a failed one normally changes nothing. Read the error, fix the
migration **in a new PR**, and re-run step 6.

**The migration worked but the new code is broken.** Roll the code back first. Only
then, if you must undo the schema, run:

```bash
docker compose run --rm -e DATABASE_URL="..." backend uv run alembic downgrade -1
```

A downgrade that drops a table or column destroys its data. Restore from the backup
in step 5 if the data matters.

**Connection errors**

| Error | Cause | Fix |
|---|---|---|
| `Network is unreachable` with an IPv6 address | You used the *Direct connection* host | Use the Session pooler string |
| `Tenant or user not found` | Username missing the project suffix | It must be `postgres.<project-ref>` |
| `password authentication failed` | Wrong password | Retype it, or reset it in Supabase |
| `flag needs an argument: 'e'` | The command was split across lines | Paste it as one line |

---

## Rules to keep

- Do not paste the database password into chat, tickets or commits. Use `read -s`.
- Do not point your local `.env` at Supabase. `make test` and `make bootstrap`
  would then run against it. Pass the URL per command, as above.
- At least two people must be able to do this procedure and reach the password
  (the project's "no single point of failure" rule in `CLAUDE.md`).
