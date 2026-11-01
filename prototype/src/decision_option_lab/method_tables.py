# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Cheap classification/merge-review tables from frozen instances; no new paper extraction."""
import argparse
from collections import Counter, defaultdict
import itertools
import json
import os
from pathlib import Path
import re
import sys
import lab
import merge
ROOT = Path(__file__).resolve().parent
SIG = ('function_key', 'object_role_key', 'mechanism_key')
KINDS = ('method', 'strategy', 'metric')

def signature_ok(value):
    return isinstance(value, dict) and set(value) == set(SIG) and all((isinstance(value[k], str) and value[k].strip() for k in SIG))

def classification_errors(obj, refs):
    errors = []
    for field in ('families', 'methods', 'rows', 'suggested_pairs', 'limitations'):
        if not isinstance(obj.get(field), list):
            errors.append(field + ' array required')
    families = {}
    methods = {}
    for items, prefix, lookup, keys in [(obj.get('families', []), 'F', families, ('name', 'kind', 'definition', 'scientific_function', 'operation_object', 'mechanism_scope', 'inclusion_boundary')), (obj.get('methods', []), 'M', methods, ('family_id', 'name', 'kind', 'definition', 'scientific_function', 'operation_object', 'mechanism', 'semantic_signature', 'aliases', 'parameter_slots', 'parent_reason'))]:
        for item in items:
            iid = item.get('id')
            if not isinstance(iid, str) or not re.fullmatch(prefix + '[1-9][0-9]*', iid):
                errors.append('Invalid ' + prefix + ' id')
            if iid in lookup:
                errors.append('Duplicate catalog ID')
            lookup[iid] = item
            for key in keys:
                if key not in item:
                    errors.append(f'{iid} missing {key}')
            if item.get('kind') not in KINDS:
                errors.append('Invalid family/method kind')
    for mid, m in methods.items():
        f = families.get(m.get('family_id'))
        if not f:
            errors.append(mid + ' missing parent family')
        elif f['kind'] != m.get('kind'):
            errors.append(mid + ' kind differs from parent family')
        if not signature_ok(m.get('semantic_signature')):
            errors.append(mid + ' invalid semantic signature')
        if not isinstance(m.get('aliases'), list) or not isinstance(m.get('parameter_slots'), list):
            errors.append(mid + ' aliases/slots arrays required')
    rows = obj.get('rows', [])
    if Counter((r.get('source_ref') for r in rows)) != Counter(refs):
        errors.append('Rows must cover each original option exactly once')
    components = []
    used = set()

    def parameters_ok(parameters):
        return isinstance(parameters, list) and all((isinstance(p, dict) and all((k in p for k in ('name', 'value', 'basis'))) and (p['basis'] in ('input_reported', 'inferred', 'unknown')) for p in parameters))
    for row in rows:
        ref = row.get('source_ref')
        if row.get('entity_kind') not in (*KINDS, 'parameter_setting', 'workflow_bundle', 'uncertain'):
            errors.append(str(ref) + ' invalid entity kind')
        if row.get('composition') not in ('atomic', 'composite', 'parameter_only', 'unclear'):
            errors.append(str(ref) + ' invalid composition')
        for key in ('components', 'option_parameters', 'retained_conditions', 'uncertainties'):
            if not isinstance(row.get(key), list):
                errors.append(str(ref) + ' ' + key + ' array required')
        cs = row.get('components', [])
        if row.get('composition') == 'atomic' and len(cs) != 1:
            errors.append(str(ref) + ' atomic needs one component')
        if (row.get('composition') == 'composite' or row.get('entity_kind') == 'workflow_bundle') and len(cs) < 2:
            errors.append(str(ref) + ' composite needs >=2 components')
        if row.get('composition') == 'parameter_only' and (cs or not row.get('option_parameters')):
            errors.append(str(ref) + ' parameter_only needs parameter settings and no method component')
        if row.get('entity_kind') == 'uncertain' and (not row.get('uncertainties')):
            errors.append('uncertain row must explain uncertainty')
        if row.get('composition') == 'unclear' and (not row.get('uncertainties')):
            errors.append('unclear composition must explain uncertainty')
        if row.get('entity_kind') != 'uncertain' and row.get('composition') not in ('parameter_only',) and (not cs):
            errors.append(str(ref) + ' requires component or uncertainty')
        if not parameters_ok(row.get('option_parameters')):
            errors.append(str(ref) + ' invalid option parameter')
        for comp in cs:
            cid = comp.get('id')
            components.append(cid)
            if not isinstance(cid, str) or not re.fullmatch('C[1-9][0-9]*', cid):
                errors.append('Invalid component ID')
            mid = comp.get('method_id')
            m = methods.get(mid)
            if not m:
                errors.append(str(cid) + ' unknown method')
            else:
                used.add(mid)
                if comp.get('semantic_signature') != m.get('semantic_signature'):
                    errors.append(str(cid) + ' signature must match assigned specific method')
            if comp.get('role') not in ('primary', 'component'):
                errors.append(str(cid) + ' invalid role')
            if not parameters_ok(comp.get('parameters')):
                errors.append(str(cid) + ' invalid parameters')
            if not isinstance(comp.get('applicability_conditions'), list) or not comp.get('assignment_reason'):
                errors.append(str(cid) + ' conditions/reason required')
    if len(components) != len(set(components)):
        errors.append('Duplicate component IDs')
    if set(methods) != used:
        errors.append('Every method must have instance support')
    if set(families) != {m.get('family_id') for m in methods.values()}:
        errors.append('Every family must have method support')
    seen = set()
    for pair in obj.get('suggested_pairs', []):
        a, b = (pair.get('a'), pair.get('b'))
        key = frozenset((a, b))
        if a not in methods or b not in methods or a == b or (key in seen) or (not pair.get('reason')):
            errors.append('Invalid suggested pair')
        seen.add(key)
    return errors

def candidates(catalog, old):
    methods = {m['id']: m for m in catalog['methods']}
    new_by_ref = {r['source_ref']: {c['method_id'] for c in r['components']} for r in catalog['rows']}
    pool = {}

    def add(a, b, reason):
        if a == b:
            return
        a, b = sorted((a, b), key=lambda n: int(n[1:]))
        pool.setdefault((a, b), set()).add(reason)
    families = defaultdict(list)
    signatures = defaultdict(list)
    for m in catalog['methods']:
        families[m['family_id']].append(m['id'])
        signatures[tuple((m['semantic_signature'][k] for k in SIG))].append(m['id'])
    for values in families.values():
        for a, b in itertools.combinations(values, 2):
            add(a, b, 'same_family')
    for values in signatures.values():
        for a, b in itertools.combinations(values, 2):
            add(a, b, 'same_declared_signature')
    old_to_new = defaultdict(set)
    for row in old['catalog']['option_mappings']:
        for assignment in row['methods']:
            old_to_new[assignment['type_id']] |= new_by_ref.get(row['source_ref'], set())
    for oldid, values in old_to_new.items():
        for a, b in itertools.combinations(sorted(values), 2):
            add(a, b, 'previous_shared_type:' + oldid)
    for issue in old.get('model_review', {}).get('issues', []):
        ids = set(re.findall('\\bMT[0-9]+\\b', ' '.join((str(issue.get(k, '')) for k in ('target_id', 'problem', 'suggestion')))))
        current = set().union(*(old_to_new.get(i, set()) for i in ids)) if ids else set()
        for a, b in itertools.combinations(sorted(current), 2):
            add(a, b, 'previous_review_overlap')
    for p in catalog['suggested_pairs']:
        add(p['a'], p['b'], 'model_nominated:' + p['reason'])
    result = [{'pair_id': f'Q{i:03}', 'a': a, 'b': b, 'candidate_reasons': sorted(reasons)} for i, ((a, b), reasons) in enumerate(sorted(pool.items(), key=lambda x: (int(x[0][0][1:]), int(x[0][1][1:]))), 1)]
    if len(result) > 300:
        raise ValueError('Quick-test cap exceeded: >300 candidate pairs; no pairs silently dropped')
    return result

def comparison_errors(obj, pairs):
    errors = []
    lookup = {p['pair_id']: p for p in pairs}
    if not isinstance(obj.get('assessments'), list) or not isinstance(obj.get('limitations'), list):
        return ['assessments/limitations arrays required']
    if Counter((a.get('pair_id') for a in obj['assessments'])) != Counter(list(lookup)):
        errors.append('Assess each candidate pair exactly once')
    for a in obj['assessments']:
        if a.get('relation') not in ('synonym', 'parameter_variant', 'parent_child', 'different', 'uncertain'):
            errors.append('Invalid relation')
        if a.get('recommendation') not in ('merge_aliases', 'share_method_keep_parameters', 'retain_parent_child', 'keep_separate', 'manual_review'):
            errors.append('Invalid recommendation')
        if any((type(a.get(k)) is not bool for k in ('function_same', 'object_same', 'mechanism_same'))):
            errors.append('Three semantic comparison booleans required')
        if not a.get('reason') or not isinstance(a.get('conditions_to_keep'), list):
            errors.append('Comparison reason/conditions required')
        p = lookup.get(a.get('pair_id'))
        if p and a.get('relation') == 'parent_child':
            if {a.get('parent_id'), a.get('child_id')} != {p['a'], p['b']}:
                errors.append('parent/child must be the two compared methods')
        elif a.get('parent_id') is not None or a.get('child_id') is not None:
            errors.append('Nonhierarchical comparison must not declare parent/child')
    return errors

def rule_check(assessment, pair, methods):
    a, b = (methods[pair['a']], methods[pair['b']])
    wants_merge = assessment['recommendation'] in ('merge_aliases', 'share_method_keep_parameters')
    if not wants_merge:
        reasons = ['\u672c\u8f6e\u53ea\u51fa\u5ba1\u6838\u8868，\u4e0d\u81ea\u52a8\u6267\u884c\u5408\u5e76\u6216\u5c42\u7ea7\u4fee\u6539。']
        if assessment['relation'] == 'parent_child':
            reasons.append('\u4e24\u8005\u5f53\u524d\u5747\u5217\u5728\u5177\u4f53\u65b9\u6cd5\u5c42；\u8be5\u5efa\u8bae\u63d0\u793a\u7c92\u5ea6\u9700\u91cd\u5ba1，\u672a\u81ea\u52a8\u589e\u52a0\u7b2c\u56db\u5c42。')
        return {'status': 'review_only', 'reasons': reasons}
    blocked = []
    expected = {'merge_aliases': 'synonym', 'share_method_keep_parameters': 'parameter_variant'}
    if assessment['relation'] != expected[assessment['recommendation']]:
        blocked.append('\u5173\u7cfb\u7c7b\u578b\u4e0e\u5408\u5e76\u5efa\u8bae\u4e0d\u4e00\u81f4')
    if not all((assessment[k] for k in ('function_same', 'object_same', 'mechanism_same'))):
        blocked.append('\u6a21\u578b\u672a\u540c\u65f6\u5224\u5b9a\u529f\u80fd、\u5bf9\u8c61、\u673a\u5236\u4e00\u81f4')
    if a['kind'] != b['kind']:
        blocked.append('\u5bf9\u8c61\u6027\u8d28\u4e0d\u4e00\u81f4（\u65b9\u6cd5/\u7b56\u7565/\u6307\u6807）')
    if a['semantic_signature'] != b['semantic_signature']:
        blocked.append('\u58f0\u660e\u7684\u8bed\u4e49\u7b7e\u540d\u4e0d\u4e00\u81f4，\u9700\u5148\u4eba\u5de5\u5ba1\u67e5\u6216\u7531\u6a21\u578b\u91cd\u5ba1')
    return {'status': 'blocked' if blocked else 'eligible_for_review', 'reasons': blocked or ['\u4ec5\u901a\u8fc7\u8868\u793a\u5c42\u4e00\u81f4\u6027\u68c0\u67e5；\u7b49\u5f85\u4eba\u5de5\u5ba1\u6838，\u672a\u6267\u884c\u5408\u5e76。']}

def revalidate_saved(stage, material, cfg, out, validator):
    """Recover an unchanged raw response after a validator fix; never call the API here."""
    expected = {'model': cfg['model'], 'messages': [{'role': 'system', 'content': (ROOT / 'prompts' / f'{stage}.txt').read_text(encoding='utf-8')}, {'role': 'user', 'content': lab.dumps(material)}], 'temperature': 0, 'thinking': {'type': 'disabled'}, 'response_format': {'type': 'json_object'}, 'max_tokens': cfg['max_tokens']}
    fingerprint = lab.sha(lab.dumps({'body': expected, 'endpoint': cfg['base_url'], 'repairs': cfg['max_structural_repairs'], 'validator_version': 1}).encode('utf-8'))
    cache = out / 'cache' / fingerprint
    if (cache / 'accepted.json').exists() or not (cache / 'request_0.json').exists():
        return
    if lab.read(cache / 'request_0.json') != expected:
        return
    for path in sorted(cache.glob('response_*.json')):
        raw = lab.read(path)
        choice = raw['choices'][0]
        if choice.get('finish_reason') != 'stop':
            continue
        try:
            obj = json.loads(choice['message']['content'])
            errors = validator(obj)
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        if not errors:
            lab.save(cache / 'accepted.json', obj)
            lab.save(cache / 'validation_recheck.json', {'current_errors': [], 'raw_response_file': path.name, 'raw_response_sha256': lab.sha(path.read_bytes()), 'note': '\u9a8c\u8bc1\u5668\u4fee\u590d\u540e\u5bf9\u65e2\u5b58\u539f\u59cb\u54cd\u5e94\u91cd\u65b0\u6821\u9a8c；\u672a\u4fee\u6539\u6a21\u578b\u5185\u5bb9，\u672a\u53d1\u51fa\u65b0\u8bf7\u6c42。'})
            print('  Revalidated unchanged saved response: ' + stage, flush=True)
            return

def cell(x):
    if isinstance(x, (dict, list)):
        x = lab.dumps(x)
    return str(x).replace('|', '\\|').replace('\n', '<br>')

def export_tables(out, result, rule_checker=None):
    rule_checker = rule_checker or rule_check
    catalog = result['classification']
    methods = {m['id']: m for m in catalog['methods']}
    families = {f['id']: f for f in catalog['families']}
    rows = []
    for r in catalog['rows']:
        original = result['original_options'][r['source_ref']]
        names = []
        params = []
        profiles = []
        conditions = []
        for comp in r['components']:
            m = methods[comp['method_id']]
            f = families[m['family_id']]
            names.append(f'{f['id']} {f['name']} → {m['id']} {m['name']}（{comp['id']}/{comp['role']}）')
            profiles.append(f'{comp['id']} \u529f\u80fd：{comp.get('scientific_function', m['scientific_function'])}；\u5bf9\u8c61：{comp.get('operation_object', m['operation_object'])}；\u673a\u5236：{comp.get('mechanism', m['mechanism'])}')
            params.extend(({'component': comp['id'], **p} for p in comp['parameters']))
            conditions += comp['applicability_conditions']
        params.extend(({'component': 'option', **p} for p in r['option_parameters']))
        rows.append({'ref': r['source_ref'], 'original_label': original['option']['label'], 'decision': original['decision_label'], 'original_description': original['option']['description'], 'original_origin': original['option']['origin'], 'original_prerequisites': original['option']['prerequisites'], 'original_evidence': original['option'].get('evidence', []), 'original_forbidden_combinations': original.get('original_forbidden_combinations', []), 'entity_kind': r['entity_kind'], 'composition': r['composition'], 'hierarchy': names, 'semantic_profile': profiles, 'parameters': params, 'conditions': r['retained_conditions'] + conditions, 'uncertainties': r['uncertainties'], 'assignment_reasons': [c['assignment_reason'] for c in r['components']]})
    pairlookup = {p['pair_id']: p for p in result['candidate_pairs']}
    comparisons = []
    for a in result['comparison']['assessments']:
        p = pairlookup[a['pair_id']]
        comparisons.append({**p, **a, 'a_name': methods[p['a']]['name'], 'b_name': methods[p['b']]['name'], 'rule_check': rule_checker(a, p, methods)})
    lab.save(out / 'classification_table.json', rows)
    lab.save(out / 'comparison_table.json', comparisons)
    md = ['# \u65b9\u6cd5\u5206\u7c7b\u8868（\u6a21\u578b\u8f93\u51fa，\u5f85\u5ba1\u6838）', '', '\u4ec5\u4f7f\u7528\u5df2\u6709\u4e09\u7bc7\u768451\u4e2a\u9009\u9879。\u539f Decision–Option \u672a\u4fee\u6539；\u6307\u6807、\u7b56\u7565\u548c\u53c2\u6570\u4e0d\u5f3a\u884c\u5f52\u4e3a\u4f30\u8ba1\u65b9\u6cd5。input_reported \u53ea\u8868\u793a\u4e0a\u6e38\u6a21\u578b\u8f93\u5165\u4e2d\u51fa\u73b0，\u4e0d\u4ee3\u8868\u539f\u6587\u5df2\u7ecf\u9a8c\u8bc1。', '', '| \u5b9e\u4f8b | \u539f\u59cb\u9009\u9879 | \u5bf9\u8c61\u6027\u8d28/\u7ec4\u5408 | \u5bb6\u65cf → \u5177\u4f53\u65b9\u6cd5（\u7ec4\u6210\u64cd\u4f5c） | \u529f\u80fd、\u5bf9\u8c61、\u673a\u5236 | \u5b9e\u4f8b\u53c2\u6570 | \u6761\u4ef6 | \u5f85\u786e\u8ba4\u9879 |', '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in rows:
        values = [r['ref'], r['original_label'], r['entity_kind'] + ' / ' + r['composition'], r['hierarchy'], r['semantic_profile'], r['parameters'], r['conditions'], r['uncertainties']]
        md.append('| ' + ' | '.join((cell(v) for v in values)) + ' |')
    (out / '01_\u65b9\u6cd5\u5206\u7c7b\u8868.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    md = ['# \u7591\u4f3c\u91cd\u590d\u65b9\u6cd5\u5408\u5e76\u5224\u65ad\u8868（\u672a\u6267\u884c\u5408\u5e76）', '', '\u5019\u9009\u6765\u81ea\u540c\u5bb6\u65cf、\u76f8\u540c\u58f0\u660e\u7b7e\u540d、\u65e7\u7c7b\u578b\u5171\u7528、\u5148\u524d\u5ba1\u9605\u51b2\u7a81\u548c\u6a21\u578b\u63d0\u540d。\u6ca1\u6709\u904d\u5386\u6240\u6709\u4e0d\u540c\u5bb6\u65cf\u65b9\u6cd5\u5bf9；\u672a\u88ab\u7eb3\u5165\u4e0d\u7b49\u4e8e\u4e0d\u540c\u65b9\u6cd5。\u7a0b\u5e8f\u4ec5\u68c0\u67e5\u58f0\u660e\u4e00\u81f4\u6027，\u4e0d\u80fd\u8bc1\u660e\u6a21\u578b\u8bed\u4e49\u6b63\u786e。', '', '| \u914d\u5bf9 | \u65b9\u6cd5 A | \u65b9\u6cd5 B | \u5173\u7cfb | \u529f\u80fd/\u5bf9\u8c61/\u673a\u5236\u76f8\u540c | \u6a21\u578b\u5efa\u8bae | \u7a0b\u5e8f\u68c0\u67e5 | \u7406\u7531 | \u9700\u4fdd\u7559\u6761\u4ef6 | \u5019\u9009\u6765\u6e90 |', '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in comparisons:
        values = [r['pair_id'], r['a'] + ' ' + r['a_name'], r['b'] + ' ' + r['b_name'], r['relation'], [r[k] for k in ('function_same', 'object_same', 'mechanism_same')], r['recommendation'], r['rule_check'], r['reason'], r['conditions_to_keep'], r['candidate_reasons']]
        md.append('| ' + ' | '.join((cell(v) for v in values)) + ' |')
    (out / '02_\u5408\u5e76\u5224\u65ad\u8868.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    data = {'classification_rows': rows, 'comparison_rows': comparisons, 'result': result}
    payload = lab.dumps(data).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    (out / 'index.html').write_text((ROOT / 'method_tables_report.html').read_text(encoding='utf-8').replace('__DATA_JSON__', payload), encoding='utf-8')
    return comparisons

def run(args):
    out = args.output.resolve()
    if args.fresh and out.exists() and any(out.iterdir()):
        raise ValueError('Fresh output folder must be empty')
    out.mkdir(parents=True, exist_ok=True)
    papers = merge.load_papers(args.input)
    old = lab.read(args.previous / 'knowledge_library.json')
    files = [p for p in sorted(args.input.glob('paper_*/*.json')) if p.name in ('context.json', 'options.json', 'sources.json', 'checks.json')] + [args.previous / 'knowledge_library.json']
    hashes = {str(p.resolve()): lab.sha(p.read_bytes()) for p in files}
    original_options = {}
    for p in papers:
        for d in p['space']['decisions']:
            for o in d['options']:
                ref = f'{p['alias']}:{d['id']}:{o['id']}'
                original_options[ref] = {'paper': p['alias'], 'paper_id': p['paper_id'], 'decision_ref': f'{p['alias']}:{d['id']}', 'decision_label': d['label'], 'decision_reason': d['why_a_decision'], 'option': o}
    old_refs = {m['source_ref'] for m in old['catalog']['option_mappings']}
    if old_refs != set(original_options):
        raise ValueError('Previous knowledge library must cover the same original option instances')
    for ref, o in original_options.items():
        if old['option_instances'][ref]['option'] != o['option']:
            raise ValueError('Old/new original options differ')
    cfg = lab.read(args.config)
    cfg['max_tokens'] = 30000
    material = {'original_options': original_options, 'hypotheses': {p['alias']: p['context']['hypothesis'] for p in papers}, 'constraints': {p['alias']: p['space']['forbidden_combinations'] for p in papers}, 'old_methods': old['catalog']['method_types'], 'old_option_mappings': old['catalog']['option_mappings'], 'previous_model_review': old['model_review'], 'option_refs': list(original_options), 'upstream_quote_checks': {p['alias']: p['checks']['evidence']['options'] for p in papers}}
    print(f'Classifying {len(original_options)} frozen option instances', flush=True)
    classified = lab.generate('method_classify', material, cfg, out, lambda x: classification_errors(x, list(original_options)), args.fresh, args.replay)
    pairs = candidates(classified, old)
    lab.save(out / 'candidate_pairs.json', pairs)
    print(f'Comparing {len(pairs)} targeted method pairs', flush=True)
    comparison_material = {'classification': classified, 'original_options': original_options, 'candidate_pairs': pairs}
    if not args.fresh:
        revalidate_saved('method_compare', comparison_material, cfg, out, lambda x: comparison_errors(x, pairs))
    compared = lab.generate('method_compare', comparison_material, cfg, out, lambda x: comparison_errors(x, pairs), args.fresh, args.replay)
    original_unchanged = all((lab.sha(Path(p).read_bytes()) == h for p, h in hashes.items()))
    if not original_unchanged:
        raise ValueError('Original inputs changed')
    for p in papers:
        for d in p['space']['decisions']:
            for o in d['options']:
                original_options[f'{p['alias']}:{d['id']}:{o['id']}']['original_forbidden_combinations'] = [c for c in p['space']['forbidden_combinations'] if c['choices'].get(d['id']) == o['id']]
    result = {'classification': classified, 'comparison': compared, 'candidate_pairs': pairs, 'original_options': original_options, 'original_constraints': {p['alias']: p['space']['forbidden_combinations'] for p in papers}, 'checks': {'papers': len(papers), 'option_instances': len(original_options), 'classification_rows': len(classified['rows']), 'families': len(classified['families']), 'specific_methods': len(classified['methods']), 'components': sum((len(r['components']) for r in classified['rows'])), 'entity_kind_counts': dict(Counter((r['entity_kind'] for r in classified['rows']))), 'family_to_method_links': len(classified['methods']), 'hierarchy_levels': 'family → specific method → instance component', 'candidate_pairs': len(pairs), 'assessed_pairs': len(compared['assessments']), 'relation_counts': dict(Counter((a['relation'] for a in compared['assessments']))), 'input_files_unchanged': original_unchanged, 'original_options_preserved': True, 'knowledge_library_overwritten': False, 'automatic_merges_executed': 0, 'new_paper_extraction': False, 'semantic_accuracy': 'not_evaluated'}}
    methods = {m['id']: m for m in classified['methods']}
    lookup = {p['pair_id']: p for p in pairs}
    result['checks']['merge_rule_counts'] = dict(Counter((rule_check(a, lookup[a['pair_id']], methods)['status'] for a in compared['assessments'])))
    lab.save(out / 'input_manifest.json', {'files_sha256': hashes, 'previous_library': str(args.previous.resolve())})
    lab.save(out / 'trial_result.json', result)
    lab.save(out / 'checks.json', result['checks'])
    export_tables(out, result)
    if (out / 'error.json').exists():
        (out / 'error.json').unlink()
    print(lab.dumps(result['checks']), flush=True)
    print(f'Report: {out / 'index.html'}', flush=True)
if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, default=ROOT / 'results')
    p.add_argument('--previous', type=Path, default=ROOT / 'knowledge_results')
    p.add_argument('--output', type=Path, default=ROOT / 'method_table_results')
    p.add_argument('--config', type=Path, default=ROOT / 'config.json')
    p.add_argument('--replay', action='store_true')
    p.add_argument('--fresh', action='store_true')
    args = p.parse_args()
    if args.replay and args.fresh:
        p.error('Cannot combine --fresh and --replay')
    try:
        run(args)
    except Exception as exc:
        lab.save(args.output / 'error.json', {'error': str(exc)})
        raise
