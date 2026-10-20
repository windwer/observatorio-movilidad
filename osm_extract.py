"""Convert bounded OpenStreetMap API extracts into the demo walk graph.

This utility is intentionally independent from Transitland and GTFS.  It keeps
only walkable highway ways, preserves OSM identifiers/tags for provenance, and
deduplicates overlapping review windows.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from territory import ALLOW_FOOT


def convert(inputs: list[Path], output: Path) -> dict:
    ways: dict[str, dict] = {}
    for source in inputs:
        root = ET.parse(source).getroot()
        nodes = {
            node.attrib['id']: [float(node.attrib['lon']), float(node.attrib['lat'])]
            for node in root.findall('node')
        }
        for way in root.findall('way'):
            tags = {tag.attrib['k']: tag.attrib['v'] for tag in way.findall('tag')}
            highway = tags.get('highway', '').lower()
            if highway not in ALLOW_FOOT:
                continue
            if tags.get('foot', '').lower() in ('no', 'private') or tags.get('access', '').lower() in ('no', 'private'):
                continue
            coords = [nodes[nd.attrib['ref']] for nd in way.findall('nd') if nd.attrib.get('ref') in nodes]
            if len(coords) < 2:
                continue
            ident = way.attrib['id']
            ways[ident] = {
                'type': 'Feature',
                'id': f'way/{ident}',
                'properties': {**tags, 'osm_type': 'way', 'osm_id': ident},
                'geometry': {'type': 'LineString', 'coordinates': coords},
            }
    doc = {
        'type': 'FeatureCollection',
        'name': 'OSM pedestrian network - Product Review pilot',
        'metadata': {
            'source': 'OpenStreetMap contributors',
            'license': 'ODbL 1.0',
            'retrieved': date.today().isoformat(),
            'method': 'bounded OSM API extracts around DEMO stops; walkable highway filter',
            'transport_api_used': False,
        },
        'features': list(ways.values()),
    }
    output.write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return {'files': len(inputs), 'walkable_ways': len(ways), 'bytes': output.stat().st_size}


if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise SystemExit('usage: osm_extract.py OUTPUT.geojson INPUT.osm [INPUT.osm ...]')
    print(convert([Path(x) for x in sys.argv[2:]], Path(sys.argv[1])))
