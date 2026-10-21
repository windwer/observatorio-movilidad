import io
import sqlite3
import unittest
import zipfile
from pathlib import Path

import engine
import source_fetch
import territory


def _zip(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    return out.getvalue()


def _euskotren_fixture():
    return _zip({
        'routes.txt': 'route_id,route_short_name,route_long_name\nE1,E1,Bilbao-Donostia\nE3,E3,Lezama-Kukullaga\n',
        'stops.txt': 'stop_id,stop_name,stop_lat,stop_lon\ns1,Amara,43.312,-1.981\ns2,Irun,43.341,-1.796\ns3,Lezama,43.270,-2.850\n',
        'trips.txt': 'route_id,service_id,trip_id,direction_id,trip_headsign,shape_id\nE1,SVC,t1,0,Irun,shape1\nE3,SVC,t2,0,Kukullaga,shape3\n',
        'stop_times.txt': 'trip_id,arrival_time,departure_time,stop_id,stop_sequence\nt1,08:00:00,08:00:00,s1,1\nt1,08:30:00,08:30:00,s2,2\nt2,09:00:00,09:00:00,s1,1\nt2,09:30:00,09:30:00,s3,2\n',
        'calendar.txt': 'service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nSVC,1,1,1,1,1,1,1,20261001,20261031\n',
        'shapes.txt': 'shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\nshape1,43.312,-1.981,1\nshape1,43.341,-1.796,2\nshape3,43.270,-2.850,1\nshape3,43.270,-2.851,2\n',
        'feed_info.txt': 'feed_publisher_name,feed_start_date,feed_end_date\nTest,20261001,20261031\n',
    })


class NetworkAdditionTests(unittest.TestCase):
    def test_euskotren_ingest_keeps_only_corridor_rail_lines(self):
        con = engine.connect(Path('network_additions_test.sqlite3'))
        original_zip = None
        try:
            result = engine.ingest(con, _euskotren_fixture(), 'euskotren', '2026-10-21', 'euskotren.zip')
            original_zip = Path(__file__).resolve().parent / 'originals' / f"{result['sha256']}.zip"
            self.assertEqual(result['routes'], 1)
            self.assertEqual(result['stops'], 2)
            self.assertEqual([r['name'] for r in engine.route_catalog(con, 'euskotren')['routes']], ['E1'])
            feed = con.execute('SELECT warning FROM feeds WHERE id=?', (result['feed_id'],)).fetchone()
            self.assertIn('E1/E2', feed['warning'])
        finally:
            con.close()
            Path('network_additions_test.sqlite3').unlink(missing_ok=True)
            if original_zip:
                original_zip.unlink(missing_ok=True)

    def test_official_static_sources_are_allowlisted(self):
        self.assertIn('euskotren', source_fetch.GTFS_URLS)
        self.assertIn('errenteria_urbanoa', source_fetch.GTFS_URLS)
        self.assertIn('opendata.euskadi.eus', source_fetch.GTFS_URLS['euskotren'])
        self.assertIn('opendata.euskadi.eus', source_fetch.GTFS_URLS['errenteria_urbanoa'])

    def test_packaged_real_geography_returns_target_population(self):
        """The production package must calculate, not blank, target population."""
        geo_dir = Path(__file__).resolve().parent / 'data' / 'real' / 'geography'
        store = territory.TerritoryStore(geo_dir)
        status = store.status()
        self.assertEqual(status['census_sections'], 109)
        self.assertEqual(status['census_population'], 150832)
        self.assertGreater(status['walk_segments'], 0)
        self.assertTrue(status['area_interpolation_ready'])
        result = store.stop(43.3392, -1.7894, minutes=10)
        self.assertEqual(result['status'], 'calculated')
        self.assertGreater(result['population'], 0)
        self.assertEqual(result['population_method'], 'census_section_area_interpolation')

    def test_new_network_routes_are_mappable(self):
        con = engine.connect(Path('network_additions_test.sqlite3'))
        try:
            result = engine.ingest(con, _euskotren_fixture(), 'euskotren', '2026-10-21', 'euskotren.zip')
            mapped = engine.map_data(con, 'euskotren', '2026-10-21')
            self.assertEqual(mapped['quality'], 'snapshot_on_or_before_date')
            self.assertTrue(mapped['routes'])
            self.assertTrue(mapped['stops'])
            self.assertTrue(any(r['name'] == 'E1' for r in mapped['routes']))
        finally:
            con.close()
            Path('network_additions_test.sqlite3').unlink(missing_ok=True)

    def test_real_ui_exposes_all_network_operators(self):
        html = (Path(__file__).resolve().parent / 'static' / 'index.html').read_text(encoding='utf-8')
        for value in ('value="euskotren"', 'value="errenteria_urbanoa"'):
            self.assertIn(value, html)


if __name__ == '__main__':
    unittest.main()
