import io,sys,zipfile,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine
from test_engine import sample_gtfs

def with_frequency(exact='1',headway='900'):
 buf=io.BytesIO()
 with zipfile.ZipFile(io.BytesIO(sample_gtfs())) as old:
  with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
   for n in old.namelist():z.writestr(n,old.read(n))
   z.writestr('frequencies.txt',
       'trip_id,start_time,end_time,headway_secs,exact_times\n'
       +f't1,07:30:00,08:30:00,{headway},{exact}\n')
 return buf.getvalue()
class FrequencyTests(unittest.TestCase):
 def test_exact_times_one_expands_deterministically(self):
  with tempfile.TemporaryDirectory() as d:
   con=engine.connect(Path(d)/'f.db')
   try:
    v=engine.ingest(con,with_frequency(),'irunbus','2026-09-30','freq.zip')
    self.assertEqual(v['trips'],5) # four exact trips + Friday trip
    r=engine.date_trip_rows(con,v['feed_id'],{'wk'})
    self.assertEqual(sorted(t['first_dep'] for t in r),[450,465,480,495])
   finally:con.close()
 def test_nonexact_frequency_not_turned_into_false_timetable(self):
  with tempfile.TemporaryDirectory() as d:
   con=engine.connect(Path(d)/'f.db')
   try:
    with self.assertRaises(ValueError):engine.ingest(con,with_frequency('0'),'irunbus','2026-09-30','freq.zip')
   finally:con.close()
 def test_second_precision_no_silent_rounding(self):
  with tempfile.TemporaryDirectory() as d:
   con=engine.connect(Path(d)/'f.db')
   try:
    with self.assertRaises(ValueError):engine.ingest(con,with_frequency('1','75'),'irunbus','2026-09-30','freq.zip')
   finally:con.close()
