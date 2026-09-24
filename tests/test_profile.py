import unittest
from datetime import date
from cat_stats.profile import pet_age
from cat_stats.standalone import robot_metrics

class ProfileTests(unittest.TestCase):
    def test_birthday_boundaries(self):
        self.assertEqual(pet_age('2018-08-09',date(2026,9,23)),{'age_years':8,'age_days':45})
        self.assertEqual(pet_age('2018-08-09',date(2026,8,9)),{'age_years':8,'age_days':0})
        self.assertEqual(pet_age('2018-08-09',date(2026,8,8)),{'age_years':7,'age_days':364})
        self.assertEqual(pet_age('2020-02-29',date(2025,2,28)),{'age_years':5,'age_days':0})
        self.assertEqual(pet_age('invalid',date(2026,9,23)),{})
        self.assertEqual(pet_age('2027-01-01',date(2026,9,23)),{})
    def test_hopper_status_is_not_fullness(self):
        class Robot:
            status='Ready'
            def to_dict(self):
                return {'state':{'isOnline':True,'hopperStatusIndicator':{'title':'Litter Low','value':'LITTER_LOW'}}}
        result=robot_metrics(Robot())
        self.assertEqual(result['hopper_status'],'Litter Low')
        self.assertNotIn('hopper_pct',result)
