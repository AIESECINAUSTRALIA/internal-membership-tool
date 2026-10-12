# Authentication (sign in with an aiesec.net Google account)

How people sign in to the Membership Tool, how the backend knows who they are, and the
one-time setup needed to make it work. Written for someone with no prior context.
Spec: §9 (Authentication) and §2A.3 (Sign in).

---

## The short version

- People sign in with their **AIESEC Google account** (`@aiesec.net`). There are no
  passwords, no sign-up form and no custom auth code: **Supabase Auth** does the sign-in.
- The backend gets a short-lived **token** from the browser on every request, checks it,
  and matches the email to a row in `person` (`person.aiesec_email`).
- Email matched, active membership → in. Email matched but no active membership, or no
  match at all → the **not-allocated page**. Not an allowed domain (e.g. a personal
  Gmail) → rejected on the sign-in page.

## The flow

```
 Browser                    Google           Supabase Auth               Our API (FastAPI)
    │  click "Sign in with Google"                 │                            │
    │ ───────────────────────────────────────────▶ │  /auth/v1/authorize        │
    │ ◀──────── redirect to Google ─────────────── │                            │
    │ ──── choose aiesec.net account ──▶ │         │                            │
    │ ◀──── back to Supabase ─────────── │ ──────▶ │  (Supabase checks Google)  │
    │ ◀──────── redirect to /sign-in?code=… ────── │                            │
    │  supabase-js swaps the code for a session (access token = JWT)           │
    │                                                                           │
    │  GET /api/v1/me   Authorization: Bearer <access token>  ───────────────▶ │
    │                       verify signature with Supabase's public keys (JWKS) │
    │                       check expiry, issuer, audience, email domain        │
    │                       email → person → active memberships                 │
    │ ◀─────────────────────── { person, memberships, permissions } ────────── │
```

Where the code lives:

| Piece | File |
|---|---|
| Supabase client (browser) | `frontend/src/auth/supabaseClient.ts` |
| Sign-in / sign-out / `getMe` against the backend | `frontend/src/api/supabaseSession.ts` |
| Choosing mock or real sign-in | `frontend/src/api/index.ts` (`VITE_AUTH_MODE`) |
| The signed-in state, reacting to session changes | `frontend/src/auth/AuthProvider.tsx` |
| Token verification | `backend/app/core/auth.py` |
| FastAPI dependencies (`CurrentUser`, `CurrentPerson`, `CurrentActor`, `DbSession`) | `backend/app/api/deps.py` |
| Permissions for `/me` (`resolve_permissions`) | `backend/app/core/permissions.py` |
| Sign-in audit entry | `backend/app/api/v1/auth.py` (`_record_sign_in_once`), `backend/app/core/audit.py` |
| Production default for the sign-in mode | `frontend/src/api/authMode.ts` |
| `GET /api/v1/me` | `backend/app/api/v1/auth.py` |
| Settings (`SUPABASE_URL`, `ALLOWED_EMAIL_DOMAINS`) | `backend/app/config.py` |

## Design decisions (and why)

**Supabase Auth, not our own login.** Spec §9 and `CLAUDE.md` require managed OAuth.
Supabase handles Google, sessions and token refresh. We never see a password or a Google
token, and there is no "users" table of our own: `person` is the only identity table.

**Verify tokens with Supabase's public keys (JWKS), not a shared secret.** Supabase signs
access tokens with a private key (ES256) and publishes the public half at
`<SUPABASE_URL>/auth/v1/.well-known/jwks.json`. The backend downloads it (and caches it)
and checks each token's signature. So the backend needs only `SUPABASE_URL`, and there is
no JWT secret to leak or rotate. Only ES256 is accepted, which blocks the classic
"algorithm confusion" trick of signing a token with the public key as an HMAC secret.

**The backend enforces the email domain, not Google.** `ALLOWED_EMAIL_DOMAINS` (default
`aiesec.net`, comma-separated) is checked on **every request**. The domain must match
exactly: `x@notaiesec.net` and `x@aiesec.net.evil.com` are rejected. The frontend passes
`hd=aiesec.net` to Google (`VITE_GOOGLE_HOSTED_DOMAIN`), but that only filters Google's
account picker and anyone can strip it, so it is never the security check. Adding a domain
is a config change, not a code change (spec §9 TODO: confirm the full list of domains).

**Email match is case-insensitive.** Both sides are lower-cased before comparing.

**An `ANONYMISED` person can never sign in.** After a deletion request (spec §8) the row
counts as "no match".

**"Signed in, no access" is not an error.** `/me` answers 200 with `person: null` (no
match) or an empty `memberships` list (term ended / not started). The frontend shows the
not-allocated page with the spec's fixed wording.

**Permissions come from the server, in the frontend's own shape.** `/me` returns every
(resource, action, scope) the person holds: the union of the grants of all their
**active** memberships, keeping the **widest** scope where two overlap (spec §3.2). For
example LCVP oGV plus Team Leader BD gives `membership:edit` at `function`, not `team`.
This is `resolve_permissions` in `backend/app/core/permissions.py`, the one place `/me`
reads the matrix. Today the matrix is the `BASELINE_PERMISSION_MATRIX` list in that file
(from PR #18). When it moves to a database table (spec §3.3), only that function's data
source changes. An ended or future membership grants nothing, so access stays
deny-by-default. The frontend only uses the list to decide what to *show*; every feature
endpoint checks again on the server.

**Each sign-in is written to `audit_log`** (spec §9, §8.4), with `record_audit` from
`backend/app/core/audit.py`. The frontend calls `/me` on every page load, and a reload
is not a sign-in. So `/me` writes an `auth.sign_in` entry only the **first time it sees a
Supabase session**: the token's `session_id` claim stays the same across token refreshes
and changes on each new sign-in, and it is stored in the entry's `diff`. Entries are
permanent, so they never contain personal data: the person is referred to by id
(`actor_person_id`), and an email that matches nobody is logged with no ids and no email.
Two first requests at the exact same moment could both write an entry. A duplicate
sign-in line is harmless, so there is no lock. Rejected sign-ins (wrong domain, bad
token) are not logged.

**No backend sign-in stub.** Feature endpoints (`api/v1/members.py`) get the caller from
the same verified token (`get_current_actor` in `backend/app/api/deps.py`). An earlier
development stub trusted an `X-Actor-Email` header. It has been removed, and a test checks
the header alone gets a 401.

**Session expiry.** Supabase refreshes the token in the background. If refreshing fails or
the backend answers 401, the frontend signs out locally and the guards send the person to
`/sign-in`. There is no separate "session expired" page (spec §9).

**PKCE.** The browser gets a one-time `code` back from Supabase rather than a token in the
URL (`flowType: 'pkce'`).

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

## One-time setup (Supabase + Google)

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
  read the mock API, even under real sign-in. Wiring them to `/api/v1/members` is a
  separate ticket.
- **Admin console sign-in** (spec §2A.2): will reuse this same provider.
- **Queueing unmatched sign-ins for an admin** (spec §9, optional).
