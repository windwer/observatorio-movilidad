import unittest,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_client import TestClient
import app
from test_network_compare import make_gtfs
class CombinedMapTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();app.DB=Path(self.tmp.name)/'db.sqlite3';self.client=TestClient(app.app)
 def tearDown(self):self.tmp.cleanup()
 def upload(self,operator,code):
  return self.client.post('/api/import',data={'operator':operator,'snapshot_date':'2026-10-02'},
      files={'file':(operator+'.zip',make_gtfs(code,'20261001','20261031'),'application/zip')})
 def test_partial_joint_map_not_misleading(self):
  self.assertEqual(self.upload('ekialdebus','OR01').status_code,200)
  data=self.client.get('/api/map/both',params={'day':'2026-10-15'}).json()
  self.assertEqual(data['quality'],'partial')
  self.assertIn('irunbus',data['missing_operators'])
  self.assertEqual({s['operator'] for s in data['stops']},{'ekialdebus'})
  self.assertEqual(self.client.get('/api/geo/network',params={'operator':'both','day':'2026-10-15'}).json()['population'],None)
 def test_joint_map_when_both_loaded(self):
  self.upload('ekialdebus','OR01');self.upload('irunbus','L1')
  data=self.client.get('/api/map/both',params={'day':'2026-10-15'}).json()
  self.assertEqual(data['quality'],'available_unverified')
  self.assertEqual({s['operator'] for s in data['stops']},{'ekialdebus','irunbus'})
  self.assertEqual(len(data['routes']),2)
  self.assertFalse(data['certified'])
 def test_future_date_clearly_planning(self):
  self.upload('ekialdebus','OR01');self.upload('irunbus','L1')
  data=self.client.get('/api/map/both',params={'day':'2026-10-19'}).json()
  self.assertEqual(data['state'],'planning')
