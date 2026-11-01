# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Boundary and matching tests, using synthetic records only."""
import unittest
from author_evaluate_v16 import reference_common_decision, path_record, evaluate_author_conclusions

def match(choices=None):
    return {'status': 'eligible', 'allowed_choices': choices or {}, 'reason': 'synthetic scope', 'method_differences': [], 'row_direction_multiplier': 1}

def row(sid='S1', contrast='A', p=0.02):
    return {'spec_id': sid, 'family_id': 'F', 'plot_group': 'G', 'choices': {'contrast': contrast}, 'configuration_key': sid, 'status': 'success', 'p_status': 'valid', 'p_value': p, 'alpha': 0.05, 'direction': 'positive'}

class AuthorEvaluationTests(unittest.TestCase):

    def test_known_p_does_not_require_author_alpha(self):
        self.assertTrue(reference_common_decision({'reported_p_value': 0.004, 'reported_alpha': None})['decision'])
        self.assertFalse(reference_common_decision({'reported_p_value': 0.707, 'reported_alpha': None})['decision'])

    def test_bounds_do_not_become_exact_p(self):
        self.assertTrue(reference_common_decision({'reported_p_value': 0.001, 'p_operator': '<'})['decision'])
        self.assertTrue(reference_common_decision({'reported_p_value': 0.05, 'p_operator': '<'})['decision'])
        self.assertIsNone(reference_common_decision({'reported_p_value': 0.1, 'p_operator': '<'})['decision'])
        self.assertIsNone(reference_common_decision({'reported_p_value': 0.05, 'p_operator': '<='})['decision'])
        self.assertFalse(reference_common_decision({'reported_p_value': 0.05, 'p_operator': '>='})['decision'])

    def test_threshold_and_invalid_values(self):
        self.assertFalse(reference_common_decision({'reported_p_value': 0.05})['decision'])
        self.assertIsNone(reference_common_decision({'reported_p_value': True})['decision'])
        self.assertIsNone(reference_common_decision({'reported_p_value': float('nan')})['decision'])
        self.assertIsNone(reference_common_decision({'reported_p_value': 0, 'p_operator': '<'})['decision'])

    def test_text_only_remains_a_different_metric(self):
        refs = [{'author_significance': 'significant', 'reported_alpha': None, 'author_reported_direction': 'positive'}]
        rules = [{'family_id': 'F', 'reference_index': 0, 'direction_match': match(), 'significance_match': match()}]
        r = path_record(row(), rules, refs, 0.05)
        self.assertIsNone(r['common_alpha_agreement'])
        self.assertTrue(r['reported_conclusion_agreement'])

    def test_multiple_family_references_match_by_choice(self):
        refs = [{'reported_p_value': 0.004, 'author_significance': 'significant'}, {'reported_p_value': 0.334, 'author_significance': 'not_significant'}]
        rules = [{'family_id': 'F', 'reference_index': i, 'direction_match': match({'contrast': [c]}), 'significance_match': match({'contrast': [c]})} for i, c in enumerate(['A', 'B'])]
        a = path_record(row(), rules, refs, 0.05)
        b = path_record(row('S2', 'B', 0.3), rules, refs, 0.05)
        self.assertEqual(a['significance_reference_index'], 0)
        self.assertEqual(b['significance_reference_index'], 1)
        self.assertTrue(a['common_alpha_agreement'])
        self.assertTrue(b['common_alpha_agreement'])

    def test_ambiguous_matches_fail_closed(self):
        rule = {'family_id': 'F', 'reference_index': 0, 'direction_match': match(), 'significance_match': match()}
        r = path_record(row(), [rule, rule], [{'reported_p_value': 0.004}], 0.05)
        self.assertIsNone(r['common_alpha_agreement'])
        self.assertEqual(r['common_alpha_reason_code'], 'ambiguous_reference')

    def test_missing_own_p_is_never_nonsignificant(self):
        r = row(p=None)
        r['p_status'] = 'NA'
        rule = {'family_id': 'F', 'reference_index': 0, 'direction_match': match(), 'significance_match': match()}
        value = path_record(r, [rule], [{'reported_p_value': 0.334, 'author_significance': 'not_significant'}], 0.05)
        self.assertIsNone(value['common_alpha_agreement'])
        self.assertIsNone(value['reported_conclusion_agreement'])

    def test_only_author_fields_change(self):
        old = {'groups': [{'plot_group': 'G', 'raw_paths': {'significant_count': 1, 'author_significance_comparison': None}, 'structural_configurations': {'significant_count': 1, 'author_significance_comparison': None}}]}
        rule = {'family_id': 'F', 'reference_index': 0, 'direction_match': match(), 'significance_match': match()}
        new, _, _ = evaluate_author_conclusions(old, [row()], [{'reported_p_value': 0.004, 'author_significance': 'significant'}], [rule])
        self.assertIsNone(old['groups'][0]['raw_paths']['author_significance_comparison'])
        self.assertEqual(new['groups'][0]['raw_paths']['significant_count'], 1)
        self.assertEqual(new['groups'][0]['raw_paths']['author_significance_comparison']['eligible_paths'], 1)
if __name__ == '__main__':
    unittest.main()
