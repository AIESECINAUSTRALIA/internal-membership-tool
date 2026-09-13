"""The membership lifecycle: `membership`, `team`, `team_member`.

A `membership` row is never edited to reflect a change — see spec §5.1 and
`docs/data-model.md`. There is deliberately no `is_current` column: whether a
row is current is answered by a query against `start_date` / `end_date`
(`app/repositories/membership.py::get_active_memberships_for_person`), never a
stored flag that could drift out of sync.
"""

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Membership(Base):
    """A person's assignment to an LC, in a position (and usually a function),
    for a term. A person may hold several concurrent rows."""

    __tablename__ = "membership"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"))
    lc_id: Mapped[int] = mapped_column(ForeignKey("lc.id"))
    position_id: Mapped[int] = mapped_column(ForeignKey("position.id"))
    # Nullable because some positions (e.g. LCP) aren't tied to one function.
    function_id: Mapped[int | None] = mapped_column(ForeignKey("function.id"), nullable=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("term.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Flags a person's "main" concurrent membership for UI purposes only —
    # not used for access control (spec §3.2: access is the union of all).
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class Team(Base):
    """A team within one function within one LC, for one term."""

    __tablename__ = "team"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lc_id: Mapped[int] = mapped_column(ForeignKey("lc.id"))
    function_id: Mapped[int] = mapped_column(ForeignKey("function.id"))
    term_id: Mapped[int] = mapped_column(ForeignKey("term.id"))
    name: Mapped[str] = mapped_column(String)
    leader_membership_id: Mapped[int | None] = mapped_column(
        ForeignKey("membership.id"), nullable=True
    )


class TeamMember(Base):
    """Join table between `membership` and `team`, time-scoped the same way
    as `membership` so team history is preserved the same way."""

    __tablename__ = "team_member"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("team.id"))
    membership_id: Mapped[int] = mapped_column(ForeignKey("membership.id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
