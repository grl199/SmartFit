"""Estimación orientativa de platos a partir de texto o fotografía.

La IA propone ingredientes, cantidades y nutrientes por 100 g. El usuario debe revisar
y confirmar el resultado antes de crear el alimento y su registro en el diario.
"""
from __future__ import annotations

import base64
import json
import math
import re
from typing import Any

from ..config import get_settings
from ..llm import create_chat_completion, get_chat_client
from .images import prepare_for_llm


class VisionEstimationDisabled(RuntimeError):
    """La estimación por fotografía no está activada en esta instalación."""


NUTRIENT_FIELDS = {
    "kcal": "kcal_per_100g",
    "protein_g": "protein_g_per_100g",
    "carbs_g": "carbs_g_per_100g",
    "sugars_g": "sugars_g_per_100g",
    "fat_g": "fat_g_per_100g",
    "sat_fat_g": "sat_fat_g_per_100g",
    "fiber_g": "fiber_g_per_100g",
    "sodium_mg": "sodium_mg_per_100g",
}

SYSTEM_PROMPT = """Eres un asistente de estimación nutricional para una aplicación de diario de comida.
Descompón el plato en ingredientes reconocibles y estima los gramos comestibles de cada uno.
Para cada ingrediente estima los nutrientes por 100 g: kcal, proteína, hidratos, azúcares,
grasa, saturadas, fibra y sodio (mg). Usa valores plausibles de alimentos genéricos cocinados
o crudos según corresponda; no inventes marcas ni afirmes precisión de laboratorio.
En una fotografía, estima las cantidades de forma conservadora y explica las suposiciones
visuales relevantes. Si no puedes identificar un ingrediente, usa un nombre genérico y baja
la confianza. Devuelve ÚNICAMENTE un objeto JSON, sin Markdown, con esta estructura:
{
  "name": "nombre breve del plato",
  "items": [{
    "name": "ingrediente",
    "grams": 80,
    "kcal_per_100g": 120,
    "protein_g_per_100g": 5,
    "carbs_g_per_100g": 10,
    "sugars_g_per_100g": 2,
    "fat_g_per_100g": 4,
    "sat_fat_g_per_100g": 1,
    "fiber_g_per_100g": 2,
    "sodium_mg_per_100g": 100,
    "confidence": "low"
  }],
  "assumptions": ["suposición breve"]
}
Incluye entre 1 y 25 ingredientes. Los valores son aproximaciones, no inventes una báscula
ni deduzcas una precisión que la fotografía no permite. confidence debe ser low o medium.
"""


def _parse_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    text = re.sub(r"^\`\`\`(?:json)?\s*|\s*\`\`\`$", "", text, flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("La IA no devolvió una propuesta JSON válida")
    result = json.loads(text[start:end + 1])
    if not isinstance(result, dict):
        raise ValueError("La respuesta nutricional no tiene el formato esperado")
    return result


def normalize_estimate(payload: dict[str, Any]) -> dict[str, Any]:
    """Valida ingredientes y calcula totales de forma determinista, sin confiar en sumas del LLM."""
    name = str(payload.get("name") or "Comida estimada").strip()[:200] or "Comida estimada"
    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= 25:
        raise ValueError("La estimación debe contener entre 1 y 25 ingredientes")

    items: list[dict[str, Any]] = []
    totals = {key: 0.0 for key in NUTRIENT_FIELDS}
    total_grams = 0.0
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError("Ingrediente no válido en la estimación")
        item_name = str(raw.get("name") or "").strip()[:120]
        grams = float(raw.get("grams") or 0)
        if not item_name or not math.isfinite(grams) or not 0 < grams <= 5000:
            raise ValueError("Nombre o cantidad de ingrediente no válidos")
        item: dict[str, Any] = {"name": item_name, "grams": round(grams, 1)}
        per100: dict[str, float] = {}
        for key, field in NUTRIENT_FIELDS.items():
            value = float(raw.get(field) or 0)
            limit = 10000 if key == "sodium_mg" else 950 if key == "kcal" else 100
            if not math.isfinite(value) or value < 0 or value > limit:
                raise ValueError(f"Valor nutricional no válido para {item_name}: {field}")
            per100[key] = value
            item[field] = round(value, 2)
            totals[key] += value * grams / 100
        if per100["protein_g"] + per100["carbs_g"] + per100["fat_g"] > 105:
            raise ValueError(f"Los macronutrientes de {item_name} superan un valor plausible por 100 g")
        if per100["sugars_g"] > per100["carbs_g"] + 0.5 or per100["sat_fat_g"] > per100["fat_g"] + 0.5:
            raise ValueError(f"Los nutrientes de {item_name} son incoherentes")
        item["confidence"] = "medium" if raw.get("confidence") == "medium" else "low"
        items.append(item)
        total_grams += grams

    if not 0 < total_grams <= 5000:
        raise ValueError("La cantidad total estimada debe estar entre 0 y 5000 g")
    total_grams = round(total_grams, 1)
    totals = {key: round(value, 2) for key, value in totals.items()}
    per_100g = {
        NUTRIENT_FIELDS[key]: round(value * 100 / total_grams, 2)
        for key, value in totals.items()
    }
    assumptions = payload.get("assumptions") or []
    if not isinstance(assumptions, list):
        assumptions = []
    assumptions = [str(x).strip()[:240] for x in assumptions if str(x).strip()][:8]
    return {
        "name": name,
        "items": items,
        "assumptions": assumptions,
        "total_grams": total_grams,
        "totals": totals,
        "per_100g": per_100g,
        "confidence": "low",
    }


def estimate_meal(description: str, image: bytes | None = None) -> dict[str, Any]:
    """Estima texto con el proveedor configurado; Gemini u OpenAI pueden analizar fotografías."""
    settings = get_settings()
    user_text = description.strip() or (
        "Analiza la fotografía del plato. Identifica ingredientes, cantidades y estimación nutricional."
    )
    provider = settings.ai_provider.strip().lower()
    client = get_chat_client()
    if image is not None:
        if provider == "gemini":
            jpg, mime = prepare_for_llm(image)
            image_url = f"data:{mime};base64,{base64.b64encode(jpg).decode('ascii')}"
            kwargs: dict[str, Any] = {
                "model": settings.gemini_model,
                "service_tier": settings.gemini_service_tier,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ]},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
            }
            response = create_chat_completion(client, kwargs, service_tier=kwargs.get("service_tier"))
        elif provider == "openai" and settings.food_vision_enabled:
            jpg, mime = prepare_for_llm(image)
            image_url = f"data:{mime};base64,{base64.b64encode(jpg).decode('ascii')}"
            response = create_chat_completion(client, {
                "model": settings.food_vision_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ]},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            })
        else:
            raise VisionEstimationDisabled(
                "La estimación por fotografía requiere AI_PROVIDER=gemini o AI_PROVIDER=openai con FOOD_VISION_ENABLED=true."
            )
    else:
        model = (
            settings.openrouter_model if provider == "openrouter"
            else settings.openai_model if provider == "openai"
            else settings.gemini_model
        )
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.2,
        }
        if provider in ("openai", "gemini"):
            kwargs["response_format"] = {"type": "json_object"}
        if provider == "gemini":
            kwargs["service_tier"] = settings.gemini_service_tier
        response = create_chat_completion(client, kwargs, service_tier=kwargs.get("service_tier"))

    raw = response.choices[0].message.content or ""
    return normalize_estimate(_parse_json(raw))
