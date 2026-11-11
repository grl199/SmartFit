# HealthApp

Seguimiento de nutrición y entrenamiento con un asistente (OpenAI + búsqueda web) que consulta tus datos reales.

```
Streamlit ──HTTP──▶ FastAPI ──▶ PostgreSQL (+pgvector)
                      │
                      ├─▶ Agente (OpenAI Responses API)
                      │     ├─ web_search (hosted tool)
                      │     └─ function tools: resúmenes SQL, barcode, foods, log_food, RAG, remember
                      ├─▶ Open Food Facts (barcode → nutrientes)
                      ├─▶ zxing-cpp (decodifica el código de la foto, determinista)
                      └─▶ Vault (API key de OpenAI)
```

## Puesta en marcha

```bash
docker compose --profile vault up -d          # Postgres+pgvector y Vault (dev)

# Guardar la API key en Vault (KV v2, mount "secret")
docker compose exec -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN=dev-root-token vault \
  vault kv put -mount=secret healthapp/openai api_key=sk-...

cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                          # ajusta API_TOKEN, OFF_USER_AGENT, modelo...
uvicorn app.main:app --reload                 # http://localhost:8000/docs

cd ../frontend && pip install -r requirements.txt
API_TOKEN=<el mismo> streamlit run Home.py
```
En VS Code: `.vscode/launch.json` incluye ambas configuraciones de depuración.
Tests: `cd backend && pytest`.

## Decisiones de diseño

- **Código de barras fuera del LLM.** Se decodifica con zxing-cpp (los LLM fallan con dígitos) y el resultado se inyecta en el
  mensaje; el agente llama a `lookup_barcode` → BD local → Open Food Facts → `web_search` → `create_food` (cachea para la próxima vez).
- **Snapshot de nutrientes en cada registro** (`food_logs`): editar un alimento no reescribe el histórico.
- **Datos exactos con SQL, memoria difusa con RAG.** Las preguntas numéricas usan `get_day_summary` / `get_period_summary`.
  pgvector indexa resúmenes diarios + notas (`remember`) para preguntas cualitativas sobre el pasado.
- **Perfil → system prompt**, junto con objetivos y totales de hoy, en cada turno.
- **`log_food` exige confirmación** (instrucción del prompt). Para garantía dura, hazlo en dos pasos: tool `propose_log` + botón en la UI.
- La API de OpenAI se usa con `store` por defecto; si no quieres que OpenAI retenga datos de salud, pasa `store=False`
  y gestiona el estado de la conversación tú mismo (hay que reenviar los items de salida en lugar de `previous_response_id`).
- Modelo configurable (`OPENAI_MODEL`). Las llamadas a `web_search` se facturan por llamada además de los tokens.

## Pendiente antes de producción

Auth real (JWT/OIDC en `deps.current_user_id`; ya todo filtra por `user_id`), Vault con AppRole, Alembic, streaming SSE en el chat,
rate-limit en `/chat`, backups, HTTPS, zona horaria por usuario, límite de coste por usuario.
