# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Windows-safe resumption of the existing bounded execution-repair path.

New runtime directory for the one retry: never rename an active Windows working
directory, never discard the first real receipts, never change the frozen plan.
"""
import argparse, shutil, os
from pathlib import Path
from proposal_trial_v11 import FastProposalRun
from proposal_executor_v12 import execute_guarded
from auto_trial_v9 import shared_execution_lock
from auto_trial_v8 import read, save, sha, now, ROOT

class WindowsProposalRun(FastProposalRun):

    def __init__(self, path):
        super().__init__(path)
        self.original_execute = execute_guarded
        self.state['invocations'][-1]['windows_executor_sha256'] = sha(Path(__file__).with_name('proposal_executor_v12.py'))
        self.persist()

    def recover_archived_implementation(self):
        archive = self.out / 'runtime_repair_attempt_0'
        stage = self.state['stages'].get('06_scientific_code_and_review', {})
        missing = not (self.out / 'blind_code_lock.json').exists()
        if missing and (archive / 'blind_code_lock.json').exists() and (archive / 'execution_results_round_0.json').exists():
            for p, h in stage.get('outputs', {}).items():
                original = archive / Path(p).name
                if not original.exists() or sha(original) != h:
                    raise RuntimeError('Interrupted repair archive does not match the completed code checkpoint')
            result = read(archive / 'execution_results_round_0.json')
            self.set_feedback(result)
            stage.setdefault('prior_output_versions', []).append({'utc': now(), 'outputs': stage.get('outputs', {}), 'reason': 'Resume interrupted Windows directory move; originals retained in runtime_repair_attempt_0'})
            stage.update(status='pending', reason='Continue the already-authorized bounded implementation repair')
            self.persist()

    def set_feedback(self, result):
        failures = [{k: r.get(k) for k in ['spec_id', 'error_type', 'error', 'traceback']} for r in result['results'] if r['status'] != 'success']
        self.runtime_feedback = {'failed_paths': failures, 'instruction': 'Repair implementation under identical frozen choices/parameters; no successful effect sizes or author results supplied. Check contrast estimability with redundant nuisance columns.'}

    def step(self, name, fn, outputs=()):
        if name == '06_scientific_code_and_review':
            self.recover_archived_implementation()
        return super().step(name, fn, outputs)

    def execute(self):
        archive = self.out / 'runtime_repair_attempt_0'
        slot = 'auto_v9_boba_execution.lock' if os.environ.get('PROPOSAL_BOBASLOT') == 'primary' else 'auto_v12_boba_additional_slot.lock'
        with shared_execution_lock(ROOT / 'work' / slot, lambda: self.log('waiting_for_shared_boba_execution_slot', parallel_boba_limit=2)):
            if (archive / 'execution_results_round_0.json').exists():
                result = execute_guarded(self.out / 'isolated_execution_retry_1')
                if not result['success']:
                    raise RuntimeError('No successful effects after the single bounded runtime repair')
                self.refresh_code_checkpoint()
                return
            first = execute_guarded()
            if not first['failed']:
                return
            declarations = read(self.out / 'blind_code_lock.json').get('partial_execution', [])
            expected = set()
            for d in declarations:
                if d.get('status') != 'failed_receipt_expected' or 'donor count k' not in str(d.get('reason')):
                    continue
                for spec in read(self.out / 'specifications.json')['specifications']:
                    if spec['group_id'] == d.get('family_id') and spec['choices'].get(d.get('decision_key')) == d.get('option_id'):
                        expected.add(spec['spec_id'])
            failures = [r for r in first['results'] if r['status'] != 'success']
            if failures and all((r['spec_id'] in expected and 'donor count k' in str(r.get('error')) for r in failures)):
                save(self.out / 'declared_unavailable_paths.json', {'utc': now(), 'source': 'Pre-execution independent code review, unchanged declared capability', 'failed_spec_ids': [r['spec_id'] for r in failures], 'not_repaired_by_inventing_scientific_parameters': True, 'included_in_effect_or_p_denominator': False, 'declarations': declarations})
                self.log('predeclared_unavailable_paths_retained', count=len(failures), no_redundant_api_repair=True)
                return
            archive.mkdir(exist_ok=True)
            for name in ['execution_results_round_0.json', 'blind_results_lock.json', 'analysis_round_0.py', 'blind_code_lock.json']:
                source = self.out / name
                copy = archive / name
                if source.exists():
                    if copy.exists() and sha(source) != sha(copy):
                        raise RuntimeError('Refusing to replace an earlier repair archive')
                    shutil.copy2(source, copy)
            self.set_feedback(first)
            save(archive / 'repair_receipt.json', {'utc': now(), 'frozen_plan_sha256': sha(self.out / 'specification_plan.json'), 'first_success': first['success'], 'first_failed': first['failed'], 'original_runtime_unchanged': True, 'retry_runtime': 'isolated_execution_retry_1', 'no_author_reference_opened': True})
            for name in ['execution_results_round_0.json', 'blind_results_lock.json', 'analysis_round_0.py', 'blind_code_lock.json']:
                (self.out / name).unlink(missing_ok=True)
            self.implementation()
            result = execute_guarded(self.out / 'isolated_execution_retry_1')
            if not result['success']:
                raise RuntimeError('No successful effects after the single bounded runtime repair')
            self.refresh_code_checkpoint()
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['run', 'amend', 'replay'])
    p.add_argument('--manifest', required=True)
    a = p.parse_args()
    if a.action == 'replay':
        from auto_report_v8 import build_report
        c = read(a.manifest)
        print(build_report(Path(c['output']), Path(c['report']), Path(c['quarantine'])))
    else:
        r = WindowsProposalRun(a.manifest)
        if a.action == 'amend':
            r.amend_preexecution_contract()
        r.run()
