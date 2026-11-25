"""Seed `position` and `function` with a working baseline.

This is explicitly **not** the authoritative list — spec §2 marks the real
positions/functions list as a `TODO:`, pending confirmation against AIESEC
Australia's current national structure docs. Both tables are runtime-editable
(spec §1.5), so once the authoritative list lands, correcting these rows is an
admin task done through the app, not a new migration or a code change.

Idempotent: skips any `key` that already exists, so running this more than
once (`make seed`) is safe.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.org import Function, Position

# Spec §2: a HIGHER `rank` is a HIGHER position (Member = 1 ... MCP = 7). The
# permission code compares ranks (§3.4), so this order matters.
# `can_add_same_rank` is the president exception: an LCP may add another LCP (§3.4).
POSITIONS: list[dict[str, object]] = [
    {"key": "lcp", "label": "LC President", "rank": 4, "level": "lc", "can_add_same_rank": True},
    {"key": "lcvp", "label": "LC Vice President", "rank": 3, "level": "lc"},
    {"key": "team_leader", "label": "Team Leader", "rank": 2, "level": "lc"},
    {"key": "member", "label": "Member", "rank": 1, "level": "lc"},
]

FUNCTIONS: list[dict[str, object]] = [
    {"key": "ogv", "label": "oGV"},
    {"key": "igv", "label": "iGV"},
    {"key": "ogta_oget", "label": "oGTa / oGET"},
    {"key": "igte", "label": "iGTe"},
    {"key": "bd", "label": "BD"},
    {"key": "fnl", "label": "F&L"},
    {"key": "mkt", "label": "MKT"},
    {"key": "pmim_digital", "label": "PM&IM / Digital"},
    {"key": "ewa", "label": "EwA"},
    {"key": "mxp", "label": "MXP"},
]


def seed_positions(session: Session) -> None:
    existing_keys = set(session.execute(select(Position.key)).scalars())
    for row in POSITIONS:
        if row["key"] not in existing_keys:
            session.add(Position(**row))


def seed_functions(session: Session) -> None:
    existing_keys = set(session.execute(select(Function.key)).scalars())
    for row in FUNCTIONS:
        if row["key"] not in existing_keys:
            session.add(Function(**row))


def main() -> None:
    with SessionLocal() as session:
        seed_positions(session)
        seed_functions(session)
        session.commit()


if __name__ == "__main__":
    main()
