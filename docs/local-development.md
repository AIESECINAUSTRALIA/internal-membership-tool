# Local Development

> One-time project scaffolding is recorded in
> `docs/superpowers/specs/2026-09-02-project-skeleton-design.md` §12 (setup
> runbook). This page is the day-to-day reference: **how to run the app**, and
> **how environment variables and secrets are managed**.

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

`VITE_API_URL` in `.env` (default `http://localhost:8000`) points the browser app
at the API. Other commands: `npm run test`, `npm run lint`, `npm run build`.

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
- **Supabase vars** (`SUPABASE_*`, `VITE_SUPABASE_*`) — real values. Get them
  from the shared store (below), not by asking in Slack.

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

### Deployed environments

Real secrets are **never** stored in a file in a deployed environment. Each
platform holds its own copy, set through its dashboard:

| Environment | Where secrets are set |
|---|---|
| Frontend hosting (Vercel, per `external-services.md`) | Project → Settings → Environment Variables, set separately for Preview and Production |
| Backend hosting (not yet chosen) | that platform's env-var configuration |
| Supabase | project settings (the origin of the keys) |
| GitHub Actions CI | repo → Settings → Secrets and variables → Actions, referenced as `${{ secrets.NAME }}` |

Local, Preview, and Production each use **different** values (different Supabase
projects / databases). Never point local dev at production.

The current `backend` CI workflow starts its own throwaway Postgres and needs
**no** real secrets. Add GitHub Actions secrets only when a workflow genuinely
requires one.

### Rotation (turnover)

The governing constraint for this project is annual turnover. When someone with
access to these secrets leaves:

1. Rotate the Supabase keys (anon key, service-role key) and the database
   password in the Supabase dashboard.
2. Update the new values in Bitwarden and in every deployed environment's
   configuration.
3. Remove the departing person's Bitwarden and platform access.

Rotate immediately, out of cycle, if a secret is ever committed, pasted into a
chat or ticket, or otherwise exposed.
