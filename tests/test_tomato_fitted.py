import csv
import json
import math
import unittest
from pathlib import Path
from src.tomato_predictor import predict_tomato, load_data
from src.tomato_fitted_model import load_fitted_model, curve_value, fit_curve, infer_stage, observations_digest
from scripts.build_tomato_fitted_model import build

ROOT=Path(__file__).resolve().parents[1]

class TomatoFittedTests(unittest.TestCase):
    def predict(self,temp=5,hardness=62,**extra):
        return predict_tomato(dict(storage_temperature_c=temp,firmness=hardness,**extra))

    def test_zero_and_five_now_use_fitted_trends(self):
        for t in (0,2.5,5,7.5,10,12.5,15,20,25):
            r=self.predict(t)
            self.assertEqual(r['prediction_method'],'tomato_pooled_fitted_inference')
            self.assertEqual(r['status'],'fitted_estimate')
            self.assertIsNotNone(r['estimated_remaining_days'])
            self.assertGreaterEqual(r['estimated_remaining_days'],0)
            self.assertLessEqual(r['estimated_remaining_days'],r['reference_total_days'])
            self.assertEqual(len(r['matched_curve']),24)
            self.assertTrue(all(p['observed_n']==0 for p in r['matched_curve']))
            self.assertIn('低可信度',r['confidence_label'])
            json.dumps(r,allow_nan=False)

    def test_five_baseline_anchored_without_imputed_training(self):
        model=load_fitted_model()
        observed=[p for p in load_data()['firmness'] if p['metric']=='integer']
        self.assertEqual(model['training_group_count'],len(observed))
        baseline=next(p for p in observed if p['temperature']==5)
        self.assertAlmostEqual(curve_value(model,5,0)['integer_mean'],baseline['mean'])
        r=self.predict()
        self.assertEqual(len(r['firmness_sources']),1)
        self.assertIn('借用',r['decision'])

    def test_missing_values_exported_separately(self):
        with (ROOT/'data/tomato_fitted_daily.csv').open(encoding='utf-8-sig') as source:
            rows=list(csv.DictReader(source))
        self.assertEqual(len(rows),144)
        five=[p for p in rows if p['temperature_c']=='5' and p['day']!='0']
        self.assertEqual(len(five),23)
        self.assertTrue(all(p['observed_integer_mean']=='' and p['observed_n']=='0' for p in five))
        self.assertTrue(all(float(p['fitted_ft11'])>0 for p in rows))
        self.assertTrue(all('not_individual_measurement' in p['value_kind'] for p in rows))

    def test_exact_rebuild_and_honest_baseline_comparison(self):
        model=load_fitted_model(); rebuilt=build(load_data())
        def compare(a,b):
            if isinstance(a,dict):
                self.assertEqual(set(a),set(b))
                for k in a: compare(a[k],b[k])
            elif isinstance(a,list):
                self.assertEqual(len(a),len(b))
                for x,y in zip(a,b): compare(x,y)
            elif isinstance(a,float): self.assertAlmostEqual(a,b,places=8)
            else: self.assertEqual(a,b)
        for key in ('intercepts','linear','curvature','validation'):
            compare(model[key],rebuilt[key])
        validation=model['validation']
        self.assertFalse(validation['beats_constant_baseline'])
        self.assertGreater(validation['loo_rmse_integer'],validation['baseline_loo_rmse_integer'])
        self.assertEqual(len(validation['held_out_groups']),19)
        self.assertEqual(observations_digest(load_data()),model['observations_sha256'])

    def test_hardness_and_temperature_both_change_prediction(self):
        for t in range(0,26,5):
            self.assertLess(self.predict(t,61)['estimated_remaining_days'],self.predict(t,63)['estimated_remaining_days'])
        results=[self.predict(t)['estimated_remaining_days'] for t in range(0,26,5)]
        self.assertEqual(results,sorted(results,reverse=True))

    def test_temperature_interpolation_is_continuous(self):
        for t in (5,10,15,20):
            a=self.predict(t-1e-5)['estimated_remaining_days']
            b=self.predict(t+1e-5)['estimated_remaining_days']
            self.assertLess(abs(a-b),.001)

    def test_full_reading_range_finite_and_extrapolation_labeled(self):
        for t in (0,5,10,15,20,25):
            for h in (40,50,60,70,80,90):
                r=self.predict(t,h)
                self.assertTrue(math.isfinite(r['estimated_remaining_days']))
                self.assertTrue(0<=r['estimated_remaining_days']<=r['reference_total_days'])
                bounds=r['remaining_days_range']
                self.assertTrue(0<=bounds['min']<=bounds['max']<=r['reference_total_days'])
                json.dumps(r,allow_nan=False)
        self.assertEqual(self.predict(5,90)['status'],'fitted_extrapolation')
        self.assertIn('外推',self.predict(5,90)['decision'])

    def test_unknown_endpoint_still_not_invented(self):
        r=self.predict(failure_threshold=.30)
        self.assertEqual(r['status'],'reference_endpoint_unavailable')
        self.assertIsNone(r['estimated_remaining_days'])
        self.assertEqual(len(r['matched_curve']),24)

    def test_no_fit_reads_independent_g_per_mm_as_ft11(self):
        original=load_data()
        modified=dict(original,firmness=[dict(p,mean=p['mean']*100) if p['metric']=='g_per_mm' else dict(p) for p in original['firmness']])
        self.assertEqual(build(original)['intercepts'],build(modified)['intercepts'])

    def test_prior_and_error_scale_are_explicit_not_zero_uncertainty(self):
        model=load_fitted_model()
        a=infer_stage(model,5,210,15.75)
        b=infer_stage(model,5,210,15.75,horizon=15.75)
        self.assertNotEqual(a['remaining_mean'],b['remaining_mean'])
        self.assertGreater(a['remaining_range']['max']-a['remaining_range']['min'],1)
        self.assertIn('uniform',str(model['assumptions']))

if __name__=='__main__':unittest.main()
