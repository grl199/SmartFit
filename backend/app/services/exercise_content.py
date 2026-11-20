"""Contenido didáctico propio de los ejercicios del catálogo (texto original de SmartFit).

No incluye imágenes ni vídeos: los recursos visuales deben ser propios o tener licencia que permita usarlos, así que el
modelo (`ExerciseContent.image_url/video_url/media_type/media_credit`) queda listo para rellenarlos cuando haya material
con derechos. Los ejercicios sin ficha específica reciben una guía genérica derivada de sus músculos y su equipamiento
(`generic_content`), claramente marcada como tal."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import enums
from ..models import Exercise, ExerciseContent

log = logging.getLogger(__name__)

# nombre exacto del catálogo -> (descripción, posición inicial, pasos, errores frecuentes)
CONTENT: dict[str, tuple[str, str, list[str], list[str]]] = {
    "Sentadilla con barra": (
        "Ejercicio base de pierna: trabaja sobre todo cuádriceps y glúteos, con apoyo de isquiotibiales y zona lumbar.",
        "Barra apoyada sobre la parte alta de la espalda, pies a la anchura de los hombros y puntas ligeramente abiertas.",
        ["Respira hondo y aprieta el abdomen antes de bajar.", "Baja llevando la cadera atrás y abajo, con las rodillas siguiendo la línea de los pies.",
         "Desciende hasta donde mantengas la espalda neutra (idealmente muslos paralelos al suelo).", "Empuja el suelo con todo el pie para subir y expulsa el aire arriba."],
        ["Dejar que las rodillas se vayan hacia dentro.", "Redondear la espalda al final de la bajada.", "Despegar los talones del suelo."]),
    "Prensa de piernas": (
        "Alternativa guiada a la sentadilla: cuádriceps y glúteos con menos exigencia de equilibrio.",
        "Espalda y cabeza bien apoyadas, pies a la anchura de los hombros en la plataforma.",
        ["Desbloquea el seguro y baja la plataforma de forma controlada.", "Baja hasta unos 90° de rodilla sin que la pelvis se despegue del respaldo.",
         "Empuja con todo el pie hasta casi extender las piernas.", "Vuelve a asegurar la máquina al terminar."],
        ["Bloquear las rodillas al subir.", "Levantar la cadera del asiento al bajar demasiado.", "Rebotar abajo."]),
    "Zancadas con mancuernas": (
        "Pierna unilateral: cuádriceps y glúteos, con exigencia de equilibrio y estabilidad de cadera.",
        "De pie con una mancuerna en cada mano a los lados del cuerpo, tronco erguido.",
        ["Da un paso largo hacia delante.", "Baja la rodilla de atrás hacia el suelo sin llegar a golpearlo.", "Empuja con el pie delantero para volver a la posición inicial.", "Alterna las piernas."],
        ["Paso demasiado corto (la rodilla pasa mucho de la punta del pie).", "Inclinar el tronco hacia delante.", "Perder el equilibrio por ir rápido."]),
    "Peso muerto convencional": (
        "Ejercicio global: isquiotibiales, glúteos y espalda, con trabajo de agarre.",
        "Barra sobre la mitad del pie, pies a la anchura de la cadera, agarre justo por fuera de las piernas.",
        ["Baja la cadera hasta agarrar la barra con la espalda recta y el pecho abierto.", "Tensa los dorsales («aprieta la barra al cuerpo») y empuja el suelo con las piernas.",
         "Cuando la barra pase las rodillas, extiende la cadera hasta quedar erguido.", "Baja controlando, empujando la cadera atrás."],
        ["Redondear la espalda.", "Tirar de la barra con los brazos antes de empujar con las piernas.", "Alejar la barra del cuerpo."]),
    "Peso muerto rumano": (
        "Bisagra de cadera: isquiotibiales y glúteos con la espalda baja como estabilizador.",
        "De pie con la barra a la altura de los muslos, rodillas ligeramente flexionadas.",
        ["Empuja la cadera hacia atrás manteniendo la barra pegada a las piernas.", "Baja hasta notar tensión en la parte trasera del muslo (suele ser por debajo de la rodilla).",
         "Aprieta los glúteos para volver arriba.", "Mantén la espalda neutra todo el recorrido."],
        ["Flexionar demasiado las rodillas (se convierte en sentadilla).", "Redondear la espalda.", "Hiperextender la zona lumbar arriba."]),
    "Hip thrust": (
        "El ejercicio más directo para glúteos.",
        "Espalda alta apoyada en un banco, barra sobre la cadera (con protección), pies apoyados y rodillas a unos 90° arriba.",
        ["Apoya los pies a la anchura de la cadera y mete la barbilla.", "Empuja el suelo y sube la cadera hasta alinear tronco y muslos.",
         "Aprieta los glúteos un segundo arriba.", "Baja controlando sin apoyar del todo."],
        ["Arquear la zona lumbar al subir.", "Pies demasiado cerca o lejos (la tensión pasa a isquios o cuádriceps).", "Subir con impulso."]),
    "Press banca con barra": (
        "Empuje horizontal: pectoral mayor, con ayuda de tríceps y deltoides anterior.",
        "Tumbado en el banco con los pies apoyados en el suelo, omóplatos juntos y agarre algo más ancho que los hombros.",
        ["Saca la barra del soporte con los brazos extendidos.", "Baja controladamente hasta rozar la parte media del pecho.", "Empuja hasta extender los brazos sin perder el control.",
         "Mantén los omóplatos juntos y los pies firmes todo el rato."],
        ["Rebotar la barra en el pecho.", "Despegar la cadera del banco.", "Abrir demasiado los codos (90° respecto al tronco)."]),
    "Press banca inclinado con mancuernas": (
        "Empuje inclinado: parte superior del pecho y hombro anterior.",
        "Banco a 30-45°, una mancuerna en cada mano a la altura del pecho.",
        ["Empuja las mancuernas hacia arriba acercándolas ligeramente.", "Extiende los brazos sin chocar las mancuernas.", "Baja despacio hasta sentir estiramiento en el pecho.", "Mantén las muñecas rectas."],
        ["Inclinar el banco demasiado (se convierte en press de hombros).", "Bajar sin control.", "Arquear en exceso la espalda."]),
    "Flexiones": (
        "Empuje con peso corporal: pecho, tríceps y hombros, con el abdomen estabilizando.",
        "Manos algo más anchas que los hombros, cuerpo en línea recta de cabeza a talones.",
        ["Aprieta abdomen y glúteos.", "Baja el pecho hacia el suelo con los codos a unos 45° del cuerpo.", "Empuja hasta extender los brazos.", "Si es muy difícil, apoya las rodillas o las manos en un banco."],
        ["Hundir o elevar la cadera.", "Abrir los codos en cruz.", "Hacer recorrido corto."]),
    "Press militar con barra": (
        "Empuje vertical: deltoides, tríceps y trapecio.",
        "De pie, barra a la altura de la clavícula, agarre algo más ancho que los hombros.",
        ["Aprieta glúteos y abdomen.", "Empuja la barra en línea recta, echando la cabeza ligeramente atrás para dejarle paso.", "Termina con la barra sobre la coronilla y los brazos extendidos.", "Baja hasta la clavícula con control."],
        ["Arquear la zona lumbar.", "Mover la barra hacia delante en vez de en vertical.", "Usar impulso de piernas sin querer."]),
    "Press de hombros con mancuernas": (
        "Empuje vertical con mayor libertad de movimiento: deltoides y tríceps.",
        "Sentado o de pie, mancuernas a la altura de las orejas con las palmas hacia delante.",
        ["Empuja las mancuernas hacia arriba hasta casi juntarlas.", "No bloquees los codos arriba.", "Baja hasta que los codos queden a unos 90°.", "Mantén el abdomen firme."],
        ["Arquear la espalda.", "Bajar demasiado sin control.", "Encoger los hombros hacia las orejas."]),
    "Elevaciones laterales": (
        "Aislamiento del deltoides lateral (anchura de hombros).",
        "De pie con una mancuerna ligera en cada mano, codos ligeramente flexionados.",
        ["Eleva los brazos hacia los lados hasta la altura de los hombros.", "Lidera el movimiento con los codos, no con las manos.", "Pausa breve arriba.", "Baja despacio."],
        ["Usar demasiado peso y balancear el cuerpo.", "Subir por encima de los hombros.", "Encoger el trapecio."]),
    "Extensión de tríceps en polea": (
        "Aislamiento del tríceps.",
        "De pie frente a la polea alta, codos pegados a las costillas, agarre con cuerda o barra.",
        ["Empuja hacia abajo extendiendo los codos.", "Aprieta el tríceps al final.", "Sube despacio hasta unos 90° de codo.", "Mantén los codos fijos."],
        ["Mover los codos hacia delante y atrás.", "Inclinar el tronco para empujar con el cuerpo.", "Soltar el peso en la subida."]),
    "Dominadas": (
        "Tirón vertical: dorsales y bíceps, con trabajo de agarre y core.",
        "Colgado de la barra con las palmas al frente (agarre algo más ancho que los hombros), brazos extendidos.",
        ["Baja los omóplatos y tira de los codos hacia las costillas.", "Sube hasta que la barbilla supere la barra.", "Baja despacio hasta extender los brazos.", "Si aún no puedes, usa banda de ayuda o máquina asistida."],
        ["Balancearse (kipping) sin querer.", "No extender del todo abajo.", "Tirar solo con los brazos y los hombros subidos."]),
    "Jalón al pecho": (
        "Alternativa guiada a las dominadas: dorsales y bíceps.",
        "Sentado con los muslos fijados bajo el soporte, agarre algo más ancho que los hombros.",
        ["Inclina el tronco ligeramente atrás y saca el pecho.", "Tira de la barra hacia la parte alta del pecho llevando los codos abajo.", "Aprieta los dorsales un segundo.", "Sube la barra con control."],
        ["Tirar de la barra por detrás de la nuca.", "Balancear el tronco.", "Encoger los hombros."]),
    "Remo con barra": (
        "Tirón horizontal: espalda media y dorsales, con bíceps de apoyo.",
        "Tronco inclinado unos 45° con la espalda recta, rodillas flexionadas, barra colgando.",
        ["Tira de la barra hacia el abdomen llevando los codos atrás.", "Junta los omóplatos al final.", "Baja controlando sin redondear la espalda.", "Mantén el torso quieto."],
        ["Usar impulso con el tronco.", "Redondear la espalda.", "Tirar hacia el pecho en vez de al abdomen."]),
    "Remo en polea baja": (
        "Tirón horizontal guiado: espalda media y dorsales.",
        "Sentado con los pies en la plataforma, rodillas ligeramente flexionadas y espalda recta.",
        ["Tira del agarre hacia el abdomen.", "Junta los omóplatos sin encoger los hombros.", "Vuelve despacio estirando los brazos.", "No te balancees."],
        ["Inclinarse mucho hacia delante al volver.", "Tirar con los brazos sin mover los omóplatos.", "Balancear el tronco."]),
    "Remo con mancuerna": (
        "Tirón unilateral: dorsales y espalda media.",
        "Una rodilla y una mano apoyadas en un banco, espalda paralela al suelo, mancuerna colgando.",
        ["Tira de la mancuerna hacia la cadera.", "Lleva el codo hacia atrás y arriba.", "Baja despacio hasta estirar el brazo.", "Repite y cambia de lado."],
        ["Girar el tronco para ayudarse.", "Subir la mancuerna hacia el hombro.", "Usar demasiado peso."]),
    "Curl de bíceps con barra": (
        "Aislamiento del bíceps.",
        "De pie, barra con agarre supino a la anchura de los hombros, codos pegados al cuerpo.",
        ["Flexiona los codos subiendo la barra hacia los hombros.", "Aprieta el bíceps arriba.", "Baja despacio hasta casi extender.", "No muevas los codos."],
        ["Balancear el cuerpo.", "Adelantar los codos.", "Bajar de golpe."]),
    "Curl martillo": (
        "Bíceps (braquial) y antebrazo.",
        "De pie con mancuernas, palmas enfrentadas (agarre neutro).",
        ["Sube una mancuerna manteniendo el agarre neutro.", "Mantén el codo pegado al costado.", "Baja con control.", "Alterna o sube las dos a la vez."],
        ["Balancear el tronco.", "Girar la muñeca durante el recorrido.", "Peso excesivo."]),
    "Plancha": (
        "Isométrico de core: abdominales y estabilizadores del tronco.",
        "Apoyado en antebrazos y puntas de los pies, codos bajo los hombros.",
        ["Aprieta abdomen y glúteos.", "Mantén cuerpo recto de cabeza a talones.", "Respira con normalidad.", "Mantén el tiempo marcado."],
        ["Hundir la zona lumbar.", "Elevar la cadera.", "Contener la respiración."]),
    "Crunch abdominal": (
        "Flexión de tronco: abdominales.",
        "Tumbado boca arriba, rodillas dobladas y pies apoyados, manos cruzadas sobre el pecho o junto a las sienes.",
        ["Expulsa el aire y eleva los hombros del suelo curvando el tronco.", "Pausa breve arriba.", "Baja controlando sin relajar del todo.", "No tires del cuello con las manos."],
        ["Tirar del cuello.", "Subir demasiado el tronco (trabaja el psoas).", "Ir muy rápido."]),
    "Sentadilla con peso corporal": (
        "Patrón de sentadilla sin carga: ideal para aprender la técnica.",
        "Pies a la anchura de los hombros, brazos al frente para equilibrarte.",
        ["Lleva la cadera atrás y abajo.", "Baja manteniendo el pecho abierto y las rodillas alineadas con los pies.", "Sube empujando el suelo.", "Mantén los talones apoyados."],
        ["Rodillas hacia dentro.", "Redondear la espalda.", "Levantar los talones."]),
    "Fondos en paralelas": (
        "Empuje con peso corporal: pecho inferior, tríceps y hombros.",
        "Sostenido sobre las paralelas con los brazos extendidos y el cuerpo ligeramente inclinado.",
        ["Baja flexionando los codos hasta unos 90°.", "Mantén el pecho abierto y los hombros bajos.", "Empuja hasta extender los brazos.", "Evita balancearte."],
        ["Bajar demasiado (castiga el hombro).", "Encoger los hombros.", "Balancear las piernas."]),
    "Face pull": (
        "Deltoides posterior y estabilizadores del hombro: salud de hombro y postura.",
        "Polea a la altura de la cara con cuerda, brazos extendidos al frente.",
        ["Tira de la cuerda hacia la cara separando los extremos.", "Lleva los codos altos y atrás.", "Aprieta la parte posterior del hombro.", "Vuelve con control."],
        ["Usar demasiado peso y tirar con la espalda baja.", "Codos caídos.", "Mover el tronco."]),
    "Elevación de gemelos de pie": (
        "Pantorrillas (gemelos).",
        "De pie con la punta del pie sobre un escalón o plataforma, talones al aire.",
        ["Sube de puntillas lo máximo posible.", "Pausa un segundo arriba.", "Baja estirando el gemelo.", "Mantén las rodillas casi extendidas."],
        ["Rebotar.", "Recorrido corto.", "Doblar las rodillas."]),
    "Extensión de piernas (cuádriceps)": (
        "Aislamiento del cuádriceps.",
        "Sentado en la máquina con la espalda apoyada y el rodillo sobre los tobillos.",
        ["Extiende las rodillas hasta casi bloquearlas.", "Aprieta el cuádriceps arriba.", "Baja despacio.", "Ajusta el respaldo para que la rodilla quede alineada con el eje."],
        ["Balancear el cuerpo.", "Bloquear de golpe la rodilla.", "Peso excesivo."]),
    "Curl femoral tumbado": (
        "Aislamiento de isquiotibiales.",
        "Tumbado boca abajo en la máquina con el rodillo sobre los tobillos.",
        ["Flexiona las rodillas llevando los talones hacia los glúteos.", "Mantén la cadera pegada al banco.", "Baja despacio.", "Evita arquear la espalda."],
        ["Levantar la cadera.", "Tirones.", "Bajar sin control."]),
    "Swing con pesa rusa": (
        "Ejercicio explosivo de cadera: glúteos, isquiotibiales y core.",
        "Pies algo más anchos que los hombros, pesa delante de ti, espalda recta.",
        ["Lanza la cadera atrás («bisagra») y balancea la pesa entre las piernas.", "Extiende la cadera con fuerza: la pesa sube por inercia hasta el pecho.", "Deja que caiga y vuelve a la bisagra.", "Los brazos solo guían."],
        ["Hacer una sentadilla en vez de una bisagra.", "Levantar la pesa con los brazos.", "Redondear la espalda."]),
    "Burpees": (
        "Ejercicio de cuerpo entero de alta intensidad.",
        "De pie, pies a la anchura de los hombros.",
        ["Agáchate y apoya las manos en el suelo.", "Lanza los pies atrás hasta la posición de plancha.", "Opcional: haz una flexión.", "Recoge los pies y salta con los brazos arriba."],
        ["Hundir la zona lumbar en la plancha.", "Ir tan rápido que se pierde la técnica.", "Aterrizar con las piernas rígidas."]),
}

GENERIC_TIPS = [
    "Calienta antes con una o dos series ligeras del movimiento.",
    "Controla la bajada (2-3 segundos) y evita rebotes.",
    "Respira: exhala en el esfuerzo e inhala en la fase de retorno.",
    "Usa un peso con el que puedas mantener la técnica en todas las repeticiones.",
    "Si sientes dolor articular (no muscular), para y consulta con un profesional.",
]


def generic_content(ex: Exercise) -> dict:
    """Guía genérica (sin ficha específica) a partir de los músculos y el equipamiento del ejercicio."""
    primary = enums.MUSCLE_GROUP.get(ex.primary_muscle, ex.primary_muscle)
    secondary = [enums.MUSCLE_GROUP.get(m, m) for m in ex.secondary_muscles or []]
    equip = [enums.EQUIPMENT.get(e, e) for e in ex.equipment or []]
    return {"description": f"Trabaja principalmente {primary.lower()}" + (f" y, como apoyo, {', '.join(m.lower() for m in secondary)}." if secondary else "."),
            "start_position": None, "instructions": [], "common_mistakes": GENERIC_TIPS, "image_url": None, "video_url": None,
            "media_type": None, "media_credit": None, "has_detailed_guide": False, "equipment": equip}


def content_for(db: Session, ex: Exercise) -> dict:
    row = db.get(ExerciseContent, ex.id)
    base = {"exercise_id": ex.id, "name": ex.name, "primary_muscle": ex.primary_muscle,
            "secondary_muscles": list(ex.secondary_muscles or []), "equipment": [enums.EQUIPMENT.get(e, e) for e in ex.equipment or []]}
    if row is None:
        return {**base, **generic_content(ex)}
    return {**base, "description": row.description, "start_position": row.start_position, "instructions": list(row.instructions or []),
            "common_mistakes": list(row.common_mistakes or []), "image_url": row.image_url, "video_url": row.video_url,
            "media_type": row.media_type, "media_credit": row.media_credit, "has_detailed_guide": True}


def seed_content(db: Session) -> int:
    """Crea/actualiza las fichas del catálogo compartido (idempotente). Devuelve cuántas escribió."""
    shared = {e.name: e.id for e in db.scalars(select(Exercise).where(Exercise.user_id.is_(None)))}
    existing = {c.exercise_id: c for c in db.scalars(select(ExerciseContent))}
    n = 0
    for name, (desc, start, steps, mistakes) in CONTENT.items():
        ex_id = shared.get(name)
        if ex_id is None:
            log.warning("Contenido para un ejercicio que no está en el catálogo: %s", name)
            continue
        row = existing.get(ex_id) or ExerciseContent(exercise_id=ex_id)
        new = (desc, start, steps, mistakes)
        if (row.description, row.start_position, row.instructions, row.common_mistakes) != new:
            row.description, row.start_position, row.instructions, row.common_mistakes = desc, start, steps, mistakes
            db.add(row)
            n += 1
    db.commit()
    return n
