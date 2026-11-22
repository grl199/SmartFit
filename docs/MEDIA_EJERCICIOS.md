# Medios demostrativos de ejercicios

SmartFit ya reproduce vídeos mediante `ExerciseContent.video_url` y `st.video()`. Este documento define cómo completar
el catálogo sin introducir recursos con procedencia o licencia desconocidas.

## Requisitos del recurso

- Preferir MP4/H.264 o WebM; usar una URL HTTPS accesible desde el navegador del usuario.
- Vídeos cortos, encuadre estable, cuerpo y aparato completos, una repetición lenta y otra a ritmo normal.
- Identificar el ejercicio, variante, equipamiento y ángulo de cámara.
- Añadir autoría y licencia explícita en `media_credit`. Guardar copia de la licencia y la fecha de adquisición fuera del binario.
- No utilizar vídeos descargados de redes sociales o repositorios de código como prueba de permiso de redistribución.

## Dónde alojarlos

Usar almacenamiento de objetos (por ejemplo, un bucket privado con CDN o un bucket público de solo lectura) y servir los
vídeos desde HTTPS. No subir MP4/GIF grandes al historial Git: aumentan el tamaño de cada clon y no son adecuados para
el versionado de código.

## Asociar un vídeo con un ejercicio

Sube primero el archivo al almacenamiento y conserva la URL final y la licencia. Luego localiza el ID del ejercicio:

```sql
SELECT id, name
FROM exercises
WHERE user_id IS NULL
  AND name IN ('Dominadas', 'Prensa de piernas', 'Press de pecho en máquina');
```

Crea o actualiza su ficha. Ejemplo para un único recurso autorizado:

```sql
INSERT INTO exercise_contents (exercise_id, video_url, media_type, media_credit)
VALUES (
  123,
  'https://media.example.com/smartfit/dominadas.mp4',
  'video',
  'Vídeo propio SmartFit, licencia interna, versión 1'
)
ON CONFLICT (exercise_id) DO UPDATE
SET video_url = EXCLUDED.video_url,
    media_type = EXCLUDED.media_type,
    media_credit = EXCLUDED.media_credit;
```

Sustituye el ID, URL, titular y licencia por datos reales. No reutilices el ejemplo ficticio. La interfaz consulta
`GET /exercises/{id}/content` y muestra el vídeo automáticamente cuando `media_type='video'` y existe `video_url`.

## Animaciones 3D generadas

Para demostraciones simuladas, una vía reproducible es crear un rig humano en Blender y animaciones revisadas por un
profesional del entrenamiento. Claude Code puede ayudar a escribir scripts de Blender y automatizar exportaciones,
pero no certifica la biomecánica. Cada animación debe pasar una revisión técnica antes de publicarse, especialmente en
movimientos cargados como sentadilla, peso muerto y prensa.
