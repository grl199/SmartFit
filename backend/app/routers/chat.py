from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..agent.agent import run_agent
from ..db import get_db
from ..deps import current_user_id, read_image
from ..models import ChatMessage
from ..schemas import ChatMessageOut, ChatOut
from ..services.rag import reindex_all

router = APIRouter(tags=["chat"])


# `def` (no async): el SDK de OpenAI y SQLAlchemy son síncronos -> FastAPI lo ejecuta en su threadpool.
@router.post("/chat", response_model=ChatOut)
def chat(message: str = Form(""), image: UploadFile | None = File(None),
         db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    if not message.strip() and image is None:
        raise HTTPException(422, "Escribe un mensaje o adjunta una imagen")
    data = read_image(image) if image else None
    try:
        return run_agent(db, uid, message, data)
    except ValueError as e:  # imagen corrupta
        raise HTTPException(422, str(e))


@router.get("/chat/history", response_model=list[ChatMessageOut])
def history(limit: int = Query(50, le=200), db: Session = Depends(get_db),
            uid: int = Depends(current_user_id)):
    rows = db.scalars(select(ChatMessage).where(ChatMessage.user_id == uid)
                      .order_by(ChatMessage.id.desc()).limit(limit)).all()
    return list(reversed(rows))


@router.delete("/chat/history", status_code=204)
def clear_history(db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    db.execute(delete(ChatMessage).where(ChatMessage.user_id == uid))
    db.commit()


@router.post("/rag/reindex")
def reindex(db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Backfill: genera/actualiza el resumen vectorizado de todos los días con registros."""
    return {"days_indexed": reindex_all(db, uid)}
