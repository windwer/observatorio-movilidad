"""Synthetic geometries are test fixtures only; never packaged as observatory data."""
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pyproj import Transformer
import territory
from shapely.geometry import Point

back=Transformer.from_crs('EPSG:25830','EPSG:4326',always_xy=True)
x0,y0=territory.TO_LOCAL(-1.8,43.33)
def coord(dx,dy):return list(back.transform(x0+dx,y0+dy))
def square(x,y,size):
 return [coord(x-size,y-size),coord(x+size,y-size),coord(x+size,y+size),coord(x-size,y+size),coord(x-size,y-size)]
def collection(features):return json.dumps({'type':'FeatureCollection','features':features}).encode()
def feat(geom,**kwargs):return {'type':'Feature','properties':kwargs,'geometry':geom}
class TerritoryTests(unittest.TestCase):
  def setUp(self):
    self.d=tempfile.TemporaryDirectory();self.store=territory.TerritoryStore(Path(self.d.name))
    c=feat({'type':'Polygon','coordinates':[square(470,20,700)]},municipality='Irun',population=100,section_id='001')
    b1=feat({'type':'Polygon','coordinates':[square(100,0,12)]},building='residential')
    b2=feat({'type':'Polygon','coordinates':[square(1050,0,12)]},building='residential')
    w=feat({'type':'LineString','coordinates':[coord(x,0) for x in [0,150,300,450,600,750,900,1100]]},highway='footway')
    self.store.ingest('census',collection([c]));self.store.ingest('buildings',collection([b1,b2]));self.store.ingest('walkways',collection([w]))
  def tearDown(self):self.d.cleanup()
  def test_real_network_not_circle_and_population(self):
    result=self.store.stop(*reversed(coord(0,0)))
    self.assertEqual(result['status'],'calculated')
    self.assertEqual(result['population'],50)
    self.assertGreaterEqual(result['reached_nodes'],1)
    self.assertEqual(result['population_method'],'residential_building')
    self.assertNotEqual(result['geometry']['type'],'Point')
    self.assertIn('Dijkstra sobre topología peatonal OSM',result['method'])
  def test_no_walkway_far_stop(self):
    result=self.store.stop(*reversed(coord(0,300)))
    self.assertEqual(result['status'],'no_walkway_near_stop')
    self.assertIsNone(result['population'])
  def test_unique_population_not_doubled_across_two_stops(self):
    a,b=coord(0,0),coord(100,0)
    rows=[{'lat':a[1],'lon':a[0]},{'lat':b[1],'lon':b[0]}]
    outcome=self.store.network_coverage(rows)
    self.assertEqual(outcome['population'],50)
    self.assertEqual(outcome['stops_connected'],2)

  def test_persistent_layers(self):
    self.assertTrue(self.store.status()['ready'])
    again=territory.TerritoryStore(Path(self.d.name))
    self.assertEqual(again.status()['walk_segments'],1)
    self.assertEqual(again.status()['resident_units'],2)
  def test_section_population_without_buildings_not_fabricated(self):
    only=territory.TerritoryStore(Path(self.d.name)/'empty')
    only.ingest('census',collection([feat({'type':'Polygon','coordinates':[square(0,0,500)]},municipality='Irun',population=100,section_id='a')]))
    self.assertFalse(only.status()['ready'])
    self.assertEqual(len(only.residents),0)

  def test_section_population_uses_walk_network_anchors_without_buildings(self):
    only=territory.TerritoryStore(Path(self.d.name)/'area')
    only.ingest('census',collection([feat({'type':'Polygon','coordinates':[square(0,0,500)]},municipality='Irun',population=100,section_id='a')]))
    w=feat({'type':'LineString','coordinates':[coord(x,0) for x in [0,150,300,450,600,750,900,1100]]},highway='footway')
    only.ingest('walkways',collection([w]))
    result=only.stop(*reversed(coord(0,0)))
    self.assertFalse(only.status()['area_interpolation_ready'])
    self.assertTrue(only.status()['population_access_ready'])
    self.assertTrue(only.status()['ready'])
    self.assertGreater(result['population'],0)
    self.assertEqual(result['population_method'],'census_walk_network_anchor')

  def test_origin_in_middle_of_long_edge_reaches_nearby_population(self):
    network=territory.WalkNetwork([feat({'type':'LineString','coordinates':[coord(-1200,0),coord(1200,0)]},highway='footway')])
    iso=network.isochrone(*reversed(coord(0,0)),minutes=5)
    resident={'id':'r','municipality':'Irun','population':25,
              'point':Point(*territory.TO_LOCAL(*coord(10,0))),'edge_index':0}
    result=territory.calculate_population(iso,[resident],network)
    self.assertEqual(result['population'],25)

  def test_population_is_independent_from_display_buffer(self):
    network=territory.WalkNetwork([feat({'type':'LineString','coordinates':[coord(0,0),coord(1000,0)]},highway='footway')])
    resident={'id':'r','municipality':'Irun','population':40,
              'point':Point(*territory.TO_LOCAL(*coord(300,0))),'edge_index':0}
    thin=network.isochrone(*reversed(coord(0,0)),minutes=5,display_buffer_m=5)
    wide=network.isochrone(*reversed(coord(0,0)),minutes=5,display_buffer_m=75)
    self.assertNotEqual(round(thin['display_area_m2']),round(wide['display_area_m2']))
    self.assertEqual(territory.calculate_population(thin,[resident],network)['population'],40)
    self.assertEqual(territory.calculate_population(wide,[resident],network)['population'],40)

  def test_bundled_provincial_census_geometry_matches_eustat(self):
    path=Path(__file__).resolve().parent/'data'/'real'/'geography'/'census.geojson'
    with path.open(encoding='utf-8') as handle:doc=json.load(handle)
    self.assertEqual(len(doc['features']),544)
    self.assertEqual(sum(f['properties']['population'] for f in doc['features']),724797)
    self.assertEqual(len({f['properties']['municipality'] for f in doc['features']}),88)

if __name__=='__main__':unittest.main()
