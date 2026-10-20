"""Adversarial acceptance regressions added at validation of 0.5.0."""
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine,territory
from test_engine import sample_gtfs


def mutate_zip(filename, transformer):
    content={}
    with zipfile.ZipFile(io.BytesIO(sample_gtfs())) as z:
        for name in z.namelist():content[name]=z.read(name).decode('utf-8-sig')
    content[filename]=transformer(content[filename])
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,t in content.items():z.writestr(name,t)
    return out.getvalue()

class FullMVPAcceptance(unittest.TestCase):
    def check_invalid_feed(self,raw,reason):
        with tempfile.TemporaryDirectory() as root:
            db=engine.connect(Path(root)/'t.sqlite')
            try:
                with self.assertRaisesRegex(ValueError,reason):
                    engine.ingest(db,raw,'irunbus','2026-10-10','adversarial.zip')
                self.assertEqual(engine.versions(db),[])
            finally:db.close()
    def test_gtfs_date_parser_rejects_invalid_8digit_date(self):
        with self.assertRaises(ValueError):engine.clean_date('20261399')
    def test_gtfs_seconds_are_preserved(self):
        self.assertAlmostEqual(engine.minutes('07:30:42'),450.7)
        self.assertEqual(engine.fmt_minutes(engine.minutes('07:30:42')),'07:30:42')
        raw=mutate_zip('stop_times.txt',lambda s:s.replace('07:30:00','07:30:42'))
        with tempfile.TemporaryDirectory() as folder:
            conn=engine.connect(Path(folder)/'times.sqlite')
            try:
                engine.ingest(conn,raw,'irunbus','2026-10-10','seconds.zip')
                values=engine.stop_departures(conn,'irunbus','2026-10-16','s1')['departures']
                self.assertEqual(values[0]['time'],'07:30:42')
            finally:conn.close()
    def test_invalid_gtfs_seconds_are_rejected(self):
        raw=mutate_zip('stop_times.txt',lambda s:s.replace('07:30:00','07:30:67'))
        self.check_invalid_feed(raw,'inválido')
    def test_gtfs_duplicate_route_rejected(self):
        raw=mutate_zip('routes.txt',lambda s:s+'\n'+s.splitlines()[1]+'\n')
        self.check_invalid_feed(raw,'duplicados')
    def test_gtfs_duplicate_stop_rejected(self):
        raw=mutate_zip('stops.txt',lambda s:s+'\n'+s.splitlines()[1]+'\n')
        self.check_invalid_feed(raw,'duplicados')
    def test_census_duplicate_section_not_counted_twice(self):
        feature={'type':'Feature','properties':{'section_id':'01001','municipality':'Irun','population':123},
                 'geometry':{'type':'Polygon','coordinates':[[[-1.80,43.32],[-1.79,43.32],[-1.79,43.33],[-1.80,43.32]]]}}
        with self.assertRaisesRegex(ValueError,'duplicadas'):
            territory.normalise_census([feature,feature])
    def test_census_wrong_crs_rejected(self):
        feature={'type':'Feature','properties':{'section_id':'01001','municipality':'Irun','population':123},
                 'geometry':{'type':'Polygon','coordinates':[[[500000,4800000],[500050,4800000],[500050,4800050],[500000,4800000]]]}}
        with self.assertRaisesRegex(ValueError,'CRS distinto'):
            territory.normalise_census([feature])
    def test_cutoff_is_frozen(self):
        self.assertEqual(engine.CUTOFF.isoformat(),'2026-10-18')

if __name__=='__main__':unittest.main()
