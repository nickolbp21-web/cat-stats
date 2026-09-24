import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from cat_stats.store import Store
from cat_stats.ha import collect, value

NOW = datetime(2026, 9, 24, 1, tzinfo=timezone.utc)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / 'test.sqlite'))
        self.tz = ZoneInfo('America/New_York')
        self.devices = [{'id': 'a'}, {'id': 'b'}]

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_seven_calendar_days_multi_fountain_and_restarts(self):
        today = NOW.astimezone(self.tz).date()
        for n in range(7):
            for d in ['a', 'b']:
                self.store.daily(d, today-timedelta(days=n), 10, n > 0, NOW.isoformat())
        self.store.db.commit()
        self.store.db.close()
        self.store = Store(str(Path(self.tmp.name) / 'test.sqlite'))
        result = self.store.hydration(self.devices, NOW, self.tz)
        self.assertEqual(result['today_ml'], 20)
        self.assertEqual(result['seven_days_ml'], 140)

    def test_missing_day_is_unknown_not_zero(self):
        self.store.daily('a', NOW.astimezone(self.tz).date(), 10, False, NOW.isoformat())
        result = self.store.hydration(self.devices, NOW, self.tz)
        self.assertIsNone(result['today_ml'])
        self.assertIsNone(result['seven_days_ml'])

    def test_event_deduplication_and_no_counter_double_count(self):
        event = {'source':'test','device':'a','event_id':'1','at':NOW.isoformat(),'amount_ml':18}
        self.store.event(event, NOW)
        self.store.event(event, NOW)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM events').fetchone()[0], 1)
        result = self.store.hydration(self.devices, NOW, self.tz)
        self.assertEqual(result['last_ml'], 18)
        self.assertIsNone(result['today_ml'])
        self.assertEqual(result['last_at_local'], '09/23 21:00')

    def test_invalid_and_future_event_rejected(self):
        for value in [float('nan'), -1, True]:
            with self.assertRaises(ValueError):
                self.store.event({'source':'s','device':'a','event_id':'1','at':NOW.isoformat(),'amount_ml':value}, NOW)
        with self.assertRaises(ValueError):
            self.store.event({'source':'s','device':'a','event_id':'1','at':(NOW+timedelta(days=1)).isoformat(),'amount_ml':1}, NOW)

    def test_units_unknown_and_false(self):
        states = {'s': {'state':'1','attributes':{'unit_of_measurement':'L'}}, 'b':{'state':'off'}}
        self.assertEqual(value(states, 's', 'today_ml'), 1000)
        self.assertIsNone(value(states, 's', 'water_pct'))
        self.assertIsNone(value(states, 'missing', 'today_ml'))
        self.assertIs(value(states, 'b', 'online'), False)

    def test_unavailable_current_counter_does_not_reuse_history(self):
        config = {'devices':[{'id':'a','kind':'fountain','name':'A','entities':{'today_ml':'sensor.a'}}]}
        self.store.daily('a', NOW.astimezone(self.tz).date(), 20, False, NOW.isoformat())
        data = collect(config, {'sensor.a':{'state':'unavailable'}}, self.store, NOW, self.tz)
        self.assertIsNone(data['hydration']['today_ml'])

    def test_midnight_old_counter_not_assigned_to_new_day(self):
        config = {'devices':[{'id':'a','kind':'fountain','name':'A','entities':{'today_ml':'s'}}]}
        states = {'s': {'state':'10','last_updated':'2026-09-23T03:59:00Z','attributes':{'unit_of_measurement':'mL'}}}
        data = collect(config, states, self.store, NOW, self.tz)
        self.assertIsNone(data['hydration']['today_ml'])

    def test_priority_and_pet_names(self):
        config = {'pets':[{'id':'p','name':'Custom Name'}], 'devices':[
            {'id':'a','kind':'fountain','name':'Kitchen','entities':{'water_pct':'w'}},
            {'id':'b','kind':'litter','name':'Robot','entities':{'online':'o'}}]}
        data = collect(config, {'w':{'state':'5','attributes':{'unit_of_measurement':'%'}},'o':{'state':'off'}}, self.store, NOW, self.tz)
        self.assertEqual(data['alerts'][0]['title'], 'DEVICE OFFLINE')
        self.assertEqual(data['pets'][0]['name'], 'Custom Name')

    def test_dst_calendar_boundaries(self):
        winter = datetime(2026,11,2,4,30,tzinfo=timezone.utc)
        self.store.daily('a', winter.astimezone(self.tz).date(), 8, False, winter.isoformat())
        self.assertEqual(self.store.hydration([{'id':'a'}],winter,self.tz)['today_ml'],8)


if __name__ == '__main__':
    unittest.main()
