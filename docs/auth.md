# Authentication (sign in with an aiesec.net Google account)

> **Being replaced: sign-in is moving to EXPA.** Decided 2026-11-09. This page still
> describes the code as it is today: Google sign-in through Supabase Auth (DEV-36). After
> the EXPA sign-in tickets land:
>
> - People sign in with their **EXPA account** (`auth.aiesec.org`; EXPA staging on the dev
>   environment).
> - The **backend** runs the OAuth exchange, reads `currentPerson { id aiesec_email }`
>   from the GIS API, and discards EXPA's tokens.
> - It matches on a new `person.expa_id`, falling back to `aiesec_email` on first sign-in.
> - The browser gets our own 12-hour server-side session in an HttpOnly `__session`
>   cookie.
> - `@supabase/supabase-js` is removed with no replacement.
>
> These stay as they are: the `ALLOWED_EMAIL_DOMAINS` check, the not-allocated rules,
> `/me`, permission resolution, the sign-in audit entry and "no backend sign-in stub".
>
> Full design: §5.4 of `docs/superpowers/specs/2026-11-09-gcp-deployment-design.md`. This
> page gets rewritten for EXPA in the same PR as the backend change. Don't do new Supabase
> setup.

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

The frontend authentication files are deliberately not listed here. They
still implement Supabase sign-in and will be updated under DEV-83.

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
authentication cookies. The frontend's redirect and session-expiry UI
behaviour will be updated in DEV-83.

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

> **Frontend transition (DEV-83).** The sections below describe the
> current Supabase-based frontend and are retained until DEV-83 changes
> that code. They are not instructions for authenticating against the
> DEV-82 backend: the backend now accepts only its own EXPA-derived
> `__session` cookie. Real frontend sign-in will not work end-to-end
> until DEV-83 is completed.
>
## Mock mode vs real sign-in

`VITE_AUTH_MODE` (frontend) picks how sign-in works:

| Value | What you get | Needs |
|---|---|---|
| `mock` | The development "Sign in" button and the `?as=` personas (`docs/frontend.md`). No Google, no backend. **Default for the dev server and tests.** | nothing |
| `supabase` | "Sign in with Google", checked by `GET /api/v1/me`. **Default for production builds** (`npm run build`). | The Supabase + Google setup below, and the backend running |

When `VITE_AUTH_MODE` is unset, `frontend/src/api/authMode.ts` picks by build type, so a
deployed build is real sign-in unless someone explicitly sets `VITE_AUTH_MODE=mock`
(spec §2A.3: the placeholder must be off in any deployed environment). A production build
without `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` stops at startup with an error,
rather than falling back to the mock.

In `supabase` mode **who you are and what you may do** are real. The other pages' data
(member lists, reference data, the homepage chart) still comes from the mock until the
frontend is wired to the backend endpoints. Where that mock data can't load for a real
user, the page shows an error message rather than spinning. The mock lives only in the browser and the backend trusts only
Supabase-signed tokens, so mock mode can never grant real access (spec §2A.3).

## One-time setup (Supabase + Google; legacy frontend, DEV-83)

Do this **once per Supabase project** (local/dev, and later production). Use the
**AIESEC Australia-owned** Google and Supabase accounts, never a personal one
(`CLAUDE.md`: no single point of failure, everything owned by the entity).

1. **Google Cloud: create the OAuth client**
   1. In Google Cloud Console (an AIESEC-owned project): *APIs & Services → OAuth consent
      screen*. Pick **Internal** if the aiesec.net Workspace admin allows it (then only
      aiesec.net accounts can even reach the consent screen), otherwise **External**. App
      name "AIESEC Australia Membership Tool". Scopes: `openid`, `email`, `profile` only.
   2. *Credentials → Create credentials → OAuth client ID → Web application*.
   3. **Authorised redirect URI**: `https://<your-project>.supabase.co/auth/v1/callback`
      (Supabase shows the exact value on its Google provider page).
   4. Copy the **Client ID** and **Client secret**.
2. **Supabase: turn on Google**
   1. *Authentication → Sign In / Providers → Google*: enable it, paste the Client ID and
      secret.
   2. Turn **off** the providers we don't use (email/password, magic link, phone), so
      Google is the only way in.
   3. *Authentication → URL Configuration*: set **Site URL** to the frontend address and add
      every frontend address to **Redirect URLs**, with `/**`:
      `http://localhost:5173/**` for local, plus the Vercel preview and production URLs.
3. **Store the secrets.** Put the Google client secret in the shared **Bitwarden**
   collection (`docs/local-development.md` → "Where the real values live"). It lives only
   in Google and Supabase. The app never reads it.
4. **Configure the app** (`.env`, from `.env.example`):

   ```bash
   SUPABASE_URL=https://<your-project>.supabase.co      # backend
   ALLOWED_EMAIL_DOMAINS=aiesec.net                     # backend
   VITE_SUPABASE_URL=https://<your-project>.supabase.co # frontend
   VITE_SUPABASE_ANON_KEY=<publishable / anon key>      # frontend, browser-safe
   VITE_API_URL=http://localhost:8000                   # frontend
   VITE_AUTH_MODE=supabase                              # frontend
   VITE_GOOGLE_HOSTED_DOMAIN=aiesec.net                 # frontend, optional hint
   ```

   Then `make up`. `VITE_*` values are read when the frontend starts or builds, so restart
   it after changing them.
5. **Make sure you exist in `person`.** Sign-in only works for an email in
   `person.aiesec_email` with an active `membership`. Until the Admin console exists, add
   yourself with SQL or a seed.

## Checking it works

| Try | Expect |
|---|---|
| Sign in with an `@aiesec.net` account that has an active membership | Home |
| `@aiesec.net` account with no `person` row, or a term that ended | the not-allocated page |
| A personal Gmail | back on sign-in with "Only AIESEC accounts can sign in…" |
| Profile menu → Sign out | back on sign-in |
| `curl localhost:8000/api/v1/me` (no token) | 401 |

If `/me` answers **503**, `SUPABASE_URL` is empty on the backend, or the backend can't
reach Supabase to download its public keys.

## Not built yet

- **The permission matrix as a database table** (spec §3.3): `/me` reads the in-code
  `BASELINE_PERMISSION_MATRIX` through `resolve_permissions` until then.
- **Frontend pages on real data**: the member list, Tracking and the homepage chart still
  read the mock API, even under real sign-in. Wiring them to the membership summary API
  (DEV-0042, `/api/v1/members`) is a separate ticket.
- **Admin console sign-in** (spec §2A.2): will reuse this same provider.
- **Queueing unmatched sign-ins for an admin** (spec §9, optional).
