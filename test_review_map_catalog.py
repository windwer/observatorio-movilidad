import os,sys,unittest
from pathlib import Path
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
class ReviewMapCatalogTests(unittest.TestCase):
 def setUp(self):
  self.prevdb=app.DB;self.prevdemo=os.environ.get('OBS_DEMO');os.environ['OBS_DEMO']='1';app.DB=Path(__file__).resolve().parents[1]/'data'/'demo'/'observatorio_demo.sqlite3';self.client=TestClient(app.app)
 def tearDown(self):
  app.DB=self.prevdb
  if self.prevdemo is None:os.environ.pop('OBS_DEMO',None)
  else:os.environ['OBS_DEMO']=self.prevdemo
 def routes(self,operator,day):
  res=self.client.get('/api/map',params={'operator':operator,'day':day});self.assertEqual(res.status_code,200)
  return {x['name'] for x in res.json()['routes']}
 def test_complete_demo_catalog_by_period(self):
  self.assertEqual(len(self.routes('ekialdebus','2025-10-16')),20)
  self.assertEqual(len(self.routes('ekialdebus','2025-10-17')),26)
  self.assertEqual(len(self.routes('ekialdebus','2026-10-15')),18)
  self.assertEqual(len(self.routes('ekialdebus','2026-10-16')),25)
 def test_irunbus_l4_in_old_and_new(self):
  for day in ('2025-10-16','2026-10-15'):
   self.assertTrue({'L1','L2','L3','L4'}.issubset(self.routes('irunbus',day)))
  self.assertTrue({'G1','G2'}.issubset(self.routes('irunbus','2025-10-17')))
 def test_all_lines_filter_l4(self):
  r=self.client.get('/api/map',params={'operator':'irunbus','day':'2026-10-15','route_id':'L4'}).json()
  self.assertEqual({x['name'] for x in r['routes']},{'L4'})
  self.assertGreater(len(r['stops']),0)
 def test_map_no_external_tiles_or_javascript(self):
  html=self.client.get('/').text
  javascript=self.client.get('/static/app.js').text
  offline=self.client.get('/static/offline_map.js')
  self.assertEqual(offline.status_code,200)
  self.assertIn('GeographicReviewMap',offline.text)
  for source in (html,javascript):
   self.assertNotIn('tile.openstreetmap.org',source)
   self.assertNotIn('unpkg.com',source)
 def test_combined_map_and_cutoff(self):
  both=self.client.get('/api/map/both',params={'day':'2026-10-16'}).json()
  self.assertFalse(both['missing_operators'])
  self.assertTrue({'ekialdebus','irunbus'}<=set(x['operator'] for x in both['routes']))
  self.assertEqual(self.client.get('/api/map',params={'operator':'ekialdebus','day':'2026-10-19'}).json()['state'],'planning')
 def test_full_catalog_includes_even_off_day_lines(self):
  for operator,year,month,size in [('ekialdebus',2025,10,26),('ekialdebus',2026,10,25),('irunbus',2025,10,6)]:
   response=self.client.get('/api/demo/catalog',params={'operator':operator,'year':year,'month':month})
   self.assertEqual(response.status_code,200)
   self.assertEqual(len(response.json()['routes']),size)
  names={x['name'] for x in self.client.get('/api/demo/catalog?operator=irunbus&year=2026&month=10').json()['routes']}
  self.assertIn('L4',names)
 def test_no_api_download_writes_review(self):
  self.assertEqual(self.client.post('/api/sources/refresh?operator=irunbus').status_code,403)
