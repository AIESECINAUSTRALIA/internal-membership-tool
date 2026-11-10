# Homepage chart

**Status: proposed — awaiting Tech Lead sign-off.** Resolves spec §12 #12 ("what the
default homepage shows") once signed off. Until then the backend below is built but
should not be treated as the final answer.

| | |
|---|---|
| Spec | §2A.4 (Homepage), §4.2–4.3 (attribute catalog, `kpi_record`) |
| Endpoint | `GET /api/v1/home/chart?kpi=<key>` (`backend/app/api/v1/home.py`) |
| Frontend | `Api.getHomeChart(kpiKey?)`, `HomeChart` in `frontend/src/api/types.ts` |
| Table | `home_chart_default` (`docs/data-model.md`) |

## What the chart shows

**One KPI, as a line, month by month, over the viewer's current term up to today.**

Two things decide what's on it:

1. **Whose data — from the viewer's position, never from the request.**

   | Position | Scope | Records counted |
   |---|---|---|
   | Member, Team Leader | `team` | Logged against the viewer's current team |
   | LCVP, LCP | `function` | Every membership in the viewer's LC and function |
   | MCD, MCVP, MCP | `all` | Every LC |
   | Any other position (e.g. `admin`) | `team` | Narrowest on purpose: an unknown position sees less, never more |

   Rule: `home_chart_scope` in `backend/app/core/permissions.py`.

2. **Which KPI — the function's default, unless the viewer picks another.**
   Each function has at most one default KPI, stored in `home_chart_default` (data,
   not code: changing it is an admin edit, not a deploy). The viewer may pick any
   active KPI that is their function's own or shared by all functions. Picking only
   changes *which* KPI is plotted; it can't widen *whose* data is shown.

## Rules the endpoint follows

- **No stored aggregates.** Every point is `SUM(kpi_record.value_number)` at query
  time (spec §4.3).
- **Month bucket = the month `period_start` falls in.** Records are weekly, monthly
  or per-event, so splitting a value across months would invent data.
- **Empty months are zero** once any record exists in the window. **No records at
  all is no points**, so the page says "No data exists" rather than drawing a flat
  line.
- **No default and no pick → no KPI**, no points; the choice list is still returned.
- **A default that's since been deactivated** counts as no default, not an error.
- **Picking a KPI outside the allowed set → 400.** It is never silently swapped for
  the default, so the chart never shows a different KPI from the one asked for. The
  message is the same whatever the reason (unknown, inactive, another function's), so
  the response doesn't reveal which KPIs exist.
- **Not allocated → 403**, with the §9 "contact your EB or MC" message.

## Why this design

- **A default per function, with the option to pick.** Functions track different
  KPIs, and adding different KPIs together is meaningless, so a single line needs a
  single KPI. A default keeps the page useful with zero clicks; the pick covers
  people who care about a different KPI.
- **The pick is not saved.** Remembering a person's choice would be homepage
  customisation, which is V2 (§2A.4). Today it's a view filter, like the Data page's
  date range.
- **A lookup table, not `function.default_kpi_id`.** Avoids `function` and
  `attribute` referencing each other. See `docs/data-model.md` → `home_chart_default`.

## Questions for the Tech Lead

Record the answers here, then change the status line at the top.

1. Is one KPI per chart, defaulting per function, the right content for the homepage?
2. Is an unsaved KPI picker acceptable for MVP, or is that already V2 customisation?
3. Is "current term, up to today" the right window, or the last 12 months?
4. **LCP and MCP** hold the `president` function (spec §2). At `function` scope an LCP
   sees only records logged by presidential memberships, which is probably not what
   they want. Should presidential positions see the whole LC (MCP: all LCs) instead?
5. **MC** sees all LCs, but only for KPIs their function can pick. Is that right, or
   should MC be able to pick any KPI?
6. Who sets each function's default once the real KPI list exists (spec §12 #4)?

## Not done yet

- **Real KPI catalog.** The seeded KPIs and defaults (`seed_attributes.py`) are
  placeholders until spec §12 #4 lands.
- **Backend function seed** still uses the old function list (see
  `docs/data-model.md` → "Known differences from the spec"), so most spec functions
  have no default yet.
- **Admin UI to set defaults.** Belongs on the Admin console's KPIs screen; until
  then, defaults are set through `set_home_chart_default` (seed or shell).
- **Frontend.** `HomePage.tsx` doesn't render the line or a KPI picker yet, and
  `getHomeChart` isn't in `http/httpApi.ts` yet, so even in HTTP mode it falls back to
  the mock.
