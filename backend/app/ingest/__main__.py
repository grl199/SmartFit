"""CLI de ingesta batch.  Uso (desde backend/):

  python -m app.ingest fdc RUTA [RUTA ...] [--dry-run]       # USDA FoodData Central (carpeta o .zip de Foundation / SR Legacy)
  python -m app.ingest csv FICHERO.csv --source bedca --license "..." --attribution "..." [--delimiter ";"] [--decimal-comma] [--map "A=name"] [--dry-run]
  python -m app.ingest translate [--source usda] [--limit N] [--batch 25]   # traduce nombres con IA (reanudable; es el único paso que usa IA)
  python -m app.ingest stats                                                # cuántos alimentos hay por fuente
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select

from ..db import SessionLocal, init_db
from ..models import Food
from ..services.food_sources import bulk_upsert
from . import csv_foods, fdc, translate


def _load(name: str, items, stats: dict, dry: bool) -> None:
    print(f"{name}: " + ", ".join(f"{k}={v}" for k, v in stats.items()))
    if dry:
        print("  (dry-run: no se ha escrito nada)")
        return
    with SessionLocal() as db:
        res = bulk_upsert(db, items)
    print(f"  insertados={res['inserted']} actualizados={res['updated']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.ingest", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("fdc", help="USDA FoodData Central (CSV oficiales)")
    a.add_argument("paths", nargs="+")
    a.add_argument("--dry-run", action="store_true")
    c = sub.add_parser("csv", help="CSV genérico")
    c.add_argument("path")
    c.add_argument("--source", required=True)
    c.add_argument("--license")
    c.add_argument("--attribution")
    c.add_argument("--confidence", default="medium")
    c.add_argument("--delimiter", default=",")
    c.add_argument("--decimal-comma", action="store_true")
    c.add_argument("--map", action="append", default=[], metavar="ORIGINAL=DESTINO")
    c.add_argument("--dry-run", action="store_true")
    t = sub.add_parser("translate", help="Traduce nombres con IA")
    t.add_argument("--source", default="usda")
    t.add_argument("--limit", type=int)
    t.add_argument("--batch", type=int, default=25)
    sub.add_parser("stats")
    args = p.parse_args(argv)

    try:
        init_db()
        if args.cmd == "fdc":
            for path in args.paths:
                items, stats = fdc.read_fdc(path)
                _load(path, items, stats, args.dry_run)
        elif args.cmd == "csv":
            mapping = dict(m.split("=", 1) for m in args.map if "=" in m)
            items, stats = csv_foods.read_csv(args.path, source=args.source, license=args.license, attribution=args.attribution,
                                              confidence=args.confidence, delimiter=args.delimiter, decimal_comma=args.decimal_comma, mapping=mapping)
            _load(args.path, items, stats, args.dry_run)
        elif args.cmd == "translate":
            with SessionLocal() as db:
                print(f"Pendientes de traducir ({args.source}): {translate.pending(db, args.source)}")
                n = translate.translate_source(db, args.source, args.limit, args.batch, progress=lambda d, tot: print(f"  {d}/{tot}", flush=True))
                print(f"Traducidos: {n}. Pendientes: {translate.pending(db, args.source)}")
        elif args.cmd == "stats":
            with SessionLocal() as db:
                for src, n in db.execute(select(Food.source, func.count()).where(Food.user_id.is_(None)).group_by(Food.source).order_by(func.count().desc())):
                    print(f"{src:16s} {n}")
    except (fdc.FdcFormatError, ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
