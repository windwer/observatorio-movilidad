"""Official Eustat 2025 uploaded CSV; no fictitious population estimates."""
from pathlib import Path
import tempfile
import unittest
from test_client import TestClient
import app
import population_reference as p

SOURCE=Path(__file__).resolve().parent/'data'/'references'/'eustat_2025_original.csv'

class EustatRealTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'data.sqlite3'
  self.old_db=app.DB;self.old_store=app._TERRITORY;app.DB=self.db;app._TERRITORY=None
  self.client=TestClient(app.app)
 def tearDown(self):app.DB=self.old_db;app._TERRITORY=self.old_store;self.tmp.cleanup()
 def test_real_csv_load_exact_subtotals(self):
  x=p.ingest(self.db,SOURCE.read_bytes())
  self.assertEqual(x['total_population'],724797)
  self.assertEqual(x['study_area_population'],150832)
  self.assertEqual(x['sections'],544)
  self.assertEqual(x['districts'],120)
  self.assertEqual(x['by_region'],{'Bidasoaldea':77625,'Oarsoaldea':73207,'Resto de Gipuzkoa':573965,'Gipuzkoa':724797})
  self.assertFalse(x['geometry_joined'])
  self.assertFalse(x['spatial_coverage_ready'])
 def test_api_reads_prepared_population_without_writing_on_get(self):
  p.ingest(self.db,SOURCE.read_bytes())
  response=self.client.get('/api/population/status')
  self.assertEqual(response.status_code,200,response.text)
  x=response.json();self.assertTrue(x['loaded']);self.assertEqual(x['total_population'],724797);self.assertEqual(x['municipality_count'],88)
  detail=self.client.get('/api/population/sections',params={'municipality':'Irun'})
  self.assertEqual(detail.status_code,200,detail.text)
  self.assertEqual(detail.json()['count'],42)
  self.assertEqual(sum(y['population'] for y in detail.json()['sections']),60665)
  self.assertFalse(detail.json()['geometry_joined'])
  self.assertEqual(self.client.get('/api/population/sections',params={'municipality':'Bilbao'}).status_code,400)
 def test_reject_corrupt_district_preserve_original(self):
  original=SOURCE.read_bytes();p.ingest(self.db,original)
  corrupted=original.replace(b'16.960;8.349',b'16.961;8.349',1)
  with self.assertRaisesRegex(ValueError,'no cuadran'):
   p.ingest(self.db,corrupted)
  self.assertEqual(p.summary(self.db)['total_population'],724797)
 def test_source_included_version_and_panel(self):
  doc=self.client.get('/').text
  self.assertIn('Población Eustat 2025 · Gipuzkoa',doc)
  self.assertIn('eustat-population-panel',doc)
  self.assertIn('/static/app.js?v=1.1.0',doc)
  self.assertIn('loadEustatPopulation',Path(__file__).resolve().parent.joinpath('static/app.js').read_text(encoding='utf-8'))

if __name__=='__main__':unittest.main()
