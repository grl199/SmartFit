# Registro GPS de carreras y paseos (web)
## Persistencia y recuperación
- Los puntos se guardan localmente cada ~5 s y se envían al backend cada ~15 s por lotes.
- Cada borrador tiene un ID generado en el cliente; reenviar puntos con la misma marca temporal no duplica datos.
- Al volver a abrir SmartFit se ofrece reanudar, guardar tal cual o descartar el último recorrido interrumpido.
- Los borradores del servidor sin actividad durante 7 días dejan de ofrecerse y se eliminan al recibir un nuevo borrador.
## Calidad y huecos
- Entre puntos separados por más de 120 s hay un hueco: no se suma la distancia ni el desnivel de ese salto y el tiempo se descuenta de la duración activa.
- Se descartan lecturas con precisión superior a 50 m y velocidades implícitas superiores a 12 m/s.
- Las reglas se comparten entre `apps/web/src/lib/route.ts` y `backend/app/services/route.py`.
## Limitaciones
Screen Wake Lock evita el apagado automático cuando el navegador lo permite; no mantiene GPS al bloquear manualmente el móvil o suspender la pestaña. Para segundo plano fiable hace falta una app nativa (servicios de ubicación de Android/iOS).
