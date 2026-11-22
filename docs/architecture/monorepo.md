# Monorepo multiplataforma: fase inicial

Esta fase prepara el repositorio para incorporar web y móvil sin sustituir el
backend ni interrumpir Streamlit.

## Límites de responsabilidad

- `backend/` sigue siendo la fuente de verdad de autenticación, reglas de
  negocio, persistencia, nutrición, entrenamiento, hábitos e IA.
- `frontend/` conserva la aplicación Streamlit actual durante la transición.
- `packages/contracts/` contiene únicamente el contrato OpenAPI y los tipos
  TypeScript generados. No contiene lógica de negocio ni modelos duplicados.
- `apps/*` queda reservado para Next.js y Expo en entregas posteriores.
- Los futuros paquetes `packages/api-client`, `packages/design-tokens` y
  `packages/validation` se añadirán cuando exista una primera interfaz que los
  consuma.

## Requisitos

- Python 3.11 o superior (CI utiliza Python 3.12).
- Node.js 20.19.0 o superior.
- pnpm 10.12.1, fijado mediante `packageManager` en el `package.json` raíz.

## Instalación y generación

Desde la raíz del repositorio:

```bash
python -m pip install -r backend/requirements.txt
pnpm install
pnpm contracts:generate
pnpm typecheck
```

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
generación y compilación de los contratos TypeScript. No despliega aplicaciones
ni cambia el pipeline de Cloud Run.

## Configuración por entorno y secretos

Los secretos continúan siendo responsabilidad del backend y de su entorno de
despliegue (por ejemplo, Secret Manager en Cloud Run). No se deben añadir
credenciales a los paquetes TypeScript ni al repositorio. Cuando se incorporen
las aplicaciones web y móvil, cada plataforma tendrá variables de configuración
públicas y separadas para desarrollo, staging y producción; las claves privadas
y las decisiones de autorización permanecerán siempre en el backend.
