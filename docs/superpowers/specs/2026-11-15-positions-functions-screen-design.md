# Positions & functions screen design

Status: implemented · Ticket: DEV-0049 · Date: 2026-11-15

---

## The key design question this doc answers

The ticket (DEV-0049) explicitly requires confirming whether the Admin console's
"Positions & functions" screen and the Settings → Functions screen (spec §2A.8) are
the **same screen surfaced in two places or two separate screens with different scope**.

**Decision: two separate screens with different scope and gating.**

---

## Screen 1 — Admin console: Positions & functions (this ticket)

| Attribute | Value |
|---|---|
| Location | `/admin/positions-functions` |
| Permission gate | `position:manage` |
| Who holds that grant | MC positions (mcd, mcvp, mcp) and future admin positions |
| What it manages | **Both** positions (label, rank, level, can_add_same_rank, active) **and** functions (label, active) |
| Rank / level / can_add_same_rank editable? | Yes |

## Screen 2 — Settings → Functions (not built in this ticket)

| Attribute | Value |
|---|---|
| Location | Settings page, Functions tab |
| Permission gate | `function:manage` |
| Who holds that grant | All MC positions (same as above, via spec §2A.8) |
| What it manages | **Functions only** (label, active) — no position management, no rank editing |
| Rank / level / can_add_same_rank editable? | No |

## Why two screens?

Spec §1.5 says: "Positions and their ranks stay admin-only."
Spec §2A.8 says: "Other organisation-wide administration lives in the Admin console, not here."
Spec §2A.2 says: "MC can also manage functions from Settings (§2A.8)." — the word "also" is additive.

The Settings screen is a convenience so MC positions can manage functions without
needing to navigate to the Admin console. It is intentionally scoped to functions only
because positions (especially rank, which drives access control) are higher-risk changes
that belong in the more deliberate Admin console context.

## Shared backend

Both screens call the same backend endpoints:
- `PATCH /api/v1/functions/{id}` for label/active changes

The Admin console additionally calls:
- `GET /api/v1/positions`, `POST /api/v1/positions`, `PATCH /api/v1/positions/{id}`
- `GET /api/v1/functions`, `POST /api/v1/functions`

The backend enforces `function:manage` on function mutations and `position:manage` on
position mutations. Both grants happen to be held by the same set of people (MC positions),
but the enforcement is independent, which means a future admin-only position can be granted
`position:manage` without getting `function:manage`, or vice versa.

## What is NOT built in this ticket

- Settings → Functions screen (a separate frontend build, to be ticketed separately)
- The `attribute` / `kpi_record` tables (tracked in `ticket.md`)
- The real permission matrix table (the backend currently uses a hardcoded baseline)
