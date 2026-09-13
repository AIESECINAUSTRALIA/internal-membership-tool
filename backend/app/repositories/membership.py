"""Queries over `membership`.

"Current membership" is never a stored flag — it's derived from
`start_date`/`end_date` at query time (spec §4.1, §5.1), so a membership
change (position, function, team, leaving) only ever needs an end-date on the
old row and a new row, never an update to some `is_current` column that could
drift out of sync.
"""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.membership import Membership


def get_active_memberships_for_person(
    session: Session, person_id: int, as_of: date | None = None
) -> Sequence[Membership]:
    """Memberships for `person_id` that are current as of `as_of` (default: today).

    A membership is current when it has started (`start_date <= as_of`) and
    either has no end date yet or hasn't ended (`end_date IS NULL OR
    end_date >= as_of`). A person can hold several concurrent memberships
    (spec §5.1), so this can return more than one row.
    """
    reference_date = as_of if as_of is not None else date.today()
    stmt = select(Membership).where(
        Membership.person_id == person_id,
        Membership.start_date <= reference_date,
        or_(Membership.end_date.is_(None), Membership.end_date >= reference_date),
    )
    return session.execute(stmt).scalars().all()
