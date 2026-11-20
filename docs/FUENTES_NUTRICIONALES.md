# Fuentes nutricionales y alimentos propios

## Cómo se buscan los alimentos

La búsqueda es **local** (Postgres, instantánea, sin cupos): tu catálogo cargado por ingesta + tus alimentos + recetas. Solo si hay pocos
resultados se consulta además **Open Food Facts** (productos con código de barras) y lo encontrado se guarda. **No se llama a USDA ni a ninguna
otra API en la búsqueda**: sus datos se cargan una vez por lotes.

| Fuente | Uso | Licencia | Cómo entra |
|---|---|---|---|
| Open Food Facts | Productos con código de barras | ODbL (atribución; base derivada abierta si se redistribuye) | En línea al buscar (se guarda) |
| USDA FoodData Central (Foundation + SR Legacy) | Alimentos genéricos | CC0 | **Ingesta batch** desde sus CSV oficiales |
| Catálogo SmartFit | Alimentos habituales, raciones y recetas | Propio (valores orientativos) | Se siembra al arrancar |
| BEDCA u otra base en CSV | Alimentos propios del mercado español | **Por confirmar** (no la incluyo sin verificar su licencia) | **Ingesta batch** con el importador CSV |
| Alimentos del usuario | Lo que cada persona añade | Privados | Desde la app |

## Ingesta batch (una vez; se puede repetir para actualizar)

Desde `backend/`, con `DATABASE_URL` apuntando a tu Postgres:

```bash
# 1) USDA: descarga de https://fdc.nal.usda.gov/download-datasets.html los CSV de «Foundation Foods» y «SR Legacy»
#    (los nombres de fichero llevan la fecha de la versión). Vale el .zip tal cual o la carpeta descomprimida.
python -m app.ingest fdc ~/Descargas/FoodData_Central_foundation_food_csv_*.zip ~/Descargas/FoodData_Central_sr_legacy_food_csv_*.zip --dry-run   # ver qué entraría
python -m app.ingest fdc ~/Descargas/FoodData_Central_foundation_food_csv_*.zip ~/Descargas/FoodData_Central_sr_legacy_food_csv_*.zip

# 2) Los nombres de USDA están en inglés: traducción única con IA (reanudable; es el ÚNICO paso que usa IA)
python -m app.ingest translate --limit 200      # prueba pequeña y revisa el resultado en la app
python -m app.ingest translate                  # el resto (≈25 nombres por llamada)

# 3) Otra fuente en CSV (p. ej. BEDCA, tras confirmar que su licencia permite reutilizarla)
python -m app.ingest csv bedca.csv --source bedca --license "..." --attribution "..." --delimiter ";" --decimal-comma \
    --map "Alimento=name" --map "Energía (kcal)=kcal" --map "Proteínas=protein_g" --map "Hidratos=carbs_g" --map "Grasas=fat_g"

python -m app.ingest stats                      # alimentos por fuente
```

- **Idempotente:** repetir una carga (por ejemplo con una versión nueva de USDA) actualiza nutrientes y procedencia sin duplicar y **sin pisar
  las traducciones**. Clave única: `(fuente, id externo)`.
- **Filtros de calidad:** se omiten alimentos sin energía, con macros incompletos o con valores absurdos (> 950 kcal/100 g o macros > 105 g); el
  resumen indica cuántos y por qué.
- Cada alimento guarda fuente, id externo, fecha de carga, fiabilidad (`high`/`medium`/`low`), licencia y atribución.
- **Probado con ficheros sintéticos** en el formato oficial (columnas de `food.csv`, `food_nutrient.csv`, `nutrient.csv`, `food_category.csv`). No he podido
  descargar los CSV reales desde el entorno de desarrollo: haz primero `--dry-run` y revisa el resumen. Si una versión futura cambia las columnas, el
  lector falla con un mensaje claro en lugar de cargar datos erróneos.

## Alimentos propios de cada usuario

Privados (solo los ve su dueño, salvo que decida compartirlos) y salen **primero** en sus búsquedas:

- Crear: pestaña «Crear manual», o desde una búsqueda sin resultados («¿No lo encuentras?»), con unidad habitual opcional (1 loncha = 20 g).
- **«Crear mi versión»** de cualquier alimento (catálogo, USDA, Open Food Facts…): copia valores y unidades para ajustarlos; el original no cambia.
- Editar, borrar y gestionar unidades en «Mis alimentos». Lo ya registrado conserva su instantánea; un alimento usado en el diario o en una receta
  no se puede borrar (sí editar).
- Se pueden usar como ingredientes de recetas.

## Licencias

OFF (ODbL) y USDA (CC0) son compatibles para uso conjunto, pero ODbL exige atribuir y mantener abierta la base derivada de OFF si se redistribuye.
Revisa esto antes de publicar una base combinada.
