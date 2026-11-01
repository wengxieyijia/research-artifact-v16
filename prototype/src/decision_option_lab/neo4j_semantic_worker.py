# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Generic execution wrapper. All statistical algorithms reside in DeepSeek's module."""
import ast
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import time
import traceback
import numpy as np
import pandas as pd
ALLOWED_IMPORTS = {'numpy', 'pandas', 'scipy', 'statsmodels', 'sklearn', 'math', 'warnings', 'collections', 'itertools', 'functools', 'typing', 'hashlib', 'json'}
FORBIDDEN = {'open', 'exec', 'eval', 'compile', '__import__', 'input', 'breakpoint', 'exit', 'quit'}
FORBIDDEN_ATTRS = {'read_csv', 'read_json', 'read_pickle', 'read_excel', 'read_parquet', 'to_csv', 'to_json', 'to_pickle', 'to_excel', 'to_sql', 'to_parquet', 'save', 'savez', 'load', 'write', 'system', 'popen'}

def audit(source):
    errors = []
    try:
        tree = ast.parse(source)
        compile(tree, '<generated-scientific-module>', 'exec')
    except SyntaxError as exc:
        return ['Python syntax: ' + str(exc)]
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            roots = [a.name.split('.')[0] for a in node.names] if isinstance(node, ast.Import) else [(node.module or '').split('.')[0]]
            if any((r not in ALLOWED_IMPORTS for r in roots)):
                errors.append('Forbidden import: ' + ','.join(roots))
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN:
                errors.append('Forbidden call: ' + node.func.id)
            if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_ATTRS:
                errors.append('Forbidden IO: ' + node.func.attr)
        if isinstance(node, ast.Attribute) and node.attr.startswith('__'):
            errors.append('Dunder access is not permitted in analysis source')
    if not any((isinstance(n, ast.FunctionDef) and n.name == 'analyze' for n in tree.body)):
        errors.append('analyze(data,spec) missing')
    return sorted(set(errors))

def plain(v):
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, np.ndarray):
        return [plain(x) for x in v.tolist()]
    if isinstance(v, dict):
        return {str(k): plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    return v

def run_one(out_path, spec_id, round_id):
    out = Path(out_path)
    results = Path(os.environ.get('NEO4J_TRIAL_RESULT_DIR', str(out / f'execution_round_{round_id}' / 'results')))
    if not results.resolve().is_relative_to(out.resolve()):
        raise ValueError('Result directory must remain inside this trial output')
    results.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    record = {'spec_id': spec_id, 'round': round_id}
    try:
        lock = json.loads((out / 'specification_lock.json').read_text(encoding='utf-8'))
        for name, key in [('data.csv', 'data_sha256'), ('specifications.json', 'specifications_sha256'), ('specification_plan.json', 'plan_sha256')]:
            if hashlib.sha256((out / name).read_bytes()).hexdigest() != lock[key]:
                raise ValueError('Frozen input changed: ' + name)
        specs = json.loads((out / 'specifications.json').read_text(encoding='utf-8'))['specifications']
        spec = next((s for s in specs if s['spec_id'] == spec_id))
        record.update(group_id=spec['group_id'], choices=spec['choices'], comparison_definition=spec['comparison_definition'])
        module_path = out / f'analysis_round_{round_id}.py'
        source = module_path.read_text(encoding='utf-8')
        errors = audit(source)
        if errors:
            raise ValueError('Basic code check: ' + json.dumps(errors))
        module_spec = importlib.util.spec_from_file_location('trial_science', module_path)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        frame = pd.read_csv(out / 'data.csv')
        outcome = plain(module.analyze(frame.copy(), spec))
        if not isinstance(outcome, dict):
            raise TypeError('analyze must return a JSON object')
        for key in ['effect_size', 'p_value', 'ci_lower', 'ci_upper', 'n', 'effect_scale', 'estimand']:
            if key not in outcome:
                raise ValueError('Result missing ' + key)
        if not isinstance(outcome['effect_size'], (int, float)) or not math.isfinite(outcome['effect_size']):
            raise ValueError('Effect is not finite')
        if not isinstance(outcome['n'], (int, float)) or not math.isfinite(outcome['n']) or outcome['n'] <= 0:
            raise ValueError('Invalid actual sample size')
        for key in ['p_value', 'ci_lower', 'ci_upper']:
            if outcome[key] is not None and (not isinstance(outcome[key], (int, float)) or not math.isfinite(outcome[key])):
                raise ValueError('Nonfinite ' + key)
        if outcome['p_value'] is not None and (not 0 <= outcome['p_value'] <= 1):
            raise ValueError('p_value outside [0,1]')
        if outcome['effect_scale'] != spec['comparison_definition']['effect_scale']:
            raise ValueError('Effect scale differs from frozen comparison definition')
        if outcome['estimand'] != spec['comparison_definition']['estimand']:
            raise ValueError('Estimand differs from frozen comparison definition')
        if outcome['ci_lower'] is not None and outcome['ci_upper'] is not None and (outcome['ci_lower'] > outcome['ci_upper']):
            raise ValueError('Reversed interval')
        record.update(status='success', result=outcome, input_rows=len(frame), code_sha256=hashlib.sha256(source.encode('utf-8')).hexdigest())
    except Exception as exc:
        record.update(status='failed', error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
    record['seconds'] = round(time.monotonic() - started, 3)
    (results / (spec_id + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(spec_id + ' ' + record['status'], flush=True)
    return record
