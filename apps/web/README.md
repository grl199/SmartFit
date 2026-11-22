# SmartFit Web

Primera interfaz web de SmartFit: autenticación y onboarding conectados a FastAPI.

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

Abre http://localhost:3000. Si FastAPI escucha en otra URL, cambia `NEXT_PUBLIC_API_URL` en `apps/web/.env.local`.

En otra terminal, desde la raíz:

```bash
cd backend
uvicorn app.main:app --reload
```

El onboarding genera objetivos con el proveedor de IA configurado en el backend; para completar ese paso se necesita su clave API y una base de datos accesible. Registro y login no necesitan una clave de IA.
