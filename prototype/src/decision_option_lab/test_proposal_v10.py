# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Synthetic control-flow checks; these are not paper results or statistical tests."""
import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from proposal_trial_v10 import ProposalRun, legacy
from auto_trial_v8 import save
from auto_evaluate_v8 import classify

class CaseAdapterTests(unittest.TestCase):

    def make(self, root):
        r = ProposalRun.__new__(ProposalRun)
        r.out = Path(root)
        r.runtime_feedback = None
        r.log = lambda *a, **k: None
        r.data_conditions = lambda: {}
        save(r.out / 'specification_plan.json', {'families': []})
        save(r.out / 'specifications.json', {'specifications': [{'spec_id': 'S1'}]})
        return r

    def test_repairs_continue_after_last_revision_and_preserve_originals(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.make(d)
            for n in range(3):
                (r.out / f'analysis_revision_{n}.py').write_text('old ' + str(n), encoding='utf-8')
                save(r.out / f'scientific_code_review_revision_{n}.json', {'ready': False, 'blocking_issues': ['synthetic blocker']})
            calls = []

            def fake(stage, instruction, contract, material, validator, zone='blind'):
                calls.append((stage, material))
                value = {'source_code': 'def analyze(data,spec):\n    raise ValueError("synthetic fixture")\n'} if stage.startswith('scientific_implementation') else {'ready': True, 'blocking_issues': [], 'partial_execution': ['synthetic unavailable test']}
                self.assertEqual(validator(value), [])
                return value
            r.call = fake
            with patch.object(legacy, 'packet', side_effect=lambda v: v):
                r.implementation()
            self.assertTrue(calls[0][0].endswith('_3'))
            self.assertEqual(calls[0][1]['implementation_feedback']['previous_source'], 'old 2')
            self.assertEqual((r.out / 'analysis_revision_2.py').read_text(encoding='utf-8'), 'old 2')
            self.assertEqual((r.out / 'case_adapter_v10/original_implementation/analysis_revision_2.py').read_text(encoding='utf-8'), 'old 2')
            self.assertEqual(json.loads((r.out / 'blind_code_lock.json').read_text(encoding='utf-8'))['revision'], 3)

    def test_new_execution_policy_cannot_be_introduced_after_outcomes(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.make(d)
            save(r.out / 'execution_results_round_0.json', {})
            with self.assertRaises(RuntimeError):
                r.implementation()

    def test_author_unblinding_blocks_reimplementation(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.make(d)
            save(r.out / 'author_extraction_receipt.json', {})
            with self.assertRaises(RuntimeError):
                r.implementation()

    def test_implementation_unavailable_is_NA_not_NS(self):
        s = {'spec_id': 'S1', 'group_id': 'F1', 'choices': {}, 'selected_options': {}, 'comparison_definition': {'evaluation': {'plot_group': 'C1', 'plot_title': 'Synthetic', 'plot_unit': 'score', 'effect_kind': 'difference', 'null_value': 0, 'direction_multiplier': 1}}, 'output_contract': {'inference': {'policy': 'conditional_formal_test', 'alpha': 0.05, 'alternative': 'two_sided'}}}
        record = {'spec_id': 'S1', 'status': 'success', 'result': {'effect_size': -0.4, 'p_value': None, 'ci_lower': None, 'ci_upper': None, 'inference': {'status': 'unavailable', 'reason': 'Synthetic backend missing'}}}
        row = classify(s, record)
        self.assertEqual(row['p_status'], 'NA')
        self.assertIsNone(row['significant'])
        self.assertEqual(row['direction'], 'negative')
if __name__ == '__main__':
    unittest.main(verbosity=2)
