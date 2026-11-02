"""Homepage endpoint (spec §2A.4). What the chart shows is recorded in
docs/home-chart.md.

The chart plots one KPI, month by month, over the viewer's current term. Whose
data it covers comes from the viewer's position (`home_chart_scope`), never from
the request: the optional `kpi` query parameter only changes *which* KPI is
plotted, so it can't widen what a viewer sees.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.core.permissions import HomeChartScope, home_chart_scope
from app.models.attribute import Attribute
from app.models.membership import Team
from app.models.org import Function, Term
from app.repositories.attribute import AttributeValidationError
from app.repositories.kpi import (
    list_home_chart_kpis,
    month_starts,
    monthly_totals,
    resolve_home_chart_kpi,
)
from app.repositories.membership import build_membership_context
from app.schemas.home import HomeChart, HomeChartPoint, KpiRef

router = APIRouter(prefix="/home", tags=["home"])


def _kpi_ref(attribute: Attribute) -> KpiRef:
    return KpiRef(key=attribute.key, label=attribute.label, unit=attribute.unit)


def _scope_label(
    db: Session, scope: HomeChartScope, team_id: int | None, function_id: int | None
) -> str:
    """The "whose data" half of the chart title, e.g. "oGV Team 1"."""
    if scope == "team":
        team = db.get(Team, team_id) if team_id else None
        return team.name if team else "your team"
    if scope == "function":
        function = db.get(Function, function_id) if function_id else None
        return function.label if function else "your function"
    return "All LCs"


@router.get("/chart", response_model=HomeChart)
def get_home_chart(
    kpi: str | None = Query(default=None, description="KPI key; omit for the function default"),
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> HomeChart:
    """The homepage chart for the signed-in person (getHomeChart)."""
    acting = actor.acting_membership
    if acting is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You have not been allocated yet, please contact someone in your EB or MC",
        )
    context = build_membership_context(db, acting)
    scope = home_chart_scope(context.position_key)

    try:
        attribute = resolve_home_chart_kpi(db, function_id=acting.function_id, kpi_key=kpi)
    except AttributeValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    where = _scope_label(db, scope, context.team_id, acting.function_id)
    title = f"{attribute.label if attribute else 'Monthly activity'}, {where}"

    points: list[HomeChartPoint] = []
    term = db.get(Term, acting.term_id)
    if attribute is not None and term is not None:
        # The current term, up to today: no point plotting months that haven't happened.
        start, end = term.start_date, min(term.end_date, date.today())
        totals = monthly_totals(
            db,
            attribute_id=attribute.id,
            scope=scope,
            start=start,
            end=end,
            lc_id=acting.lc_id,
            function_id=acting.function_id,
            team_id=context.team_id,
        )
        # No records at all is "No data exists", not a flat line of zeros.
        if totals:
            points = [
                HomeChartPoint(month=month.strftime("%Y-%m"), value=totals.get(month, 0.0))
                for month in month_starts(start, end)
            ]

    return HomeChart(
        scope=scope,
        kpi=_kpi_ref(attribute) if attribute else None,
        availableKpis=[
            _kpi_ref(a) for a in list_home_chart_kpis(db, function_id=acting.function_id)
        ],
        title=title,
        period="monthly",
        points=points,
    )
