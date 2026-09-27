"""Offline tests for demo-only fictional risk scoring."""
import unittest

from demo_profile_fixtures import FICTIONAL_CATEGORIES, catalog
from demo_risk_score import compute_risk_score
from riskscore.riskscore import score_profile


class DemoRiskScoreTests(unittest.TestCase):
    def setUp(self):
        self.profiles = {profile['name']: profile for profile in catalog().values()}

    def test_score_matches_the_riskscore_model_for_the_same_factors(self):
        profile = self.profiles['Alex Morgan']
        result = compute_risk_score(profile['fixture_id'], profile['findings'])
        expected = score_profile(person={**profile['risk_factors'], 'digital_footprint_exposure': 'high'})
        self.assertEqual(result['score'], expected['score'])
        self.assertEqual(result['band'], expected['band'])
        self.assertEqual(result['breakdown'], expected['breakdown'])
        self.assertTrue(1.0 <= result['score'] <= 10.0)

    def test_sensitive_fictional_categories_raise_digital_footprint_exposure(self):
        profile = self.profiles['Sam Taylor']  # minimal coverage, no sensitive categories
        minimal_result = compute_risk_score(profile['fixture_id'], profile['findings'])
        self.assertEqual(minimal_result['factors']['digital_footprint_exposure'], 'low')
        sensitive_finding = next(f for f in self.profiles['Alex Morgan']['findings']
                                  if f['category'] in FICTIONAL_CATEGORIES)
        boosted_result = compute_risk_score(profile['fixture_id'], profile['findings'] + [sensitive_finding])
        self.assertEqual(boosted_result['factors']['digital_footprint_exposure'], 'high')
        self.assertGreater(boosted_result['score'], minimal_result['score'])

    def test_many_findings_alone_also_raise_exposure_without_sensitive_categories(self):
        profile = self.profiles['Jordan Lee']
        non_sensitive = [f for f in profile['findings'] if f['category'] not in FICTIONAL_CATEGORIES]
        self.assertLess(len(non_sensitive), 10)
        padded = non_sensitive + non_sensitive[:1] * (10 - len(non_sensitive))
        result = compute_risk_score(profile['fixture_id'], padded[:10])
        self.assertEqual(result['factors']['digital_footprint_exposure'], 'high')

    def test_caller_supplied_findings_never_override_authored_ground_truth_factors(self):
        profile = self.profiles['Alex Morgan']
        tampered = [{'id': 'fake', 'category': 'age_bracket', 'value': '18-37'}]
        result = compute_risk_score(profile['fixture_id'], tampered)
        self.assertEqual(result['factors']['age_bracket'], profile['risk_factors']['age_bracket'])

    def test_unknown_person_id_raises(self):
        from demo_profile_fixtures import DemoProfileError
        with self.assertRaises(DemoProfileError):
            compute_risk_score('not-a-real-fixture', [])

    def test_score_stays_within_documented_scale_for_every_built_in_profile(self):
        for profile in self.profiles.values():
            with self.subTest(name=profile['name']):
                result = compute_risk_score(profile['fixture_id'], profile['findings'])
                self.assertTrue(1.0 <= result['score'] <= 10.0)
                self.assertIn(result['band'], {'very_low', 'low', 'moderate', 'high', 'very_high'})


if __name__ == '__main__':
    unittest.main()
