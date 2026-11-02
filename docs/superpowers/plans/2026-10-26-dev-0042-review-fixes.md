# DEV-0042 Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the authorisation holes and correctness issues found in the PR #18 review so the Membership summary API meets the DEV-0042 ticket's acceptance criteria.

**Architecture:** All permission decisions stay in `backend/app/core/permissions.py` (pure functions over `MembershipContext`); the repository (`app/repositories/membership.py`) calls them before any read or write; the API layer (`app/api/v1/members.py`) stays thin. Auth remains a stub behind `get_current_actor`, but it fails closed unless explicitly enabled for local dev. Tests run against real, migrated Postgres only.

**Tech Stack:** FastAPI, SQLAlchemy 2, Pydantic, pytest, PostgreSQL 16 (Docker Compose locally, service container in CI).

**Spec:** `ticket.md` (DEV-0042 / "Membership integration" section) and `docs/membership-tool-requirements-spec.md` §2A.5, §3.4, §3.6, §5.1, §8.3. Review findings: PR #18 review (numbered 1–8 below map to those findings).

## Global Constraints

- Branch: `feat/DEV-0042_sangam_membership_summary_api` (existing). Commit prefix: `fix: DEV-0042 ...`.
- Every write enforces both §3.4 checks: matrix scope covers the target **and** target rank < actor rank (president exception: `lcp`/`mcp` may add the same position in their own LC).
- Non-MC users only ever see their own LC (§2A.5) — this now applies to `getMembershipDetail` too.
- Response shapes must not change: they mirror `frontend/src/api/types.ts`.
- Tests run against real Postgres via `DATABASE_URL` — no SQLite fallback, no SQLite type variants on models.
- Test fixtures must not hard-code primary keys or collide with baseline seeds (they must pass on both the empty CI DB and a seeded `make bootstrap` DB).
- `ruff`, `ruff format`, `mypy --strict` stay green (`make lint`).
- Do not change the `CurrentActor` dataclass fields — ticket 7 is building against that shape.

## Review Focus

1. **Email probing by unauthorised users** — a `member` POSTing `addMember` with someone's email must get `rejected`, never `confirm_existing` (which would reveal the email exists). Test in Task 2.
2. **Unknown `functionKey` on add** — must be `rejected`, not silently stored as "no function" (which would also bypass the function-scope check). Test in Task 2.
3. **Actor with no active membership** (unallocated person) — list returns empty, add/extend/move reject, detail 404s. Test in Task 3.
4. **Dev-header flag left on in a deployed environment** — default must be off; the flag must be documented as dev-only. Test in Task 4 (flag unset ⇒ 401 even with a valid header).
5. **Running tests on a seeded local DB** — must pass after `make bootstrap`, not only on empty CI. Verified in Task 1 Step 4.

---

### Task 1: Postgres-only tests, seed-safe fixture, restore deleted docs (findings 7, 8)

**Files:**
- Modify: `backend/tests/conftest.py` — revert to `main`'s version (uses `app.db.session.engine`).
- Modify: `backend/app/db/session.py` — revert to `main`'s `os.environ["DATABASE_URL"]` (fail fast, no hardcoded password).
- Modify: `backend/app/models/privacy.py` — revert to `main`'s version (drops SQLite variants, restores the §8.3 FK rationale and "must never contain personal data" comments).
- Modify: `backend/app/models/__init__.py` — revert to `main`'s docstring.
- Modify: `backend/app/main.py` — keep `include_router(api_router)`; restore a module docstring that explains what the file is and that routers are mounted from `app/api/router.py`; restore the CORS comment.
- Modify: `backend/app/repositories/membership.py` — restore `main`'s module docstring paragraph ("Current membership is never a stored flag…") and `get_active_memberships_for_person` docstring, appended to the new module summary.
- Modify: `backend/tests/test_membership_api.py` — rewrite the fixture (below).

**Interfaces:**
- Produces: fixture `client_with_actor` yielding `tuple[TestClient, dict[str, CurrentActor], Seed]`, where `Seed` is a `@dataclass` in the test file with attributes:
  `term, lc_usyd, lc_mu, fn_ogv, fn_bnm, pos_member, pos_tl, pos_lcvp, pos_lcp, team_a, team_b, m_lcvp, m_member_usyd, m_member_mu, m_tl, p_lcvp, p_member_usyd, p_member_mu, p_tl` (ORM objects, flushed so `.id` is set).
  Later tasks add `lcp` to `actor_map` and `m_lcp`/`p_lcp` to `Seed` as needed.
- Produces: helper `_get_or_create(session: Session, model: type[T], *, key: str, **defaults: Any) -> T` in the test file — looks up `Function`/`Position` by `key`, creates if absent. Use it for every lookup table that baseline seeds populate. LCs, persons, terms and teams are created fresh with test-unique names/emails (prefix `test-`, e.g. `test-usyd`, `test-lcvp@aiesec.net`) and no explicit `id=`.

- [ ] **Step 1: Migrate local DB to head**

Run: `make migrate`
Expected: `alembic current` prints the same revision as `alembic heads`.

- [ ] **Step 2: Apply the reverts and doc restorations listed under Files**

Run: `git checkout main -- backend/tests/conftest.py backend/app/db/session.py backend/app/models/privacy.py backend/app/models/__init__.py`, then hand-edit `main.py` and the repository docstrings.

- [ ] **Step 3: Rewrite the fixture and every test to use `seed.<obj>.id`** instead of literal ids (`/api/v1/members/{seed.m_member_usyd.id}`, `{"teamId": seed.team_b.id}`, `db_session.get(Membership, seed.m_member_mu.id)`, `assert data["membershipId"] == str(seed.m_member_usyd.id)`). Assertions on LC names become `"test-usyd"` / `"test-mu"`.

- [ ] **Step 4: Run on the seeded local DB**

Run: `docker compose exec -T backend uv run pytest -q`
Expected: all pass (the 7 `test_membership_api.py` errors from `UniqueViolation ... function_pkey` are gone).

- [ ] **Step 5: Lint and commit**

Run: `make lint` — expected clean.
```bash
git add backend/
git commit -m "fix: DEV-0042 run API tests on real Postgres and restore removed docs"
```

---

### Task 2: Enforce permissions on `addMember` (finding 1)

**Files:**
- Modify: `backend/app/core/permissions.py`
- Modify: `backend/app/repositories/membership.py` (`add_member`)
- Test: `backend/tests/test_membership_api.py`, `backend/tests/test_permissions.py`

**Interfaces:**
- Consumes: `Seed`, `_get_or_create` (Task 1); existing `can_add_member(...) -> tuple[bool, str | None]`.
- Produces in `permissions.py`:
  - `MC_POSITIONS: set[str] = {"mcd", "mcvp", "mcp"}`
  - `def position_level(position_key: str) -> Literal["lc", "mc"]` — `"mc"` if key in `MC_POSITIONS` else `"lc"`. Comment: fallback until ticket 2 adds `position.level` (same pattern as `POSITION_RANKS`).

Order of checks in `add_member` after the change (the order is the decision — it closes the email-probing hole):
1. `end_date < start_date` → rejected (existing).
2. Resolve LC, position; if `function_key` given and not found → `rejected`, message `"Function not found."`.
3. **`can_add_member(actor_memberships, target_lc_id=lc.id, target_lc_type=lc.type.value, target_position_key=pos.key, target_position_rank=<rank as build_membership_context computes it>, target_position_level=position_level(pos.key), target_function_id=func.id if func else None, target_team_id=team_id)`** → if not allowed, `{"status": "rejected", "message": reason}`.
4. Only then: person lookup, `needs_name` / `confirm_existing`, MC-overlap block, duplicate function, create/transfer (existing logic).

- [ ] **Step 1: Write failing tests** in `test_membership_api.py`:

```python
def test_add_member_denied_for_plain_member(client_with_actor, db_session):
    # actor = member; email belongs to an existing person
    resp = client.post("/api/v1/members", json={... "email": seed.p_member_mu.aiesec_email, "lcId": seed.lc_usyd.id, "positionKey": "member", ...})
    assert resp.json()["status"] == "rejected"          # NOT "confirm_existing"
    assert db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "membership.create")) == 0

def test_add_member_denied_outside_lc(...):        # lcvp (test-usyd) adds into test-mu → rejected, message "You cannot add people outside your scope."
def test_add_member_denied_equal_rank(...):        # lcvp adds positionKey "lcvp" in own LC → rejected, "You cannot add someone of equal or higher rank."
def test_add_member_denied_mc_position_in_lc(...): # lcvp adds positionKey "mcvp" into test-usyd → rejected, "Position level does not match LC type."
def test_add_member_unknown_function_rejected(...):# functionKey "nope" → rejected, "Function not found."
def test_add_member_allowed_new_person(...):       # lcvp adds new email as member in own LC with firstName/lastName → "created"; Person row exists
```

And in `test_permissions.py`: `test_position_level_mc_keys` asserting `position_level("mcvp") == "mc"` and `position_level("lcvp") == "lc"`.

- [ ] **Step 2: Run to verify they fail**

Run: `docker compose exec -T backend uv run pytest tests/test_membership_api.py -k add_member -v`
Expected: the five denial tests FAIL (currently return `confirm_existing`/`created`); `test_add_member_allowed_new_person` may already pass.

- [ ] **Step 3: Implement** `MC_POSITIONS`, `position_level`, and the check order above. Extract the rank lookup duplicated in `build_membership_context`/`list_members_summary`/`get_membership_detail` into `def _position_rank(pos: Position | None) -> int` in the repository and use it here.

- [ ] **Step 4: Run tests** — same command plus `tests/test_permissions.py`. Expected: PASS, including the existing transfer test.

- [ ] **Step 5: Commit** — `fix: DEV-0042 enforce matrix and rank checks on addMember`

---

### Task 3: Scope-check `getMembershipDetail` (finding 2)

**Files:**
- Modify: `backend/app/core/permissions.py`
- Modify: `backend/app/repositories/membership.py` (`get_membership_detail`)
- Test: `backend/tests/test_membership_api.py`, `backend/tests/test_permissions.py`

**Interfaces:**
- Produces: `def can_view_membership(actor_memberships: Sequence[MembershipContext], target: MembershipContext) -> bool` — `resolve_widest_scope(..., "membership", "view")`, `None` ⇒ False, else `scope_covers(...)` with the target's person/LC/function/team. No rank check (viewing is not a write; §3.4's rank rule governs writes).
- `get_membership_detail` returns `None` (⇒ existing 404) when `can_view_membership` is False — 404 rather than 403 so ids in other LCs aren't confirmed to exist.

- [ ] **Step 1: Write failing tests**

```python
def test_get_membership_detail_other_lc_is_404(...):   # lcvp (test-usyd) GET m_member_mu → 404
def test_get_membership_detail_denied_for_member(...): # actor = member, GET m_tl → 404
def test_actor_without_membership_gets_nothing(...):   # CurrentActor(person=<new person>, active_memberships=[], acting_membership=None):
    # list → 200, items == [], total == 0; detail → 404; extend/move → status "rejected"; add → "rejected"
```
Plus `test_can_view_membership_lc_scope` in `test_permissions.py` (same LC True, other LC False).

- [ ] **Step 2: Run to verify they fail** — `pytest tests/test_membership_api.py -k "detail or without_membership" -v`. Expected: the two 404 tests FAIL with 200.

- [ ] **Step 3: Implement** `can_view_membership`; call it in `get_membership_detail` after loading `m` (build the target via `build_membership_context`).

- [ ] **Step 4: Run tests** — expected PASS, including existing `test_get_membership_detail`.

- [ ] **Step 5: Commit** — `fix: DEV-0042 apply LC isolation to membership detail`

---

### Task 4: Fail-closed auth stub and correct acting membership (findings 3, 6)

**Files:**
- Modify: `backend/app/api/deps.py`
- Modify: `.env.example`, `docs/local-development.md` (one short paragraph)
- Test: `backend/tests/test_deps.py` (create)

**Interfaces:**
- `get_current_actor` signature unchanged. New behaviour:
  - Reads `os.environ.get("DEV_ACTOR_HEADER_ENABLED")` **at call time** (so tests can `monkeypatch.setenv`). Anything other than `"true"` ⇒ `401`, detail `"Sign-in is not available yet"`, regardless of header.
  - When enabled: existing header lookup.
  - `acting_membership` = the active membership with the highest position rank (use `build_membership_context(db, m).position_rank` as the key), not `active_memberships[0]`. Update the module docstring: the header path is dev-only and ticket 7 replaces it; tests use `app.dependency_overrides[get_current_actor]`.
- `.env.example`: `DEV_ACTOR_HEADER_ENABLED=false` with comment `# Dev only: trust X-Actor-Email as the signed-in user. NEVER enable in a deployed environment. Removed by ticket 7.`

- [ ] **Step 1: Write failing tests** in `tests/test_deps.py` (call the dependency function directly with `db_session`):

```python
def test_header_ignored_when_flag_unset(monkeypatch, db_session): # delenv → HTTPException 401 even for a real person's email
def test_header_accepted_when_flag_true(monkeypatch, db_session): # setenv "true" → returns CurrentActor for that person
def test_acting_membership_is_highest_rank(monkeypatch, db_session):
    # person with a member membership (created first) and an lcvp membership → acting_membership is the lcvp one
```

- [ ] **Step 2: Run to verify they fail** — `pytest tests/test_deps.py -v`. Expected: first and third FAIL.

- [ ] **Step 3: Implement** as specified.

- [ ] **Step 4: Run full suite** — `docker compose exec -T backend uv run pytest -q`. Expected: PASS (API tests use `dependency_overrides`, so they're unaffected).

- [ ] **Step 5: Commit** — `fix: DEV-0042 make dev actor header opt-in and pick highest-rank acting membership`

---

### Task 5: Real term resolution and correct audit actor (findings 4, 5)

**Files:**
- Modify: `backend/app/repositories/membership.py`
- Test: `backend/tests/test_membership_api.py`

**Interfaces:**
- Produces in the repository:
  - `def _resolve_term_id(session: Session, term_id: int | None, start_date: date) -> int | None` — if `term_id` given: return it if a `Term` with that id exists, else `None`. If not given: the `Term` with `start_date <= start_date <= end_date` (latest `start_date` wins if several). `add_member` returns `rejected`, message `"No term covers that start date."`, on `None`. Remove `term_id or 1`.
  - `def _audit_actor(actor_memberships: Sequence[MembershipContext]) -> dict[str, int | None]` — returns `{"actor_membership_id": ..., "actor_person_id": ...}` from `get_acting_membership(...)`; used via `**_audit_actor(actor_memberships)` in all four `record_audit` calls (create, transfer end_term, extend_term, move).

- [ ] **Step 1: Write failing tests**

```python
def test_add_member_resolves_term_from_start_date(...): # no termId; startDate 2026-11-01 → created membership.term_id == seed.term.id (or any term covering that date)
def test_add_member_rejects_date_outside_any_term(...): # startDate 2099-01-01 → rejected, "No term covers that start date."
def test_audit_records_acting_membership_and_person(...):
    # actor with [m_member-like lower-rank membership, m_lcvp] in that order; extend m_member_usyd
    # audit.actor_membership_id == seed.m_lcvp.id and audit.actor_person_id == seed.p_lcvp.id
```

- [ ] **Step 2: Run to verify they fail** — `pytest tests/test_membership_api.py -k "term or audit_records" -v`.

- [ ] **Step 3: Implement** both helpers and wire them in.

- [ ] **Step 4: Run full suite + lint** — `docker compose exec -T backend uv run pytest -q && make lint`. Expected: all green.

- [ ] **Step 5: Commit** — `fix: DEV-0042 resolve term from dates and audit the acting membership`

---

## Not in this plan (flag to PR author, don't fix here)

- `list_members_summary` uses the first membership's LC for the row and every role's `level` — wrong for multi-LC people, but transfers end other-LC memberships, so rare. Raise as a follow-up comment.
- Non-numeric `lcId` is silently ignored — harmless; the frontend only sends ids from the API.
- Team Leaders see the whole LC in `listMembers` though their matrix scope is `team` — matches the ticket's LC-isolation wording; confirm intent with the Tech Lead before changing.
