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

- Proyecto seleccionado: `woven-passkey-515111-t5` (`gcloud config set project woven-passkey-515111-t5`).
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


## Checklist previo a producción

No publiques la web hasta verificar estos puntos en el proyecto de Google Cloud:

### 1. Backend y base de datos

- [ ] El servicio Cloud Run `smartfit` está desplegado y responde en
  `/health`.
- [ ] La URL HTTPS del backend está disponible y se configurará como
  `_API_INTERNAL_URL` en Cloud Build.
- [ ] La base PostgreSQL/Neon tiene copia de seguridad reciente y el usuario
  de conexión puede crear las extensiones PostgreSQL requeridas:
  `vector`, `unaccent` y `pg_trgm`.
- [ ] Se ha comprobado que el esquema actual puede ejecutar
  `Base.metadata.create_all` y las migraciones idempotentes de
  `backend/app/migrations.py`. El backend ejecuta este trabajo al arrancar;
  no despliegues varias revisiones simultáneas durante una migración.
- [ ] `DATABASE_URL` se configura en el servicio backend desde Secret Manager,
  nunca en el repositorio ni en la imagen.

### 2. Secretos y configuración del backend

Configura como secretos de Secret Manager y enlázalos al servicio `smartfit`:

- [ ] `DATABASE_URL`: cadena de conexión PostgreSQL con SSL según el proveedor.
- [ ] `SECRET_KEY`: valor aleatorio estable (por ejemplo,
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`). No generes
  una clave nueva en cada revisión: invalidaría las sesiones existentes.
- [ ] La clave del proveedor de IA elegido: `GEMINI_API_KEY`,
  `OPENROUTER_API_KEY` o `OPENAI_API_KEY`, según `AI_PROVIDER`.

Variables de configuración a revisar en el backend:

- `ALLOW_REGISTRATION=false` cuando no quieras altas públicas.
- `AI_PROVIDER` y el modelo correspondiente.
- `OFF_USER_AGENT` con un identificador de contacto real.
- `TIMEZONE=Europe/Madrid` si esa sigue siendo la zona horaria deseada.

No guardes secretos en `--set-env-vars`, archivos YAML, GitHub ni en
variables `NEXT_PUBLIC_*`. Usa Secret Manager y concede a la cuenta de
ejecución del backend únicamente `roles/secretmanager.secretAccessor` sobre
los secretos que necesita.

### 3. Acceso entre servicios

En la configuración actual el proxy Next.js no genera Google ID tokens para
invocar un backend privado. Por tanto, el backend debe aceptar invocaciones
HTTP sin autenticación IAM de Cloud Run mientras la aplicación valida cada
usuario mediante JWT.

Esto significa que las rutas de login y las rutas protegidas son accesibles a
nivel de red pública; las protegidas deben seguir exigiendo autenticación de
SmartFit. Antes de producción, comprueba los límites de intentos de login y
evita considerar el endpoint público `/health` como prueba de disponibilidad
de la base de datos. Para cerrar el backend con IAM habrá que implementar
autenticación servicio-a-servicio desde el proxy y probarla antes de cambiar
`--no-allow-unauthenticated`.

### 4. Cloud Build y Cloud Run web

- [ ] Habilita Cloud Run, Cloud Build y Artifact Registry en el proyecto.
- [ ] Crea el repositorio Docker `cloud-run-source-deploy` en
  `europe-west1` si todavía no existe.
- [ ] Concede a la cuenta de Cloud Build permisos mínimos para publicar en
  Artifact Registry, desplegar Cloud Run y actuar sobre la cuenta de ejecución
  del servicio.
- [ ] Configura `_API_INTERNAL_URL` con la URL HTTPS real del backend. El
  pipeline ahora falla antes de construir si conserva el valor de ejemplo.
- [ ] Configura alertas de presupuesto y revisa límites de instancias, memoria
  y CPU antes de habilitar tráfico real.
- [ ] Tras desplegar, verifica login, refresh, logout, onboarding, carga del
  panel y una operación de escritura desde el dominio HTTPS final.

### 5. Dominio y cookies

La cookie de sesión es `Secure` en producción. Prueba la aplicación bajo HTTPS
y en el dominio definitivo; no pruebes el login de producción desde una URL
HTTP. Si se cambia el dominio después de probar sesiones, inicia sesión de
nuevo porque las cookies están vinculadas al host.

### 6. Qué falta confirmar antes de ejecutar el despliegue

Este repositorio no contiene ni debe contener el ID del proyecto de Google
Cloud, las credenciales, los secretos ni el dominio final. Antes de ejecutar
`gcloud builds submit` o crear un trigger, confirma esos datos y verifica
que tienes seleccionado el proyecto correcto con `gcloud config get-value project`.
