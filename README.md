# HealthApp

Seguimiento de nutrición y entrenamiento con un asistente que consulta tus datos reales. El proveedor de chat es seleccionable por variable de entorno: OpenRouter, OpenAI o Gemini.

```
Streamlit ──HTTP──▶ FastAPI ──▶ PostgreSQL (+pgvector)
                      │
                      ├─▶ Agente (OpenRouter, OpenAI Responses API o Gemini OpenAI-compatible API)
                      │     ├─ herramientas locales: resúmenes SQL, barcode, foods, log_food, RAG, remember
                      │     └─ web_search alojado (solo OpenAI)
                      ├─▶ Embeddings RAG (proveedor independiente para preservar el índice existente)
                      ├─▶ Open Food Facts (barcode → nutrientes)
                      ├─▶ zxing-cpp (decodifica el código de la foto, determinista)
                      ├─▶ Vault (opcional, API key de OpenAI directo)
                      └─▶ Cloud Run Secret Manager (GEMINI_API_KEY inyectada como variable de entorno)
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

`openai/gpt-oss-20b:free` es la variante gratuita de chat de OpenRouter, sujeta a límites y disponibilidad. Los embeddings se envían también a OpenRouter con `openai/text-embedding-3-small` y pueden generar cargos separados. Este modelo de chat acepta texto, no imágenes: los códigos de barras de las fotos se decodifican localmente.

**Gemini:** `AI_PROVIDER=gemini` usa el endpoint oficial compatible con OpenAI, por lo que mantiene el mismo bucle de function calling y las herramientas de SmartFit. El modelo por defecto es `gemini-3.1-flash-lite` con `GEMINI_SERVICE_TIER=flex` (menor coste y menor prioridad; cambia a `standard` si necesitas menor latencia). La API oficial publica para Flex un precio de USD 0,125/M tokens de entrada y USD 0,75/M de salida. Las fotos del chat y del registro de comida también se pueden analizar con Gemini.

En Cloud Run crea un secreto en **Secret Manager** y asígnalo a la variable `GEMINI_API_KEY` del contenedor (por ejemplo, `--update-secrets=GEMINI_API_KEY=smartfit-gemini-api-key:1`). Con variables de entorno, Google recomienda fijar una versión concreta del secreto. No añadas la clave a `.env`, al repositorio ni a los logs.

Ejemplo de despliegue (ajusta servicio, región y cuenta de servicio):

```bash
# La cuenta de servicio de Cloud Run necesita roles/secretmanager.secretAccessor.
gcloud secrets add-iam-policy-binding smartfit-gemini-api-key \\
  --member="serviceAccount:TU_SERVICE_ACCOUNT" \\
  --role="roles/secretmanager.secretAccessor"

gcloud run services update TU_SERVICIO --region TU_REGION \\
  --update-secrets=GEMINI_API_KEY=smartfit-gemini-api-key:1 \\
  --update-env-vars=AI_PROVIDER=gemini,GEMINI_MODEL=gemini-3.1-flash-lite,GEMINI_SERVICE_TIER=flex
```

Crea previamente `smartfit-gemini-api-key` en Secret Manager y carga la Gemini API key como una versión del secreto. Si el servicio ya tiene variables de entorno administradas por IaC, incorpora estos valores en esa configuración para que el siguiente despliegue no los sobrescriba.

**Embeddings y RAG:** se mantienen separados del proveedor de chat para no mezclar vectores de modelos distintos. Con `EMBEDDING_PROVIDER=auto` y `AI_PROVIDER=gemini`, SmartFit usa OpenRouter si existe `OPENROUTER_API_KEY`; como alternativa, OpenAI/Vault. Mantén esa credencial si usas RAG. No cambies el proveedor/modelo de embeddings sin reindexar primero todos los documentos.
Consulta también [los prompts para ampliar el catálogo y generar vídeos de ejercicios](docs/PROMPTS_CATALOGO_Y_VIDEOS.md).

### Estimación de comidas por IA

En Registrar → «Estimar con IA» puedes describir un plato, o introducir directamente las kcal totales cuando ya las
conoces. La propuesta por IA se desglosa en ingredientes y cantidades editables; el backend recalcula los nutrientes
y solo crea el alimento y el registro cuando confirmas. Las entradas estimadas quedan marcadas con confianza baja
y guardan el desglose usado. La descripción utiliza el proveedor configurado en `AI_PROVIDER`.

Con `AI_PROVIDER=gemini`, la fotografía utiliza el mismo modelo Gemini y la misma clave de Cloud Run. Con OpenAI,
se mantiene la opción separada `FOOD_VISION_ENABLED=true`, `FOOD_VISION_MODEL=gpt-4.1-mini` y OPENAI_API_KEY/Vault.
Las imágenes se procesan en memoria y no se guardan como archivos en la base de datos. Revisa siempre los ingredientes
y las cantidades estimadas, especialmente aceites, salsas y alimentos ocultos.

Con `AI_PROVIDER=openrouter`, el chat usa OpenRouter y los embeddings siguen su configuración independiente. Las herramientas locales (SQL, alimentos, registro y memoria) siguen activas; no hay búsqueda web integrada en este flujo. OpenAI directo mantiene su flujo original, incluido `web_search`, cuando `AI_PROVIDER=openai`. Gemini utiliza function calling e imágenes mediante el endpoint compatible con OpenAI; no añade grounding/búsqueda web automática.

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
los valores de texto libre antiguos (conservándolos en `context_notes`). Cuando el esquema se estabilice, pasa a Alembic. Al arrancar también se siembra el catálogo de ejercicios.

## Búsqueda de alimentos

- **Por texto, mientras escribes** (Registrar → Buscar): primero Postgres, instantáneo y sin acentos. Si hay menos de 5 resultados
  y la consulta tiene ≥ 3 caracteres, se completa con Open Food Facts (*search-a-licious*) y **todo lo encontrado se guarda** en
  `foods`, de modo que la siguiente búsqueda ya es local.
- Open Food Facts limita las búsquedas a **10/min/IP**, por eso hay debounce en la interfaz, un límite propio
  (`OFF_SEARCH_PER_MINUTE`) y una caché de consultas recientes. Si OFF falla, la búsqueda local sigue funcionando.
- **Por código de barras:** cualquier código de 8 a 32 dígitos, incluidos los de tienda de 24 dígitos (p. ej. los de Mercadona),
  que Open Food Facts también tiene. Primero se busca en tu base de datos y después en OFF; el resultado se guarda.
- `python scripts/check_off_search.py "yogur griego"` (o un código: `... 232839950000100350003502`) comprueba OFF con la red real y muestra el formato de los datos.
- El agente usa la misma búsqueda híbrida en su herramienta `search_foods`.
- **Metadatos de Open Food Facts** (se guardan y se muestran en la ficha del alimento): foto, **Nutri-Score**, grupo **NOVA**
  (nivel de procesamiento), **Eco-Score**, **alérgenos** (traducidos), ingredientes, categorías y tamaño del envase. El código de barras
  aparece en cada resultado de búsqueda y en la ficha. Si el buscador no los trae, se completan con una consulta al seleccionar el producto.

- **Nombres en español.** Open Food Facts guarda el nombre comercial del envase («Milbona Cottage Cheese – 200 g»). Al guardar un
  producto se limpia (se quitan la marca y la cantidad repetidas) y se muestra su «denominación general» en español; además la IA
  traduce los nombres en segundo plano (`TRANSLATE_NAMES`) y el original se conserva y también se busca. Perfil → «Traducir nombres
  pendientes» lo fuerza para los productos ya guardados.
- **Códigos de tienda ambiguos.** Los códigos que empiezan por 2 (y los de 24 dígitos de tienda) son de circulación restringida:
  distintas tiendas pueden reutilizarlos para productos diferentes. La app lo avisa con ⚠ y la ficha lo explica.

## Fuentes de datos de alimentos (estrategia)

Capas, de más fiable a menos; cada una alimenta a la anterior para que la app «aprenda» con el uso:

1. **Tu base de datos** (instantánea): lo que ya consumiste, lo que creaste, lo que guardó Open Food Facts y los productos confirmados
   por la comunidad. La búsqueda es **tolerante a erratas y variantes entre idiomas** (índice de trigramas: «pistacho» encuentra
   «Pistacchio»; «pandorp» encuentra «pandoro»).
2. **Open Food Facts** (código de barras y texto): todo lo que devuelve se guarda en tu base de datos.
3. **Catálogo comunitario**: un producto que creas con código de barras puede ofrecerse a los demás (casilla «Compartir con la
   comunidad»). Se publica **solo cuando otro usuario registra el mismo código con valores concordantes (±10 %)**, con la mediana de los
   valores, y sin revelar quién los aportó. Los códigos de tienda (prefijo 2) no se comparten.
4. **Foto de la etiqueta con IA** *(pendiente; requiere un modelo con visión)*: rellena el formulario para que lo confirmes.

Por qué **no** se rastrean webs de supermercados (Carrefour, Mercadona…): no ofrecen una API pública, sus condiciones suelen prohibir la
extracción automática y es frágil (cambian la web sin avisar). Para alimentos genéricos (no de marca) tendrían sentido tablas abiertas
de composición (CIQUAL, BEDCA, USDA), pero no resuelven productos de marca. Si un producto no está en ningún sitio, lo más fiable es el
código de barras (la URL de Carrefour solo trae un identificador propio; el EAN va impreso en el envase).

**Seguridad de datos compartidos:** cada usuario solo ve sus alimentos privados y los compartidos; el código de barras es único *por
propietario* (antes lo era globalmente: un código creado por un usuario podía devolverse a otro y dos usuarios no podían registrar el
mismo código).

## Chat

Cada conversación se guarda y tiene su propio historial: la barra lateral las agrupa por fecha (hoy, ayer, últimos 7 días…) y permite
saltar de una a otra, renombrarlas y eliminarlas. La primera pregunta da título a la conversación. Los mensajes que había antes de esta
versión quedan en «Conversación anterior».

## Entrenamiento

**Jerarquía de la sesión:** *Tipo* → Fuerza · Cardio (Andar · Correr · Otros deportes) · Cuerpo entero · Estiramientos.

- **Fuerza y estiramientos:** eliges **grupos muscular** por región, con un pictograma por músculo — *Tren superior:* abdominales, antebrazo,
  bíceps, cuello, dorsales, espalda baja, espalda superior, hombros, pecho, trapecio, tríceps · *Tren inferior:* abductores, aductores,
  cuádriceps, glúteos, isquiotibiales, pantorrillas.
- **Equipamiento** (con iconos): ninguno, banda de resistencia, banda de suspensión, barra, mancuerna, disco, máquina, pesa rusa, rueda,
  balón medicinal, banco(s), cajones, otros. Filtra los ejercicios que usan *alguno* de los elegidos; se combina con los músculos y
  con la búsqueda de texto. Lo que ya habías elegido no se pierde al cambiar los filtros.
- **Catálogo de 106 ejercicios** (fuerza, cuerpo entero y estiramientos) con músculo principal, secundarios y equipamiento; puedes crear
  los tuyos. Los estiramientos no cuentan como volumen de fuerza.
- **Otros deportes:** fútbol, tenis, pádel, baloncesto, natación, ciclismo… (el título toma el deporte; la IA estima las calorías).
- **Registro por series:** tabla editable por ejercicio (repeticiones, peso, RPE) precargada con lo que hiciste la última vez.
- **Calorías con IA:** la IA estima la **intensidad y el MET**; el **código** calcula `kcal = MET × peso(kg) × horas` y valida rangos.
  Si falla, la sesión se guarda igualmente y se puede recalcular desde el Historial.
- **Andar y correr** tienen sus métricas: distancia, **ritmo** (min/km) y velocidad (derivados), **desnivel positivo**, **pasos** y FC.
  Sus músculos se encienden en el mapa como «series equivalentes» según tiempo e intensidad (estimación orientativa). Progresión de
  ritmo, km por semana y desnivel en Progresión. *Preparado para Strava:* una actividad importada solo rellenaría estos mismos campos.
- **Mapa muscular** frontal y posterior (modo claro/oscuro) coloreado por series ponderadas por semana (principal = 1, secundarios = 0,5),
  ranking por músculo y lista de los no trabajados. **Progresión** de fuerza: peso máximo, 1RM estimado (Epley) y volumen.
- El agente dispone de `get_workout_log` para responder sobre tus sesiones, series y volumen por músculo.

## Medios de ejercicios

Las fichas ya soportan `ExerciseContent.video_url`, `media_type='video'` y `media_credit`; la pantalla de entrenamiento
reproduce el recurso con `st.video()`. No se incluyen vídeos de terceros en el repositorio sin comprobar derechos de
redistribución. El procedimiento para añadir recursos propios o con licencia está en
[`docs/MEDIA_EJERCICIOS.md`](docs/MEDIA_EJERCICIOS.md).

## Interfaz

**Modo claro/oscuro:** menú ⋮ (arriba a la derecha) → Settings → Theme. Por defecto sigue el modo de tu sistema, y el mapa muscular y
los gráficos se adaptan.

**Progreso:** resumen con medias frente a objetivo, calorías por día coloreadas (verde = en objetivo ±10 %, azul = por debajo, rojo =
por encima) con línea de objetivo, reparto de macros frente al objetivo, peso con media móvil y entrenamiento por semana.

Tema y componentes propios (`frontend/ui.py`, `.streamlit/config.toml`): anillo de calorías restantes y barras de macros, navegación
por días, comidas en tarjetas, fichas de producto con fotos e insignias, y adaptación a modo claro/oscuro. Los datos de terceros (nombres,
marcas, ingredientes) se escapan antes de pintarse como HTML. Requiere **Python 3.11 o superior**.

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

## Novedades (rama `feat/first_draft`)

**Entrenamiento** — plan estructurado (días → ejercicios reales del catálogo con series/reps/descanso, editable), «Ejercicios recomendados para hoy» al registrar,
fichas «Cómo se hace», fallo / no fallo en lugar de RPE, tarjeta «Última sesión» y recomendaciones deterministas tras entrenar (récord, progresión prudente, mantener).
**Nutrición** — recetas y alimentos compuestos (recálculo en vivo, instantánea al registrar), unidades por alimento (cucharada, rebanada…), catálogo SmartFit y
carga batch de USDA FoodData Central y otras bases en CSV (`python -m app.ingest`, sin APIs con cupo), alimentos propios por usuario, con procedencia/licencia ([docs/FUENTES_NUTRICIONALES.md](docs/FUENTES_NUTRICIONALES.md)).
**Hábitos** — agua, check-in emocional privado, pasos (manual + `/activity/sync` con consentimiento) y «Analiza mi progreso» (indicadores por código; la IA solo redacta).
**Cálculo energético** — edad, metabolismo basal y gasto total por código (`GET /profile/energy`).

Pendiente: app Android para Health Connect / Samsung Health, OAuth de Google Health API, BEDCA, vídeos/imágenes de ejercicios con licencia, Alembic.
