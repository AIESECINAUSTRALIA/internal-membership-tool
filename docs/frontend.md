# Frontend guide

For someone opening `frontend/` with no prior context. The product rules are in
`docs/membership-tool-requirements-spec.md` (§2A is the source of truth for pages).

## Where things are

```
frontend/src/
  theme/theme.ts        ALL styling. Colours, type, component looks. Read its header comment.
  api/types.ts          Every shape the UI knows about the server, and the one `Api` interface.
  api/index.ts          THE swap point: chooses the mock or the real backend.
  api/mock/             In-memory fake server (seed data, rules). Delete when the backend is real.
  auth/permissions.ts   Pure functions: permission gating and the hierarchy rule (§3.4).
  auth/guards.tsx       Route guards, driven by the signed-in person's `me` payload.
  navigation/navConfig.ts  The sidebar menu as data (which permission shows which item).
  layout/               App shell (sidebar + header) and the sign-in frame.
  pages/                One file per page.
  features/membership/  The Add member, Extend term and Move to team dialogs.
  components/           Small shared pieces (confirm dialog, "not built yet" page/dialog).
  assets/               Logos (copied from frontend/images with kebab-case names).
  test/                 vitest.
```

## Rules

1. **Style through the theme only.** No CSS files, no hardcoded colours in components.
   Use `sx` with theme tokens (`bgcolor: 'background.paper'`, `p: 2`). If something looks
   wrong everywhere, fix it once in `theme/theme.ts`.
2. **Text is black, white, or the dark-gray brand colour.** Never a brand colour as text.
   One exception: the title on the sign-in panel is white on blue, allowed only because it
   is large text (white on blue is 3.98:1, which passes AA at 3:1 for text of 24px or more).
   Keep every line of it at least 24px.
   Brand colours are fills and marks. MUI would put white text on the brand blue (3.98:1,
   fails AA), so every palette colour sets `contrastText` explicitly. Contrast table:
   spec §2A.11.
3. **All data goes through `Api`** (`api/types.ts`), obtained with `useApi()`. Components
   never call `fetch`.
4. **Hiding a button is a convenience.** The server enforces access on every request
   (spec §2A). The logic in `auth/permissions.ts` only decides what to *show*.

## Fonts

Two families, self-hosted with `@fontsource` (no CDN), set in `theme/theme.ts`:

- **Lato** for all everyday text (weights 400 and 700, imported in `main.tsx`).
- **Marcellus** for the sign-in and not-allocated headlines only.

## Logos

`src/assets/aiesec-logo-black.png` is `images/Black-Logo.png` with the empty padding trimmed
(same artwork). It sits top-left in the sidebar as a link home. The original in
`frontend/images/` is untouched. The sign-in pages show no logo: their blue panel carries
the product title instead.

## Swapping the mock for the real backend

1. Write a class or object that implements `Api` (`api/types.ts`) using `fetch`.
2. In `api/index.ts`, replace `createMockApi(...)` with it.
3. Delete `api/mock/`, and the `?as=` persona code in `api/index.ts`.

The mock enforces the same rules the spec gives the server (scope in the query, no email in
the member list, the hierarchy rule, the LC-level rule, transfers end old memberships).
`src/test/mockApi.test.ts` pins those rules, so the real backend can be checked against the
same expectations.

## Mock people

Everyone in the mock data is a numbered placeholder: "Member 1", "Member 2" and so on
(first name "Member", last name is the number). The one exception is the default demo
person, the LC Vice President in oGV at USYD, whose first name is `temp_oGV` (last name
blank). There are no real or realistic names. Tests find people by id (for example
`p-sam`), never by name. Change names in `buildSeed` in `api/mock/seed.ts`.

## Signing in as a different role (development only)

The sign-in page has one plain button. It signs in as an LC Vice President. To try another
role, load the sign-in page with `?as=`:

| URL | Signs in as |
|---|---|
| `/sign-in?as=lcvp` (default) | LC Vice President, oGV, USYD |
| `/sign-in?as=lcp` | LC President, USYD |
| `/sign-in?as=tl` | Team Leader, oGV, USYD |
| `/sign-in?as=member` | Member, oGV, USYD (no Membership page) |
| `/sign-in?as=mcvp` | MC Vice President (all LCs) |
| `/sign-in?as=unallocated` | Term ended: sees the not-allocated page |

## Assumptions to settle before the real backend

These are in the mock and the frontend, but **not in the spec or schema yet**:

- **`Position.presidential` / `Function.presidentOnly`**: LCP and MCP use the President
  function, and nobody else does (spec §2 says "for LCP and MCP").
- **`Position.homeChartScope`**: which default chart the homepage shows. Member and Team
  Leader see a team chart, LCVP and LCP a function chart (as requested). MC positions see
  all of Australia, which is a guess (spec §12 #12).
- **The permission matrix** in `api/mock/seed.ts` is illustrative. The real seed is a spec
  TODO (§3.3). In particular the mock lets Team Leaders extend terms but not move people,
  and gives LCVPs `edit` at `function` scope but `create` at `lc` scope.
- **Rank source**: the UI takes the actor's rank from their highest active position. The spec
  takes it from the membership that supplies the grant (§3.4). The server is authoritative.
- **Future-dated memberships** don't appear on the Membership page (it lists current
  members only, §2A.5). A person added with a start date in the future shows up on that date.

## Tracking, Data, Settings: scaffolds, not placeholders

These three pages have their real layout and controls (spec §2A.6–§2A.8), wired to
real mock data wherever the data already exists. What they do NOT have is the KPI
catalog (spec §4.3 TODO), so anywhere a real number would appear, the page shows the
table or chart in its intended shape but empty — "No data exists", the same fixed
wording used everywhere else (spec §2A).

- **Tracking** (`pages/TrackingPage.tsx`): a function switcher (`ToggleButtonGroup`)
  for anyone who holds more than one function at once (`auth/permissions.ts`,
  `distinctFunctions`). "My tracking" always shows, empty. "Track someone" shows only
  with `canTrackOthers` (`kpi_record.edit` wider than `own`), searches with the
  existing `listMembers`, and narrows results to people the actor may track with
  `trackableRoleIds` — the same two-check hierarchy rule as Extend term and Move to
  team, now generalised in `permissions.ts` as `canActOnTarget`. **Simplification**:
  `listMembers` is scoped by `membership.view`, not `kpi_record`, so the search
  candidates are an approximation until a KPI-scoped search exists on the real
  backend.
- **Data** (`pages/DataPage.tsx`): scope tabs (Team/Function/LC/Australia-wide) from
  `availableDataScopes`, an LC picker for `all`-scope viewers, a start/end
  `DatePicker` pair (§6), an empty summary table and an empty chart panel, and a
  "Build a report" button that opens `NotBuiltYetDialog` (§2A.7's report generator,
  kept separate from the official NAMs/SONA/MTR reports, §7). **Assumption**:
  `availableDataScopes` offers every scope up to the widest grant, on the reasoning
  that a wider grant already covers every narrower cut of the same data (spec §12
  #18 is still open on the real report design).
- **Settings** (`pages/SettingsPage.tsx`): the Functions block now reads the real
  function list from `getReferenceData()` and lists each one with its active state.
  Add, Rename and Deactivate all open `NotBuiltYetDialog` rather than doing
  anything — there is no function-mutation endpoint yet.

Their menu items and routes are gated by the same permission the real pages will use
(`navigation/navConfig.ts` and `App.tsx`). `built: false` in `navConfig.ts` hides an
item whose page doesn't exist at all yet.

## Profile custom fields

The Profile page can edit person-level custom fields (spec §2A.9, §4.2), but the real
catalog is not decided, so the mock catalog is **empty** and no "About you" box shows. To
try the form, add an entry to `CUSTOM_FIELD_DEFS` in `api/mock/seed.ts` (text, number,
date, boolean and enum are supported).

## Not built yet

The Admin console (own sign-in and address, spec §2A.2). The MC/admin permissions table on
the Membership page (spec §2A.5, who may view it is open, §12 #19). Anywhere real KPI data
would appear (the homepage chart, Tracking, the Data summary/chart/report generator, and
Settings' Add/Rename/Deactivate function actions): the KPI catalog is still a spec TODO
(§4.3), and function mutations have no endpoint yet, so these show real layout with "No
data exists" or a "Not built yet" dialog rather than working.

## Checks that were run

Slice 1 (theme, app shell, sign-in, Home, Profile, Membership summary):

- `npx tsc -b`, `npx eslint .`, `npx vitest run`, `npm run build`.
- axe-core (WCAG 2.0/2.1/2.2 A and AA rules) on every page and the Add member dialog: no violations.
- Keyboard: the skip link, the focus ring on buttons, links and grid headers.
  (axe cannot judge focus visibility, so this was checked by eye.)

Tracking/Data/Settings scaffolds: `npx tsc -b`, `npx eslint .`, `npx vitest run` (71
tests) and `npm run build` all pass. **Not yet done for these three pages**: a live
axe-core pass and an eyeballed keyboard check, the way slice 1 got them. Run those
before treating the scaffolds as finished, the same way slice 1 was checked.

Known gap: the production bundle is about 1.2 MB (375 kB gzipped) in one chunk, mostly MUI
and the Data Grid. Fine for an internal tool. Route-level code splitting is the fix if it
ever matters.
