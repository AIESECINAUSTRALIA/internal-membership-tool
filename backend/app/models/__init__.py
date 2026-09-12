"""Import every model module so `Base.metadata` is fully populated.

A model class that's never imported never registers its table with
`Base.metadata` — needed by Alembic's `env.py` for autogenerate, and by
anything else that builds a schema from the metadata. As tables from later
tickets (`attribute`, `kpi`, `permission`, `privacy`) grow real models, import
them here too.
"""

from app.models import membership, org, person  # noqa: F401
