import unittest
from datetime import datetime, timezone
from cat_stats.standalone import next_feed, robot_metrics, synthetic_states, Petlibro
from cat_stats.ha import value

NOW = datetime(2026,9,24,1,tzinfo=timezone.utc)


class StandaloneTests(unittest.TestCase):
    def test_feed_schedule_timezone_and_disabled(self):
        plans = [{'enable':True,'executionTime':'22:00','repeatDay':'[3]', 'timezone':'America/New_York'},
                 {'enable':False,'executionTime':'21:05','repeatDay':'[]', 'timezone':'America/New_York'}]
        self.assertEqual(next_feed(plans,NOW), '2026-09-24T02:00:00+00:00')
        self.assertIsNone(next_feed([{'enable':True,'executionTime':'99:00'}],NOW))

    def test_missing_robot_fields_remain_unknown(self):
        class Robot:
            status = 'Ready'
            def to_dict(self):
                return {'state':{'isOnline':True,'dfiLevelPercent':34,'isHopperInstalled':False}}
        data = robot_metrics(Robot())
        self.assertEqual(data['waste_pct'],34)
        self.assertIsNone(data['litter_pct'])
        self.assertIs(data['hopper_connected'],False)

    def test_standalone_normalization_matches_ha(self):
        config = {'devices':[{'id':'f','kind':'fountain'}],'pets':[]}
        mapped, states = synthetic_states(config,{'f':{'today_ml':146,'online':True}},NOW)
        self.assertEqual(value(states,mapped['devices'][0]['entities']['today_ml'],'today_ml'),146)
        self.assertIs(value(states,'f.online','online'),True)

    def test_petlibro_missing_totals_never_become_zero(self):
        client = Petlibro('America/New_York')
        client.token = 'test'
        client.call = lambda path,body: {'online':True,'weightPercent':64} if 'realInfo' in path else {}
        result = client.device({'serial':'test','kind':'fountain','model':'PLWF106'},NOW)
        self.assertIsNone(result['today_ml'])
        self.assertEqual(result['water_pct'],64)

    def test_feeder_uses_latest_success_not_response_order(self):
        client = Petlibro('America/New_York')
        client.token = 'test'
        def call(path,body):
            if path == '/device/workRecord/list':
                return [{'workRecords':[
                    {'type':'GRAIN_OUTPUT_SUCCESS','recordTime':(NOW.timestamp()-50)*1000},
                    {'type':'GRAIN_OUTPUT_SUCCESS','recordTime':(NOW.timestamp()-10)*1000},
                    {'type':'ERROR','recordTime':NOW.timestamp()*1000}]}]
            return {}
        client.call = call
        result = client.device({'serial':'test','kind':'feeder','model':'PLAF203'},NOW)
        self.assertEqual(result['last_feed_at'],'2026-09-24T00:59:50+00:00')


if __name__ == '__main__':
    unittest.main()
