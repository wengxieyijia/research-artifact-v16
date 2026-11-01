# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Resume only missing, already compiled universes; no statistical code is changed."""
import ast, concurrent.futures, hashlib, json, os, subprocess, sys
from pathlib import Path
from proposal_trial_v12 import WindowsProposalRun
from proposal_executor_v12 import execute_guarded
from auto_trial_v8 import read, save, sha, now
ROOT = Path(__file__).resolve().parents[2]
manifest = ROOT / 'work/batch_v9_20261029/manifests/02_card.json'
runner = WindowsProposalRun(manifest)
out = runner.out
runtime = out / 'isolated_execution'
work = runtime / 'execution_round_0'
lock = read(out / 'blind_code_lock.json')
assert lock['source_sha256'] == sha(out / 'analysis_round_0.py') == sha(runtime / 'analysis_round_0.py')
assert lock['plan_sha256'] == sha(out / 'specification_plan.json')
stage = runner.state['stages']['06_scientific_code_and_review']
archive = out / 'runtime_repair_attempt_0'
if any((sha(p) != h for p, h in stage['outputs'].items())):
    assert all(((archive / Path(p).name).exists() and sha(archive / Path(p).name) == h for p, h in stage['outputs'].items()))
    review = read(out / (lock['review_stage'] + '.json'))
    assert review['ready'] and (not review['blocking_issues'])
    runner.refresh_code_checkpoint()
scripts = {}
for script in (work / 'multiverse').rglob('universe_*.py'):
    tree = ast.parse(script.read_text(encoding='utf-8'))
    assignment = next((n for n in tree.body if isinstance(n, ast.Assign) and any((isinstance(t, ast.Name) and t.id == 'SPEC_ID' for t in n.targets))))
    scripts[ast.literal_eval(assignment.value)] = script
expected = {s['spec_id'] for s in read(out / 'specifications.json')['specifications']}
assert set(scripts) == expected
existing = {p.stem: sha(p) for p in (work / 'results').glob('S*.json')}
missing = sorted(expected - set(existing))
safe = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT'}}
safe.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', TEMP=str(runtime / 'temp'), TMP=str(runtime / 'temp'))

def run(sid):
    with (work / ('resume_' + sid + '.log')).open('w', encoding='utf-8') as log:
        p = subprocess.run([sys.executable, '-X', 'utf8', str(scripts[sid])], cwd=runtime, env=safe, stdout=log, stderr=subprocess.STDOUT, timeout=180)
    if p.returncode or not (work / 'results' / (sid + '.json')).exists():
        raise RuntimeError('Missing-path execution failed: ' + sid)
    return sid
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    for sid in pool.map(run, missing):
        print('Resumed exact compiled universe', sid, flush=True)
assert all((sha(work / 'results' / (sid + '.json')) == h for sid, h in existing.items()))
save(out / 'missing_compiled_paths_resume.json', {'utc': now(), 'missing_spec_ids': missing, 'previous_receipts_unchanged': True, 'statistical_code_changed': False, 'source_sha256': lock['source_sha256'], 'mode': 'Official Boba compile/run followed by direct execution of only missing compiled universes'})
result = execute_guarded()
result['compiled_missing_path_resume'] = read(out / 'missing_compiled_paths_resume.json')
save(out / 'execution_results_round_0.json', result)
results_lock = read(out / 'blind_results_lock.json')
results_lock['results_sha256'] = sha(out / 'execution_results_round_0.json')
save(out / 'blind_results_lock.json', results_lock)
print('Complete actual Card receipts:', result['success'], result['failed'], flush=True)
runner.run()
