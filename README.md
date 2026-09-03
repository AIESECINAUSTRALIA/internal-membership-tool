# internal-membership-tool

AIESEC Australia's Membership / Data Management Platform. FastAPI API + React
(Vite) frontend + PostgreSQL, run locally with Docker Compose.

## Tech stack

| Layer | |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2 + Alembic · **uv** |
| Frontend | Node 22 · React · TypeScript · Vite |
| Database | PostgreSQL 16 |
| Auth | Supabase (managed OAuth) |
| Local dev | Docker Compose · Make |
| Quality | pytest · vitest · ruff · mypy · eslint · pre-commit · GitHub Actions |

Rationale for each choice is in the design spec
(`docs/superpowers/specs/2026-09-02-project-skeleton-design.md` §2).

## Team

| Name | Email | GitHub |
|---|---|---|
| YJ | yeonjun.kim@aiesec.net | @yyeonjunkim |
| Andrew | andrew.davindra@aiesec.net | @andrew.davindra |
| Akein | tsung.akein@gmail.com | @yatsensei |
| Jerry | jerry.chang@aiesec.net | @ctc_is_me |
| Sam | kri1ssamjc@gmail.com | @ksamciiiii |
| Sangam | sangam.shakya@aiesec.net | @sangam.shakya |

## Quick start

**You need:** Docker Desktop running.

```bash
cp .env.example .env      # first time only
make bootstrap            # build and start everything
```

Open:

| | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 (`/` and `/healthz`) |

## Daily use

| When | Command |
|---|---|
| **First time** (or after a reset) | `make bootstrap` |
| Done for now — shut it down | `make down` |
| Next time — start it back up | `make up` |

You only run `make bootstrap` once. After that it's `make up` to start and
`make down` to stop.

While the stack is up, editing `backend/app/**` or `frontend/src/**` reloads
automatically — keep `localhost:5173` open.

## Other commands

| Command | |
|---|---|
| `make logs` | tail logs |
| `make test` | run tests |
| `make` | list all targets |

Re-run `make bootstrap` after changing a dependency or Dockerfile, or to reset
the database (`docker compose down -v && make bootstrap`).

## More

- Running without Docker, secrets, deployment → **[docs/local-development.md](docs/local-development.md)**
- Design & setup history → `docs/superpowers/specs/2026-09-02-project-skeleton-design.md`
