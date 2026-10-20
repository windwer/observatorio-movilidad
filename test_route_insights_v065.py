import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import engine
import route_insights


class RouteInsightsV065Tests(unittest.TestCase):
    def test_route_metrics_use_shape_and_timetable(self):
        con = engine.connect(ROOT / 'data' / 'demo' / 'observatorio_demo.sqlite3')
        try:
            result = route_insights.route_metrics(con, 'irunbus', 'L1', '2026-10-15')
        finally:
            con.close()
        self.assertEqual(result['status'], 'calculated')
        self.assertGreater(result['distance_km'], 0)
        self.assertGreater(result['commercial_speed_kmh'], 0)
        self.assertGreater(result['runtime_min'], 0)
        self.assertIn('first_departure', result)

    def test_frequency_is_grouped_by_public_line_and_week_class(self):
        con = engine.connect(ROOT / 'data' / 'demo' / 'observatorio_demo.sqlite3')
        try:
            result = route_insights.route_frequency_week(con, 'irunbus', 'L1', 2026, 10, '2026-10-15')
        finally:
            con.close()
        self.assertEqual(result['status'], 'calculated')
        self.assertEqual([x['key'] for x in result['points']], ['LJ', 'V', 'S', 'D'])
        self.assertEqual(result['grouped_route_ids'], ['L1'])
        self.assertTrue(all(x['trips_per_day'] is not None for x in result['points']))


if __name__ == '__main__':
    unittest.main()
