"""Join official GeoEuskadi section geometry to the Eustat 2025 counts.

The GeoEuskadi service can return more than one feature for a section key.
Those parts are dissolved before writing the layer consumed by TerritoryStore,
so population is never duplicated.  The resulting layer supports transparent
section-area interpolation when residential building data is not available.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[1]
RAW_GEOMETRY = ROOT / "data" / "references" / "eustat_sections_2025_geometry.geojson"
POPULATION = ROOT / "data" / "references" / "eustat_sections_2025_normalized.csv"
OUTPUT = ROOT / "data" / "real" / "geography" / "census.geojson"


def section_key(municipality_code: object, district: object, section: object) -> str:
    return f"{str(municipality_code).strip().zfill(3)}-{str(district).strip().zfill(2)}-{str(section).strip().zfill(3)}"


def main() -> None:
    raw = json.loads(RAW_GEOMETRY.read_text(encoding="utf-8"))
    population_rows: dict[str, dict[str, str]] = {}
    with POPULATION.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            population_rows[section_key(row["municipality_code"], row["district"], row["section"])] = row

    geometries: defaultdict[str, list] = defaultdict(list)
    for feature in raw.get("features", []):
        props = feature.get("properties") or {}
        key = section_key(props.get("SEC_MUNI"), props.get("SEC_DIST"), props.get("SEC_SECC"))
        if key not in population_rows:
            continue
        geometry = shape(feature["geometry"])
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        if not geometry.is_empty:
            geometries[key].append(geometry)

    missing = sorted(set(population_rows) - set(geometries))
    if missing:
        raise RuntimeError(f"Faltan geometrías oficiales para {len(missing)} secciones: {missing[:5]}")

    features = []
    for key, row in population_rows.items():
        geometry = unary_union(geometries[key])
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        features.append(
            {
                "type": "Feature",
                "id": key,
                "properties": {
                    "section_id": key,
                    "municipality": row["municipality"],
                    "municipality_code": row["municipality_code"],
                    "district": row["district"],
                    "section": row["section"],
                    "population": int(float(row["population"])),
                    "reference_date": row["reference_date"],
                    "source_geometry": "GeoEuskadi DGSGIS/WFS_DGSGIS/Secciones",
                    "source_population": "Eustat 2025",
                },
                "geometry": mapping(geometry),
            }
        )

    total = sum(feature["properties"]["population"] for feature in features)
    if len(features) != len(population_rows) or total != 150832:
        raise RuntimeError(f"Validación Eustat fallida: {len(features)} secciones, {total} habitantes")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "name": "Eustat 2025 sections · GeoEuskadi geometry",
                "features": features,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    print(f"{OUTPUT}: {len(features)} secciones, {total} habitantes")


if __name__ == "__main__":
    main()
