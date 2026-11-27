# SmartFit Mobile

Aplicación para iOS y Android construida con Expo SDK 58, Expo Router y React Native. Forma parte del workspace apps/* y reutiliza el paquete @smartfit/api-client.

## Requisitos

- Node.js 22.13 o superior.
- pnpm 10.12.1.
- Backend SmartFit levantado y accesible desde el dispositivo.
- Expo Go compatible con SDK 58 o un development build.

## Arranque

Desde la raíz del repositorio:

~~~bash
pnpm install
cp apps/mobile/.env.example apps/mobile/.env
# En un móvil físico sustituye localhost por la IP LAN del ordenador.
pnpm dev:mobile
~~~

Pulsa a para Android, i para iOS (macOS/Xcode) o escanea el QR con Expo Go. Para la versión web de desarrollo ejecuta pnpm --filter @smartfit/mobile web.

URL del backend según el entorno:
- Emulador Android: normalmente http://10.0.2.2:8000.
- Simulador iOS: http://localhost:8000.
- Móvil físico: http://IP_LAN_DEL_ORDENADOR:8000.

## Funcionalidad

- Registro e inicio de sesión con renovación de sesión mediante refresh token.
- Almacenamiento de access/refresh tokens en Expo SecureStore.
- Onboarding conectado a /onboarding con los campos requeridos por FastAPI.
- Dashboard diario, macros y objetivo de hidratación.
- Nutrición: búsqueda de catálogo y registro de ingestas.
- Hidratación: registro rápido de agua.
- Entrenamiento: consulta de plan y sesiones, registro de sesión rápida y seguimiento GPS de paseos/carreras con recuperación de lecturas y guardado local.
- Progreso: historial y registro de peso.
- Perfil y cierre de sesión.

## Seguimiento GPS

- En Android/iOS, la app combina el observador en primer plano con una tarea de ubicación nativa registrada mediante Expo TaskManager. Los puntos se escriben primero en AsyncStorage y se sincronizan por lotes con `/activity-drafts`.
- Android mantiene un servicio de ubicación en primer plano con una notificación persistente. iOS solicita permiso de ubicación «Siempre» para mantener la ruta al cambiar de app o bloquear la pantalla.
- El usuario debe conceder los permisos de ubicación en primer plano y segundo plano. En Android 11 o posterior, el sistema puede abrir Ajustes para que se seleccione «Permitir siempre».
- La ubicación en segundo plano requiere una build nativa actualizada (EAS/Cloud Build); Expo Go no sirve para validar el servicio persistente de Android.
- En web se usa la Geolocation API del navegador, con reintentos del observador y persistencia local tras cada punto. Los navegadores pueden suspender la geolocalización cuando la pestaña pasa a segundo plano, se bloquea el dispositivo o se cierra la página; para recorridos con pantalla bloqueada se debe usar la app móvil.
- La ubicación en segundo plano no sobrevive a una detención forzada de la aplicación. El comportamiento al retirar SmartFit de aplicaciones recientes puede variar según el fabricante de Android.

Para validar una build nativa: inicia un recorrido, espera a que aparezcan varios puntos, cambia a otra aplicación durante un par de minutos, vuelve a SmartFit y comprueba que el contador de puntos ha seguido aumentando y que la ruta aparece sincronizada. Repite también con la pantalla bloqueada. No debe utilizarse una detención forzada como prueba de continuidad.

## Comprobaciones

~~~bash
pnpm --filter @smartfit/mobile typecheck
pnpm --filter @smartfit/mobile test
pnpm --filter @smartfit/mobile export
~~~

Las pruebas de CI y el typecheck no sustituyen una prueba en dispositivo real. Las operaciones requieren que el backend esté desplegado y que las variables estén configuradas.