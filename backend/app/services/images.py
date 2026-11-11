"""Decodificación determinista de códigos de barras (no se delega en el LLM: los LLM leen mal dígitos)."""
import io

import zxingcpp
from PIL import Image, ImageOps, UnidentifiedImageError


def _open(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        return ImageOps.exif_transpose(img).convert("RGB")  # las fotos de móvil vienen rotadas por EXIF
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError("Imagen no válida") from e


def _fit(img: Image.Image, max_side: int) -> Image.Image:
    img = img.copy()
    img.thumbnail((max_side, max_side))
    return img


def _read(img: Image.Image) -> list[str]:
    out: list[str] = []
    for r in zxingcpp.read_barcodes(img):
        t = r.text.strip()
        if t.isdigit() and len(t) in (8, 12, 13) and t not in out:  # EAN-8 / UPC-A / EAN-13
            out.append(t)
    return out


def decode_barcodes(data: bytes) -> list[str]:
    """Prueba varias variantes de la imagen (original, gris, reducida + autocontraste)."""
    img = _open(data)
    gray = ImageOps.grayscale(img)
    for candidate in (img, gray, ImageOps.autocontrast(_fit(gray, 1200)), _fit(gray, 700)):
        found = _read(candidate)
        if found:
            return found
    return []


def prepare_for_llm(data: bytes, max_side: int = 1600) -> tuple[bytes, str]:
    """Reduce la foto antes de enviarla al modelo (menos tokens y menos latencia)."""
    img = _fit(_open(data), max_side)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), "image/jpeg"
