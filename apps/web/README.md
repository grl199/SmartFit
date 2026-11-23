# SmartFit Web

Interfaz web de SmartFit: autenticación, onboarding y espacio personal conectado a FastAPI.

## Requisitos

- Node.js 20.19+
- pnpm 10.12.1
- Backend SmartFit disponible en `http://localhost:8000`

## Desarrollo

Desde la raíz del monorepo:

```bash
pnpm install
cp apps/web/.env.example apps/web/.env.local
pnpm dev:web
```

Abre http://localhost:3000. El frontend utiliza rutas del mismo origen (`/api/*`) y Next.js reenvía las peticiones al backend. Así el navegador no depende de CORS para login ni para el resto de llamadas.

Si FastAPI escucha en otra dirección, cambia `API_INTERNAL_URL` en `apps/web/.env.local` y reinicia Next.js. Si ya tenías `NEXT_PUBLIC_API_URL` configurado, no es necesario mantenerlo: la nueva configuración usa `API_INTERNAL_URL`.

En otra terminal, desde la raíz:

```bash
cd backend
uvicorn app.main:app --reload
```

Para iniciar la base de datos local:

```bash
docker compose up -d db
```

Comprueba la API en http://localhost:8000/health. Debe devolver `{"ok":true}`.

El onboarding puede requerir la configuración de IA del backend y una base de datos accesible. Registro y login no necesitan una clave de IA.

## Producción en Cloud Run

La web se empaqueta como una imagen Node.js standalone desde la raíz del
monorepo. La guía de despliegue, los requisitos de Cloud Build y la configuración
de `API_INTERNAL_URL` están en
[`docs/deployment/web-cloud-run.md`](../../docs/deployment/web-cloud-run.md).
