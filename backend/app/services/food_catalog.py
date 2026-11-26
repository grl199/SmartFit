"""Catálogo interno SmartFit: alimentos genéricos de uso diario, sus raciones habituales y recetas predefinidas.

Los valores son orientativos (referencia: composición genérica tipo USDA FoodData Central, CC0). Se marcan con
confianza «medium» y fuente «catalog»; si necesitas precisión, usa el producto concreto. Todo se siembra de forma idempotente
(clave `external_id` = «smartfit:<slug>»)."""
import logging
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Food, FoodServing, Recipe, RecipeIngredient

log = logging.getLogger(__name__)
ATTRIBUTION = "Valores genéricos orientativos de SmartFit (referencia: USDA FoodData Central, CC0)."

# nombre: (kcal, prot, hidr, azúcares, grasa, saturadas, fibra, sodio_mg, [(unidad, plural, gramos, aclaración)])
FOODS: dict[str, tuple] = {
    "Café (infusión, sin azúcar)": (1, 0.1, 0, 0, 0, 0, 0, 2, [("taza", "tazas", 150, "taza de café largo"), ("ml", "ml", 1.0, "mililitros")]),
    "Leche entera": (61, 3.2, 4.8, 4.8, 3.3, 1.9, 0, 43, [("vaso", "vasos", 200, "vaso de 200 ml"), ("ml", "ml", 1.03, "mililitros")]),
    "Leche semidesnatada": (46, 3.3, 4.8, 4.8, 1.6, 1.0, 0, 44, [("vaso", "vasos", 200, "vaso de 200 ml"), ("ml", "ml", 1.03, "mililitros")]),
    "Leche desnatada": (34, 3.4, 4.9, 4.9, 0.1, 0.1, 0, 44, [("vaso", "vasos", 200, "vaso de 200 ml"), ("ml", "ml", 1.03, "mililitros")]),
    "Pan de molde": (265, 8.0, 49, 4.0, 3.2, 0.8, 2.7, 490, [("rebanada", "rebanadas", 30, "rebanada media")]),
    "Hummus": (166, 7.9, 14.3, 0.3, 9.6, 1.4, 6.0, 379, [("cucharada", "cucharadas", 15, "cucharada sopera colmada")]),
    "Aceite de oliva virgen extra": (884, 0, 0, 0, 100, 13.8, 0, 2, [("cucharada", "cucharadas", 13.5, "cucharada sopera"), ("cucharadita", "cucharaditas", 4.5, None), ("ml", "ml", 0.91, "mililitros")]),
    "Tomate": (18, 0.9, 3.9, 2.6, 0.2, 0, 1.2, 5, [("rodaja", "rodajas", 20, "rodaja de tomate mediano"), ("unidad", "unidades", 120, "tomate mediano")]),
    "Yogur natural": (61, 3.5, 4.7, 4.7, 3.3, 2.1, 0, 46, [("unidad", "unidades", 125, "tarrina de 125 g")]),
    "Copos de avena": (389, 16.9, 66.3, 0, 6.9, 1.2, 10.6, 2, [("cucharada", "cucharadas", 10, "cucharada sopera"), ("puñado", "puñados", 30, None)]),
    "Plátano": (89, 1.1, 22.8, 12.2, 0.3, 0.1, 2.6, 1, [("unidad", "unidades", 120, "plátano mediano sin piel")]),
    "Almendras": (579, 21.2, 21.6, 4.4, 49.9, 3.8, 12.5, 1, [("unidad", "unidades", 1.2, "almendra"), ("puñado", "puñados", 28, None)]),

    "Pan integral": (247, 13.0, 41.0, 5.0, 4.2, 0.8, 7.0, 400, [("rebanada", "rebanadas", 35, "rebanada mediana")]),
    "Pan de barra": (270, 9.0, 52.0, 2.5, 1.8, 0.4, 2.7, 550, [("rebanada", "rebanadas", 30, "rebanada fina"), ("trozo", "trozos", 50, "trozo pequeño")]),
    "Huevo entero": (143, 12.6, 0.7, 0.4, 9.5, 3.1, 0.0, 142, [("unidad", "unidades", 60, "huevo mediano sin cáscara")]),
    "Atún al natural escurrido": (116, 25.5, 0.0, 0.0, 0.8, 0.2, 0.0, 300, [("lata", "latas", 60, "peso escurrido orientativo")]),
    "Pechuga de pollo cocinada": (165, 31.0, 0.0, 0.0, 3.6, 1.0, 0.0, 74, [("filete", "filetes", 120, "filete mediano")]),
    "Pavo cocinado": (135, 29.0, 0.0, 0.0, 1.6, 0.4, 0.0, 50, [("filete", "filetes", 100, "filete mediano")]),
    "Pavo fiambre": (105, 18.0, 2.0, 1.5, 2.0, 0.5, 0.0, 900, [("loncha", "lonchas", 20, "loncha fina")]),
    "Jamón cocido": (116, 20.9, 1.5, 1.0, 3.4, 1.2, 0.0, 900, [("loncha", "lonchas", 20, "loncha fina")]),
    "Aguacate": (160, 2.0, 8.5, 0.7, 14.7, 2.1, 6.7, 7, [("medio", "medios", 75, "medio aguacate sin piel ni hueso")]),
    "Lechuga": (15, 1.4, 2.9, 0.8, 0.2, 0.0, 1.3, 28, [("hoja", "hojas", 10, "hoja grande")]),
    "Pepino": (15, 0.7, 3.6, 1.7, 0.1, 0.0, 0.5, 2, [("unidad", "unidades", 250, "pepino mediano")]),
    "Cebolla": (40, 1.1, 9.3, 4.2, 0.1, 0.0, 1.7, 4, [("unidad", "unidades", 110, "cebolla mediana")]),
    "Zanahoria": (41, 0.9, 9.6, 4.7, 0.2, 0.0, 2.8, 69, [("unidad", "unidades", 60, "zanahoria mediana")]),
    "Arroz blanco cocido": (130, 2.7, 28.2, 0.1, 0.3, 0.1, 0.4, 1, [("vaso", "vasos", 160, "vaso de arroz cocido")]),
    "Pasta cocida": (158, 5.8, 30.9, 0.6, 0.9, 0.2, 1.8, 1, [("plato", "platos", 180, "ración cocida")]),
    "Patata cocida": (87, 1.9, 20.1, 0.9, 0.1, 0.0, 1.8, 4, [("unidad", "unidades", 150, "patata mediana")]),
    "Garbanzos cocidos": (164, 8.9, 27.4, 4.8, 2.6, 0.3, 7.6, 7, [("cucharón", "cucharones", 100, "cucharón pequeño")]),
    "Lentejas cocidas": (116, 9.0, 20.1, 1.8, 0.4, 0.1, 7.9, 2, [("cucharón", "cucharones", 100, "cucharón pequeño")]),
    "Quinoa cocida": (120, 4.4, 21.3, 0.9, 1.9, 0.2, 2.8, 7, [("vaso", "vasos", 150, "vaso de quinoa cocida")]),
    "Queso fresco batido 0%": (46, 8.5, 3.5, 3.5, 0.2, 0.1, 0.0, 40, [("tarrina", "tarrinas", 200, "tarrina individual")]),
    "Queso fresco": (174, 11.0, 3.4, 2.7, 12.7, 8.3, 0.0, 450, [("porción", "porciones", 50, "porción individual")]),
    "Manzana": (52, 0.3, 13.8, 10.4, 0.2, 0.0, 2.4, 1, [("unidad", "unidades", 170, "manzana mediana")]),
    "Naranja": (47, 0.9, 11.8, 9.4, 0.1, 0.0, 2.4, 0, [("unidad", "unidades", 150, "naranja mediana sin piel")]),
    "Fresas": (32, 0.7, 7.7, 4.9, 0.3, 0.0, 2.0, 1, [("puñado", "puñados", 80, None)]),
    "Yogur griego natural": (97, 9.0, 3.9, 3.2, 5.0, 3.3, 0.0, 35, [("unidad", "unidades", 150, "tarrina individual")]),
    "Espinacas": (23, 2.9, 3.6, 0.4, 0.4, 0.1, 2.2, 79, [("puñado", "puñados", 30, None)]),
    "Champiñones": (22, 3.1, 3.3, 2.0, 0.3, 0.0, 1.0, 5, [("unidad", "unidades", 18, "champiñón mediano")]),
    "Salsa de tomate casera": (50, 1.5, 7.0, 5.0, 1.8, 0.3, 1.5, 250, [("cucharada", "cucharadas", 20, "cucharada sopera")]),

    "Arroz integral cocido": (123, 2.7, 25.6, 0.2, 1.0, 0.2, 1.8, 4, [("vaso", "vasos", 160, "vaso de arroz cocido")]),
    "Pasta integral cocida": (149, 5.5, 30.1, 0.6, 1.1, 0.2, 3.9, 4, [("plato", "platos", 180, "ración cocida")]),
    "Cuscús cocido": (112, 3.8, 23.2, 0.1, 0.2, 0.0, 1.4, 5, [("vaso", "vasos", 160, "vaso de cuscús")]),
    "Bulgur cocido": (83, 3.1, 18.6, 0.1, 0.2, 0.0, 4.5, 5, [("vaso", "vasos", 150, "vaso de bulgur")]),
    "Avena cocida": (71, 2.5, 12.0, 0.3, 1.5, 0.3, 1.7, 4, [("cuenco", "cuencos", 250, "cuenco de gachas")]),
    "Pan de centeno": (259, 8.5, 48.3, 3.9, 3.3, 0.6, 5.8, 600, [("rebanada", "rebanadas", 35, "rebanada mediana")]),
    "Tortita de maíz": (387, 8.0, 81.0, 0.7, 3.0, 0.5, 4.5, 700, [("unidad", "unidades", 8, "tortita de maíz")]),
    "Brócoli": (34, 2.8, 6.6, 1.7, 0.4, 0.1, 2.6, 33, [("ración", "raciones", 150, "ración cocida")]),
    "Coliflor": (25, 1.9, 5.0, 1.9, 0.3, 0.1, 2.0, 30, [("ración", "raciones", 150, "ración cocida")]),
    "Calabacín": (17, 1.2, 3.1, 2.5, 0.3, 0.1, 1.0, 8, [("unidad", "unidades", 250, "calabacín mediano")]),
    "Pimiento rojo": (31, 1.0, 6.0, 4.2, 0.3, 0.1, 2.1, 4, [("unidad", "unidades", 150, "pimiento mediano")]),
    "Espárragos": (20, 2.2, 3.9, 1.9, 0.1, 0.0, 2.1, 2, [("ración", "raciones", 150, "ración")]),
    "Judías verdes": (31, 1.8, 7.0, 3.3, 0.2, 0.1, 3.4, 6, [("ración", "raciones", 150, "ración cocida")]),
    "Guisantes cocidos": (81, 5.4, 14.5, 5.7, 0.4, 0.1, 5.7, 5, [("cucharón", "cucharones", 100, "cucharón pequeño")]),
    "Berenjena": (25, 1.0, 5.9, 3.5, 0.2, 0.0, 3.0, 2, [("unidad", "unidades", 250, "berenjena mediana")]),
    "Calabaza": (26, 1.0, 6.5, 2.8, 0.1, 0.0, 0.5, 1, [("ración", "raciones", 150, "ración cocida")]),
    "Boniato asado": (90, 2.0, 20.7, 6.5, 0.2, 0.0, 3.3, 36, [("unidad", "unidades", 180, "boniato mediano")]),
    "Remolacha cocida": (44, 1.7, 10.0, 7.0, 0.2, 0.0, 2.0, 78, [("unidad", "unidades", 80, "remolacha pequeña")]),
    "Apio": (14, 0.7, 3.0, 1.3, 0.2, 0.0, 1.6, 80, [("rama", "ramas", 40, "rama mediana")]),
    "Col lombarda": (31, 1.4, 7.4, 3.8, 0.2, 0.0, 2.1, 27, [("ración", "raciones", 100, "ración cruda")]),
    "Pera": (57, 0.4, 15.2, 9.8, 0.1, 0.0, 3.1, 1, [("unidad", "unidades", 170, "pera mediana")]),
    "Kiwi": (61, 1.1, 14.7, 9.0, 0.5, 0.0, 3.0, 3, [("unidad", "unidades", 75, "kiwi mediano")]),
    "Piña": (50, 0.5, 13.1, 9.9, 0.1, 0.0, 1.4, 1, [("rodaja", "rodajas", 80, "rodaja natural")]),
    "Arándanos": (57, 0.7, 14.5, 10.0, 0.3, 0.0, 2.4, 1, [("puñado", "puñados", 50, "puñado pequeño")]),
    "Frambuesas": (52, 1.2, 11.9, 4.4, 0.7, 0.0, 6.5, 1, [("puñado", "puñados", 50, "puñado pequeño")]),
    "Uvas": (69, 0.7, 18.1, 15.5, 0.2, 0.1, 0.9, 2, [("racimo", "racimos", 100, "racimo pequeño")]),
    "Sandía": (30, 0.6, 7.6, 6.2, 0.2, 0.0, 0.4, 1, [("tajada", "tajadas", 200, "tajada mediana")]),
    "Mango": (60, 0.8, 15.0, 13.7, 0.4, 0.1, 1.6, 1, [("unidad", "unidades", 200, "porción comestible")]),
    "Melocotón": (39, 0.9, 9.5, 8.4, 0.3, 0.0, 1.5, 0, [("unidad", "unidades", 150, "melocotón mediano")]),
    "Mandarina": (53, 0.8, 13.3, 10.6, 0.3, 0.0, 1.8, 2, [("unidad", "unidades", 80, "mandarina mediana")]),
    "Salmón cocinado": (206, 22.1, 0.0, 0.0, 12.4, 2.8, 0.0, 59, [("lomo", "lomos", 150, "lomo mediano")]),
    "Merluza cocinada": (90, 19.0, 0.0, 0.0, 1.5, 0.3, 0.0, 80, [("filete", "filetes", 150, "filete mediano")]),
    "Bacalao cocinado": (105, 23.0, 0.0, 0.0, 0.9, 0.2, 0.0, 250, [("lomo", "lomos", 150, "lomo mediano")]),
    "Sardinas en conserva escurridas": (208, 24.6, 0.0, 0.0, 11.5, 2.7, 0.0, 505, [("lata", "latas", 85, "peso escurrido orientativo")]),
    "Gambas cocidas": (99, 24.0, 0.2, 0.0, 0.3, 0.1, 0.0, 111, [("puñado", "puñados", 100, "puñado")]),
    "Ternera magra cocinada": (217, 26.0, 0.0, 0.0, 12.0, 4.8, 0.0, 65, [("filete", "filetes", 150, "filete mediano")]),
    "Lomo de cerdo cocinado": (143, 26.0, 0.0, 0.0, 3.5, 1.2, 0.0, 55, [("filete", "filetes", 120, "filete mediano")]),
    "Tofu firme": (144, 17.3, 2.8, 0.6, 8.7, 1.3, 2.3, 14, [("porción", "porciones", 100, "porción individual")]),
    "Tempeh": (193, 20.3, 9.4, 0.0, 10.8, 2.5, 3.8, 9, [("porción", "porciones", 100, "porción individual")]),
    "Edamame cocido": (121, 12.0, 8.9, 2.2, 5.2, 0.6, 5.2, 6, [("cuenco", "cuencos", 100, "cuenco pequeño")]),
    "Alubias blancas cocidas": (139, 9.7, 25.1, 0.3, 0.4, 0.1, 6.3, 6, [("cucharón", "cucharones", 100, "cucharón pequeño")]),
    "Alubias rojas cocidas": (127, 8.7, 22.8, 0.3, 0.5, 0.1, 6.4, 2, [("cucharón", "cucharones", 100, "cucharón pequeño")]),
    "Queso cottage": (98, 11.1, 3.4, 2.7, 4.3, 1.7, 0.0, 364, [("tarrina", "tarrinas", 200, "tarrina individual")]),
    "Mozzarella": (280, 28.0, 2.2, 1.0, 17.0, 10.0, 0.0, 600, [("bola", "bolas", 125, "bola mediana")]),
    "Queso feta": (265, 14.2, 4.1, 4.1, 21.5, 15.0, 0.0, 1116, [("porción", "porciones", 40, "porción pequeña")]),
    "Skyr natural": (63, 11.0, 4.0, 4.0, 0.2, 0.1, 0.0, 45, [("tarrina", "tarrinas", 150, "tarrina individual")]),
    "Kéfir natural": (63, 3.5, 4.7, 4.7, 3.5, 2.2, 0.0, 50, [("vaso", "vasos", 200, "vaso mediano")]),
    "Bebida de soja sin azúcar": (33, 3.3, 0.7, 0.2, 1.8, 0.3, 0.6, 35, [("vaso", "vasos", 200, "vaso de 200 ml"), ("ml", "ml", 1.0, "mililitros")]),
    "Nueces": (654, 15.2, 13.7, 2.6, 65.2, 6.1, 6.7, 2, [("unidad", "unidades", 5, "media nuez"), ("puñado", "puñados", 25, "puñado pequeño")]),
    "Cacahuetes": (567, 25.8, 16.1, 4.7, 49.2, 6.8, 8.5, 18, [("puñado", "puñados", 25, "puñado pequeño")]),
    "Crema de cacahuete 100%": (588, 25.1, 20.0, 9.2, 50.4, 10.1, 6.0, 17, [("cucharada", "cucharadas", 15, "cucharada sopera")]),
    "Semillas de chía": (486, 16.5, 42.1, 0.0, 30.7, 3.3, 34.4, 16, [("cucharada", "cucharadas", 12, "cucharada sopera")]),
    "Semillas de calabaza": (559, 30.2, 10.7, 1.4, 49.1, 8.7, 6.0, 7, [("cucharada", "cucharadas", 10, "cucharada sopera")]),
    "Tahini": (595, 17.0, 21.2, 0.5, 53.8, 7.5, 9.3, 115, [("cucharada", "cucharadas", 15, "cucharada sopera")]),
    "Miel": (304, 0.3, 82.4, 82.1, 0.0, 0.0, 0.2, 4, [("cucharadita", "cucharaditas", 7, "cucharadita")]),
    "Chocolate negro 85%": (598, 7.8, 19.0, 11.0, 52.0, 30.0, 11.0, 20, [("onza", "onzas", 10, "onza de tableta")]),
    "Cacao puro en polvo": (228, 19.6, 57.9, 1.8, 13.7, 8.1, 37.0, 21, [("cucharada", "cucharadas", 5, "cucharada sopera")]),
    "Leche semidesnatada sin lactosa": (46, 3.3, 4.8, 4.8, 1.6, 1, 0, 44, [("vaso", "vasos", 200, "vaso de 200 ml")]),
    "Bebida de avena sin azúcar": (40, 1, 6.7, 3, 1.5, 0.2, 0.8, 40, [("vaso", "vasos", 200, "vaso de 200 ml")]),
    "Bebida de almendras sin azúcar": (15, 0.5, 0.3, 0, 1.2, 0.1, 0.3, 40, [("vaso", "vasos", 200, "vaso de 200 ml")]),
    "Yogur natural desnatado": (46, 4.3, 6, 6, 0.2, 0.1, 0, 52, [("unidad", "unidades", 125, "tarrina de 125 g")]),
    "Requesón": (98, 11, 3.4, 2.7, 4.3, 1.7, 0, 364, [("porción", "porciones", 100, "porción individual")]),
    "Ricotta": (174, 11.3, 3, 0.3, 13, 8.3, 0, 84, [("cucharada", "cucharadas", 30, "cucharada colmada")]),
    "Claras de huevo": (52, 10.9, 0.7, 0.7, 0.2, 0, 0, 166, [("unidad", "unidades", 33, "clara de huevo mediano")]),
    "Pechuga de pavo cocinada": (135, 29, 0, 0, 1.6, 0.4, 0, 50, [("filete", "filetes", 110, "filete mediano")]),
    "Atún fresco cocinado": (184, 30, 0, 0, 6.3, 1.6, 0, 50, [("filete", "filetes", 150, "filete mediano")]),
    "Caballa cocinada": (262, 23.9, 0, 0, 17.8, 4.2, 0, 83, [("filete", "filetes", 120, "filete mediano")]),
    "Seitán": (141, 24, 4, 0, 2, 0.3, 1, 30, [("porción", "porciones", 100, "porción individual")]),
    "Soja texturizada hidratada": (112, 17.5, 8, 3, 1, 0.2, 4, 5, [("ración", "raciones", 100, "peso ya hidratado")]),
    "Maíz dulce cocido": (96, 3.4, 21, 4.5, 1.5, 0.2, 2.4, 2, [("cucharada", "cucharadas", 15, "cucharada sopera")]),
    "Pan de pita integral": (262, 9.8, 55, 2, 1.7, 0.3, 6, 450, [("unidad", "unidades", 60, "pan de pita mediano")]),
    "Tortilla de trigo": (312, 8.3, 52, 2.5, 7.5, 2, 3, 650, [("unidad", "unidades", 40, "tortilla mediana")]),
    "Harina de avena": (404, 14, 65, 1, 9, 1.5, 9, 5, [("cucharada", "cucharadas", 10, "cucharada sopera")]),
    "Rúcula": (25, 2.6, 3.7, 2.1, 0.7, 0.1, 1.6, 27, [("puñado", "puñados", 20, "puñado pequeño")]),
    "Col rizada (kale)": (49, 4.3, 8.8, 2.3, 0.9, 0.1, 3.6, 38, [("puñado", "puñados", 30, "hojas frescas")]),
    "Coles de Bruselas": (43, 3.4, 9, 2.2, 0.3, 0.1, 3.8, 25, [("ración", "raciones", 150, "ración cocida")]),
    "Ajo": (149, 6.4, 33.1, 1, 0.5, 0.1, 2.1, 17, [("diente", "dientes", 3, "diente mediano")]),
    "Tomate triturado natural": (24, 1.2, 4.5, 3.5, 0.2, 0, 1.5, 10, [("cucharada", "cucharadas", 20, "cucharada sopera")]),
    "Papaya": (43, 0.5, 10.8, 7.8, 0.3, 0.1, 1.7, 8, [("porción", "porciones", 150, "porción sin piel")]),
    "Ciruela": (46, 0.7, 11.4, 9.9, 0.3, 0, 1.4, 0, [("unidad", "unidades", 65, "ciruela mediana")]),
    "Cerezas": (63, 1.1, 16, 12.8, 0.2, 0, 2.1, 0, [("puñado", "puñados", 80, "puñado sin hueso")]),
    "Pomelo": (42, 0.8, 10.7, 6.9, 0.1, 0, 1.6, 0, [("medio", "medios", 120, "medio pomelo")]),
    "Dátiles": (282, 2.5, 75, 63, 0.4, 0.1, 8, 2, [("unidad", "unidades", 8, "dátil mediano")]),
    "Salsa de soja": (53, 8.1, 4.9, 0.4, 0.6, 0.1, 0.8, 5493, [("cucharadita", "cucharaditas", 5, "cucharadita")]),


    "Café con leche (leche entera)": (31, 1.65, 2.4, 2.4, 1.65, 0.95, 0.0, 23, [("taza", "tazas", 200, "taza de 200 ml")]),
    "Café con leche (leche semidesnatada)": (24, 1.7, 2.4, 2.4, 0.8, 0.5, 0.0, 23, [("taza", "tazas", 200, "taza de 200 ml")]),
    "Café con leche (leche desnatada)": (18, 1.75, 2.45, 2.45, 0.05, 0.05, 0.0, 23, [("taza", "tazas", 200, "taza de 200 ml")]),

}
# receta: (descripción, raciones, [(alimento, gramos)])
RECIPES: dict[str, tuple[str, float, list[tuple[str, float]]]] = {
    "Tostada con hummus": ("Dos rebanadas de pan con hummus.", 1, [("Pan de molde", 60), ("Hummus", 30)]),
    "Tostada con aceite y tomate": ("Dos rebanadas de pan con tomate y aceite de oliva.", 1,
                                    [("Pan de molde", 60), ("Tomate", 60), ("Aceite de oliva virgen extra", 10)]),
    "Yogur con avena y fruta": ("Yogur natural con copos de avena y plátano.", 1,
                                [("Yogur natural", 125), ("Copos de avena", 30), ("Plátano", 60)]),

    "Tostada integral con aguacate": ("Tostada de pan integral con aguacate y un toque de aceite.", 1,
                                      [("Pan integral", 50), ("Aguacate", 40), ("Aceite de oliva virgen extra", 5)]),
    "Tostada integral con tomate y aceite": ("Tostada integral con tomate natural y aceite de oliva.", 1,
                                             [("Pan integral", 50), ("Tomate", 60), ("Aceite de oliva virgen extra", 8)]),
    "Tostada integral con pavo": ("Tostada integral con pavo y tomate.", 1,
                                  [("Pan integral", 50), ("Pavo fiambre", 40), ("Tomate", 30)]),
    "Bocadillo de pavo y tomate": ("Bocadillo pequeño de pavo con tomate.", 1,
                                  [("Pan de barra", 100), ("Pavo fiambre", 60), ("Tomate", 30)]),
    "Ensalada mixta con atún": ("Ensalada de lechuga, tomate, pepino, atún, huevo y aceite.", 1,
                               [("Lechuga", 60), ("Tomate", 100), ("Pepino", 50), ("Atún al natural escurrido", 80),
                                ("Huevo entero", 60), ("Aceite de oliva virgen extra", 8)]),
    "Ensalada de garbanzos y atún": ("Ensalada de garbanzos con atún, tomate y cebolla.", 1,
                                    [("Garbanzos cocidos", 150), ("Atún al natural escurrido", 80), ("Tomate", 60),
                                     ("Cebolla", 20), ("Aceite de oliva virgen extra", 8)]),
    "Ensalada de quinoa": ("Ensalada fría de quinoa, tomate, pepino y aguacate.", 1,
                           [("Quinoa cocida", 120), ("Tomate", 60), ("Pepino", 50), ("Aguacate", 40),
                            ("Aceite de oliva virgen extra", 5)]),
    "Ensalada de lentejas": ("Ensalada de lentejas con tomate, cebolla y zanahoria.", 1,
                             [("Lentejas cocidas", 150), ("Tomate", 60), ("Cebolla", 20), ("Zanahoria", 40),
                              ("Aceite de oliva virgen extra", 8)]),
    "Tortilla francesa": ("Tortilla francesa de dos huevos con aceite.", 1,
                          [("Huevo entero", 120), ("Aceite de oliva virgen extra", 5)]),
    "Huevos revueltos con queso fresco": ("Huevos revueltos con queso fresco.", 1,
                                         [("Huevo entero", 120), ("Queso fresco", 40)]),
    "Pollo con arroz": ("Pechuga de pollo a la plancha con arroz blanco cocido.", 1,
                        [("Pechuga de pollo cocinada", 120), ("Arroz blanco cocido", 150)]),
    "Pasta con tomate y atún": ("Pasta cocida con salsa de tomate y atún.", 1,
                                [("Pasta cocida", 180), ("Salsa de tomate casera", 60),
                                 ("Atún al natural escurrido", 70), ("Aceite de oliva virgen extra", 5)]),
    "Lentejas estofadas caseras": ("Lentejas con zanahoria, cebolla y patata.", 1,
                                   [("Lentejas cocidas", 180), ("Zanahoria", 40), ("Cebolla", 30),
                                    ("Patata cocida", 60), ("Aceite de oliva virgen extra", 5)]),
    "Arroz con pollo y verduras": ("Arroz con pollo, zanahoria y cebolla.", 1,
                                   [("Arroz blanco cocido", 150), ("Pechuga de pollo cocinada", 100),
                                    ("Zanahoria", 40), ("Cebolla", 30), ("Aceite de oliva virgen extra", 5)]),
    "Patata cocida con huevo y atún": ("Patata cocida con huevo, atún y aceite de oliva.", 1,
                                       [("Patata cocida", 150), ("Huevo entero", 60), ("Atún al natural escurrido", 60),
                                        ("Aceite de oliva virgen extra", 5)]),
    "Garbanzos con espinacas": ("Garbanzos guisados con espinacas y tomate.", 1,
                                [("Garbanzos cocidos", 150), ("Espinacas", 80), ("Tomate", 40),
                                 ("Cebolla", 20), ("Aceite de oliva virgen extra", 5)]),
    "Porridge de avena con leche y plátano": ("Gachas de avena con leche entera y plátano.", 1,
                                              [("Copos de avena", 40), ("Leche entera", 150), ("Plátano", 60)]),
    "Yogur griego con fresas y avena": ("Yogur griego natural con fresas y avena.", 1,
                                       [("Yogur griego natural", 150), ("Fresas", 80), ("Copos de avena", 20)]),
    "Batido de plátano y leche": ("Batido casero de plátano con leche entera.", 1,
                                  [("Plátano", 100), ("Leche entera", 200)]),
    "Crema de verduras casera": ("Crema de zanahoria, patata, cebolla y espinacas.", 1,
                                 [("Zanahoria", 80), ("Patata cocida", 100), ("Cebolla", 30),
                                  ("Espinacas", 30), ("Aceite de oliva virgen extra", 5)]),

    "Arroz integral con pollo y brócoli": ("Arroz integral con pechuga de pollo y brócoli.", 1,
        [("Arroz integral cocido", 160), ("Pechuga de pollo cocinada", 120), ("Brócoli", 100), ("Aceite de oliva virgen extra", 5)]),
    "Salmón con boniato y verduras": ("Lomo de salmón con boniato asado y calabacín.", 1,
        [("Salmón cocinado", 140), ("Boniato asado", 160), ("Calabacín", 100), ("Aceite de oliva virgen extra", 5)]),
    "Merluza con patata y judías verdes": ("Merluza al horno con patata y judías verdes.", 1,
        [("Merluza cocinada", 160), ("Patata cocida", 160), ("Judías verdes", 100), ("Aceite de oliva virgen extra", 5)]),
    "Bowl de quinoa con garbanzos": ("Quinoa con garbanzos, pepino, tomate y salsa de yogur.", 1,
        [("Quinoa cocida", 120), ("Garbanzos cocidos", 100), ("Pepino", 50), ("Tomate", 60), ("Yogur natural", 40)]),
    "Ensalada de tomate y mozzarella": ("Tomate fresco con mozzarella y aceite de oliva.", 1,
        [("Tomate", 150), ("Mozzarella", 80), ("Aceite de oliva virgen extra", 5)]),
    "Ensalada de alubias blancas": ("Alubias blancas con pimiento, cebolla y tomate.", 1,
        [("Alubias blancas cocidas", 150), ("Pimiento rojo", 50), ("Cebolla", 20), ("Tomate", 60), ("Aceite de oliva virgen extra", 5)]),
    "Pasta integral con atún y tomate": ("Pasta integral con atún al natural y salsa de tomate casera.", 1,
        [("Pasta integral cocida", 180), ("Atún al natural escurrido", 70), ("Salsa de tomate casera", 60)]),
    "Tofu salteado con arroz integral": ("Tofu firme con arroz integral y verduras salteadas.", 1,
        [("Tofu firme", 120), ("Arroz integral cocido", 140), ("Calabacín", 60), ("Pimiento rojo", 40), ("Aceite de oliva virgen extra", 5)]),
    "Tacos de pollo con aguacate": ("Pollo con aguacate, tomate y hojas de lechuga.", 1,
        [("Pechuga de pollo cocinada", 120), ("Aguacate", 35), ("Tomate", 40), ("Lechuga", 20)]),
    "Tostada integral de aguacate y huevo": ("Pan integral con aguacate y huevo cocido.", 1,
        [("Pan integral", 50), ("Aguacate", 40), ("Huevo entero", 60)]),
    "Avena nocturna con chía y frutos rojos": ("Copos de avena hidratados con leche, chía y frutos rojos.", 1,
        [("Copos de avena", 40), ("Leche semidesnatada", 120), ("Semillas de chía", 8), ("Arándanos", 40), ("Frambuesas", 40)]),
    "Bol de skyr con plátano y nueces": ("Skyr natural con plátano y nueces.", 1,
        [("Skyr natural", 170), ("Plátano", 60), ("Nueces", 10)]),
    "Ternera con verduras y arroz": ("Ternera magra salteada con pimiento, calabacín y arroz.", 1,
        [("Ternera magra cocinada", 120), ("Arroz blanco cocido", 130), ("Pimiento rojo", 50), ("Calabacín", 50), ("Aceite de oliva virgen extra", 5)]),
    "Tortilla de espinacas y champiñones": ("Tortilla de huevo con espinacas y champiñones.", 1,
        [("Huevo entero", 120), ("Espinacas", 50), ("Champiñones", 50), ("Aceite de oliva virgen extra", 5)]),
    "Bacalao con boniato y espárragos": ("Bacalao cocinado con boniato asado y espárragos.", 1,
        [("Bacalao cocinado", 150), ("Boniato asado", 130), ("Espárragos", 100), ("Aceite de oliva virgen extra", 5)]),
    "Batido de kéfir y frutos rojos": ("Kéfir natural con arándanos y fresas.", 1,
        [("Kéfir natural", 200), ("Arándanos", 50), ("Fresas", 50)]),
    "Bocadillo de ternera y pimiento": ("Pan de barra con ternera magra y pimiento asado.", 1,
        [("Pan de barra", 90), ("Ternera magra cocinada", 80), ("Pimiento rojo", 30)]),
    "Tortitas de avena y plátano": ("Tortitas caseras de avena, plátano y huevo.", 1,
        [("Harina de avena", 40), ("Plátano", 60), ("Huevo entero", 60), ("Leche semidesnatada", 30)]),
    "Tostada de queso fresco y tomate": ("Pan integral con queso fresco y tomate.", 1,
        [("Pan integral", 50), ("Queso fresco", 50), ("Tomate", 40)]),
    "Porridge de cacao y plátano": ("Gachas de avena con leche, cacao puro y plátano.", 1,
        [("Copos de avena", 40), ("Leche semidesnatada", 160), ("Cacao puro en polvo", 5), ("Plátano", 50)]),
    "Pisto con huevo": ("Pisto casero de verduras con huevo.", 1,
        [("Calabacín", 80), ("Berenjena", 60), ("Pimiento rojo", 50), ("Cebolla", 30), ("Tomate triturado natural", 80), ("Huevo entero", 60), ("Aceite de oliva virgen extra", 5)]),
    "Fajitas de pollo y verduras": ("Tortilla de trigo rellena de pollo, pimiento y cebolla.", 1,
        [("Tortilla de trigo", 40), ("Pechuga de pollo cocinada", 100), ("Pimiento rojo", 40), ("Cebolla", 20), ("Aguacate", 20)]),
    "Cuscús con pavo y verduras": ("Cuscús con pavo cocinado, calabacín y zanahoria.", 1,
        [("Cuscús cocido", 150), ("Pechuga de pavo cocinada", 110), ("Calabacín", 60), ("Zanahoria", 40), ("Aceite de oliva virgen extra", 5)]),
    "Ensalada mediterránea de garbanzos": ("Garbanzos con tomate, pepino, rúcula y feta.", 1,
        [("Garbanzos cocidos", 130), ("Tomate", 60), ("Pepino", 40), ("Rúcula", 20), ("Queso feta", 25), ("Aceite de oliva virgen extra", 5)]),
    "Ensalada de arroz integral y atún": ("Arroz integral con atún, maíz, tomate y pepino.", 1,
        [("Arroz integral cocido", 140), ("Atún al natural escurrido", 70), ("Maíz dulce cocido", 30), ("Tomate", 40), ("Pepino", 30)]),
    "Bowl de tofu y edamame": ("Bowl vegetal de tofu, edamame, arroz integral y verduras.", 1,
        [("Tofu firme", 90), ("Edamame cocido", 60), ("Arroz integral cocido", 100), ("Zanahoria", 30), ("Pepino", 30)]),
    "Lentejas con boniato y verduras": ("Guiso de lentejas con boniato, zanahoria y espinacas.", 1,
        [("Lentejas cocidas", 150), ("Boniato asado", 80), ("Zanahoria", 40), ("Espinacas", 30), ("Cebolla", 20), ("Aceite de oliva virgen extra", 5)]),
    "Patata rellena de atún": ("Patata cocida rellena de atún y yogur natural.", 1,
        [("Patata cocida", 180), ("Atún al natural escurrido", 70), ("Yogur natural", 30), ("Cebolla", 10)]),
    "Crema de calabacín casera": ("Crema de calabacín, patata, cebolla y leche.", 1,
        [("Calabacín", 140), ("Patata cocida", 80), ("Cebolla", 25), ("Leche semidesnatada", 50), ("Aceite de oliva virgen extra", 5)]),
    "Salmón con arroz y espárragos": ("Salmón cocinado con arroz y espárragos.", 1,
        [("Salmón cocinado", 130), ("Arroz blanco cocido", 120), ("Espárragos", 80), ("Aceite de oliva virgen extra", 5)]),
    "Tortilla de claras y espinacas": ("Tortilla ligera de claras con huevo entero y espinacas.", 1,
        [("Claras de huevo", 100), ("Huevo entero", 30), ("Espinacas", 50), ("Champiñones", 30), ("Aceite de oliva virgen extra", 3)]),
    "Bocadillo integral de atún": ("Pan integral con atún, tomate y un poco de aceite.", 1,
        [("Pan integral", 80), ("Atún al natural escurrido", 70), ("Tomate", 30), ("Aceite de oliva virgen extra", 4)]),
    "Salteado de soja texturizada": ("Soja texturizada hidratada con verduras y arroz.", 1,
        [("Soja texturizada hidratada", 120), ("Arroz blanco cocido", 100), ("Pimiento rojo", 40), ("Calabacín", 40), ("Salsa de soja", 5)]),
    "Tostada de crema de cacahuete y plátano": ("Pan integral con crema de cacahuete y plátano.", 1,
        [("Pan integral", 45), ("Crema de cacahuete 100%", 15), ("Plátano", 50)]),

}


# Secciones visibles del catálogo. Las preparaciones compuestas viven en RECIPES, nunca en FOODS.
FOOD_CATALOG_SECTIONS: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    ("produce", "Frutas y verduras", "Fruta fresca, hortalizas y verduras", "🥦", (
        "Tomate", "Lechuga", "Pepino", "Cebolla", "Zanahoria", "Aguacate", "Manzana", "Naranja", "Fresas", "Plátano",
        "Espinacas", "Champiñones", "Brócoli", "Coliflor", "Calabacín", "Pimiento rojo", "Espárragos", "Judías verdes",
        "Berenjena", "Calabaza", "Remolacha cocida", "Apio", "Col lombarda", "Pera", "Kiwi", "Piña", "Arándanos",
        "Frambuesas", "Uvas", "Sandía", "Mango", "Melocotón", "Mandarina", "Rúcula", "Col rizada (kale)",
        "Coles de Bruselas", "Ajo", "Papaya", "Ciruela", "Cerezas", "Pomelo",
    )),
    ("cereals", "Cereales, pan y tubérculos", "Pan, arroz, pasta, avena, cereales y patata", "🌾", (
        "Pan de molde", "Pan integral", "Pan de barra", "Arroz blanco cocido", "Pasta cocida", "Patata cocida",
        "Copos de avena", "Arroz integral cocido", "Pasta integral cocida", "Cuscús cocido", "Bulgur cocido",
        "Avena cocida", "Pan de centeno", "Tortita de maíz", "Boniato asado", "Pan de pita integral",
        "Tortilla de trigo", "Harina de avena", "Maíz dulce cocido", "Quinoa cocida",
    )),
    ("protein", "Carnes, pescados y huevos", "Fuentes de proteína animal y huevos", "🍳", (
        "Huevo entero", "Claras de huevo", "Atún al natural escurrido", "Pechuga de pollo cocinada", "Pavo cocinado",
        "Pavo fiambre", "Jamón cocido", "Pechuga de pavo cocinada", "Salmón cocinado", "Merluza cocinada",
        "Bacalao cocinado", "Sardinas en conserva escurridas", "Gambas cocidas", "Ternera magra cocinada",
        "Lomo de cerdo cocinado", "Atún fresco cocinado", "Caballa cocinada",
    )),
    ("plant", "Legumbres y proteínas vegetales", "Legumbres, tofu, soja y alternativas vegetales", "🫘", (
        "Garbanzos cocidos", "Lentejas cocidas", "Guisantes cocidos", "Alubias blancas cocidas", "Alubias rojas cocidas",
        "Tofu firme", "Tempeh", "Edamame cocido", "Seitán", "Soja texturizada hidratada", "Hummus",
    )),
    ("dairy", "Lácteos y bebidas vegetales", "Leche, yogures, quesos y bebidas vegetales", "🥛", (
        "Leche entera", "Leche semidesnatada", "Leche desnatada", "Yogur natural", "Yogur griego natural",
        "Queso fresco batido 0%", "Queso fresco", "Queso cottage", "Mozzarella", "Queso feta", "Skyr natural",
        "Kéfir natural", "Bebida de soja sin azúcar", "Leche semidesnatada sin lactosa",
        "Bebida de avena sin azúcar", "Bebida de almendras sin azúcar", "Yogur natural desnatado", "Requesón", "Ricotta",
    )),
    ("nuts", "Frutos secos y semillas", "Frutos secos, semillas y cremas", "🥜", (
        "Almendras", "Nueces", "Cacahuetes", "Crema de cacahuete 100%", "Semillas de chía",
        "Semillas de calabaza", "Tahini",
    )),
    ("beverages", "Bebidas", "Café solo y café con leche preparado en casa", "☕", (
        "Café (infusión, sin azúcar)", "Café con leche (leche entera)",
        "Café con leche (leche semidesnatada)", "Café con leche (leche desnatada)",
    )),
    ("pantry", "Aceites, salsas y otros", "Aceites, salsas, cacao y otros básicos", "🫒", (
        "Aceite de oliva virgen extra", "Salsa de tomate casera", "Tomate triturado natural",
        "Miel", "Chocolate negro 85%", "Cacao puro en polvo", "Dátiles", "Salsa de soja",
    )),
)
FOOD_SECTION_BY_NAME = {name: section_id for section_id, _, _, _, names in FOOD_CATALOG_SECTIONS for name in names}


def list_food_catalog_sections(db: Session) -> list[dict]:
    """Devuelve el catálogo genérico organizado por secciones, listo para navegar desde la app."""
    foods = list(db.scalars(
        select(Food).where(Food.user_id.is_(None), Food.source == "catalog").order_by(Food.name)
    ))
    by_id: dict[str, list[Food]] = {section_id: [] for section_id, *_ in FOOD_CATALOG_SECTIONS}
    for food in foods:
        by_id.setdefault(FOOD_SECTION_BY_NAME.get(food.name, "pantry"), []).append(food)
    return [{
        "id": section_id, "title": title, "description": description, "icon": icon,
        "count": len(by_id.get(section_id, [])), "foods": by_id.get(section_id, []),
    } for section_id, title, description, icon, _ in FOOD_CATALOG_SECTIONS if by_id.get(section_id)]


# Cada alimento obtiene un icono concreto cuando es reconocible y, en el resto,
# hereda el icono de su sección. Así el catálogo nunca muestra elementos sin icono.
FOOD_ICON_BY_NAME = {
    "Café (infusión, sin azúcar)": "☕",
    "Café con leche (leche entera)": "☕",
    "Café con leche (leche semidesnatada)": "☕",
    "Café con leche (leche desnatada)": "☕",
    "Leche entera": "🥛", "Leche semidesnatada": "🥛", "Leche desnatada": "🥛",
    "Bebida de soja sin azúcar": "🥛", "Bebida de avena sin azúcar": "🥛", "Bebida de almendras sin azúcar": "🥛",
    "Tomate": "🍅", "Tomate triturado natural": "🍅", "Zanahoria": "🥕", "Manzana": "🍎",
    "Naranja": "🍊", "Plátano": "🍌", "Fresas": "🍓", "Aguacate": "🥑", "Brócoli": "🥦",
    "Pepino": "🥒", "Cebolla": "🧅", "Ajo": "🧄", "Champiñones": "🍄", "Patata cocida": "🥔",
    "Boniato asado": "🍠", "Uvas": "🍇", "Sandía": "🍉", "Piña": "🍍", "Mango": "🥭",
    "Limón": "🍋", "Pera": "🍐", "Kiwi": "🥝", "Cerezas": "🍒", "Pan de molde": "🍞",
    "Pan integral": "🍞", "Pan de barra": "🥖", "Pan de centeno": "🍞", "Pan de pita integral": "🫓",
    "Huevo entero": "🥚", "Claras de huevo": "🥚", "Pechuga de pollo cocinada": "🍗",
    "Pavo cocinado": "🍗", "Pechuga de pavo cocinada": "🍗", "Ternera magra cocinada": "🥩",
    "Lomo de cerdo cocinado": "🥩", "Salmón cocinado": "🐟", "Merluza cocinada": "🐟",
    "Bacalao cocinado": "🐟", "Atún fresco cocinado": "🐟", "Atún al natural escurrido": "🐟",
    "Caballa cocinada": "🐟", "Gambas cocidas": "🦐", "Sardinas en conserva escurridas": "🐟",
    "Tofu firme": "🧈", "Tempeh": "🫘", "Edamame cocido": "🫛", "Garbanzos cocidos": "🫘",
    "Lentejas cocidas": "🫘", "Alubias blancas cocidas": "🫘", "Alubias rojas cocidas": "🫘",
    "Hummus": "🧆", "Arroz blanco cocido": "🍚", "Arroz integral cocido": "🍚",
    "Quinoa cocida": "🌾", "Pasta cocida": "🍝", "Pasta integral cocida": "🍝",
    "Copos de avena": "🥣", "Harina de avena": "🌾", "Yogur natural": "🥣",
    "Yogur griego natural": "🥣", "Kéfir natural": "🥛", "Skyr natural": "🥣",
    "Queso fresco": "🧀", "Queso cottage": "🧀", "Mozzarella": "🧀", "Queso feta": "🧀",
    "Almendras": "🌰", "Nueces": "🌰", "Cacahuetes": "🥜", "Semillas de chía": "🌱",
    "Semillas de calabaza": "🌱", "Crema de cacahuete 100%": "🥜",
    "Aceite de oliva virgen extra": "🫒", "Miel": "🍯", "Chocolate negro 85%": "🍫",
}


def food_icon(name: str) -> str:
    """Icono de alimento con fallback de la familia del catálogo; nunca devuelve cadena vacía."""
    exact = FOOD_ICON_BY_NAME.get(name)
    if exact:
        return exact
    section_id = FOOD_SECTION_BY_NAME.get(name, "pantry")
    return next((icon for key, _, _, icon, _ in FOOD_CATALOG_SECTIONS if key == section_id), "🥗")


def recipe_preparation_steps(name: str) -> list[str]:
    """Instrucciones iniciales orientativas para recetas del sistema sin pasos previos."""
    if name == "Pisto con huevo":
        return [
            "Lava y corta el calabacín, la berenjena y el pimiento en dados pequeños. Pica la cebolla y prepara el tomate.",
            "Calienta el aceite en una sartén amplia. Pocha la cebolla y el pimiento a fuego medio durante 6–8 minutos.",
            "Añade la berenjena y el calabacín. Cocina 8–10 minutos, removiendo para que las verduras se ablanden.",
            "Incorpora el tomate triturado y una pizca de sal. Cocina a fuego suave 15–20 minutos, hasta que el pisto quede meloso.",
            "Cocina el huevo a la plancha o escalfado y sírvelo encima del pisto caliente.",
        ]
    if name.startswith(("Ensalada", "Bowl")):
        return ["Lava y prepara las verduras. Escurre y enjuaga las legumbres o conservas si las lleva.",
                "Cuece los cereales o huevos indicados y deja que se templen.",
                "Mezcla los ingredientes en un bol, añade el aliño y sirve."]
    if name.startswith(("Tostada", "Bocadillo")):
        return ["Prepara y corta los ingredientes del relleno.",
                "Tuesta el pan si corresponde y distribuye los ingredientes de forma uniforme.",
                "Añade el aliño o condimento indicado y sirve recién preparado."]
    if name.startswith(("Tortilla", "Huevos")):
        return ["Bate los huevos o claras y prepara el resto de ingredientes.",
                "Cocina las verduras o el relleno en una sartén con el aceite indicado.",
                "Añade el huevo y cocina a fuego medio hasta que cuaje. Sirve caliente."]
    if "café con leche" in name.lower():
        return ["Prepara el café y calienta la leche sin dejar que hierva.",
                "Vierte la leche en la taza y añade el café al gusto. Sirve."]
    if name.startswith(("Porridge", "Avena nocturna", "Bol de skyr", "Yogur")):
        return ["Pesa los ingredientes y prepara la fruta o los acompañamientos.",
                "Mezcla la avena o el yogur con la leche o base indicada.",
                "Añade la fruta y los toppings. Sirve o deja reposar en frío según la preparación."]
    if name.startswith(("Pasta", "Arroz", "Cuscús", "Lentejas", "Garbanzos", "Patata")):
        return ["Prepara los ingredientes: lava, corta y escurre lo necesario.",
                "Cuece el arroz, la pasta, las legumbres o la patata según corresponda.",
                "Cocina la proteína y las verduras con el aceite indicado.",
                "Mezcla todos los ingredientes, ajusta el punto de sal y sirve."]
    if name.startswith(("Crema", "Pisto")):
        return ["Lava, pela si hace falta y trocea las verduras.",
                "Cocina las verduras en una cazuela con el aceite y el líquido indicados hasta que estén tiernas.",
                "Tritura hasta conseguir la textura deseada y sirve."]
    if name.startswith(("Batido",)):
        return ["Prepara y trocea la fruta.",
                "Añade todos los ingredientes al vaso de la batidora.",
                "Tritura hasta obtener una mezcla homogénea y sirve frío."]
    return ["Prepara y pesa todos los ingredientes.",
            "Cocina los ingredientes que lo requieran con el método adecuado y las cantidades indicadas.",
            "Combina la preparación, ajusta el punto y reparte en las raciones indicadas."]


def slug(text: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def seed_food_catalog(db: Session) -> int:
    """Inserta lo que falte (alimentos, raciones y recetas del sistema). Devuelve cuántos alimentos añadió."""
    from .recipes import sync_recipe_food
    existing = {f.external_id: f for f in db.scalars(select(Food).where(Food.user_id.is_(None), Food.source == "catalog"))}
    added = 0
    for name, (kcal, p, c, sug, fat, sat, fib, sod, servings) in FOODS.items():
        key = f"smartfit:{slug(name)}"
        food = existing.get(key)
        if food is None:
            food = Food(user_id=None, name=name, source="catalog", external_id=key, kcal=kcal, protein_g=p, carbs_g=c, sugars_g=sug,
                        fat_g=fat, sat_fat_g=sat, fiber_g=fib, sodium_mg=sod, confidence="medium", license="CC0", attribution=ATTRIBUTION)
            db.add(food)
            db.flush()
            added += 1
        have = {s.unit_name for s in db.scalars(select(FoodServing).where(FoodServing.food_id == food.id))}
        for unit, plural, grams, desc in servings:
            if unit not in have:
                db.add(FoodServing(food_id=food.id, unit_name=unit, unit_name_plural=plural, grams_per_unit=grams, description=desc))
    db.commit()
    by_name = {f.name: f for f in db.scalars(select(Food).where(Food.user_id.is_(None), Food.source == "catalog"))}
    have_recipes = {r.name for r in db.scalars(select(Recipe).where(Recipe.user_id.is_(None)))}
    for name, (desc, servings, ings) in RECIPES.items():
        if name in have_recipes:
            continue
        r = Recipe(user_id=None, name=name, description=desc, serving_count=servings, steps=recipe_preparation_steps(name))
        r.ingredients = [RecipeIngredient(food_id=by_name[n].id, quantity_g=g) for n, g in ings]
        db.add(r)
        db.flush()
        sync_recipe_food(db, r)
    for recipe in db.scalars(select(Recipe).where(Recipe.user_id.is_(None))):
        if not recipe.steps:
            recipe.steps = recipe_preparation_steps(recipe.name)
    db.commit()
    if added:
        log.info("Catálogo de alimentos: %s añadidos", added)
    return added
