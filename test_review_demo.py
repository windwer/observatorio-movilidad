import unittest,os,sys
from pathlib import Path
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
class ReviewDemoTests(unittest.TestCase):
  def setUp(self):
    self.prev=os.environ.get('OBS_DEMO');self.prevdb=app.DB
    os.environ['OBS_DEMO']='1'
    app.DB=Path(__file__).resolve().parents[1]/'data'/'demo'/'observatorio_demo.sqlite3'
    self.client=TestClient(app.app)
  def tearDown(self):
    app.DB=self.prevdb
    if self.prev is None:os.environ.pop('OBS_DEMO',None)
    else:os.environ['OBS_DEMO']=self.prev
  def test_demo_explicit_and_write_blocked(self):
    self.assertTrue(self.client.get('/api/demo/status').json()['demo'])
    self.assertEqual(self.client.post('/api/sources/refresh?operator=ekialdebus').status_code,403)
    self.assertIn('DATOS FICTICIOS',self.client.get('/').text)
  def test_scenarios_and_real_population_reference(self):
    r=self.client.get('/api/map?operator=ekialdebus&day=2025-10-16').json()
    self.assertEqual(r['state'],'historical')
    self.assertIn('E01',{x['name'] for x in r['routes']})
    r=self.client.get('/api/map?operator=ekialdebus&day=2026-10-16').json()
    self.assertIn('OR01',{x['name'] for x in r['routes']})
    self.assertEqual(self.client.get('/api/map?operator=ekialdebus&day=2026-10-21').json()['state'],'planning')
    self.assertEqual(self.client.get('/api/population/status').json()['total_population'],724797)
    self.assertTrue(self.client.get('/api/geo/status').json()['ready'])
  def test_demo_comparison(self):
    r=self.client.get('/api/compare?operator=ekialdebus&month=10&day_type=LJ').json()
    self.assertTrue(r['comparable']); self.assertFalse(r['certified'])
