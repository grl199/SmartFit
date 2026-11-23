# Despliegue de SmartFit Web en Cloud Run

## Decisión

Desplegar `apps/web` como un segundo servicio de Cloud Run, independiente del
servicio FastAPI existente:

- `smartfit`: backend FastAPI y conexión con Neon/Gemini.
- `smartfit-web`: Next.js, renderizado de servidor y proxy del mismo origen
  `/api/*` hacia FastAPI.
- Streamlit se conserva durante la transición y no participa en este despliegue.

Esta opción aprovecha Google Cloud, Artifact Registry y Cloud Build ya usados
por el backend. No requiere convertir Next.js en una exportación estática:
la imagen utiliza `output: "standalone"` y ejecuta el servidor Node.js.

## Archivos de despliegue

- `apps/web/Dockerfile`: build multietapa desde la raíz del monorepo pnpm.
- `.dockerignore`: excluye instalaciones, builds locales y secretos.
- `apps/web/cloudbuild.yaml`: construye la imagen, la publica en Artifact
  Registry y despliega `smartfit-web` en Cloud Run.
- `apps/web/next.config.ts`: salida standalone con trazado desde la raíz del
  monorepo.

El build context debe seguir siendo la raíz del repositorio, ya que la web
consume `packages/contracts`.

## Despliegue inicial manual

Requisitos:

- Proyecto de Google Cloud seleccionado con `gcloud config set project PROJECT_ID`.
- Cloud Run, Cloud Build y Artifact Registry habilitados.
- El repositorio Artifact Registry `cloud-run-source-deploy` ya creado (el
  pipeline del backend utiliza ese nombre).
- La cuenta de servicio que ejecuta Cloud Build necesita permisos para escribir
  en Artifact Registry y desplegar en Cloud Run, además de
  `iam.serviceAccounts.actAs` sobre la cuenta de ejecución de Cloud Run.

Primero obtiene la URL del backend desplegado:

```bash
gcloud run services describe smartfit \
  --region=europe-west1 \
  --format='value(status.url)'
```

Después envía el contexto completo del monorepo a Cloud Build y sustituye la
URL del backend en el despliegue:

```bash
gcloud builds submit . \
  --config=apps/web/cloudbuild.yaml \
  --substitutions=_API_INTERNAL_URL="$(gcloud run services describe smartfit --region=europe-west1 --format='value(status.url)')"
```

El servicio web queda publicado como `smartfit-web` en `europe-west1`.
Cloud Run asigna una URL HTTPS propia. Se puede conectar un dominio desde la
configuración de Cloud Run una vez validado el despliegue.

## Despliegue automático desde GitHub

1. En Google Cloud Console abre Cloud Build → Triggers y conecta el repositorio
   `grl199/SmartFit`.
2. Crea un trigger de push para la rama de despliegue que quieras utilizar
   (para validar esta entrega, `test/multiplatform-foundation`).
3. Selecciona configuración desde el repositorio y establece el path
   `apps/web/cloudbuild.yaml`.
4. Añade la sustitución `_API_INTERNAL_URL` con la URL HTTPS real del servicio
   FastAPI `smartfit`. No uses la URL de la web en esa variable.
5. Ejecuta el trigger y comprueba el servicio `smartfit-web` en Cloud Run.

Para producción conviene crear un trigger separado para la rama de release,
con su propio servicio o política de despliegue. No se recomienda desplegar
automáticamente cada commit experimental a la URL de producción.

## Configuración y seguridad

- `API_INTERNAL_URL` es una variable de entorno de servidor. No la declares
  como `NEXT_PUBLIC_*`: el navegador llama a `/api/*` en el mismo origen y
  Next.js reenvía la petición a FastAPI.
- La URL del backend no es una contraseña, pero debe mantenerse en la
  configuración del servicio, no incrustada en el código.
- El servicio web acepta tráfico público porque es la interfaz de acceso. La
  autenticación de usuario sigue siendo responsabilidad de FastAPI.
- El proxy actual reenvía el JWT del usuario como `Authorization: Bearer`, pero
  no añade un token de identidad de Google para llamadas Cloud Run privadas.
  Por eso, con la implementación actual, el backend debe aceptar las peticiones
  HTTP de entrada a nivel de Cloud Run; las rutas protegidas siguen verificando
  el JWT en FastAPI. Si se decide bloquear el backend con IAM de Cloud Run, hay
  que implementar primero autenticación servicio-a-servicio con ID tokens en
  el proxy.
- La web usa cookies `HttpOnly`, `SameSite=Lax` y `Secure` en producción:
  `smartfit_access` dura 15 minutos y `smartfit_refresh` dura 30 días. El refresh
  token se rota en cada renovación y solo se almacena su hash en PostgreSQL.
- El proxy Next.js convierte la cookie de acceso en un header Bearer para
  FastAPI. Las peticiones de escritura con sesión exigen `Origin` del mismo
  origen; el navegador no recibe los tokens en JavaScript.
- En desarrollo local `Secure` se desactiva para permitir HTTP en localhost.
  En producción Cloud Run debe servirse por HTTPS. La revocación se persiste en
  `auth_sessions`; la tabla se crea automáticamente con el arranque de FastAPI.
- El build usa Node.js 22 y pnpm 10.12.1, coherentes con las versiones fijadas
  en el monorepo.

## CI y validación

GitHub Actions ejecuta:

1. tests puros de Python y generación OpenAPI;
2. typecheck y build de Next.js;
3. build de la imagen Docker de producción.

CI valida que la imagen se puede construir, pero no publica imágenes ni cambia
Cloud Run. El despliegue real requiere configurar el trigger y la sustitución
`_API_INTERNAL_URL` en el proyecto Google Cloud.

## Por qué Cloud Run y no Streamlit Cloud

Streamlit Cloud está orientado a aplicaciones Streamlit; la nueva interfaz es
un servidor Next.js y necesita Node.js, proxy servidor y renderizado dinámico.
Cloud Run ejecuta ese servidor como contenedor sin convertirlo en una web
estática y permite mantener frontend y backend como servicios separados.

Alternativas válidas:

- Vercel: integración muy cómoda para Next.js, pero el plan Hobby es solo para
  uso personal/no comercial; Pro tiene precio base publicado de USD 20/mes.
- Render: sencillo para Next.js y admite servicio Node.js; el nivel gratuito
  duerme tras 15 minutos de inactividad y el propio proveedor lo desaconseja
  para producción.
- Firebase App Hosting: también utiliza Cloud Build, Cloud Run y Cloud CDN y
  ofrece integración GitHub; su guía de monorepos documenta Nx y Turborepo,
  mientras este repositorio usa un workspace pnpm simple.

Cloud Run es la elección inicial porque la infraestructura backend ya reside
en Google Cloud y el monorepo puede construirse desde su raíz sin trasladar
paquetes compartidos ni adoptar otro proveedor.
