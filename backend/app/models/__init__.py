"""A model class that's never imported never registers its table with
`Base.metadata` — needed by Alembic's `env.py` for autogenerate, and by
anything else that builds a schema from the metadata. As tables from later
tickets (`permission`) grow real models, import them here too.
"""

from app.models import attribute, kpi, membership, org, person, privacy  # noqa: F401
