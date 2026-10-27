import json
import math
import re
import tempfile
import unittest
from pathlib import Path
from app import create_app
from src.tomato_predictor import load_data, predict_tomato


class TomatoModelTests(unittest.TestCase):
    def predict(self,temperature=5,day=7,**kwargs):
        return predict_tomato(dict(storage_temperature_c=temperature,storage_days=day,**kwargs))

    def test_threshold_reference_points(self):
        for temp,expected in [(0,17.625),(5,15.75),(10,14.5),(15,9.5),(20,7.25),(25,5.25)]:
            with self.subTest(temp=temp):
                result=self.predict(temp,2)
                self.assertAlmostEqual(result['estimated_shelf_life_days'],expected)
                self.assertAlmostEqual(result['estimated_remaining_days'],expected-2)
                self.assertEqual(result['status'],'threshold_interpolation')

    def test_temperature_interpolation_and_unknown_hardness(self):
        r=self.predict(12.5,1)
        self.assertEqual(r['estimated_shelf_life_days'],12)
        self.assertEqual(r['status'],'temperature_interpolation')
        self.assertIsNone(r['firmness']['mean'])
        self.assertEqual(r['firmness']['observed_n'],0)

    def test_first_crossing_preserves_nonmonotonic_observations(self):
        r=self.predict(10,0,failure_threshold=.09)
        self.assertEqual(r['shelf_life_sources'][0]['bracket'][0]['day'],12)
        points=r['ratio_series'][0]['points']
        self.assertEqual(next(p['ratio'] for p in points if p['day']==14),.088)

    def test_unobserved_threshold_is_not_extrapolated(self):
        r=self.predict(failure_threshold=.30)
        self.assertIsNone(r['estimated_shelf_life_days'])
        self.assertIsNone(r['estimated_remaining_days'])
        self.assertEqual(r['status'],'threshold_not_observed')

    def test_unsupported_temperature_threshold_does_not_borrow_one_side(self):
        self.assertIsNone(self.predict(7.5,failure_threshold=.11)['estimated_shelf_life_days'])

    def test_expired_threshold_remaining_zero(self):
        self.assertEqual(self.predict(25,10)['estimated_remaining_days'],0)

    def test_firmness_only_original_values_and_no_unit_conversion(self):
        f=self.predict(0,0)['firmness']
        self.assertEqual(f['status'],'observed_group_mean')
        self.assertEqual(f['observed_n'],23)
        self.assertAlmostEqual(f['mean'],234.8217391304348)
        self.assertEqual(f['unit'],'g/mm')
        self.assertEqual(sum(p['n'] for p in load_data()['firmness']),930)

    def test_firmness_interpolation_and_missing_integer_group(self):
        f=self.predict(0,12)['firmness']
        self.assertEqual(f['status'],'time_interpolation')
        self.assertAlmostEqual(f['mean'],190.72934782608695)
        self.assertEqual(f['observed_n'],0)
        f=self.predict(25,3,firmness_metric='integer')['firmness']
        self.assertEqual(f['status'],'time_interpolation')
        self.assertAlmostEqual(f['mean'],67.2991718426501)

    def test_hypothetical_and_extrapolated_values_labeled(self):
        for temp,day,status,mean in [(5,14,'assumed_scenario',199.139607),(10,9,'extrapolation_scenario',127.316495)]:
            f=self.predict(temp,day)['firmness']
            self.assertEqual(f['status'],status)
            self.assertAlmostEqual(f['mean'],mean,places=5)
            self.assertEqual(f['observed_n'],0)
            self.assertLess(f['scenario_range']['min'],f['mean'])
            self.assertGreaterEqual(f['scenario_range']['max'],f['mean'])
        f=self.predict(5,7,firmness_metric='integer')['firmness']
        self.assertLess(f['scenario_range']['min'],f['mean'])

    def test_firmness_does_not_extrapolate_without_support(self):
        for temp,day in [(0,23),(5,15),(10,10),(15,7),(20,7),(25,6)]:
            self.assertIsNone(self.predict(temp,day)['firmness']['mean'])

    def test_workbook_missing_not_zero_and_ratio_consistency(self):
        data=load_data();records={(r['temperature'],r['day']):r for r in data['ratios']}
        self.assertNotIn((15,11),records)
        repeats={(r['temperature'],r['day']):r for r in data['repeat_counts']}
        for key,r in records.items():self.assertAlmostEqual(r['ratio'],sum(repeats[key]['counts'])/125)

    def test_invalid_inputs(self):
        for key,values in [('storage_temperature_c',[-1,26,None,True,{},'oops',float('nan'),float('inf')]),
                           ('storage_days',[-1,24,None,False,float('nan')]),
                           ('failure_threshold',[0,.31,None,True,float('inf')]),
                           ('firmness_metric',['handheld','g/mm2',None,[]])]:
            for value in values:
                with self.subTest(key=key,value=value):
                    args=dict(storage_temperature_c=5,storage_days=7);args[key]=value
                    with self.assertRaises(ValueError):predict_tomato(args)

    def test_all_supported_grid_outputs_json_finite_and_bounded(self):
        for temp in range(26):
            for day in range(24):
                r=self.predict(temp,day)
                json.dumps(r,allow_nan=False)
                self.assertGreaterEqual(r['estimated_remaining_days'],0)
                if r['firmness']['mean'] is not None:self.assertGreater(r['firmness']['mean'],0)


class TomatoAppTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.app=create_app({'TESTING':True,'SECRET_KEY':'test','DATABASE':str(Path(self.directory.name)/'db.sqlite3'),'CSRF_ENABLED':False})
        self.client=self.app.test_client()
    def tearDown(self):self.directory.cleanup()

    def test_pages_and_metadata(self):
        self.assertIn('/tomato',self.client.get('/').get_data(as_text=True))
        self.assertIn('小番茄预测工作台',self.client.get('/tomato').get_data(as_text=True))
        self.assertIn('cherry_tomato',self.client.get('/methods').get_json()['products'])
        self.assertEqual(self.client.get('/api/tomato/data').get_json()['provenance']['raw_firmness_readings'],930)

    def test_existing_cherry_contract_and_new_product(self):
        cherry=self.client.post('/predict',json={'storage_temperature_c':5,'firmness':70}).get_json()
        self.assertEqual(cherry['estimated_shelf_life_days'],25)
        r=self.client.post('/predict',json={'product':'cherry_tomato','storage_temperature_c':5,'storage_days':7})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.get_json()['estimated_remaining_days'],8.75)
        self.assertNotIn('firmness_g_mm2',r.get_json())
        self.assertNotIn('history_id',r.get_json())

    def test_api_rejects_malformed_and_unknown_product(self):
        for payload in [[],[1],None,42,'hello',{'product':'unknown'},{'product':{}},
                        {'product':'cherry_tomato','storage_temperature_c':'NaN'}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post('/predict',json=payload).status_code,400)

    def test_csrf_required_and_page_token_works(self):
        self.app.config['CSRF_ENABLED']=True
        payload={'product':'cherry_tomato','storage_temperature_c':10,'firmness':240}
        self.assertEqual(self.client.post('/predict',json=payload).status_code,400)
        html=self.client.get('/tomato').get_data(as_text=True)
        token=re.search(r'name="csrf-token" content="([^"]+)"',html).group(1)
        r=self.client.post('/predict',json=payload,headers={'X-CSRF-Token':token})
        self.assertEqual(r.status_code,200)

if __name__=='__main__':unittest.main()
