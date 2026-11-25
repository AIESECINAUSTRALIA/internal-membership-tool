# Local Development

The day-to-day reference: **how to run the app**, and **how environment variables
and secrets are managed**.

---

## Running the app

Two ways to run the stack locally:

- **Docker (recommended)** — one prerequisite, one command. This is what
  onboarding and CI-parity assume.
- **Manual / native** — run Postgres, the API, and the frontend as separate
  processes on your machine. Faster inner loop when you're deep in one service;
  more to install and keep track of.

Every path needs the `.env` file first — `cp .env.example .env` (see
[Environment variables & secrets](#environment-variables--secrets)).

> **Authentication (DEV-82 / DEV-83).** Sign-in uses EXPA OAuth and server-side
> sessions. The backend handles the OAuth exchange; the frontend uses the
> backend's HttpOnly session cookie.
>
> Backend configuration uses `EXPA_AUTH_URL`, `EXPA_GRAPHQL_URL`,
> `EXPA_CLIENT_ID`, `EXPA_CLIENT_SECRET`, `APP_BASE_URL`,
> `SESSION_TTL_HOURS` and `ALLOWED_EMAIL_DOMAINS`. The frontend's
> `VITE_AUTH_MODE` chooses between development sign-in (`mock`) and real
> EXPA sign-in (`expa`).
>
> Backend tests mock EXPA and require no real OAuth credentials. The frontend's
> mock mode also needs no credentials or running backend.
> Live EXPA authentication requires an HTTPS callback registered
> with EXPA and matching deployment configuration. See `docs/auth.md`.

### Prerequisites

| | Docker path | Manual path |
|---|---|---|
| Docker Desktop (or Colima / Podman) | required | only if you use it for Postgres |
| `uv` | — | required (it fetches Python 3.12 itself) |
| Node 22 via `nvm` (see `.nvmrc`) | — | required |
| PostgreSQL 16 | — | required — a local install, or the `db` container |

### Docker path

```bash
cp .env.example .env      # first time only
make bootstrap            # build images, start db + backend + frontend, run migrations + seed
```

Everyday commands after that:

| Command | Does |
|---|---|
| `make up` | start the stack in the foreground (logs stream; Ctrl-C stops) |
| `make down` | stop and remove the containers |
| `make logs` | tail all logs |
| `make migrate` | apply migrations |
| `make migration name="add teams"` | autogenerate a migration from model changes |
| `make seed` | load placeholder lookup data |
| `make test` / `make test-backend` / `make test-frontend` | run test suites |
| `make lint` | pre-commit hooks + `mypy` |
| `make format` | auto-fix ruff + eslint |
| `make shell-backend` | shell inside the backend container |
| `make psql` | `psql` into the database |

URLs: frontend **http://localhost:5173**, API **http://localhost:8000**, Postgres
**localhost:5433** (host port remapped so it doesn't clash with a local Postgres
on 5432; inside the compose network it is still `db:5432`).

Reset everything, including the database volume:

```bash
docker compose down -v && make bootstrap
```

You can also drive the stack from **Docker Desktop → Containers →
`internal-membership-tool`** — start/stop buttons for the whole project, and
per-container **Logs / Exec / Files** tabs.

### Manual path (no Docker for the app)

Three processes — use three terminals, or background the first two.

**1. PostgreSQL.** Either start just the DB container:

```bash
docker compose up -d db          # Postgres on localhost:5433
```

…or use a locally-installed Postgres 16, creating the database and role once:

```bash
createdb membership
psql -d membership -c "CREATE ROLE membership LOGIN PASSWORD 'localdevpassword';"
psql -d membership -c "GRANT ALL ON DATABASE membership TO membership;"
```

Use the matching port in `DATABASE_URL` below: **5433** for the container, **5432**
for a local install.

**2. Backend API** — from `backend/`:

```bash
cd backend
uv sync                          # create .venv, install deps

# point at your local DB (host/port from step 1); an inline value is NOT
# overridden by --env-file, so the root .env supplies only the other vars
export DATABASE_URL='postgresql+psycopg://membership:localdevpassword@localhost:5433/membership'

uv run alembic upgrade head      # apply migrations (run from inside backend/)
uv run --env-file ../.env uvicorn app.main:app --reload --port 8000
```

- Serves at http://localhost:8000. Until `app/main.py` is implemented (Step 7) it
  exits with `Error loading ASGI app` — expected.
- Without Docker, tests and checks are just `uv run pytest`,
  `uv run ruff check .`, `uv run mypy app`.

**3. Frontend** — from `frontend/`:

```bash
cd frontend
nvm use                          # reads .nvmrc -> Node 22
npm ci                           # first time / after dependency changes
npm run dev                      # http://localhost:5173
```

The frontend calls the API at the relative path `/api`. Vite's development proxy
forwards those requests to `http://localhost:8000` by default, so the browser
doesn't need to know where the backend runs.

When the frontend runs in Docker, `docker-compose.yml` sets
`API_PROXY_TARGET=http://backend:8000` instead (the backend's service name on
the compose network). The browser still sees `http://localhost:5173/api`.

For a native frontend talking to a backend on a different address or port,
set `API_PROXY_TARGET` in the shell before starting Vite. It is a development
server setting, not a `VITE_` variable: it is never exposed to the browser
or included in the production build.

Other commands: `npm run test`, `npm run lint`, `npm run build`.

### Which one?

- **Just want it running / onboarding / match CI:** Docker path.
- **Iterating hard on the backend** (debugger, fast restarts): Postgres via
  `docker compose up -d db`, backend manual, frontend either way.
- **Iterating on the frontend only:** Docker for `db` + `backend`, `npm run dev`
  native (Vite HMR is snappier outside the container).

### Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop / Colima isn't running — start it. |
| `Bind for 0.0.0.0:5433 failed: port is already allocated` | Something else on 5433 — change the host port in `docker-compose.yml` (e.g. `"5434:5432"`). |
| Compose warns `The "POSTGRES_USER" variable is not set` | No `.env` — run `cp .env.example .env`. |
| `backend` shows **Up** in `docker compose ps` but `curl localhost:8000` is refused | Expected until Step 7. uvicorn `--reload` keeps the container alive; `make logs` shows `Error loading ASGI app`. |
| `make test-backend` → `make: *** [test-backend] Error 5` | No backend tests yet (`tests/` are empty). Clears in Step 7. |
| Native backend: `connection refused` to the DB | Wrong port in `DATABASE_URL` — `5433` for the `db` container, `5432` for a local Postgres. |
| Native `alembic`: `ModuleNotFoundError: No module named 'app'` | Run it from inside `backend/` (so `prepend_sys_path = .` applies), via `uv run`. |

---

## Environment variables & secrets

### The two files

| File | Committed? | Purpose |
|---|---|---|
| `.env.example` | **yes** | Template. Lists every variable the app reads, with safe placeholder values. The source of truth for *what* configuration exists. |
| `.env` | **no** — git-ignored | Your real local values. Created by copying `.env.example`. Never committed. |

`.gitignore` enforces this (`.env` and `.env.*` ignored, `.env.example`
explicitly re-included). Do not change those rules.

**Rule:** when you add or rename a variable the code reads, update
`.env.example` in the same commit. A missing entry there means the next
person's app breaks with no clue why.

### First-time local setup

```bash
cp .env.example .env
```

Then fill in `.env`:

- **Postgres vars** (`POSTGRES_*`, `DATABASE_URL`) — leave the placeholder
  values as-is. The local database is a throwaway Docker container; these are
  not secrets.
- **Backend sign-in settings** (`APP_BASE_URL`, `FRONTEND_ORIGIN`,
  `SESSION_TTL_HOURS`, `ALLOWED_EMAIL_DOMAINS`) — leave the local defaults
  as-is for ordinary development. `APP_BASE_URL` determines the OAuth callback
  URL and whether cookies are marked Secure; `FRONTEND_ORIGIN` is where the
  browser lands after sign-in. See [`docs/auth.md`](auth.md) for the full list
  and what each setting does.
- **Frontend sign-in mode** (`VITE_AUTH_MODE`) — leave it at `mock` to use
  the development sign-in with no EXPA credentials at all. Set it to `expa`
  for real EXPA sign-in; that needs the one-time setup in
  [`docs/auth.md`](auth.md), including a registered HTTPS callback URL.
  The default local HTTP stack is not enough for live EXPA sign-in.

### Where the real values live

Per `docs/external-services.md`, the org's secret store is **Bitwarden**, with
access granted by role via the MC.

- Dev / staging Supabase keys for this project live in a **shared Bitwarden
  collection** scoped to the dev team.
- A new contributor gets Bitwarden access when they join, opens that
  collection, and copies the values into their local `.env`.
- Never paste secret values into Slack, Jira, PR descriptions, commit
  messages, or screenshots. If one leaks there, rotate it (see below).

### How each run mode reads `.env`

- **`docker compose` / `make`:** compose reads the root `.env` automatically —
  for `${VAR}` substitution in `docker-compose.yml`, and (via `env_file: .env`)
  for injecting variables into the `backend` container. `DATABASE_URL` in
  `.env.example` uses host `db:5432` for exactly this; leave it.
- **Native:** the backend process does **not** pick up the root `.env` on its
  own — pass it with `uv run --env-file ../.env`, and override `DATABASE_URL` to
  a `localhost` host/port (an inline or exported value wins over `--env-file`).
  Full steps in [Running the app → Manual path](#manual-path-no-docker-for-the-app).
- **Native frontend:** Vite runs from `frontend/` and does not automatically
  read the repository-root `.env`. The default sign-in mode is `mock`.
  To override `VITE_AUTH_MODE` or the development server's `API_PROXY_TARGET`,
  set the variable in the shell running Vite. Restart the dev server after
  changing it.

### Deployed environments

> **Changing.** Deployment is moving to Google Cloud (decided 2026-11-09; design:
> `docs/superpowers/specs/2026-11-09-gcp-deployment-design.md`). The table below is the
> target. Supabase and Vercel are being retired and should not get new secrets.

Real secrets are **never** stored in a file in a deployed environment:

| Where | Where secrets are set |
|---|---|
| Backend (Cloud Run, dev and prod) | **GCP Secret Manager**, one set per environment: `database-url-app`, `database-url-migrator`, `expa-client-secret`. Mounted into Cloud Run as environment variables. Non-secret settings (`EXPA_AUTH_URL`, `APP_BASE_URL`, …) are plain Cloud Run env vars |
| Frontend (Firebase Hosting) | **No secrets.** The frontend calls the API at the relative path `/api`, so one build works in both environments |
| GitHub Actions | **No GCP secrets.** Workflows sign in to GCP with Workload Identity Federation. Only non-secret *variables* (project IDs, region, WIF provider) live under repo → Settings → Secrets and variables → Actions → Variables |
| EXPA developer apps | the shared MC EXPA developer account (the origin of the client ids and secrets) |

Local, dev and prod each use **different** values: different databases and different EXPA
apps (dev uses EXPA staging). Never point local dev at prod.

### Sign-in placeholder in deployed environments

Spec §2A.3: the development sign-in (the plain "Sign in" button and `?as=` personas) must
be **off in every deployed environment**.

How it's enforced:

- **Frontend:** a production build (`npm run build`, which produces the files
  served by Firebase Hosting) always uses real EXPA sign-in
  (`frontend/src/api/authMode.ts`). Even setting `VITE_AUTH_MODE=mock` explicitly
  cannot turn on the development sign-in in a production build. The dev server
  and tests default to `mock`; they can opt into `expa` for real sign-in.
- **Backend:** there is no sign-in stub. Every protected API request needs a
  valid server-side session, established after a successful EXPA sign-in.
  The backend checks the EXPA account's email against `ALLOWED_EMAIL_DOMAINS`
  and requires an active membership before issuing a session. The browser
  sends the HttpOnly `__session` cookie with subsequent API requests.
- **Hosting:** Firebase Hosting serves the frontend and forwards `/api/**`
  to Cloud Run, so the frontend and API share one origin. The frontend uses
  relative API URLs with `credentials: 'same-origin'`. There is no frontend
  API hostname or OAuth client secret to configure. The same production build
  can be used on both dev and prod.
- The mock lives only in the browser and cannot create a valid backend session,
  so even a wrongly configured frontend can't get real access with it.

Details: [`docs/auth.md`](auth.md).

The current `backend` CI workflow starts its own throwaway Postgres and needs
**no** real secrets. Add GitHub Actions secrets only when a workflow genuinely
requires one.

### Rotation (turnover)

The governing constraint for this project is annual turnover. When someone with
access to these secrets leaves:

1. Remove the person from the Google Workspace groups (this removes all their GCP
   access), from GitHub teams and from the Bitwarden collection.
2. If they could read prod secrets (`mt-tech-leads@`): rotate the prod database
   passwords and the EXPA prod client secret. Add a new version in Secret Manager,
   then redeploy the Cloud Run service so it picks up the new version.
3. If they knew a shared login (hello email, the MC EXPA developer account): change
   it.
4. Update the new values in Bitwarden.

The full offboarding checklist will live in `docs/access-and-ownership.md` (being
written; until then see §10 of the GCP design doc). Until Supabase is retired, also
rotate its keys if the person had them.

Rotate immediately, out of cycle, if a secret is ever committed, pasted into a
chat or ticket, or otherwise exposed.

---

## Using the real backend for Profile

Profile's custom fields (`getMyCustomFields`, `updateMyCustomFields`) come from the real
API whenever you sign in for real (`VITE_AUTH_MODE=expa`). In `mock` mode they come
from the mock like everything else (`docs/frontend.md`).

Live EXPA sign-in requires a configured HTTPS environment and a callback URL
registered with EXPA. The default local HTTP stack does not meet that requirement.
Use the development sign-in for ordinary local frontend work.

1. Set up real sign-in once: `docs/auth.md`, "EXPA backend setup". Use a
   development environment with the registered HTTPS callback, never prod.

2. The seeds don't create people, LCs or terms, so add yourself once, with the
   `@aiesec.net` email you sign in with:

   ```bash
   docker compose exec db psql -U membership -d membership -c "
     INSERT INTO lc (name, type, active) VALUES ('Dev LC', 'LC', true);
     INSERT INTO term (name, start_date, end_date) VALUES ('Dev term', '2026-01-01', '2026-12-31');
     INSERT INTO person (full_name, aiesec_email, join_date, status, timezone)
       VALUES ('Your Name', 'you@aiesec.net', '2026-01-01', 'ACTIVE', 'Australia/Melbourne');
     INSERT INTO membership (person_id, lc_id, position_id, term_id, start_date, end_date, is_primary)
       SELECT p.id, l.id, pos.id, t.id, '2026-01-01', '2026-12-31', true
       FROM person p, lc l, position pos, term t
       WHERE p.aiesec_email = 'you@aiesec.net' AND l.name = 'Dev LC'
         AND pos.key = 'member' AND t.name = 'Dev term';"
   ```

   Make sure the membership dates cover today, or sign-in will be refused
   with the not-allocated message.
3. `make seed` (if you haven't) so there are custom fields to edit, then restart:
   `make down && make up`. Vite reads env vars only at startup.
4. Sign in with EXPA. Profile now shows and saves your real fields.
