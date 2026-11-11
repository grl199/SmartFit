# HealthApp

Seguimiento de nutrición y entrenamiento con un asistente que consulta tus datos reales. El proveedor de IA es seleccionable por variable de entorno: Hugging Face u OpenAI.

```
Streamlit ──HTTP──▶ FastAPI ──▶ PostgreSQL (+pgvector)
                      │
                      ├─▶ Agente (Hugging Face Chat Completions u OpenAI Responses API)
                      │     ├─ herramientas locales: resúmenes SQL, barcode, foods, log_food, RAG, remember
                      │     └─ web_search alojado (solo OpenAI)
                      ├─▶ Embeddings RAG (Hugging Face u OpenAI según AI_PROVIDER)
                      ├─▶ Open Food Facts (barcode → nutrientes)
                      ├─▶ zxing-cpp (decodifica el código de la foto, determinista)
                      └─▶ Vault (API key de OpenAI)
```

## Puesta en marcha

```bash
docker compose --profile vault up -d          # Postgres+pgvector y Vault (opcional)

cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                          # ajusta AI_PROVIDER, HUGGINGFACE_API_KEY y API_TOKEN
uvicorn app.main:app --reload                 # http://localhost:8000/docs

cd ../frontend && pip install -r requirements.txt
API_TOKEN=<el mismo> streamlit run Home.py
```

## Selección del proveedor

En `backend/.env`:

```dotenv
# Recomendado para evitar consumo de créditos OpenAI
AI_PROVIDER=huggingface
HUGGINGFACE_API_KEY=hf_...
HUGGINGFACE_MODEL=Qwen/Qwen2.5-VL-7B-Instruct

# Para volver a OpenAI:
# AI_PROVIDER=openai
# OPENAI_MODEL=gpt-5.5
```

Hugging Face usa el router OpenAI-compatible para chat y su endpoint de inferencia para embeddings. El token de Hugging Face es necesario incluso para modelos públicos. El nivel gratuito de Inference Providers tiene cuotas, límites de velocidad y disponibilidad de modelos/proveedores variables; no implica uso ilimitado ni SLA. El modelo seleccionado debe estar disponible en un proveedor compatible y admitir llamadas a herramientas. El modelo Qwen VL conserva la entrada de imágenes cuando el proveedor la soporta.

Con `AI_PROVIDER=huggingface`, no se consulta Vault ni se hacen llamadas de chat/embeddings a OpenAI. Las herramientas locales (SQL, alimentos, registro y memoria) siguen activas. La búsqueda web alojada de OpenAI no está disponible en Hugging Face; el asistente lo indicará en lugar de fingir una búsqueda. OpenAI mantiene su flujo original, incluido `web_search`, cuando se selecciona.

## Decisiones de diseño

- **Código de barras fuera del LLM.** Se decodifica con zxing-cpp y el resultado se inyecta en el mensaje.
- **Snapshot de nutrientes en cada registro** (`food_logs`): editar un alimento no reescribe el histórico.
- **Datos exactos con SQL, memoria difusa con RAG.** pgvector indexa resúmenes diarios + notas (`remember`).
- **Perfil → system prompt**, junto con objetivos y totales de hoy, en cada turno.
- **`log_food` exige confirmación** (instrucción del prompt).
- Los embeddings multilingües de Hugging Face (384 dimensiones) se completan con ceros hasta la dimensión pgvector actual (1536 por defecto). Así se evita una migración destructiva de los vectores ya almacenados. Al cambiar de proveedor/modelo conviene reindexar el histórico para que todos los vectores usen el mismo espacio semántico.

## Tests

```bash
cd backend && pytest
```

## Pendiente antes de producción

Auth real (JWT/OIDC en `deps.current_user_id`), Vault con AppRole, Alembic, streaming SSE en el chat, rate-limit en `/chat`, backups, HTTPS, zona horaria por usuario y límite de coste por usuario.
