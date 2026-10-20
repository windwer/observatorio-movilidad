import sys,unittest,tempfile,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine,import_sources
from test_engine import sample_gtfs

class BatchTests(unittest.TestCase):
 def test_manifest_sha_and_provenance(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);payload=sample_gtfs();(root/'test.zip').write_bytes(payload)
   rows={'versions':[{'operator':'irunbus','snapshot_date':'2026-09-30','path':'test.zip','sha256':hashlib.sha256(payload).hexdigest()}]}
   (root/'sources.json').write_text(json.dumps(rows))
   conn=engine.connect(root/'test.sqlite')
   try:
    r=import_sources.import_manifest(conn,root/'sources.json')
    self.assertEqual(r['imported'],1)
    self.assertFalse(r['historical_certification'])
    r=import_sources.import_manifest(conn,root/'sources.json')
    self.assertEqual(r['items'][0]['state'],'already_imported')
   finally:conn.close()
 def test_bad_hash_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'test.zip').write_bytes(sample_gtfs())
   (root/'s.json').write_text(json.dumps({'versions':[{'operator':'irunbus','snapshot_date':'2026-09-30','path':'test.zip','sha256':'0'*64}]}))
   conn=engine.connect(root/'a.db')
   try:self.assertEqual(import_sources.import_manifest(conn,root/'s.json')['failed'],1)
   finally:conn.close()
