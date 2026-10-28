"""Performance shortcuts must preserve calendar, topology and population results."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import engine
import route_insights
import territory
import app
from dataclasses import replace
from access_cache import AccessCache,fingerprint
from test_engine import sample_gtfs
from test_territory import collection,coord,feat,square


class PerformanceTests(unittest.TestCase):
    def test_materialized_trips_preserve_exceptions_and_overnight_metrics(self):
        with tempfile.TemporaryDirectory() as folder:
            conn=engine.connect(Path(folder)/'db.sqlite3')
            engine.ingest(conn,sample_gtfs(),'irunbus','2026-09-30','test.zip')
            expected=engine.month_analysis(conn,'irunbus',2026,10,'V',1440,2880)
            metrics=route_insights.route_metrics(conn,'irunbus','r1','2026-10-09')
            self.assertTrue(engine.has_trip_summary(conn,1))
            conn.execute('DELETE FROM trip_summary_feeds');conn.commit()
            self.assertEqual(expected,engine.month_analysis(conn,'irunbus',2026,10,'V',1440,2880))
            self.assertEqual(metrics,route_insights.route_metrics(conn,'irunbus','r1','2026-10-09'))
            engine.prepare_trip_summaries(conn)
            self.assertEqual(expected,engine.month_analysis(conn,'irunbus',2026,10,'V',1440,2880))
            conn.close()

    def make_store(self,root,cache=None):
        geo=Path(root)/'geo'
        store=territory.TerritoryStore(geo)
        store.ingest('census',collection([feat({'type':'Polygon','coordinates':[square(0,0,2000)]},municipality='Irun',population=100,section_id='x')]))
        store.ingest('walkways',collection([feat({'type':'LineString','coordinates':[coord(-1200,0),coord(1200,0)]},highway='footway')]))
        store.save_population_anchors()
        return territory.TerritoryStore(geo,artifact_path=cache)

    def test_population_shortcut_matches_geometry_at_both_thresholds(self):
        with tempfile.TemporaryDirectory() as folder:
            store=self.make_store(folder)
            for minutes in (5,10):
                lat,lon=reversed(coord(0,0))
                original=store._isochrone(lat,lon,minutes)
                reached=store._reachable_indices(original)
                self.assertEqual(set(store.reachable(lat,lon,minutes)['indices']),reached)
                with patch.object(store.network,'isochrone',wraps=store.network.isochrone) as search:
                    result=store.network_coverage([{'lat':lat,'lon':lon}]*2,minutes)
                    self.assertEqual(result['population'],store.stop(lat,lon,minutes=minutes)['population'])
                    self.assertFalse(search.call_args_list[0].kwargs['geometry'])

    def test_stop_artifacts_survive_restart_and_invalidate_on_input_change(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'access.sqlite3';store=self.make_store(folder,path)
            lat,lon=reversed(coord(0,0));expected=store.stop(lat,lon)
            indices=store.reachable(lat,lon)
            again=territory.TerritoryStore(store.directory,artifact_path=path)
            with patch.object(again.network,'isochrone',side_effect=AssertionError('must use persisted artifact')):
                self.assertEqual(again.stop(lat,lon)['population'],expected['population'])
                self.assertEqual(again.reachable(lat,lon),indices)
            old_namespace=fingerprint(store.directory)
            census=store.directory/'census.geojson';census.write_bytes(census.read_bytes()+b' ')
            self.assertNotEqual(old_namespace,fingerprint(store.directory))
            self.assertIsNone(AccessCache(path,fingerprint(store.directory)).get('reach:%.6f:%.6f:10'%(lat,lon)))

    def test_unconnected_stop_remains_unconnected(self):
        with tempfile.TemporaryDirectory() as folder:
            store=self.make_store(folder)
            lat,lon=reversed(coord(0,300))
            result=store.network_coverage([{'lat':lat,'lon':lon}])
            self.assertEqual(result['stops_unconnected'],1)
            self.assertEqual(result['population'],0)

    def test_prepared_stop_endpoint_does_not_load_provincial_graph(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'access-cache.sqlite3';store=self.make_store(folder,path)
            lat,lon=reversed(coord(0,0));expected=store.stop(lat,lon)
            db=root/'gtfs.sqlite3';conn=engine.connect(db)
            engine.ingest(conn,sample_gtfs(),'irunbus','2026-09-30','test.zip')
            conn.execute('UPDATE stops SET lat=?,lon=? WHERE stop_id=?',(lat,lon,'s1'));conn.commit();conn.close()
            config=replace(app.CONFIG,db=db.resolve(),geography_dir=store.directory,state_db=root/'state.sqlite3')
            with patch.object(app,'CONFIG',config),patch.object(app,'DB',db),patch.object(app,'geo_store',side_effect=AssertionError('cold graph must not load')):
                result=app.geo_stop('irunbus','2026-10-16','s1',10,True)
                self.assertEqual(result['population'],expected['population'])
                self.assertEqual(result['stop_id'],'s1')


if __name__=='__main__':unittest.main()
