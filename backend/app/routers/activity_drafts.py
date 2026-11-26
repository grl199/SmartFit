"""Persistencia de borradores GPS para recuperar rutas interrumpidas."""
from datetime import timedelta
from fastapi import APIRouter,Depends,HTTPException,Path
from sqlalchemy import delete,func,select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import current_user_id
from ..models import ActivityDraft
from ..schemas import ActivityDraftIn,ActivityDraftOut
from ..services.nutrition import today_local
from ..services.route import MAX_ROUTE_POINTS,as_utc,merge_route_points
router=APIRouter(tags=["training"])
STALE_AFTER=timedelta(days=7)
CLIENT_ID=Path(pattern=r"^[A-Za-z0-9_-]{8,64}$")
def _out(d:ActivityDraft)->ActivityDraftOut:
    return ActivityDraftOut(client_id=d.client_id,kind=d.kind,category=d.category,performed_on=d.performed_on,started_at=d.started_at,updated_at=d.updated_at,points=d.points or [],point_count=len(d.points or []))
def _find(db:Session,uid:int,cid:str,lock:bool=False):
    q=select(ActivityDraft).where(ActivityDraft.user_id==uid,ActivityDraft.client_id==cid)
    return db.scalar(q.with_for_update() if lock else q)
@router.put("/activity-drafts/{client_id}",response_model=ActivityDraftOut)
def upsert_activity_draft(body:ActivityDraftIn,client_id:str=CLIENT_ID,db:Session=Depends(get_db),uid:int=Depends(current_user_id)):
    incoming=[p.model_dump(mode="json") for p in body.points]
    for _ in range(2):
        d=_find(db,uid,client_id,lock=True)
        if d is None:
            db.execute(delete(ActivityDraft).where(ActivityDraft.user_id==uid,ActivityDraft.updated_at<func.now()-STALE_AFTER))
            d=ActivityDraft(user_id=uid,client_id=client_id,kind=body.kind.strip(),category=body.category,performed_on=body.performed_on or today_local(),started_at=as_utc(body.started_at),points=[])
            db.add(d)
        merged=merge_route_points(d.points or [],incoming)
        if len(merged)>MAX_ROUTE_POINTS:raise HTTPException(422,f"Un recorrido no puede tener más de {MAX_ROUTE_POINTS} puntos GPS.")
        d.kind,d.category=body.kind.strip(),body.category
        if body.performed_on:d.performed_on=body.performed_on
        d.points=merged;d.updated_at=func.now()
        try:db.commit()
        except IntegrityError:db.rollback();continue
        db.refresh(d);return _out(d)
    raise HTTPException(409,"No se pudo guardar el recorrido; inténtalo de nuevo.")
@router.get("/activity-drafts/active",response_model=ActivityDraftOut|None)
def active_activity_draft(db:Session=Depends(get_db),uid:int=Depends(current_user_id)):
    d=db.scalar(select(ActivityDraft).where(ActivityDraft.user_id==uid,ActivityDraft.updated_at>=func.now()-STALE_AFTER).order_by(ActivityDraft.updated_at.desc()).limit(1))
    return _out(d) if d else None
@router.delete("/activity-drafts/{client_id}",status_code=204)
def delete_activity_draft(client_id:str=CLIENT_ID,db:Session=Depends(get_db),uid:int=Depends(current_user_id)):
    db.execute(delete(ActivityDraft).where(ActivityDraft.user_id==uid,ActivityDraft.client_id==client_id));db.commit()
