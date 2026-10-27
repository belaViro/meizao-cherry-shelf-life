import unittest
from src.tomato_predictor import predict_tomato
from src.hardness_conversion import map_handheld_to_g_mm2
from app import create_app

class FT11ConversionTests(unittest.TestCase):
    def predict(self, reading=62, **kwargs):
        return predict_tomato(dict(storage_temperature_c=10,firmness=reading,**kwargs))

    def test_default_integer_input_maps_ft11_before_matching(self):
        r=self.predict()
        self.assertEqual(r['firmness_unit'],'handheld')
        self.assertEqual(r['handheld_hardness'],62)
        self.assertAlmostEqual(r['firmness_ft11'],(62-32.714)/.14)
        self.assertEqual(r['firmness_g_mm2'],r['firmness_ft11'])
        self.assertTrue(r['model_version'].endswith('ft11-v2'))
        self.assertEqual(r['status'],'matched')
        old=self.predict(firmness_metric='integer')
        self.assertEqual(r['estimated_remaining_days'],old['estimated_remaining_days'])
        self.assertNotEqual(r['matched_curve'],old['matched_curve'])
        for p in r['firmness_sources']:
            self.assertEqual(p['metric'],'integer')
            self.assertAlmostEqual(p['mean'],map_handheld_to_g_mm2(p['original_integer_mean']))
            self.assertEqual(p['value_kind'],'mapped_integer_group_mean')

    def test_explicit_handheld_and_known_mapping(self):
        for h in (40,62,70,90):
            r=self.predict(h,firmness_unit='handheld')
            self.assertAlmostEqual(r['firmness_ft11'],map_handheld_to_g_mm2(h))
        self.assertAlmostEqual(self.predict(70)['firmness_ft11'],266.32857142857)

    def test_mapping_recomputed_server_side_not_trusted(self):
        r=self.predict(firmness_unit='handheld',firmness_ft11=999999,firmness_g_mm2=999999)
        self.assertAlmostEqual(r['firmness_ft11'],209.1857142857)

    def test_integer_enforced_no_clamping_or_rounding(self):
        for h in (None,True,False,39,91,62.5,'',[],{},float('nan'),float('inf')):
            with self.subTest(h=h),self.assertRaises(ValueError): self.predict(h)
        self.assertEqual(self.predict('62')['handheld_hardness'],62)

    def test_conflicting_scale_rejected(self):
        with self.assertRaises(ValueError):self.predict(firmness_unit='handheld',firmness_metric='g_per_mm')
        with self.assertRaises(ValueError):self.predict(firmness_unit='unknown')

    def test_reading_changes_prediction_not_just_display(self):
        self.assertLess(self.predict(61)['estimated_remaining_days'],self.predict(63)['estimated_remaining_days'])

    def test_endpoint_validates_and_returns_conversion(self):
        app=create_app({'TESTING':True,'CSRF_ENABLED':False})
        with app.test_client() as client:
            for h,expected in ((62,200),(62.5,400),(39,400),(91,400)):
                r=client.post('/predict',json=dict(product='cherry_tomato',storage_temperature_c=10,firmness=h,firmness_unit='handheld'))
                self.assertEqual(r.status_code,expected)
                if expected==200:self.assertAlmostEqual(r.get_json()['firmness_ft11'],209.1857142857)

if __name__=='__main__':unittest.main()
