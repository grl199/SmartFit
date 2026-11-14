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
test -f .env || cp .env.example .env            # después configura OPENROUTER_API_KEY y SECRET_KEY
python -m uvicorn app.main:app --reload        # http://localhost:8000/docs

# En otra terminal:
cd frontend
python3 -m venv .venv                          # solo la primera vez
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run Home.py                # http://localhost:8501
```

**Primer acceso:** abre la app y crea una cuenta (pestaña «Crear cuenta»). Si ya tenías datos del usuario 1 de una
versión anterior, pon `BOOTSTRAP_USERNAME` y `BOOTSTRAP_PASSWORD` en `backend/.env` antes de arrancar el backend
y entra con esas credenciales: conservas todo tu histórico.

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

## Autenticación y onboarding

- **Login con usuario y contraseña.** Las contraseñas se guardan con argon2id; la sesión es un JWT (`TOKEN_TTL_HOURS`,
  12 h por defecto) que el frontend guarda en `st.session_state` (al recargar la página hay que volver a entrar).
  Tras 5 intentos fallidos en 10 minutos el usuario queda bloqueado temporalmente.
- **Registro y baja.** `POST /auth/register` (se puede desactivar con `ALLOW_REGISTRATION=false`) y `DELETE /auth/me`,
  que exige la contraseña y **borra todos los datos** del usuario. En la app: «Crear cuenta» y Perfil → «Eliminar mi cuenta».
- **Onboarding obligatorio.** Un usuario recién registrado no puede usar nada (la API devuelve 403 `onboarding_required`)
  hasta completar el perfil. `POST /onboarding` guarda el perfil y el peso y le pide a la IA los objetivos de nutrición y un plan
  de entrenamiento. El **código** calcula el metabolismo basal (Mifflin-St Jeor) y el gasto total; la **IA** decide déficit/superávit,
  macros y plan; el código **valida** la respuesta (mínimos de kcal, proteína g/kg, coherencia macros↔kcal, días de entreno) y
  reintenta una vez. Si falla, el perfil queda guardado y se puede reintentar.
- **Salvaguardas:** solo adultos (18-100 años) y no se genera un objetivo de pérdida de grasa con IMC < 18,5.
- **Listas cerradas** (`app/enums.py`, servidas en `GET /meta/options`): objetivo, nivel de actividad, experiencia y sexo.
  `alergias/restricciones` y `notas` siguen siendo texto libre.
- El perfil completo, los objetivos y el plan de entrenamiento se inyectan en el system prompt del agente en cada turno.

## Modelo de datos

Todas las tablas y columnas llevan `comment=` en `app/models.py`, que se aplica como `COMMENT ON` en cada arranque
(`\d+ tabla` en psql, o el panel de DBeaver/pgAdmin). Un test impide añadir columnas sin documentar.
`app/migrations.py` añade de forma idempotente las columnas nuevas a bases de datos de versiones anteriores y normaliza
los valores de texto libre antiguos (conservándolos en `context_notes`). Cuando el esquema se estabilice, pasa a Alembic.

## Búsqueda de alimentos

- **Por texto, mientras escribes** (Registrar → Buscar): primero Postgres, instantáneo y sin acentos. Si hay menos de 5 resultados
  y la consulta tiene ≥ 3 caracteres, se completa con Open Food Facts (*search-a-licious*) y **todo lo encontrado se guarda** en
  `foods`, de modo que la siguiente búsqueda ya es local.
- Open Food Facts limita las búsquedas a **10/min/IP**, por eso hay debounce en la interfaz, un límite propio
  (`OFF_SEARCH_PER_MINUTE`) y una caché de consultas recientes. Si OFF falla, la búsqueda local sigue funcionando.
- **Por código de barras:** cualquier código de 8 a 32 dígitos. Los EAN/UPC/GTIN se consultan en OFF; los demás (códigos internos de
  tienda, peso variable) solo se resuelven contra tu base de datos: créalos una vez a mano y se reconocerán al escanearlos.
- `python scripts/check_off_search.py "yogur griego"` comprueba la búsqueda de OFF con la red real y muestra el formato de los datos.
- El agente usa la misma búsqueda híbrida en su herramienta `search_foods`.

## Decisiones de diseño

- **Código de barras fuera del LLM.** Se decodifica con zxing-cpp y el resultado se inyecta en el mensaje.
- **Snapshot de nutrientes en cada registro** (`food_logs`): editar un alimento no reescribe el histórico.
- **Datos exactos con SQL, memoria difusa con RAG.** pgvector indexa resúmenes diarios + notas (`remember`).
- **Perfil → system prompt**, junto con objetivos y totales de hoy, en cada turno.
- **`log_food` exige confirmación** (instrucción del prompt).
- Al cambiar de proveedor o modelo de embeddings, reindexa la memoria existente desde `POST /rag/reindex` para que todos los vectores compartan el mismo espacio semántico. La operación usa el modelo de embeddings configurado y puede tener coste.

## Tests

```bash
cd backend && pytest                            # tests puros
# Tests de API (necesitan Postgres+pgvector; usa una BD distinta de la de desarrollo):
docker compose exec db createdb -U health health_test
TEST_DATABASE_URL=postgresql+psycopg://health:health@localhost:5432/health_test pytest
```

## Pendiente antes de producción

Cambio de contraseña y recuperación de cuenta, sesión persistente tras recargar (cookie HttpOnly), Vault con AppRole, Alembic, streaming SSE en el chat, rate-limit en `/chat`, backups, HTTPS, zona horaria por usuario y límite de coste por usuario.
