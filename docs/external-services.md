# External Services

Registry of third-party services this project depends on. One row per service.

**Why this doc exists:** Due to dev team turnover, next codeowners need to have this information.

**Note:** All usage of the hello email requires MC given access via Bitwarden.

## Conventions

- **Account owner:** every service is registered to an **AIESEC Australia**
  (hello email), never a personal account.
- **Access:** at least **2 people** can administer each service at all times
  (`CLAUDE.md`: no single point of failure). Access is granted by **role/position**, not
  to named individuals. For GCP this means Google Workspace groups. When someone leaves,
  their access is removed and their successor is added.
- **Plans:** free tiers where they're enough; anything paid comes out of the ~$500 AUD/yr
  budget (`CLAUDE.md` → Tech & infra defaults).
- When a value is unknown, leave `_TBD_` and a name/date next to it.

**Decision (2026-11-09):** all deployment and hosting moves to **Google Cloud**. Supabase
and Vercel are being retired. Design:
`docs/superpowers/specs/2026-11-09-gcp-deployment-design.md`.

---

## Summary

| Service  | Purpose | Account email | Plan / tier | Status |
|----------|---------|---------------|-------------|--------|
| Google Cloud (GCP) | All hosting: Cloud Run, Cloud SQL, Secret Manager, Artifact Registry, monitoring | hello email (org admin) | pay-as-you-go | **being set up** |
| Firebase (part of GCP) | Frontend hosting, custom domain, SSL | same GCP projects | Blaze (pay-as-you-go, ~$0 at our traffic) _[verify]_ | **being set up** |
| EXPA developer account | Owns the EXPA OAuth apps used for sign-in | shared MC developer account | free | **being set up** |
| Cloudflare | DNS for `aiesecaustralia.org` (incl. `members.` / `members-dev.`) | _TBD_ | free | in use (national team) |
| Squarespace Domains | Registration of `aiesecaustralia.org` | hello email _[verify]_ | paid yearly | in use |
| Snyk           | Dependency vulnerability scanning | hello email | free | in use |
| Jira     | Issue tracking (`DEV-XXXX` tickets) | hello email | free (waiting nfp) | in use |
| Supabase      | Interim Google sign-in (Supabase Auth) | hello email | free | **retiring** |
| Vercel   | Interim frontend hosting | hello email | free | **retiring** |

---

## Google Cloud (GCP)

- **Purpose:** the one platform for deployment and hosting, all in Sydney
  (`australia-southeast1`):
  - **Cloud Run:** the API
  - **Cloud SQL:** Postgres, one instance holding the dev and prod databases
  - **Firebase Hosting:** the frontend
  - **Secret Manager, Artifact Registry**
  - **Cloud Logging / Monitoring / Error Reporting**
- **Account:** GCP organization on `aiesecaustralia.org`, created with the hello email.
  - Folder `membership-tool`, projects `aiesec-au-mt-dev` and `aiesec-au-mt-prod`.
  - Billing account "AIESEC Australia" (AUD, org-owned card).
- **Access:** Google Workspace groups, each ≥2 people by role: `gcp-org-admins@`,
  `gcp-billing-admins@`, `mt-tech-leads@`, `mt-developers@`, `mt-alerts@`. The hello email
  is the break-glass org admin.
- **Plan / tier:** pay-as-you-go, no credits (Google for Nonprofits not approved).
  - Estimated ~AU$205–320/yr, mostly Cloud SQL _[verify in billing once running]_.
  - Budget alert at AU$35/month to `gcp-billing-admins@` and `mt-alerts@`.
- **How we use it:** two environments:
  - **dev** (`members-dev.aiesecaustralia.org`): deploys on every merge to `main`.
  - **prod** (`members.aiesecaustralia.org`): deploys on an approved release tag.

  GitHub Actions deploys with Workload Identity Federation, so no keys are stored anywhere.

## EXPA developer account

- **Purpose:** sign-in. People sign in with their EXPA account through AIESEC's OAuth
  provider.
- **Account:** the **shared MC-level EXPA developer account** (credentials in Bitwarden),
  never a personal EXPA login. It owns two developer applications:
  - staging (`expa-staging.aiesec.org`) for dev
  - production (`expa.aiesec.org`) for prod

  Each app's UID and secret are in Bitwarden. The secret is also in GCP Secret Manager.
- **Approval:** apps are approved by the AIVP IM, which can take up to 14 days. EXPA staging
  logins are requested from `vpis@ai.aiesec.org`.
- **Docs:** AIESEC developer guides at `aies.ec/developer-guides`. Don't commit copies of the
  decks to this repo.

## Cloudflare

- **Purpose:** DNS for `aiesecaustralia.org`. The tool needs only its own records
  (`members`, `members-dev`), set to **DNS only** (grey cloud) so Firebase can issue
  certificates.
- **Account email:** _TBD_. Must be an org email, with ≥2 members able to edit DNS.
- **How we use it:** DNS stays here rather than moving to Cloud DNS, because the whole
  website's DNS (owned by the national team) lives here.

## Squarespace Domains

- **Purpose:** registrar for `aiesecaustralia.org` (registry: Tucows).
- **Account email:** hello email _[verify]_. Registrant should be AIESEC Australia; check
  inside the account, because public WHOIS is privacy-masked.
- **Renewal:** expires **2027-10-23**. Keep auto-renew on with an org-owned card, plus a
  shared-calendar reminder 60 days before.

## Supabase _(retiring)_

- **Purpose (interim):** Google sign-in through Supabase Auth (DEV-36). Its database was
  never used for app data.
- **Account email:** hello email (access role-based, via Bitwarden, granted by MC)
- **Retirement:** once EXPA sign-in runs on GCP, confirm with a row count that the database
  holds nothing, then delete the project and remove its Bitwarden entries.

## Vercel _(retiring)_

- **Purpose (interim):** temporary frontend hosting.
- **Account email:** hello email (access role-based, via Bitwarden, granted by MC; linked to the GitHub org)
- **Retirement:** remove the project once the frontend runs on Firebase Hosting.

## Snyk

- **Purpose:** Dependency and vulnerability scanning (alongside Dependabot), part of the
  OWASP-based security checklist.
- **Account email:** hello email (access role-based, via Bitwarden, granted by MC)
- **Plan / tier:** Free.
- **How we use it:** Monitoring security issues in our dependencies.

## Jira

- **Purpose:** Issue tracker. `DEV-XXXX` ticket IDs drive branch names
  (`chore/DEV-XXXX_short_description`) and commit / PR titles.
- **Account email:** hello email (access role-based, via Bitwarden, granted by MC)
- **Plan / tier:** Free — waiting on nonprofit (NFP) program approval.
- **How we use it:** Task management and sprint monitoring.
