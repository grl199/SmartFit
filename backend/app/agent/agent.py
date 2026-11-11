import base64
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..llm import get_client
from ..models import ChatMessage
from ..services.images import decode_barcodes, prepare_for_llm
from .prompts import build_system_prompt
from .tools import FUNCTION_TOOLS, ToolContext, run_tool

log = logging.getLogger(__name__)
MAX_STEPS = 8
HISTORY_TURNS = 12
TOOLS = [{"type": "web_search"}, *FUNCTION_TOOLS]


def _collect(resp, sources: list[dict], used: list[str]) -> list:
    """Acumula fuentes web y nombres de herramientas; devuelve las function_calls pendientes."""
    calls = []
    for item in resp.output:
        if item.type == "function_call":
            calls.append(item)
            used.append(item.name)
        elif item.type == "web_search_call":
            used.append("web_search")
        elif item.type == "message":
            for part in item.content:
                for a in getattr(part, "annotations", None) or []:
                    if getattr(a, "type", "") == "url_citation" and all(s["url"] != a.url for s in sources):
                        sources.append({"title": a.title, "url": a.url})
    return calls


def run_agent(db: Session, user_id: int, message: str, image: bytes | None = None) -> dict:
    s, client = get_settings(), get_client()
    ctx = ToolContext(db, user_id)
    system = build_system_prompt(db, user_id)

    text = message.strip() or ("Analiza esta imagen." if image else "")
    content: list[dict] = []
    barcodes: list[str] = []
    if image:
        barcodes = decode_barcodes(image)  # determinista, antes de llamar al modelo
        text += "\n\n[Sistema: " + (
            f"códigos de barras detectados en la imagen: {', '.join(barcodes)}]" if barcodes
            else "no se ha detectado ningún código de barras legible en la imagen]")
        jpg, mime = prepare_for_llm(image)
        content.append({"type": "input_image", "image_url": f"data:{mime};base64,{base64.b64encode(jpg).decode()}"})
    content.insert(0, {"type": "input_text", "text": text})

    past = db.scalars(select(ChatMessage).where(ChatMessage.user_id == user_id)
                      .order_by(ChatMessage.id.desc()).limit(HISTORY_TURNS * 2)).all()
    history = [{"role": m.role, "content": m.content} for m in reversed(past)]

    kwargs = {"model": s.openai_model, "instructions": system, "tools": TOOLS}
    if s.openai_reasoning_effort:
        kwargs["reasoning"] = {"effort": s.openai_reasoning_effort}

    sources: list[dict] = []
    used: list[str] = []
    resp = client.responses.create(input=[*history, {"role": "user", "content": content}], **kwargs)
    for _ in range(MAX_STEPS):
        calls = _collect(resp, sources, used)
        if not calls:
            break
        outputs = [{"type": "function_call_output", "call_id": c.call_id,
                    "output": run_tool(ctx, c.name, c.arguments)} for c in calls]
        # Dentro de un turno encadenamos con previous_response_id; `instructions` NO se hereda.
        resp = client.responses.create(input=outputs, previous_response_id=resp.id, **kwargs)
    else:
        log.warning("MAX_STEPS alcanzado")

    reply = resp.output_text or "No he podido completar la respuesta; ¿puedes reformular la pregunta?"
    db.add(ChatMessage(user_id=user_id, role="user", content=message.strip() + (" 📷" if image else "")))
    db.add(ChatMessage(user_id=user_id, role="assistant", content=reply))
    db.commit()
    return {"reply": reply, "sources": sources, "tools_used": list(dict.fromkeys(used)), "barcodes": barcodes}
