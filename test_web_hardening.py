"""Regressions for the failures reproduced in the web audit."""
import concurrent.futures
import gc
import tempfile
import os
import unittest
from pathlib import Path
from shapely.geometry import Point
import analysis_jobs,app,territory,model,access_cache
from unittest.mock import patch
from dataclasses import replace
from test_territory import feat,coord


class WebHardening(unittest.TestCase):
    @unittest.skipIf(os.environ.get('OBS_SKIP_LOOPBACK_TESTS')=='1','El entorno restringe las conexiones locales internas del bucle asíncrono')
    def test_geographic_loader_runs_outside_the_async_request_thread(self):
        import asyncio,threading,io
        from fastapi import UploadFile
        from types import SimpleNamespace
        request_thread=threading.get_ident()
        def load():
            self.assertNotEqual(threading.get_ident(),request_thread)
            return SimpleNamespace(ingest=lambda layer,raw:{'layer':layer})
        upload=UploadFile(file=io.BytesIO(b'{}'),filename='walkways.geojson')
        with patch.object(app,'geo_store',side_effect=load):
            self.assertEqual(asyncio.run(app.geo_import('walkways',upload,True)),{'layer':'walkways'})

    def test_cold_stop_is_queued_without_loading_the_web_graph(self):
        import engine,json
        from test_engine import sample_gtfs
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'db.sqlite3';conn=engine.connect(path)
            engine.ingest(conn,sample_gtfs(),'irunbus','2026-09-30','test.zip');conn.close()
            config=replace(app.CONFIG,db=path,immutable_data=True,state_db=root/'state.sqlite3')
            with patch.object(app,'DB',path),patch.object(app,'CONFIG',config),patch.object(app,'prepared_stop',return_value=None),patch.object(app,'require_analysis_worker'),patch.object(app,'current_identity',return_value='fixture'),patch.object(app,'geo_store',side_effect=AssertionError('Graph must stay in worker')):
                response=app.geo_stop('irunbus','2026-10-16','s1',10,True)
            self.assertEqual(response.status_code,202)
            self.assertEqual(json.loads(response.body)['kind'],'stop_isochrone')
    def test_stale_anchor_file_rejected_when_geometry_changes(self):
        from test_performance import PerformanceTests
        import json
        with tempfile.TemporaryDirectory() as folder:
            store=PerformanceTests().make_store(folder)
            before=store.residents[0]['point'].y
            path=store.directory/'walkways.geojson';doc=json.loads(path.read_text())
            for point in doc['features'][0]['geometry']['coordinates']:point[1]+=.001
            path.write_text(json.dumps(doc))
            rebuilt=territory.TerritoryStore(store.directory)
            self.assertGreater(abs(rebuilt.residents[0]['point'].y-before),50)

    def test_missing_worker_is_visible_and_rejects_new_public_work(self):
        from fastapi import HTTPException
        with tempfile.TemporaryDirectory() as folder:
            config=replace(app.CONFIG,immutable_data=True,state_db=Path(folder)/'state.sqlite3')
            with patch.object(app,'CONFIG',config):
                with self.assertRaises(HTTPException) as caught:app.require_analysis_worker()
            self.assertEqual(caught.exception.status_code,503)

    def test_release_activation_and_rollback_are_validated(self):
        import release_manager,json
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pointer=root/'active.json';state=root/'state.sqlite3'
            with patch.object(release_manager.data_release,'validate',return_value={'valid':True}) as validate:
                release_manager.activate(root/'r1',pointer,state)
                release_manager.activate(root/'r2',pointer,state)
                self.assertEqual(Path(json.loads(pointer.read_text())['release_dir']),root/'r2')
                release_manager.rollback(pointer)
                self.assertEqual(Path(json.loads(pointer.read_text())['release_dir']),root/'r1')
                self.assertEqual(validate.call_count,3)
                validate.side_effect=ValueError('invalid manifest')
                with self.assertRaises(ValueError):release_manager.activate(root/'bad',pointer,state)
                self.assertEqual(Path(json.loads(pointer.read_text())['release_dir']),root/'r1')

    def test_concurrent_duplicate_jobs_are_atomic(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.sqlite3'
            def enqueue(_):return analysis_jobs.enqueue(path,'network_coverage',{'x':1},'r','m',1)['id']
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                ids=list(pool.map(enqueue,range(16)))
            self.assertEqual(len(set(ids)),1)

    def test_queue_limit_is_atomic_for_different_jobs(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.sqlite3'
            def enqueue(i):
                try:return analysis_jobs.enqueue(path,'network_coverage',{'x':i},'r','m',1)['id']
                except OverflowError:return None
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:ids=list(pool.map(enqueue,range(8)))
            self.assertEqual(sum(x is not None for x in ids),1)

    def test_expired_worker_cannot_publish_or_renew(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.sqlite3'
            analysis_jobs.enqueue(path,'network_coverage',{},'r','m',3)
            old=analysis_jobs.claim(path,60)
            connection=analysis_jobs.connect(path)
            connection.execute("UPDATE analysis_jobs SET lease_expires_at='2000-01-01'");connection.close()
            new=analysis_jobs.claim(path,60)
            self.assertNotEqual(old['lease_token'],new['lease_token'])
            self.assertFalse(analysis_jobs.finish(path,old['id'],result={},lease_token=old['lease_token']))
            self.assertFalse(analysis_jobs.renew(path,old['id'],old['lease_token']))
            self.assertTrue(analysis_jobs.finish(path,new['id'],result={},lease_token=new['lease_token']))

    def test_cancelled_job_cannot_reappear(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.sqlite3'
            job=analysis_jobs.enqueue(path,'network_coverage',{},'r','m',3)
            row=analysis_jobs.claim(path,60);analysis_jobs.cancel(path,job['id'])
            self.assertFalse(analysis_jobs.finish(path,row['id'],result={},lease_token=row['lease_token']))
            self.assertEqual(analysis_jobs.get(path,job['id'])['status'],'cancelled')

    def test_closed_walkway_retains_its_length(self):
        network=territory.WalkNetwork([feat({'type':'LineString','coordinates':[coord(-100,0),coord(0,0)]},highway='footway'),
          feat({'type':'LineString','coordinates':[coord(0,0),coord(100,0),coord(100,100),coord(0,100),coord(0,0)]},highway='footway')])
        self.assertAlmostEqual(sum(g.length for g in network.geoms),500,places=2)
        self.assertEqual(network.isochrone(*reversed(coord(-100,0)),minutes=5)['status'],'calculated')

    def test_directional_origin_cannot_walk_backwards(self):
        network=territory.WalkNetwork([feat({'type':'LineString','coordinates':[coord(0,0),coord(1000,0)]},highway='footway',**{'oneway:foot':'yes'})])
        iso=network.isochrone(*reversed(coord(500,0)),minutes=5)
        behind=Point(*territory.TO_LOCAL(*coord(300,0)))
        ahead=Point(*territory.TO_LOCAL(*coord(600,0)))
        def distance(point):return network.walk_distance_to(point,iso['_node_distances'],iso['_origin_edge'],iso['_origin_offset'],iso['_origin_access_m'],edge_index=0)
        self.assertGreater(distance(behind),375)
        self.assertLess(distance(ahead),375)

    def test_reverse_foot_direction_reaches_only_the_allowed_side(self):
        network=territory.WalkNetwork([feat({'type':'LineString','coordinates':[coord(0,0),coord(1000,0)]},highway='footway',**{'oneway:foot':'-1'})])
        iso=network.isochrone(*reversed(coord(500,0)),minutes=5)
        def distance(x):return network.walk_distance_to(Point(*territory.TO_LOCAL(*coord(x,0))),iso['_node_distances'],iso['_origin_edge'],iso['_origin_offset'],iso['_origin_access_m'],edge_index=0)
        self.assertLess(distance(300),375);self.assertGreater(distance(700),375)

    def test_cache_changes_with_model_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            before=access_cache.fingerprint(Path(folder));previous=model.WALK_PROFILE['speed_kmh']
            try:
                model.WALK_PROFILE['speed_kmh']=3.0
                self.assertNotEqual(before,access_cache.fingerprint(Path(folder)))
            finally:model.WALK_PROFILE['speed_kmh']=previous

    def test_failed_read_does_not_leak_locks(self):
        def fail():raise ValueError('failure')
        before=len(app._READ_KEY_LOCKS)
        for i in range(5):
            with self.assertRaises(ValueError):app.cached_read(('failure',i),fail)
        gc.collect();self.assertLessEqual(len(app._READ_KEY_LOCKS),before)


if __name__=='__main__':unittest.main()
