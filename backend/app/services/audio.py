"""Voice-note transcription shared by food estimation and chat.

Audio is processed in memory and is never persisted by this service.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import types

from ..config import get_settings
from ..llm import get_openai_client

MAX_AUDIO_BYTES = 19 * 1024 * 1024
SUPPORTED_AUDIO_MIME_TYPES = {
    "audio/aac", "audio/flac", "audio/m4a", "audio/mp3", "audio/mpeg",
    "audio/mp4", "audio/ogg", "audio/opus", "audio/wav", "audio/webm",
    "audio/x-aac",
}


def audio_transcription_available() -> bool:
    """Whether the configured environment has credentials for a transcription provider."""
    settings = get_settings()
    if settings.gemini_api_key:
        return True
    return bool(settings.openai_api_key or settings.vault_addr)


def _normalise_mime(mime_type: str | None, filename: str | None) -> str:
    mime = (mime_type or "").split(";", 1)[0].strip().lower()
    if mime in ("application/octet-stream", "") and filename:
        suffix = Path(filename).suffix.lower()
        mime = {
            ".aac": "audio/aac", ".flac": "audio/flac", ".m4a": "audio/m4a",
            ".mp3": "audio/mpeg", ".mp4": "audio/mp4", ".oga": "audio/ogg",
            ".ogg": "audio/ogg", ".opus": "audio/opus", ".wav": "audio/wav",
            ".webm": "audio/webm",
        }.get(suffix, mime)
    if mime == "audio/x-wav":
        mime = "audio/wav"
    if mime == "audio/x-m4a":
        mime = "audio/m4a"
    if mime not in SUPPORTED_AUDIO_MIME_TYPES:
        raise ValueError("Formato de audio no compatible. Usa WAV, MP3, M4A, OGG o WebM.")
    return mime


def transcribe_audio(data: bytes, mime_type: str | None = None, filename: str | None = None) -> str:
    """Transcribe a voice note in its original language, prioritising an available Gemini key."""
    if not data:
        raise ValueError("La nota de voz está vacía.")
    settings = get_settings()
    mime = _normalise_mime(mime_type, filename)

    if settings.gemini_api_key:
        if len(data) > MAX_AUDIO_BYTES:
            raise ValueError("La nota de voz supera el límite de 19 MB para el envío directo a Gemini.")
        client = genai.Client(api_key=settings.gemini_api_key)
        prompt = (
            "Transcribe literalmente esta nota de voz en el idioma original. "
            "Es una persona describiendo alimentos, cantidades, ingredientes y pasos de una receta. "
            "Conserva nombres, cantidades y unidades; no resumas, no inventes y devuelve solo la transcripción."
        )
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                prompt,
                types.Part.from_bytes(data=data, mime_type=mime),
            ],
            config=types.GenerateContentConfig(temperature=0),
        )
        transcript = (response.text or "").strip()
    elif settings.openai_api_key or settings.vault_addr:
        if len(data) > 24 * 1024 * 1024:
            raise ValueError("La nota de voz supera el límite de 24 MB para la transcripción.")
        suffix = Path(filename or "").suffix or {
            "audio/wav": ".wav", "audio/webm": ".webm", "audio/ogg": ".ogg",
            "audio/m4a": ".m4a", "audio/mp3": ".mp3", "audio/mpeg": ".mp3",
            "audio/mp4": ".mp4", "audio/flac": ".flac", "audio/aac": ".aac",
        }.get(mime, ".wav")
        result = get_openai_client().audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=(filename or f"nota-de-voz{suffix}", BytesIO(data), mime),
            language="es",
            prompt=(
                "Transcripción en español de una nota de voz sobre recetas y alimentación. "
                "Presta atención a ingredientes, cantidades, gramos, mililitros y pasos de preparación."
            ),
        )
        transcript = (result.text or "").strip()
    else:
        raise RuntimeError(
            "Las notas de voz requieren GEMINI_API_KEY o AI_PROVIDER=openai con una clave de OpenAI directa o en Vault. "
            "OpenRouter por sí solo no incluye transcripción de audio en esta configuración."
        )

    if not transcript:
        raise ValueError("No se ha podido reconocer voz en la grabación. Prueba a grabarla de nuevo.")
    return transcript
