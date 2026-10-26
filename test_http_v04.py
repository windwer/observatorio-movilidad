import sys,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_client import TestClient
import app,engine
from test_network_compare import make_gtfs

class NewHttpTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.old_db=app.DB;self.old_store=app._TERRITORY
  app.DB=Path(self.tmp.name)/'database.sqlite3'
  engine.connect(app.DB).close();app._TERRITORY=None
  self.client=TestClient(app.app)
 def tearDown(self):app.DB=self.old_db;app._TERRITORY=self.old_store;self.tmp.cleanup()
 def test_new_version_visible_and_not_cached(self):
  doc=self.client.get('/')
  self.assertIn('Observatorio · Gipuzkoa',doc.text)
  self.assertIn('v=1.1.0',doc.text)
  self.assertIn('no-store',doc.headers['cache-control'])
  self.assertEqual(self.client.get('/api/version').json()['version'],'1.1.0')
  self.assertEqual(self.client.get('/api/health').json()['version'],'1.1.0')
 def test_import_diff_and_quality(self):
  for code,snapshot,start,finish in [('E25','2025-10-01','20251001','20251031'),('BI05','2026-10-02','20261001','20261031')]:
   response=self.client.post('/api/import',data={'operator':'ekialdebus','snapshot_date':snapshot},
     files={'file':('sample.zip',make_gtfs(code,start,finish),'application/zip')})
   self.assertEqual(response.status_code,200,response.text)
  r=self.client.get('/api/diff/routes',params={'operator':'ekialdebus','old_day':'2025-10-16','new_day':'2026-10-15'})
  self.assertEqual(r.status_code,200,r.text)
  self.assertEqual(r.json()['pairs'][0]['new_route'],'BI05')
  q=self.client.get('/api/quality').json()
  self.assertEqual(q['versions'],2)
  self.assertTrue(all(x['structurally_valid'] for x in q['feeds']))
  self.assertFalse(self.client.get('/api/audit/readiness').json()['publication_ready'])
 def test_no_false_delta_without_history(self):
  result=self.client.get('/api/compare',params={'operator':'irunbus','month':10,'day_type':'V'}).json()
  self.assertFalse(result['comparable']);self.assertIsNone(result['delta_pct'])
