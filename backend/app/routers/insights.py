from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..clock import today_local
from ..db import get_db
from ..deps import current_user_id
from ..llm import chat_text
from ..services import progress_insights as svc

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("/insights")
def insights(days: int = Query(7, ge=3, le=90), ai: bool = False, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Análisis del periodo frente al anterior equivalente. Todo se calcula por código; con `ai=true` la IA redacta el resumen a partir de
    esos indicadores (si no está disponible, se devuelve el resumen determinista)."""
    data = svc.build(db, uid, today_local(), days)
    if ai and data["enough_data"]:
        data["ai_summary"] = svc.ai_rewrite(data, chat_text)
    return data
