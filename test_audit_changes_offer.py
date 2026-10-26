import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_client import TestClient
import engine,audit,changes,offer,territory,app
from test_engine import sample_gtfs
from test_territory import coord,feat,collection,square

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.con=engine.connect(Path(self.tmp.name)/'test.db')
        self.add=engine.ingest(self.con,sample_gtfs(),'irunbus','2026-09-30','testing_only.zip')
    def tearDown(self):
        self.con.close();self.tmp.cleanup()
    def test_grid_freezes_october_and_planning(self):
        october=audit.month_grid(self.con,'irunbus',2026)['months'][9]
        self.assertEqual(october['historical_days'],18)
        self.assertEqual(october['planning_days'],13)
        self.assertFalse(october['ready'])
        november=audit.month_grid(self.con,'irunbus',2026)['months'][10]
        self.assertEqual(november['historical_days'],0)
        self.assertFalse(november['ready'])
    def test_release_not_ready_on_sample_fixture(self):
        s=audit.readiness(self.con)
        self.assertFalse(s['publication_ready'])
        self.assertEqual(s['target_days_per_operator'],656)
        self.assertGreater(s['operators']['irunbus']['missing'],0)
    def test_review_needs_evidence_and_correct_feed(self):
        with self.assertRaisesRegex(ValueError,'evidencia'):
            audit.review_period(self.con,'irunbus','2026-10-15','2026-10-16','QA','ok')
        r=audit.review_period(self.con,'irunbus','2026-10-15','2026-10-16','QA equipo',
              'Contrastado con horarios oficiales de AUIF para estas fechas')
        self.assertEqual(r['reviewed'],2)
        self.assertEqual(audit.provenance_day(self.con,'irunbus',engine.date(2026,10,16))['state'],'verified')
        self.assertFalse(audit.readiness(self.con)['data_gate_passed'])
    def test_cannot_certify_future_planning(self):
        with self.assertRaises(ValueError):
            audit.review_period(self.con,'irunbus','2026-10-19','2026-10-19','QA equipo',
                         'Evidencia futura provisional, no acreditada')
    def test_spatial_comparison_requires_two_versions(self):
        r=changes.compare_stops(self.con,'irunbus')
        self.assertFalse(r['comparable'])
        self.assertEqual(r['changes'],None)
    def test_supply_threshold_requires_two_departures(self):
        offer_data=offer.stop_service_offer(self.con,'irunbus','2026-10-16',420,540)
        self.assertEqual(offer_data['status'],'source_available')
        self.assertEqual(len(offer_data['threshold_stops']),0)
        self.assertEqual(offer_data['pattern_count'],0)

class GeographicRegression(unittest.TestCase):
    def test_mid_segment_walk_is_reachable(self):
        # A single 3-km OSM segment: the stop is at its midpoint.
        path=feat({'type':'LineString','coordinates':[coord(0,0),coord(3000,0)]},highway='footway')
        graph=territory.WalkNetwork([path])
        lon,lat=coord(1500,0)
        result=graph.isochrone(lat,lon)
        self.assertEqual(result['status'],'calculated')
        self.assertTrue(result['polygon'].covers(territory.Point(*territory.TO_LOCAL(*coord(1600,0)))))
        self.assertFalse(result['polygon'].covers(territory.Point(*territory.TO_LOCAL(*coord(2600,0)))))

class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.original_db=app.DB
        app.DB=Path(self.tmp.name)/'db.sqlite3'
        engine.connect(app.DB).close()
        app._TERRITORY=None
        self.client=TestClient(app.app)
    def tearDown(self):
        app.DB=self.original_db;app._TERRITORY=None;self.tmp.cleanup()
    def test_new_readiness_api_and_page(self):
        r=self.client.get('/api/audit/readiness')
        self.assertEqual(r.status_code,200)
        self.assertFalse(r.json()['publication_ready'])
        page=self.client.get('/').text
        self.assertIn('Auditoría del histórico',page)
        self.assertIn('Población cubierta por nivel de servicio',page)
    def test_csrf_origin_restriction(self):
        r=self.client.post('/api/sources/refresh?operator=irunbus',headers={'origin':'https://evil.invalid'})
        self.assertEqual(r.status_code,403)
    def test_no_population_figures_without_inputs(self):
        r=self.client.get('/api/geo/service-coverage',params={'operator':'both','day':'2026-10-16'})
        self.assertEqual(r.status_code,200)
        self.assertIsNone(r.json()['population_by_frequency'])
    def test_no_fake_stop_comparison(self):
        r=self.client.get('/api/diff/stops',params={'territorial_scope':'false'})
        self.assertEqual(r.status_code,200)
        self.assertFalse(r.json()['comparable'])

if __name__=='__main__':unittest.main()
