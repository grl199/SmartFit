# Despliegue móvil de SmartFit con Cloud Build y EAS

## Qué hace este tercer activador

SmartFit tiene tres artefactos distintos:

| Activador | Configuración | Resultado |
| --- | --- | --- |
| Backend | `backend/cloudbuild.yaml` | Imagen Docker y despliegue del servicio FastAPI `smartfit` en Cloud Run |
| Web | `apps/web/cloudbuild.yaml` | Imagen Docker y despliegue del servicio Next.js `smartfit-web` en Cloud Run |
| Móvil | `apps/mobile/cloudbuild.yaml` | Cloud Build inicia y espera una compilación Android de Expo EAS |

**La app móvil no se despliega en Cloud Run.** Cloud Run sirve servicios HTTP; Android necesita un binario instalable. El nuevo activador usa Google Cloud Build como disparador/orquestador y Expo Application Services (EAS) como constructor nativo remoto. EAS genera el APK/AAB y gestiona la firma Android, sin tener que guardar una clave de firma dentro del repositorio ni construir un SDK Android propio en Cloud Build.

El fichero `apps/mobile/eas.json` define dos perfiles:

- `preview`: APK con distribución interna, instalable directamente en un Android para pruebas.
- `production`: Android App Bundle (AAB), formato destinado a Google Play, con incremento automático del número de versión remoto.

La URL de la API se incorpora al bundle en `EXPO_PUBLIC_API_URL`. Está alineada con el backend que ya usa el despliegue web. No es un secreto; no pongas aquí claves privadas ni tokens.

## 1. Vincular la app Expo una sola vez

Desde la raíz del repositorio:

```bash
cd apps/mobile
npx eas-cli@latest login
npx eas-cli@latest init
```

En `eas init`, crea un proyecto Expo o vincula el proyecto existente de SmartFit. El comando añade a `apps/mobile/app.json` el identificador real `expo.extra.eas.projectId`. **Conserva y sube ese cambio a Git**: el Cloud Build móvil comprueba que el identificador esté configurado y falla expresamente si falta.

Inicializa el contador remoto de Android para producción:

```bash
npx eas-cli@latest build:version:set --platform android --profile production
```

Comprueba la configuración:

```bash
npx eas-cli@latest config --platform android --profile preview
npx eas-cli@latest config --platform android --profile production
```

La primera compilación puede pedir a EAS que cree o configure las credenciales de firma de Android. Permite que EAS las gestione y almacene de forma remota; no subas keystores, passwords ni ficheros de credenciales al repositorio.

## 2. Guardar el token EAS en Secret Manager

En Expo, crea un **Access Token** para automatización. En Google Cloud, crea un secreto llamado exactamente `EXPO_TOKEN` y guarda ahí el token. No lo declares en `eas.json`, en Cloud Build substitutions, en GitHub ni en el código fuente.

También puedes crearlo desde terminal; el comando solicita el valor sin mostrarlo:

```bash
gcloud config get-value project
gcloud services enable cloudbuild.googleapis.com secretmanager.googleapis.com
gcloud secrets create EXPO_TOKEN --replication-policy=automatic
read -s -p "Token de Expo: " EXPO_TOKEN_VALUE
printf '%s' "$EXPO_TOKEN_VALUE" | gcloud secrets versions add EXPO_TOKEN --data-file=-
unset EXPO_TOKEN_VALUE
```

Concede `roles/secretmanager.secretAccessor` **a la cuenta de servicio seleccionada en el activador móvil** sobre el secreto `EXPO_TOKEN`. En Cloud Build → Triggers, revisa la cuenta de servicio elegida para el trigger; no supongas que coincide con la cuenta de servicio antigua de Cloud Build. La cuenta necesita además los permisos habituales para ejecutar builds de Cloud Build. Este YAML no publica contenedores en Artifact Registry ni despliega Cloud Run.

## 3. Crear el tercer activador de Cloud Build

En Google Cloud Console:

1. Abre **Cloud Build → Triggers** y selecciona el proyecto correcto.
2. Conecta el repositorio GitHub `grl199/SmartFit` si aún no está conectado.
3. Crea un trigger nuevo llamado, por ejemplo, `smartfit-mobile-android`.
4. Elige el evento **Push to a branch** y la rama de despliegue. Para probar la configuración actual puedes usar `^feat/mobile-app-design$`; antes de producción, cambia al patrón de la rama estable/release que uses.
5. En **Configuration**, selecciona **Cloud Build configuration file** y establece la ruta `apps/mobile/cloudbuild.yaml`. El contexto es la raíz del repositorio, no `apps/mobile`.
6. En **Substitution variables**, deja `_EAS_PROFILE=preview` para generar un APK de pruebas.
7. Selecciona la cuenta de servicio a la que acabas de otorgar acceso al secreto.
8. Guarda y ejecuta el trigger.

La configuración admite solo estos perfiles: `preview` y `production`. El perfil predeterminado es `preview`; para una ejecución de producción, cambia la sustitución `_EAS_PROFILE` a `production` en una ejecución manual o configura otro trigger de release con esa sustitución.

Es recomendable filtrar los cambios que disparan el pipeline para incluir `apps/mobile/**`, `packages/**`, `pnpm-lock.yaml`, `pnpm-workspace.yaml` y el `package.json` de la raíz. Así, los cambios en paquetes compartidos también regeneran la app móvil.

El paso de Cloud Build ejecuta `eas build --platform android --profile ... --non-interactive --wait --json`: espera a que termine la compilación remota y devuelve un resultado de build en los logs. El artefacto y su enlace de instalación/descarga quedan disponibles en el proyecto Expo/EAS. No esperes una nueva revisión de Cloud Run ni una imagen en Artifact Registry para esta app.

## 4. Instalar el APK en Android

Con `_EAS_PROFILE=preview`, abre la ejecución del build en Expo/EAS y utiliza el enlace de distribución interna para instalar el APK en el dispositivo Android. El perfil produce un APK y no necesita publicarse en Play Store para probarlo.

Verifica especialmente:

- login y persistencia de sesión;
- conexión al backend Cloud Run indicado por `EXPO_PUBLIC_API_URL`;
- cámara y código de barras;
- estimación de alimentos;
- permisos de ubicación y registro GPS en primer plano;
- navegación y pantallas de entrenamiento.

## 5. Publicar en Google Play

Para la distribución pública, ejecuta el trigger con `_EAS_PROFILE=production`. Ese perfil genera un AAB firmado para Google Play. El primer alta de la aplicación en Play Console y la configuración de la cuenta de desarrollador se hacen una sola vez.

Después puedes descargar el AAB desde el build de EAS y subirlo a Play Console (prueba interna primero, luego los tracks que correspondan). La subida a Google Play es un paso separado del despliegue en Cloud Run. Para automatizar también ese paso se puede añadir EAS Submit y configurar una cuenta de servicio de Google Play con los permisos mínimos; esta primera versión del trigger **solo construye** el AAB, no lo publica automáticamente.

## 6. Comprobaciones antes de producción

- [ ] `expo.extra.eas.projectId` ya existe en `apps/mobile/app.json` y está versionado.
- [ ] `EXPO_TOKEN` está en Secret Manager y la cuenta de servicio del trigger puede leerlo.
- [ ] La URL de `EXPO_PUBLIC_API_URL` es la URL HTTPS del backend de producción.
- [ ] Se ha generado e instalado un APK de `preview` en un Android real.
- [ ] Se ha comprobado la firma Android y la conservación de la clave de subida administrada por EAS.
- [ ] Se ha generado un AAB de `production` antes de intentar subirlo a Play Console.
- [ ] Los cambios de backend necesarios para móvil ya están desplegados y sus contratos compartidos están actualizados.

Referencias oficiales:

- [Cloud Build: crear y administrar triggers](https://docs.cloud.google.com/build/docs/automating-builds/create-manage-triggers)
- [Cloud Build: compilar desde GitHub](https://docs.cloud.google.com/build/docs/automating-builds/github/build-repos-from-github)
- [Expo: EAS Build en monorepos](https://docs.expo.dev/build-reference/build-with-monorepos/)
- [Expo: configuración de eas.json](https://docs.expo.dev/build/eas-json/)
- [Expo: APK instalable para Android](https://docs.expo.dev/build-reference/apk/)
