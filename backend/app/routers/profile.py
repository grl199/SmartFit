from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user_id
from ..models import UserProfile, UserTarget
from ..schemas import ProfileIO, TargetIO

router = APIRouter(tags=["profile"])


@router.get("/profile", response_model=ProfileIO)
def get_profile(db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    return db.get(UserProfile, uid) or ProfileIO()


@router.put("/profile", response_model=ProfileIO)
def put_profile(body: ProfileIO, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    p = db.get(UserProfile, uid) or UserProfile(user_id=uid)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    db.add(p)
    db.commit()
    return p


@router.get("/targets", response_model=TargetIO)
def get_targets_(db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    return db.get(UserTarget, uid)


@router.put("/targets", response_model=TargetIO)
def put_targets(body: TargetIO, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    t = db.get(UserTarget, uid) or UserTarget(user_id=uid)
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    db.add(t)
    db.commit()
    return t
