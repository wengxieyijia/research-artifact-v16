# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Reported paper graph -> catalog expansion -> frozen multiverse -> audited pilot runs."""
import argparse
import ast
import copy
import csv
import itertools
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import lab
import model_runner
import reported_extract
import semantic_stitch as s
import task_graph as t
import priority_trial as priority
ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT.parent / 'Paper_Graph_Expansion_20261024'
BASE = t.BASE

def read(path):
    return lab.read(path)

def save(path, x):
    lab.save(path, x)

def digest(x):
    return lab.sha(lab.dumps(x).encode('utf-8'))

def standard():
    return read(ROOT / 'standards/paper_graph_expansion_v1.json')

def ask(stage, material, validator, out, replay=False):
    cfg = read(ROOT / 'config_high.json')
    cfg['max_structural_repairs'] = 2
    contract = read(ROOT / 'contracts/paper_graph_expansion.json')[stage]
    return model_runner.run_json(stage, (ROOT / 'instructions' / (stage + '.txt')).read_text('utf-8'), standard(), contract, material, cfg, out, validator, replay)

def graph1_errors(x, h1, sources, dataset):
    e = reported_extract.errors(x, h1, sources)
    cols = {c['column_id'] for c in dataset['columns']}
    for d in x.get('decisions', []):
        for o in d.get('options', []):
            triad = o.get('triad', {})
            if not triad.get('method') or not triad.get('data_columns') or (not triad.get('parameters')) or (not triad.get('components')):
                e.append('Every reported Option needs method/data/parameter triad and components')
            for b in triad.get('data_columns', []):
                if b.get('column_id') and b['column_id'] not in cols:
                    e.append('Reported binding invented actual column ID')
                if b.get('status') not in ['reported', 'unknown']:
                    e.append('Original data status reported/unknown only')
            for p in triad.get('parameters', []):
                if p.get('status') not in ['reported', 'unknown'] or 'value' not in p:
                    e.append('Original parameter explicit value/unknown required')
    return e

def prepare_data(out, base, dataset, replay):
    dest = out / 'analysis_input/analysis_data.csv'
    record = out / 'analysis_input_manifest.json'
    if record.exists():
        manifest = read(record)
        if not dest.exists() or s.sha(dest) != manifest['csv_sha256']:
            raise ValueError('Frozen analysis data changed/missing')
        return manifest
    if replay:
        raise ValueError('Replay analysis data missing')
    source = base / dataset['file']
    if not source.exists() or s.sha(source) != dataset['sha256']:
        raise ValueError('Measured original data file missing/changed')
    import pyreadr
    import pandas as pd
    ext = source.suffix.lower()
    if ext in ['.rdata', '.rds']:
        frames = pyreadr.read_r(str(source))
        frame = frames[dataset['table']] if dataset['table'] in frames else next(iter(frames.values()))
    elif ext == '.csv':
        frame = pd.read_csv(source)
    elif ext == '.dta':
        frame = pd.read_stata(source, convert_categoricals=False)
    else:
        raise ValueError('No ordinary trial reader for ' + ext)
    if len(frame) != dataset['rows'] or list(map(str, frame.columns)) != [c['name'] for c in dataset['columns']]:
        raise ValueError('Frame differs from frozen measurements')
    dest.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(dest, index=False)
    manifest = {'file': 'analysis_data.csv', 'csv_sha256': s.sha(dest), 'source_sha256': dataset['sha256'], 'rows': len(frame), 'columns': list(map(str, frame.columns)), 'conversion': 'ordinary complete-table serialization; no selection, pairing, model fitting or source code execution'}
    save(record, manifest)
    return manifest

def apply_expansion(original, patch):
    graph = copy.deepcopy(original)
    for row in patch['added_options']:
        next((d for d in graph['decisions'] if d['id'] == row['decision_id']))['options'].append(copy.deepcopy(row['option']))
    graph['decisions'].extend(copy.deepcopy(patch['new_decisions']))
    graph['dependency_edges'].extend(copy.deepcopy(patch['added_edges']))
    graph['forbidden_combinations'].extend(copy.deepcopy(patch['added_forbidden_combinations']))
    return graph

def original_unchanged(original, expanded):
    for d in original['decisions']:
        found = next((x for x in expanded['decisions'] if x['id'] == d['id']), None)
        if not found:
            return False
        if any((found.get(k) != v for k, v in d.items() if k != 'options')):
            return False
        for o in d['options']:
            if next((x for x in found['options'] if x['id'] == o['id']), None) != o:
                return False
    return all((e in expanded['dependency_edges'] for e in original['dependency_edges']))

def group_errors(groups):
    e = []
    if not groups or not t.unique(groups, 'id'):
        e.append('Nonempty unique comparison groups required')
    for g in groups:
        for key in ['label', 'estimand', 'population', 'analysis_unit', 'contrast', 'outcome', 'effect_scale', 'metric_id', 'direction', 'inference_scope']:
            if not isinstance(g.get(key), str) or not g[key].strip():
                e.append('Comparison group ' + key + ' required')
        if g.get('sample_policy') not in ['same', 'documented_variation']:
            e.append('Explicit same/variable sample policy required')
        if type(g.get('null_value')) not in [int, float]:
            e.append('Numeric comparison null required')
    return e

def expansion_errors(x, original, index, dataset):
    e = t.require(x, ['matching_ledger', 'comparison_groups', 'original_option_status', 'added_options', 'new_decisions', 'added_edges', 'added_forbidden_combinations', 'path_proposals', 'limitations'], 'expansion')
    e += group_errors(x.get('comparison_groups', []))
    mids = {m['method_id']: m for m in index['methods']}
    cols = {c['column_id'] for c in dataset['columns']}
    orig = {d['id']: d for d in original['decisions']}
    new = x.get('new_decisions', [])
    if not t.unique(new, 'id') or set(orig) & {d.get('id') for d in new}:
        e.append('New decision IDs must be unique and not overwrite graph1')
    allids = set(orig) | {d.get('id') for d in new}
    groups = {g['id'] for g in x.get('comparison_groups', [])}
    ledger = {}
    for row in x.get('matching_ledger', []):
        if row.get('anchor_decision') not in set(orig) | {'NEW_OPERATION'} or not row.get('operation'):
            e.append('Retrieval ledger must anchor original decision or declared new operation')
        for c in row.get('candidates', []):
            mid = c.get('method_id')
            m = mids.get(mid, {})
            if not m or c.get('family_id') != m.get('family_id'):
                e.append('Retrieved F/M must exist with original family relation')
            if c.get('status') not in ['selected', 'conditional', 'rejected']:
                e.append('Candidate status required')
            for key in ['function_fit', 'object_fit', 'data_semantic_fit', 'assumption_fit', 'dependency_fit', 'reason']:
                if not c.get(key):
                    e.append('Candidate missing uniform screening factor ' + key)
            if not c.get('component_refs'):
                e.append('Candidate source component references required')
            for ref in c.get('component_refs', []):
                if index['components'].get(ref, {}).get('method_id') != mid:
                    e.append('Retrieved component does not belong to M')
            ledger.setdefault(mid, []).append(c)
    for row in x.get('added_options', []):
        if row.get('decision_id') not in orig:
            e.append('added_options must target an existing graph1 decision')
    added = [(r.get('decision_id'), r.get('option', {})) for r in x.get('added_options', [])] + [(d.get('id'), o) for d in new for o in d.get('options', [])]
    pairs = {(d['id'], o['id']) for d in original['decisions'] for o in d['options']}
    keys = set(pairs)
    for did, o in added:
        key = (did, o.get('id'))
        if key in keys:
            e.append('Cannot overwrite or duplicate an Option ID within a Decision')
        keys.add(key)
        if o.get('origin') != 'proposed' or o.get('method_mode') not in ['reused', 'adapted', 'technical_glue']:
            e.append('Added configuration must be proposed; Method is reused/adapted or technical glue')
        if o.get('method_mode') != 'technical_glue' and (not o.get('method_refs')):
            e.append('New scientific Option cannot bypass catalog')
        for m in o.get('method_refs', []):
            mid = m.get('method_id')
            if mid not in mids or not any((c['status'] in ['selected', 'conditional'] for c in ledger.get(mid, []))):
                e.append('Applied Method must be retrieved and selected/conditional')
            if not m.get('core_preserved') or 'adaptation_changes' not in m:
                e.append('Method core and source-to-target change record required')
            if not m.get('component_refs'):
                e.append('Applied Method source components required')
            for ref in m.get('component_refs', []):
                if index['components'].get(ref, {}).get('method_id') != mid:
                    e.append('Applied Method component mismatch')
        triad = o.get('triad', {})
        if not triad.get('method') or not triad.get('data_columns') or (not triad.get('parameters')) or (not triad.get('components')):
            e.append('Added Option must retain full triad')
        for b in triad.get('data_columns', []):
            if b.get('column_id') and b['column_id'] not in cols:
                e.append('Invented measured column ID')
            if b.get('status') not in ['target_bound', 'derived', 'unknown']:
                e.append('Column binding status must distinguish real/derived/unknown')
        for p in triad.get('parameters', []):
            if p.get('status') not in ['target_supported', 'proposed', 'unknown'] or 'value' not in p or (not p.get('reason')):
                e.append('Complete parameter value/status/reason required')
        if not set(o.get('comparison_group_ids', [])) <= groups or not o.get('equivalence_key'):
            e.append('Group membership and nonredundancy key required')
        if o.get('status') not in ['candidate', 'conditional', 'blocked']:
            e.append('Added Option applicability status required')
    statuses = x.get('original_option_status', [])
    found = [(r.get('decision_id'), r.get('option_id')) for r in statuses]
    if len(found) != len(set(found)) or set(found) != pairs:
        e.append('Account for every original Option exactly once, separately from immutable graph1')
    for r in statuses:
        if r.get('status') not in ['active', 'conditional', 'inactive', 'blocked'] or not r.get('reason'):
            e.append('Original Option status/reason required')
    for edge in x.get('added_edges', []):
        if edge.get('from') not in allids or edge.get('to') not in allids or (not edge.get('reason')) or (edge.get('origin') != 'proposed_dependency'):
            e.append('New dependency has invalid endpoint/source/reason')
    if e:
        return e
    expanded = apply_expansion(original, x)
    try:
        topological(expanded)
    except ValueError as exc:
        e.append(str(exc))
    if not original_unchanged(original, expanded):
        e.append('Graph1 modified by expansion')
    for d in expanded['decisions']:
        signatures = [o.get('equivalence_key') for o in d['options'] if o.get('origin') != 'reported']
        if len(signatures) != len(set(signatures)):
            e.append('Added alternatives share a mathematical-equivalence key in ' + d['id'])
    for f in expanded['forbidden_combinations']:
        if not f.get('choices') or not f.get('reason'):
            e.append('Constraint choices and reason required')
        for did, oid in f.get('choices', {}).items():
            if (did, oid) not in keys:
                e.append('Constraint references nonexistent Option')
    specs = x.get('path_proposals', [])
    if not 2 <= len(specs) <= 3 or not t.unique(specs, 'spec_id'):
        e.append('Two or three unique pre-outcome pilot paths required')
    signatures = []
    for sp in specs:
        if sp.get('group_id') not in groups:
            e.append('Path group does not exist')
        if set(sp.get('choices', {})) != allids:
            e.append('Path chooses exactly one Option per graph2 Decision, including singleton Decisions')
        inactive = {r.get('decision_id') for r in sp.get('inactive_decisions', [])}
        if not inactive <= allids or any((not r.get('reason') for r in sp.get('inactive_decisions', []))):
            e.append('Inactive decision must exist and have reason')
        for did, oid in sp.get('choices', {}).items():
            if (did, oid) not in keys:
                e.append('Path chose nonexistent Option')
            elif did not in inactive:
                o = next((o for d in expanded['decisions'] if d['id'] == did for o in d['options'] if o['id'] == oid))
                if o.get('origin') == 'reported':
                    st = next((r for r in statuses if r['decision_id'] == did and r['option_id'] == oid))
                    if st['status'] in ['inactive', 'blocked']:
                        e.append('Path activated unavailable original Option')
                elif o.get('status') == 'blocked' or sp['group_id'] not in o.get('comparison_group_ids', []):
                    e.append('Path used blocked/group-incompatible option')
        for f in expanded['forbidden_combinations']:
            if all((sp.get('choices', {}).get(k) == v for k, v in f['choices'].items())):
                e.append('Pilot violates forbidden combination')
        if sp.get('status') not in ['ready', 'conditional', 'blocked'] or not sp.get('distinctness_reason'):
            e.append('Path status and substantive distinctness explanation required')
        signatures.append(tuple(sorted(((k, v) for k, v in sp.get('choices', {}).items() if k not in inactive))))
    if len(signatures) != len(set(signatures)):
        e.append('Pilot paths duplicate active scientific choices')
    return e

def topological(graph):
    todo = [d['id'] for d in graph['decisions']]
    done = []
    while todo:
        ready = [d for d in todo if all((e['from'] in done for e in graph['dependency_edges'] if e['to'] == d))]
        if not ready:
            raise ValueError('Execution graph has cyclic/missing dependencies')
        for did in ready:
            done.append(did)
            todo.remove(did)
    return done

def enumerate_paths(graph, limit=10000):
    ds = graph['decisions']
    raw = math.prod((len(d['options']) for d in ds))
    rows = []
    examined = 0
    for combination in itertools.product(*(d['options'] for d in ds)):
        if examined >= limit:
            break
        examined += 1
        choices = {d['id']: o['id'] for d, o in zip(ds, combination)}
        if not any((all((choices.get(k) == v for k, v in f['choices'].items())) for f in graph['forbidden_combinations'])):
            rows.append(choices)
    return {'raw_combinations': raw, 'examined': examined, 'constraint_feasible_examined': len(rows), 'complete': examined == raw, 'limit': limit, 'choices': rows, 'meaning': 'structural combinations only, not certification of scientific validity; only reviewed pilot paths execute'}

def remaining(out, base, common, graph1, sources, graph, index, replay, stage, rerun):
    basis = priority.core_basis(graph, index)
    material = {**common, 'graph1': graph1, 'existing_methods': index['methods'], 'source_component_records': basis}
    expansion = ask('graph2_expansion', material, lambda x: expansion_errors(x, graph1, index, common['dataset']), out, replay)
    graph2 = apply_expansion(graph1, expansion)
    save(out / 'graph2_expanded.json', graph2)
    save(out / 'path_space.json', enumerate_paths(graph2))
    plan = {'hypothesis': common['research_context']['h1'], 'comparison_groups': expansion['comparison_groups'], 'specifications': expansion['path_proposals'], 'execution_order': topological(graph2)}
    save(out / 'specification_plan.json', plan)
    freeze = {'graph1_sha256': digest(graph1), 'graph2_sha256': digest(graph2), 'plan_sha256': digest(plan), 'catalog_sha256': s.sha(out / 'inputs/knowledge_graph.json')}
    freeze['freeze_sha256'] = digest(freeze)
    if (out / 'analysis_freeze.json').exists() and read(out / 'analysis_freeze.json') != freeze:
        raise ValueError('Graph or plan changed after freeze; use a new directory')
    save(out / 'analysis_freeze.json', freeze)
    if stage == 'expand':
        return
    return implement(out, base, common, graph1, graph2, expansion, plan, freeze, sources, replay, stage, rerun)

def code_errors(x, graph2, freeze):
    import specification_trial as execution
    e = execution.code_errors(x, graph2)
    if x.get('language') != 'python' or x.get('executed') is not False:
        e.append('At JSON ROOT explicitly include language=python and executed=false')
    if x.get('freeze_sha256') != freeze['freeze_sha256']:
        e.append('Generated code must retain frozen graph/plan hash')
    source = x.get('source_code', '')
    try:
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef)):
                continue
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                continue
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                try:
                    ast.literal_eval(node.value)
                    continue
                except (ValueError, TypeError):
                    pass
            e.append('Module top level may only import, define functions or assign literal constants')
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and (node.attr.startswith('_') or node.attr in {'os', 'sys', 'ctypes', 'ctypeslib', 'environ', 'modules', 'builtins', 'eval', 'query', 'load_library'}):
                e.append('Unsafe attribute access ' + node.attr)
    except SyntaxError:
        pass
    return list(dict.fromkeys(e))

def code_audit_errors(x, plan, code, freeze):
    e = t.require(x, ['freeze_sha256', 'approved', 'blocking_issues', 'specification_checks', 'limitations'], 'code audit')
    if x.get('freeze_sha256') != freeze['freeze_sha256'] or type(x.get('approved')) is not bool:
        e.append('Audit hash/approved boolean required')
    if not t.unique(x.get('specification_checks', []), 'spec_id', [s['spec_id'] for s in plan['specifications']]):
        e.append('Audit every frozen pilot path exactly once')
    for row in x.get('specification_checks', []):
        if not row.get('code_evidence') or not row.get('reason'):
            e.append('Code audit needs literal implementation evidence and reasoning')
        for ev in row.get('code_evidence', []):
            if not ev.get('quote') or ev['quote'] not in code['source_code']:
                e.append('Audit code evidence not found literally')
        if x.get('approved'):
            if any((row.get(k) is not True for k in ['target_preserved', 'choice_implementation_faithful', 'method_core_preserved', 'inference_appropriate', 'same_scale'])):
                e.append('Approved audit requires all scientific checks true')
    if x.get('approved') and x.get('blocking_issues'):
        e.append('Approved audit cannot contain blocking issues')
    return e

def result_errors(result, spec, groups):
    if not isinstance(result, dict):
        return ['Expected result dictionary']
    e = []
    g = next((g for g in groups if g['id'] == spec['group_id']))
    for key in ['metric_id', 'effect_scale', 'estimand', 'population']:
        if result.get(key) != g[key]:
            e.append('Result comparability drift ' + key)
    if result.get('group_id') != g['id']:
        e.append('Result group mismatch')
    if type(result.get('estimate')) not in [int, float] or not math.isfinite(result['estimate']):
        e.append('Finite computed estimate required')
    if result.get('pvalue') is not None and (type(result['pvalue']) not in [int, float] or not math.isfinite(result['pvalue']) or (not 0 <= result['pvalue'] <= 1)):
        e.append('P value must be finite in [0,1] or explicitly null')
    ci = [result.get('ci_low'), result.get('ci_high')]
    if any((v is not None for v in ci)) and (not all((type(v) in [int, float] and math.isfinite(v) for v in ci)) or ci[0] > ci[1]):
        e.append('CI bounds must both be finite ordered numbers or both null')
    if not isinstance(result.get('warnings'), list) or not result.get('inference_method') or (not isinstance(result.get('diagnostics'), dict)):
        e.append('Inference, warnings and measured diagnostics required')
    if result.get('pvalue') is None and (not result.get('warnings')):
        e.append('Unavailable P value needs explanation')
    ids = result.get('analysis_unit_ids', [])
    if type(result.get('nobs')) is not int or result['nobs'] < 3 or len(ids) != result['nobs']:
        e.append('At least three real analysis units; IDs count must match nobs')
    try:
        if len({json.dumps(i, sort_keys=True) for i in ids}) != len(ids):
            e.append('Duplicate analysis-unit IDs')
    except TypeError:
        e.append('Analysis-unit IDs must be JSON values')
    if not e and isinstance(g.get('estimate_bounds'), list) and (len(g['estimate_bounds']) == 2):
        if not g['estimate_bounds'][0] <= result['estimate'] <= g['estimate_bounds'][1]:
            e.append('Estimate outside declared metric bounds')
    return e

def execute(out, code, plan, expansion, common, freeze, manifest, attempt, replay=False, rerun=False):
    key = digest({'source_code': code['source_code'], 'plan': plan, 'freeze': freeze, 'data_sha256': manifest['csv_sha256']})
    receipt = out / 'execution_cache' / key / 'results.json'
    if receipt.exists() and (not rerun):
        rows = read(receipt)
        for row in rows:
            if row['status'] == 'ok':
                sp = next((sp for sp in plan['specifications'] if sp['spec_id'] == row['spec_id']))
                if result_errors(row['result'], sp, plan['comparison_groups']):
                    raise ValueError('Saved execution result fails current contract')
        return rows
    if replay and (not rerun):
        raise ValueError('Strict replay has no matching result receipt; will not run analysis')
    rows = []
    before = s.sha(out / 'analysis_input/analysis_data.csv')
    contract = {'graph2': read(out / 'graph2_expanded.json'), 'expansion': expansion, 'comparison_groups': plan['comparison_groups'], 'dataset': common['dataset'], 'freeze_sha256': freeze['freeze_sha256']}
    for sp in plan['specifications']:
        if sp['status'] == 'blocked':
            rows.append({'spec_id': sp['spec_id'], 'status': 'blocked', 'error': sp['conditions']})
            continue
        if not all((ch.isalnum() or ch in '_-' for ch in sp['spec_id'])):
            raise ValueError('Unsafe specification filename')
        serial = 1
        job = out / 'runs' / ('code_' + str(attempt)) / sp['spec_id']
        while job.exists():
            job = out / 'runs' / ('code_' + str(attempt)) / (sp['spec_id'] + '_run' + str(serial))
            serial += 1
        job.mkdir(parents=True)
        (job / 'analysis.py').write_text(code['source_code'], encoding='utf-8')
        save(job / 'job.json', {'data_dir': str((out / 'analysis_input').resolve()), 'spec': sp, 'contract': contract})
        env = {k: v for k, v in os.environ.items() if not any((tag in k.upper() for tag in ['KEY', 'TOKEN', 'SECRET', 'PASSWORD']))}
        env.update(PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        started = time.monotonic()
        try:
            proc = subprocess.run([sys.executable, '-B', str(ROOT / 'spec_worker.py'), str(job.resolve())], cwd=job, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
            (job / 'stdout.txt').write_text(proc.stdout, encoding='utf-8')
            (job / 'stderr.txt').write_text(proc.stderr, encoding='utf-8')
            payload = read(job / 'result.json') if (job / 'result.json').exists() else {'status': 'error', 'error': proc.stderr[-5000:] or 'No result'}
            if payload.get('status') == 'ok':
                errs = result_errors(payload['result'], sp, plan['comparison_groups'])
                if errs:
                    payload = {'status': 'error', 'error': errs}
        except subprocess.TimeoutExpired:
            payload = {'status': 'error', 'error': '120-second pilot timeout'}
        rows.append({'spec_id': sp['spec_id'], 'group_id': sp['group_id'], 'seconds': round(time.monotonic() - started, 3), **payload})
        print('Pilot ' + sp['spec_id'] + ' ' + payload['status'], flush=True)
    if s.sha(out / 'analysis_input/analysis_data.csv') != before:
        raise ValueError('Data mutated during execution')
    for g in plan['comparison_groups']:
        successful = [r for r in rows if r.get('status') == 'ok' and r['group_id'] == g['id']]
        if g['sample_policy'] == 'same' and len(successful) > 1:
            unitsets = [{json.dumps(v, sort_keys=True) for v in r['result']['analysis_unit_ids']} for r in successful]
            if any((u != unitsets[0] for u in unitsets[1:])):
                for row in successful:
                    row.update(status='error', error='Frozen same-sample policy violated; do not pool curve')
    if receipt.exists():
        history = out / 'execution_history' / key
        history.mkdir(parents=True, exist_ok=True)
        previous = history / (str(len(list(history.glob('*.json'))) + 1) + '.json')
        shutil.copy2(receipt, previous)
    save(receipt, rows)
    save(out / ('execution_results_attempt_' + str(attempt) + '.json'), rows)
    return rows

def render_boba(out, code, plan, graph2, freeze, expansion, common):
    ds = graph2['decisions']
    order = topological(graph2)
    lookup = {d['id']: d for d in ds}
    variables = []
    constraints = []
    for did in order:
        variables.append({'var': did, 'options': [repr(o['id']) for o in lookup[did]['options']]})
    last = order[-1]
    previous = order[:-1]
    for idx, opt in enumerate(lookup[last]['options']):
        matching = [sp for sp in plan['specifications'] if sp['choices'][last] == opt['id']]
        expressions = []
        for sp in matching:
            terms = []
            for did in previous:
                index = next((i for i, o in enumerate(lookup[did]['options']) if o['id'] == sp['choices'][did]))
                terms.append(did + '.index == ' + str(index))
            expressions.append('(' + ' and '.join(terms) + ')' if terms else '1 == 1')
        constraints.append({'variable': last, 'index': idx, 'condition': ' or '.join(expressions) if expressions else '1 == 0'})
    config = {'graph': ['Setup->Choices->Run'], 'decisions': variables, 'constraints': constraints}
    choices = '{' + ', '.join((repr(did) + ': {{' + did + '}}' for did in order)) + '}'
    contract = {'graph2': graph2, 'expansion': expansion, 'comparison_groups': plan['comparison_groups'], 'dataset': common['dataset'], 'freeze_sha256': freeze['freeze_sha256']}
    text = '# --- (BOBA_CONFIG)\n' + lab.dumps(config) + '\n\n# --- (Setup)\n# Automatically generated from frozen graph2; not author source.\n' + code['source_code']
    text += '\nPLAN = ' + repr(plan) + '\nCONTRACT = ' + repr(contract) + '\n\n# --- (Choices)\nCHOICES = ' + choices
    text += "\n\n# --- (Run)\nimport os\nimport json\nSPEC = next(s for s in PLAN['specifications'] if s['choices'] == CHOICES)\nRESULT = analyze(os.environ.get('MULTIVERSE_DATA_DIR', 'analysis_input'), SPEC, CONTRACT)\nprint(json.dumps(RESULT, ensure_ascii=False, default=str))\n"
    (out / 'boba_template.py').write_text(text, encoding='utf-8')
    save(out / 'boba_config.json', config)

def compile_boba(out, plan):
    from importlib.metadata import version
    i = 1
    while (out / 'boba_compile_checks' / str(i)).exists():
        i += 1
    dest = out / 'boba_compile_checks' / str(i)
    dest.mkdir(parents=True)
    if not (dest / 'multiverse').resolve().is_relative_to(out.resolve()) or (dest / 'multiverse').exists():
        raise ValueError('Unsafe compiler directory')
    proc = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'boba.cli', 'compile', '--script', str((out / 'boba_template.py').resolve()), '--out', str(dest.resolve())], capture_output=True, text=True, encoding='utf-8', timeout=120)
    (dest / 'compiler.log').write_text(proc.stdout + '\n' + proc.stderr, encoding='utf-8')
    if proc.returncode:
        raise ValueError('Boba compile failed: ' + proc.stderr[-1500:])
    actual = []
    files = list((dest / 'multiverse').rglob('universe_*.py'))
    for f in files:
        tree = ast.parse(f.read_text('utf-8'))
        node = next((n for n in tree.body if isinstance(n, ast.Assign) and any((isinstance(k, ast.Name) and k.id == 'CHOICES' for k in n.targets))))
        actual.append(ast.literal_eval(node.value))
    if {digest(c) for c in actual} != {digest(sp['choices']) for sp in plan['specifications']} or len(files) != len(plan['specifications']):
        raise ValueError('Boba expansion differs from frozen pilot choices')
    report = {'official_boba_compile_passed': True, 'boba_version': version('boba'), 'generated_scripts': len(files), 'frozen_choices_match': True, 'template_sha256': s.sha(out / 'boba_template.py'), 'compile_directory': dest.relative_to(out).as_posix()}
    save(out / 'boba_compiler_verification.json', report)
    return report

def implement(out, base, common, graph1, graph2, expansion, plan, freeze, sources, replay, stage, rerun):
    manifest = prepare_data(out, base, common['dataset'], replay)
    material = {**common, 'graph1': graph1, 'graph2': graph2, 'expansion': expansion, 'plan': plan, 'freeze_sha256': freeze['freeze_sha256'], 'data_file': manifest}
    feedback = None
    previous = None
    history = []
    rows = []
    code = None
    audit = None
    for attempt in range(3):
        cm = material if attempt == 0 else {**material, 'previous_code': previous, 'errors_without_successful_estimates': feedback}
        code = ask('graph_code', cm, lambda x: code_errors(x, graph2, freeze), out, replay)
        save(out / ('code_round_' + str(attempt) + '.json'), code)
        audit = ask('graph_code_audit', {**material, 'generated_code': code}, lambda x: code_audit_errors(x, plan, code, freeze), out, replay)
        save(out / ('audit_round_' + str(attempt) + '.json'), audit)
        history.append({'attempt': attempt, 'code_sha256': digest(code['source_code']), 'approved': audit['approved']})
        if not audit['approved']:
            previous = code
            feedback = {'pre_execution_audit': audit['blocking_issues']}
            continue
        render_boba(out, code, plan, graph2, freeze, expansion, common)
        if stage == 'code':
            return
        rows = execute(out, code, plan, expansion, common, freeze, manifest, attempt, replay, rerun)
        failed = [r for r in rows if r['status'] == 'error']
        if not failed:
            break
        previous = code
        feedback = [{'spec_id': r['spec_id'], 'error': r.get('error'), 'traceback': r.get('traceback')} for r in failed]
    save(out / 'implementation_history.json', history)
    save(out / 'execution_results.json', rows)
    if code:
        save(out / 'accepted_code.json', code)
        (out / 'analysis.py').write_text(code['source_code'], encoding='utf-8')
    if audit:
        save(out / 'accepted_audit.json', audit)
    if audit and audit['approved']:
        if replay:
            saved = read(out / 'boba_compiler_verification.json')
            if saved['template_sha256'] != s.sha(out / 'boba_template.py'):
                raise ValueError('Boba receipt/template mismatch')
        else:
            compile_boba(out, plan)
    report = {'original_twenty_unchanged': s.sha(out / 'inputs/knowledge_graph.json') == read(out / 'selection.json')['frozen_graph_sha256'], 'graph1_preserved_in_graph2': original_unchanged(graph1, graph2), 'graph1_decisions': len(graph1['decisions']), 'graph1_reported_options': sum((len(d['options']) for d in graph1['decisions'])), 'graph2_decisions': len(graph2['decisions']), 'graph2_options': sum((len(d['options']) for d in graph2['decisions'])), 'new_options': sum((len(d['options']) for d in graph2['decisions'])) - sum((len(d['options']) for d in graph1['decisions'])), 'catalog_method_ids_used': sorted({m['method_id'] for d in graph2['decisions'] for o in d['options'] for m in o.get('method_refs', [])}), 'preselected_paths': len(plan['specifications']), 'successful_paths': sum((r['status'] == 'ok' for r in rows)), 'comparison_groups': len(plan['comparison_groups']), 'analysis_executed': any((r['status'] in ['ok', 'error'] for r in rows)), 'audit_approved': audit['approved'] if audit else False, 'scientific_validity_certified': False, 'freeze_sha256': freeze['freeze_sha256'], 'code_sha256': digest(code['source_code']) if code else None, 'data_sha256': manifest['csv_sha256']}
    if not report['original_twenty_unchanged'] or not report['graph1_preserved_in_graph2']:
        raise ValueError('Frozen originals changed')
    save(out / 'verification.json', report)
    from paper_graph_view import build
    build(out)

def run(out=DEFAULT, base=BASE, replay=False, stage='all', rerun=False):
    t.bootstrap(out, base, replay)
    context = read(out / 'research_context.json')
    features = read(out / 'data_features.json')
    ranking = read(out / 'column_ranking.json')
    dataset = next((d for d in features['datasets'] if d['dataset_id'] == context['dataset_choice']['dataset_id']))
    sources = read(out / 'inputs/sources.json')['sources']
    graph = read(out / 'inputs/knowledge_graph.json')
    index = read(out / 'semantic_index.json')
    h1 = context['h1']['text']
    common = {'research_context': context, 'dataset': dataset, 'column_ranking': ranking}
    graph1 = ask('paper_graph1', {**common, 'fixed_h1': h1, 'sources': sources}, lambda x: graph1_errors(x, h1, sources, dataset), out, replay)
    save(out / 'graph1_reported.json', graph1)
    if stage == 'graph1':
        return
    return remaining(out, base, common, graph1, sources, graph, index, replay, stage, rerun)
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=DEFAULT)
    p.add_argument('--baseline', type=Path, default=BASE)
    p.add_argument('--stage', choices=['graph1', 'expand', 'code', 'all'], default='all')
    p.add_argument('--replay', action='store_true')
    p.add_argument('--rerun', action='store_true')
    a = p.parse_args()
    run(a.output.resolve(), a.baseline.resolve(), a.replay, a.stage, a.rerun)
