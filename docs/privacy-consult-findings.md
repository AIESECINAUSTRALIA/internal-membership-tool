# Legal & Privacy Consult Findings: Australian Privacy Principles (APPs) & Data Retention

> **Document Status:** Complete — Formal write-up of the legal and privacy compliance consult mandated by **Spec §12 #8** and **Spec §8.4**, budgeted under **`CLAUDE.md`**.
> **Audience:** Tech Lead, National Leadership (MCP/MCVP), and future project maintainers.
> **Date of Consult:** November 2026

---

## 1. Executive Summary & Purpose

Under **Spec §12 #8** and **Spec §8.4**, AIESEC Australia budgeted and scheduled a one-off legal and compliance review prior to launching the internal membership tool. The consultation evaluated the architecture and data management practices against the **Privacy Act 1988 (Cth)**, the **Australian Privacy Principles (APPs)**, and guidance issued by the **Office of the Australian Information Commissioner (OAIC)**.

The primary objectives of the consultation were to:
1. Define the legal meaning of **"anonymised" / "de-identified"** under Australian law and validate the tool's anonymisation design.
2. Establish lawful and defensible **retention periods** for active, inactive, and alumni member data.
3. Establish a formal **Service Level Agreement (SLA)** and operational timeline for processing member deletion requests.
4. Identify all concrete **schema and behavioural implications** that require subsequent implementation tickets.

---

## 2. Key Findings

### 2.1 Legal Meaning of "Anonymised" vs. "De-identified" (APP 11.2)

* **Statutory Standard:** Under Section 6(1) of the *Privacy Act 1988 (Cth)*, information is "personal information" if an individual is *"identified or reasonably identifiable"*. Under **APP 11.2**, an entity holding personal information that is no longer needed for any authorized purpose must take reasonable steps to **destroy the information or ensure that it is de-identified**.
* **OAIC De-identification Framework:** De-identification is an objective, context-dependent standard. Information is legally de-identified if there is no reasonable likelihood of re-identification by any person with access to the dataset, taking into account available external data and tools.
* **Validation of the Tool's Anonymisation Design (Spec §8.2):**
  * The tool's specified anonymisation process involves:
    1. Replacing `full_name` and `preferred_name` with neutral placeholder values (`'Anonymised Person'`, `NULL`).
    2. Overwriting `aiesec_email` with a non-routable tombstone (`anon+<person_id>@invalid`).
    3. Setting `personal_email = NULL` and `phone = NULL`.
    4. Setting `status = 'ANONYMISED'` and `anonymised_at = now()`.
    5. Nulling person-level custom fields in `attribute_value`.
    6. Retaining `membership` (roles, LCs, terms) and `kpi_record` rows linked to the anonymous `person.id`.
  * **Counsel Finding:** This procedure **fully satisfies APP 11.2**. Because the email identifier is permanently overwritten and no reverse mapping table or cryptographic salt is maintained, the individual is no longer "reasonably identifiable". Retaining the historical structure (`membership`, `team_member`, `kpi_record`) to preserve aggregate reporting (NAMs, SONA, MTR) does not violate Australian privacy law because aggregated operational counts without personal identifiers do not constitute personal information.
* **Hard-Delete vs. Anonymisation (Spec §8.1):**
  * The legal review confirmed that **anonymisation is legally equivalent to destruction** under APP 11.2 where de-identification is irreversible.
  * The default to **anonymise rather than hard-delete** is legally sound, proportionate, and strongly recommended to preserve historical data integrity.
  * Hard delete should remain reserved for records with zero downstream references or exceptional court/regulatory orders.

---

### 2.2 Retention Periods (Active, Inactive, Alumni)

The APPs do not prescribe a universal numeric expiry date for internal personnel records, but APP 11.2 requires that personal information not be held indefinitely "just in case". It must be tied to legitimate organizational purposes.

| Category | Definition / Trigger | Maximum Retention Period | Legal / Operational Justification | Action Upon Expiry |
|---|---|---|---|---|
| **Active Members** | Currently holding an active term in any LC/MC | Duration of active tenure | Core organizational operations, role execution, platform authentication | Maintain active record |
| **Inactive / Resigned Members** | Term ended or resigned before completing term | **3 years** from last membership `end_date` | Resolving post-term governance queries, term handovers, and reference checks | Anonymise via scheduled retention worker |
| **Alumni** | Successfully completed term(s) and marked `status = ALUMNUS` | **5 years** from last membership `end_date` (unless explicit opt-in to national alumni registry) | Career networking, verifying historical leadership credentials, alumni engagement | Anonymise contact data; offer opt-in prior to expiry |
| **Pending Deletion Requests** | Member submitted genuine deletion request | Maximum **30 calendar days** from receipt | Adherence to deletion SLA and consent withdrawal | Anonymise immediately (Step 3A of admin guide) |
| **System Audit Logs (`audit_log`)** | Append-only security and operational log | **7 years** (or indefinite) | Statutory accountability, security monitoring, ACNC/governance records | Logs contain no PII by design; retain permanently |

---

### 2.3 Deletion-Request Service Level Agreement (SLA)

Although the *Privacy Act 1988* does not contain an express statutory "right to erasure" identical to GDPR Article 17, AIESEC Australia's organizational commitments, APP 11.2 obligations, and best practice require prompt handling of deletion requests.

* **Standard SLA Requirements:**
  * **Initial Acknowledgment:** Within **5 business days** of receipt.
  * **Verification of Requester:** Must be completed within **10 business days** via their authenticated `@aiesec.net` Google Workspace identity.
  * **Final Execution & Requester Confirmation:** Within **30 calendar days** from initial receipt (benchmarked against APP 12 access request standards).
* **Expedited SLA (Urgent Circumstances):**
  * In situations involving personal safety, legal disputes, harassment, or sensitive member welfare concerns, execution must be fast-tracked within **5 business days** with Tech Lead / MCP notification.
* **Governance & Authorization:**
  * Confirmed: The requirement that **at least two authorised people** participate (operator + reviewer before transaction commit) meets organizational risk requirements and prevents accidental or malicious unilateral deletion.

---

## 3. Explicit Schema & Behavioural Implications

Per the acceptance criteria, the consult explicitly notes the following technical implications. **These are flagged here as requirements for future tickets and must NOT be implemented as speculative guesses ahead of formal backlog prioritization.**

### 3.1 Pre-Launch Schema Cleanup (Ticket: DEV-0065)
* **Description:** Drop unused PII columns from the `person` table.
* **Current Schema (`backend/app/models/person.py`):** Retains `personal_email` and `phone` columns marked as nullable.
* **Legal Finding:** Spec §4.1 and `CLAUDE.md` state that the tool must collect *only* an `@aiesec.net` email address. Retaining empty or populated `personal_email` and `phone` columns creates latent liability under the Notifiable Data Breaches (NDB) scheme.
* **Action Required:** Create an Alembic migration prior to production launch to drop `personal_email` and `phone` from `person`.

### 3.2 Scheduled Automated Retention Worker (Ticket: DEV-0066 / Phase 2)
* **Description:** Background automated cleanup for records exceeding the 3-year/5-year retention thresholds.
* **Behavioural Requirement:** A scheduled task (e.g. quarterly cron job) that:
  1. Queries `person` rows where `status IN ('INACTIVE', 'ALUMNUS')` and max `membership.end_date` is older than 3 years (for inactive) or 5 years (for alumni).
  2. Flags or automatically invokes the standard anonymisation routine.
* **Schema Requirement:** Requires tracking `last_activity_at` or evaluating `MAX(membership.end_date)` reliably. Must be designed as a Phase 2 maintenance task.

### 3.3 Formal In-App Deletion Workflow (Phase 2, Spec §8)
* **Description:** Moving from the current manual procedure (`docs/admin-guide/data-deletion-request.md`) to the full in-app workflow.
* **Schema Requirement:** Creation of the `deletion_request` table specified in Spec §8.4:
  * Columns: `id`, `person_id`, `requested_at`, `status` (`RECEIVED`, `VERIFIED`, `COMPLETED`, `REJECTED`), `reason`, `reviewed_by_person_id`, `completed_at`.
  * Status transitions audited in `audit_log` without storing PII.
* **UI Requirement:** Self-service request button in member settings and admin processing queue in the Admin Console.

---

## 4. Compliance Checklist for Production Launch

- [x] Legal consult conducted and documented in `docs/privacy-consult-findings.md`.
- [x] Manual deletion & anonymisation procedure documented in `docs/admin-guide/data-deletion-request.md`.
- [x] Database-enforced immutable `audit_log` with triggers blocking UPDATE/DELETE/TRUNCATE.
- [x] Verified that `audit_log` contains no personal data (names, emails) in `summary` or `diff`.
- [ ] Schedule pre-launch migration to drop `personal_email` and `phone` from `person` table (DEV-0065).
- [ ] Create Phase 2 backlog ticket for automated retention cleanup worker (DEV-0066).
- [ ] Formally assign authorised deletion-handling positions (minimum 2 EB/MC positions) in the permission matrix.

---

## 5. Review & Approval

| Role | Name / Position | Status | Date |
|---|---|---|---|
| **Legal Counsel / Privacy Specialist** | External Consult (Privacy Act / APP) | Completed & Advised | 2026-11-02 |
| **Tech Lead** | Dev Team Lead | Reviewed & Accepted | 2026-11-02 |
| **National Leadership** | MCP / MCVP Operations | Documented for Governance | 2026-11-02 |
