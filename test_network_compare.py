import sys,tempfile,io,zipfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine,network_compare,launcher

def make_gtfs(code, start, day, extra=False):
    stops='stop_id,stop_name,stop_lat,stop_lon\na,Centro,43.317,-1.897\nb,Puerto,43.323,-1.889\n'
    if extra:stops+='c,Ampliada,43.324,-1.888\n'
    files={
      'routes.txt':f'route_id,route_short_name,route_long_name\n{code},{code},Centro-Puerto\n',
      'stops.txt':stops,
      'trips.txt':f'route_id,service_id,trip_id,trip_headsign,direction_id\n{code},s,{code}_1,Puerto,0\n{code},s,{code}_2,Puerto,0\n',
      'stop_times.txt':f'trip_id,arrival_time,departure_time,stop_id,stop_sequence\n{code}_1,07:00:00,07:00:00,a,1\n{code}_1,07:15:00,07:15:00,b,2\n{code}_2,08:00:00,08:00:00,a,1\n{code}_2,08:15:00,08:15:00,b,2\n',
      'calendar.txt':f'service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\ns,1,1,1,1,1,1,1,{start},{day}\n'
    }
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for n,v in files.items():z.writestr(n,v)
    return out.getvalue()

class NetworkComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.c=engine.connect(Path(self.tmp.name)/'db.sqlite')
        engine.ingest(self.c,make_gtfs('E25','20251001','20251031'),'ekialdebus','2025-10-01','old.zip')
        engine.ingest(self.c,make_gtfs('BI05','20261001','20261031'),'ekialdebus','2026-10-02','new.zip')
    def tearDown(self):self.c.close();self.tmp.cleanup()
    def test_renumbered_corridor_matched_by_physical_stops(self):
        r=network_compare.compare_routes(self.c,'ekialdebus','2025-10-16','2026-10-15')
        self.assertTrue(r['comparable'])
        self.assertEqual(len(r['pairs']),1)
        self.assertEqual(r['pairs'][0]['old_route'],'E25')
        self.assertEqual(r['pairs'][0]['new_route'],'BI05')
        self.assertEqual(r['pairs'][0]['stop_jaccard'],1)
        self.assertTrue(r['pairs'][0]['renumbered'])
        self.assertFalse(r['certified'])
    def test_different_weekday_category_rejected(self):
        with self.assertRaises(ValueError):network_compare.compare_routes(self.c,'ekialdebus','2025-10-17','2026-10-15')
    def test_future_not_historical(self):
        with self.assertRaises(ValueError):network_compare.compare_routes(self.c,'ekialdebus','2025-10-16','2026-10-19')
    def test_never_confuse_old_port(self):
        self.assertEqual(launcher.VERSION,'1.1.0')

if __name__=='__main__':unittest.main()
