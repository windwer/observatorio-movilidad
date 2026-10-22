"""Extract Gipuzkoa pedestrian ways from the official regional OSM PBF."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import osmium
from shapely.geometry import LineString, Point, shape, mapping
from shapely.ops import transform, unary_union
from shapely.prepared import prep
from pyproj import Transformer


ROOT = Path(__file__).resolve().parents[1]
PBF = ROOT / "data" / "references" / "pais-vasco-latest.osm.pbf"
CENSUS = ROOT / "data" / "real" / "geography" / "census.geojson"
OUTPUT = ROOT / "data" / "real" / "geography" / "walkways.geojson"
ALLOWED = {
    "footway", "pedestrian", "path", "living_street", "residential", "steps",
    "service", "unclassified", "tertiary", "secondary", "primary", "track",
    "cycleway", "bridleway",
}
TO_LOCAL = Transformer.from_crs("EPSG:4326", "EPSG:25830", always_xy=True).transform


def gipuzkoa_region():
    document = json.loads(CENSUS.read_text(encoding="utf-8"))
    polygons = [shape(feature["geometry"]) for feature in document["features"]]
    # Union in WGS84 is sufficient for the inclusion test; the output remains
    # in WGS84 and is projected by TerritoryStore for graph calculations.
    return prep(unary_union(polygons))


class Handler(osmium.SimpleHandler):
    def __init__(self, region):
        super().__init__()
        self.region = region
        self.features: dict[str, dict] = {}

    def way(self, way):
        tags = way.tags
        highway = tags.get("highway")
        if highway not in ALLOWED or tags.get("foot") in {"no", "private"} or tags.get("access") in {"no", "private"}:
            return
        coords = [[node.lon, node.lat] for node in way.nodes if node.location.valid()]
        if len(coords) < 2:
            return
        # Keep a way when any node falls in a province section.  This retains
        # the short cross-border approach to an edge stop without inventing
        # geometry inside the census layer.
        if not any(self.region.covers(Point(x, y)) for x, y in coords):
            return
        properties = {"osm_id": str(way.id), "highway": highway}
        for key in ("foot", "access", "oneway", "surface", "sidewalk"):
            value = tags.get(key)
            if value is not None:
                properties[key] = value
        self.features[str(way.id)] = {
            "type": "Feature",
            "id": str(way.id),
            "properties": properties,
            "geometry": {"type": "LineString", "coordinates": coords},
        }


def main():
    if not PBF.is_file():
        raise SystemExit(f"Falta el extracto OSM: {PBF}")
    region = gipuzkoa_region()
    handler = Handler(region)
    handler.apply_file(str(PBF), locations=True)
    features = list(handler.features.values())
    if not features:
        raise SystemExit("No se encontraron vías peatonales en Gipuzkoa")
    output = {
        "type": "FeatureCollection",
        "name": "OSM pedestrian network · Gipuzkoa province",
        "metadata": {
            "source": "OpenStreetMap contributors via Geofabrik País Vasco extract",
            "license": "ODbL 1.0",
            "retrieved": date.today().isoformat(),
            "extract": "https://download.geofabrik.de/europe/spain/pais-vasco.html",
            "scope": "ways with at least one node inside the 544 official Gipuzkoa census sections",
            "method": "regional PBF filter; highway classes and foot/access restrictions",
        },
        "features": features,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUTPUT}: {len(features):,} vías OSM extraídas", flush=True)


if __name__ == "__main__":
    main()
