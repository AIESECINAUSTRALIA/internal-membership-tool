"""Server-side authentication sessions for EXPA OAuth."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserSession(Base):
    __tablename__ = "user_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Only the SHA-256 digest is stored, never the raw cookie token.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    # Pending OAuth sessions have no associated person.
    person_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("person.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Hash of the OAuth state, used to validate the callback.
    oauth_state_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Indexed: `purge_stale_sessions` deletes by it on every sign-in.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
