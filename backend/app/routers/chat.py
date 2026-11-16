from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..agent.agent import DEFAULT_TITLE, run_agent
from ..db import get_db
from ..deps import current_user_id, read_image
from ..models import ChatMessage, Conversation
from ..schemas import ChatMessageOut, ChatOut, ConversationOut, ConversationRename
from ..services.rag import reindex_all

router = APIRouter(tags=["chat"])
MAX_CONVERSATIONS = 200


def _own(db: Session, conv_id: int, uid: int) -> Conversation:
    conv = db.get(Conversation, conv_id)
    if not conv or conv.user_id != uid:
        raise HTTPException(404, "Conversación no encontrada")
    return conv


# `def` (no async): el SDK de OpenAI y SQLAlchemy son síncronos -> FastAPI lo ejecuta en su threadpool.
@router.post("/chat", response_model=ChatOut)
def chat(message: str = Form(""), image: UploadFile | None = File(None), conversation_id: int | None = Form(None),
         db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Envía un mensaje. Sin `conversation_id` se crea una conversación nueva (queda guardada en el histórico)."""
    if not message.strip() and image is None:
        raise HTTPException(422, "Escribe un mensaje o adjunta una imagen")
    data = read_image(image) if image else None
    if conversation_id is None:
        conv = Conversation(user_id=uid, title=DEFAULT_TITLE)
        db.add(conv)
        db.commit()
    else:
        conv = _own(db, conversation_id, uid)
    try:
        return run_agent(db, uid, message, data, conv.id)
    except ValueError as e:  # imagen corrupta
        raise HTTPException(422, str(e))


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(limit: int = Query(50, ge=1, le=MAX_CONVERSATIONS), db: Session = Depends(get_db),
                       uid: int = Depends(current_user_id)):
    """Histórico: más recientes primero. Las conversaciones vacías no se listan."""
    counts = (select(ChatMessage.conversation_id, func.count().label("n")).where(ChatMessage.user_id == uid)
              .group_by(ChatMessage.conversation_id).subquery())
    rows = db.execute(select(Conversation, func.coalesce(counts.c.n, 0)).outerjoin(counts, counts.c.conversation_id == Conversation.id)
                      .where(Conversation.user_id == uid, func.coalesce(counts.c.n, 0) > 0)
                      .order_by(Conversation.updated_at.desc(), Conversation.id.desc()).limit(limit)).all()
    return [ConversationOut.model_validate(c).model_copy(update={"message_count": n}) for c, n in rows]


@router.get("/conversations/{conv_id}/messages", response_model=list[ChatMessageOut])
def conversation_messages(conv_id: int, limit: int = Query(200, ge=1, le=500), db: Session = Depends(get_db),
                          uid: int = Depends(current_user_id)):
    _own(db, conv_id, uid)
    rows = db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conv_id)
                      .order_by(ChatMessage.id.desc()).limit(limit)).all()
    return list(reversed(rows))


@router.patch("/conversations/{conv_id}", response_model=ConversationOut)
def rename_conversation(conv_id: int, body: ConversationRename, db: Session = Depends(get_db),
                        uid: int = Depends(current_user_id)):
    conv = _own(db, conv_id, uid)
    conv.title = body.title.strip()
    db.commit()
    n = db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.conversation_id == conv_id)) or 0
    return ConversationOut.model_validate(conv).model_copy(update={"message_count": n})


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: int, db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    conv = _own(db, conv_id, uid)
    db.execute(delete(ChatMessage).where(ChatMessage.conversation_id == conv_id))
    db.delete(conv)
    db.commit()


@router.post("/rag/reindex")
def reindex(db: Session = Depends(get_db), uid: int = Depends(current_user_id)):
    """Recrea los embeddings existentes y actualiza los resúmenes diarios."""
    return reindex_all(db, uid)
