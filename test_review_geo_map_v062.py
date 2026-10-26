import os,sys,unittest
from pathlib import Path
from test_client import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
class GeoMapAndIsochronesReviewTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if not (Path(__file__).resolve().parent/'data'/'demo'/'observatorio_demo.sqlite3').is_file():
   raise unittest.SkipTest('El fixture DEMO legado no forma parte del checkout de producción')
 def setUp(self):
  self.prevdb=app.DB;self.prev=os.environ.get('OBS_DEMO')
  os.environ['OBS_DEMO']='1'
  app.DB=Path(__file__).resolve().parents[1]/'data'/'demo'/'observatorio_demo.sqlite3'
  self.client=TestClient(app.app)
 def tearDown(self):
  app.DB=self.prevdb
  if self.prev is None:os.environ.pop('OBS_DEMO',None)
  else:os.environ['OBS_DEMO']=self.prev
 def test_base_map_is_true_geographic_raster_and_two_providers(self):
  js=self.client.get('/static/offline_map.js').text
  for key in ('GeoEuskadi','Esri World Topographic Map','mercator','/MapServer/tile/','map-basemap','map-iso-selector','data-layer'):
   self.assertIn(key,js)
  self.assertNotIn('tile.openstreetmap.org',js)
 def test_5_10_min_options_in_frontend(self):
  js=self.client.get('/static/app.js').text
  for key in ('minutes:5','minutes:10','displayIsochrones','Promise.all','5 min:','10 min:'):
   self.assertIn(key,js)
 def test_both_isochrones_return_real_distinct_geometry_from_demo_walkways(self):
  data=self.client.get('/api/map',params={'operator':'irunbus','day':'2026-10-15'}).json()
  stops=data['stops'];self.assertGreater(len(stops),0)
  any_success=False
  for s in stops[:30]:
   params={'operator':'irunbus','day':'2026-10-15','stop_id':s['id']}
   x=self.client.get('/api/geo/stop',params={**params,'minutes':5})
   y=self.client.get('/api/geo/stop',params={**params,'minutes':10})
   self.assertEqual(x.status_code,200,x.text)
   self.assertEqual(y.status_code,200,y.text)
   a,b=x.json(),y.json()
   if a.get('status')=='calculated' and b.get('status')=='calculated':
    self.assertEqual(a['minutes'],5);self.assertEqual(b['minutes'],10)
    self.assertLess(a['travel_limit_m'],b['travel_limit_m'])
    self.assertIsNotNone(a.get('geometry'));self.assertIsNotNone(b.get('geometry'))
    self.assertGreaterEqual(b.get('population') or 0,a.get('population') or 0)
    any_success=True;break
  self.assertTrue(any_success,'Demo needs at least one stop with both isochrones')
 def test_reject_unsupported_isochrone_duration(self):
  x=self.client.get('/api/geo/stop',params={'operator':'irunbus','day':'2026-10-15','stop_id':'irrelevant','minutes':999})
  self.assertEqual(x.status_code,400)
 def test_historical_cutoff_is_not_modified(self):
  self.assertEqual(self.client.get('/api/version').json()['date_cutoff'],'2026-10-18')
 def test_demo_does_not_download_live_transport_data(self):
  self.assertEqual(self.client.post('/api/sources/refresh',params={'operator':'irunbus'}).status_code,403)
