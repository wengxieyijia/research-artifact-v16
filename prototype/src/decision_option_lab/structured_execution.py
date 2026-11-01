# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Validate model-generated code/template, official Boba compilation and actual universe execution."""
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from structured_multiverse import ROOT, read, save, ask, digest, file_sha, unique

def code_errors(x, frozen):
    import paper_graph_trial as old
    space = {'decisions': frozen['plan']['execution_decisions']}
    e = old.code_errors(x, space, frozen['freeze'])
    e = [message for message in e if message != 'forbidden attribute rename']
    text = x.get('boba_template', '')
    marker = re.search('#\\s*---\\s*\\(BOBA_CONFIG\\)\\s*\\n(.*?)(?=\\n#\\s*---)', text, re.S)
    if not marker:
        return e + ['Complete model-generated Boba template and BOBA_CONFIG block required']
    try:
        config = json.loads(marker.group(1))
        ds = frozen['plan']['execution_decisions']
        variables = config['decisions']
        if {r.get('var') for r in variables} != {d['id'] for d in ds} or len(variables) != len(ds):
            e.append('Boba must expose every actual execution Decision, not a synthetic SPEC selector')
        for r in variables:
            d = next((d for d in ds if d['id'] == r.get('var')), None)
            if not d:
                continue
            if not r['var'].isidentifier():
                e.append('Boba variable must be a valid identifier')
            values = [ast.literal_eval(v) for v in r.get('options', [])]
            if values != [o['id'] for o in d['options']]:
                e.append('Boba options must retain frozen Decision Option order and IDs for ' + d['id'] + '; expected ' + str([o['id'] for o in d['options']]) + ' got ' + str(values))
        for c in config.get('constraints', []):
            tree = ast.parse(c['condition'], mode='eval')
            allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.Compare, ast.Eq, ast.Constant, ast.Attribute, ast.Name, ast.Load)
            if any((not isinstance(n, allowed) for n in ast.walk(tree))):
                e.append('Boba constraint only allows literal index equalities and and/or')
            if any((isinstance(n, ast.Attribute) and (n.attr != 'index' or not isinstance(n.value, ast.Name) or n.value.id not in {d['id'] for d in ds}) for n in ast.walk(tree))):
                e.append('Invalid Boba constraint attribute')
        if config.get('graph') != ['Setup->Choices->Run']:
            e.append('Use the requested technical Boba block graph')
        rest = text[:marker.start()] + text[marker.end():]
        for d in ds:
            rest = rest.replace('{{' + d['id'] + '}}', repr(d['options'][0]['id']))
        tree = ast.parse(rest)
        imports = [n for n in tree.body if isinstance(n, ast.Import)]
        if len(imports) != 1 or len(imports[0].names) != 1 or imports[0].names[0].name != 'structured_boba_runtime' or (imports[0].names[0].asname != 'runtime'):
            e.append('Template Setup must only import structured_boba_runtime as runtime')
        for n in tree.body:
            if isinstance(n, ast.Import):
                continue
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and (n.targets[0].id == 'CHOICES'):
                ast.literal_eval(n.value)
                continue
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute) and isinstance(n.value.func.value, ast.Name) and (n.value.func.value.id == 'runtime') and (n.value.func.attr == 'run') and (len(n.value.args) == 1) and isinstance(n.value.args[0], ast.Name) and (n.value.args[0].id == 'CHOICES') and (not n.value.keywords):
                continue
            e.append('Template is only the generated choice wrapper; scientific logic belongs in source_code')
        for d in ds:
            if '{{' + d['id'] + '}}' not in text:
                e.append('Template missing Decision placeholder ' + d['id'])
        for p in x.get('parameter_coverage', []):
            for r in p.get('parameters', []):
                if not r.get('code_quote') or r['code_quote'] not in x['source_code']:
                    e.append('Parameter coverage must quote actual code literally')
        coverage = x.get('parameter_coverage', [])
        used = {d + '/' + o for s in frozen['space']['selected_specifications'] for d, o in s.get('execution_choices', s['choices']).items()}
        expected_parameters = {ref: {p['name'] for p in frozen['instances'][ref]['parameters']} for ref in used}
        expected_parameters.update({s['id']: {p['name'] for p in s['parameters']} for s in frozen['plan']['fixed_original_steps']})
        if not unique(coverage, 'instance_id') or {p.get('instance_id') for p in coverage} != set(expected_parameters):
            e.append('Parameter coverage must include every used instance and fixed step')
        for p in coverage:
            missing = expected_parameters.get(p.get('instance_id'), set()) - {r.get('name') for r in p.get('parameters', [])}
            if missing:
                e.append('Do not omit frozen scientific parameters in coverage for ' + str(p.get('instance_id')) + '; missing exact names=' + str(sorted(missing)))
    except (ValueError, KeyError, TypeError, SyntaxError, StopIteration) as exc:
        e.append('Malformed Boba/code contract: ' + str(exc))
    return list(dict.fromkeys(e))

def audit_errors(x, frozen, code):
    e = []
    specs = frozen['space']['selected_specifications']
    used = {d + '/' + o for s in specs for d, o in s.get('execution_choices', s['choices']).items()} | {s['id'] for s in frozen['plan']['fixed_original_steps']}
    groups = {s['group_id'] for s in specs}
    rows = x.get('instance_checks', [])
    checks = x.get('specification_checks', [])
    allids = {s['spec_id'] for s in specs}
    passed = set(x.get('approved_spec_ids', []))
    if not unique(checks, 'spec_id') or {s.get('spec_id') for s in checks} != allids:
        e.append('Audit every frozen path individually')
    if any((type(s.get('approved')) is not bool or not s.get('reason') for s in checks)):
        e.append('Every path audit requires an explicit Boolean and reason')
    if {s.get('spec_id') for s in checks if s.get('approved') is True} != passed:
        e.append('approved_spec_ids must exactly match individual approved checks')
    if not passed <= allids:
        e.append('No invented approved specification')
    if x.get('approved') is True and passed != allids:
        e.append('Global approval requires every frozen path approved')
    if x.get('global_blocking_issues') and passed:
        e.append('Global blockers prohibit all execution')
    if any((s.get('approved') is True and s.get('blocking_issues') for s in checks)):
        e.append('An approved path cannot have blockers')
    byinstance = {r['instance_id']: r for r in rows}
    bygroup = {r['group_id']: r for r in x.get('group_checks', [])}
    for sp in specs:
        if sp['spec_id'] not in passed:
            continue
        needed = {d + '/' + o for d, o in sp.get('execution_choices', sp['choices']).items()} | {s['id'] for s in frozen['plan']['fixed_original_steps']}
        if any((not all((byinstance.get(ref, {}).get(k) is True for k in ['source_identity_preserved', 'core_preserved', 'parameters_faithful', 'no_new_scientific_defaults'])) for ref in needed)):
            e.append('Approved path requires all active source/core/parameter checks: ' + sp['spec_id'])
        if not all((bygroup.get(sp['group_id'], {}).get(k) is True for k in ['target_preserved', 'metric_and_population_comparable', 'inference_appropriate'])):
            e.append('Approved path requires a passing comparison group: ' + sp['spec_id'])
    if x.get('freeze_sha256') != frozen['freeze']['freeze_sha256'] or type(x.get('approved')) is not bool:
        e.append('Audit frozen hash and Boolean approval required')
    if not unique(rows, 'instance_id') or {r.get('instance_id') for r in rows} != used:
        e.append('Audit every used instance and fixed original step exactly once: ' + str(sorted(used)))
    if not unique(x.get('group_checks', []), 'group_id') or {r.get('group_id') for r in x.get('group_checks', [])} != groups:
        e.append('Audit every actual comparison group')
    coverage = x.get('specification_coverage', {})
    if set(coverage.get('spec_ids', [])) != {s['spec_id'] for s in specs} or coverage.get('all_choices_checked') is not True:
        e.append('Audit frozen choices for every selected spec')
    for r in rows:
        if not r.get('reason') or not r.get('code_evidence'):
            e.append('Instance audit requires reasoning and literal code evidence')
        for ev in r.get('code_evidence', []):
            if not ev.get('quote') or ev['quote'] not in code['source_code']:
                e.append('Audit quoted code not found literally')
        if x.get('approved') and any((r.get(k) is not True for k in ['source_identity_preserved', 'core_preserved', 'parameters_faithful', 'no_new_scientific_defaults'])):
            e.append('Approved code must faithfully implement source and frozen settings')
    if x.get('approved'):
        if x.get('blocking_issues'):
            e.append('Approved audit cannot contain blockers')
        if any((r.get(k) is not True for r in x.get('group_checks', []) for k in ['target_preserved', 'metric_and_population_comparable', 'inference_appropriate'])):
            e.append('Approved group checks must pass')
    return e

def compile_template(out, code, frozen, replay=False):
    record = out / 'boba_compilation.json'
    if replay:
        receipt = read(record)
        if receipt['template_sha256'] != digest(code['boba_template']) or receipt['code_sha256'] != digest(code['source_code']):
            raise ValueError('Compiler receipt does not match model template/code')
        for row in receipt['universes']:
            if file_sha(out / row['path']) != row['sha256']:
                raise ValueError('Compiled Boba universe changed')
        return receipt
    i = 1
    while (out / 'boba_compiles' / str(i)).exists():
        i += 1
    folder = out / 'boba_compiles' / str(i)
    folder.mkdir(parents=True)
    if not (folder / 'multiverse').resolve().is_relative_to(out.resolve()) or (folder / 'multiverse').exists():
        raise ValueError('Unsafe official compiler output')
    (out / 'boba_template.py').write_text(code['boba_template'], encoding='utf-8')
    (out / 'generated_analysis.py').write_text(code['source_code'], encoding='utf-8')
    proc = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'boba.cli', 'compile', '--script', str((out / 'boba_template.py').resolve()), '--out', str(folder.resolve())], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
    (folder / 'compiler.log').write_text(proc.stdout + '\n' + proc.stderr, encoding='utf-8')
    if proc.returncode:
        raise ValueError('Official Boba compile failed: ' + proc.stderr[-3000:])
    universes = []
    for f in sorted((folder / 'multiverse').rglob('universe_*.py')):
        tree = ast.parse(f.read_text('utf-8'))
        node = next((n for n in tree.body if isinstance(n, ast.Assign) and any((isinstance(t, ast.Name) and t.id == 'CHOICES' for t in n.targets))))
        choices = ast.literal_eval(node.value)
        universes.append({'path': f.relative_to(out).as_posix(), 'sha256': file_sha(f), 'choices': choices})
    expected = {digest(s['choices']) for s in frozen['space']['selected_specifications']}
    actual = {digest(r['choices']) for r in universes}
    if actual != expected or len(universes) != len(expected):
        raise ValueError('Compiled Boba choices differ from frozen selected paths: expected ' + str(len(expected)) + ' unique choices, got ' + str(len(universes)))
    import importlib.metadata
    receipt = {'official_boba_version': importlib.metadata.version('boba'), 'universes': universes, 'template_sha256': digest(code['boba_template']), 'code_sha256': digest(code['source_code']), 'compiled_choices_match_frozen': True, 'template_author': 'DeepSeek', 'scientific_code_author': 'DeepSeek'}
    save(record, receipt)
    return receipt

def run_universes(out, ctx, frozen, code, compilation, replay=False, rerun=False, eligible_ids=None):
    import paper_graph_trial as old
    specs = [s for s in frozen['space']['selected_specifications'] if eligible_ids is None or s['spec_id'] in eligible_ids]
    key = digest({'freeze': frozen['freeze'], 'code': code['source_code'], 'template': code['boba_template'], 'data': file_sha(out / 'inputs/analysis_data.csv'), 'pre_execution_approved_ids': sorted((s['spec_id'] for s in specs))})
    receipt = out / 'execution_cache' / key / 'results.json'
    groups = frozen['plan']['comparison_groups']
    if receipt.exists() and (not rerun):
        rows = read(receipt)
        if {r['spec_id'] for r in rows} != {s['spec_id'] for s in specs}:
            raise ValueError('Saved real runs do not cover the frozen plan')
        for row in rows:
            if row['status'] == 'ok':
                e = old.result_errors(row['result'], next((s for s in specs if s['spec_id'] == row['spec_id'])), groups)
                if e:
                    raise ValueError('Saved result violates comparison contract: ' + str(e))
        return rows
    if replay:
        raise ValueError('Missing saved actual execution results; replay does not run statistics')
    source_files = {digest(r['choices']): out / r['path'] for r in compilation['universes']}
    before = file_sha(out / 'inputs/analysis_data.csv')
    run_id = 1
    while (out / 'runs' / str(run_id)).exists():
        run_id += 1
    runroot = out / 'runs' / str(run_id)
    runroot.mkdir(parents=True)

    def worker(sp):
        job = runroot / sp['spec_id']
        job.mkdir()
        shutil.copy2(source_files[digest(sp['choices'])], job / 'universe.py')
        (job / 'generated_analysis.py').write_text(code['source_code'], encoding='utf-8')
        save(job / 'job.json', {'data_dir': str((out / 'inputs').resolve()), 'specifications': [sp], 'contract': {'context': ctx, **frozen, 'freeze_sha256': frozen['freeze']['freeze_sha256']}})
        env = {k: v for k, v in os.environ.items() if not any((tag in k.upper() for tag in ['KEY', 'TOKEN', 'SECRET', 'PASSWORD']))}
        env.update(PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        t = time.monotonic()
        try:
            proc = subprocess.run([sys.executable, '-B', str(ROOT / 'structured_worker.py'), str(job.resolve())], cwd=job, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
            (job / 'stdout.txt').write_text(proc.stdout, encoding='utf-8')
            (job / 'stderr.txt').write_text(proc.stderr, encoding='utf-8')
            payload = read(job / 'result.json') if (job / 'result.json').exists() else {'status': 'error', 'error': proc.stderr[-5000:] or 'Compiled universe produced no result'}
            if payload.get('status') == 'ok':
                errors = old.result_errors(payload['result'], sp, groups)
                if errors:
                    payload = {'status': 'error', 'error': errors}
        except subprocess.TimeoutExpired:
            payload = {'status': 'error', 'error': '180-second specification timeout'}
        print('Boba universe ' + sp['spec_id'] + ' ' + payload['status'], flush=True)
        return {'spec_id': sp['spec_id'], 'group_id': sp['group_id'], 'choices': sp['choices'], 'seconds': round(time.monotonic() - t, 3), 'execution_engine': 'official compiled Boba universe', **payload}
    rows = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(worker, s) for s in specs]):
            r = f.result()
            rows[r['spec_id']] = r
    ordered = [rows[s['spec_id']] for s in specs]
    if file_sha(out / 'inputs/analysis_data.csv') != before:
        raise ValueError('Analysis mutated original input')
    for group in groups:
        rr = [r for r in ordered if r['status'] == 'ok' and r['group_id'] == group['id']]
        if group['sample_policy'] == 'same' and len(rr) > 1:
            unitsets = [{json.dumps(v, sort_keys=True) for v in r['result']['analysis_unit_ids']} for r in rr]
            if any((s != unitsets[0] for s in unitsets[1:])):
                for r in rr:
                    r.update(status='error', error='Frozen same-sample comparison violated')
    if receipt.exists():
        history = out / 'execution_history' / key
        history.mkdir(parents=True, exist_ok=True)
        shutil.copy2(receipt, history / (str(len(list(history.glob('*.json'))) + 1) + '.json'))
    save(receipt, ordered)
    save(out / ('execution_attempt_' + str(run_id) + '.json'), ordered)
    return ordered

def compile_with_model_repair(out, code, frozen, replay=False):
    for repair in range(3):
        try:
            return (code, compile_template(out, code, frozen, replay))
        except (ValueError, StopIteration, SyntaxError) as exc:
            if replay or repair == 2:
                raise
            previous = code

            def validate(x):
                candidate = {**previous, 'boba_template': x.get('boba_template', '')}
                errors = code_errors(candidate, frozen)
                match = re.search('#\\s*---\\s*\\(BOBA_CONFIG\\)\\s*\\n(.*?)(?=\\n#\\s*---)', candidate['boba_template'], re.S)
                if match:
                    try:
                        conf = json.loads(match.group(1))
                        if any(('constraints' in d for d in conf.get('decisions', []))):
                            errors.append('Put constraints at BOBA_CONFIG root, never inside a decision')
                        if any((not {'variable', 'index', 'condition'} <= set(c) for c in conf.get('constraints', []))):
                            errors.append('Each official constraint requires variable/index/condition')
                    except ValueError:
                        pass
                return errors
            x = ask('boba_repair_' + digest(code['boba_template'])[:12], 'boba_repair', {'boba_template': 'complete corrected official template', 'reason': 'technical repair only'}, {'previous_template': code['boba_template'], 'frozen_plan': frozen['plan'], 'selected_specifications': frozen['space']['selected_specifications'], 'compiler_error': str(exc), 'scientific_code_sha256_unchanged': digest(code['source_code'])}, validate, out, False)
            code = {**code, 'boba_template': x['boba_template']}
            save(out / ('template_repair_' + str(repair) + '.json'), {'source_code_unchanged': code['source_code'] == previous['source_code'], 'old_template_sha256': digest(previous['boba_template']), 'new_template_sha256': digest(code['boba_template']), 'author': 'DeepSeek'})

def frozen_conflicts(out, frozen):
    """A code revision cannot clear a model-identified contradiction in an unchanged plan."""
    conflicts = {}
    for p in sorted(out.glob('code_audit_[0-9]*.json')):
        if p.name.endswith('_provenance.json'):
            continue
        a = read(p)
        if a.get('freeze_sha256') != frozen['freeze']['freeze_sha256']:
            continue
        for row in a.get('specification_checks', []):
            reasons = [v for v in row.get('blocking_issues', []) if 'scientific_freeze_conflict' in str(v)]
            if reasons:
                conflicts.setdefault(row['spec_id'], []).append({'audit': p.name, 'reasons': reasons})
    save(out / 'freeze_conflict_guard.json', {'freeze_sha256': frozen['freeze']['freeze_sha256'], 'blocked': conflicts, 'rule': 'A model flagged an immutable scientific-plan conflict. Code changes alone cannot clear it; keep the path blocked in this frozen trial.'})
    return conflicts

def execute_plan(out, ctx, index, frozen, replay=False, rerun=False):
    specs = frozen['space']['selected_specifications']
    history = []
    rows = []
    code = None
    audit = None
    saved_accepted = bool(specs and (out / 'accepted_code.json').exists() and (out / 'accepted_audit.json').exists())
    if saved_accepted:
        code = read(out / 'accepted_code.json')
        audit = read(out / 'accepted_audit.json')
        errors = code_errors(code, frozen) + audit_errors(audit, frozen, code)
        if errors:
            raise ValueError('Saved final implementation no longer satisfies frozen contracts: ' + str(errors))
        history = read(out / 'implementation_history.json')
        conflicts = frozen_conflicts(out, frozen)
        eligible = [s for s in audit.get('approved_spec_ids', [s['spec_id'] for s in specs] if audit['approved'] else []) if s not in conflicts]
        if eligible and (out / 'boba_compilation.json').exists():
            compiled = compile_template(out, code, frozen, True)
            rows = run_universes(out, ctx, frozen, code, compiled, replay, rerun, eligible)
        elif replay:
            rows = read(out / 'execution_results.json')
        else:
            saved_accepted = False
    if specs and (not saved_accepted):
        used = {o['source_option_ref'] for d in frozen['plan']['execution_decisions'] for o in d['options'] if any((s.get('execution_choices', s['choices']).get(d['id']) == o['id'] for s in specs))}
        base = {'context': ctx, 'frozen': frozen, 'source_records': {r: index['options'][r] for r in sorted(used)}, 'runtime_api': 'structured_boba_runtime.run(CHOICES) executes generated_analysis.analyze for frozen specs; no scientific defaults in bridge'}
        feedback = None
        previous = None
        for attempt in range(4):
            material = base if attempt == 0 else {**base, 'previous_code': previous, 'failed_only_feedback': feedback}
            code = ask('code_' + str(attempt), 'code', read(ROOT / 'contracts/structured_code.json'), material, lambda x: code_errors(x, frozen), out, replay)
            save(out / ('code_round_' + str(attempt) + '.json'), code)
            audit = ask('code_audit_' + str(attempt), 'code_audit', read(ROOT / 'contracts/structured_code_audit.json'), {**base, 'generated_code': code}, lambda x: audit_errors(x, frozen, code), out, replay)
            history.append({'attempt': attempt, 'audit_approved': audit['approved'], 'code_sha256': digest(code['source_code'])})
            conflicts = frozen_conflicts(out, frozen)
            eligible = [s for s in audit.get('approved_spec_ids', [s['spec_id'] for s in specs] if audit['approved'] else []) if s not in conflicts]
            if not eligible:
                previous = code
                feedback = {'pre_execution_blockers': audit['blocking_issues']}
                continue
            try:
                code, compiled = compile_with_model_repair(out, code, frozen, replay)
            except (ValueError, StopIteration, SyntaxError) as exc:
                if replay:
                    raise
                previous = code
                feedback = {'boba_compile_error': str(exc)}
                continue
            rows = run_universes(out, ctx, frozen, code, compiled, replay, rerun, eligible)
            failures = [r for r in rows if r['status'] == 'error']
            if not failures:
                break
            previous = code
            feedback = [{'spec_id': r['spec_id'], 'error': r.get('error'), 'traceback': r.get('traceback')} for r in failures]
        if code:
            save(out / 'accepted_code.json', code)
        if audit:
            save(out / 'accepted_audit.json', audit)
    returned = {r['spec_id'] for r in rows}
    excluded_reasons = {s['spec_id']: s.get('blocking_issues', []) for s in (audit or {}).get('specification_checks', []) if s.get('approved') is not True}
    conflicts = frozen_conflicts(out, frozen)
    excluded_reasons.update({sid: ['Unresolved model-identified scientific_freeze_conflict in the unchanged plan', records] for sid, records in conflicts.items()})
    rows += [{'spec_id': s['spec_id'], 'group_id': s['group_id'], 'choices': s['choices'], 'status': 'error', 'error': excluded_reasons.get(s['spec_id']) or 'Selected path did not reach execution; see implementation history and audit/compile feedback', 'execution_engine': None} for s in specs if s['spec_id'] not in returned]
    save(out / 'implementation_history.json', history)
    save(out / 'execution_results.json', rows)
    original_ok = file_sha(out / 'inputs/knowledge_graph.json') == read(out / 'input_manifest.json')['catalog_sha256']
    report = {'source_catalog_unchanged': original_ok, 'scientific_graph_or_methods_hand_edited': False, 'new_scientific_decisions_or_options_invented': False, 'selected_specifications': len(specs), 'successful_specifications': sum((r['status'] == 'ok' for r in rows)), 'failed_specifications': sum((r['status'] == 'error' for r in rows)), 'comparison_groups': len({s['group_id'] for s in specs}), 'model_code_audit_approved': audit['approved'] if audit else None, 'pre_execution_approved_specifications': len(set((audit or {}).get('approved_spec_ids', [])) - set(conflicts)), 'pre_execution_blocked_specifications': len(excluded_reasons), 'runtime_failed_specifications': sum((r['status'] == 'error' and r.get('execution_engine') is not None for r in rows)), 'compiled_boba_scripts': len(read(out / 'boba_compilation.json')['universes']) if (out / 'boba_compilation.json').exists() else 0, 'code_and_template_author': 'DeepSeek', 'actual_compiled_boba_execution': any((r.get('execution_engine') == 'official compiled Boba universe' for r in rows)), 'scientific_validity_certified': False}
    if not original_ok:
        raise ValueError('Frozen catalog changed')
    save(out / 'verification.json', report)
    from structured_view import build
    build(out)
