# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## AIESEC Australia Tech Team

This file gives Claude persistent context on this project. Read it before making architectural, scoping, or process decisions — not just before writing code.

## Repo state & conventions

This repository is currently pre-code — the only tracked files are `README.md` (team roster: name, email, GitHub handle) and this file. There is no build system, test suite, or application code yet. When the first code lands, add build/lint/test commands and concrete architecture notes here.

- **Branches**: `chore/DEV-XXXX_short_description` (see the current `chore/DEV-0000_misc_setup`).
- **Commits / PR titles**: prefixed with the ticket ID, e.g. `chore: DEV-0008 ...`. `DEV-XXXX` refers to the tracker issue.
- Changes land on `main` via PR.

---

## Who this is for

AIESEC Australia's in-house volunteer dev team, building two internal tools over one term (Aug–Dec). Team is small (6 incl. Tech Lead), mostly 2nd-year uni students with limited experience, mentored by the Tech Lead as they build.

**The single most important constraint: annual turnover.** Leadership and dev team membership turn over roughly yearly. Every decision — architecture, tooling, docs, access control — should be made assuming the person who built it won't be here next year and the person maintaining it next year has zero prior context. When in doubt, favour:
- boring, common, well-documented tech over clever/novel solutions
- managed platforms over self-hosted infra
- data-driven config (tables, lookups) over hardcoded logic
- written documentation over tribal knowledge
- role-based access (GitHub Teams, position-based permissions) over access tied to named individuals
- no single point of failure in either code ownership or account access (e.g. ≥2 GitHub org owners, no admin powers held by only one person)

If a suggestion only works because one specific person understands it, that's a flag, not a feature.

---

## What we're building

### 1. Membership / Data Management Platform
Replaces scattered LC productivity spreadsheets with a single source-of-truth database, role-based access, analytics dashboards, and query-derived official reporting (NAMs, SONA, MTR). Full requirements spec: see `docs/membership-tool-requirements-spec.md` (or wherever this is placed in-repo).

**Core pillars:**
- **Auth:** OAuth login via AIESEC emails.
- **Access control:** two-dimensional — **position × function**, not flat role checks (e.g. LCP / VP / Team Leader / Member combined with function like MCBD). Must be implemented as a data-driven permission matrix (DB table), not hardcoded if/else logic.
- **Data model:** single relational source of truth. No feature should require manually re-linking spreadsheets. KPI/productivity data granular enough that rollups and reports are computed via query, not maintained as separately-entered aggregates.
- **Analytics:** dashboards with custom date-range filtering (not fixed presets only).
- **Reporting:** NAMs, SONA, MTR generated from queries against granular data. Get and follow the actual current report templates before finalising schema — don't guess field lists.
- **Privacy/deletion:** genuine deletion requests must be honoured. Prefer **anonymisation over hard delete** where records have downstream aggregate/reporting dependencies (KPI history, generated reports). Map cascading effects explicitly. Maintain an audit trail of deletion requests (logging the action taken, not the deleted personal data itself).
- **Exchange SU linking:** out of scope to build this term, but the person/member data model should be designed so a future SU→application→opened-exchange table can FK into it later. Don't build the pipeline now.

### 2. Website (replacing WordPress)
Motivation for replacing WordPress (design/speed vs. CMS usability vs. need for dynamic features) should be clarified per-initiative, not assumed. If dynamic features are needed (EP applications, event registration, partner forms), treat it as a small web app and design it to **feed data into the membership platform** rather than existing as a disconnected silo.

---

## Explicit non-goals for this term (Phase 2 — flag, don't build)
- Exchange SU → opened exchange pipeline (design-ready only)
- Website ↔ membership tool shared auth/integration (unless the website project independently reaches that point)
- Automated/scheduled report generation or exports
- Mobile app / offline support
- Any custom payment handling — if payments are ever needed, use Stripe or similar, never build it in-house

---

## Tech & infra defaults

| Area | Default |
|---|---|
| Budget | ~$500 AUD/year ceiling for hosting/infra, combined across both projects. Realistic target $100–350/year using free/managed tiers. |
| Database | Supabase or Neon preferred — must not be a free tier that auto-expires data (avoid e.g. Render's 30-day Postgres). |
| File/image storage | Object storage (e.g. Supabase Storage), never stored directly in DB rows. |
| Hosting | Managed platforms over self-hosting — Vercel/Netlify, Supabase. |
| Auth | Managed OAuth (e.g. Supabase Auth), no custom auth system. |
| Code hosting | GitHub Organisation account (not personal accounts) — apply for GitHub's nonprofit program for free Team-tier features. ≥2 org owners at all times. Access via GitHub Teams tied to role, not individuals. |
| Security | No outsourced security retainer. Instead: OWASP Top 10 as a dev checklist, Dependabot + Snyk free tier, one pre-launch external security/privacy audit, a one-page incident response plan. A genuine one-off Australian Privacy Act / APP compliance consult is worth paying for even though technical security is handled in-house. |
| IP/ownership | All code and infra accounts owned by AIESEC Australia as an entity, confirmed in writing — never under individual personal accounts. |

---

## Working conventions

- **Documentation is not optional.** Every non-trivial design decision (schema choices, permission matrix logic, deletion/anonymisation approach) should be documented in-repo, written for a reader with zero prior context. This is direct mitigation for the turnover constraint, not busywork.
- **Scope discipline.** This term's job is a strong, realistic MVP — not the full long-term vision. When a feature request or design idea creeps toward "nice to have long-term," flag it explicitly as Phase 2 rather than quietly expanding scope or quietly dropping it.
- **Lookup tables over hardcoding** for anything likely to change across terms (functions, KPI types, permission rules) — a future non-technical admin or a future dev with no context should be able to reason about these from data, not code.
- **Mentoring context:** most contributors are 2nd-year students with limited experience. Code review and technical explanations should favour clarity and teaching over terseness — this is a training ground as much as a build.
- When giving technical specs, docs, or code, stay consistent with the stack/decisions above unless told they've changed.

---

## Reference docs (keep in repo, link here once placed)
- `docs/membership-tool-requirements-spec.md` — full MVP requirements spec for Project 1
- `docs/website-requirements-spec.md` — (to be written)
- `docs/permission-matrix.md` — position × function × scope × allowed-actions table
- `docs/deletion-cascade-map.md` — what happens to KPI/report/exchange data on a deletion request
- `docs/incident-response-plan.md` — one-pager
