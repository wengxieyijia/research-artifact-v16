# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Resume only missing frozen Boba scripts. Based on resume_missing_card_v13.py.

No changes to science, choices, sources, successful receipts, or private inputs.
"""
import argparse, ast, concurrent.futures, json, os, subprocess, sys, time
from pathlib import Path
from proposal_trial_v12 import WindowsProposalRun
from proposal_executor_v12 import execute_guarded
from auto_trial_v8 import read, save, sha, now

def resume(manifest, runtime_name, jobs=4):
    runner = WindowsProposalRun(manifest)
    out = runner.out
    runtime = out / runtime_name
    work = runtime / 'execution_round_0'
    if (out / 'author_reference.json').exists():
        raise RuntimeError('Use ordinary checkpoint replay after author unblinding')
    lock = read(out / 'blind_code_lock.json')
    assert lock['source_sha256'] == sha(out / 'analysis_round_0.py') == sha(runtime / 'analysis_round_0.py')
    assert lock['plan_sha256'] == sha(out / 'specification_plan.json') == sha(runtime / 'specification_plan.json')
    for name, stage in runner.state['stages'].items():
        if name[:2] <= '06' and stage.get('status') == 'complete':
            assert all((Path(p).exists() and sha(p) == h for p, h in stage.get('outputs', {}).items())), name
    scripts = {}
    for script in (work / 'multiverse').rglob('universe_*.py'):
        tree = ast.parse(script.read_text(encoding='utf-8'))
        assignment = next((n for n in tree.body if isinstance(n, ast.Assign) and any((isinstance(t, ast.Name) and t.id == 'SPEC_ID' for t in n.targets))))
        sid = ast.literal_eval(assignment.value)
        if sid in scripts:
            raise RuntimeError('Duplicate compiled universe ' + sid)
        scripts[sid] = script
    expected = {s['spec_id'] for s in read(out / 'specifications.json')['specifications']}
    assert set(scripts) == expected
    existing = {}
    for receipt in (work / 'results').glob('S*.json'):
        row = read(receipt)
        assert row['spec_id'] == receipt.stem and (row.get('inference_contract_checked') or row['status'] == 'failed')
        existing[receipt.stem] = sha(receipt)
    assert set(existing) <= expected
    missing = sorted(expected - set(existing))
    print('Missing compiled universes', missing, flush=True)
    receipt_path = out / 'missing_compiled_paths_resume_v15.json'
    record = {'utc': now(), 'user_request': 'Resume remaining papers and deliver five reports', 'runtime_folder': str(runtime), 'missing_spec_ids': missing, 'previous_receipt_hashes': existing, 'source_sha256': lock['source_sha256'], 'statistical_code_changed': False, 'mode': 'Official Boba compilation/run already attempted; execute only the missing unchanged compiled scripts', 'completed_missing': []}
    save(receipt_path, record)
    safe = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT'}}
    (runtime / 'temp').mkdir(exist_ok=True)
    safe.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', TEMP=str(runtime / 'temp'), TMP=str(runtime / 'temp'))

    def run(sid):
        start = time.monotonic()
        with (work / ('resume_v15_' + sid + '.log')).open('w', encoding='utf-8') as log:
            proc = subprocess.run([sys.executable, '-X', 'utf8', str(scripts[sid])], cwd=runtime, env=safe, stdout=log, stderr=subprocess.STDOUT, timeout=1200)
        if proc.returncode or not (work / 'results' / (sid + '.json')).exists():
            raise RuntimeError('Missing-path execution failed: ' + sid)
        return {'spec_id': sid, 'seconds': round(time.monotonic() - start, 2)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(run, sid): sid for sid in missing}
        for future in concurrent.futures.as_completed(futures):
            item = future.result()
            record['completed_missing'].append(item)
            save(receipt_path, record)
            print('Resumed exact frozen universe', item, flush=True)
    assert all((sha(work / 'results' / (sid + '.json')) == h for sid, h in existing.items()))
    record['previous_receipts_unchanged'] = True
    record['completed'] = now()
    save(receipt_path, record)
    result = execute_guarded(runtime)
    result['compiled_missing_path_resume'] = record
    save(out / 'execution_results_round_0.json', result)
    result_lock = read(out / 'blind_results_lock.json')
    result_lock['results_sha256'] = sha(out / 'execution_results_round_0.json')
    save(out / 'blind_results_lock.json', result_lock)
    print('Collected frozen receipts', result['count'], result['success'], result['failed'], flush=True)
    if runner.state.get('paused_reason'):
        runner.state['prior_user_pause'] = {'reason': runner.state.pop('paused_reason'), 'resumed': now(), 'authorization': 'Current user requested remaining two papers'}
        runner.persist()
    runner.run()
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', required=True)
    p.add_argument('--runtime', required=True)
    p.add_argument('--jobs', type=int, default=4)
    a = p.parse_args()
    resume(a.manifest, a.runtime, a.jobs)
