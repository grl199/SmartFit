import base64
import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..llm import get_chat_client
from ..models import ChatMessage
from ..services.images import decode_barcodes, prepare_for_llm
from .prompts import build_system_prompt
from .tools import FUNCTION_TOOLS, ToolContext, run_tool

log = logging.getLogger(__name__)
MAX_STEPS = 8
HISTORY_TURNS = 12
OPENAI_TOOLS = [{"type": "web_search"}, *FUNCTION_TOOLS]


def _collect(resp, sources: list[dict], used: list[str]) -> list:
    """Recoge function calls y citas de la Responses API de OpenAI."""
    calls = []
    for item in resp.output:
        if item.type == "function_call":
            calls.append(item)
            used.append(item.name)
        elif item.type == "web_search_call":
            used.append("web_search")
        elif item.type == "message":
            for part in item.content:
                for annotation in getattr(part, "annotations", None) or []:
                    if (getattr(annotation, "type", "") == "url_citation"
                            and all(source["url"] != annotation.url for source in sources)):
                        sources.append({"title": annotation.title, "url": annotation.url})
    return calls


def _chat_tools() -> list[dict]:
    """Convierte el esquema de Responses API al formato Chat Completions."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        }
        for tool in FUNCTION_TOOLS
    ]


def _run_huggingface(client, model: str, system: str, history: list[dict],
                     content: list[dict], ctx: ToolContext, used: list[str]) -> str:
    """Bucle de herramientas compatible con el endpoint Chat Completions de HF."""
    messages = [{"role": "system", "content": system}, *history]
    user_content = []
    for part in content:
        if part["type"] == "input_text":
            user_content.append({"type": "text", "text": part["text"]})
        elif part["type"] == "input_image":
            user_content.append({
                "type": "image_url",
                "image_url": {"url": part["image_url"]},
            })
    messages.append({"role": "user", "content": user_content})
    tools = _chat_tools()

    for _ in range(MAX_STEPS):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.2,
        )
        assistant = response.choices[0].message
        calls = assistant.tool_calls or []
        if not calls:
            return assistant.content or ""

        messages.append({
            "role": "assistant",
            "content": assistant.content,
            "tool_calls": [call.model_dump(exclude_none=True) for call in calls],
        })
        for call in calls:
            name = call.function.name
            used.append(name)
            output = run_tool(ctx, name, call.function.arguments)
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": output,
            })
    log.warning("Hugging Face MAX_STEPS alcanzado")
    return "He alcanzado el límite de pasos de herramientas. ¿Puedes concretar un poco más?"


def run_agent(db: Session, user_id: int, message: str, image: bytes | None = None) -> dict:
    s = get_settings()
    client = get_chat_client()
    ctx = ToolContext(db, user_id)
    system = build_system_prompt(db, user_id)

    text = message.strip() or ("Analiza esta imagen." if image else "")
    content: list[dict] = []
    barcodes: list[str] = []
    if image:
        barcodes = decode_barcodes(image)
        text += "\n\n[Sistema: " + (
            f"códigos de barras detectados en la imagen: {', '.join(barcodes)}]"
            if barcodes else "no se ha detectado ningún código de barras legible en la imagen]"
        )
        jpg, mime = prepare_for_llm(image)
        content.append({
            "type": "input_image",
            "image_url": f"data:{mime};base64,{base64.b64encode(jpg).decode()}",
        })
    content.insert(0, {"type": "input_text", "text": text})

    past = db.scalars(
        select(ChatMessage).where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.id.desc()).limit(HISTORY_TURNS * 2)
    ).all()
    history = [{"role": item.role, "content": item.content} for item in reversed(past)]

    sources: list[dict] = []
    used: list[str] = []
    provider = s.ai_provider.strip().lower()

    if provider == "huggingface":
        # Hugging Face no ofrece el hosted web_search de OpenAI; se conservan
        # todas las herramientas locales (SQL, alimentos, registros y memoria).
        system += (
            "\n\nEste proveedor no dispone de búsqueda web integrada. No afirmes haber "
            "consultado Internet ni inventes fuentes; si falta información externa, "
            "explícalo claramente al usuario."
        )
        reply = _run_huggingface(
            client, s.huggingface_model, system, history, content, ctx, used
        )
    elif provider == "openai":
        kwargs = {"model": s.openai_model, "instructions": system, "tools": OPENAI_TOOLS}
        if s.openai_reasoning_effort:
            kwargs["reasoning"] = {"effort": s.openai_reasoning_effort}
        response = client.responses.create(
            input=[*history, {"role": "user", "content": content}], **kwargs
        )
        for _ in range(MAX_STEPS):
            calls = _collect(response, sources, used)
            if not calls:
                break
            outputs = [
                {"type": "function_call_output", "call_id": call.call_id,
                 "output": run_tool(ctx, call.name, call.arguments)}
                for call in calls
            ]
            response = client.responses.create(
                input=outputs, previous_response_id=response.id, **kwargs
            )
        else:
            log.warning("OpenAI MAX_STEPS alcanzado")
        reply = response.output_text or (
            "No he podido completar la respuesta; ¿puedes reformular la pregunta?"
        )
    else:
        raise ValueError(
            f"AI_PROVIDER no válido: {provider!r}. Usa 'openai' o 'huggingface'."
        )

    db.add(ChatMessage(
        user_id=user_id, role="user",
        content=message.strip() + (" 📷" if image else ""),
    ))
    db.add(ChatMessage(user_id=user_id, role="assistant", content=reply))
    db.commit()
    return {
        "reply": reply,
        "sources": sources,
        "tools_used": list(dict.fromkeys(used)),
        "barcodes": barcodes,
    }
