# Authentication (sign in with an EXPA account)

How people sign in to the Membership Tool, how the backend knows who they are, and the
one-time setup needed to make it work. Written for someone with no prior context.
Spec: §9 (Authentication) and §2A.3 (Sign in).

---

## The short version

- People sign in with their **EXPA account**, not directly with Google or
  Supabase. EXPA handles authentication; our backend handles the OAuth code
  exchange and creates its own session.
- The backend asks EXPA GIS for `currentPerson { id aiesec_email }`. It first
  matches `person.expa_id`, falling back to an exact, case-insensitive
  `aiesec_email` match for an unlinked person.
- A matched person with an active membership can sign in. An unmatched,
  anonymised or unallocated person gets no session and is redirected to
  `/sign-in?error=not_allocated`, which shows the spec §2A.3 message. Every
  other failed sign-in also redirects to `/sign-in?error=<reason>`.
- The browser gets a 12-hour, server-side session through an HttpOnly
  `__session` cookie. EXPA tokens are discarded after the identity lookup.

## The flow

```text
Browser                    Our API (FastAPI)                 EXPA / GIS
   |                              |                               |
   | GET /api/v1/auth/login       |                               |
   |----------------------------->|                               |
   |                  create pending session + OAuth state         |
   |<----- __oauth_pending cookie + redirect to EXPA ------------|
   |------------------------------------------------------------->|
   |                       EXPA sign-in                            |
   |<---------------- redirect to /api/v1/auth/callback ----------|
   |                              |                               |
   | callback: code + state       |                               |
   |----------------------------->|                               |
   |                   validate cookie + consume state             |
   |                              |---- exchange code ------------>|
   |                              |<--- access token --------------|
   |                              |---- currentPerson query ------>|
   |                              |<--- id + aiesec_email ---------|
   |                   match person + active membership            |
   |                   discard EXPA token                          |
   |                   rotate session token + write audit          |
   |<---- __session cookie + redirect to FRONTEND_ORIGIN ----------|
   |                              |                               |
   | GET /api/v1/me (cookie)      |                               |
   |----------------------------->|                               |
   |<--- person, memberships, permissions ------------------------|
```

The pending cookie and OAuth state are separate random values. Only their
SHA-256 hashes are stored. Both must match before the callback can continue,
and the state is consumed before contacting EXPA so the same callback cannot
be replayed.

Where the code lives:

| Piece | File |
|---|---|
| OAuth login, callback, logout and `/me` | `backend/app/api/v1/auth.py` |
| EXPA OAuth exchange and GIS identity lookup | `backend/app/core/auth.py` |
| Pending, active and revoked sessions | `backend/app/core/sessions.py` |
| Cookie authentication and current actor | `backend/app/api/deps.py` |
| Session database model | `backend/app/models/user_session.py` |
| EXPA identity on the local person | `backend/app/models/person.py` |
| Origin validation and CORS | `backend/app/main.py` |
| Permissions returned by `/me` | `backend/app/core/resolved_permissions.py` |
| Sign-in audit entry | `backend/app/core/audit.py` |
| OAuth and session configuration | `backend/app/config.py` |
| Frontend authentication mode | `frontend/src/api/authMode.ts` |
| EXPA sign-in, sign-out and `/me` mapping | `frontend/src/api/expaSession.ts` |
| Cookie-based HTTP requests | `frontend/src/api/http/httpApi.ts` |
| Session-expiry notifications | `frontend/src/api/sessionEvents.ts` |
| Signed-in person and session state | `frontend/src/auth/AuthProvider.tsx` |
| Sign-in page and callback error messages | `frontend/src/pages/SignInPage.tsx` |
| Choosing the mock or real API | `frontend/src/api/index.ts` |
| Frontend route guards | `frontend/src/auth/guards.tsx` |
| Local API proxy | `frontend/vite.config.ts` |

## Design decisions (and why)

**EXPA OAuth, not our own password system.** EXPA authenticates the member.
The Membership Tool never asks for or stores their EXPA password. Our backend
only exchanges the authorization code and retrieves the identity needed to
match the member to our database. The OAuth application must be registered
with AIESEC, using an HTTPS callback URL.

**Why our own session instead of keeping EXPA tokens.** EXPA tells us who
the person is; our database decides what they can access. After retrieving
the EXPA ID and email, the backend discards the access token. The browser
uses our own session cookie for subsequent requests. That means EXPA tokens
do not need to be stored in local storage, sent with every API request or
persisted in PostgreSQL. Logout can revoke our session immediately.

**Why the EXPA ID comes before email.** Email addresses can change. A
stable EXPA ID is a better long-term identity key. On the first sign-in,
an unlinked person can be matched by their AIESEC email, provided they have
an active membership. The backend then saves `person.expa_id`. On later
sign-ins, that ID takes precedence. An already-linked person is not
reassigned just because EXPA reports a different email.

**The backend enforces the email domain.** `ALLOWED_EMAIL_DOMAINS` defaults
to `aiesec.net` and accepts comma-separated domains. The match is exact:
`x@notaiesec.net` and `x@aiesec.net.evil.com` are not accepted. This check
happens when EXPA returns the identity during sign-in, not through a
frontend account-picker hint.

It runs **once, at sign-in**, not on every request. Removing a domain from
`ALLOWED_EMAIL_DOMAINS` therefore does not end sessions that already exist:
they run out within `SESSION_TTL_HOURS` (12 by default). To cut someone off
immediately, revoke their rows in `user_session`.

**An `ANONYMISED` person can never sign in.** The callback rejects an
anonymised record even when the EXPA ID matches. The anonymisation workflow
must also clear `person.expa_id` when that workflow is implemented.

**An `INACTIVE` (deactivated) person can't sign in either, and gets a 401.** Both
statuses are in `SIGN_IN_BLOCKED` (`backend/app/models/person.py`). The callback treats
them as "not allocated", and `get_current_user` (`backend/app/api/deps.py`) answers an
existing session with 401 "Account is unavailable". The status is checked on every
request, so this takes effect even for a session that is still open.

**Deactivating and unlinking both revoke the person's sessions.** The Admin console's
*Deactivate* and *Unlink EXPA* call `revoke_sessions_for_person`
(`backend/app/core/sessions.py`), which marks every open session revoked in the same
transaction as the change. The person is signed out everywhere at once, instead of
waiting up to `SESSION_TTL_HOURS`.

**Unlinking and re-linking.** *Unlink EXPA* (`POST /api/v1/people/{id}/unlink-expa`) clears
`person.expa_id` and revokes sessions. It does not stop the person being matched again:
the next EXPA sign-in finds an unlinked person by their AIESEC email and links that
EXPA account. So **to fix a wrong match, correct the person's email first, then unlink.**
Unlinking first would re-link the same wrong account at the next sign-in. Editing the
email of a linked person doesn't change who signs in, because the EXPA ID is matched
first. The audit entry (`person.unlink_expa`) records only that the link was removed,
never the EXPA ID. Admin guide: `docs/admin-guide/02-people-and-memberships.md`.

**No allocation means no authenticated session.** The callback requires
both a matching local person and at least one active membership. If either
is missing, it issues no session cookie and redirects to
`/sign-in?error=not_allocated`. This is different from the old Supabase
flow, where `/me` could return a successful response with `person: null`.
It lands on the sign-in page rather than `/not-allocated` because that
page's route guard needs a signed-in user.

**A failed callback always ends on a frontend page.** The callback is a page
the browser visits, not an API call, so it never answers with JSON. Each
failure redirects to `{FRONTEND_ORIGIN}/sign-in?error=<reason>`, and
`SignInPage` shows a message for it:

| `error=` | Meaning |
|---|---|
| `denied` | The person cancelled on EXPA's page |
| `expired` | Missing, wrong or already-used state or pending cookie |
| `expa` | EXPA could not be reached, or answered badly |
| `domain` | The EXPA email is not in `ALLOWED_EMAIL_DOMAINS` |
| `not_allocated` | No matching person, anonymised, or no active membership |

The reasons are listed in `SignInError` (`backend/app/api/v1/auth.py`) and
`SIGN_IN_ERRORS` (`frontend/src/pages/SignInPage.tsx`); keep the two in sync.

**Permissions still come from the server.** `/me` returns the union of
(resource, action, scope) grants across the person's active memberships,
keeping the widest scope when two grants overlap (spec section 3.2).
For example, LCVP oGV plus Team Leader BD gives `membership:edit` at
`function`, not `team`. `resolve_permissions` reads the
`BASELINE_PERMISSION_MATRIX` in `backend/app/core/permissions.py`.
An ended or future membership grants nothing. Frontend visibility is only
a convenience; feature endpoints enforce permissions again on the backend.

**Why sessions are stored in PostgreSQL.** `user_session` contains a
SHA-256 hash of the session token, an optional person ID, a pending OAuth
state hash, creation and expiry timestamps, and an optional revocation
timestamp. Raw tokens and state values are never stored. A pending OAuth
session lasts one hour. After successful sign-in, the token is rotated and
the authenticated session lasts 12 hours by default, without sliding
renewal. The `__session` cookie uses HttpOnly, SameSite=Lax and Path=/.
It is also `Secure` whenever `APP_BASE_URL` is `https://` (every
deployment). Locally over plain http it isn't, because Safari drops
`Secure` cookies on `http://localhost`.

**Old sessions are cleaned up automatically.** Every `GET /auth/login`
first deletes expired and revoked rows (`purge_stale_sessions`), and a
failed callback deletes its own pending row. No scheduled job is needed,
and the table can't grow without bound even if someone calls the login URL
in a loop: pending rows expire after an hour. `expires_at` is indexed for
this. When the anonymisation workflow is built (Phase 2), it must also
delete the person's `user_session` rows.

**Each successful sign-in is written once to `audit_log`.** The callback
uses `record_audit` with action `auth.sign_in`, the local person ID and
`{"allocated": true}`. The identity link, authenticated session and audit
entry are committed together. Calling `/me` repeatedly does not create
more sign-in entries. The audit entry contains no email, OAuth code or
session token.

**Refused sign-ins are audited too, but only after EXPA has confirmed who the
person is** (spec open question 17). A refused sign-in writes `auth.sign_in`
with `{"allocated": false, "reason": ...}`:

| `reason` | `resource_id` / `actor_person_id` |
|---|---|
| `domain` (email outside `ALLOWED_EMAIL_DOMAINS`) | none |
| `not_allocated`, no person row or anonymised | none |
| `not_allocated`, person exists but has no active membership | the person's id |

The email is never stored. An anonymised person's id is left out so the record
gains no new linked activity. Cancelled, expired-state and EXPA-error failures
are **not** audited: anyone can trigger those in a loop without an EXPA
account, and the audit log is permanent and append-only, so auditing them
would let a script fill it.

**Origin validation protects write requests.** Browsers attach cookies
automatically, even to requests another website triggers, so a
cookie-based session needs CSRF protection. For methods other than GET,
HEAD and OPTIONS, the backend requires an `Origin` header matching either
`FRONTEND_ORIGIN` or `APP_BASE_URL`, compared without a trailing slash and
case-insensitively. A mismatch or missing Origin gets 403. Locally these
are two different origins (Vite on :5173, the API on :8000). Deployed,
Firebase serves both from one domain, so they are the same.

**No backend sign-in stub.** API authentication requires a valid local
session cookie. The backend no longer trusts Supabase JWTs or the old
`X-Actor-Email` development header. `get_current_actor` still resolves the
person's active memberships and enforces the existing permission model.

**Session expiry and logout.** Expired or revoked sessions get 401.
`POST /api/v1/auth/logout` revokes the current session and clears both
authentication cookies. The frontend clears the signed-in person after a
successful logout, and the route guards send them back to sign-in.

When a real HTTP API request gets a 401, `api/sessionEvents.ts` notifies
`AuthProvider`, which checks `/me` again. If the session is no longer valid,
the provider clears the signed-in person and the guards send them back to
sign-in. Overlapping notifications are grouped so that several failed
requests don't all start their own `/me` check. A 403 does not trigger this:
the person is still signed in, but doesn't have permission to perform
that action.

There is no background polling or client-side session timer. An expired or
revoked session is picked up on the next backend request or when the app
loads again. The backend enforces expiry and revocation on every protected
request, regardless of what the frontend is currently showing.

## EXPA backend setup

The backend reads these settings from `backend/app/config.py`. The
repository-root `.env.example` lists the corresponding environment
variables.

| Variable | Purpose |
|---|---|
| `EXPA_AUTH_URL` | EXPA OAuth service URL |
| `EXPA_GRAPHQL_URL` | GIS GraphQL endpoint |
| `EXPA_CLIENT_ID` | Registered OAuth application ID |
| `EXPA_CLIENT_SECRET` | OAuth client secret, backend only |
| `APP_BASE_URL` | Public URL of the API, used to build the callback URL; `https://` turns on Secure cookies |
| `SESSION_TTL_HOURS` | Fixed session lifetime, default 12 |
| `ALLOWED_EMAIL_DOMAINS` | Exact permitted email domains |
| `FRONTEND_ORIGIN` | Where the browser app runs: allowed by CORS and the Origin check, and where sign-in redirects to |

The callback URL is built as:

`{APP_BASE_URL}/api/v1/auth/callback`

**Register the exact HTTPS callback URL with EXPA.** The local HTTP
defaults are useful for mocked tests, but they are not a working live
EXPA OAuth setup. The real OAuth client ID and secret are still pending
the AIESEC developer application and deployment configuration (DEV-77).

Keep secrets in the organisation's approved secret store. Do not put
`EXPA_CLIENT_SECRET` in a `VITE_` variable, a commit, a PR description
or a frontend bundle.

The intended deployment uses Firebase Hosting with `/api` routed to
Cloud Run. That routing and `APP_BASE_URL` must agree before real
browser sign-in can be tested.

## Checking the backend

| Try | Expect |
|---|---|
| `GET /api/v1/me` without a cookie | 401 |
| `GET /api/v1/auth/login` without EXPA credentials | 503 |
| OAuth callback with missing or wrong state | 302 to `/sign-in?error=expired` |
| OAuth callback with a disallowed email domain | 302 to `/sign-in?error=domain` |
| OAuth callback for a person with no active membership | 302 to `/sign-in?error=not_allocated`, no session |
| Valid OAuth callback for an allocated person | Session cookie and 302 to `FRONTEND_ORIGIN` |
| Reuse a consumed OAuth state | 302 to `/sign-in?error=expired` |
| Request with an expired or revoked session | 401 |
| POST with a missing or incorrect Origin | 403 |
| Logout with a valid session | Session revoked; cookie cleared |

Backend tests stub the EXPA provider, so they do not require live
credentials. Run `uv run pytest -q` from `backend/`. A passing suite
does not prove that EXPA's live OAuth endpoints, GIS URL, registered
redirect or deployed proxy routing have been configured correctly.

## Mock mode vs real sign-in

`VITE_AUTH_MODE` (frontend) picks how sign-in works:

| Value | What you get | Needs |
|---|---|---|
| `mock` | The development "Sign in" button and the `?as=` personas (`docs/frontend.md`). No EXPA, no backend. **Default for the dev server and tests.** | nothing |
| `expa` | "Sign in with EXPA", checked by `GET /api/v1/me` using the backend's session cookie. **Always used in production builds** (`npm run build`). | A configured EXPA application and the backend running |

When `VITE_AUTH_MODE` is unset, `frontend/src/api/authMode.ts` picks by build type.
Production builds always use `expa`, even if `VITE_AUTH_MODE=mock` is set
explicitly (spec §2A.3: the placeholder must be off in any deployed environment).
There is no fallback to mock sign-in if the backend or EXPA is unavailable.

In `expa` mode **who you are and what you may do** are real. The membership-summary
methods, the LCs/terms/teams in the reference data, Profile's custom fields and
position history, and the Admin console's People and Memberships methods come
from the real backend. Features whose endpoints are not wired up yet still
come from the mock (see `docs/frontend.md`, "Real sign-in"). Where that mock data
can't load for a real user, the page shows an error message rather than spinning.

The mock lives only in the browser and cannot issue a valid backend session.
The backend accepts only its own server-side session cookie, so mock mode can
never grant real access (spec §2A.3).

## Frontend sign-in and session handling

The frontend uses `api/expaSession.ts` to wrap the underlying `Api`
implementation. It replaces only the authentication methods, leaving the
membership, reference data, Profile and Admin methods to the underlying API.

- **Sign in:** `signIn()` navigates the browser to `/api/v1/auth/login`.
  This is a browser navigation, not a `fetch` call: the backend redirects
  the browser to EXPA, and EXPA redirects it back to the backend's callback.
  The frontend does not exchange the authorization code or handle EXPA tokens.
- **Who is signed in:** `getMe()` calls `GET /api/v1/me` with
  `credentials: 'same-origin'`. The browser sends the session cookie
  automatically. A 401 means there is no valid session and returns `null`.
  Other failures are reported to the sign-in page rather than being treated
  as a successful sign-in.
- **Sign out:** `signOut()` sends `POST /api/v1/auth/logout` with the
  session cookie. The backend revokes the session and clears the cookies.
  The provider clears its signed-in person after the request succeeds.

`AuthProvider` loads `/me` when the app starts. This is also how it picks up a
successful EXPA sign-in: the callback sends the browser back to the app, the
app loads again, and `/me` identifies the new session. There is no frontend
OAuth callback handler, token refresh process or authentication SDK.

The provider holds the `Me` payload for the whole app. Navigation, route
guards and page actions are derived from that payload, so the frontend uses
the same permissions that the backend resolved. This does not replace the
backend's permission checks on individual requests.

Positions in the `/me` response are looked up by key against the frontend's
reference data. An unknown position gets the most restrictive defaults.
The sign-in wrapper takes those positions from the local reference data
rather than making another backend request, so a broken reference-data
endpoint does not prevent someone signing in.

## Same-origin API requests

All frontend API requests use relative `/api` URLs. The browser sends them
to the same origin that served the frontend, and the hosting layer forwards
them to the backend:

| Environment | Browser origin | Where `/api/**` goes |
|---|---|---|
| Local (native) | `http://localhost:5173` | Vite proxy → `http://localhost:8000` |
| Local (Docker Compose) | `http://localhost:5173` | Vite proxy → `http://backend:8000` |
| Dev | `https://members-dev.aiesecaustralia.org` | Firebase Hosting → dev Cloud Run service |
| Prod | `https://members.aiesecaustralia.org` | Firebase Hosting → prod Cloud Run service |

The Vite development proxy is configured in `frontend/vite.config.ts`.
`API_PROXY_TARGET` can override its target when needed; Docker Compose sets
it automatically. It is a development-server setting, not a browser setting.

On a deployment, `FRONTEND_ORIGIN` and `APP_BASE_URL` are the same public
origin. Firebase serves both the frontend and `/api`, and the backend's
cookies are marked Secure because the public URL uses HTTPS.

There is no `VITE_API_URL` to configure per environment. The same production
frontend build can be served on dev and prod, with the hosting layer
forwarding requests to the appropriate backend.

See `docs/local-development.md` for running the local stack, and
`docs/superpowers/specs/2026-11-09-gcp-deployment-design.md` for the deployment
design.

## Checking it works

The frontend tests use a fake backend and a fake browser navigation, so
they do not need EXPA credentials or a running API. The backend tests
exercise the OAuth exchange and session handling with a stubbed EXPA
provider.

| Try | Expect |
|---|---|
| Open the app without a valid session | the sign-in page |
| Select "Sign in with EXPA" | the browser visits `/api/v1/auth/login` and is redirected to EXPA |
| Sign in with an allowed EXPA account that has an active membership | Home |
| EXPA account with no matching person row, or no active membership | sign-in page with the fixed not-allocated message |
| EXPA account outside the allowed email domains | sign-in page with the AIESEC account message |
| Cancel sign-in on EXPA | sign-in page with the cancellation message |
| Return with missing or expired OAuth state | sign-in page with the expired-attempt message |
| Use the app after the session expires or is revoked | next protected request gets 401, and the app returns to sign-in |
| Attempt an action without permission | 403; the person remains signed in |
| Profile menu → Sign out | session revoked, back on sign-in |
| Production build with `VITE_AUTH_MODE=mock` | real EXPA sign-in, not the development placeholder |

If `/auth/login` answers **503**, the backend's `EXPA_CLIENT_ID` or
`EXPA_CLIENT_SECRET` is not configured. Check the backend environment,
not the frontend: the browser does not need either credential.

If the browser returns to sign-in with `error=expired`, check that the
registered callback URL, public API origin and cookie handling agree.
If it returns with `error=expa`, check the backend's EXPA OAuth and GIS
configuration.

Frontend checks (from `frontend/`):

- `npm run lint`
- `npx tsc --noEmit`
- `npm run test`
- `npm run build`

The authentication tests are in `src/test/expaSession.test.tsx` and
`src/test/authMode.test.ts`. Cookie-based HTTP requests and 401 notifications
are covered in `src/test/httpApi.test.ts`.

A passing test suite does not prove that live EXPA sign-in works. Before
DEV-83 is accepted, someone other than the implementer must confirm a
manual sign-in on `members-dev.aiesecaustralia.org` against EXPA staging.
This also checks the registered callback, Firebase's forwarding of API
requests and cookies, and the deployed backend's configuration.

## Not built yet

- **The permission matrix as a database table** (spec §3.3): `/me` reads the in-code
  `BASELINE_PERMISSION_MATRIX` through `resolve_permissions` until then.
- **Frontend pages on real data**: features whose backend endpoints are not
  wired into `httpApi.ts` still read the mock API, even under real sign-in.
  See `docs/frontend.md` for which methods use the real backend.
- **Admin console sign-in** (spec §2A.2): the Admin console uses the same
  authentication provider and permission payload as the main app. Its
  dedicated sign-in page and return destination still need to be aligned
  with the EXPA flow.
- **Queueing unmatched sign-ins for an admin** (spec §9, optional).
