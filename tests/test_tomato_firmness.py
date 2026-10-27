import json
import unittest
from unittest.mock import patch
from src.tomato_predictor import predict_tomato, load_data
from app import create_app

class TomatoFirmnessPredictionTests(unittest.TestCase):
    def predict(self, temp=10, firmness=240, metric='g_per_mm', **extra):
        return predict_tomato(dict(storage_temperature_c=temp, firmness=firmness, firmness_metric=metric, **extra))

    def test_firmness_changes_remaining_time(self):
        a,b=self.predict(firmness=240),self.predict(firmness=250)
        self.assertEqual(a['prediction_method'],'tomato_firmness_stage_matching')
        self.assertEqual(a['status'],'matched')
        self.assertLess(a['estimated_remaining_days'],b['estimated_remaining_days'])
        points=sorted((p for p in load_data()['firmness'] if p['temperature']==10 and p['metric']=='g_per_mm'),key=lambda p:p['day'])
        stage=3*(points[0]['mean']-240)/(points[0]['mean']-points[1]['mean'])
        self.assertAlmostEqual(a['estimated_remaining_days'],14.5-stage,places=4)

    def test_temperature_changes_result(self):
        a,b=self.predict(10,240),self.predict(25,240)
        self.assertNotEqual(a['remaining_days_range'],b['remaining_days_range'])

    def test_nonmonotonic_curve_retains_multiple_solutions(self):
        r=self.predict(25,240)
        self.assertEqual(r['status'],'matched')
        r=self.predict(25,220)
        self.assertEqual(r['status'],'ambiguous')
        self.assertIsNone(r['estimated_remaining_days'])
        self.assertEqual(len(r['candidate_stage_intervals']),2)
        self.assertLess(r['remaining_days_range']['min'],r['remaining_days_range']['max'])

    def test_baseline_only_and_adjacent_temperatures_not_invented(self):
        for temp in (2.5,5,7.5):
            r=self.predict(temp)
            self.assertEqual(r['status'],'insufficient_data')
            self.assertIsNone(r['estimated_remaining_days'])
            self.assertEqual(r['matched_curve'],[])

    def test_temperature_interpolation_uses_common_time_window(self):
        r=self.predict(12.5,240)
        self.assertEqual(r['status'],'matched')
        self.assertEqual([p['day'] for p in r['matched_curve']],[0,2,3])
        self.assertEqual(r['reference_total_days'],12)
        self.assertTrue(9 <= r['estimated_remaining_days'] <= 12)

    def test_outside_curve_does_not_mean_zero_or_fresh(self):
        for h in (1,500,1000):
            r=self.predict(firmness=h)
            self.assertEqual(r['status'],'firmness_out_of_support')
            self.assertIsNone(r['estimated_remaining_days'])

    def test_metric_is_used_without_conversion(self):
        self.assertEqual(self.predict(firmness=62,metric='integer')['status'],'matched')
        self.assertEqual(self.predict(firmness=62)['status'],'firmness_out_of_support')

    def test_all_observed_knots_match_and_deduplicate(self):
        for p in load_data()['firmness']:
            if p['temperature']==5: continue
            r=self.predict(p['temperature'],p['mean'],p['metric'])
            intervals=r['candidate_stage_intervals']
            self.assertTrue(any(i['min']-1e-8 <= p['day'] <= i['max']+1e-8 for i in intervals))
            self.assertEqual(len(intervals),len({(i['min'],i['max']) for i in intervals}))
            json.dumps(r,allow_nan=False)
            self.assertGreaterEqual(r['remaining_days_range']['min'],0)

    def test_flat_segment_is_an_interval_not_unique(self):
        curve=[dict(temperature=10,day=0,mean=240,n=10),dict(temperature=10,day=3,mean=240,n=10)]
        with patch('src.tomato_predictor._observed_curve',return_value=curve):
            r=self.predict()
        self.assertEqual(r['status'],'ambiguous')
        self.assertEqual(r['candidate_stage_intervals'],[dict(min=0,max=3)])
        self.assertEqual(r['remaining_days_range'],dict(min=11.5,max=14.5))

    def test_missing_reference_endpoint(self):
        r=self.predict(failure_threshold=.3)
        self.assertEqual(r['status'],'reference_endpoint_unavailable')
        self.assertIsNone(r['estimated_remaining_days'])

    def test_invalid_and_conflicting_inputs(self):
        for value in (None,True,{},[],0,-1,'',float('nan'),float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError): self.predict(firmness=value)
        with self.assertRaises(ValueError): self.predict(storage_days=2)
        with self.assertRaises(ValueError): predict_tomato(dict(storage_temperature_c=10))

    def test_api_new_mode_and_methods(self):
        app=create_app({'TESTING':True,'CSRF_ENABLED':False})
        client=app.test_client()
        r=client.post('/predict',json=dict(product='cherry_tomato',storage_temperature_c=10,firmness=240,firmness_metric='g_per_mm'))
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.get_json()['status'],'matched')
        self.assertEqual(client.get('/methods').get_json()['tomato_prediction_method'],'tomato_firmness_stage_matching')
        self.assertEqual(client.post('/predict',json=dict(product='cherry_tomato',storage_temperature_c=10)).status_code,400)

if __name__=='__main__':unittest.main()
