"""Publication-regression cases beyond v0.2."""
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app,archive_sync,engine,offer,territory
from test_engine import sample_gtfs

class SecurityAndIntegrityTests(unittest.TestCase):
    def test_requires_authorized_archive_api_key(self):
        with self.assertRaisesRegex(ValueError,'TRANSITLAND_API_KEY'):
            archive_sync.archived_versions('irunbus','')
    def test_frequency_template_is_not_one_trip(self):
        raw=io.BytesIO(sample_gtfs())
        with zipfile.ZipFile(raw,'a') as z:
            z.writestr('frequencies.txt','trip_id,start_time,end_time,headway_secs,exact_times\nt1,07:00:00,09:00:00,900,0\n')
        with tempfile.TemporaryDirectory() as folder:
            conn=engine.connect(Path(folder)/'test.db')
            try:
                with self.assertRaisesRegex(ValueError,'frequencies.txt'):
                    engine.ingest(conn,raw.getvalue(),'irunbus','2026-09-30','frequency.zip')
                self.assertEqual(len(engine.versions(conn)),0)
            finally:conn.close()
    def test_private_password_is_enforced_when_configured(self):
        original=app.PASSWORD
        try:
            app.PASSWORD='Only-for-automatic-testing-12345'
            c=TestClient(app.app)
            self.assertEqual(c.get('/api/health').status_code,401)
            self.assertEqual(c.get('/api/health',auth=('analista','incorrect')).status_code,401)
            self.assertEqual(c.get('/api/health',auth=('analista',app.PASSWORD)).status_code,200)
        finally:app.PASSWORD=original

if __name__=='__main__':unittest.main()
