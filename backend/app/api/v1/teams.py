"""Team management endpoints (spec §1.5, §2A.2).

Reading teams needs a signed-in actor. Every mutating endpoint also needs
`manage` on `team`, checked by `require_team_manager`. There is no delete
endpoint: a team is removed by disbanding it (setting active=False).
"""

from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, get_current_actor, get_db
from app.core.permissions import can_manage_team
from app.models.membership import Team
from app.repositories.membership import build_membership_context
from app.repositories.team import (
    create_team,
    disband_team,
    get_team,
    list_teams,
    move_member,
    reassign_leader,
    rename_team,
    reparent_team,
)
from app.schemas.team import (
    MoveMemberRequest,
    TeamCreate,
    TeamResponse,
    TeamUpdate,
)

router = APIRouter(prefix="/teams", tags=["teams"])


def _require_team_manager(
    lc_id: int,
    actor: CurrentActor,
    db: Session,
) -> CurrentActor:
    """Allow only actors holding `manage` on `team` for the given LC; else 403."""
    contexts = [build_membership_context(db, m) for m in actor.active_memberships]
    if not can_manage_team(contexts, lc_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage teams in this LC",
        )
    return actor


def _actor_membership_id(actor: CurrentActor) -> int | None:
    if actor.acting_membership is None:
        return None
    return actor.acting_membership.id


def _get_team_or_404(db: Session, team_id: int) -> Team:
    team = get_team(db, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")
    return team


@router.get("", response_model=list[TeamResponse])
def list_teams_endpoint(
    lc_id: int,
    term_id: int | None = None,
    include_inactive: bool = False,
    _actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> Sequence[Team]:
    return list_teams(db, lc_id=lc_id, term_id=term_id, include_inactive=include_inactive)


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
def create_team_endpoint(
    lc_id: int,
    body: TeamCreate,
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> Team:
    _require_team_manager(lc_id, actor, db)
    try:
        team = create_team(
            db,
            lc_id=lc_id,
            function_id=body.function_id,
            term_id=body.term_id,
            name=body.name,
            actor_membership_id=_actor_membership_id(actor),
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return team


@router.patch("/{team_id}", response_model=TeamResponse)
def update_team_endpoint(
    team_id: int,
    body: TeamUpdate,
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> Team:
    team = _get_team_or_404(db, team_id)
    _require_team_manager(team.lc_id, actor, db)

    if body.active is True:
        raise HTTPException(
            status_code=400,
            detail="A disbanded team cannot be re-activated",
        )

    actor_id = _actor_membership_id(actor)
    try:
        if body.name is not None:
            rename_team(db, team_id=team_id, new_name=body.name,
                        actor_membership_id=actor_id)
        if body.function_id is not None:
            reparent_team(db, team_id=team_id, new_function_id=body.function_id,
                          actor_membership_id=actor_id)
        if "leader_membership_id" in body.model_fields_set:
            reassign_leader(db, team_id=team_id,
                            new_leader_membership_id=body.leader_membership_id,
                            actor_membership_id=actor_id)
        if body.active is False:
            disband_team(db, team_id=team_id, actor_membership_id=actor_id)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.refresh(team)
    return team


@router.post("/{team_id}/move-member", response_model=TeamResponse)
def move_member_endpoint(
    team_id: int,
    body: MoveMemberRequest,
    actor: CurrentActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> Team:
    team = _get_team_or_404(db, team_id)
    _require_team_manager(team.lc_id, actor, db)
    try:
        move_member(
            db,
            membership_id=body.membership_id,
            new_team_id=team_id,
            actor_membership_id=_actor_membership_id(actor),
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.refresh(team)
    return team
