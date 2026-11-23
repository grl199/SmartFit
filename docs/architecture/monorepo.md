# Monorepo multiplataforma: fase inicial

Esta fase prepara el repositorio para incorporar web y móvil sin sustituir el
backend ni interrumpir Streamlit.

## Límites de responsabilidad

- `backend/` sigue siendo la fuente de verdad de autenticación, reglas de
  negocio, persistencia, nutrición, entrenamiento, hábitos e IA.
- `frontend/` conserva la aplicación Streamlit actual durante la transición.
- `packages/contracts/` contiene únicamente el contrato OpenAPI y los tipos
  TypeScript generados. No contiene lógica de negocio ni modelos duplicados.
- `packages/api-client/` contiene el cliente HTTP compartido por las
  aplicaciones TypeScript. La URL base se configura por consumidor: la web usa
  el proxy del mismo origen (`/api`) y una aplicación nativa podrá usar la URL
  HTTPS pública del backend.
- `apps/web/` contiene la interfaz Next.js; las futuras aplicaciones nativas
  se incorporarán en `apps/mobile/` con Expo.
- Otros paquetes compartidos (por ejemplo, design tokens y validación) se
  extraerán cuando haya consumidores reales en más de una plataforma.

## Requisitos

- Python 3.11 o superior (CI utiliza Python 3.12).
- Node.js 22.13.0 o superior (requisito de Expo SDK 58).
- pnpm 10.12.1, fijado mediante `packageManager` en el `package.json` raíz.

## Instalación y generación

Después de clonar o cambiar de rama, ejecuta desde la raíz del repositorio:

```bash
corepack enable
corepack prepare pnpm@10.12.1 --activate
pnpm install
pnpm contracts:generate
pnpm typecheck
pnpm --filter @smartfit/mobile start
```

**Importante:** vuelve a ejecutar `pnpm install` después de incorporar un
paquete nuevo en `packages/*` o una dependencia `workspace:*`. pnpm debe
crear el enlace `apps/web/node_modules/@smartfit/api-client`; arrancar Next.js
sin actualizar la instalación local puede producir `Module not found`.
No ejecutes la instalación desde `apps/web`: el workspace se instala desde la
raíz.

El comando `pnpm contracts:generate`:
1. Importa `backend/app/main.py` y obtiene el esquema con `app.openapi()`.
2. Escribe `packages/contracts/openapi.json`.
3. Ejecuta `openapi-typescript` para producir
   `packages/contracts/src/generated.ts`.

No necesita levantar Uvicorn, conectarse a Neon/PostgreSQL ni configurar claves
de Gemini. Los routers y esquemas Pydantic registrados en FastAPI son la única
fuente de verdad. El JSON y el TypeScript son artefactos generados: no se deben
editar manualmente y, cuando se actualicen, deben revisarse y mantenerse
sincronizados.

Para ejecutar los tests puros del backend:

```bash
cd backend
pytest -q tests/test_pure.py
```

Los tests de integración existentes necesitan una base de datos de pruebas
PostgreSQL con pgvector y `TEST_DATABASE_URL`; no se ejecutan en el job ligero
de CI de esta fase.

## CI

La acción `.github/workflows/ci.yml` valida los tests puros de Python y la
generación y compilación de los contratos TypeScript. También construye la
imagen Docker de producción de Next.js desde la raíz del monorepo. No despliega
aplicaciones ni cambia el pipeline de Cloud Run.

## Configuración por entorno y secretos

Los secretos continúan siendo responsabilidad del backend y de su entorno de
despliegue (por ejemplo, Secret Manager en Cloud Run). No se deben añadir
credenciales a los paquetes TypeScript ni al repositorio. Cada plataforma
tendrá variables de configuración públicas y separadas para desarrollo,
staging y producción; las claves privadas y las decisiones de autorización
permanecerán siempre en el backend.


## Aplicación móvil Expo

La primera base nativa vive en `apps/mobile/` y comparte los contratos
OpenAPI y el cliente HTTP de `packages/`. Los tokens móviles son Bearer y se
guardan en `expo-secure-store`; no se usan cookies del navegador ni
`localStorage`.

Para desarrollo:

```bash
pnpm install
pnpm contracts:generate
cp apps/mobile/.env.example apps/mobile/.env
# Ajusta EXPO_PUBLIC_API_URL según simulador o dispositivo.
pnpm --filter @smartfit/mobile start
```

- iOS Simulator: `http://localhost:8000`.
- Android Emulator: `http://10.0.2.2:8000`.
- Dispositivo físico: IP LAN de la máquina que ejecuta FastAPI.
- Producción: URL HTTPS del servicio FastAPI.

La API móvil llama directamente a FastAPI. En un dispositivo físico, el
servidor debe escuchar en una interfaz accesible por la LAN y el firewall debe
permitir el puerto; para producción se requiere HTTPS. Expo SecureStore
protege los tokens en Keychain (iOS) y Android Keystore. La app inicial cubre
registro, login, restauración y renovación de sesión, logout y onboarding;
las áreas de nutrición, entrenamiento, hábitos y progreso se integrarán
después por módulos.

El CI ejecuta el typecheck de la aplicación móvil junto al de web y contratos.
