# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Outcome-blind DAG specification generation, constrained generated-code execution, and curves."""
import argparse
import ast
import difflib
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import html
import importlib.metadata
import json
import math
import os
import shutil
from pathlib import Path
import subprocess
import sys
import time
import lab
import model_runner
import spec_prepare
ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'specification_results'
ALLOWED_IMPORTS = {'numpy', 'pandas', 'scipy', 'statsmodels', 'sklearn', 'math', 'json', 'pathlib', 'warnings', 'itertools', 'collections'}
FORBIDDEN_CALLS = {'exec', 'eval', 'compile', 'open', '__import__', 'getattr', 'setattr', 'delattr', 'globals', 'locals', 'vars', 'input', 'breakpoint', 'exit', 'quit'}
FORBIDDEN_ATTRS = {'write_text', 'write_bytes', 'to_csv', 'to_json', 'to_pickle', 'to_excel', 'to_stata', 'read_pickle', 'read_html', 'read_sql', 'read_sql_query', 'read_sql_table', 'load', 'loads', 'save', 'savez', 'savez_compressed', 'system', 'popen', 'unlink', 'rmdir', 'mkdir', 'rename', 'replace', 'chmod', 'chdir', 'resolve', 'home', 'cwd'}
FORBIDDEN_ATTRS -= {'replace', 'loads', 'resolve'}

def ask(stage, instruction, material, out, validator, replay=False):
    return model_runner.run_json(stage, (ROOT / 'instructions' / instruction).read_text(encoding='utf-8'), lab.read(ROOT / 'execution_policy.json'), {}, material, lab.read(ROOT / 'config_high.json'), out, validator, replay)

def topo_order(space):
    remaining = {d['id'] for d in space['decisions']}
    order = []
    while remaining:
        ready = sorted((d for d in remaining if all((e['from'] in order for e in space['dependency_edges'] if e['to'] == d))))
        if not ready:
            raise ValueError('DAG cycle')
        order.extend(ready)
        remaining -= set(ready)
    return order

def evidence_errors(obj, sources):
    audit = lab.evidence_audit(obj, sources)
    lookup = {s['source_id']: s for s in sources}
    errors = []
    for item in audit['checks']:
        if item['matched']:
            continue
        source = lookup.get(item['source_id'])
        quote = item['quote']
        snippet = 'Source ID missing'
        if source and isinstance(quote, str):
            match = difflib.SequenceMatcher(None, quote, source['text'], autojunk=False).find_longest_match()
            snippet = source['text'][max(0, match.b - 120):match.b + match.size + 220]
        errors.append({'error': 'quotation must match a continuous actual source segment; no ellipsis/translated/paraphrased quote', 'path': item['path'], 'source_id': item['source_id'], 'invalid_quote': quote, 'automatically_retrieved_nearby_source_text': snippet})
    return (audit, errors)

def plan_errors(obj, space, intake, sources):
    errors = []
    if obj.get('h1_text') != intake['hypothesis']['text']:
        errors.append('fixed H1 mismatch')
    target = obj.get('target', {})
    for key in ('estimand', 'outcome', 'exposure', 'population', 'effect_scale'):
        if not isinstance(target.get(key), str) or not target[key].strip():
            errors.append('target ' + key + ' required')
    if target.get('null_value') != 0:
        errors.append('pilot supports a fixed null value 0')
    specs = obj.get('specifications', [])
    if not 2 <= len(specs) <= 3:
        return errors + ['Need exactly 2–3 specifications']
    if len({s.get('spec_id') for s in specs}) != len(specs):
        errors.append('unique spec IDs required')
    ids = {d['id']: {o['id'] for o in d['options']} for d in space['decisions']}
    signatures = []
    for spec in specs:
        choices = spec.get('choices', {})
        order = spec.get('execution_order', [])
        if set(choices) != set(ids) or any((v not in ids.get(k, set()) for k, v in choices.items())):
            errors.append('Each Decision must have one existing Option')
        if Counter(order) != Counter(list(ids)):
            errors.append('Execution order must cover DAG once')
        elif any((order.index(e['from']) >= order.index(e['to']) for e in space['dependency_edges'])):
            errors.append('Topological order violated')
        for c in space['forbidden_combinations']:
            if all((choices.get(k) == v for k, v in c['choices'].items())):
                errors.append('Forbidden combination chosen: ' + lab.dumps(c['choices']))
        inactive = spec.get('inactive_decisions', [])
        if any((x.get('decision_id') not in ids or not x.get('reason') for x in inactive)):
            errors.append('Invalid inactive decision')
        inactive_ids = {x['decision_id'] for x in inactive}
        mandatory = {x['decision_id'] for x in intake.get('dag_applicability', []) if x['status'] == 'inactive'}
        if not mandatory <= inactive_ids:
            errors.append('Must disclose all inactive DAG decisions')
        signatures.append(tuple(sorted(((k, v) for k, v in choices.items() if k not in inactive_ids))))
        for key in ('label', 'scientific_rationale', 'redundancy_check'):
            if not spec.get(key):
                errors.append('Missing ' + key)
        for key in ('algorithm_steps', 'statistical_preconditions', 'limitations'):
            if not isinstance(spec.get(key), list) or (key != 'limitations' and (not spec[key])):
                errors.append('Missing ' + key)
        audit, quote_errors = evidence_errors(spec, sources)
        if not audit['total']:
            errors.append('Each spec needs source evidence')
        errors.extend(quote_errors)
    if len(set(signatures)) != len(signatures):
        errors.append('Specifications differ only by inactive choices or are duplicates')
    return errors

def code_errors(obj, space):
    source = obj.get('source_code', '')
    errors = []
    if not isinstance(source, str) or not source.strip():
        return ['source_code required']
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return ['syntax error ' + str(exc)]
    functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'analyze']
    if len(functions) != 1 or len(functions[0].args.args) != 3:
        errors.append('exactly analyze(data_dir,spec,contract) function required')
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split('.')[0] not in ALLOWED_IMPORTS:
                    errors.append('forbidden import ' + alias.name)
        if isinstance(node, ast.ImportFrom) and (not node.module or node.module.split('.')[0] not in ALLOWED_IMPORTS or node.level):
            errors.append('forbidden from import ' + str(node.module))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and (node.func.id in FORBIDDEN_CALLS):
            errors.append('forbidden call ' + node.func.id)
        if isinstance(node, ast.Attribute) and (node.attr.startswith('__') or node.attr in FORBIDDEN_ATTRS):
            errors.append('forbidden attribute ' + node.attr)
    implemented = obj.get('decision_implementation', [])
    if Counter((x.get('decision_id') for x in implemented)) != Counter((d['id'] for d in space['decisions'])):
        errors.append('Document implementation of every Decision')
    return list(dict.fromkeys(errors))

def audit_errors(obj, plan):
    errors = []
    if type(obj.get('approved')) is not bool or not isinstance(obj.get('blocking_issues'), list):
        return ['approved boolean/blocking_issues array required']
    rows = obj.get('specification_checks', [])
    if Counter((x.get('spec_id') for x in rows)) != Counter((s['spec_id'] for s in plan['specifications'])):
        errors.append('Audit each specification once')
    if obj['approved']:
        if obj['blocking_issues']:
            errors.append('Approved audit cannot contain blocking issues')
        if any((row.get(k) is not True for row in rows for k in ('target_preserved', 'choice_implementation_faithful', 'inference_appropriate', 'same_scale'))):
            errors.append('Approved audit must pass all checks')
    return errors

def target_material(out):
    sources = lab.read(out / 'sources.json')
    intake = lab.read(out / 'intake.json')
    profiles = lab.read(out / 'data_profiles.json')
    return {'intake': intake, 'data_profiles': profiles, 'sources': sources['sources']}

def plan_one(out, replay=False):
    material = target_material(out)
    intake = material['intake']
    if not intake['feasible']:
        raise ValueError('Study infeasible: ' + intake['feasibility_reason'])
    if (out / 'input_dag.json').exists():
        space = lab.read(out / 'input_dag.json')
    else:
        text = (ROOT / 'prompts/options.txt').read_text(encoding='utf-8')
        text += '\n\u989d\u5916\u8981\u6c42：\u672c\u6b21\u662f\u5feb\u901f\u6267\u884c\u8bd5\u9519。\u53ea\u4fdd\u7559\u9488\u5bf9\u56fa\u5b9a\u6570\u636e/H1\u548c\u56fa\u5b9a\u53d8\u91cf\u5b9a\u4e49\u7684\u53ef\u6267\u884c\u81ea\u7531\u5ea6。fixed_execution_settings\u4e0d\u53ef\u968f\u610f\u53d8\u5316。\u4e0d\u540c\u63a8\u65ad\u7b97\u6cd5\u53ef\u4ee5\u4f5c\u4e3a\u771f\u5b9e\u81ea\u7531\u5ea6，\u4f46\u4ec5\u6539\u968f\u673aseed\u6216\u91cd\u590d\u6b21\u6570\u4e0d\u7b97\u4e0d\u540c\u65b9\u6848。\u4e0d\u5b58\u5728\u7684Census\u6570\u636e\u4e0d\u53ef\u4f7f\u7528。\u4e0d\u8981\u5c06\u5bf9\u6570/\u6bd4\u7387、\u4e0d\u540c\u5b50\u7fa4、\u52a0\u6743/\u672a\u52a0\u6743、Pearson/Spearman\u7b49\u4e0d\u540c\u53c2\u6570\u6df7\u6210\u540c\u4e00\u66f2\u7ebf。\u53ef\u53ea\u67091–3\u4e2a\u6709\u4f9d\u636e\u7684\u51b3\u7b56。'
        cfg = lab.read(ROOT / 'config_high.json')
        h = intake['hypothesis']

        def valid(obj):
            errs = lab.validate_space(obj, h['text'])
            audit, quote_errors = evidence_errors(obj, material['sources'])
            errs.extend(quote_errors)
            return errs
        space = model_runner.run_json('execution_dag', text, lab.read(ROOT / 'execution_policy.json'), {}, {'research_contract': {'hypothesis': h}, 'fixed_execution_settings': intake['fixed_execution_settings'], 'data_profiles': material['data_profiles'], 'sources': material['sources']}, cfg, out, valid, replay)
        lab.save(out / 'input_dag.json', space)
    material['dag'] = space
    plan = ask('specification_plan', 'execution_plan.txt', material, out, lambda x: plan_errors(x, space, intake, material['sources']), replay)
    freeze = {'plan_sha256': lab.sha(lab.dumps(plan).encode('utf-8')), 'input_dag_sha256': lab.sha(lab.dumps(space).encode('utf-8')), 'outcome_models_seen': False, 'specification_count': len(plan['specifications']), 'hypothesis': intake['hypothesis'], 'scope_change_from_original': intake['difference_from_original_h1']}
    if (out / 'frozen_plan.json').exists():
        prior = lab.read(out / 'frozen_plan.json')
        if prior['plan_sha256'] != freeze['plan_sha256'] or prior['input_dag_sha256'] != freeze['input_dag_sha256']:
            raise ValueError('Plan/DAG changed after freezing; use a new explicit trial directory')
    else:
        if (out / 'runs').exists():
            raise ValueError('Cannot claim outcome-blind freeze after analysis already ran')
        lab.save(out / 'frozen_plan.json', freeze)
    lab.save(out / 'input_bundle.json', {'H1': intake['hypothesis'], 'H1_origin': 'model_inferred_operational', 'data_manifest': lab.read(out / 'data_manifest.json'), 'DAG_file': 'input_dag.json', 'DAG_sha256': freeze['input_dag_sha256'], 'applicability': intake['dag_applicability'], 'background_files': ['sources.json', 'data_profiles.json', 'intake.json'], 'output_plan_file': 'specification_plan.json'})
    return plan

def result_errors(result, plan):
    if not isinstance(result, dict):
        return ['Analysis must return a result dictionary']
    errors = []
    for key in ('estimate', 'pvalue'):
        if isinstance(result.get(key), bool) or not isinstance(result.get(key), (int, float)) or (not math.isfinite(result[key])):
            errors.append('Nonfinite/missing ' + key)
    if errors:
        return errors
    if not 0 <= result['pvalue'] <= 1:
        errors.append('P outside [0,1]')
    optional = [result.get(k) for k in ('std_error', 'ci_low', 'ci_high')]
    if any((x is not None for x in optional)):
        if not all((isinstance(x, (int, float)) and (not isinstance(x, bool)) and math.isfinite(x) for x in optional)):
            errors.append('SE and CI must be all finite or all explicitly unavailable')
        elif result['std_error'] <= 0 or result['ci_low'] >= result['ci_high'] or (not result['ci_low'] <= result['estimate'] <= result['ci_high']):
            errors.append('Invalid SE/CI')
    elif not result.get('warnings'):
        errors.append('Unavailable SE/CI must be disclosed')
    if type(result.get('nobs')) is not int or result['nobs'] < 10:
        errors.append('At least 10 analysis units required')
    for key in ('estimand', 'outcome', 'exposure', 'effect_scale'):
        if result.get(key) != plan['target'][key]:
            errors.append('Target drift: ' + key)
    if not isinstance(result.get('diagnostics'), dict) or not result['diagnostics']:
        errors.append('Measured diagnostics required')
    if not result.get('inference_method'):
        errors.append('Inference method required')
    return errors

def execute(out, plan, code, attempt):
    results = []
    before = {p.name: lab.sha(p.read_bytes()) for p in (out / 'inputs').iterdir() if p.is_file()}
    for spec in plan['specifications']:
        job = out / 'runs' / f'code_{attempt}' / spec['spec_id']
        job.mkdir(parents=True, exist_ok=True)
        if (job / 'result.json').exists():
            history = job.parent / (spec['spec_id'] + '_history')
            history.mkdir(exist_ok=True)
            target = history / str(len(list(history.iterdir())) + 1)
            if not job.resolve().is_relative_to(out.resolve()) or not target.resolve().is_relative_to(out.resolve()):
                raise ValueError('History path outside study')
            shutil.copytree(job, target)
        (job / 'analysis.py').write_text(code['source_code'], encoding='utf-8')
        lab.save(job / 'job.json', {'data_dir': str((out / 'inputs').resolve()), 'spec': spec, 'contract': {'intake': lab.read(out / 'intake.json'), 'plan': plan}})
        env = {k: v for k, v in os.environ.items() if not any((token in k.upper() for token in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD')))}
        env.update(PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        start = time.monotonic()
        try:
            proc = subprocess.run([sys.executable, '-B', str(ROOT / 'spec_worker.py'), str(job.resolve())], cwd=job, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=1200)
            (job / 'stdout.txt').write_text(proc.stdout, encoding='utf-8')
            (job / 'stderr.txt').write_text(proc.stderr, encoding='utf-8')
            payload = lab.read(job / 'result.json') if (job / 'result.json').exists() else {'status': 'error', 'error': proc.stderr[-4000:] or 'No result produced'}
            if payload['status'] == 'ok':
                errs = result_errors(payload['result'], plan)
                if errs:
                    payload = {'status': 'error', 'error': errs, 'raw_result': payload['result']}
        except subprocess.TimeoutExpired:
            payload = {'status': 'error', 'error': 'Analysis exceeded 1200-second timeout'}
        results.append({'spec_id': spec['spec_id'], 'choices': spec['choices'], 'seconds': round(time.monotonic() - start, 3), **payload})
        print(out.name + ' ' + spec['spec_id'] + ' ' + payload['status'], flush=True)
    after = {p.name: lab.sha(p.read_bytes()) for p in (out / 'inputs').iterdir() if p.is_file()}
    if before != after:
        raise ValueError('Input data changed')
    receipt = out / f'execution_results_attempt_{attempt}.json'
    if receipt.exists():
        history_dir = out / 'execution_history'
        history_dir.mkdir(exist_ok=True)
        prior = history_dir / (receipt.stem + '_' + str(len(list(history_dir.iterdir())) + 1) + '.json')
        shutil.copy2(receipt, prior)
    lab.save(receipt, results)
    return results

def implement_one(out, replay=False):
    material = target_material(out)
    space = lab.read(out / 'input_dag.json')
    plan = lab.read(out / 'specification_plan.json')
    base = {**material, 'dag': space, 'plan': plan, 'runtime_versions': runtime_versions()}
    issues = []
    previous = None
    history = []
    for attempt in range(5):
        material_code = {**base, 'previous_code': previous, 'runtime_errors': issues}
        code = ask('codegen_' + str(attempt), 'execution_codegen.txt', material_code, out, lambda x: code_errors(x, space), replay)
        audit = ask('code_audit_' + str(attempt), 'execution_audit.txt', {**base, 'generated_code': code}, out, lambda x: audit_errors(x, plan), replay)
        history.append({'attempt': attempt, 'code_sha256': lab.sha(code['source_code'].encode('utf-8')), 'audit_approved': audit['approved']})
        if not audit['approved']:
            previous = code
            issues = [{'kind': 'pre_execution_statistical_audit', 'issues': audit['blocking_issues']}]
            print(out.name + ' pre-execution audit rejected code ' + str(attempt), flush=True)
            continue
        rows = execute(out, plan, code, attempt)
        failed = [x for x in rows if x['status'] != 'ok']
        if not failed:
            diagnostic_review = ask('diagnostics_audit_' + str(attempt), 'execution_diagnostics_audit.txt', {**base, 'generated_code': code, 'runtime_diagnostics': structural_diagnostics(rows)}, out, diagnostics_audit_errors, replay)
            history[-1]['diagnostics_approved'] = diagnostic_review['approved']
            if not diagnostic_review['approved']:
                previous = code
                issues = [{'kind': 'post_execution_structural_diagnostics_audit', 'issues': diagnostic_review['blocking_issues']}]
                print(out.name + ' diagnostic review rejected code ' + str(attempt), flush=True)
                continue
            lab.save(out / 'accepted_code.json', code)
            (out / 'analysis.py').write_text(code['source_code'], encoding='utf-8')
            lab.save(out / 'accepted_audit.json', audit)
            lab.save(out / 'execution_results.json', rows)
            lab.save(out / 'implementation_history.json', history)
            lab.save(out / 'accepted_diagnostics_audit.json', diagnostic_review)
            if (out / 'pipeline_error.json').exists():
                history_dir = out / 'execution_history'
                history_dir.mkdir(exist_ok=True)
                prior = history_dir / ('resolved_pipeline_error_' + str(len(list(history_dir.iterdir())) + 1) + '.json')
                shutil.copy2(out / 'pipeline_error.json', prior)
                (out / 'pipeline_error.json').unlink()
            lab.save(out / 'pipeline_status.json', {'status': 'success', 'accepted_code_attempt': attempt, 'specifications': len(rows)})
            return rows
        previous = code
        issues = [{'spec_id': x['spec_id'], 'error': x.get('error'), 'traceback': x.get('traceback')} for x in failed]
    lab.save(out / 'implementation_history.json', history)
    raise RuntimeError('Could not obtain audited successful code after 5 attempts; all failures retained')

def runtime_versions():
    return {name: importlib.metadata.version(name) for name in ['numpy', 'pandas', 'scipy', 'statsmodels', 'scikit-learn', 'matplotlib', 'pypdf']}

def structural_diagnostics(rows):

    def keep(key):
        k = key.lower()
        if any((term in k for term in ('pvalue', 'p_value', 'estimate', 'pearson', 'mean', 'median', 'effect', 'ci_', 'covariance', 'correlation', 'quantile', 'extreme', 'exceed', 'tail', 'null_', 'statistic', 'significant', '_se', '_sd'))):
            return False
        return any((term in k for term in ('row', 'count', 'nobs', 'n_', '_n', 'rank', 'column', 'success', 'fail', 'merge', 'valid', 'unique', 'ess', 'weight', 'seed', 'requested', 'repetition', 'bootstrap', 'permutation', 'missing', 'sample')))
    return [{'spec_id': row['spec_id'], 'status': row['status'], 'diagnostics': {k: v for k, v in row.get('result', {}).get('diagnostics', {}).items() if keep(k)}} for row in rows]

def diagnostics_audit_errors(obj):
    if type(obj.get('approved')) is not bool or not isinstance(obj.get('blocking_issues'), list):
        return ['approved boolean/blocking issues required']
    if obj['approved'] and obj['blocking_issues']:
        return ['Approved diagnostic review must have no blocking issues']
    return []

def plot_curve(out, rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    import numpy as np
    font = FontProperties(fname='C:/Windows/Fonts/msyh.ttc') if Path('C:/Windows/Fonts/msyh.ttc').exists() else FontProperties()
    plan = lab.read(out / 'specification_plan.json')
    space = lab.read(out / 'input_dag.json')
    intake = lab.read(out / 'intake.json')
    specs = {s['spec_id']: s for s in plan['specifications']}
    valid = sorted([r for r in rows if r['status'] == 'ok'], key=lambda x: x['result']['estimate'])
    varying = [d for d in space['decisions'] if len({s['choices'][d['id']] for s in specs.values()}) > 1]
    fig, (ax, bottom) = plt.subplots(2, 1, figsize=(9.2, 7), gridspec_kw={'height_ratios': [3, max(1, len(varying) * 0.5)]}, sharex=True)
    x = np.arange(1, len(valid) + 1)
    for i, row in enumerate(valid, 1):
        result = row['result']
        color = '#25775c' if result['pvalue'] < 0.05 else '#526478'
        has_ci = result['ci_low'] is not None and result['ci_high'] is not None
        if has_ci:
            ax.errorbar(i, result['estimate'], yerr=[[result['estimate'] - result['ci_low']], [result['ci_high'] - result['estimate']]], fmt='o', capsize=6, color=color)
        else:
            ax.plot(i, result['estimate'], marker='s', color=color, fillstyle='none')
        extra = '' if has_ci else '\nCI not supplied'
        ax.annotate(f'{row['spec_id']}\np={result['pvalue']:.4g}' + extra, (i, result['estimate']), xytext=(12, 10), textcoords='offset points', fontsize=10)
    ax.axhline(0, color='#a2aab3', lw=1, ls='--')
    ax.set_ylabel(plan['target']['effect_scale'], fontproperties=font)
    title = lab.read(out / 'paper.json')['title']
    ci_label = '95% CI' if all((r['result']['ci_low'] is not None for r in valid)) else '95% CI where available'
    ax.set_title(title + f'\n{len(valid)} preselected specifications · ' + ci_label, fontsize=11, pad=16)
    ax.grid(axis='y', alpha=0.2)
    ax.set_xlim(0.4, len(valid) + 0.65)
    labels = []
    for j, d in enumerate(varying):
        lookup = {o['id']: o['label'] for o in d['options']}
        labels.append(d['id'] + ' ' + d['label'])
        for i, row in enumerate(valid, 1):
            oid = specs[row['spec_id']]['choices'][d['id']]
            bottom.text(i, j, oid + ' ' + lookup[oid], ha='center', va='center', fontproperties=font, fontsize=8, wrap=True)
    bottom.set_yticks(range(len(varying)), labels, fontproperties=font, fontsize=8)
    bottom.set_ylim(-0.7, max(0.7, len(varying) - 0.3))
    bottom.invert_yaxis()
    bottom.set_xticks(x, [r['spec_id'] for r in valid])
    bottom.set_xlabel('Specifications ordered by estimate')
    bottom.grid(axis='y', alpha=0.15)
    fig.tight_layout()
    fig.savefig(out / 'specification_curve.png', dpi=180, bbox_inches='tight')
    fig.savefig(out / 'specification_curve.svg', bbox_inches='tight')
    plt.close(fig)

def render_report(studies):
    from csv import DictWriter
    blocks = []
    summary = []
    lines = ['# \u4e24\u7bc7\u8bba\u6587：\u81ea\u52a8 Specification \u8bd5\u8dd1', '', '\u7a0b\u5e8f\u8bfb\u53d6\u8bba\u6587、\u4ee3\u7801\u4e0e\u771f\u5b9e\u6570\u636e，\u7531 DeepSeek \u81ea\u52a8\u786e\u5b9a\u53ef\u68c0\u9a8c\u7684\u7ecf\u9a8c\u5b50\u95ee\u9898、\u751f\u6210\u65b9\u6848\u548c\u5206\u6790\u4ee3\u7801。\u5f00\u53d1\u8005\u672a\u624b\u6539\u79d1\u7814\u5224\u65ad、DAG\u6216\u6548\u5e94\u7ed3\u679c。\u4e24\u7bc7\u5747\u4e3a\u7ecf\u9a8c\u5b50\u95ee\u9898\u8bd5\u8dd1，\u4e0d\u662f\u539f\u8bba\u6587\u6574\u4f53\u590d\u73b0。', '', '\u6bcf\u7bc7\u65b9\u6848\u5148\u56fa\u5b9a\u518d\u8fd0\u884c；\u66f2\u7ebf\u53ea\u67092–3\u4e2a\u9884\u9009\u70b9，\u4e0d\u4ee3\u8868\u7a77\u5c3d\u5408\u7406\u65b9\u6848\u6216\u5b8c\u6210\u6b63\u5f0f\u7a33\u5065\u6027\u68c0\u9a8c。\u539f\u4e09\u7bc7\u4e2d\u7684 MTNN \u4e3b\u5047\u8bbe“\u7b97\u6cd5\u8bef\u5dee\u66f4\u5c0f”\u4e0d\u5728\u672c\u6b21\u68c0\u9a8c\u8303\u56f4。', '']
    for out in studies:
        paper = lab.read(out / 'paper.json')
        intake = lab.read(out / 'intake.json')
        plan = lab.read(out / 'specification_plan.json') if (out / 'specification_plan.json').exists() else None
        rows = lab.read(out / 'execution_results.json') if (out / 'execution_results.json').exists() else []
        status = 'ok' if rows and all((r['status'] == 'ok' for r in rows)) else 'failed'
        summary.append({'paper_id': paper['paper_id'], 'title': paper['title'], 'group': paper['group'], 'status': status, 'h1': intake['hypothesis']['text'], 'specifications': len(rows), 'scope_change': intake['difference_from_original_h1']})
        lines += ['', '## ' + paper['title'], '', '**\u672c\u6b21 H1：** ' + intake['hypothesis']['text'], '', '**\u8303\u56f4\u533a\u522b：** ' + intake['difference_from_original_h1'], '']
        table = []
        if rows:
            plot_curve(out, rows)
            for row in rows:
                if row['status'] == 'ok':
                    table.append({'spec_id': row['spec_id'], **{k: row['result'][k] for k in ('estimate', 'std_error', 'pvalue', 'ci_low', 'ci_high', 'nobs')}})
            with (out / 'estimates.csv').open('w', encoding='utf-8-sig', newline='') as f:
                writer = DictWriter(f, fieldnames=list(table[0]) if table else ['spec_id'])
                writer.writeheader()
                writer.writerows(table)
            lines += ['| \u65b9\u6848 | \u4f30\u8ba1\u503c | P\u503c（\u53cc\u4fa7） | 95% CI | \u6837\u672c\u91cf |', '|---|---:|---:|---|---:|']
            for r in table:
                ci = f'[{r['ci_low']:.6g}, {r['ci_high']:.6g}]' if r['ci_low'] is not None and r['ci_high'] is not None else '\u8be5\u63a8\u65ad\u672a\u63d0\u4f9b\u533a\u95f4'
                lines.append(f'| {r['spec_id']} | {r['estimate']:.6g} | {r['pvalue']:.6g} | {ci} | {r['nobs']} |')
            lines += ['', f'![Specification Curve]({paper['paper_id']}/specification_curve.png)', '']
        else:
            err = lab.read(out / 'pipeline_error.json') if (out / 'pipeline_error.json').exists() else {'error': 'Not executed'}
            lines += ['\u6267\u884c\u672a\u5b8c\u6210：' + str(err['error'])]
        limits = list(intake['limitations']) + (plan.get('comparison_limits', []) if plan else [])
        if (out / 'accepted_audit.json').exists():
            limits += lab.read(out / 'accepted_audit.json').get('limitations', [])
        diagnostic_review = lab.read(out / 'accepted_diagnostics_audit.json') if (out / 'accepted_diagnostics_audit.json').exists() else None
        if diagnostic_review:
            limits += diagnostic_review.get('limitations', [])
            lines += ['', '**\u6267\u884c\u540e\u7ed3\u6784\u8bca\u65ad\u590d\u6838（\u6a21\u578b\u5224\u65ad）：** ' + diagnostic_review['overall']]
        if paper['group'] == 'outside':
            lines += ['', '\u7a0b\u5e8f\u9636\u6bb5\u8bf4\u660e：\u672c\u7bc7\u7684DAG\u5728H1\u53ef\u884c\u6027\u68c0\u67e5\u540e\u81ea\u52a8\u751f\u6210，intake\u4e2d“\u672a\u63d0\u4f9bDAG”\u7684\u63cf\u8ff0\u5bf9\u5e94\u8f93\u5165\u65f6\u70b9；\u5f53\u524d input_dag.json \u5df2\u5b58\u5728。']
        lines += ['', '**\u65b9\u6848\u4e0e\u6761\u4ef6：**']
        if plan:
            for s in plan['specifications']:
                lines.append('- ' + s['spec_id'] + ' ' + s['label'] + '：' + s['scientific_rationale'])
        lines += ['', '**\u4e3b\u8981\u5c40\u9650：**'] + ['- ' + v for v in dict.fromkeys(limits)]
        esc = html.escape
        headers = ''.join(('<th>' + esc(k) + '</th>' for k in table[0])) if table else ''
        cells = ''.join(('<tr>' + ''.join(('<td>' + esc(str(v)) + '</td>' for v in r.values())) + '</tr>' for r in table))
        diagnostic_note = '<p><b>\u6267\u884c\u540e\u590d\u6838\u4e0e\u5c40\u9650：</b>' + esc(diagnostic_review['overall']) + '</p>' if diagnostic_review else ''
        blocks.append('<section><h2>' + esc(paper['title']) + '</h2><p><b>H1：</b>' + esc(intake['hypothesis']['text']) + '</p><p><b>\u4e0e\u4e3b\u5047\u8bbe\u7684\u533a\u522b：</b>' + esc(intake['difference_from_original_h1']) + '</p>' + diagnostic_note + ('<img src="' + paper['paper_id'] + '/specification_curve.png" alt="Specification Curve"><table><tr>' + headers + '</tr>' + cells + '</table>' if rows else '<p>\u6267\u884c\u5931\u8d25，\u8be6\u89c1\u4fdd\u5b58\u7684\u9519\u8bef\u8bb0\u5f55。</p>') + '<details><summary>\u65b9\u6848、\u7ea6\u675f\u4e0e\u63a8\u65ad\u65b9\u5f0f</summary><pre>' + esc(lab.dumps(plan)) + '</pre></details><details><summary>\u8fd0\u884c\u8bca\u65ad\u548c\u7edf\u8ba1\u5c40\u9650</summary><pre>' + esc(lab.dumps({'results': rows, 'limitations': limits})) + '</pre></details></section>')
    lines += ['', '## \u624b\u52a8\u8fd0\u884c', '', '\u5728\u9879\u76ee\u76ee\u5f55\u8fd0\u884c `run_specification_trial.ps1 -Replay`：\u4ece\u4fdd\u5b58\u7684\u6a21\u578b\u54cd\u5e94\u91cd\u653e\u65b9\u6848\u4e0e\u4ee3\u7801，\u5e76\u91cd\u65b0\u8ba1\u7b97\u771f\u5b9e\u6570\u636e\u5206\u6790\u7ed3\u679c，\u4e0d\u8bbf\u95ee DeepSeek。\u6b63\u5e38\u8fd0\u884c\u590d\u7528\u5df2\u6709\u5339\u914d\u7f13\u5b58，\u7f3a\u5931\u7f13\u5b58\u624d\u8c03\u7528\u6a21\u578b。\u8be6\u89c1 README_SPECIFICATION_TRIAL.md。', '']
    (OUT / 'README_\u79d1\u7814\u8ba8\u8bba.md').write_text('\n'.join(lines), encoding='utf-8')
    quick = ['# \u4e24\u7bc7 Specification \u5feb\u901f\u8bd5\u8dd1\u7ed3\u679c', '', '\u540c\u4e00\u7a0b\u5e8f\u5b8c\u6210：\u771f\u5b9e\u6570\u636e\u8bfb\u53d6 → H1\u4e0eDAG\u9002\u7528\u6027\u68c0\u67e5 → 2–3\u4e2a\u9884\u9009\u65b9\u6848 → \u81ea\u52a8\u751f\u6210\u4ee3\u7801\u4e0e\u590d\u6838 → \u8fd0\u884c → \u4f30\u8ba1\u503c/P\u503c/\u66f2\u7ebf。\u79d1\u7814\u5224\u65ad\u548c\u5206\u6790\u4ee3\u7801\u5747\u7531DeepSeek\u4ea7\u751f，\u5f00\u53d1\u8005\u672a\u624b\u6539DAG\u6216\u6548\u5e94\u7ed3\u679c。', '', '\u4e24\u7bc7\u5747\u4e3a\u4ece\u539f\u6587\u9009\u62e9\u7684\u7ecf\u9a8c\u5b50\u95ee\u9898，\u4e0d\u662f\u539f\u8bba\u6587\u5b8c\u6574\u590d\u73b0。MTNN\u8fd9\u6b21\u4e0d\u68c0\u9a8c“\u7b97\u6cd5\u8bef\u5dee\u66f4\u5c0f”。', '']
    for study in studies:
        paper = lab.read(study / 'paper.json')
        intake = lab.read(study / 'intake.json')
        quick += ['## ' + paper['title'], '', 'H1：' + intake['hypothesis']['text'], '', '| \u65b9\u6848 | \u4f30\u8ba1\u503c | \u53cc\u4fa7P\u503c | \u6709\u6548\u6837\u672c\u91cf |', '|---|---:|---:|---:|']
        if (study / 'execution_results.json').exists():
            for row in lab.read(study / 'execution_results.json'):
                if row['status'] == 'ok':
                    rr = row['result']
                    quick.append(f'| {row['spec_id']} | {rr['estimate']:.6g} | {rr['pvalue']:.6g} | {rr['nobs']} |')
        quick += ['', f'![Specification Curve]({study.name}/specification_curve.png)', '']
        if (study / 'accepted_diagnostics_audit.json').exists():
            quick += ['\u6a21\u578b\u5bf9\u5b9e\u9645\u8fd0\u884c\u7684\u590d\u6838：' + lab.read(study / 'accepted_diagnostics_audit.json')['overall'], '']
    quick += ['## \u5982\u4f55\u8bc4\u4ef7', '', '\u8fd9\u53ea\u662f2–3\u4e2a\u65b9\u6848\u7684\u6d41\u7a0b\u8bd5\u9a8c，\u4e0d\u8986\u76d6\u5b8c\u6574\u5206\u6790\u7a7a\u95f4，\u4e0d\u80fd\u636e\u6b64\u5ba3\u79f0\u7a33\u5065。\u81ea\u52a8\u590d\u6838\u4ecd\u6709\u5206\u6b67，\u5168\u90e8\u62d2\u7edd/\u4fee\u590d\u8bb0\u5f55\u4fdd\u7559；\u7edf\u8ba1\u8bc6\u522b\u5047\u8bbe\u4e0e\u63a8\u65ad\u65b9\u5f0f\u6ca1\u6709\u7ecf\u8fc7\u72ec\u7acb\u4e13\u5bb6\u9a8c\u8bc1。\u7f6e\u6362\u65b9\u6848\u5982\u672a\u63d0\u4f9b\u533a\u95f4，\u4fdd\u7559\u4e3a\u7a7a，\u4e0d\u8865\u9020\u6807\u51c6\u8bef\u6216\u7f6e\u4fe1\u533a\u95f4。', '', '\u5b8c\u6574H1\u5dee\u5f02、\u65b9\u6848\u548c\u5c40\u9650\u89c1 README_\u79d1\u7814\u8ba8\u8bba.md \u4e0e index.html；\u4ee3\u7801\u5165\u53e3\u548c\u624b\u52a8\u8fd0\u884c\u89c1\u9879\u76ee\u6839\u76ee\u5f55 README_SPECIFICATION_TRIAL.md。', '']
    (OUT / 'README_\u5feb\u901f\u7ed3\u679c.md').write_text('\n'.join(quick), encoding='utf-8')
    (OUT / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Specification \u8bd5\u8dd1</title><style>body{max-width:1100px;margin:35px auto;padding:0 20px;font:16px/1.7 sans-serif;color:#233342}img{max-width:100%}section{margin:40px 0}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:8px;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>\u4e24\u7bc7\u8bba\u6587 · Specification Curve</h1><p>\u771f\u5b9e\u6570\u636e\u8ba1\u7b97；\u65b9\u6848\u9884\u5148\u56fa\u5b9a；2–3\u4e2a\u70b9\u4ec5\u4f5c\u6d41\u7a0b\u8bd5\u8dd1；\u4e0d\u4ee3\u8868\u5b8c\u6574\u7a33\u5065\u6027\u7ed3\u8bba。\u539f\u6709Graph\u672a\u4fee\u6539。</p>' + ''.join(blocks), encoding='utf-8')
    lab.save(OUT / 'summary.json', summary)

def main(args):
    model_runner.verify_provider(lab.read(ROOT / 'config_high.json'), OUT, args.replay)
    studies = [OUT / x['paper_id'] for x in lab.read(OUT / 'selection.json')['selected']]
    before = {str(p.relative_to(ROOT)): lab.sha(p.read_bytes()) for p in (ROOT / 'results').rglob('*') if p.is_file() and p.suffix in ('.json', '.svg')}

    def work(out):
        try:
            plan_one(out, args.replay)
            if not args.plan_only:
                implement_one(out, args.replay)
            return {'paper_id': out.name, 'ok': True}
        except Exception as exc:
            lab.save(out / 'pipeline_error.json', {'error': str(exc)})
            print(out.name + ' ERROR ' + str(exc), flush=True)
            return {'paper_id': out.name, 'ok': False, 'error': str(exc)}
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(work, studies))
    if not args.plan_only:
        render_report(studies)
    after = {str(p.relative_to(ROOT)): lab.sha(p.read_bytes()) for p in (ROOT / 'results').rglob('*') if p.is_file() and p.suffix in ('.json', '.svg')}
    if before != after:
        raise ValueError('Original input DAG/results changed')
    lab.save(OUT / 'verification.json', {'studies': statuses, 'original_dags_unchanged': before == after, 'runtime_versions': runtime_versions(), 'h1_scope': 'model_inferred_empirical_subquestions', 'human_test_labels_used': False, 'post_result_specification_selection': False})
    return 0 if all((x['ok'] for x in statuses)) else 1
if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--replay', action='store_true')
    p.add_argument('--plan-only', action='store_true')
    sys.exit(main(p.parse_args()))
