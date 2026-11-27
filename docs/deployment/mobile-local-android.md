# Compilar SmartFit para Android en tu Mac con Android Studio

Esta guía genera APK sin consumir la cuota mensual de compilaciones cloud de Expo/EAS. Expo sigue gestionando la configuración de React Native, pero Gradle compila el binario en tu Mac.

## Qué necesitas

- macOS (Intel o Apple Silicon).
- Node.js 22.13 o superior.
- pnpm 10.12.1.
- Android Studio instalado desde [developer.android.com/studio](https://developer.android.com/studio).
- Un teléfono Android con opciones de desarrollador y depuración USB activadas, o un emulador Android.

En Android Studio, abre **Settings/Preferences → Languages & Frameworks → Android SDK** e instala Android SDK Platform, Android SDK Platform-Tools, Android SDK Build-Tools y Android SDK Command-line Tools (latest). Si Gradle solicita una plataforma concreta durante la sincronización, instálala desde SDK Manager.

En **Settings/Preferences → Build, Execution, Deployment → Build Tools → Gradle**, selecciona el JDK incluido con Android Studio (Embedded JDK/JBR) como Gradle JDK. No hace falta configurar una instalación JDK distinta salvo que Gradle lo solicite.

Para utilizar `adb` desde Terminal, el SDK suele estar en `$HOME/Library/Android/sdk`. Puedes añadirlo a `~/.zshrc`:

~~~bash
export ANDROID_HOME="$HOME/Library/Android/sdk"
export PATH="$PATH:$ANDROID_HOME/platform-tools"
~~~

Abre una Terminal nueva y comprueba `adb version`.

## 1. Actualizar el repositorio

Desde una Terminal, entra en el repositorio y confirma que estás en la rama de trabajo:

~~~bash
cd /Users/guille/Desktop/ProyectosML/SmartFit
git status
git switch feat/mobile-app-design
git pull
pnpm install --frozen-lockfile
~~~

Si `git status` muestra cambios locales que quieres conservar, no cambies de rama ni hagas pull hasta guardarlos.

## 2. Configurar la URL del backend

Crea el entorno local solo si todavía no existe:

~~~bash
test -f apps/mobile/.env || cp apps/mobile/.env.example apps/mobile/.env
~~~

Para un APK instalado en tu móvil, `EXPO_PUBLIC_API_URL` debe apuntar a un backend accesible desde Internet. El ejemplo del repositorio utiliza el Cloud Run de SmartFit:

~~~dotenv
EXPO_PUBLIC_API_URL=https://smartfit-367317612865.europe-west1.run.app
~~~

No uses `localhost` para el APK instalado en el teléfono: `localhost` señalaría al propio teléfono, no al Mac. Si estás desarrollando contra un backend local, usa `http://10.0.2.2:8000` en el emulador o `http://IP_LAN_DEL_MAC:8000` en un móvil físico conectado a la misma Wi-Fi.

El fichero `apps/mobile/.env` está excluido de Git. No lo sobrescribas cada vez que actualices el repositorio.

## 3. Generar y abrir el proyecto Android

Desde la raíz del repositorio puedes ejecutar:

~~~bash
pnpm --filter @smartfit/mobile android:studio
~~~

El script ejecuta Expo Prebuild para generar `apps/mobile/android/` y abre esa carpeta como proyecto de Android Studio. También puedes hacerlo por separado:

~~~bash
pnpm --filter @smartfit/mobile android:prebuild
open -a "Android Studio" apps/mobile/android
~~~

La carpeta Android se genera localmente a partir de `apps/mobile/app.json` y los config plugins. Está ignorada por Git intencionadamente para mantener el flujo Expo Continuous Native Generation; no la añadas al repositorio.

En Android Studio, espera a que termine **Gradle Sync**. Si pide descargar componentes del SDK, acepta la instalación.

## 4. Conectar el teléfono

En el teléfono Android:

1. Activa Opciones de desarrollador (pulsa varias veces «Número de compilación» en Ajustes → Información del teléfono).
2. Activa «Depuración USB».
3. Conecta el teléfono al Mac con un cable de datos.
4. Acepta en el teléfono el diálogo que autoriza la depuración de este ordenador.

En Terminal, comprueba que aparece:

~~~bash
adb devices
~~~

También puedes seleccionar el dispositivo en Android Studio.

## 5. Generar un APK independiente de tu Mac

Para tener una aplicación que funcione sin Metro ni el Mac, genera un APK **release** firmado. No uses el botón Run ni un APK debug para esta prueba: las builds debug normalmente esperan que Metro esté ejecutándose durante el desarrollo.

En Android Studio:

1. Abre **Build → Generate Signed Bundle / APK…**.
2. Selecciona **APK** y pulsa Next.
3. Selecciona el módulo `app`.
4. Crea un keystore local con **Create new…** si todavía no tienes uno para estas builds.
5. Guarda el keystore fuera del repositorio, por ejemplo en `~/.smartfit-android/smartfit-local.jks`.
6. Elige el build variant **release** y completa el asistente.

Guarda la contraseña, el alias y el keystore en un lugar seguro. No los subas a Git ni los compartas. **Conserva siempre la misma clave para futuras APK locales**: Android solo permite actualizar una instalación existente cuando la firma coincide.

Android Studio mostrará una notificación con la ubicación del APK (opción **locate**). El artefacto suele llamarse `app-release.apk`.

Si quieres instalarlo desde Terminal:

~~~bash
adb install -r "/ruta/que-muestra-Android-Studio/app-release.apk"
~~~

Si Android informa de que la firma no coincide con la aplicación ya instalada (por ejemplo, con el APK anterior firmado por EAS), desinstala la versión anterior y vuelve a instalar:

~~~bash
adb uninstall com.smartfit.mobile
adb install "/ruta/que-muestra-Android-Studio/app-release.apk"
~~~

**La desinstalación borra los datos locales de esa instalación** (por ejemplo, la sesión guardada en el teléfono y un borrador GPS todavía no sincronizado). Los datos que ya están guardados en la cuenta del backend no se borran.

## 6. Usar SmartFit con el Mac apagado

Una vez instalada una APK **release**, Android ejecuta la aplicación de forma independiente:

- No necesita Android Studio abierto.
- No necesita que el Mac esté encendido.
- No necesita Metro ni un servidor de desarrollo.
- La captura GPS y la copia provisional de la ruta se realizan en el teléfono.
- Las funciones que consultan o sincronizan datos necesitan Internet y que el backend de Cloud Run esté disponible.

Concede los permisos de ubicación que solicita SmartFit. Para mantener el registro al cambiar de aplicación o bloquear la pantalla, Android debe permitir la ubicación en segundo plano («Permitir siempre») y mostrar la notificación persistente del servicio. Una detención forzada desde Ajustes puede interrumpir el seguimiento; no es una prueba válida del comportamiento normal en segundo plano.

## 7. Compilaciones posteriores

Para cada nueva versión:

1. Actualiza la rama `feat/mobile-app-design`.
2. Conserva el mismo `apps/mobile/.env` y el mismo keystore.
3. Ejecuta `pnpm install --frozen-lockfile`.
4. Si han cambiado plugins, dependencias nativas o configuración de `app.json`, vuelve a generar el proyecto con `pnpm --filter @smartfit/mobile android:prebuild` y sincroniza Gradle.
5. Genera otra APK **release** con el mismo keystore.

Antes de distribuir una actualización, incrementa el `versionCode` de Android en `apps/mobile/app.json`; Android no instala como actualización una versión con un código inferior al instalado.

Esta clave local sirve para APK privadas instaladas manualmente. No sustituye automáticamente la clave de firma que EAS utiliza para builds cloud ni debe utilizarse para publicar en Google Play sin coordinar previamente la clave de subida y la configuración de Play App Signing.

## Diferencia entre comandos de desarrollo y APK instalable

- `pnpm --filter @smartfit/mobile android:studio`: genera el proyecto nativo y abre Android Studio.
- **Generate Signed Bundle / APK → APK → release**: genera el APK autónomo que puedes instalar y usar con el Mac apagado.
- `pnpm --filter @smartfit/mobile exec expo run:android --device`: compila una variante de desarrollo, instala y abre la app con Metro. Es útil para depurar, pero no es el flujo para el APK autónomo.

## Referencias

- [Expo: desarrollo local de aplicaciones](https://docs.expo.dev/guides/local-app-development/)
- [Expo: Continuous Native Generation y Prebuild](https://docs.expo.dev/workflow/continuous-native-generation/)
- [Expo: compilar y depurar con Android Studio](https://docs.expo.dev/debugging/runtime-issues/)
- [Android: Android SDK y herramientas de línea de comandos](https://developer.android.com/tools)
- [Descargar Android Studio](https://developer.android.com/studio)
