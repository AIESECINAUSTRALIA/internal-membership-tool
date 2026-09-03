# Project Skeleton — Design Spec

Status: draft for review · Owner: Tech Lead · Ticket: DEV-0015 · Date: 2026-09-02

## 1. Goal

Stand up a runnable, empty-but-correct project skeleton for the Membership / Data
Management Platform: a Python API, a React frontend, and a Postgres database, wired
together so that a new contributor can go from `git clone` to a running stack with
**one prerequisite and one command**, and so that the first feature work has an
obvious place to land.

This is the **architectural** groundwork only. It deliberately builds no product
features — the requirements spec (`docs/membership-tool-requirements-spec.md`) has
open `TODO:` items that block the real schema, the permission-matrix seed, and the
report layouts. Those are called out in §9.

### Success criteria

- `docker compose up` (via `make bootstrap` on first run) brings up Postgres +
  API + frontend; `GET /healthz` returns ok; the frontend renders a login screen.
- `make test` runs and passes backend (`pytest`) and frontend (`vitest`) suites.
- `make lint` is clean; CI runs the same checks on every PR.
- A new contributor needs only **Docker** installed. Native toolchains (uv, Node)
  are optional and documented for a faster inner loop.
- Every table in requirements spec §4 has a model stub and exists in the first
  migration, so the schema has a home without being prematurely finalised.
- `docs/architecture.md` and `docs/local-development.md` let a zero-context reader
  understand the layout and run the app.

## 2. Decisions

| Area | Decision | Rationale |
|---|---|---|
| Backend framework | **FastAPI** + Pydantic | Minimal boilerplate, auto OpenAPI docs, large community; natural fit for a JSON API behind a React SPA. |
| ORM / migrations | **SQLAlchemy 2.0 + Alembic** | Real SQL for the spec's joins, rollups, and reports; versioned migration files committed to the repo. |
| DB driver | **psycopg 3** (`psycopg[binary]`) | Current standard driver; URL scheme `postgresql+psycopg://`. |
| DB connection | Direct Postgres connection string | Supabase Auth handles OAuth; the database is just Postgres. |
| Python tooling | **uv** (`pyproject.toml` + `uv.lock`) | One fast tool for venv + resolution + lockfile; `uv sync` onboarding. |
| Python version | **3.12** | Ecosystem stability over bleeding edge. |
| Frontend build | **Vite + React + TypeScript** SPA | Boring, fast, well documented; SPA is sufficient for an internal dashboard. |
| Frontend routing | **react-router-dom** | The standard client router. |
| Frontend auth client | **@supabase/supabase-js** (auth only) | Managed OAuth per `CLAUDE.md`; no custom auth. |
| Node version | **22 LTS** | Current LTS. |
| Repo layout | **Monorepo** — `backend/` + `frontend/` in this repo | One set of issues/PRs/CI; smaller turnover handover surface. |
| Local dev | **Full stack in Docker Compose** | Docker is the only prerequisite; onboarding is two lines that don't rot per-OS. |
| Command layer | **Makefile** (single source of truth) + **pre-commit** | Raw `docker compose run …` incantations live once, in the Makefile; docs reference `make <target>`, never copy commands. |
| CI | GitHub Actions, one workflow per sub-project | Path-filtered so backend/frontend checks run independently. |

## 3. Repository structure

```
internal-membership-tool/
├── CLAUDE.md
├── README.md
├── .gitignore
├── .env.example                  # every var the stack reads, dummy values
├── docker-compose.yml            # db + backend + frontend
├── Makefile                      # self-documenting; single source for commands
├── .pre-commit-config.yaml
├── .github/
│   └── workflows/
│       ├── backend.yml           # ruff + ruff format --check + mypy + pytest
│       └── frontend.yml          # eslint + tsc --noEmit + vitest
├── docs/
│   ├── external-services.md      # (exists)
│   ├── membership-tool-requirements-spec.md   # (exists)
│   ├── architecture.md           # NEW — how the pieces fit, for a zero-context reader
│   ├── local-development.md      # NEW — clone → running app; references make targets
│   └── superpowers/specs/2026-09-02-project-skeleton-design.md   # this file
├── backend/
└── frontend/
```

### 3.1 `backend/`

```
backend/
├── pyproject.toml                # deps + [tool.ruff] / [tool.mypy] / [tool.pytest.ini_options]
├── uv.lock
├── .python-version               # 3.12
├── Dockerfile
├── alembic.ini
├── migrations/                   # Alembic — committed
│   ├── env.py                    # reads DATABASE_URL; target_metadata = Base.metadata
│   └── versions/
│       └── 0001_initial_schema.py
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI app factory, router registration, CORS
│   ├── config.py                # Pydantic Settings; reads env, fails loud on missing
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py              # DeclarativeBase + model import registry
│   │   └── session.py          # engine + get_db() dependency
│   ├── models/                  # SQLAlchemy ORM stubs — columns from spec §4, no logic
│   │   ├── __init__.py
│   │   ├── org.py              # lc, term, position, function
│   │   ├── person.py           # person
│   │   ├── membership.py       # membership, team, team_member
│   │   ├── permission.py       # permission_matrix
│   │   ├── attribute.py        # attribute, attribute_value        (spec §4.2)
│   │   ├── kpi.py              # kpi_record                         (spec §4.3)
│   │   └── privacy.py          # deletion_request, audit_log        (spec §4.5, §8.4)
│   ├── schemas/                 # Pydantic request/response models
│   │   ├── __init__.py
│   │   └── health.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py             # get_db, get_current_person, require_person
│   │   ├── router.py           # aggregates v1
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── health.py       # GET /healthz  — the only real endpoint
│   │       ├── auth.py         # GET /auth/me  — resolves token → person or 403
│   │       └── people.py       # one stub CRUD route showing the permission pattern
│   ├── core/
│   │   ├── __init__.py
│   │   ├── permissions.py      # matrix resolution (spec §3.2) — data-driven, tested
│   │   └── audit.py            # append-only audit_log writer (spec §8.4) — stub
│   └── seeds/
│       ├── __init__.py
│       └── seed_lookups.py     # placeholder positions / functions / terms
└── tests/
    ├── __init__.py
    ├── conftest.py             # transactional test DB fixture (rollback per test)
    ├── test_health.py
    └── test_permissions.py     # resolver against seeded matrix + membership rows
```

Model files contain table classes with the columns named in requirements spec §4 and
foreign keys between them — **no business logic, no methods**. This gives the schema a
concrete home and lets `0001_initial_schema` be generated, without pretending the data
model is final (it is not; see §9).

### 3.2 `frontend/`

```
frontend/
├── package.json                 # deps + scripts (single source for FE commands)
├── package-lock.json
├── Dockerfile
├── vite.config.ts               # + vitest config
├── tsconfig.json / tsconfig.node.json
├── eslint.config.js
├── index.html
├── public/
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── vite-env.d.ts
    ├── lib/
    │   ├── api.ts              # typed fetch wrapper; base URL from env; attaches token
    │   └── supabase.ts         # Supabase client — auth only
    ├── auth/
    │   ├── AuthProvider.tsx    # session context from Supabase Auth
    │   └── useAuth.ts
    ├── routes/
    │   ├── router.tsx          # react-router setup
    │   ├── Login.tsx           # Google OAuth button (spec §9)
    │   ├── Dashboard.tsx       # placeholder shell behind auth
    │   └── NotAuthorised.tsx   # "ask your VP to be added" (spec §9)
    ├── components/
    │   └── ProtectedRoute.tsx
    └── test/
        ├── setup.ts
        └── App.test.tsx
```

## 4. Docker Compose

Three services. Source is bind-mounted so hot-reload works inside the containers;
dependency directories (`.venv`, `node_modules`) are kept off the mount so the host
does not shadow them.

| Service | Image / build | Ports | Notes |
|---|---|---|---|
| `db` | `postgres:16` | `5432:5432` | Named volume `pgdata`; healthcheck `pg_isready`. Port exposed so native dev can connect too. |
| `backend` | build `./backend` | `8000:8000` | `depends_on: db (service_healthy)`. Command: `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`. Venv baked at `/opt/venv` (via `UV_PROJECT_ENVIRONMENT`), outside the bind mount. |
| `frontend` | build `./frontend` | `5173:5173` | Command: `npm run dev -- --host 0.0.0.0`. `node_modules` as an anonymous volume over the bind mount. |

- **Migrations are not auto-run on start** — they are explicit (`make migrate`), so
  startup has no hidden magic. First-run ordering is handled by `make bootstrap`
  (`up -d` → wait for healthy → `migrate` → `seed`).
- `DATABASE_URL` inside Compose uses host `db`; native dev overrides it to
  `localhost` (documented in `.env.example` and `local-development.md`).

### Dockerfiles

- **backend**: `python:3.12-slim`; install `uv` (copied from the official
  `ghcr.io/astral-sh/uv` image); `uv sync --frozen`; non-root user; default command
  runs uvicorn with `--reload` for dev.
- **frontend**: `node:22-alpine`; `npm ci`; default command runs the Vite dev server.
- Both are **dev-oriented**. Production images are out of scope (§9 — deployment
  target undecided).

## 5. Command layer

### 5.1 Makefile (self-documenting via `##` comments; `make help` lists targets)

| Target | Action |
|---|---|
| `help` | Print target list. Default goal. |
| `bootstrap` | First-time setup: build, `up -d`, wait for `db` healthy, `migrate`, `seed`. |
| `up` / `down` / `logs` / `ps` | `docker compose` lifecycle passthroughs. |
| `migrate` | `docker compose run --rm backend uv run alembic upgrade head` |
| `migration name=...` | `… alembic revision --autogenerate -m "$(name)"` |
| `seed` | `… uv run python -m app.seeds.seed_lookups` |
| `test` | `test-backend` + `test-frontend` |
| `test-backend` | `docker compose run --rm backend uv run pytest` |
| `test-frontend` | `docker compose run --rm frontend npm run test` |
| `lint` | `pre-commit run --all-files` + `… uv run mypy app` |
| `format` | `… uv run ruff format .` + `… uv run ruff check --fix .` + `… npm run lint -- --fix` |
| `shell-backend` | Interactive shell in the backend container. |
| `psql` | `psql` into `db`. |

`docs/local-development.md` refers to these targets and explains the workflow; it
does **not** reproduce the underlying commands, so there is one source of truth.

### 5.2 pre-commit (`.pre-commit-config.yaml`)

Runs on commit and in CI:

- `ruff` (lint) and `ruff-format` on `backend/`
- `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-json`,
  `check-added-large-files`
- local `eslint` hook scoped to `frontend/`

`mypy` and `vitest`/`pytest` are **CI + `make` only** (too slow / dependency-heavy
for a commit hook), but `make lint` includes `mypy`.

## 6. CI (GitHub Actions)

- **`backend.yml`** — triggers on push / PR touching `backend/**` or the workflow:
  set up `uv`; `uv sync --frozen`; `uv run ruff check`; `uv run ruff format --check`;
  `uv run mypy app`; start a `postgres:16` service container; `uv run alembic upgrade
  head`; `uv run pytest`.
- **`frontend.yml`** — triggers on push / PR touching `frontend/**` or the workflow:
  set up Node 22; `npm ci`; `npm run lint`; `npx tsc --noEmit`; `npm run test`.

Branch protection wiring (require checks green) is an org setting, noted for the Tech
Lead, not done by this ticket.

## 7. Environment variables

Single root `.env`, git-ignored; **`.env.example` (committed) is the authoritative
list** — this spec does not copy its contents (that only drifts). Groups:
Postgres (`POSTGRES_*`, `DATABASE_URL`), Supabase auth (`SUPABASE_*`), CORS
(`FRONTEND_ORIGIN`), frontend (`VITE_*`).

- Compose reads the root `.env` for `${VAR}` substitution and injects it into the
  `backend` container via `env_file`. `DATABASE_URL` uses host `db:5432` inside
  the compose network.
- Native dev overrides `DATABASE_URL` to a `localhost` host/port.
- Management (Bitwarden, deployed-env dashboards, rotation) is documented in
  `docs/local-development.md` → "Environment variables & secrets".

## 8. Behaviour the skeleton actually implements

1. **Health** — `GET /healthz` → `{"status": "ok"}`; opens a DB session and runs
   `SELECT 1` so it also proves DB connectivity.
2. **Auth dependency** (`app/api/deps.py`) — `get_current_person`: read the
   `Authorization: Bearer` token, `jwt.decode(token, SUPABASE_JWT_SECRET,
   algorithms=["HS256"], audience="authenticated")`, take the email claim, look up
   `person` by `aiesec_email`. Returns `Person | None`. `require_person` raises
   `403` with the "ask your VP to be added" message when `None` (spec §9).
3. **`GET /auth/me`** — returns the resolved person and their active memberships, or
   `403`. Demonstrates the pattern; not a full profile endpoint.
4. **Permission resolver** (`app/core/permissions.py`) — `resolve_scope(session,
   person_id, resource, action) -> Scope | None` implementing requirements spec
   §3.2: load active memberships (date-bounded), match `permission_matrix` rows by
   `position` and (`function` or wildcard), return the **widest** `max_scope` under
   the ordering `own < team < function < lc < all`; `None` if no row matches
   (deny by default). Covered by `tests/test_permissions.py` against seeded rows.
5. **One stub CRUD route** (`app/api/v1/people.py`) — `GET /people` wired through
   `require_person` + a `resolve_scope` check, returning an empty list. Exists to
   show where and how feature routes plug in; not a real endpoint.
6. **Frontend** — Supabase `AuthProvider`, a `Login` route with a Google OAuth
   button, a `ProtectedRoute` guarding a placeholder `Dashboard`, and a
   `NotAuthorised` route. `lib/api.ts` attaches the access token to requests.
7. **Seed script** — inserts a handful of clearly-placeholder `position`,
   `function`, and `term` rows so the resolver test and local clicking-around have
   data. Not the real lookup values (spec §12 item 1).

## 9. Out of scope / open items

**Not built by this ticket:**

- Any real endpoint beyond health, `/auth/me`, and the one stub CRUD route.
- Dashboards, reporting, CSV import, deletion/anonymisation workflow, audit-log
  writes beyond the stub writer.
- Production Docker images and backend deployment config — the backend host is
  undecided (`external-services.md` currently lists Vercel for the frontend only).
- Branch-protection / required-checks configuration (org setting).

**Blocked on requirements-spec `TODO:`s (design-ready, not built):**

- Final schema. Model stubs use the columns in spec §4, but the authoritative
  **positions/functions** list, the **KPI catalog**, and the **NAMs/SONA/MTR**
  report fields are all open (`spec §12`, items 1–4). The first migration will need
  revising once those land — expected and acceptable for a skeleton.
- Real **permission-matrix seed** — needs Tech Lead + LCP review (spec §3.3). The
  skeleton ships only placeholder rows for tests.
- **Auth end-to-end** needs a real Supabase project with Google OAuth configured
  and the official email domains confirmed (spec §9, §12 item 7). The skeleton
  wires the client and verifies tokens; the full login loop depends on that
  project existing.

## 10. Verification

The skeleton is done when, from a clean checkout with only Docker installed:

- [ ] `make bootstrap` brings `db`, `backend`, `frontend` all healthy.
- [ ] `curl localhost:8000/healthz` → `{"status":"ok"}`.
- [ ] `localhost:5173` renders the login screen.
- [ ] `make test` — backend and frontend suites pass (health test, permission
      resolver test, frontend render test).
- [ ] `make lint` is clean.
- [ ] `docker compose down -v && make bootstrap` reproduces the running stack.
- [ ] CI (both workflows) is green on the PR.
- [ ] `docs/architecture.md` and `docs/local-development.md` are present and
      accurate against the tree that was built.

## 11. Generation commands

Moved into §12 (the setup runbook), which records the exact commands actually run
and their outcomes. This section previously duplicated them.

## 12. Setup runbook

> Live status of the skeleton build. Steps 1–2 are complete; Step 3 onward
> remain. This section supersedes the earlier draft step list.

### Step 1 — Backend scaffold — done

- `uv` project at `backend/`; Python pinned to **3.12** (`.python-version`,
  `requires-python = ">=3.12"`; `uv add` initially picked up a conda 3.14
  interpreter — fixed with `uv python pin 3.12` + rebuilt `.venv`).
- Runtime deps: fastapi, `uvicorn[standard]`, sqlalchemy, `psycopg[binary]`,
  alembic, pydantic, pydantic-settings, pyjwt, python-multipart.
  Dev deps: pytest, pytest-asyncio, httpx, ruff, mypy.
- `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.mypy]`, `[tool.pytest.ini_options]`
  added to `backend/pyproject.toml`.
- `alembic init migrations` run. `migrations/env.py` wired: reads `DATABASE_URL`
  from the environment (falls back to `alembic.ini` only if unset), imports
  `app.db.base.Base` and `app.models`, sets `target_metadata = Base.metadata`.
- `app/db/base.py` holds the `DeclarativeBase`.
- Every other `app/**` and `tests/**` module exists as an **empty stub**.
  Application code is Step 7 — the backend is wired, not implemented.

### Step 2 — Frontend scaffold — done

Both fixes below are applied. `npm run lint`, `npx tsc --noEmit`, and
`npm run test` (1 test) all pass under Node 22.

Created with `npm create vite@latest frontend -- --template react-ts`
(**ESLint**, not Oxlint). Added `react-router-dom`, `@supabase/supabase-js`, and
dev deps `vitest @testing-library/react @testing-library/dom
@testing-library/jest-dom jsdom`. Created `src/{lib,auth,routes,components,test}`.
Added `test` / `test:watch` scripts. `src/test/setup.ts` contains
`import '@testing-library/jest-dom/vitest'`.

Stack as scaffolded: Vite 8, React 19, TypeScript 6, ESLint 10, Vitest 4,
react-router 7, supabase-js 2.

Two corrections to the generated files (see the files for current content):

- **`frontend/vite.config.ts`** — `defineConfig` imported from `vitest/config`,
  not `vite` (the `vite` one rejects the `test` key and breaks `tsc` / CI);
  `globals: true` dropped in favour of explicit `vitest` imports in tests.
- **`frontend/src/test/App.test.tsx`** — a smoke test so the suite (and CI) has
  something to run.

Verify: `cd frontend && npm run lint && npx tsc --noEmit && npm run test` — all
three pass.

Optional: the scaffold pulled `@types/node` ^24; pin to `^22` to match the
runtime (`npm i -D @types/node@^22`).

### Step 3 — Node version pinning — done

`.nvmrc` (`22`), `frontend/.npmrc` (`engine-strict=true`), and the `engines` key
in `frontend/package.json` are in place; `nvm use` resolves to Node 22 and
`npm ci` passes the engine gate under it.

Node **22.x** (Active LTS "Jod", supported to Apr 2027) with the npm 10.x bundled
in it — do not pin npm separately.

**`.nvmrc`** (repo root):

```
22
```

**`frontend/.npmrc`**:

```
engine-strict=true
```

**`frontend/package.json`** — add a top-level key:

```json
"engines": { "node": "22.x", "npm": ">=10 <11" }
```

Major-only (`22`) so security patches flow in without a repo change;
`package-lock.json` already gives dependency reproducibility. The version is named
in four places — `.nvmrc`, `engines`, `frontend/Dockerfile`, CI (via `.nvmrc`) —
change them together on a future bump. Note this in `docs/local-development.md`.

### Step 4 — Root & Docker files — done

All files below are created. The files themselves are the source of truth — this
runbook lists what was created, not their contents.

| File | Purpose |
|---|---|
| `.env.example` (root) | committed template; see §7 |
| `backend/.dockerignore` | keep `.venv` / caches out of the build context |
| `frontend/.dockerignore` | keep `node_modules` / `dist` out of the build context |
| `docker-compose.yml` (root) | `db` + `backend` + `frontend`; `db` host port **5433→5432** (a local Postgres already held 5432); frontend gets only the `VITE_*` vars |
| `backend/Dockerfile` | `python:3.12-slim` + `uv`; venv baked at `/opt/venv`, outside the bind mount |
| `frontend/Dockerfile` | `node:22-alpine`; `npm ci`; Vite dev server on `0.0.0.0` |
| `Makefile` (root) | self-documenting (`make help`); recipe lines use real tabs; `bootstrap` calls the `migrate` + `seed` targets rather than restating them; `psql` wrapped in `sh -c` so the vars resolve in-container |

Verified: `make help` renders the target list; `docker compose config` validates.

**Hardening TODO (not done):** the `backend` image runs as root — add a
non-root `USER` before any non-local deployment.

### Step 5 — First run — done

```bash
cp .env.example .env
make bootstrap
```

Ran on 2026-09-03. A local Postgres was already on port 5432, so the `db`
service's host port was remapped to **5433** in `docker-compose.yml` (container
port unchanged; `DATABASE_URL` still uses `db:5432` inside the compose network).
Both images build; `alembic upgrade head` created `alembic_version` and applied
nothing (no migrations yet); the seed step is a no-op (empty module).

Observed results, before the backend application code exists:

| Check | Result | Reason |
|---|---|---|
| `db` container | Up (healthy), `5433->5432` | — |
| `frontend` at `localhost:5173` | HTTP 200, Vite default page | dev server needs no app code |
| `db` tables (`make psql` → `\dt`) | only `alembic_version` | no migrations written yet |
| `backend` container | shows **Up** but not serving | uvicorn `--reload` keeps the reloader process alive; logs show `Error loading ASGI app. Attribute "app" not found in module "app.main"` |
| `curl localhost:8000/healthz` | connection refused (HTTP 000) | nothing bound on 8000 |
| `make test-backend` | `make: *** [test-backend] Error 5` — "no tests ran" | `tests/` are empty stubs |
| `make test-frontend` | 1 passed | the Step 2 smoke test, run in the frontend container |

None of the failures are configuration errors; they clear as Step 7 lands. Note
the `backend` row: `docker compose ps` / Docker Desktop show it green — trust the
**logs**, not the status, until `app/main.py` exists.

### Step 6 — pre-commit + CI — done

- `.github/workflows/backend.yml` and `frontend.yml` created (both parse; jobs
  run on `pull_request` and `push` to `main`, path-filtered).
- `.pre-commit-config.yaml` created; `pre-commit autoupdate` pinned
  ruff-pre-commit `v0.16.5` and pre-commit-hooks `v6.0.0`. `pre-commit install`
  run (git hook active). First `pre-commit run --all-files` passed — it
  auto-stripped trailing whitespace in `README.md` (the ruff / eslint hooks
  report "no files to check" only because `backend/` and `frontend/` are not
  git-tracked yet).

The three files (`.pre-commit-config.yaml`, `.github/workflows/backend.yml`, `.github/workflows/frontend.yml`) are the source of truth and are not reproduced here. Key points: CI is path-filtered per sub-project; `frontend.yml` reads Node from `.nvmrc`; `backend.yml` runs ruff + `ruff format --check` + mypy + `alembic upgrade head` (against a `postgres:16` service) + pytest. Bump `setup-uv` / hook `rev:` pins as majors are released.

### Step 7 — Remaining implementation (spec §3.1 + §8)

**Minimal starter landed (2026-09-03)** so the stack serves during development,
ahead of the full implementation below:

- `backend/app/main.py` — real FastAPI `app`: `GET /` greeting, `GET /healthz`
  liveness, CORS from `FRONTEND_ORIGIN` (added to `.env.example`; a
  config-driven allowlist replaces the `os.environ` read in step 3). No DB yet.
- `backend/tests/test_health.py` — `TestClient` tests for `/` and `/healthz`
  (2 passing). (Env note: this environment's Starlette warns that
  `TestClient`'s httpx backend is deprecated in favour of `httpx2` — harmless
  for now.)
- `frontend/src/App.tsx` — replaced the Vite demo with a "Hello World" page that
  fetches `/healthz` from `VITE_API_URL` and shows the result. `index.css`
  trimmed to essentials; `App.css` deleted; smoke test updated (stubs `fetch`).

Verified: `docker compose up -d` → `curl localhost:8000/healthz` →
`{"status":"ok"}`, `curl localhost:8000/` → greeting, `localhost:5173` renders
the page; `make test` → backend 2 passed, frontend 1 passed; `ruff` / `ruff
format --check` / `mypy` clean (ruff-format also collapsed one line in the
Alembic-generated `migrations/env.py`).

Full implementation, backend, in order:

1. `app/models/*.py` + `app/models/__init__.py` (import every model module) —
   columns from spec §4.
2. `make migration name="initial schema"` → `migrations/versions/0001_*.py`.
3. `app/config.py` (Pydantic `Settings`), `app/db/session.py` (engine + `get_db`).
4. `app/main.py` (app factory + CORS), `app/api/router.py`,
   `app/api/v1/health.py`, `app/schemas/health.py`.
5. `app/core/permissions.py` (`resolve_scope`, spec §3.2), `app/api/deps.py`
   (`get_current_person` / `require_person`), `app/api/v1/auth.py`,
   `app/api/v1/people.py` (stub CRUD), `app/core/audit.py` (stub writer).
6. `tests/conftest.py`, `tests/test_health.py`, `tests/test_permissions.py`.
7. `app/seeds/seed_lookups.py` (placeholder positions / functions / terms).

Frontend, in order:

1. `src/lib/supabase.ts` (auth-only client), `src/lib/api.ts` (typed fetch
   wrapper, token attach).
2. `src/auth/AuthProvider.tsx`, `src/auth/useAuth.ts`.
3. `src/routes/router.tsx`, `Login.tsx`, `Dashboard.tsx`, `NotAuthorised.tsx`.
4. `src/components/ProtectedRoute.tsx`.

Then `docs/architecture.md` and `docs/local-development.md`, and the `make
bootstrap` verification checklist in §10.
