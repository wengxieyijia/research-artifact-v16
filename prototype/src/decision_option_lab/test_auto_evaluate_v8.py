# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Evaluation and isolation regression tests using explicit synthetic receipts, never paper results."""
import copy, json, subprocess, sys, tempfile, unittest, urllib.error
from unittest.mock import patch
from pathlib import Path
from auto_evaluate_v8 import classify, evaluate, evaluate_run

def spec(sid='S1', choice='O1', kind='difference', null=0, mult=1, group='C1', unit='coefficient', policy='formal_test'):
    return {'spec_id': sid, 'group_id': 'F1', 'choices': {'D_METHOD': choice}, 'selected_options': {'D_METHOD': {'id': choice, 'parameters': {}}}, 'comparison_definition': {'evaluation': {'plot_group': group, 'plot_title': 'A common scientific question', 'plot_unit': unit, 'effect_kind': kind, 'null_value': null, 'direction_multiplier': mult}}, 'output_contract': {'inference': {'policy': policy, 'test_name': 'frozen synthetic test', 'alpha': 0.05, 'alternative': 'two_sided'}}}

def receipt(sid='S1', effect=0.2, p=0.01, null=0, status='formal_test'):
    return {'spec_id': sid, 'status': 'success', 'result': {'effect_size': effect, 'p_value': p, 'ci_lower': None, 'ci_upper': None, 'inference': {'status': status, 'test_name': 'frozen synthetic test', 'alpha': 0.05, 'alternative': 'two_sided', 'null_value': null, 'reason': 'P not identified in this synthetic receipt' if p is None else ''}}}

class EvaluationTests(unittest.TestCase):

    def test_NA_not_counted_as_nonsignificant(self):
        ss = [spec('S1'), spec('S2', choice='O2'), spec('S3', choice='O3', policy='not_identifiable'), spec('S4', choice='O4')]
        rr = [receipt('S1', 0.2, 0.01), receipt('S2', -0.3, 0.4), receipt('S3', 0.5, None, status='not_identifiable'), {'spec_id': 'S4', 'status': 'failed', 'error': 'invalid data'}]
        ev, rows = evaluate(ss, rr, [])
        s = ev['groups'][0]['raw_paths']
        self.assertEqual((s['total_paths'], s['successful_effects'], s['failed_paths'], s['valid_tests'], s['p_unavailable']), (4, 3, 1, 2, 1))
        self.assertEqual(s['significant_fraction'], 0.5)
        self.assertEqual(s['positive_fraction'], 2 / 3)
        self.assertEqual(s['nonsignificant_count'], 1)

    def test_all_NA_yields_NA_not_zero_percent(self):
        s = spec(policy='not_identifiable')
        ev, _ = evaluate([s], [receipt(p=None, status='not_identifiable')], [])
        self.assertIsNone(ev['groups'][0]['raw_paths']['significant_fraction'])

    def test_ratio_null_is_one(self):
        s = spec(kind='ratio', null=1, unit='odds ratio')
        self.assertEqual(classify(s, receipt(effect=0.8, null=1))['direction'], 'negative')
        self.assertEqual(classify(s, receipt(effect=1, null=1))['direction'], 'zero')
        self.assertEqual(classify(s, receipt(effect=1.2, null=1))['direction'], 'positive')

    def test_direction_reversal_is_frozen(self):
        self.assertEqual(classify(spec(mult=-1), receipt(effect=0.2))['direction'], 'negative')

    def test_p_value_requires_a_frozen_inference_policy(self):
        r = classify(spec(policy='not_identifiable'), receipt())
        self.assertEqual(r['p_status'], 'invalid')
        self.assertIsNone(r['significant'])

    def test_conditional_formal_test_is_explicit(self):
        self.assertEqual(classify(spec(policy='conditional_formal_test'), receipt(status='conditional_formal_test'))['p_status'], 'valid')

    def test_alpha_is_not_silently_changed(self):
        r = receipt()
        r['result']['inference']['alpha'] = 0.1
        self.assertEqual(classify(spec(), r)['p_status'], 'invalid')

    def test_bad_p_and_nonfinite_effect(self):
        for bad in [-0.1, 1.1, float('nan'), True]:
            self.assertEqual(classify(spec(), receipt(p=bad))['p_status'], 'invalid')
        self.assertEqual(classify(spec(), receipt(effect=float('inf')))['status'], 'failed')

    def test_distinct_choices_not_deduplicated_by_equal_effect(self):
        ev, _ = evaluate([spec('S1'), spec('S2', 'O2')], [receipt('S1'), receipt('S2')], [])
        s = ev['groups'][0]
        self.assertEqual(s['structural_configurations']['total_paths'], 2)
        self.assertEqual(s['unique_numerical_effects_12dp'], 1)

    def test_identical_structural_configurations_can_be_counted_once(self):
        ev, _ = evaluate([spec('S1'), spec('S2')], [receipt('S1'), receipt('S2')], [])
        self.assertEqual(ev['groups'][0]['raw_paths']['total_paths'], 2)
        self.assertEqual(ev['groups'][0]['structural_configurations']['total_paths'], 1)

    def test_analysis_options_do_not_create_extra_curves(self):
        ev, _ = evaluate([spec('S1'), spec('S2', 'O2')], [receipt('S1'), receipt('S2')], [])
        self.assertEqual(ev['overall_path_inventory']['plot_groups'], 1)

    def test_incompatible_units_cannot_be_silently_pooled(self):
        with self.assertRaises(ValueError):
            evaluate([spec('S1'), spec('S2', kind='ratio', null=1, unit='odds ratio')], [receipt('S1'), receipt('S2', effect=1.2, null=1)], [])

    def test_author_thresholds_and_unreported_significance(self):
        ref = {'family_id': 'F1', 'same_scientific_question': True, 'author_reported_direction': 'positive', 'author_significance': 'not_reported', 'reported_alpha': None}
        ev, _ = evaluate([spec()], [receipt()], [ref])
        s = ev['groups'][0]['raw_paths']
        self.assertEqual(s['author_direction_comparison']['agreement_fraction'], 1)
        self.assertIsNone(s['author_significance_comparison']['agreement_fraction'])
        ref.update(author_significance='significant', reported_alpha=0.1)
        ev, _ = evaluate([spec()], [receipt()], [ref])
        self.assertIsNone(ev['groups'][0]['raw_paths']['author_significance_comparison']['agreement_fraction'])
        ref['reported_alpha'] = 0.05
        ev, _ = evaluate([spec()], [receipt()], [ref])
        self.assertEqual(ev['groups'][0]['raw_paths']['author_significance_comparison']['agreement_fraction'], 1)

    def test_missing_or_duplicate_receipts_are_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([spec()], [], [])
        with self.assertRaises(ValueError):
            evaluate([spec()], [receipt(), receipt()], [])

    def test_independent_result_hash_is_enforced(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / 'blind_results_lock.json').write_text(json.dumps({'results_sha256': 'wrong'}))
            (p / 'execution_results_round_0.json').write_text('{}')
            with self.assertRaises(ValueError):
                evaluate_run(p)

class IsolationTests(unittest.TestCase):

    def test_real_file_and_network_audit_hook(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            runtime = root / 'runtime'
            runtime.mkdir()
            (runtime / 'execution_round_0/results').mkdir(parents=True)
            (runtime / 'temp').mkdir()
            secret = root / 'author_only.txt'
            secret.write_text('must not be read')
            code = "import sys,socket\nfrom pathlib import Path\nfrom blind_five_worker_v7 import install_guard\nruntime=Path(sys.argv[1]);secret=Path(sys.argv[2]);denied=[]\ninstall_guard(runtime,denied,0)\nfor action in [lambda:secret.read_text(),lambda:socket.create_connection(('127.0.0.1',9),timeout=.1)]:\n try:action();raise AssertionError('Access guard did not block forbidden access')\n except PermissionError:pass\nassert len(denied)==2\nprint('file_and_network_denied')\n"
            p = subprocess.run([sys.executable, '-c', code, str(runtime), str(secret)], cwd=Path(__file__).parent, capture_output=True, text=True, timeout=30)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn('file_and_network_denied', p.stdout)

class OrchestrationTests(unittest.TestCase):

    def make_runner(self, root):
        from auto_trial_v8 import AutoRun
        runner = AutoRun.__new__(AutoRun)
        runner.out = Path(root)
        runner.state_path = runner.out / 'run_state.json'
        runner.state = {'stages': {}}
        runner.events = []
        runner.log = lambda event, **kwargs: runner.events.append((event, kwargs))
        return runner

    def test_completed_checkpoint_cannot_accept_a_changed_result(self):
        from auto_trial_v8 import sha
        with tempfile.TemporaryDirectory() as d:
            r = self.make_runner(d)
            p = Path(d) / 'frozen.json'
            p.write_text('{}')
            r.state['stages']['done'] = {'status': 'complete', 'outputs': {str(p): sha(p)}}
            p.write_text('{"changed":true}')
            with self.assertRaises(RuntimeError):
                r.step('done', lambda: self.fail('Changed artifact was silently trusted'))

    def test_transport_retry_keeps_material_and_resumes(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.make_runner(d)
            calls = []

            def transport(*args, **kwargs):
                calls.append(copy.deepcopy(args[3]))
                if len(calls) == 1:
                    raise urllib.error.URLError('synthetic connection interrupted')
                return {'accepted': True}
            r.original_task = transport
            with patch('auto_trial_v8.time.sleep'):
                self.assertEqual(r.call('synthetic', 'instruction', {}, {'metadata': 'unchanged'}, lambda o: [], zone='metadata_boundary_only'), {'accepted': True})
            self.assertEqual(calls, [{'metadata': 'unchanged'}] * 2)
            self.assertEqual(r.events[0][0], 'model_transport_retry')

    def test_independent_science_is_closed_after_result_freeze(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.make_runner(d)
            (Path(d) / 'blind_results_lock.json').write_text('{}')
            r.original_task = lambda *a, **k: self.fail('Author unblinding boundary crossed')
            with self.assertRaises(RuntimeError):
                r.call('new_science', '', {}, {}, lambda o: [])

    def test_five_input_source_slots_cannot_be_replaced(self):
        from auto_trial_v8 import KEYS
        with tempfile.TemporaryDirectory() as d:
            r = self.make_runner(d)
            base = {k: {} for k in KEYS}
            base[KEYS[4]] = {'contract': {'unit': 'test unit'}, 'derived_current_trial': {}}
            (Path(d) / 'five_inputs.json').write_text(json.dumps(base), encoding='utf-8')
            changed = copy.deepcopy(base)
            changed[KEYS[1]] = {'unauthorized': 'replacement'}
            r.original_task = lambda *a, **k: self.fail('Replaced source was forwarded')
            with self.assertRaises(ValueError):
                r.call('new_science', '', {}, changed, lambda o: [])
if __name__ == '__main__':
    unittest.main(verbosity=2)
