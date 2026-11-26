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
- Entrenamiento: consulta de plan y sesiones, registro de sesión rápida.
- Progreso: historial y registro de peso.
- Perfil y cierre de sesión.

## Comprobaciones

~~~bash
pnpm --filter @smartfit/mobile typecheck
pnpm --filter @smartfit/mobile test
pnpm --filter @smartfit/mobile export
~~~

Las pruebas de CI y el typecheck no sustituyen una prueba en dispositivo real. Las operaciones requieren que el backend esté desplegado y que las variables estén configuradas.