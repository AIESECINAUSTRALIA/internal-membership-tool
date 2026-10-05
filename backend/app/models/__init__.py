"""Import every model module so `Base.metadata` is fully populated."""

from app.models import membership, org, person, privacy  # noqa: F401
