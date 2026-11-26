# Prompts de SmartFit: catálogo de alimentos y vídeos de ejercicios

Estos prompts están pensados para usarse con un LLM de investigación/brainstorming y con un generador de vídeo. No deben ejecutarse como si sus propuestas fueran automáticamente datos validados.

---

## 1. Brainstorming para ampliar el catálogo de alimentos

Copia el prompt completo. Adjunta, cuando sea posible, el catálogo actual de `FOODS` y `RECIPES` de `backend/app/services/food_catalog.py` para que el modelo detecte duplicados.

```text
Actúa como un equipo formado por:
- un dietista-nutricionista familiarizado con hábitos alimentarios de España;
- un especialista en composición de alimentos y bases de datos nutricionales;
- un product manager de una aplicación de seguimiento de calorías y macronutrientes.

CONTEXTO
Estoy ampliando SmartFit, una app de registro de alimentación. El usuario debe poder encontrar tanto alimentos simples como comidas cotidianas ya preparadas. El catálogo actual es insuficiente. Ejemplos representativos:
- café con leche entera;
- tostada con hummus;
- tostada con tomate y aceite;
- café cortado;
- yogur con avena y fruta;
- ensalada mixta con atún.

El objetivo no es crear una base de datos de productos comerciales con marca. Es crear un catálogo útil de alimentos genéricos, preparaciones y combinaciones domésticas habituales, especialmente en España.

MISIÓN
Haz un brainstorming amplio, práctico y priorizado de nuevas entradas. Busca variedad real de hábitos, no 100 variaciones cosméticas del mismo plato.

Incluye, como mínimo, estas familias:
1. Cafés, infusiones y bebidas habituales: café solo, cortado, café con leche entera/semidesnatada, cacao con leche, etc.
2. Desayunos y tostadas: tomate y aceite, hummus, aguacate, queso fresco, pavo, jamón, crema de cacahuete, mantequilla y mermelada.
3. Bocadillos, sándwiches y wraps: tortilla, atún, pollo, pavo, queso, vegetal, mixto, etc.
4. Huevos: cocidos, tortilla, revueltos, con verduras, con patata.
5. Platos de cuchara y legumbres: lentejas, garbanzos, alubias, cocidos y purés.
6. Ensaladas y platos fríos: mixta, atún, pasta, arroz, quinoa, legumbres, caprese, etc.
7. Arroz, pasta, patatas y otros acompañamientos, distinguiendo peso cocido de peso en seco.
8. Carnes y pescados cocinados de formas habituales: plancha, horno, guiso, empanado, conservas escurridas.
9. Lácteos y postres: yogures naturales/griegos, queso fresco, requesón, arroz con leche, flan, natillas, etc.
10. Fruta, frutos secos y snacks.
11. Salsas, aliños y extras que cambian mucho las calorías: aceite, mayonesa, tomate frito, pesto, kétchup, alioli, mantequilla, miel, azúcar.
12. Comida preparada común en España: tortilla de patata, gazpacho, salmorejo, paella, croquetas, empanadillas, pizza, etc.

REGLAS DE CALIDAD
- Prioriza entradas que una persona realmente buscaría al registrar su día.
- Distingue alimento simple, receta compuesta y producto comercial. No crees una receta si el alimento ya representa la misma preparación.
- No dupliques ni renombres entradas existentes: compara nombres, ingredientes y equivalencia semántica con el catálogo adjunto.
- En platos compuestos, proporciona una lista de ingredientes y cantidades plausibles en gramos para UNA ración estándar. Incluye aceite, salsas y aliños explícitamente; no los ocultes dentro de una descripción.
- Distingue siempre crudo/cocido, escurrido/no escurrido, con piel/sin piel y seco/hidratado cuando cambie el valor nutricional.
- Sugiere equivalencias de unidades de uso cotidiano (taza, vaso, cucharada, rebanada, loncha, unidad, puñado) solo cuando tengan sentido. Añade gramos orientativos por unidad.
- Da prioridad a las preparaciones más reconocibles en España, pero incluye alternativas mediterráneas e internacionales frecuentes.
- No inventes precisión nutricional. No rellenes valores de nutrientes si no se pueden respaldar.
- Para cada ingrediente simple, indica la fuente de composición que habría que consultar (USDA FoodData Central, CIQUAL, BEDCA u otra fuente abierta) y la descripción exacta de búsqueda. No atribuyas a una fuente valores que no has consultado.
- Señala alérgenos relevantes como información auxiliar, no como sustituto de revisar ingredientes.

PRIORIZACIÓN
Puntúa cada propuesta de 1 a 5 en:
- frecuencia probable de consumo;
- utilidad para el usuario;
- facilidad de obtener datos nutricionales fiables;
- diferencia respecto al catálogo existente.
Calcula una prioridad total ponderada: frecuencia 35%, utilidad 30%, fiabilidad 25%, novedad 10%.

ENTREGABLES
A. Resumen ejecutivo: qué huecos tiene el catálogo y qué familias faltan.
B. Lista priorizada de 150-250 candidatos, agrupados por categoría.
C. Para cada candidato, una fila con:
   - nombre español canónico;
   - aliases/sinónimos de búsqueda;
   - tipo: simple_food o recipe;
   - categoría;
   - descripción corta;
   - ración estándar en gramos;
   - ingredientes y gramos por ración (solo para recetas);
   - unidades y equivalencias en gramos;
   - estado de datos: fuente identificada / pendiente de verificar;
   - motivo de inclusión;
   - puntuación de prioridad.
D. Top 50 que implementarías primero, explicando por qué.
E. Lista de duplicados o candidatos que NO añadirías, explicando la equivalencia con elementos ya existentes.
F. Propuesta de plan de trabajo por lotes de 25 entradas para que una persona pueda revisar los datos antes de incorporarlos.

FORMATO
Entrega primero una tabla legible y después un JSON válido en un bloque separado. El JSON debe contener objetos con esta estructura:
{
  "name": "Tostada integral con hummus",
  "aliases": ["tostada de hummus", "pan con hummus"],
  "type": "recipe",
  "category": "desayuno",
  "description": "Tostada de pan integral con hummus.",
  "serving_g": 90,
  "ingredients": [
    {"food_name": "Pan integral", "grams": 60},
    {"food_name": "Hummus", "grams": 30}
  ],
  "servings": [
    {"unit_name": "tostada", "unit_name_plural": "tostadas", "grams_per_unit": 90}
  ],
  "data_status": "pending_verification",
  "priority_score": 4.6
}

No generes código todavía. No conviertas estimaciones de IA en verdad nutricional. El objetivo es producir un backlog excelente, diverso, sin duplicados y fácil de validar.
```

### Cómo aprovechar el resultado

1. Adjunta al modelo el catálogo existente para evitar duplicados.
2. Pídele el resultado en lotes de 25-30 entradas.
3. Revisa nombres, cantidades, aceite y pesos cocidos/crudos.
4. Contrasta los ingredientes simples con una base de composición abierta.
5. Incorpora recetas mediante el sembrado idempotente existente y prueba que no se creen duplicados.

---

## 2. Prompt para generar vídeos animados de ejercicios

Usa una generación por ejercicio. Sustituye los campos entre corchetes por la ficha técnica real de SmartFit. Es preferible generar una animación 3D de estilo instructivo y no un clip cinematográfico: la prioridad es que la biomecánica sea correcta.

```text
Create a high-quality 3D animated fitness exercise demonstration for a workout instruction app.

EXERCISE
- Exercise name: [EXERCISE NAME]
- Variation: [EXACT VARIATION]
- Equipment: [EQUIPMENT]
- Main muscles: [PRIMARY MUSCLES]
- Starting position: [START POSITION]
- Movement phases: [ECCENTRIC / CONCENTRIC / HOLD / RETURN]
- Range of motion: [SAFE, TECHNICALLY CORRECT RANGE]
- Breathing cue: [BREATHING CUE]
- Common errors to avoid: [COMMON ERRORS]

SUBJECT AND STYLE
Show one anatomically plausible adult human fitness instructor with a neutral, non-celebrity appearance. Use a clean, premium 3D instructional animation style: realistic body proportions, natural joint articulation, clear muscle and equipment geometry, neutral gym environment, soft studio lighting. Clothing must be fitted athletic wear that does not hide the movement. Keep the same character, clothing, equipment and environment throughout the clip.

CAMERA AND COMPOSITION
Use a fixed three-quarter side view that clearly shows the full body, contact points and the entire machine or bar path. Keep every relevant joint and piece of equipment visible at all times. Do not cut away, zoom, orbit or change camera angle during the repetition. Leave a little visual margin around the subject.

MOTION
Animate exactly one complete, controlled repetition:
1. Hold the correct start position briefly.
2. Perform the eccentric phase slowly and smoothly.
3. Reach the correct end position without forcing the joints.
4. Perform the concentric phase at a controlled, natural speed.
5. Return precisely to the original start position.
The motion must be continuous and physically plausible. Preserve balance, grip, foot placement, joint alignment, contact with the equipment and realistic resistance. The equipment must move only along its mechanically valid path. No sudden acceleration, teleporting, body deformation, sliding feet, changing grip or floating weights.

TECHNICAL ACCURACY
Follow the supplied exercise description exactly. Do not invent an alternative technique. Keep the spine, shoulders, hips, knees, elbows and wrists in plausible alignment. Show a controlled range of motion and avoid exaggerated movement. The animation is educational, not a medical diagnosis. If the supplied technique is ambiguous, flag it instead of improvising.

OUTPUT
- Duration: 7-9 seconds.
- Aspect ratio: 16:9.
- Resolution: 1080p or highest available.
- Frame rate: 24 or 30 fps.
- Silent video, no narration, no music, no sound effects.
- No titles, captions, text, labels, watermarks, logos or UI.
- One exercise and one repetition only.
- End in the exact same pose as the beginning so the clip can loop cleanly.
- Stable character identity and consistent geometry across all frames.

NEGATIVE CONSTRAINTS
No extra limbs or fingers, no warped anatomy, no changing body proportions, no morphing equipment, no incorrect contact points, no impossible joint angles, no clipping through benches or machines, no camera shake, no scene transitions, no slow-motion time jumps, no additional people, no distracting background activity.

Before generating, internally check that the movement phases and equipment path are consistent with the exercise. If any essential technical detail is missing, ask for it rather than guessing.
```

### Ejemplo de campos para dominadas

```text
EXERCISE NAME: Strict overhand pull-up
VARIATION: Pronated grip, shoulder-width
EQUIPMENT: Fixed pull-up bar
PRIMARY MUSCLES: Latissimus dorsi, biceps, upper back
START POSITION: Dead hang, hands slightly wider than shoulders, elbows extended, scapula controlled, legs together and still
ECCENTRIC: Lower the body slowly from chin-over-bar to a controlled dead hang
CONCENTRIC: Pull the elbows down and back until the chin clears the bar
RANGE OF MOTION: Full controlled hang to chin clearly above bar, without kipping or excessive lumbar arch
BREATHING: Exhale while pulling up, inhale while lowering
COMMON ERRORS: Kipping, swinging legs, shrugging excessively, craning the neck, partial repetitions
CAMERA: Fixed three-quarter side view, bar and full body visible
```

### Ejemplo de campos para press de pecho en máquina

```text
EXERCISE NAME: Seated machine chest press
VARIATION: Neutral or standard grip, machine handles aligned around mid-chest
EQUIPMENT: Seated chest press machine
PRIMARY MUSCLES: Pectoralis major, triceps, anterior deltoids
START POSITION: Back and head supported, feet flat, wrists neutral, handles at mid-chest, elbows slightly behind torso but within a comfortable range
ECCENTRIC: Return the handles slowly until the elbows reach a comfortable depth
CONCENTRIC: Press the handles forward without snapping the elbows into lockout
RANGE OF MOTION: Controlled range, shoulder blades supported and no painful shoulder extension
BREATHING: Exhale while pressing, inhale while returning
COMMON ERRORS: Arching the lower back, shoulders rolling forward, elbows flaring excessively, bouncing at the end range, locking elbows aggressively
CAMERA: Fixed three-quarter side view showing seat, back support, handles and full machine path
```

### Recomendación de producción

- Genera primero tres ejercicios piloto: dominadas, press de pecho en máquina y prensa de piernas.
- Revisa la técnica con alguien que conozca entrenamiento de fuerza antes de generar los 100+ restantes.
- Mantén una convención fija de nombres: `exercise-slug-v1.mp4`.
- Exporta MP4/H.264, sin audio, y aloja los archivos en un bucket/CDN. Guarda en SmartFit la URL y la atribución/licencia.
- No uses una animación genérica para representar máquinas distintas: la trayectoria, los apoyos y el recorrido deben corresponder al equipo concreto.
