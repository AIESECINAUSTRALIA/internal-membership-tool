# External Services

Registry of third-party services this project depends on. One row per service.

**Why this doc exists:** Due to dev team turnover, next codeowners need to have this information.

**Note:** All usage of the hello email requires MC given access via Bitwarden.

## Conventions

- **Account owner:** every service is registered to an **AIESEC Australia**
  (hello email), never a personal account.
- **Access:** at least **1 person** can administer each service at all times. Access is
  granted by **role/position**, not to named individuals. When someone leaves, their
  access is removed and their successor is added.
- **Plans:** every service below is on its **free tier for now**. These are interim
  choices while we're pre-deployment — each must be reviewed before production launch
  (paid tier or nonprofit/NFP program as appropriate).
- When a value is unknown, leave `_TBD_` and a name/date next to it.

---

## Summary

| Service  | Purpose | Account email | Plan / tier |
|----------|---------|---------------|-------------|
| Supabase      | Database, auth, file storage | hello email | free |
| Vercel (temp)   | Web app hosting / deploys | hello email | free |
| Snyk           | Dependency vulnerability scanning | hello email | free |
| Jira     | Issue tracking (`DEV-XXXX` tickets) | hello email | free (waiting nfp) |

---

## Supabase

- **Purpose:** Primary managed backend — Postgres database (single source of truth),
  OAuth auth via AIESEC emails, and object storage for files/images.
- **Account email:** hello email (access role-based, via Bitwarden, granted by MC)
- **Plan / tier:** Free — interim. Before production, move to a paid tier; must **not**
  be a tier that auto-expires data.
- **How we use it:** Temporary database deployment, unless we end up using a database
  provided by a larger cloud provisioner.

## Vercel _(temporary)_

- **Purpose:** Managed hosting and CI/CD for the web front-end — automatic deploys from
  GitHub (preview deploys per PR, production on `main`).
- **Account email:** hello email (access role-based, via Bitwarden, granted by MC; linked to the GitHub org)
- **Plan / tier:** Free — temporary hosting choice, to be re-evaluated before we
  actually deploy.
- **How we use it:** Temporary deployment until we move to something like GCP or AWS.

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
