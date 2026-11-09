# Design: deploying the Membership Tool on Google Cloud, with EXPA sign-in

**Status:** approved by the Tech Lead, 2026-11-09. Not built yet. Tickets:
`tickets_sprint_6.md` (N1–N15).
**Date:** 2026-11-09
**Replaces:** Supabase (auth + interim DB) and Vercel (temporary frontend hosting).

Written for a reader with no prior context. Anything marked **[verify]** is a price, limit or
behaviour taken from research or a guess. Check it before relying on it.

---

## 1. Why we're doing this

- **One platform.** The Tech Lead wants all deployment and hosting for the Membership Tool in
  **one tool: Google Cloud (GCP)**. That means one bill, one access model, and one set of
  docs for next year's team to learn. Supabase and Vercel both go.
- **Sign-in moves to EXPA.** People sign in with their **EXPA account**, AIESEC's own OAuth
  provider at `auth.aiesec.org`. This replaces the Google-via-Supabase sign-in merged in
  DEV-36 (#21) on 2026-11-08. EXPA owns the login, so there are still no passwords or
  custom auth system of ours (`CLAUDE.md`).
- **Two environments:**
  - **dev** is for testing. Every merge to `main` lands there.
  - **prod** only ever runs released, tested code.

  The showcase MVP is the first prod deployment, on demo data. About a month later it
  becomes v1 with real data.

## 2. Goals, non-goals, anti-goals

**Goals**
- dev and prod running on GCP in Sydney (`australia-southeast1`), at
  `members-dev.aiesecaustralia.org` and `members.aiesecaustralia.org`.
- EXPA sign-in end to end: dev uses EXPA staging, prod uses EXPA production.
- Deploys from GitHub Actions with no long-lived keys. Releases to prod are deliberate,
  approved promotions of an image already tested on dev.
- Within **~$500 AUD/year**, shared with the website project, with budget alerts.
- Owned by AIESEC Australia, with ≥2 people able to do every admin task, access through
  groups, and an offboarding checklist.
- Docs that let next year's team deploy, roll back, restore and hand over without asking
  anyone.

**Non-goals (this term)**
- Moving the main website (`aiesecaustralia.org`, WordPress on Hostmate) or its DNS. That
  belongs to the national team.
- Using EXPA positions to grant access. Permissions stay in our own position × function
  matrix (spec §3). Syncing positions from EXPA is **Phase 2**.
- Calling the GIS API on a user's behalf, beyond reading who they are at sign-in (**Phase 2**).
- Automated report generation, scheduled exports, the deletion-request workflow (spec §8),
  and website ↔ tool integration. All **Phase 2**, per `CLAUDE.md`.
- High availability, multi-region and load balancers. They cost more than the budget allows
  and the scale doesn't need them.
- Terraform (see §9).

**Anti-goals (it fails even if it "works" if…)**
- …it only works because one person knows the setup, holds the only admin login, or owns
  the EXPA developer app on a personal account.
- …the bill quietly passes $500 AUD/year, or a budget "cap" deletes production.
- …real member data reaches dev, the showcase, a log line, a CDN cache or an export.
- …a backup keeps anonymised personal data around indefinitely.
- …a test or mock login can grant real access in any deployed environment.

## 3. Constraints (hard)

From `CLAUDE.md` and the conversation:
- Annual turnover. Choose boring, managed, documented tools. Grant access by role/group
  (≥2 people per capability), not to named individuals.
- **Budget:** ≤ ~$500 AUD/year across both projects, including domain. **No Google for
  Nonprofits credits** (not approved), so plan with none.
- No free tier that auto-expires data. Managed OAuth only.
- Data stays in Sydney where we control it (Privacy Act / APP).
- Files go in object storage, never DB rows.
- Everything is owned by AIESEC Australia: the GCP organization and billing account,
  GitHub, the EXPA developer account, Cloudflare, Squarespace.
- Don't commit or push without the Tech Lead's say-so.

## 4. What exists today (verified in the repo, 2026-11-09)

- **Supabase Auth is built and in use**, not just installed:
  - `backend/app/core/auth.py` verifies Supabase JWTs (ES256, JWKS, `session_id` claim).
  - `backend/app/config.py` has `supabase_url`.
  - The frontend uses `frontend/src/auth/supabaseClient.ts`, `api/supabaseSession.ts`,
    `AuthProvider.tsx` and `authMode.ts` (mode `supabase`).
  - Tests: `frontend/src/test/supabaseSession.test.tsx`, `authMode.test.ts`, and
    `backend/tests/auth/*`.
  - Docs: `docs/auth.md`.
- **Already provider-neutral and staying:**
  - `ALLOWED_EMAIL_DOMAINS` and the exact-domain check.
  - Matching to `person.aiesec_email`.
  - `resolve_permissions` and `GET /api/v1/me`.
  - The sign-in `audit_log` entry.
  - `CurrentUser` / `CurrentPerson` / `CurrentActor` in `api/deps.py`.
  - The "no backend sign-in stub" rule.
- `docs/supabase-schema-changes.md` says the Supabase database is "only used for sign-in". So
  far there is **no member data in Supabase to move** **[verify with a row count before
  deleting the project]**.
- Vercel is listed in `docs/external-services.md` as temporary frontend hosting.
- `backend/Dockerfile` and `frontend/Dockerfile` are **dev-only** (`--reload`, Vite dev server).
- CI (`.github/workflows/backend.yml`, `frontend.yml`) runs checks only. Nothing deploys.
- **Domain facts** (public DNS/WHOIS):
  - Registered via Squarespace Domains (registrar Tucows), **expires 2027-10-23**.
  - DNS is on **Cloudflare**.
  - Email is Google Workspace (`hello@aiesecaustralia.org`).
  - No GCP organization exists yet.
- EXPA docs are in `12. Dev guides/`: the auth flow, developer app, staging, and the GIS
  GraphQL schema. They're **kept out of git** by Tech Lead decision; they're AIESEC
  International's material.

## 5. Architecture

```
                        Browser
                           │  https://members.aiesecaustralia.org   (prod)
                           │  https://members-dev.aiesecaustralia.org (dev)
                           ▼
   Cloudflare DNS ── record set to "DNS only" (grey cloud) ──▶  Firebase Hosting
                                                                │  serves the React build (static)
                                                                │  rewrites /api/** ─────────────┐
                                                                                                 ▼
   auth.aiesec.org  ◀── code exchange (server→server) ──  Cloud Run service "mt-api" (Sydney)
   gis-api.aiesec.org/graphql ◀── currentPerson query ──   FastAPI container from Artifact Registry
                                                                │  built-in Cloud SQL connection (unix socket)
                                                                ▼
                                                   Cloud SQL Postgres 16 (Sydney), one instance
                                                     ├── database "membership_prod"
                                                     └── database "membership_dev"
   Secret Manager: DB passwords, EXPA client secrets │ Cloud Logging / Error Reporting / uptime check
```

### 5.1 Why this shape (decided)

- **Firebase Hosting in front, not a load balancer.**
  - Cloud Run can't attach a custom domain directly in `australia-southeast1`
    **[verify: Cloud Run locations page, domain-mapping list]**.
  - Google's suggested workaround, a load balancer, costs about **US$0.025/hour (~AU$330/yr)**
    **[verify]**, roughly two-thirds of the budget.
  - Firebase Hosting gives the custom domain, free managed SSL and a CDN for the static
    build, and forwards `/api/**` to Cloud Run.
  - Frontend and API share **one origin**, so there's no production CORS and the cookie is
    simple.
- **Cookie name must be `__session`.** When Firebase Hosting forwards to Cloud Run it
  removes every cookie except `__session` **[verify on Firebase "manage cache" docs]**.
- **API responses must send `Cache-Control: private, no-store`.** Firebase Hosting can cache
  forwarded responses at its CDN. Without this header, one person's data could be cached.
  Add it as backend middleware on every `/api` response.
- **The Firebase project may need the pay-as-you-go "Blaze" plan** to forward to Cloud Run
  **[verify]**. At our traffic this should cost ~$0.
- **Cloud SQL: one shared-core instance** holding both databases. Two instances would push
  past budget (§11). dev and prod are kept apart by separate databases and separate DB users
  (§5.3).

### 5.2 Cloud Run (backend)

| Setting | dev | prod | Why |
|---|---|---|---|
| Region | `australia-southeast1` | same | data residency |
| Min instances | 0 | 0 | scale to zero = ~free; first request after idle takes a few seconds (accepted) |
| Max instances | 1 | 3 | caps cost and DB connections |
| CPU / memory | 1 vCPU / 512 MiB | same | FastAPI is light |
| Concurrency | 40 | 40 | default-ish; DB pool is the real limit |
| CPU allocation | request-only | request-only | cheapest |
| Ingress | all | all | Firebase Hosting calls it over the internet **[verify whether "internal + Firebase" is possible]** |
| Invoker | allow unauthenticated | same | browsers call it; our app does auth |
| Runtime service account | `mt-api-dev@` | `mt-api-prod@` | least privilege (§10) |

- **Production image.** Add a `prod` stage to `backend/Dockerfile`:
  - non-root user, no `--reload`
  - `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'`,
    so the app sees `https` behind Google's front end.
- **DB pool:** SQLAlchemy `pool_size=5, max_overflow=2` per instance. Worst case is
  3×7 (prod) + 1×7 (dev) + migration jobs. That's under the micro instance's connection
  limit **[verify the limit for the chosen tier]**.

### 5.3 Cloud SQL (database)

| Setting | Choice | Why / trade-off |
|---|---|---|
| Edition / tier | Enterprise, shared-core smallest (`db-f1-micro`), Postgres 16 | cheapest; **no SLA** on shared-core (accepted for MVP, revisit if it hurts) |
| Region | `australia-southeast1`, zonal (no HA) | HA doubles cost |
| Storage | 10 GB SSD, auto-increase on | data is small (spec §10) |
| Connection | Cloud Run's built-in Cloud SQL connection (unix socket `/cloudsql/…`); public IP with **no authorised networks**; require SSL | no VPC / proxy to manage. People connect only via `gcloud`'s Cloud SQL Auth Proxy with their IAM identity |
| Backups | automated daily, **7 retained**; point-in-time recovery on, 7 days of logs | meets spec §10 "≥ every 24 h"; 7 days is the privacy bound (§12) |
| Maintenance window | Sunday 03:00 Sydney | quietest |
| Deletion protection | **on** | deleting the instance deletes its automated backups |
| Databases | `membership_prod`, `membership_dev` | |
| Users (per env) | `mt_migrator_<env>` (owns the schema, used only by the migration job); `mt_app_<env>` (runtime login) | dev users have **no** `CONNECT` on the prod DB and vice versa (`REVOKE CONNECT … FROM PUBLIC`, then grant per env) |
| Runtime grants | a shared NOLOGIN group role **`mt_runtime`**, granted to both `mt_app_dev` and `mt_app_prod`. Migrations grant table rights to `mt_runtime`, never to an env-specific name, so one migration works in both DBs. `mt_runtime` gets DML on tables but only `INSERT`/`SELECT` on `audit_log` | spec §8.4's database-level append-only protection. Roles are instance-wide, but table grants live inside each database, and `CONNECT` keeps the envs apart |

Connection string in Secret Manager, one per env and user:
`postgresql+psycopg://mt_app_prod:<pw>@/membership_prod?host=/cloudsql/<PROJECT>:australia-southeast1:<INSTANCE>`

### 5.4 Sign-in with EXPA (replaces Supabase Auth)

From the EXPA guides in `12. Dev guides/`. EXPA is classic OAuth2:
- authorize at `auth.aiesec.org/oauth/authorize`
- token at `auth.aiesec.org/oauth/token`, using the client secret
- access token lasts ~2 h and comes with a refresh token
- "who am I" is the GIS GraphQL query `currentPerson { id aiesec_email … }`
- **redirect addresses must be https**

```
Browser                         Our API (Cloud Run)                       EXPA
  │ click "Sign in with EXPA"            │                                   │
  │ GET /api/v1/auth/login ────────────▶ │ create pending session row        │
  │                                      │ (random `state`), set __session   │
  │ ◀──── 302 to auth.aiesec.org/oauth/authorize?response_type=code&client_id&redirect_uri&state
  │ ─────────────── sign in on EXPA ─────────────────────────────────────▶   │
  │ ◀──── 302 to /api/v1/auth/callback?code=…&state=… ──────────────────────  │
  │ GET /api/v1/auth/callback ─────────▶ │ check state matches pending row   │
  │                                      │ POST /oauth/token (client secret) ▶│
  │                                      │ ◀──────────── access_token        │
  │                                      │ query currentPerson ─────────────▶│ (GIS GraphQL)
  │                                      │ ◀── id, aiesec_email              │
  │                                      │ discard EXPA tokens               │
  │                                      │ match → person; new session id;   │
  │                                      │ audit_log "auth.sign_in"          │
  │ ◀── 302 to / , Set-Cookie: __session=<new id>; HttpOnly; Secure; SameSite=Lax; Path=/
  │ GET /api/v1/me (cookie) ───────────▶ │ session → person → memberships → permissions
```

**Decided:**
- **The backend does the whole exchange.** The browser never sees EXPA's tokens, the client
  secret stays in Secret Manager, and the frontend needs **no auth SDK**
  (`@supabase/supabase-js` is removed, and nothing replaces it).
- **We don't keep EXPA's tokens.** We only need to know who the person is. Storing a
  credential that can read EXPA data would be risk with no benefit (Phase 2 can revisit).
- **Matching:**
  - First sign-in matches `currentPerson.aiesec_email` (lower-cased) to
    `person.aiesec_email`, then stores `currentPerson.id` in a new **`person.expa_id`**
    (unique, nullable).
  - Later sign-ins match on `expa_id` first. A changed email then doesn't lock anyone out.
  - The `ALLOWED_EMAIL_DOMAINS` exact-domain check stays, applied to `aiesec_email`.
  - No match, no active membership, or an `ANONYMISED` person → the not-allocated page,
    exactly as today.
- **Our own sessions, stored server-side.** New table `user_session`:
  - `id` (we store a SHA-256 of a 256-bit random token; the cookie holds the token)
  - `person_id` (nullable while pending), `state` (while pending)
  - `created_at`, `expires_at`, `revoked_at`

  Rules:
  - **Absolute lifetime 12 h**, no sliding renewal. EXPA usually remembers the login, so
    signing in again is one click.
  - Server-side so a leaver or a compromised session can be revoked instantly (delete or
    revoke the rows).
  - Log out = revoke the row + clear the cookie.
  - Rotate the session id at callback, so a pending id can't be fixed in advance.
  - Expired rows are purged on sign-in, or by a small periodic cleanup (builder's choice).
- **CSRF:**
  - OAuth `state` protects the login itself **[verify EXPA honours `state`; it's a standard
    Doorkeeper param]**.
  - For the API: `SameSite=Lax` plus an **`Origin` header check** on every non-GET request
    against `APP_BASE_URL`.
- **Sign-in audit.** One `auth.sign_in` entry per new session, no email in it. The
  Supabase `session_id` trick goes away, because a session row now marks "a new sign-in".
- **Environments:**
  - dev ↔ **EXPA staging** (`auth-staging.aiesec.org`, `staging-jruby.aiesec.org/graphql`)
  - prod ↔ **EXPA production** (`auth.aiesec.org`, `gis-api.aiesec.org/graphql`)
  - Each has its own developer application, both owned by the **shared MC-level EXPA
    developer account** (credentials in Bitwarden).
  - App type "Member facing" **[verify the right type with AIVP IM]**.
  - Callback URLs: `https://members.aiesecaustralia.org/api/v1/auth/callback` and
    `https://members-dev.aiesecaustralia.org/api/v1/auth/callback`.
- **Lead time:**
  - AIVP IM approves developer apps within **14 days**.
  - EXPA staging access is requested by emailing `vpis@ai.aiesec.org`, once per person who
    needs a staging login.
  - **Apply first. It's on the critical path.**

**New backend settings** (replace `SUPABASE_URL`):

| Variable | Example | Secret? |
|---|---|---|
| `EXPA_AUTH_URL` | `https://auth.aiesec.org` | no |
| `EXPA_GRAPHQL_URL` | `https://gis-api.aiesec.org/graphql` | no |
| `EXPA_CLIENT_ID` | from the developer app ("Application UID") | no |
| `EXPA_CLIENT_SECRET` | from the developer app | **yes** (Secret Manager) |
| `APP_BASE_URL` | `https://members.aiesecaustralia.org` | no (redirect URI + Origin check derive from it) |
| `SESSION_TTL_HOURS` | `12` | no |
| `ALLOWED_EMAIL_DOMAINS` | `aiesec.net` | no |
| `DATABASE_URL` | see §5.3 | **yes** |

**Frontend:**
- `VITE_AUTH_MODE` becomes `mock | expa`; production builds default to `expa`.
- "Sign in" sends the browser to `/api/v1/auth/login`.
- `getMe` is `fetch('/api/v1/me', { credentials: 'same-origin' })`.
- Sign out is `POST /api/v1/auth/logout`.
- The API is always the relative `/api`, so `VITE_API_URL` and all `VITE_SUPABASE_*` go.
  **One frontend build works in both environments.**
- In local dev, Vite's `server.proxy` forwards `/api` to the backend, keeping local
  same-origin too.

### 5.5 Supporting services

- **Artifact Registry**
  - One Docker repo `mt` in `australia-southeast1`, in the **prod** project.
  - dev pulls from it, so the exact image tested on dev is what prod runs.
  - Cleanup policy: keep the last 15 images plus anything tagged `v*`.
- **Secret Manager**
  - Per env: `database-url-app`, `database-url-migrator`, `expa-client-secret`.
  - Mounted into Cloud Run as env vars, pinned to `latest` and re-deployed on rotation.
- **Logging**
  - Cloud Run stdout/stderr → Cloud Logging (default 30-day retention).
  - **Rule: never log emails, names, tokens or cookies.** Log ids only.
- **Error Reporting** picks up Python stack traces from Cloud Run automatically.
- **Monitoring and alerts:** see §13.
- **Cloud Storage**
  - Not needed yet: no uploads exist.
  - When the first upload feature lands: one bucket per env in `australia-southeast1`,
    uniform access, no public access, served through the API.

## 6. Environments and promotion

| | dev | prod |
|---|---|---|
| GCP project | `aiesec-au-mt-dev` | `aiesec-au-mt-prod` (also holds Cloud SQL + Artifact Registry) |
| URL | `members-dev.aiesecaustralia.org` | `members.aiesecaustralia.org` |
| EXPA | staging | production |
| Data | seed/demo only, may be reset any time | demo for the showcase, then wiped and loaded with real data for v1 |
| Deploys | automatically on every merge to `main` | only on a release tag, after approval |

**Two projects, not one.**
- In one project, "devs can deploy dev but not touch prod" needs per-resource IAM
  conditions, which are hard to read and easy to break.
- Two projects is the standard, boring split. `mt-developers` get edit rights on dev and
  view-only on prod.
- The cost of this choice: a few cross-project grants, listed in §10 and scripted in
  `infra/`:
  - dev's runtime account gets `cloudsql.client` on the prod project's instance; its DB
    password only opens `membership_dev`.
  - dev pulls images from prod's Artifact Registry.

**Promotion.** A release is a git tag `vX.Y.Z` on a commit already deployed to dev. The
release workflow:
1. Needs approval in the GitHub environment `production` (required reviewers: the
   `tech-leads` GitHub team, ≥2 members).
2. Retags the **existing** image `…/mt/api:<sha>` as `vX.Y.Z`. No rebuild.
3. Takes an on-demand Cloud SQL backup labelled with the release.
4. Runs the prod migration job (§8).
5. Deploys the image to prod Cloud Run.
6. Builds the frontend at the tag and deploys it to the prod Firebase site.

The frontend build is environment-independent, so this is equivalent to promoting it.
*[Builder's call: `firebase hosting:clone` from dev to prod instead, if it works across
projects.]*

**Showcase → v1 cutover** (a runbook section, not code):
1. Delete and recreate `membership_prod`.
2. Run migrations and the baseline seeds (no demo data).
3. Load real people and memberships.
4. Revoke all sessions.
5. Record it in the changelog.

## 7. Domain and DNS

- **Subdomains** of the existing domain: `members.` and `members-dev.aiesecaustralia.org`.
  No new domain is bought, so domain cost is **$0** for this project.
- **DNS stays on Cloudflare.** It holds the whole website's DNS, which the national team owns.
  Moving it to Cloud DNS would touch their site for little gain. This is the one recorded
  exception to "everything in GCP": the tool runs entirely on GCP, and only two DNS records
  live in Cloudflare.
- **Records:** Firebase Hosting's "Add custom domain" shows the exact records to add,
  usually A/AAAA plus a TXT verification **[verify in console]**. Add them in Cloudflare
  as **DNS only (grey cloud)**. A proxied (orange) record blocks Firebase's certificate.
- **SSL:** Firebase issues and renews certificates automatically once DNS resolves.
- **Ownership checks:** these go in `docs/access-and-ownership.md`, owner: Tech Lead + MC
  VP IM or equivalent.
  - **Squarespace Domains**
    - The account login is `hello@aiesecaustralia.org`.
    - The registrant organisation is AIESEC Australia (WHOIS is privacy-masked, so check
      inside the account).
    - **Auto-renew is on**, with an org-owned payment method.
    - Expiry **2027-10-23**, with a shared-calendar reminder 60 days before.
  - **Cloudflare:** the account owner is an org email, with ≥2 members with DNS edit.
  - **Hostmate:** listed for completeness; owned by the national team.
- **Transfer-out:** if the domain ever moves registrar:
  1. Unlock it in Squarespace and get the auth code.
  2. Start the transfer at the new registrar.
  3. Leave the nameservers on Cloudflare, so nothing breaks.

## 8. CI/CD (GitHub Actions)

- **Authentication: Workload Identity Federation**, no JSON keys.
  - One WIF pool/provider in the prod project, trusting
    `token.actions.githubusercontent.com`.
  - Attribute condition: the repository is `<org>/internal-membership-tool`.
  - Two deployer service accounts:
    - `gh-deploy-dev@` can be impersonated only by this repo's `main` branch.
    - `gh-deploy-prod@` can be impersonated only by jobs in the GitHub environment
      `production` (`assertion.environment == 'production'`).
- **Existing check workflows stay** (`backend.yml`, `frontend.yml`, path-filtered). New
  workflows:

| Workflow | Trigger | Does |
|---|---|---|
| `deploy-dev.yml` | push to `main` (after checks pass), path-filtered: backend and/or frontend | build `backend` prod image → push `api:<sha>` → run `mt-migrate-dev` job → deploy `mt-api` (dev). Frontend: `npm ci && npm run build` → `firebase deploy --only hosting` to dev site |
| `release-prod.yml` | push of tag `v*` | `environment: production` (approval) → retag image → on-demand backup → `mt-migrate-prod` job → deploy `mt-api` (prod) → build + deploy frontend to prod |
| `rollback-prod.yml` | manual (`workflow_dispatch`, input: tag) | `environment: production` → deploy that tag's image + rebuild that tag's frontend. **Does not** reverse migrations |
| `backup-cleanup.yml` | weekly cron | delete prod on-demand Cloud SQL backups older than 7 days (§12) |

`deploy-dev.yml` must deploy only after the existing checks pass. The builder chooses how:
call `backend.yml`/`frontend.yml` as reusable workflows (`workflow_call`) with `needs:`, or
trigger with `workflow_run`.

- **Migrations** run as a **Cloud Run Job** (`mt-migrate-<env>`):
  - Same image, command `alembic upgrade head`, runs as `mt_migrator_<env>`.
  - Ordering rule: run migrations, then deploy code.
  - So **every migration must be backward-compatible with the previous release**
    ("expand, then contract": add the column, ship the code, drop the old one in a later
    release). `docs/database-changes.md` teaches this.
- **Rollback:**
  - Code: redeploy the previous tag (≈1 minute).
  - Schema: write a new forward migration. If data is damaged, do a point-in-time restore
    (runbook).
  - Never run `alembic downgrade` on prod.
- **Path filtering:** a docs-only change deploys nothing.

## 9. Setup method: documented `gcloud` scripts, not Terraform (decided)

- **Why not Terraform?** It's the industry standard, but it brings a new language, a state
  file to host and lock, and "drift" errors. A team that changes every year, mostly 2nd-years,
  would likely stop trusting it and start clicking in the console anyway. Then two sources of
  truth would disagree.
- **Instead, `infra/`:**
  - Short, heavily commented bash scripts, one per concern:
    `00-org-and-projects.sh`, `10-cloudsql.sh`, `20-artifact-registry.sh`, `30-secrets.sh`,
    `40-cloud-run.sh`, `50-wif-github.sh`, `60-monitoring.sh`, `70-budget.sh`.
  - A shared `infra/env.sh` holds the names: project IDs, region, instance name.
  - Scripts are written to be **safe to re-run**: `describe || create`.
  - `docs/deployment.md` walks through them in order.
  - Console-only steps (Firebase custom domain, Workspace groups, EXPA apps, Cloudflare
    records) are numbered checklists.
- **Trade-off accepted:** nothing detects drift automatically. Mitigation: the scripts are
  the record. A console change must be copied back into the script in the same PR, and a
  checkbox in the PR template asks.

## 10. IAM and access model

**Hierarchy**
```
Organization: aiesecaustralia.org        (created once by a Workspace super admin)
└── Folder: membership-tool
    ├── Project: aiesec-au-mt-prod       (Cloud SQL, Artifact Registry, WIF, prod Cloud Run, prod Firebase)
    └── Project: aiesec-au-mt-dev        (dev Cloud Run, dev Firebase, dev secrets)
Billing account: "AIESEC Australia"      (AUD, org-owned card; linked to both projects)
```
A Workspace **super admin** of `aiesecaustralia.org` must create the Organization: sign in
to the Cloud console once, accept the org, and grant `gcp-org-admins@` Organization Admin.
If `hello@` isn't a super admin, whoever is does this once.

**Groups** (Google Workspace groups on `aiesecaustralia.org`; membership is by position, each ≥2 people)

| Group | Who (by role) | Grants |
|---|---|---|
| `gcp-org-admins@` | Tech Lead + MC VP IM (or MCP) | Organization Admin, Folder Admin. Rarely used |
| `gcp-billing-admins@` | Tech Lead + MC VP Finance | Billing Account Administrator; receives budget alerts |
| `mt-tech-leads@` | Tech Lead + a senior dev | `roles/owner` on both projects |
| `mt-developers@` | all devs | dev: `roles/editor` + `secretmanager.secretAccessor` + `cloudsql.client`. prod: `roles/viewer`, `logging.viewer`, `errorreporting.viewer`, `monitoring.viewer`. **No prod secrets, no prod DB** |
| `mt-alerts@` | Tech Lead + devs on call | alert notifications only (no GCP role) |

**Service accounts (least privilege)**

| SA | Project | Roles |
|---|---|---|
| `mt-api-prod@` | prod | `cloudsql.client`, `secretAccessor` on prod secrets only |
| `mt-api-dev@` | dev | `secretAccessor` on dev secrets; `cloudsql.client` **on prod project** (instance-level) ; `artifactregistry.reader` on the prod repo |
| `gh-deploy-prod@` | prod | `run.admin` (prod), `iam.serviceAccountUser` on `mt-api-prod@`, `artifactregistry.writer`, `cloudsql.admin` (for the on-demand backup), `firebasehosting.admin` |
| `gh-deploy-dev@` | dev | `run.admin` (dev), `iam.serviceAccountUser` on `mt-api-dev@`, `artifactregistry.writer` on prod repo, `firebasehosting.admin` (dev) |

**Break-glass:** `hello@aiesecaustralia.org` (already MC-shared via Bitwarden, 2FA backup codes
in Bitwarden) is a member of `gcp-org-admins@`. Use it only if both org admins are unavailable.
Each use is noted in the incident log.

**GitHub:** in the org's repo, Teams `tech-leads` (admin, required reviewers for `production`)
and `developers` (write). ≥2 org owners. No GCP secrets in GitHub, only *variables*: project
IDs, WIF provider name, region.

**Offboarding checklist** (in `docs/access-and-ownership.md`)
1. Remove the person from Workspace groups (this removes all GCP access).
2. Remove them from GitHub teams.
3. Remove them from the Bitwarden collection.
4. Remove them from Cloudflare / Squarespace / Jira / Snyk if they were members.
5. If they had prod secret access (tech leads): rotate the prod DB passwords and the EXPA
   prod client secret (runbook).
6. If they knew the shared EXPA developer account or `hello@` password: rotate it.
7. Revoke their app sessions: `UPDATE user_session SET revoked_at = now() WHERE person_id = …`.
8. Close their `membership` in the app (removes app access).
9. Hand over: update the owners table in `access-and-ownership.md` with the successor.

## 11. Cost model

GCP bills in the billing account's currency. **Prices below are research estimates
[verify all in the GCP pricing calculator for `australia-southeast1`], may exclude 10% GST
[verify], and assume ~1.55 AUD/USD.**

| Item | Assumption | AU$/month | AU$/year |
|---|---|---|---|
| Cloud SQL instance | `db-f1-micro`, Sydney (US ~$0.0105/h in us-central1; Sydney higher **[verify]**) | 13–17 | 155–205 |
| Cloud SQL storage + backups + PITR logs | 10 GB SSD + 7 days | 4–7 | 50–85 |
| Cloud Run (2 services, scale to zero) | inside monthly free allowance | 0–2 | 0–20 |
| Cloud Run Jobs (migrations) | a few runs a week | ~0 | ~0 |
| Firebase Hosting (2 sites) | static build ≪ 10 GB, low traffic | 0 | 0 |
| Artifact Registry | <1 GB with cleanup | 0–0.5 | 0–6 |
| Secret Manager | ~6–8 secret versions | 0–0.5 | 0–6 |
| Logging / Monitoring / uptime checks / Error Reporting | under free allowances | 0 | 0 |
| Domain | subdomains of existing domain | 0 | 0 |
| **Total (est.)** | | **~17–27** | **~205–320** (≈225–350 incl. GST) |

- The website's Hostmate hosting is **not** counted against this budget (Tech Lead,
  2026-11-09). That leaves comfortable headroom under $500, but the alert stays at
  AU$35/month so surprises show up early.
- **Budget setup** (`infra/70-budget.sh`):
  - One budget on the billing account: **AU$35/month**.
  - Alerts at 50%, 90%, 100% actual and 100% forecast.
  - Alerts go to `gcp-billing-admins@` and `mt-alerts@`.
- **No automatic billing cap.** GCP budgets only alert. An auto-cap means a script that
  disables billing, which **shuts down and can delete resources**, and that fails the
  anti-goals. Instead the runbook says what to do on a 90% alert:
  1. Check the billing report.
  2. Scale `max-instances` down.
  3. Delete stray images.
  4. Stop the dev Cloud Run service if needed.
- **No credits to run out** (no Nonprofits approval). If Google for Nonprofits is approved
  later, it's a bonus, not a dependency.
- **Where to look first if costs rise:**
  - `min-instances > 0` left on by mistake.
  - Cloud Run kept awake by a bot hammering the site.
  - Cloud SQL storage growth.
  - Undeleted on-demand backups.
  - Stopping the database isn't an option: it's shared by dev and prod.

## 12. Privacy and data

- **Residency:**
  - The database, backups, secrets, the API (Cloud Run) and logs are all in
    `australia-southeast1`.
  - Firebase Hosting's CDN is global, but serves only the static build. API responses pass
    through Google's edge but are marked `no-store` (§5.1), so they aren't cached.
  - *Note for the APP consult (DEV-64): API traffic transits Google's global edge in TLS.*
- **Backups vs deletion requests:**
  - Automated backups and PITR logs are kept **7 days**. An anonymised or deleted person is
    gone from every backup within 7 days of the change.
  - **On-demand backups never expire by themselves.** The release workflow's pre-migration
    backup must be deleted after 7 days. A small scheduled workflow (`backup-cleanup.yml`,
    weekly cron) deletes on-demand backups older than 7 days. It runs on a schedule rather
    than at release time, because releases may be weeks apart.
  - Write this into the deletion procedure (DEV-63): "fully removed from backups 7 days
    after anonymisation".
- **`person.expa_id` is an identifier.** Anonymisation (spec §8.2) must **null it**, along
  with tombstoning `aiesec_email`. Add this to spec §8.2 and `docs/data-model.md`.
- **`audit_log`:**
  - The append-only protection is enforced by the DB role split (§5.3).
  - Sign-in entries carry person ids only.
  - Backups include it (spec §10).
- **dev never holds real member data.** The showcase uses demo data. Real data arrives only
  at the v1 cutover (§6).
- **No personal-data export.** Nothing in this design exports data. The DB is reachable only
  by `mt-tech-leads` (prod) through the Auth Proxy, and every such session is visible in
  Cloud Audit Logs.
- **The deletion-request workflow stays Phase 2.** Until then, the manual procedure
  (DEV-63) runs SQL via the Auth Proxy. That happens with tech-lead access, and the
  action taken is logged in `audit_log`.

## 13. Operations

- **Monitoring and alerts** (all to `mt-alerts@aiesecaustralia.org`, never a personal inbox):
  - Uptime check on `https://members.aiesecaustralia.org/healthz`, every 5 minutes from 3
    regions. Alert after 2 consecutive failures. `firebase.json` rewrites `/healthz` as
    well as `/api/**` to Cloud Run. The backend serves `/healthz` at the root today, so the
    check tests DNS → Firebase → Cloud Run end to end.
  - Cloud Run prod 5xx rate > 5% over 10 minutes.
  - Cloud SQL disk > 80%, CPU > 90% for 15 minutes.
  - New error group in Error Reporting: email.
  - Budget alerts (§11).

  "Paging" means email to the group. There's no on-call rota for an MVP; the tech leads
  check the alerts inbox daily.
- **Restore test** (also DEV-65's acceptance):
  - Before v1 launch, and then once per term: restore the latest backup to a **temporary
    new instance**.
  - Run a row-count check, time it, write the date and duration in `docs/runbook.md`, then
    delete the temp instance (cost: a few cents per hour).
- **`docs/runbook.md`** covers:
  - site down
  - 5xx after a release (roll back)
  - "everyone gets not-allocated"
  - EXPA down or changed
  - DB full or slow
  - a migration failed halfway
  - point-in-time restore
  - rotate a secret (DB password / EXPA client secret)
  - certificate not issuing (Cloudflare proxy on)
  - budget alert
  - revoke all sessions
  - showcase → v1 cutover
- **Incident response one-pager** (`docs/incident-response.md`):
  - who decides (on-duty tech lead)
  - first 30 minutes: contain, preserve logs, don't delete anything
  - when to tell MC
  - when it's a notifiable data breach (OAIC Notifiable Data Breaches scheme: assess
    within 30 days) **[verify with the APP consult]**
  - the log template

## 14. Security (OWASP Top 10 mapping)

| OWASP 2021 | How this design handles it |
|---|---|
| A01 Broken access control | server-side permission matrix on every endpoint (existing); deny-by-default; dev/prod DB users can't cross; GitHub `production` approvals |
| A02 Cryptographic failures | HTTPS only (Firebase managed certs, HSTS header from the API); Cloud SQL SSL required; session tokens random 256-bit, stored hashed; secrets in Secret Manager |
| A03 Injection | SQLAlchemy parameterised queries (existing); Pydantic validation |
| A04 Insecure design | this doc; threat notes on sessions/CSRF (§5.4) |
| A05 Security misconfiguration | scripted setup (§9); no authorised networks on Cloud SQL; `no-store` on API; mock mode impossible in prod builds (existing `authMode.ts`, test kept) |
| A06 Vulnerable components | Dependabot + Snyk (existing); **Trivy** image scan in `deploy-dev.yml` fails on HIGH/CRITICAL with a fix available (free, avoids Artifact Registry scanning cost) |
| A07 Identification & auth failures | EXPA OAuth only; `state` check; 12 h absolute sessions; revocation; rotation at sign-in |
| A08 Software & data integrity | WIF (no keys); the prod image is the exact dev-tested digest; pinned GitHub Actions versions |
| A09 Logging & monitoring failures | audit_log for sign-ins/actions; Cloud Logging; alerts (§13); no PII in logs |
| A10 SSRF | backend only calls fixed EXPA URLs from config, never user-supplied URLs |

Also: CORS. In prod it's the same origin, so the CORS allow-list is just `APP_BASE_URL`.
Locally the Vite proxy makes it same-origin too. The pre-launch external security/privacy
audit (DEV-68) and the APP consult (DEV-64) are **gates before v1**, not before the
showcase.

## 15. Local development

- `make bootstrap` / `make up` keep working unchanged: Postgres in Docker, backend with
  `--reload`, Vite dev server.
- **Sign-in locally:** the frontend `mock` mode (default on the dev server) for UI work.
  Backend tests stub the EXPA client, the same pattern as today's stubbed key resolver.
  **There is no backend login stub.** A test keeps proving that a request without a valid
  session gets a 401.
- **Testing real EXPA sign-in:** use the **dev environment** (EXPA staging). EXPA only
  accepts https redirect addresses, so `http://localhost` can't be registered.
  *[Builder may try registering `https://localhost:5173/api/v1/auth/callback` on the
  staging app with Vite's https mode. Optional, not required.]*
- Vite `server.proxy: { '/api': 'http://backend:8000' }` (Docker) makes local requests
  same-origin, so the cookie behaves as in prod.
- Talking to the **dev** database from a laptop (tech leads/devs):
  `gcloud auth login` → `cloud-sql-proxy <instance> --port 5434` → `psql`. The steps are in
  `docs/database-changes.md`.

## 16. Migration off Supabase and Vercel: order of operations

1. **Apply for the EXPA developer apps** (staging + prod) from the shared MC account.
   Request EXPA staging logins for devs. *(14-day lead time, so start now.)*
2. **GCP foundation:** org, folder, projects, billing, groups, budget.
3. **Cloud SQL + Artifact Registry + secrets + WIF + Cloud Run (dev) + Firebase (dev)**,
   with the backend still on Supabase auth code. It deploys and serves `/healthz` and the
   mock-mode frontend.
4. **EXPA sign-in code swap** (backend + frontend + migration for `person.expa_id` and
   `user_session`) behind the dev environment. This replaces DEV-36's Supabase pieces
   (tickets N6/N7 in `tickets_sprint_6.md`).
5. **Prod environment + release workflow + monitoring + runbook.**
6. **Showcase** on prod, demo data.
7. **Confirm Supabase holds nothing**:
   `SELECT count(*)` on each table via the session pooler, recorded in the PR.
   Then **delete the Supabase project**, remove Vercel, and remove both from
   `external-services.md`.
8. **Launch gates → v1 cutover:** restore test, APP consult, security audit, incident
   one-pager, then cutover (§6).

## 17. Files to change (after approval; nothing edited yet)

| File | Change |
|---|---|
| `CLAUDE.md` | Stack table: add the hosting row (GCP: Cloud Run, Cloud SQL, Firebase Hosting); "Auth is Supabase" → "Auth is EXPA OAuth (AIESEC's provider); DB is Cloud SQL Postgres". Running it: add `docs/deployment.md`. Current state: EXPA sign-in, dev/prod on GCP. Tech & infra defaults: Database → Cloud SQL Postgres (Sydney); Hosting → Cloud Run + Firebase Hosting; Auth → EXPA OAuth; File storage → Cloud Storage (Sydney); **new Domain/DNS row** (subdomains of `aiesecaustralia.org`, DNS on Cloudflare, registrar Squarespace); budget note |
| `README.md` | stack table auth row; link to `docs/deployment.md` |
| `docs/external-services.md` | remove Supabase and Vercel; add Google Cloud (billing, org), Firebase, EXPA developer account, Cloudflare, Squarespace Domains; owners by role |
| `docs/local-development.md` | env var section (EXPA vars, no Supabase); "Deployed environments" table → Secret Manager / Cloud Run; secret-rotation steps for GCP |
| `docs/auth.md` | rewrite for EXPA (flow diagram, matching via `expa_id`, sessions, setup checklist for the EXPA apps) |
| `docs/frontend.md` | auth mode `expa`; no Supabase client |
| `docs/data-model.md` | `person.expa_id`, `user_session` table, anonymisation nulls `expa_id`, DB role split for `audit_log` |
| `docs/supabase-schema-changes.md` | **rename and rewrite** → `docs/database-changes.md` (migrations via the Cloud Run Job; manual connect via Auth Proxy; expand/contract rule). Keep git history with `git mv` |
| `docs/membership-tool-requirements-spec.md` | §9 (EXPA, `expa_id` matching, our own short-lived server-side sessions replace "no tokens of our own"/"managed provider sessions"; sign-in button text); §8.2 (null `expa_id`); §10 Database/Hosting lines; §12 #7 (domains; EXPA `aiesec_email` may be null for some members), #11 resolved |
| Jira / `ticket.md` | new tickets N1–N15 and the edits to existing tickets (DEV-76 closed, DEV-65 rewritten, …) are in `tickets_sprint_6.md` |
| `.env.example` | remove `SUPABASE_*`, `VITE_SUPABASE_*`, `VITE_API_URL`, `DEV_ACTOR_HEADER_ENABLED` (stale); add `EXPA_*`, `APP_BASE_URL`, `SESSION_TTL_HOURS`; `VITE_AUTH_MODE=mock|expa` |
| `docker-compose.yml` | drop `VITE_SUPABASE_*` / `VITE_API_URL` from frontend env |
| `frontend/package.json` (+ lock) | remove `@supabase/supabase-js`; no replacement |
| `frontend/vite.config.ts` | `/api` dev proxy |
| `frontend/src/auth/*`, `src/api/supabaseSession.ts`, `authMode.ts`, `SignInPage.tsx`, `types.ts`, `vite-env.d.ts`, tests | swap to `expaSession.ts`; "Sign in with EXPA" |
| `backend/app/config.py`, `core/auth.py`, `api/deps.py`, `api/v1/auth.py`, `main.py` | EXPA client + session store; login/callback/logout routes; `no-store` + Origin-check middleware; tests rewritten |
| `backend/Dockerfile` | add `prod` stage |
| `backend/migrations/versions/` | `person.expa_id`, `user_session`, DB role grants for `audit_log` |
| `.github/workflows/` | add `deploy-dev.yml`, `release-prod.yml`, `rollback-prod.yml` |
| `firebase.json`, `.firebaserc` (new, repo root) | hosting config, `/api/**` → Cloud Run rewrite, SPA fallback, security headers |
| `infra/` (new) | scripts per §9 |
| **New docs** | `docs/deployment.md` (architecture diagram, environments, first-time setup, deploy, release, rollback), `docs/runbook.md`, `docs/access-and-ownership.md` (accounts, owners by role, domain registrant, offboarding checklist), `docs/incident-response.md`, `docs/costs.md` (the §11 table, budget alerts, what to do on an alert) |
| `.gitignore` | add `12. Dev guides/`. **The EXPA decks stay out of the repo** (Tech Lead, 2026-11-09). `docs/auth.md` instead says where to get them: AIESEC developer guides, `aies.ec/developer-guides`, plus the copy in the MC shared drive |

## 18. Left to the builder

- Exact SQLAlchemy pool numbers, the purge mechanism for expired sessions, and naming inside
  `infra/` scripts.
- Whether frontend promotion is a rebuild at the tag or `firebase hosting:clone`.
- The exact Trivy severity threshold and ignore file.
- Trying `https://localhost` against EXPA staging for local real sign-in.
- Wording of the "Sign in with EXPA" button and error states, within spec §2A.3.

## 19. Decisions recorded and open items

**Answered by the Tech Lead (2026-11-09):**
- **Showcase: second week of December 2026** (about 4–5 weeks from now). See §20.
- The GCP Organization is created with the `hello@aiesecaustralia.org` login. That account
  then stays in `gcp-org-admins@` as the break-glass account (§10).
- The website's hosting is not part of this budget.
- The EXPA decks stay out of git.
- **Don't commit or push** any of this work until the Tech Lead says so.

**Still to verify** (marked [verify] above):
- Sydney Cloud SQL price and GST
- the Cloud Run domain-mapping region list
- the Firebase `__session` rule and Blaze requirement
- EXPA `state` support and the app type

## 20. Timeline to the showcase (second week of December)

The critical path is **EXPA developer app approval (up to 14 days)**. Without it, there's no
real sign-in on dev or prod.

| Week of | Must be done |
|---|---|
| 9 Nov | EXPA apps (staging + prod) submitted; staging logins requested; GCP org, projects, billing, groups, budget |
| 16 Nov | Cloud SQL, Artifact Registry, secrets, WIF, dev Cloud Run + Firebase + `members-dev` DNS; `deploy-dev.yml` green |
| 23 Nov | EXPA sign-in code swap merged and working on dev (if staging approval is late, keep building against stubbed tests and finish on approval) |
| 30 Nov | prod environment, `release-prod.yml`, monitoring + alerts, `members` DNS, runbook essentials; first release `v0.1.0` with demo data |
| 7 Dec | **freeze**: only fixes; showcase rehearsal on prod |

**Fallback if EXPA prod approval hasn't arrived by 30 Nov:** run the showcase on the **dev**
environment (EXPA staging, demo data). Same code, different address. Don't put a mock login on
prod to fill the gap: that's an anti-goal (§2).

After the showcase (mid-Dec → mid-Jan) come the v1 gates: restore test, APP consult, security
audit, incident one-pager, Supabase/Vercel removal, then the v1 cutover (§6).
