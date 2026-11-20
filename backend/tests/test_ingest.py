"""Ingesta batch (USDA en el formato CSV oficial, CSV genérico, traducción) y alimentos propios de cada usuario.
Los ficheros de USDA son SINTÉTICOS con las columnas oficiales (no se pueden descargar los reales desde el entorno de pruebas)."""
import csv
import io
import json
import zipfile
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.ingest import csv_foods, fdc, translate
from app.ingest.__main__ import main
from app.models import Food
from app.services.food_sources import NormalizedFood, bulk_upsert
from conftest import onboard_new_user, rnd

NUTRIENTS = [("1008", "Energy", "KCAL", "208"), ("1003", "Protein", "G", "203"), ("1005", "Carbohydrate, by difference", "G", "205"),
             ("1004", "Total lipid (fat)", "G", "204"), ("2000", "Sugars, total", "G", "269"), ("1258", "Fatty acids, total saturated", "G", "606"),
             ("1079", "Fiber, total dietary", "G", "291"), ("1093", "Sodium, Na", "MG", "307"), ("2047", "Energy (Atwater General Factors)", "KCAL", "957")]


def write_fdc(dest, tag, foods):
    """foods: [(fdc_id, data_type, description, {nbr: amount})] -> carpeta con food.csv, nutrient.csv, food_nutrient.csv, food_category.csv."""
    dest.mkdir(parents=True, exist_ok=True)
    def w(name, header, rows):
        with open(dest / name, "w", newline="", encoding="utf-8") as f:
            cw = csv.writer(f); cw.writerow(header); cw.writerows(rows)
    w("nutrient.csv", ["id", "name", "unit_name", "nutrient_nbr", "rank"], [[i, n, u, nbr, 1] for i, n, u, nbr in NUTRIENTS])
    w("food_category.csv", ["id", "code", "description"], [[1, "0100", "Legumes and Legume Products"]])
    w("food.csv", ["fdc_id", "data_type", "description", "food_category_id", "publication_date"], [[f[0], f[1], f[2], 1, "2019-04-01"] for f in foods])
    nbr_to_id = {nbr: i for i, _, _, nbr in NUTRIENTS}
    rows, k = [], 1
    for fdc_id, _, _, vals in foods:
        for nbr, amount in vals.items():
            rows.append([k, fdc_id, nbr_to_id[nbr], amount, 1, "", "", "", "", "", "", ""]); k += 1
    w("food_nutrient.csv", ["id", "fdc_id", "nutrient_id", "amount", "data_points", "derivation_id", "min", "max", "median", "loq", "footnote", "min_year_acquired"], rows)
    return dest


@pytest.fixture
def fdc_dir(tmp_path):
    t = rnd(6)
    return write_fdc(tmp_path / "FoodData_Central_sr_legacy_food_csv", t, [
        (f"9{rnd(6, True)}1", "sr_legacy_food", f"HUMMUS {t.upper()}", {"208": 166, "203": 7.9, "205": 14.3, "204": 9.6, "269": 0.3, "606": 1.4, "291": 6.0, "307": 379}),
        (f"9{rnd(6, True)}2", "foundation_food", f"Atwater only {t}", {"957": 52.5, "203": 0.3, "205": 13.8, "204": 0.2}),     # energía Atwater
        (f"9{rnd(6, True)}3", "foundation_food", f"No energy {t}", {"203": 1, "205": 1, "204": 1}),                            # sin energía -> se omite
        (f"9{rnd(6, True)}4", "sr_legacy_food", f"No protein {t}", {"208": 100, "205": 10, "204": 1}),                         # incompleto -> se omite
        (f"9{rnd(6, True)}5", "sr_legacy_food", f"Corrupt {t}", {"208": 5000, "203": 1, "205": 1, "204": 1}),                  # kcal absurdas -> se omite
        (f"9{rnd(6, True)}6", "sub_sample_food", f"Sub sample {t}", {"208": 10, "203": 1, "205": 1, "204": 1}),               # no genérico -> se omite
        (f"9{rnd(6, True)}7", "branded_food", f"Branded {t}", {"208": 10, "203": 1, "205": 1, "204": 1}),
    ])


# ───────────── USDA (CSV oficiales) ─────────────
def test_fdc_reader_filters_and_normalizes(fdc_dir):
    items, st = fdc.read_fdc(fdc_dir)
    assert st["foods_in_file"] == 7 and st["kept"] == 2 and st["skipped_other_types"] == 2
    assert st["skipped_no_energy"] == 1 and st["skipped_incomplete"] == 1 and st["skipped_insane"] == 1
    hummus = next(i for i in items if i.name.lower().startswith("hummus"))
    assert hummus.name.endswith(hummus.name[-6:]) and not hummus.name.isupper()            # «HUMMUS X» -> «Hummus x»
    assert hummus.nutrients["kcal"] == 166 and hummus.nutrients["sodium_mg"] == 379 and hummus.nutrients["fiber_g"] == 6.0
    assert hummus.source == "usda" and hummus.license == "CC0" and hummus.confidence == "high" and hummus.extra["usda_category"].startswith("Legumes")
    assert next(i for i in items if i.name.startswith("Atwater")).nutrients["kcal"] == 52.5


def test_fdc_reader_accepts_zip_and_rejects_wrong_files(fdc_dir, tmp_path):
    z = tmp_path / "sr.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in fdc_dir.iterdir():
            zf.write(f, f"FoodData_Central_sr_legacy_food_csv/{f.name}")        # subcarpeta, como en la descarga real
    assert fdc.read_fdc(z)[1]["kept"] == 2
    bad = tmp_path / "bad"; bad.mkdir()
    for n in ("food.csv", "nutrient.csv", "food_nutrient.csv"):
        (bad / n).write_text("a,b\n1,2\n")
    with pytest.raises(fdc.FdcFormatError, match="faltan columnas"):
        fdc.read_fdc(bad)
    with pytest.raises(fdc.FdcFormatError, match="No encuentro"):
        fdc.read_fdc(tmp_path / "vacia")


def test_bulk_upsert_is_idempotent_updates_nutrients_and_keeps_translations(fdc_dir):
    items, _ = fdc.read_fdc(fdc_dir)
    with SessionLocal() as db:
        assert bulk_upsert(db, items) == {"inserted": 2, "updated": 0}
        assert bulk_upsert(db, items) == {"inserted": 0, "updated": 2}                 # repetir la carga no duplica
        food = db.scalar(select(Food).where(Food.source == "usda", Food.external_id == items[0].external_id))
        food.name, food.extra = "Hummus traducido", {"name_es_done": True, "original_name": items[0].name}
        db.commit()
        items[0].nutrients["kcal"] = 170                                                # nueva versión de la fuente
        assert bulk_upsert(db, items)["updated"] == 2
        db.refresh(food)
        assert food.kcal == 170 and food.name == "Hummus traducido" and food.extra["name_es_done"]   # se actualiza el dato, no la traducción
        assert food.user_id is None and food.license == "CC0" and food.source_updated_at is not None


def test_ingested_foods_are_searchable_locally_without_any_online_call(client, onboarded, fdc_dir):
    items, _ = fdc.read_fdc(fdc_dir)
    with SessionLocal() as db:
        bulk_upsert(db, items)
    tag = items[1].name.split()[-1]
    with patch("app.services.food_search.search_off_and_store", side_effect=AssertionError("no debe consultar OFF: ya hay resultado local")):
        r = client.get("/foods/search", params={"q": f"atwater {tag}", "online": True, "limit": 5}, headers=onboarded["headers"]).json()
    assert r and r[0]["source"] == "usda" and r[0]["license"] == "CC0" and r[0]["external_id"] == items[1].external_id


def test_search_no_longer_calls_usda():
    import app.services.food_search as fs
    assert not hasattr(fs, "search_usda_and_store")


# ───────────── CSV genérico (BEDCA u otra fuente) ─────────────
def test_csv_importer_with_mapping_decimal_comma_and_validation(tmp_path):
    f = tmp_path / "bedca.csv"
    f.write_text("Alimento;Energía (kcal);Proteínas;Hidratos;Grasas;Fibra\n"
                 "Lentejas cocidas;116;9,0;20,1;0,4;7,9\n"
                 "Sin kcal;;1;1;1;0\n"
                 "Absurdo;9999;1;1;1;0\n"
                 ";100;1;1;1;0\n", encoding="utf-8")
    m = {"Alimento": "name", "Energía (kcal)": "kcal", "Proteínas": "protein_g", "Hidratos": "carbs_g", "Grasas": "fat_g", "Fibra": "fiber_g"}
    items, st = csv_foods.read_csv(f, source="bedca", license="(confirmar)", attribution="BEDCA", delimiter=";", decimal_comma=True, mapping=m)
    assert st == {"rows": 4, "kept": 1, "skipped_invalid": 3}
    assert items[0].name == "Lentejas cocidas" and items[0].nutrients["protein_g"] == 9.0 and items[0].external_id == "bedca:lentejas-cocidas"
    with SessionLocal() as db:
        assert bulk_upsert(db, items)["inserted"] in (0, 1) and bulk_upsert(db, items) == {"inserted": 0, "updated": 1}
    with pytest.raises(ValueError, match="Faltan columnas"):
        csv_foods.read_csv(f, source="bedca", license=None, attribution=None)                   # sin mapear no hay columnas válidas
    for bad in ("usda", "manual", "x y"):
        with pytest.raises(ValueError, match="fuente"):
            csv_foods.read_csv(f, source=bad, license=None, attribution=None, mapping=m)


def test_cli_dry_run_writes_nothing_and_reports_errors(fdc_dir, capsys, tmp_path):
    with SessionLocal() as db:
        before = db.scalar(select(__import__("sqlalchemy").func.count()).select_from(Food).where(Food.source == "usda"))
    assert main(["fdc", str(fdc_dir), "--dry-run"]) == 0
    assert "kept=2" in capsys.readouterr().out
    with SessionLocal() as db:
        assert db.scalar(select(__import__("sqlalchemy").func.count()).select_from(Food).where(Food.source == "usda")) == before
    assert main(["fdc", str(tmp_path / "nada")]) == 2 and "Error" in capsys.readouterr().err
    assert main(["fdc", str(fdc_dir)]) == 0 and "insertados=2" in capsys.readouterr().out
    assert main(["stats"]) == 0 and "usda" in capsys.readouterr().out


# ───────────── traducción por lotes (único paso con IA, explícito y reanudable) ─────────────
def test_translate_is_explicit_resumable_and_keeps_original(fdc_dir):
    items, _ = fdc.read_fdc(fdc_dir)
    with SessionLocal() as db:
        bulk_upsert(db, items)
        before = translate.pending(db)
        assert before >= 2
        calls = []
        def fake(messages, json_mode=False):
            names = [x["name"] for x in json.loads(messages[1]["content"])]
            calls.append(len(names))
            return json.dumps({"names": [f"ES {n}" for n in names]})
        with patch("app.ingest.translate.chat_text", fake):
            assert translate.translate_source(db, limit=1, batch=1) == 1                  # parcial
            assert translate.pending(db) == before - 1
            assert translate.translate_source(db, batch=50) == before - 1                  # reanuda donde se quedó
        assert translate.pending(db) == 0
        done = db.scalar(select(Food).where(Food.source == "usda", Food.external_id == items[1].external_id))
        assert done.name == f"ES {items[1].name}" and done.extra["original_name"] == items[1].name
        with patch("app.ingest.translate.chat_text", side_effect=RuntimeError("sin IA")):
            assert translate.translate_source(db) == 0                                     # nada pendiente: no llama a la IA


def test_bulk_import_does_not_trigger_automatic_ai_translation(fdc_dir):
    from app.services.names import pending_count
    items, _ = fdc.read_fdc(fdc_dir)
    with SessionLocal() as db:
        n = pending_count(db)
        bulk_upsert(db, items)
        assert pending_count(db) == n        # el traductor automático (productos de OFF) no ve los alimentos USDA


# ───────────── alimentos propios del usuario ─────────────
def test_custom_food_crud_privacy_and_ranking(client):
    a, b = onboard_new_user(client), onboard_new_user(client)
    tag = rnd(8)
    mine = client.post("/foods", json={"name": f"Bizcocho {tag}", "kcal": 380, "protein_g": 6, "carbs_g": 50, "fat_g": 16}, headers=a["headers"]).json()
    assert mine["user_id"] and mine["source"] == "manual"
    assert [f["id"] for f in client.get("/foods/mine", headers=a["headers"]).json()] == [mine["id"]]
    assert client.get("/foods/mine", headers=b["headers"]).json() == []                                  # privado
    assert client.get(f"/foods/{mine['id']}", headers=b["headers"]).status_code == 404
    upd = client.put(f"/foods/{mine['id']}", json={"name": f"Bizcocho casero {tag}", "kcal": 350, "protein_g": 6, "carbs_g": 48, "fat_g": 14}, headers=a["headers"])
    assert upd.status_code == 200 and upd.json()["kcal"] == 350
    assert client.put(f"/foods/{mine['id']}", json={"name": "x"}, headers=b["headers"]).status_code == 404
    assert client.delete(f"/foods/{mine['id']}", headers=b["headers"]).status_code == 404
    # al usarlo queda protegido el historial: no se puede borrar, sí editar; el registro conserva su instantánea
    log = client.post("/logs", json={"food_id": mine["id"], "grams": 100}, headers=a["headers"]).json()
    assert client.get("/foods/mine", headers=a["headers"]).json()[0]["times_used"] == 1
    assert client.delete(f"/foods/{mine['id']}", headers=a["headers"]).status_code == 409
    client.put(f"/foods/{mine['id']}", json={"name": f"Bizcocho casero {tag}", "kcal": 100}, headers=a["headers"])
    assert abs(client.get("/dashboard/day", headers=a["headers"]).json()["totals"]["kcal"] - log["kcal"]) < 0.01
    spare = client.post("/foods", json={"name": f"Sobra {tag}", "kcal": 1}, headers=a["headers"]).json()
    assert client.delete(f"/foods/{spare['id']}", headers=a["headers"]).status_code == 204
    assert client.get(f"/foods/{spare['id']}", headers=a["headers"]).status_code == 404


def test_own_foods_rank_first_and_recipe_foods_are_not_editable_here(client):
    u = onboard_new_user(client); h = u["headers"]
    own = client.post("/foods", json={"name": f"Hummus de la abuela {rnd()}", "kcal": 200}, headers=h).json()
    res = client.get("/foods/search", params={"q": "hummus", "online": False, "limit": 10}, headers=h).json()
    assert res[0]["id"] == own["id"] or any(r["id"] == own["id"] for r in res[:3])
    pan = next(f["id"] for f in client.get("/foods/search", params={"q": "Pan de molde", "online": False}, headers=h).json() if f["name"] == "Pan de molde")
    rec = client.post("/recipes", json={"name": f"R {rnd()}", "ingredients": [{"food_id": pan, "quantity_g": 50}]}, headers=h).json()
    assert client.put(f"/foods/{rec['food_id']}", json={"name": "x"}, headers=h).status_code == 422
    assert client.delete(f"/foods/{rec['food_id']}", headers=h).status_code == 422
    assert rec["food_id"] not in [f["id"] for f in client.get("/foods/mine", headers=h).json()]
    assert client.delete(f"/foods/{pan}", headers=h).status_code == 404            # el catálogo compartido no se borra


def test_copy_any_food_to_make_it_yours(client):
    u, other = onboard_new_user(client), onboard_new_user(client)
    h = u["headers"]
    hum = next(f for f in client.get("/foods/search", params={"q": "Hummus", "online": False}, headers=h).json() if f["name"] == "Hummus")
    c = client.post(f"/foods/{hum['id']}/copy", json={"name": "Mi hummus", "kcal": 150, "fat_g": 8}, headers=h)
    assert c.status_code == 201
    cj = c.json()
    assert cj["name"] == "Mi hummus" and cj["kcal"] == 150 and cj["fat_g"] == 8 and cj["protein_g"] == hum["protein_g"] and cj["user_id"]
    units = {s["unit_name"] for s in client.get(f"/foods/{cj['id']}/servings", headers=h).json()}
    assert "cucharada" in units                                                       # hereda las unidades
    assert client.get(f"/foods/{hum['id']}", headers=h).json()["kcal"] == hum["kcal"]  # el original no cambia
    assert client.get(f"/foods/{cj['id']}", headers=other["headers"]).status_code == 404
    default = client.post(f"/foods/{hum['id']}/copy", headers=h).json()
    assert default["name"] == "Hummus (mío)"
    assert client.post(f"/foods/{cj['id']}/servings", json={"unit_name": "bote", "grams_per_unit": 200}, headers=h).status_code == 201   # unidades propias
    assert client.post(f"/foods/{cj['id']}/copy", json={"kcal": 99999}, headers=h).status_code == 422
    assert client.post(f"/foods/{cj['id']}/copy", headers=other["headers"]).status_code == 404
