# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Synthetic structural tests; these objects are not paper scientific proposals."""
import copy, json, tempfile, unittest
from pathlib import Path
from auto_trial_v9 import AutoRunV9, inventory, new_items, shared_execution_lock, explicitly_no_effect, validate_definition_additions

def synthetic_plan():
    return {'target_interpretation': {'h1': 'Synthetic unit-test statement'}, 'families': [{'id': 'F1', 'comparison_definition': {'evaluation': {'plot_group': 'C1', 'plot_title': 'Synthetic effect', 'plot_unit': 'coefficient', 'effect_kind': 'difference', 'null_value': 0, 'direction_multiplier': 1, 'grouping_reason': 'same synthetic question'}}, 'dimensions': [{'key': 'D1', 'options': [{'id': 'O1', 'description': 'Synthetic operation one', 'parameters': {'test_value': 1}, 'data_binding': {'columns': ['x']}, 'method_refs': []}]}], 'output_contract': {'inference': {'policy': 'not_identifiable', 'test_name': 'synthetic unavailable', 'null_hypothesis': 'synthetic zero', 'alternative': 'two_sided', 'alpha': 0.05}}}]}

def ledger(kind='new_option', key='D1', oid='O2'):
    return {'kind': kind, 'family_id': 'F1', 'decision_key': key, 'option_id': oid, 'status': 'accepted', 'basis': 'general_methodological', 'source_refs': [], 'scientific_rationale': 'Synthetic structural test rationale', 'distinctness': 'Synthetic parameters differ', 'parameter_domain': 'Explicit finite synthetic values', 'data_equivalence': 'unknown', 'equivalence_reason': 'No actual paper data used in this structural test', 'changes_point_estimate': True, 'inference_only': False, 'why_not_existing_decision': 'Synthetic structural test of a newly missing degree of freedom' if kind == 'new_decision' else None}

class CoverageTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runner = AutoRunV9.__new__(AutoRunV9)
        self.runner.out = Path(self.temp.name)
        self.runner.cfg = {'max_specifications': 512}
        self.runner.original_validate = lambda o: []
        (self.runner.out / 'historical_source_catalog.json').write_text('{}', encoding='utf-8')
        self.before = synthetic_plan()
        self.after = copy.deepcopy(self.before)
        self.after['families'][0]['dimensions'][0]['options'].append({'id': 'O2', 'description': 'Synthetic operation two', 'parameters': {'test_value': 2}, 'data_binding': {'columns': ['x']}, 'method_refs': []})
        self.result = {'expanded_plan': self.after, 'expansion_review': {'change_ledger': [ledger()], 'limitations': []}}

    def validate(self):
        return self.runner.validate_expansion(self.result, self.before)

    def test_new_option_with_complete_receipt_is_valid(self):
        self.assertEqual(self.validate(), [])

    def test_h1_cannot_change(self):
        self.after['target_interpretation']['h1'] = 'Changed'
        self.assertTrue(any(('H1' in e for e in self.validate())))

    def test_comparison_axis_cannot_change(self):
        self.after['families'][0]['comparison_definition']['evaluation']['null_value'] = 1
        self.assertTrue(any(('axis' in e for e in self.validate())))

    def test_missing_added_option_receipt_is_rejected(self):
        self.result['expansion_review']['change_ledger'] = []
        self.assertTrue(any(('exactly one' in e for e in self.validate())))

    def test_phantom_accepted_entry_is_rejected(self):
        self.result['expansion_review']['change_ledger'].append(ledger(oid='O3'))
        self.assertTrue(any(('exactly one' in e for e in self.validate())))

    def test_known_equivalent_option_is_rejected(self):
        self.result['expansion_review']['change_ledger'][0]['data_equivalence'] = 'equivalent'
        self.assertTrue(any(('equivalent' in e for e in self.validate())))

    def test_historical_claim_requires_source(self):
        self.result['expansion_review']['change_ledger'][0]['basis'] = 'historical'
        self.assertTrue(any(('actual source' in e for e in self.validate())))

    def test_existing_option_is_not_silently_rewritten(self):
        self.after['families'][0]['dimensions'][0]['options'][0]['parameters']['test_value'] = 9
        self.assertTrue(any(('preserve existing' in e for e in self.validate())))

    def test_duplicate_operation_with_renamed_id_is_rejected(self):
        self.after['families'][0]['dimensions'][0]['options'][1] = dict(copy.deepcopy(self.after['families'][0]['dimensions'][0]['options'][0]), id='O2')
        self.assertTrue(any(('byte-identical' in e for e in self.validate())))

    def test_new_decision_needs_specific_explanation(self):
        dimension = {'key': 'D2', 'options': [{'id': 'X1', 'description': 'Synthetic third operation', 'parameters': {}, 'data_binding': {}, 'method_refs': []}]}
        self.after['families'][0]['dimensions'].append(dimension)
        self.result['expansion_review']['change_ledger'] += [ledger('new_decision', 'D2', None), ledger('new_option', 'D2', 'X1')]
        self.assertEqual(self.validate(), [])
        self.result['expansion_review']['change_ledger'][1]['why_not_existing_decision'] = None
        self.assertTrue(any(('New Decision' in e for e in self.validate())))

    def test_no_safe_expansion_can_remain_small(self):
        self.result = {'expanded_plan': self.before, 'expansion_review': {'change_ledger': [], 'limitations': [], 'no_safe_expansion_reason': 'Synthetic case with no justified additional choices'}}
        self.assertEqual(self.validate(), [])

    def test_resource_limit_is_not_silent_truncation(self):
        self.runner.cfg['max_specifications'] = 1
        self.assertTrue(any(('resource limit' in e for e in self.validate())))

    def test_inventory_counts_cartesian_space_not_new_decision_count(self):
        self.assertEqual(inventory(self.after)['raw_combinations'], 2)
        self.assertEqual(new_items(self.before, self.after), {('new_option', 'F1', 'D1', 'O2')})

    def test_shared_execution_lock_releases(self):
        p = Path(self.temp.name) / 'shared.lock'
        with shared_execution_lock(p):
            self.assertTrue(p.exists())
        with shared_execution_lock(p):
            pass

    def test_partial_coverage_write_keeps_original_baseline(self):
        from auto_trial_v8 import save, read
        save(self.runner.out / 'option_coverage_before.json', self.before)
        save(self.runner.out / 'option_coverage_review.json', self.result)
        save(self.runner.out / 'candidate_plan_raw.json', self.after)
        save(self.runner.out / 'plan_output_contract.json', {})
        self.runner.original_plan = lambda: self.fail('Saved original coverage baseline was discarded')
        self.runner.log = lambda *a, **k: None
        self.runner.expand_options()
        receipt = read(self.runner.out / 'option_coverage_receipt.json')
        self.assertEqual(receipt['before']['raw_combinations'], 1)
        self.assertEqual(receipt['after_expansion_before_preflight']['raw_combinations'], 2)
        self.assertEqual(read(self.runner.out / 'option_coverage_before.json'), self.before)

    def test_boolean_profile_does_not_change_input_data(self):
        import pandas as pd
        from auto_trial_v8 import read, sha
        p = self.runner.out / 'input.csv'
        p.write_text('flag,value\nTrue,1\nFalse,2\nTrue,3\n', encoding='utf-8')
        self.runner.cfg['data'] = {'path': str(p)}
        before = sha(p)
        method = pd.Series.quantile
        self.runner.prepare()
        profile = read(self.runner.out / 'data_structure_profile.json')
        self.assertEqual(sha(self.runner.out / 'data.csv'), before)
        self.assertIs(pd.Series.quantile, method)
        self.assertEqual(profile['columns'][0]['dtype'], 'bool')
        self.assertEqual(profile['columns'][0]['quantiles']['0.5'], 1.0)

    def test_unknown_metric_is_not_reinterpreted_as_unsuitable(self):
        for value in [None, 'unknown', 'unclear', '', 'Pearson correlation']:
            self.assertFalse(explicitly_no_effect({'metric_family': value}))
        for value in ['none', 'no_statistical_effect', 'not applicable', 'no-statistical-effect-magnitude']:
            self.assertTrue(explicitly_no_effect({'metric_family': value}))

    def test_explicit_no_effect_creates_a_real_suitability_block(self):
        from auto_trial_v8 import save, read
        save(self.runner.out / 'effect_scope_public.json', {'metric_family': 'none', 'null_value': 0})
        with self.assertRaises(RuntimeError):
            self.runner.require_declared_effect()
        self.assertTrue(read(self.runner.out / 'suitability_block.json')['numeric_null_placeholder_is_not_an_effect'])

    def test_preexecution_amendment_only_adds_missing_definitions(self):
        after = copy.deepcopy(self.before)
        after['families'][0]['dimensions'][0]['options'][0]['parameters']['new_synthetic_definition'] = 'explicit'
        errors, added = validate_definition_additions(self.before, after)
        self.assertEqual(errors, [])
        self.assertEqual(len(added), 1)
        after['families'][0]['dimensions'][0]['options'][0]['parameters']['test_value'] = 99
        self.assertTrue(validate_definition_additions(self.before, after)[0])

    def test_preexecution_amendment_cannot_change_effect_or_choices(self):
        for mutate in [lambda p: p['families'][0]['comparison_definition']['evaluation'].update(null_value=1), lambda p: p['families'][0]['dimensions'][0]['options'].append({'id': 'O9'})]:
            after = copy.deepcopy(self.before)
            mutate(after)
            self.assertTrue(validate_definition_additions(self.before, after)[0])

    def test_preexecution_amendment_cannot_follow_even_a_failed_receipt(self):
        dest = self.runner.out / 'isolated_execution/execution_round_0/results'
        dest.mkdir(parents=True)
        (dest / 'S0001.json').write_text('{"status":"failed"}', encoding='utf-8')
        with self.assertRaises(RuntimeError):
            self.runner.assert_preexecution_revision_safe()

    def test_independent_metadata_keeps_all_data_and_only_field_definitions(self):
        from auto_trial_v8 import save, read, sha
        source = self.runner.out / 'input.csv'
        source.write_text('x,flag\n1,True\n2,False\n', encoding='utf-8')
        metadata = self.runner.out / 'metadata.json'
        save(metadata, {'source_url': 'https://example.invalid/data-codebook', 'field_metadata': [{'name': 'x', 'source_label': 'Synthetic measured value', 'unit': 'synthetic units'}], 'missing_code': '.'})
        self.runner.cfg['data'] = {'path': str(source), 'column_metadata': str(metadata)}
        self.runner.prepare()
        self.assertEqual(sha(source), sha(self.runner.out / 'data.csv'))
        p = read(self.runner.out / 'data_structure_profile.json')
        self.assertEqual(p['column_count'], 2)
        self.assertEqual(p['independent_column_metadata']['field_metadata'][0]['source_label'], 'Synthetic measured value')

    def test_independent_metadata_rejects_analysis_fields(self):
        from auto_trial_v8 import save
        source = self.runner.out / 'input.csv'
        source.write_text('x\n1\n', encoding='utf-8')
        metadata = self.runner.out / 'metadata.json'
        save(metadata, {'field_metadata': [{'name': 'x', 'source_label': 'Synthetic'}], 'preferred_regression_formula': 'forbidden synthetic recipe'})
        self.runner.cfg['data'] = {'path': str(source), 'column_metadata': str(metadata)}
        with self.assertRaises(ValueError):
            self.runner.prepare()
if __name__ == '__main__':
    unittest.main(verbosity=2)
