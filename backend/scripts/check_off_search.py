"""Comprueba la búsqueda de texto de Open Food Facts con la red real y muestra la forma de los datos.
Uso:  python scripts/check_off_search.py "yogur griego"
Si imprime 'nutrientes: None' en todos los hits, el índice no devuelve nutrientes en este formato y el backend
completa cada producto con la API de producto (ver MAX_ENRICH en services/openfoodfacts.py)."""
import json
import sys

import httpx

sys.path.insert(0, ".")
from app.config import get_settings  # noqa: E402
from app.services.openfoodfacts import SEARCH_FIELDS, parse_search_hit  # noqa: E402

q = " ".join(sys.argv[1:]) or "yogur griego"
s = get_settings()
if q.replace(" ", "").isdigit():  # modo código de barras: consulta de producto
    from app.services.openfoodfacts import OFF_FIELDS, OFF_URL, parse_off_meta, parse_off_product
    code = q.replace(" ", "")
    r = httpx.get(OFF_URL.format(code=code), params={"fields": OFF_FIELDS}, headers={"User-Agent": s.off_user_agent}, timeout=15)
    d = r.json() if r.is_success else {}
    print("HTTP", r.status_code, "| status:", d.get("status"), "| nombre:", (d.get("product") or {}).get("product_name"))
    print("nutrientes:", parse_off_product(d.get("product") or {}))
    print("metadatos :", parse_off_meta(d.get("product") or {}))   # Nutri-Score, NOVA, Eco-Score, foto, alérgenos...
    sys.exit()
r = httpx.get(s.off_search_url, params={"q": q, "page_size": 5, "langs": "es,en", "fields": SEARCH_FIELDS},
              headers={"User-Agent": s.off_user_agent}, timeout=15, follow_redirects=True)
print("HTTP", r.status_code, "| claves de primer nivel:", list(r.json()) if r.is_success else r.text[:200])
hits = r.json().get("hits") or r.json().get("products") or []
for h in hits:
    item = parse_search_hit(h)
    print("-", h.get("code"), "|", h.get("product_name"), "→", "OK" if item else "descartado",
          "| nutrientes:", item and item["nutrients"] and {k: item["nutrients"][k] for k in ("kcal", "protein_g")})
if hits:
    print("\nHit crudo (para depurar el formato):\n", json.dumps(hits[0], ensure_ascii=False, indent=1)[:1200])
