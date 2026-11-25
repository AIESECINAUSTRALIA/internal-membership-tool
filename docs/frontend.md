# Frontend guide

For someone opening `frontend/` with no prior context. The product rules are in
`docs/membership-tool-requirements-spec.md` (§2A is the source of truth for pages).

## Where things are

```
frontend/src/
  theme/theme.ts        ALL styling. Colours, type, component looks. Read its header comment.
  api/types.ts          Every shape the UI knows about the server, and the one `Api` interface.
  api/index.ts          THE swap point: chooses the mock or the real backend.
  api/expaSession.ts    Real EXPA sign-in + GET /api/v1/me + sign-out. See docs/auth.md.
  api/sessionEvents.ts Notifies the auth provider when the backend rejects a session.
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

**Where it stands.** In `expa` mode (`docs/auth.md`), `api/http/httpApi.ts` sends
these to the real backend: the membership-summary methods, the LCs/terms/teams in
`getReferenceData`, and Profile's custom fields (`getMyCustomFields`,
`updateMyCustomFields`, backend `/api/v1/me/custom-fields`) and position history
(`getMyMembershipHistory`, backend `/api/v1/me/memberships`). The Admin console's
People and Memberships methods also use the real backend (DEV-47). `getMe`,
sign-in and sign-out go through `api/expaSession.ts`. Everything else still comes
from the mock. As more endpoints land, add their methods to `httpApi.ts`.

Profile's custom fields and position history are separate calls from `getMe` on
purpose. `getMe` runs at every sign-in, so it stays one small backend call: a broken
Profile endpoint shows an error on Profile instead of locking everyone out. And
`Me.memberships` holds **only active memberships**, the ones that grant access
(§3.2), so code that reads it never has to remember to skip ended ones. The full
history (past, current and future) is only for display, on Profile.

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

## Real sign-in (EXPA) vs the development sign-in

`VITE_AUTH_MODE` chooses. `mock` is the development sign-in described below, and the
default on the dev server and in tests. `expa` shows a single "Sign in with EXPA"
button and asks the backend's `GET /api/v1/me` who you are and what you may do.
Production builds always use `expa`, even if `VITE_AUTH_MODE=mock` is set
(`api/authMode.ts`, spec §2A.3). See `docs/auth.md` for the flow and the one-time
EXPA application setup.

The frontend never handles EXPA's access tokens. `signIn()` sends the browser to
`/api/v1/auth/login`, and the backend runs the OAuth exchange. On a successful
sign-in, the backend sets its own HttpOnly `__session` cookie and sends the browser
back to the app. `getMe()` calls `GET /api/v1/me` with
`credentials: 'same-origin'`, so the browser sends the cookie without the frontend
having to read or store it. `signOut()` sends `POST /api/v1/auth/logout`, which
revokes the session and clears the cookie.

The API is always the relative `/api`: Vite's development proxy forwards requests
to the backend locally, and Firebase Hosting forwards them to Cloud Run on the
deployed environments. The frontend doesn't need the backend's hostname, so the
same production build works on both dev and prod. See `docs/local-development.md`
for the local proxy configuration.

Where the data comes from in `expa` mode (`api/index.ts`, ticket DEV-0043):

| `Api` method | Source |
|---|---|
| `listMembers`, `addMember`, `getMembershipDetail`, `extendTerm`, `moveToTeam` | real backend (`api/http/httpApi.ts`) |
| `getReferenceData` | LCs, terms and teams (only teams whose term hasn't ended) from the backend, with real database ids; positions and functions from the mock |
| `getMe`, `signIn`, `signOut` | EXPA sign-in and the backend's session cookie (`api/expaSession.ts`) |
| `getMyCustomFields`, `updateMyCustomFields`, `getMyMembershipHistory` | real backend (Profile, DEV-0045) |
| Admin People and Memberships methods | real backend (DEV-47) |
| everything else | mock, until its backend endpoints exist |

In `mock` mode every method comes from the mock and the backend is never called.

> **Known gap:** positions and functions come from the mock, and their keys only partly
> match the backend seeds. Today only the `ogv` and `bd` functions exist on both sides,
> and the MC positions are missing from the seeds (`docs/data-model.md`, "Known
> differences"). Until the schema-alignment ticket fixes the seeds, Add member against
> the real backend only works for those functions.

Failures from the real backend: the write methods (`addMember`, `extendTerm`,
`moveToTeam`) never throw; they return `{ status: 'rejected', message }` with a
plain-English message (session expired, no permission, not found, or "Something went
wrong"). The read methods throw, and each page shows its own error state. A form holding a
non-numeric id (left over from mock data) is refused before anything is sent.

**An expired or revoked session sends the person back to sign-in.** When the HTTP
API receives a 401, it notifies `AuthProvider` through `api/sessionEvents.ts`.
The provider checks `/me` again, and if the session is no longer valid, clears
the signed-in person. The route guards then send them back to sign-in. Several
overlapping 401 responses trigger only one check at a time. A 403 means the person
doesn't have permission to do something, not that they have been signed out.

There is no background session polling: an expired session is picked up on the
next real backend request, or when the app is loaded again.

**Failed sign-ins come back to the sign-in page.** The backend redirects the
browser to `/sign-in?error=<reason>` when the OAuth callback fails. The sign-in
page translates the reason into a message, including the fixed not-allocated
wording from spec §2A.3. A person who has no active membership at sign-in never
gets a session. The not-allocated page is still used when an existing signed-in
person no longer has an active membership. See `docs/auth.md` for the error codes.

## Signing in as a different role (development only)

In mock mode the sign-in page has one plain button. It signs in as an LC Vice President. To try another
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
  all of Australia, which is a guess (spec §12 #12). Any other position gets the team
  chart, the narrowest scope (backend `home_chart_scope`).
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

## Admin console: Metrics & custom fields

`/admin/attributes` (`admin/pages/AdminAttributesPage.tsx`, dialogs in
`admin/AttributeDialogs.tsx`) manages the `attribute` catalog (spec §1.5, §4.2). KPIs and
custom fields are rows of the same table, so they share one screen with a filter (All /
KPIs / Person fields / Membership fields), not two screens. Needs `manage` on `attribute`.
Add and edit use one form that only shows the inputs that fit the data type; deactivate
is the soft delete. The edit rules (key and applies-to fixed, data type locked once values
exist, in-use options can't be removed) are in `docs/data-model.md` → "Editing the
catalog". The mock repeats them in `api/mock/attributeRules.ts`, and its catalog
(`ATTRIBUTES` in `api/mock/seed.ts`) is the same placeholder list the backend seeds, not
the real KPI list (still a spec TODO). It is separate from `CUSTOM_FIELD_DEFS`, so the
Profile page is unaffected until the two are wired together.

Swap note: the backend scopes an attribute by `function_id`, while the frontend uses
`functionKey` like the rest of the UI, so the real client maps between the two.

## Admin console: People & Memberships

`/admin/people` (`admin/pages/AdminPeoplePage.tsx`, dialogs in `admin/PeopleDialogs.tsx`)
adds, edits, deactivates and reactivates people (spec §1.5, §2A.2). Needs `manage` on
`person`. There is no delete. Deactivate asks for confirmation and says what it does:
the person can't sign in, their current memberships end, and nothing is deleted
(`docs/data-model.md` → `person`). The table has an EXPA column (Linked / Not linked, in
words); "Unlink EXPA" (linked people only) signs them out, and its confirm dialog says to
correct a wrong email first, since the next EXPA sign-in links again by email.

`/admin/memberships` (`admin/pages/AdminMembershipsPage.tsx`, dialogs in
`admin/MembershipDialogs.tsx`) works on one person at a time. Pick them with the person
search, or use "Manage memberships" on People. The person comes along in router state,
so no name or email goes into the URL. Needs `manage` on `membership`.

- **Assign** offers every active LC, and only the positions whose level matches it
  (§3.6). An LC other than the person's current one makes it a transfer, and the dialog
  warns before you confirm.
- **Correct** fixes a mistake in position, function or dates, and sends only the fields
  that changed.
- **End** ends a membership early.

The hierarchy rule (§3.4) isn't pre-filtered in the dialogs. The server refuses a
position at or above the admin's own, and the dialog shows its reason.

Both screens call the real backend: `api/http/httpApi.ts` sends the admin People and
Memberships methods (including `unlinkExpa`) to `/api/v1/people` and
`/api/v1/memberships`. The mock repeats the backend's rules for mock mode, and
`test/adminPeople.test.tsx` covers both the rules and the screens.

## Not built yet

The Admin console screens other than LCs, People, Memberships, Metrics & custom fields and Auditing
(see `admin/adminNavConfig.ts`). The MC/admin permissions table on
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
