import json
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

import analysis_jobs
import app
import data_release
import engine


class ArchitectureTests(unittest.TestCase):
    def test_public_read_does_not_authorize_administration(self):
        original_reader,original_admin=app.PASSWORD,app.ADMIN_PASSWORD
        try:
            app.PASSWORD=None;app.ADMIN_PASSWORD='A-strong-local-administration-password'
            self.assertTrue(app.guard(None))
            with self.assertRaises(HTTPException) as caught:
                app.admin_guard(None)
            self.assertEqual(caught.exception.status_code,401)
        finally:app.PASSWORD,app.ADMIN_PASSWORD=original_reader,original_admin

    def test_durable_queue_reuses_a_complete_analysis(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.sqlite3';params={'operator':'irunbus','day':'2026-10-16','minutes':10}
            first=analysis_jobs.enqueue(path,'network_coverage',params,'r1','m1',3)
            row=analysis_jobs.claim(path,60);self.assertEqual(row['id'],first['id'])
            analysis_jobs.finish(path,row['id'],result={'population':123})
            reused=analysis_jobs.enqueue(path,'network_coverage',params,'r1','m1',3)
            self.assertTrue(reused['reused']);self.assertEqual(reused['result']['population'],123)

    def test_data_release_build_and_restore_is_hash_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.sqlite3';conn=engine.connect(source)
            conn.execute("CREATE TABLE population_reference_meta(total INTEGER)")
            conn.execute("INSERT INTO population_reference_meta VALUES (10)")
            conn.execute("INSERT INTO feeds(sha256,operator,snapshot_date,original_name,imported_at) VALUES ('x','irunbus','2026-01-01','x.zip','2026-01-01')")
            conn.commit();conn.close()
            geo=root/'geo';geo.mkdir()
            empty={'type':'FeatureCollection','features':[]}
            (geo/'census.geojson').write_text(json.dumps(empty),encoding='utf-8')
            (geo/'walkways.geojson').write_text(json.dumps(empty),encoding='utf-8')
            (geo/'population_anchors.json').write_text(json.dumps({'method_version':'walk-network-anchors-v2','census_population':10,'anchors':[['a','Irun',10,1,1,0]]}),encoding='utf-8')
            reference=root/'reference.csv';reference.write_text('x',encoding='utf-8')
            release=root/'release';data_release.build(source,geo,reference,release,'test-release')
            checked=data_release.validate(release);self.assertTrue(checked['valid'])
            restored=root/'restored';data_release.restore(release,restored)
            self.assertTrue((restored/'release-manifest.json').is_file())


if __name__=='__main__':unittest.main()
