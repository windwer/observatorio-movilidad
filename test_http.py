import sys,tempfile,unittest,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app
from test_engine import sample_gtfs
from test_territory import collection,feat,square,coord

class HttpTests(unittest.TestCase):
  def setUp(self):
    self.dir=tempfile.TemporaryDirectory()
    app.DB=Path(self.dir.name)/'test.sqlite3'
    self.client=TestClient(app.app)
  def tearDown(self):
    self.dir.cleanup()
  def test_health_and_page(self):
    self.assertEqual(self.client.get('/api/health').json()['cutoff'],'2026-10-18')
    self.assertIn('Observatorio de Movilidad',self.client.get('/').text)
    self.assertIn('exact-date',self.client.get('/').text)
  def test_geographic_unavailable_is_not_zero(self):
    result=self.client.get('/api/geo/status').json()
    self.assertFalse(result['ready'])
    self.assertEqual(self.client.get('/api/geo/network',params={'operator':'irunbus','day':'2026-10-16'}).json()['population'],None)
  def test_geo_upload_and_endpoint_end_to_end(self):
    raw=collection([feat({'type':'Polygon','coordinates':[square(0,0,150)]},municipality='Irun',population=80,section_id='s')])
    r=self.client.post('/api/geo/import',data={'layer':'census'},files={'file':('test.geojson',raw,'application/geo+json')})
    self.assertEqual(r.status_code,200,r.text)
    self.assertEqual(r.json()['census_sections'],1)
    self.assertFalse(r.json()['ready'])
  def test_comparison_rejects_future_as_historic(self):
    c=self.client.get('/api/compare',params={'operator':'irunbus','month':12,'day_type':'V'}).json()
    self.assertFalse(c['comparable'])
    self.assertIsNone(c['delta_pct'])

  def test_source_requirements(self):
    result=self.client.get('/api/data/requirements').json()
    self.assertEqual(result['cutoff'],'2026-10-18')
    self.assertEqual(len(result['municipalities']),6)

  def test_real_gtfs_upload_flow(self):
    r=self.client.post('/api/import',data={'operator':'irunbus','snapshot_date':'2026-09-30'},files={'file':('TEST_FIXTURE.zip',sample_gtfs(),'application/zip')})
    self.assertEqual(r.status_code,200,r.text)
    self.assertEqual(r.json()['stops'],2)
    m=self.client.get('/api/month',params={'operator':'irunbus','year':2026,'month':10,'day_type':'V','hour_start':0,'hour_end':2880}).json()
    self.assertEqual(len(m['segments']),2)
    self.assertEqual(m['segments'][0]['state'],'historical')
    self.assertEqual(m['segments'][1]['state'],'planning')
    geo=self.client.get('/api/map',params={'operator':'irunbus','day':'2026-10-16'}).json()
    self.assertEqual(len(geo['routes']),1)
    stop=self.client.get('/api/stop',params={'operator':'irunbus','day':'2026-10-16','stop_id':'s1'}).json()
    self.assertEqual(len(stop['departures']),2)
    self.assertTrue(list((Path(self.dir.name)/'originals').glob('*.zip')))
if __name__=='__main__':unittest.main()
