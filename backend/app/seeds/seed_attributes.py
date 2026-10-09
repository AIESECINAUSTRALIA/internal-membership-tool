"""Seed a placeholder attribute catalog: non-KPI custom fields and KPIs.

**Neither list here is authoritative.** Spec §12 items 3 and 4 mark "classify
current LC spreadsheet columns into person/membership/KPI attributes" and
"per-function KPI list + natural period" as open TODOs, pending real
spreadsheets and a confirmed KPI list (referred to as "Epic 2" in the
ticket). Nobody has supplied that source data into this repo yet.

This seed exists so the `attribute` / `attribute_value` / `kpi_record`
mechanism (migrations, write-path validation, rollup queries) can be built
and tested now, rather than blocking on that TODO — see
`docs/data-model.md` for the same reasoning already applied to
`seed_lookups.py`'s `position`/`function` seed. It is a small, deliberately
obvious placeholder, not a guess at the real catalog.

Both `attribute` and `attribute_value` are runtime-editable (spec §1.5), so
once the real classification/KPI list lands, correcting these rows is an
admin task done through the app — not a new migration or a code change.

Idempotent: skips any `key` that already exists, so running this more than
once (`make seed`) is safe.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.attribute import Attribute, AttributeAppliesTo, AttributeDataType

# --- Non-KPI custom fields (placeholder — spec §12 item 3) -----------------
CUSTOM_ATTRIBUTES: list[dict[str, object]] = [
    {
        "key": "shirt_size",
        "label": "Shirt size",
        "applies_to": AttributeAppliesTo.PERSON,
        "data_type": AttributeDataType.ENUM,
        "enum_options": ["XS", "S", "M", "L", "XL", "XXL"],
        "validation": {"required": False},
    },
    {
        "key": "dietary_requirements",
        "label": "Dietary requirements",
        "applies_to": AttributeAppliesTo.PERSON,
        "data_type": AttributeDataType.TEXT,
        "validation": {"required": False},
    },
    {
        "key": "onboarding_complete",
        "label": "Onboarding complete",
        "applies_to": AttributeAppliesTo.MEMBERSHIP,
        "data_type": AttributeDataType.BOOLEAN,
        "validation": {"required": False},
    },
]

# --- KPI catalog (placeholder — spec §12 item 4) ----------------------------
KPI_CATALOG: list[dict[str, object]] = [
    {
        "key": "ol_signups",
        "label": "OL Signups",
        "unit": "count",
        "data_type": AttributeDataType.NUMBER,
        "validation": {"required": True, "min": 0},
    },
    {
        "key": "ep_interviews",
        "label": "EP Interviews",
        "unit": "count",
        "data_type": AttributeDataType.NUMBER,
        "validation": {"required": True, "min": 0},
    },
    {
        "key": "eps_matched",
        "label": "EPs Matched",
        "unit": "count",
        "data_type": AttributeDataType.NUMBER,
        "validation": {"required": True, "min": 0},
    },
]


def seed_custom_attributes(session: Session) -> None:
    existing_keys = set(session.execute(select(Attribute.key)).scalars())
    for row in CUSTOM_ATTRIBUTES:
        if row["key"] not in existing_keys:
            session.add(Attribute(**row))


def seed_kpi_catalog(session: Session) -> None:
    existing_keys = set(session.execute(select(Attribute.key)).scalars())
    for row in KPI_CATALOG:
        if row["key"] not in existing_keys:
            session.add(Attribute(applies_to=AttributeAppliesTo.KPI, **row))


def main() -> None:
    with SessionLocal() as session:
        seed_custom_attributes(session)
        session.flush()
        seed_kpi_catalog(session)
        session.commit()


if __name__ == "__main__":
    main()
