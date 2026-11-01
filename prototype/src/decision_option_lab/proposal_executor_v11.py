# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Technical copy of the v7 official-Boba executor with completed-receipt monitoring.

Scientific scripts and worker validation are unchanged. A stuck CLI cannot keep a
completed batch waiting for two hours. Original logs/failed receipts are retained.
"""
import ast, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path
from importlib.metadata import version
import blind_five_trial_v7 as core

def load(p):
    return json.loads(p.read_text(encoding='utf-8'))

def save(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def execute_guarded():
    core.implement()
    out = core.OUT
    if (out / 'blind_results_lock.json').exists():
        return core.read('execution_results_round_0.json')
    runtime = out / 'isolated_execution'
    runtime.mkdir(exist_ok=True)
    for name in ['data.csv', 'specifications.json', 'specification_plan.json', 'specification_lock.json', 'analysis_round_0.py']:
        dst = runtime / name
        if dst.exists():
            assert sha(dst) == sha(out / name)
        else:
            shutil.copy2(out / name, dst)
    shutil.copy2(core.WORKER_SOURCE_PATH or Path(core.__file__).with_name('blind_five_worker_v7.py'), runtime / 'blind_five_worker_v7.py')
    execution_round = core.read('technical_execution_revision.json')['execution_round'] if (out / 'technical_execution_revision.json').exists() else 0
    work = runtime / f'execution_round_{execution_round}'
    work.mkdir(exist_ok=True)
    specs = core.read('specifications.json')['specifications']
    expected = {s['spec_id'] for s in specs}
    config = {'graph': ['Run'], 'decisions': [{'var': 'SPEC_ID', 'options': [repr(s['spec_id']) for s in specs]}]}
    template = '# --- (BOBA_CONFIG)\n' + json.dumps(config, ensure_ascii=False, indent=2) + '\n\n# --- (Run)\nimport sys\nsys.path.insert(0,' + repr(str(runtime)) + ')\nfrom blind_five_worker_v7 import run_one\nSPEC_ID = {{SPEC_ID}}\nrun_one(' + repr(str(runtime)) + ',SPEC_ID,execution_round=' + str(execution_round) + ')\n'
    path = work / 'boba_template.py'
    path.write_text(template, encoding='utf-8')
    if not (work / 'multiverse').exists():
        compile_run = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'boba.cli', 'compile', '--script', str(path), '--out', str(work)], capture_output=True, text=True, encoding='utf-8', timeout=180)
        (work / 'compiler.log').write_text(compile_run.stdout + '\n' + compile_run.stderr, encoding='utf-8')
        if compile_run.returncode:
            raise RuntimeError('Official Boba compilation failed')
    multiverse = work / 'multiverse'
    bindings = []
    for script in multiverse.rglob('universe_*.py'):
        tree = ast.parse(script.read_text(encoding='utf-8'))
        assignment = next((n for n in tree.body if isinstance(n, ast.Assign) and any((isinstance(t, ast.Name) and t.id == 'SPEC_ID' for t in n.targets))))
        bindings.append(ast.literal_eval(assignment.value))
    assert sorted(bindings) == sorted(expected)
    save(multiverse / 'lang.json', {'python': {'ext': ['py'], 'run': [sys.executable, '-X', 'utf8', '{{script_name}}']}})
    results_folder = work / 'results'

    def receipts():
        return [load(p) for p in sorted(results_folder.glob('S*.json'))]

    def all_final(rows):
        return len(rows) == len(expected) and {r['spec_id'] for r in rows} == expected and all((r.get('inference_contract_checked') or r['status'] == 'failed' for r in rows))
    prior = receipts()
    stalled_existing = all_final(prior)
    if stalled_existing:
        if not (work / 'boba_run.log').exists():
            raise RuntimeError('Receipts without official run log cannot be silently adopted')
        completion = 'resumed_collection_of_completed_official_boba_receipts'
        returncode = None
    else:
        safe = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT'}}
        temp = runtime / 'temp'
        temp.mkdir(exist_ok=True)
        safe.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', TEMP=str(temp), TMP=str(temp))
        with (work / 'boba_run.log').open('w', encoding='utf-8') as log:
            command = [sys.executable, '-X', 'utf8', '-m', 'boba.cli', 'run', '--all', '--jobs', '8', '--dir', str(multiverse)]
            proc = subprocess.Popen(command, cwd=runtime, env=safe, stdout=log, stderr=subprocess.STDOUT)
            started = time.monotonic()
            ready_since = None
            completion = 'normal_cli_exit'
            while proc.poll() is None:
                current = receipts()
                if all_final(current):
                    if ready_since is None:
                        ready_since = time.monotonic()
                    if time.monotonic() - ready_since > 30:
                        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, timeout=30)
                        completion = 'controller_terminated_after_all_final_receipts'
                        break
                if time.monotonic() - started > 7200:
                    subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, timeout=30)
                    raise RuntimeError('Boba task exceeded bound; partial receipts kept')
                time.sleep(2)
            returncode = proc.wait(timeout=30)
    rows = receipts()
    if not all_final(rows):
        raise RuntimeError('Incomplete official-Boba receipt set')
    result = {'execution_attempt': execution_round, 'boba_version': version('boba'), 'official_boba_compile': True, 'official_boba_run': True, 'boba_returncode': returncode, 'scheduler_completion': completion, 'count': len(rows), 'success': sum((r['status'] == 'success' for r in rows)), 'failed': sum((r['status'] != 'success' for r in rows)), 'results': rows}
    core.save('execution_results_round_0.json', result)
    core.save('blind_results_lock.json', {'utc': core.now(), 'results_sha256': sha(out / 'execution_results_round_0.json'), 'plan_sha256': sha(out / 'specification_plan.json'), 'source_sha256': sha(out / 'analysis_round_0.py'), 'success': result['success'], 'failed': result['failed'], 'author_numeric_candidates_accessed': False, 'scheduler_completion': completion})
    core.event('blind_results_frozen', success=result['success'], failed=result['failed'])
    print('BOBA RESULTS', result['success'], result['failed'], completion, flush=True)
    return result
