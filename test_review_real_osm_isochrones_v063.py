import json
import sys
import unittest
from pathlib import Path

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import territory
import engine


class RealOsmIsochroneReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geo_dir = ROOT / 'data' / 'demo' / 'geography'
        cls.store = territory.TerritoryStore(cls.geo_dir)

    def test_packaged_walk_graph_has_real_osm_provenance(self):
        doc = json.loads((self.geo_dir / 'walkways.geojson').read_text(encoding='utf-8'))
        self.assertEqual(doc['metadata']['source'], 'OpenStreetMap contributors')
        self.assertEqual(doc['metadata']['license'], 'ODbL 1.0')
        self.assertFalse(doc['metadata']['transport_api_used'])
        self.assertGreater(len(doc['features']), 10_000)
        self.assertTrue(all(f['properties'].get('osm_id') for f in doc['features'][:100]))
        self.assertFalse(any('SINTÉTICO' in str(f.get('properties')) for f in doc['features']))

    def test_five_and_ten_minutes_are_nested_organic_network_envelopes(self):
        # Irun centro is an actual OSM-covered urban test location. Stop and
        # timetable semantics remain explicitly DEMO.
        iso5 = self.store.stop(43.3392, -1.7894, minutes=5)
        iso10 = self.store.stop(43.3392, -1.7894, minutes=10)
        self.assertEqual(iso5['status'], 'calculated')
        self.assertEqual(iso10['status'], 'calculated')
        self.assertLess(iso5['travel_limit_m'], iso10['travel_limit_m'])
        self.assertLess(iso5['reached_nodes'], iso10['reached_nodes'])
        self.assertLess(iso5['reached_network_m'], iso10['reached_network_m'])
        g5, g10 = shape(iso5['geometry']), shape(iso10['geometry'])
        self.assertTrue(g5.is_valid and g10.is_valid)
        self.assertTrue(g5.within(g10.buffer(1e-8)))
        self.assertLess(g5.area, g10.area)
        self.assertGreater(g5.area / g5.convex_hull.area, .35)
        self.assertGreater(len(g5.exterior.coords), 30)
        self.assertIn('Dijkstra', iso10['method'])
        self.assertIn('OSM', iso10['method'])

    def test_status_exposes_real_network_source(self):
        status = self.store.status()
        self.assertEqual(status['walk_source'], 'OpenStreetMap contributors')
        self.assertGreater(status['walk_osm_ways'], 10_000)
        self.assertGreater(status['walk_segments'], status['walk_osm_ways'])

    def test_route_coverage_deduplicates_all_route_stops(self):
        con = engine.connect(ROOT / 'data' / 'demo' / 'observatorio_demo.sqlite3')
        try:
            stops = engine.map_data(con, 'irunbus', '2026-10-15', 'L1')['stops']
        finally:
            con.close()
        self.assertGreaterEqual(len(stops), 2)
        coverage = self.store.network_coverage(stops, minutes=10)
        self.assertEqual(coverage['stops'], len(stops))
        self.assertEqual(coverage['stops_connected'], len(stops))
        self.assertEqual(coverage['population'], 8400)
        self.assertIn('10-min', coverage['method'])


if __name__ == '__main__':
    unittest.main()
