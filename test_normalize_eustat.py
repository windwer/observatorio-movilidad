import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from normalize_eustat import parse
from prepare_census import join_key
class EustatTests(unittest.TestCase):
 def test_hierarchical_rows_and_totals_ignored(self):
  rows='Cod;Municipio;Dist;Secc;Total\n045;Irun;01;000;60000\n;;;001;1.500\n;;;002;2.200\n'.encode()
  data=parse(rows,require_six=False)
  self.assertEqual(len(data['rows']),2)
  self.assertEqual(data['populations_by_municipality']['Irun'],3700)
  self.assertEqual(data['rows'][0]['municipality_code'],'045')
 def test_ambiguous_population_decimal_rejected(self):
  rows='Cod;Municipio;Dist;Secc;Total\n045;Irun;01;001;1,25\n'.encode()
  with self.assertRaises(ValueError):parse(rows,require_six=False)
 def test_join_keys_normalized(self):
  self.assertEqual(join_key({'a':'001','b':'01','c':'003'},['a','b','c']),join_key({'a':'1','b':'1','c':'3'},['a','b','c']))
