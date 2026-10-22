"""Join official section geometry to the Eustat 2025 counts.

The INE Secciones_2025 OGC layer provides the current 544 Gipuzkoa section
geometries; Eustat remains the population-count source.  The service can
return more than one feature for a section key, so parts are dissolved before
writing the layer consumed by TerritoryStore and population is never duplicated.
The resulting layer supports transparent section-area interpolation when
residential building data is not available.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[1]
RAW_GEOMETRY = ROOT / "data" / "references" / "ine_sections_2025_gipuzkoa.geojson"
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
        # GeoEuskadi uses SEC_* names; INE's official 2025 service uses CMUN,
        # CDIS and CSEC.  Supporting both keeps the preparation step reusable
        # for a future GeoEuskadi refresh without changing the output schema.
        key = section_key(
            props.get("SEC_MUNI", props.get("CMUN")),
            props.get("SEC_DIST", props.get("CDIS")),
            props.get("SEC_SECC", props.get("CSEC")),
        )
        if key not in population_rows:
            continue
        geometry = shape(feature["geometry"])
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        if not geometry.is_empty:
            geometries[key].append(geometry)

    # A production load must match every Eustat section.  Failing closed here
    # prevents a missing polygon from silently turning into an under-counted
    # isochrone population result.
    matched_rows = {key: row for key, row in population_rows.items() if key in geometries}
    missing = sorted(set(population_rows) - set(geometries))
    if missing:
        raise RuntimeError(f"Faltan {len(missing)} geometrías de sección Eustat: {', '.join(missing[:8])}")

    features = []
    for key, row in matched_rows.items():
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
                    "source_geometry": "INE OGC Secciones_2025 (EPSG:4326)",
                    "source_population": "Eustat 2025",
                },
                "geometry": mapping(geometry),
            }
        )

    total = sum(feature["properties"]["population"] for feature in features)
    expected_total = sum(int(row["population"]) for row in matched_rows.values())
    if len(features) != len(matched_rows) or total != expected_total:
        raise RuntimeError(f"Validación Eustat fallida: {len(features)} secciones, {total} habitantes")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "name": "Eustat 2025 sections · INE Secciones_2025 geometry",
                "features": features,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    print(f"{OUTPUT}: {len(features)} secciones, {total} habitantes; cobertura geométrica completa de Gipuzkoa")


if __name__ == "__main__":
    main()
