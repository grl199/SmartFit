# HealthApp

Seguimiento de nutrición y entrenamiento con un asistente que consulta tus datos reales. El proveedor de IA es seleccionable por variable de entorno: OpenRouter u OpenAI.

```
Streamlit ──HTTP──▶ FastAPI ──▶ PostgreSQL (+pgvector)
                      │
                      ├─▶ Agente (OpenRouter Chat Completions u OpenAI Responses API)
                      │     ├─ herramientas locales: resúmenes SQL, barcode, foods, log_food, RAG, remember
                      │     └─ web_search alojado (solo OpenAI)
                      ├─▶ Embeddings RAG (OpenRouter u OpenAI según AI_PROVIDER)
                      ├─▶ Open Food Facts (barcode → nutrientes)
                      ├─▶ zxing-cpp (decodifica el código de la foto, determinista)
                      └─▶ Vault (opcional, API key de OpenAI directo)
```

## Puesta en marcha

```bash
docker compose up -d db                       # Postgres+pgvector
# Solo si usas OpenAI con Vault: docker compose --profile vault up -d

cd backend
python3 -m venv .venv                          # solo la primera vez
source .venv/bin/activate
python -m pip install -r requirements.txt
test -f .env || cp .env.example .env            # después configura OPENROUTER_API_KEY y API_TOKEN
python -m uvicorn app.main:app --reload        # http://localhost:8000/docs

# En otra terminal:
cd frontend
python3 -m venv .venv                          # solo la primera vez
source .venv/bin/activate
python -m pip install -r requirements.txt
export API_TOKEN="$(sed -n 's/^API_TOKEN=//p' ../backend/.env)"
python -m streamlit run Home.py
```

## Selección del proveedor

En `backend/.env`:

```dotenv
# OpenRouter
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=openai/gpt-oss-20b:free
OPENROUTER_EMBEDDING_MODEL=openai/text-embedding-3-small

# Para volver a OpenAI:
# AI_PROVIDER=openai
# OPENAI_MODEL=gpt-5.5
```

`openai/gpt-oss-20b:free` es la variante gratuita de chat de OpenRouter, sujeta a límites y disponibilidad. Los embeddings se envían también a OpenRouter con `openai/text-embedding-3-small` y pueden generar cargos separados. Este modelo de chat acepta texto, no imágenes: los códigos de barras de las fotos se decodifican localmente, pero no se pueden leer etiquetas o analizar imágenes.

Con `AI_PROVIDER=openrouter`, el chat y los embeddings usan la clave de OpenRouter. Las herramientas locales (SQL, alimentos, registro y memoria) siguen activas; no hay búsqueda web integrada en este flujo. OpenAI directo mantiene su flujo original, incluido `web_search`, cuando `AI_PROVIDER=openai`.

## Decisiones de diseño

- **Código de barras fuera del LLM.** Se decodifica con zxing-cpp y el resultado se inyecta en el mensaje.
- **Snapshot de nutrientes en cada registro** (`food_logs`): editar un alimento no reescribe el histórico.
- **Datos exactos con SQL, memoria difusa con RAG.** pgvector indexa resúmenes diarios + notas (`remember`).
- **Perfil → system prompt**, junto con objetivos y totales de hoy, en cada turno.
- **`log_food` exige confirmación** (instrucción del prompt).
- Al cambiar de proveedor o modelo de embeddings, reindexa la memoria existente desde `POST /rag/reindex` para que todos los vectores compartan el mismo espacio semántico. La operación usa el modelo de embeddings configurado y puede tener coste.

## Tests

```bash
cd backend && pytest
```

## Pendiente antes de producción

Auth real (JWT/OIDC en `deps.current_user_id`), Vault con AppRole, Alembic, streaming SSE en el chat, rate-limit en `/chat`, backups, HTTPS, zona horaria por usuario y límite de coste por usuario.
