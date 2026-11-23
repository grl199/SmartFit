# SmartFit Mobile (Expo)

Aplicación nativa iOS/Android con Expo SDK 58, React Native y TypeScript.
Comparte los contratos OpenAPI y el cliente HTTP con Next.js.

## Requisitos

- Node.js `^22.13.0 || ^24.3.0 || >=26.0.0`.
- pnpm 10.12.1.
- Expo Go compatible con SDK 58 o una development build.

## Instalación

Desde la raíz del monorepo:

```bash
corepack enable
corepack prepare pnpm@10.12.1 --activate
pnpm install --no-frozen-lockfile
pnpm contracts:generate
cp apps/mobile/.env.example apps/mobile/.env
```

Configura `EXPO_PUBLIC_API_URL` en función del dispositivo:

- iOS Simulator: `http://localhost:8000`.
- Android Emulator: `http://10.0.2.2:8000`.
- Dispositivo físico: IP local del ordenador que ejecuta FastAPI.
- Producción: URL HTTPS del backend.

Para usar **Expo Web** en desarrollo, FastAPI permite por defecto los orígenes
locales `:3000` (Next.js), `:8081` (Expo actual) y `:19006` (Expo clásico).
Si abres Expo Web desde otro equipo y aparece un error CORS, añade el origen
exacto del navegador a `CORS_ORIGINS` en `backend/.env` (lista JSON) y
reinicia FastAPI. Esto solo afecta al target web; React Native nativo no aplica
CORS del navegador.

FastAPI debe escuchar en una interfaz de red accesible desde el teléfono y el
firewall debe permitir el puerto en desarrollo con dispositivo físico.

## Ejecutar

```bash
pnpm --filter @smartfit/mobile start
```

Para forzar un target:

```bash
pnpm --filter @smartfit/mobile android
pnpm --filter @smartfit/mobile ios
pnpm --filter @smartfit/mobile web
```

La vista web de Expo usa `react-native-web`, `react-dom` y
`@expo/metro-runtime`. Estas dependencias son específicas del target web y no
sustituyen el runtime nativo de React Native.

## Sesiones

Los tokens de acceso y renovación se guardan mediante `expo-secure-store`.
No se usan cookies del navegador ni `localStorage`. La API móvil usa los
endpoints `/auth/session/*` de FastAPI y envía el token de acceso como Bearer.

## Validación

```bash
pnpm --filter @smartfit/mobile typecheck
pnpm --filter @smartfit/mobile export:web
```

Si Metro conserva un error de resolución después de instalar dependencias,
detén el servidor y reinicia limpiando la caché:

```bash
pnpm --filter @smartfit/mobile start -- --clear
```
