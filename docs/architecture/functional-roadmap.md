# Paridad funcional y hoja de ruta multiplataforma

Estado contrastado entre \`feat/first_draft\` (base Python/Streamlit) y \`test/multiplatform-foundation\` (monorepo y web), a 23 de noviembre de 2026.

## Diagnóstico ejecutivo

La rama de trabajo conserva el backend FastAPI y la interfaz Streamlit original. La aplicación Next.js ya permite acceder a los flujos principales, pero su cobertura es una primera migración funcional, no una paridad completa. La carpeta \`apps/mobile\` todavía no existe. El backend debe seguir siendo la única autoridad para reglas de negocio, persistencia, IA y permisos.

## Matriz de capacidades

| Área | Base disponible en el backend / Streamlit | Web actual | Trabajo pendiente |
|---|---|---|---|
| Acceso y onboarding | Registro, login, JWT, onboarding, perfil y objetivos | Implementado en primera versión | Sustituir token en localStorage por sesión segura HttpOnly; diseñar renovación/revocación; añadir pruebas E2E |
| Resumen | Dashboard diario, rango temporal y plan | Parcial: resumen diario y accesos rápidos | Rango semanal/mensual, calendario y resúmenes comparativos |
| Nutrición: búsqueda y diario | Catálogo, Open Food Facts, búsqueda online, registros, habituales y fechas | Parcial: búsqueda, registro, diario y repetición de frecuentes | Filtros online/offline, ficha completa, cantidades/unidades y acceso rápido |
| Nutrición: alimentos propios | Crear, editar, borrar, copiar, equivalencias y compartir con comunidad | Parcial: alta básica | CRUD completo, unidades/servings, copia, permisos de comunidad y estado de publicación |
| Nutrición: captura e IA | Lectura de código de barras, cámara, estimación Gemini por texto/foto, audio/transcripción y confirmación | Pendiente | Escaneo de código, captura de plato/etiqueta, estimación revisable y confirmación explícita |
| Recetas | Biblioteca, preview nutricional, edición de cantidades, copia y registro por raciones | Parcial: crear y registrar recetas | Preview de nutrientes, edición, copia de recetas de sistema y ajuste de raciones/cantidades |
| Asistente IA | Agente, herramientas, RAG, conversaciones, fuentes, imagen y audio | Añadido en este cambio | Validar límites por plan, gestión robusta de errores/cuotas y pruebas multimedia |
| Entrenamiento: sesiones | Registro de fuerza/cardio, series, repeticiones, peso, distancia, duración y kcal estimadas | Parcial: registro simplificado e historial | Editor por ejercicio y por serie, campos cardio, reestimación de kcal y feedback estructurado |
| Entrenamiento: catálogo | Búsqueda por músculo/equipo/tipo, ejercicios propios, historial individual y contenido multimedia/3D | Parcial: búsqueda y selección | Filtros, alta de ejercicio, guía, animaciones, últimas series y progreso por ejercicio |
| Entrenamiento: planes | Generar, editar días/ejercicios, alternativas, sugerencia de rutina | Parcial: generación y lectura | Edición de días, añadir/quitar/reordenar ejercicios, alternativas y plan histórico |
| Progreso | Peso, grasa corporal, fuerza, distancia, músculos, logros e insights (incluida IA) | Parcial: peso e insights resumidos | Gráficas temporales, progreso de fuerza/cardio, grupos musculares, análisis asistido y comparación de periodos |
| Hábitos y bienestar | Agua, objetivos, check-ins, actividad manual, conexiones y sincronización | Parcial: agua, pasos/distancia manual y check-in | Editar objetivo de agua, eliminar check-ins, historial visual, conexiones de proveedor y sincronización |
| Perfil | Datos, energía, objetivos, recalcular IA, eliminar cuenta, traducción de catálogo y reindexado RAG | Parcial: perfil y objetivos | Eliminar cuenta con reautenticación, operaciones de mantenimiento permitidas y consentimiento |
| Móvil | No existe aplicación Expo en la rama de trabajo | Ausente | Expo Router, autenticación segura con SecureStore, pantallas y cliente compartido |
| Funciones nativas | El backend admite actividad normalizada y archivos para IA | Ausente como producto móvil | Cámara/micrófono nativos, Health Connect, Apple Health, notificaciones push y modo offline |
| Monetización | Existen límites de IA por plan en el diseño/servicios, pero no hay flujos de compra multiplataforma en los frontends | Pendiente | Entitlements en backend, Google Play Billing, StoreKit, verificación server-side y publicidad Free |
| Producción | FastAPI, PostgreSQL/Neon y Cloud Run para backend | Proxy Next.js, imagen Docker standalone y Cloud Build independiente añadidos; CI construye la imagen | Configurar trigger y URL real del backend en GCP; revisar cookies/sesiones seguras, separación dev/staging/prod, observabilidad y almacenamiento de objetos |

## Siguiente orden de implementación

1. **Paridad web de nutrición**: unidades por alimento, gestión completa de alimentos propios, escáner, estimación con IA y recetas editables. Son capacidades ya respaldadas por el backend y de alto valor para el usuario.
2. **Paridad web de entrenamiento**: editor completo de sesión/series, cardio, progreso por ejercicio, guía multimedia, grupos musculares y editor del plan.
3. **Hábitos y progreso**: objetivos de agua, conexiones/sincronización de actividad, gráficas y análisis temporal.
4. **Cuenta y seguridad**: cookie HttpOnly/Secure/SameSite mediante BFF, refresh/revocación, eliminación segura de cuenta y pruebas E2E.
5. **Aplicación Expo**: autenticación y navegación primero; después nutrición y entrenamiento usando los contratos y cliente compartidos.
6. **Capacidades nativas y monetización**: cámara, voz, integraciones de salud, notificaciones, offline, suscripciones y límites de IA verificados en servidor.
7. **Retirada gradual de Streamlit**: solo después de validar paridad de resultados y sincronización con datos compartidos.

## Criterios transversales

- No duplicar cálculos de negocio en Next.js o Expo: reutilizar FastAPI.
- Toda mutación debe tener validación de entrada, estado de carga, error comprensible y confirmación de resultado.
- Mantener pruebas backend/OpenAPI y añadir pruebas de integración/E2E por flujo.
- Aplicar idempotencia a sincronizaciones y registrar el consentimiento de integraciones de salud.
- No guardar imágenes/audio grandes en PostgreSQL: usar almacenamiento de objetos o procesamiento temporal.
- No confiar en flags de Premium enviados por el cliente: validar las compras y entitlements en el backend.

## Despliegue web: decisión tomada

La alternativa a Streamlit Cloud para la nueva interfaz Next.js es un segundo
servicio de Cloud Run (`smartfit-web`) desplegado independientemente de FastAPI
(`smartfit`). El contenedor se construye desde la raíz pnpm del monorepo; su
proxy `/api/*` utiliza `API_INTERNAL_URL` configurada en el servidor. La
configuración está en `apps/web/Dockerfile` y `apps/web/cloudbuild.yaml`.

La configuración de código y CI está preparada, pero todavía falta conectar el
trigger de Cloud Build al repositorio, establecer la URL real del backend en
`_API_INTERNAL_URL` y ejecutar un despliegue real de verificación. No se debe
considerar publicado el frontend hasta completar esos pasos.
