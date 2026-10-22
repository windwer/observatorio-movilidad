"""Download the province-wide OSM pedestrian network in bounded tiles.

The runtime needs the actual ways to calculate walking time.  This script keeps
only pedestrian-compatible highway classes and retains the OSM way identity,
then writes a compact GeoJSON FeatureCollection consumed by ``TerritoryStore``.
The download is intentionally tiled so an Overpass request never represents the
whole province in one expensive response.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "real" / "geography" / "walkways.geojson"
PARTIAL = ROOT / "data" / "real" / "geography" / "walkways.partial.json"
ENDPOINTS = (
    "https://overpass.private.coffee/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
# A deliberately generous province bounding box.  Population allocation is
# clipped by the official Gipuzkoa census sections, while the extra border
# context prevents a route near a provincial edge from being cut at the tile.
WEST, SOUTH, EAST, NORTH = -2.70, 42.85, -1.60, 43.55
COLS, ROWS = 4, 4
START_ROW = int(os.environ.get("OBS_WALK_START_ROW", "0"))
ALLOWED = (
    "footway|pedestrian|path|living_street|residential|steps|service|"
    "unclassified|tertiary|secondary|primary|track|cycleway|bridleway"
)
USER_AGENT = "ObservatorioMovilidad/1.0 (provincial pedestrian network; OSM attribution in app)"


def fetch_tile_once(south: float, west: float, north: float, east: float) -> dict:
    query = (
        f'[out:json][timeout:180];way["highway"~"^({ALLOWED})$"]'
        f"({south:.6f},{west:.6f},{north:.6f},{east:.6f});out geom;"
    )
    last_error: Exception | None = None
    for endpoint in ENDPOINTS:
        try:
            url = endpoint + "?" + urllib.parse.urlencode({"data": query})
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=55) as response:
                return json.load(response)
        except Exception as exc:  # try the second public instance
            last_error = exc
    raise RuntimeError(f"Overpass no disponible para la tesela {south},{west},{north},{east}: {last_error}")


def fetch_tile(south: float, west: float, north: float, east: float, depth: int = 0) -> dict:
    """Fetch a tile, subdividing dense rural/urban tiles after a timeout."""
    try:
        return fetch_tile_once(south, west, north, east)
    except RuntimeError:
        if depth >= 2:
            raise
        mid_lat = (south + north) / 2
        mid_lon = (west + east) / 2
        elements = []
        for sub in ((south, west, mid_lat, mid_lon), (south, mid_lon, mid_lat, east),
                    (mid_lat, west, north, mid_lon), (mid_lat, mid_lon, north, east)):
            elements.extend(fetch_tile(*sub, depth=depth + 1).get("elements", []))
        return {"elements": elements}


def feature_from_way(item: dict) -> dict | None:
    geometry = item.get("geometry") or []
    if len(geometry) < 2:
        return None
    tags = item.get("tags") or {}
    if tags.get("foot") in {"no", "private"} or tags.get("access") in {"no", "private"}:
        return None
    coords = [[float(point["lon"]), float(point["lat"])] for point in geometry]
    properties = {
        "osm_id": str(item.get("id")),
        "highway": tags.get("highway"),
    }
    for key in ("foot", "access", "oneway", "surface", "sidewalk"):
        if key in tags:
            properties[key] = tags[key]
    return {"type": "Feature", "id": str(item.get("id")), "properties": properties,
            "geometry": {"type": "LineString", "coordinates": coords}}


def main() -> None:
    ways: dict[str, dict] = {}
    if PARTIAL.exists():
        try:
            ways = {feature["id"]: feature for feature in json.loads(PARTIAL.read_text(encoding="utf-8"))}
            print(f"Retomando teselas previas: {len(ways):,} vías", flush=True)
        except (ValueError, OSError):
            ways = {}
    width = (EAST - WEST) / COLS
    height = (NORTH - SOUTH) / ROWS
    for row in range(START_ROW, ROWS):
        for col in range(COLS):
            south = SOUTH + row * height - (0.0005 if row else 0)
            north = SOUTH + (row + 1) * height + (0.0005 if row < ROWS - 1 else 0)
            west = WEST + col * width - (0.0005 if col else 0)
            east = WEST + (col + 1) * width + (0.0005 if col < COLS - 1 else 0)
            print(f"Overpass tesela {row + 1}/{ROWS}, {col + 1}/{COLS} …", flush=True)
            document = fetch_tile(south, west, north, east)
            for item in document.get("elements", []):
                if item.get("type") != "way":
                    continue
                feature = feature_from_way(item)
                if feature:
                    ways[feature["id"]] = feature
            print(f"  acumuladas: {len(ways):,} vías", flush=True)
            PARTIAL.write_text(json.dumps(list(ways.values()), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            time.sleep(0.5)
    if not ways:
        raise RuntimeError("Overpass no devolvió vías peatonales para Gipuzkoa")
    document = {
        "type": "FeatureCollection",
        "name": "OSM pedestrian network · Gipuzkoa province",
        "metadata": {
            "source": "OpenStreetMap contributors",
            "license": "ODbL 1.0",
            "retrieved": date.today().isoformat(),
            "scope": "provincial bounding box tiled download; population clipped to Gipuzkoa census sections",
            "method": "Overpass highway filter; foot/access=no/private excluded",
        },
        "features": list(ways.values()),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    PARTIAL.unlink(missing_ok=True)
    print(f"{OUTPUT}: {len(ways):,} vías OSM", flush=True)


if __name__ == "__main__":
    main()
