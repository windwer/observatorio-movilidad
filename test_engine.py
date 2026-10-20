import io
import os
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine


def sample_gtfs():
    files={
      'routes.txt': 'route_id,route_short_name,route_long_name\nr1,TEST1,Centro - Puerto\n',
      'stops.txt': 'stop_id,stop_name,stop_lat,stop_lon\ns1,Centro,43.317,-1.897\ns2,Puerto,43.323,-1.889\n',
      'trips.txt': 'route_id,service_id,trip_id,trip_headsign,direction_id,shape_id\nr1,wk,t1,Puerto,0,sh\nr1,fr,t2,Puerto,0,sh\n',
      'stop_times.txt':'trip_id,arrival_time,departure_time,stop_id,stop_sequence\nt1,07:30:00,07:30:00,s1,1\nt1,07:45:00,07:45:00,s2,2\nt2,25:05:00,25:05:00,s1,1\nt2,25:20:00,25:20:00,s2,2\n',
      'calendar.txt':'service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nwk,1,1,1,1,1,0,0,20261001,20261031\nfr,0,0,0,0,1,0,0,20261001,20261031\n',
      'calendar_dates.txt':'service_id,date,exception_type\nwk,20261009,2\nfr,20261010,1\n',
      'shapes.txt':'shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\nsh,43.317,-1.897,1\nsh,43.323,-1.889,2\n',
    }
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for name,body in files.items():z.writestr(name,body)
    return output.getvalue()

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.db=tempfile.TemporaryDirectory()
        self.conn=engine.connect(Path(self.db.name)/'sample.db')
        self.content=sample_gtfs()
        self.add=engine.ingest(self.conn,self.content,'irunbus','2026-09-30','example_TEST_ONLY.zip')
    def tearDown(self):
        self.conn.close();self.db.cleanup()
    def test_version_dedup(self):
        row=engine.ingest(self.conn,self.content,'irunbus','2026-09-30','example_TEST_ONLY.zip')
        self.assertTrue(row['already_imported'])
        self.assertEqual(len(engine.versions(self.conn)),1)
    def test_friday_exception_and_cross_midnight(self):
        version,q=engine.pick_version(self.conn,'irunbus','2026-10-09')
        self.assertEqual(engine.active_services(self.conn,version['id'],'2026-10-09'),{'fr'})
        departing=engine.stop_departures(self.conn,'irunbus','2026-10-09','s1')['departures']
        self.assertEqual([d['time'] for d in departing],['25:05'])
        self.assertEqual(engine.active_services(self.conn,version['id'],'2026-10-10'),{'fr'})
    def test_october_split(self):
        result=engine.month_analysis(self.conn,'irunbus',2026,10,'V',0,2880)
        self.assertEqual([x['state'] for x in result['segments']],['historical','planning'])
        before=result['segments'][0];after=result['segments'][1]
        self.assertTrue(all(d['date']<='2026-10-18' for d in before['daily']))
        self.assertTrue(all(d['date']>'2026-10-18' for d in after['daily']))
        self.assertEqual(before['days_available'],3)
        self.assertEqual(after['days_available'],2)
    def test_explicit_calendar_exceptions_filter(self):
        r=engine.month_analysis(self.conn,'irunbus',2026,10,'V',calendar_filter='exception')
        self.assertEqual(r['segments'][0]['days_explicit_exception'],1)
        self.assertEqual(r['segments'][0]['days_available'],1)
    def test_historical_comparison_requires_complete_sources(self):
        r=engine.historical_comparison(self.conn,'irunbus',10,'LJ')
        self.assertFalse(r['comparable'])
        self.assertIsNone(r['delta_pct'])

    def test_no_fake_zeros(self):
        other=engine.month_analysis(self.conn,'ekialdebus',2026,10,'LJ')
        self.assertIsNone(other['segments'][0]['average_trips_per_day'])
        self.assertEqual(other['segments'][0]['days_available'],0)
    def test_map_geometries(self):
        view=engine.map_data(self.conn,'irunbus','2026-10-16')
        self.assertEqual(len(view['routes']),1)
        self.assertEqual(len(view['stops']),2)
    def test_reject_future_snapshot(self):
        with self.assertRaises(ValueError):engine.ingest(self.conn,self.content,'ekialdebus','2026-10-19','future.zip')
    def test_category(self):
        self.assertEqual(engine.day_category(engine.date(2026,10,16)),'V')
        self.assertEqual(engine.day_category(engine.date(2026,10,18)),'D')

if __name__=='__main__':unittest.main()
