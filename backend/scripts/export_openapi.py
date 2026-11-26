"""Export the FastAPI application's OpenAPI schema for TypeScript clients.

Run from the repository root:
    python backend/scripts/export_openapi.py

The app is imported without starting its lifespan, opening database connections,
or requiring deployment secrets. FastAPI's registered routers and Pydantic models
remain the single source of truth for the generated contract.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
OUTPUT_PATH = REPOSITORY_ROOT / "packages" / "contracts" / "openapi.json"


def main() -> None:
    sys.path.insert(0, str(BACKEND_ROOT))

    try:
        from app.main import app
    except Exception as exc:  # noqa: BLE001 - preserve the original import error as the cause
        raise SystemExit(
            "No se pudo cargar SmartFit API. Instala primero "
            "'backend/requirements.txt' con el Python del backend."
        ) from exc

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    OUTPUT_PATH.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"OpenAPI {schema.get('openapi', 'unknown')} exportado: {OUTPUT_PATH.relative_to(REPOSITORY_ROOT)}")


if __name__ == "__main__":
    main()
