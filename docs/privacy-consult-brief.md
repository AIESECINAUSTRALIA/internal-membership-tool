# Privacy consult brief (DEV-64)

> **Status: preparation. No consult has happened yet.**
>
> **Nothing in this document is legal advice.** It's what we send a privacy adviser
> before the one-off consult that spec §12 #8 and `CLAUDE.md` budget for. Each "proposed
> position" is the **dev team's** working assumption, not an adviser's view. Each answer
> stays *pending* until the adviser gives it in writing.
>
> **Deadline:** before the v1 cutover (DEV-90, mid-January 2027), when real member data
> first enters the tool. The December showcase uses made-up data only, so it doesn't
> need the consult.
>
> **Owner:** the Tech Lead, with national leadership. This is a coordination task. It
> isn't for one developer to decide (see the DEV-64 ticket).

## How to use this document

1. **Before sending:** fill in section 1 (facts about AIESEC Australia) and resolve every
   `TODO (team)` in section 3. Then sections 1–3 can go to the adviser as they are.
2. **At the consult:** work through section 3 in order. Questions 1 and 2 shape most of
   the others.
3. **After the consult:** follow section 6. Record each answer under its question, store
   the written advice, and create the tickets it implies.

---

## 1. About AIESEC Australia (fill in before sending)

The adviser needs these first: they decide whether the Privacy Act applies to us at all
(question 1).

| Fact | Answer |
|---|---|
| Legal entity type (company limited by guarantee, incorporated association, …) | `TODO (leadership)` |
| Annual turnover: above or below A$3 million? | `TODO (leadership)` |
| Registered with the ACNC as a charity? | `TODO (leadership)` |
| Existing privacy policy (e.g. on the website)? Link | `TODO (leadership)` |
| Contact for privacy questions and requests (a shared mailbox, not a person) | `TODO (leadership)`, e.g. `hello@aiesecaustralia.org` |
| Any agreement with AIESEC International about member data or EXPA developer apps? | `TODO (leadership)` |
| Roughly how many people will be in the tool at v1? | `TODO (Tech Lead)` |

---

## 2. What the Membership Tool holds, where, and who can see it

These are facts about the system as designed on 2026-11-25. The sources are in brackets,
so a future reader can check that they're still true.

### 2.1 What it is

An internal tool for AIESEC Australia's members and leaders. It replaces the local
chapters' (LCs') spreadsheets with one database of who holds which role, in which LC, in
which term, plus their activity numbers (KPIs). It's used for dashboards and the official
reports sent to AIESEC International. It isn't public, and nothing in it is sold or shared
with third parties.

### 2.2 The personal information it holds

| Data | Details | Source |
|---|---|---|
| **Identity** | Full name, optional preferred name, AIESEC email address (`@aiesec.net`), date joined, timezone (derived from their LC's state), status (active / alumnus / inactive / anonymised) | `backend/app/models/person.py` |
| **EXPA id** | AIESEC International's identifier for the person, stored at first sign-in | `person.expa_id`, `docs/auth.md` |
| **Role history** | Each membership: LC, position (e.g. "LCVP"), function (e.g. "Outgoing Global Volunteer"), term, start and end dates; team membership and team leadership | `backend/app/models/membership.py` |
| **Activity numbers (KPIs)** | Per person, per period: counts such as sign-ups, interviews and matches, with an optional free-text note | `backend/app/models/kpi.py` |
| **Custom fields** | Admin-defined fields. Currently seeded: shirt size, **dietary requirements** (free text). Admins can add more fields without a developer. | `backend/app/seeds/seed_attributes.py`, spec §4.2 |
| **Sign-in sessions** | A hashed session token, created and expiry times. Sessions last 12 hours. | `backend/app/models/user_session.py` |
| **Audit log** | Who did what to which record, by id: sign-ins, membership and KPI changes, admin changes. Meant to hold ids only, never names or emails. It can't be edited or deleted, even by us. | `backend/app/models/privacy.py`, spec §8.4 |

What it deliberately **doesn't** hold: phone numbers, personal email addresses, addresses,
dates of birth, payment details, or uploaded files. The `phone` and `personal_email`
columns still exist in the database but are unused, and are due to be removed (section 4).
There's **no feature that exports personal data** (`CLAUDE.md`).

### 2.3 How information gets in

- **Admins add people.** An admin (by position, e.g. someone on the national board) enters
  a person's name and AIESEC email and gives them a membership. So we collect most
  information **from someone other than the person**.
- **People sign in with EXPA**, AIESEC International's own sign-in system. At sign-in, the
  tool receives only the person's **EXPA id and AIESEC email**. EXPA's access token is
  thrown away straight after (`docs/auth.md`).
- **Members and leaders enter activity numbers** for themselves and the people they lead,
  and people can edit their own custom fields.

### 2.4 Where it's stored

| Where | What | How long |
|---|---|---|
| Google Cloud SQL, **Sydney** (`australia-southeast1`) | The database | Until deleted or anonymised |
| Cloud SQL automatic backups, Sydney | Daily backups and point-in-time recovery logs | **7 days**, then deleted automatically |
| Cloud SQL backups taken before a release | Full copies | Deleted by a weekly job once older than 7 days |
| Google Cloud Logging, Sydney | Application logs (meant to contain no names or emails) | 30 days (Google's default) |
| Firebase Hosting (Google's **global** network) | Web traffic passes through it, encrypted (TLS). Responses with data are marked not to be cached. | Not stored |
| EXPA (AIESEC International) | The person's EXPA account. **Not ours.** | AIESEC International's policy |

Sources: `docs/superpowers/specs/2026-11-09-gcp-deployment-design.md` (§ backups, logging,
privacy).

### 2.5 Who can see it

- **Members** see their own data, and data about people below them in their LC and
  function, according to a permission table based on position and function (spec §3).
  Access isn't granted to named individuals.
- **Admins** (by position) use a separate admin console.
- **Direct database access**: only the Google group `mt-tech-leads@aiesecaustralia.org`
  (the Tech Lead and at least one senior developer), through Google's Cloud SQL Auth
  Proxy. Every such session is recorded in Google Cloud's audit logs.

### 2.6 How a deletion request is handled now

Until an in-app workflow exists (Phase 2), two authorised people handle requests by hand,
following `docs/admin-guide/06-deletion-requests.md`. By default the person is
**anonymised**, not deleted:

- name replaced with "Anonymised person", email replaced with `anon+<id>@invalid`
- EXPA id removed, all sessions ended, status set to anonymised
- custom-field values and free-text KPI notes about them removed
- **kept**: their role history (LC, position, function, term, dates) and activity
  numbers, now attached to the anonymous record, so past totals and submitted reports
  stay correct

A **hard delete** is used only when nothing depends on the record (someone added but
never given a membership), or when a legal obligation requires it. Each request is
recorded with no personal data, and the requester is told their data is gone from backups
7 days later.

> The guide is on the DEV-0063 branch and isn't merged into `main` yet.

---

## 3. Questions for the adviser

Ordered by how much the rest depends on them. Each question gives the context, our
proposed position, and what the answer changes.

### Q1. Does the Privacy Act apply to us?

**Context.** Our understanding is that organisations with annual turnover of A$3 million
or less are generally exempt from the Australian Privacy Principles (APPs) unless an
exception applies, and that an exempt organisation can choose to opt in. See section 1 for
our turnover and entity type.

**Questions.**
- Are we an "APP entity"? If so, why (or which exception applies)?
- If we're exempt, do you recommend opting in, or following the APPs voluntarily without
  opting in? What's the practical difference for us?
- Does the newer statutory tort for serious invasions of privacy affect a tool like this
  either way?

**Proposed position.** Follow the APPs whether or not we're legally required to. Members
expect it, and `CLAUDE.md` commits us to honouring deletion requests.

**Depends on it.** How strictly Q8 (data breaches) and Q11 (privacy policy) apply.

**Adviser's answer:** *pending*

### Q2. Does our anonymisation count as "de-identified"?

**Context.** Section 2.6. After anonymisation we keep role history and activity numbers.
Many positions have **one holder per LC per term**. So "LCVP of Outgoing Global Volunteer
at LC Adelaide in 2026", plus their numbers, could let another member work out who it was.

**Questions.**
- Is the anonymised record still "reasonably identifiable" personal information, given
  that the people who can see it are other members who may know who held the role?
- If it isn't de-identified enough, which of these do you recommend?
  - (a) keep it as it is, and treat it as personal information we're entitled to keep for
    reporting
  - (b) make it less specific: keep LC, function, term and totals, but drop position or
    exact dates on anonymised memberships
  - (c) something else
- Is keeping the person's internal id number (which links the anonymous record to their
  history) acceptable?

**Proposed position.** (a) for v1, because official reports to AIESEC International need
position-level history. We'd move to (b) if advised.

**Depends on it.** The anonymisation steps in the deletion guide; possibly a schema change.

**Adviser's answer:** *pending*

### Q3. How long should we keep information about people who have left?

**Context.** Nothing is deleted automatically today. Membership history matters for
year-on-year reports. Alumni may keep access to the tool.

**Questions.**
- Is it acceptable to keep role history and activity numbers for as long as reporting
  needs them, if we anonymise the identity after a set period?
- What period after someone's last membership ends would you consider reasonable before
  anonymising: for alumni, and for people whose membership ended early?
- Do we need to tell members this period up front?

**Proposed position.** `TODO (team)`: agree a starting proposal before sending (e.g. "anonymise N years after
the last membership ends, reviewed yearly"). Nothing is automated in v1. An automatic
clean-up would be a Phase 2 ticket built only after this answer.

**Depends on it.** Whether we need a scheduled clean-up job (new ticket).

**Adviser's answer:** *pending*

### Q4. How quickly, and how carefully, must we handle a deletion request?

**Context.** Our draft process is in section 2.6 and the deletion guide.

**Questions.**
- Are these timings reasonable: acknowledge within **5 business days**, finish within
  **30 calendar days**, and faster where someone's safety is involved?
- **Verifying identity:** we confirm through the person's AIESEC email on record. If they
  no longer have it (common for alumni), someone who knows them confirms on a video call.
  We deliberately don't ask for ID documents. Is that enough?
- How should we handle requests made on someone's behalf (a parent, a lawyer)?
- When, if ever, may we refuse or only partly carry out a request (e.g. data needed for
  reports already submitted)? What must we tell the person?

**Proposed position.** The timings and checks above, as written in the deletion guide.

**Depends on it.** The deletion guide's timings, which are marked provisional until this
consult.

**Adviser's answer:** *pending*

### Q5. Is a 7-day backup window after anonymisation acceptable?

**Context.** After anonymisation, the person's original details stay in database backups
for up to 7 days (section 2.4). Shorter retention would weaken our ability to recover from
mistakes.

**Questions.**
- Is 7 days acceptable?
- Is this wording right for the requester: "your details will be gone from every backup
  by DATE"?
- If we ever had to restore a backup inside that window, what must we do (e.g.
  re-anonymise straight away)?

**Proposed position.** 7 days. After any restore, re-apply every anonymisation completed
since the backup was taken before reopening the tool.

**Depends on it.** Backup settings (DEV-65/DEV-80) and the restore guide (admin guide 8).

**Adviser's answer:** *pending*

### Q6. Data location: Sydney storage, global network in transit

**Context.** All storage is in Sydney (section 2.4). Web traffic passes, encrypted,
through Google's global network (Firebase Hosting), which may route it through other
countries. It's marked not to be cached.

**Questions.**
- Does traffic passing through, without being stored, count as a disclosure overseas
  (APP 8)?
- Does using Google Cloud count as "use" (they store data for us) or "disclosure"?
- Is there anything we should say about this in a privacy policy?

**Proposed position.** Acceptable as it is: Google is a service provider holding data on
our behalf, and in-transit routing isn't disclosure.

**Depends on it.** If not acceptable: an architecture change (cost and design impact).

**Adviser's answer:** *pending*

### Q7. EXPA (AIESEC International) as the sign-in system

**Context.** Section 2.3. People sign in through EXPA, run by AIESEC International, which
operates outside Australia. We receive their EXPA id and AIESEC email, and we store the
EXPA id. Our numbers are also reported to AIESEC International (NAMs, SONA, MTR reports),
mostly as totals.

**Questions.**
- Does receiving and storing the EXPA id create any notice or disclosure obligations?
- Does sending reports to AIESEC International count as disclosure overseas (APP 8)? Does
  it matter whether a report contains totals only or named people?
- Do we need a written agreement with AIESEC International?
- When someone asks us to delete their data, are we obliged to tell AIESEC International,
  or only to tell the person how to ask them?

**Proposed position.** Tell the person their EXPA account is AIESEC International's, and
how to contact them. Keep reports to totals wherever the template allows.

**Depends on it.** Report design (spec §7, still blocked on the report templates) and the
requester reply in the deletion guide.

**Adviser's answer:** *pending*

### Q8. Data breaches

**Context.** We're writing a one-page incident response plan (DEV-87).

**Questions.**
- Does the Notifiable Data Breaches scheme apply to us (see Q1)? If not, what do you
  recommend we do anyway?
- Please confirm the assessment process and timelines we should follow, and who we notify
  (the OAIC, affected people, AIESEC International?).
- Who in our organisation should decide whether a breach is notifiable?

**Proposed position.** Follow the scheme's process regardless: assess quickly and within
30 days at most, notify where serious harm is likely, and record every suspected breach.

**Depends on it.** DEV-87 (incident response plan).

**Adviser's answer:** *pending*

### Q9. Sensitive information (dietary requirements and custom fields)

**Context.** A seeded custom field, "Dietary requirements", is free text. Answers like
"coeliac" or "halal" can reveal **health** or **religious beliefs**, which we understand
the Privacy Act treats as sensitive information with stricter consent rules. Admins can
also create new fields without a developer.

**Questions.**
- Does this field make us a holder of sensitive information? What consent do we need, and
  how should we record it?
- Should we remove it, change it (e.g. a short fixed list with "prefer not to say"), or
  keep it with consent?
- What guidance should admins have about what custom fields they may create?

**Proposed position.** Remove "Dietary requirements" from the tool (events can collect it
separately and temporarily). Add a rule to the admin guide: no custom fields about health,
religion, ethnicity, sexuality, politics or criminal records.

**Depends on it.** A ticket to remove or change the field, and an admin-guide rule.

**Adviser's answer:** *pending*

### Q10. How long can we keep the audit log?

**Context.** The audit log records actions by id only. By design it can't be edited or
deleted. Ids are linked to people while their record exists. After anonymisation they
point to an anonymous record.

**Questions.**
- Can we keep it indefinitely, given that the ids become anonymous when the person is
  anonymised?
- If not, what period do you recommend, and is it acceptable to archive and delete old
  entries as a whole (which the database would need a deliberate change to allow)?

**Proposed position.** Keep it indefinitely. It holds ids only, and those ids lose their
link to a person on anonymisation.

**Depends on it.** Possibly a retention job for the audit log (new ticket).

**Adviser's answer:** *pending*

### Q11. Privacy policy and collection notice

**Context.** Most people are added by an admin before they ever sign in (section 2.3). The
tool doesn't show any privacy notice at the moment.

**Questions.**
- Do we need a privacy policy covering this tool (APP 1)? Can the existing AIESEC
  Australia policy (section 1) cover it?
- What notice must people get, and when, given they're added by someone else (APP 5)?
  Would a notice on the sign-in page and at first sign-in be enough?
- What should the notice say? A short checklist would help.

**Proposed position.** A short privacy notice linked from the sign-in page and shown
once at first sign-in, pointing to the full policy and the privacy contact.

**Depends on it.** A ticket for the notice (frontend), and possibly an update to the
organisation's privacy policy.

**Adviser's answer:** *pending*

### Q12. Members seeing and correcting their own data

**Context.** Members can see their profile and memberships, and edit their own custom
fields. Name, email and role changes go through an admin.

**Questions.** Is that, plus a way to ask the privacy contact, enough for members'
rights to access and correct their information (APP 12, 13)?

**Proposed position.** Yes.

**Adviser's answer:** *pending*

---

## 4. Changes we already know about

These don't depend on the consult, or depend only partly. Each needs **its own ticket**.
None is created yet, and none should be built from this document alone.

| Change | Why | Depends on |
|---|---|---|
| Remove the unused `phone` and `personal_email` columns | We don't collect them (spec §4.1). Already listed under "Known differences from the spec" in `docs/data-model.md`. Needs removing in two releases: code first, then the columns (expand, then contract). | Nothing |
| Privacy notice on the sign-in page | Q11 | Q11 |
| Remove or change "Dietary requirements"; admin-guide rule on custom fields | Q9 | Q9 |
| Automatic anonymisation after a retention period (Phase 2) | Q3 | Q3 |
| Less specific anonymised memberships | Q2 | Q2, only if advised |
| In-app deletion-request workflow and `deletion_request` table (Phase 2) | Spec §8 (table defined in spec §4.5) | Q4 for the timings |

---

## 5. Finding an adviser

`CLAUDE.md` budgets for one paid consult. Options worth asking about first:

- free or low-cost legal help for not-for-profits (e.g. Justice Connect's Not-for-profit
  Law service)
- a university law faculty's legal clinic or pro bono programme
- a privacy lawyer for a fixed-fee review of this brief

Ask for **written** answers to section 3. The brief is designed so the adviser can answer
it without first having to learn how the system works, which keeps a paid consult short.

`TODO (Tech Lead):` record who was approached and the cost here.

---

## 6. After the consult

1. Under each question, replace *pending* with the adviser's answer. Quote the written
   advice where possible, and note anything they said only verbally.
2. Add a "Consult record" section at the top: the adviser's firm or organisation and
   qualification (no personal contact details), the date, and where the **written advice
   is stored**: a shared drive owned by `mt-tech-leads@`, never a personal drive.
3. Change the status box at the top to "Consult complete" and rename the file to
   `docs/privacy-consult.md`.
4. Update everything waiting on it:
   - spec §8: remove the consult `TODO`, add the answers
   - `docs/admin-guide/06-deletion-requests.md`: confirm or change the timings `TODO`
   - DEV-87: the data-breach answers (Q8)
5. Create a ticket for each change in section 4 that the answers confirm.
6. Close DEV-64.
