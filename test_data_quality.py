import sys,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine,data_quality
from test_engine import sample_gtfs

class QualityTests(unittest.TestCase):
  def setUp(self):
    self.tmp=tempfile.TemporaryDirectory()
    self.c=engine.connect(Path(self.tmp.name)/'db.sqlite3')
    self.feed=engine.ingest(self.c,sample_gtfs(),'irunbus','2026-09-30','fixture.zip')['feed_id']
  def tearDown(self):self.c.close();self.tmp.cleanup()
  def test_structural_audit_not_historical_certification(self):
    r=data_quality.validate_feed(self.c,self.feed)
    self.assertTrue(r['structurally_valid']);self.assertFalse(r['historically_certified'])
    self.assertEqual(r['summary']['routes'],1)
  def test_orphan_stop_detected(self):
    with self.c:self.c.execute('UPDATE stop_times SET stop_id=? WHERE feed_id=? AND trip_id=?',('absent',self.feed,'t1'))
    r=data_quality.validate_feed(self.c,self.feed)
    self.assertFalse(r['structurally_valid'])
    self.assertIn('stop_event_without_stop',[x['code'] for x in r['issues']])
  def test_invalid_lat_detected(self):
    with self.c:self.c.execute('UPDATE stops SET lat=? WHERE feed_id=? AND stop_id=?',(99,self.feed,'s1'))
    r=data_quality.validate_feed(self.c,self.feed)
    self.assertFalse(r['structurally_valid'])
