# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Mechanical sign/significance evaluation from frozen, declared scientific contracts.

Never invents a P value, infers a P from an exploratory interval, or groups by every Option.
"""
import hashlib, json, math
from collections import defaultdict, Counter
from pathlib import Path

def canonical(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def configuration_key(spec):
    obj = {k: spec.get(k) for k in ['group_id', 'choices', 'selected_options', 'comparison_definition', 'output_contract']}
    return hashlib.sha256(canonical(obj).encode()).hexdigest()

def effective_inference(spec):
    result = dict(spec.get('output_contract', {}).get('inference', {}))
    for option in spec.get('selected_options', {}).values():
        p = option.get('parameters', {})
        if p.get('inference_policy') in ['formal_test', 'conditional_formal_test', 'not_identifiable']:
            result['policy'] = p['inference_policy']
            for k in ['test_name', 'alternative', 'alpha']:
                if k in p:
                    result[k] = p[k]
    return result

def classify(spec, record):
    ev = spec['comparison_definition']['evaluation']
    frozen = effective_inference(spec)
    row = {'spec_id': spec['spec_id'], 'family_id': spec['group_id'], 'plot_group': ev['plot_group'], 'plot_title': ev['plot_title'], 'plot_unit': ev['plot_unit'], 'null_value': ev['null_value'], 'effect_kind': ev['effect_kind'], 'direction_multiplier': ev['direction_multiplier'], 'choices': spec['choices'], 'configuration_key': configuration_key(spec), 'status': record['status'], 'direction': None, 'significant': None, 'p_status': 'not_executed', 'p_value': None, 'effect_size': None, 'ci_lower': None, 'ci_upper': None, 'reason': record.get('error'), 'frozen_inference_policy': frozen.get('policy'), 'alpha': frozen.get('alpha')}
    if record['status'] != 'success':
        return row
    result = record['result']
    effect = result['effect_size']
    if not isinstance(effect, (float, int)) or not math.isfinite(effect):
        row.update(status='failed', reason='Nonfinite effect')
        return row
    delta = (effect - ev['null_value']) * ev['direction_multiplier']
    direction = 'positive' if delta > 0 else 'negative' if delta < 0 else 'zero'
    row.update(effect_size=effect, direction=direction, ci_lower=result.get('ci_lower'), ci_upper=result.get('ci_upper'), inference=result.get('inference', {}), reason=None)
    p = result.get('p_value')
    inf = result.get('inference', {})
    if p is None:
        row.update(p_status='NA', reason=inf.get('reason', 'P unavailable; never classified as nonsignificant'))
        return row
    if not isinstance(p, (int, float)) or isinstance(p, bool) or (not math.isfinite(p)) or (not 0 <= p <= 1):
        row.update(p_status='invalid', reason='Invalid P')
        return row
    expected = frozen.get('policy')
    if expected not in ['formal_test', 'conditional_formal_test'] or inf.get('status') != expected:
        row.update(p_status='invalid', reason='P not supported by frozen formal inference contract')
        return row
    if inf.get('alternative') != frozen.get('alternative') or inf.get('alpha') != frozen.get('alpha') or inf.get('null_value') != ev['null_value']:
        row.update(p_status='invalid', reason='P metadata differs from frozen null/alpha/alternative')
        return row
    row.update(p_status='valid', p_value=p, significant=p < float(frozen['alpha']), inference_kind=expected)
    return row

def ratio(n, d):
    return n / d if d else None

def summarize(rows, author=None):
    success = [r for r in rows if r['status'] == 'success' and r['direction'] is not None]
    tested = [r for r in success if r['p_status'] == 'valid']
    counts = Counter((r['direction'] for r in success))
    significant = [r for r in tested if r['significant']]
    out = {'total_paths': len(rows), 'successful_effects': len(success), 'failed_paths': len(rows) - len(success), 'valid_tests': len(tested), 'p_unavailable': sum((r['p_status'] == 'NA' for r in success)), 'p_invalid': sum((r['p_status'] == 'invalid' for r in success)), 'positive_count': counts['positive'], 'negative_count': counts['negative'], 'zero_count': counts['zero'], 'positive_fraction': ratio(counts['positive'], len(success)), 'negative_fraction': ratio(counts['negative'], len(success)), 'zero_fraction': ratio(counts['zero'], len(success)), 'significant_count': len(significant), 'nonsignificant_count': sum((not r['significant'] for r in tested)), 'significant_fraction': ratio(len(significant), len(tested)), 'positive_and_significant_fraction': ratio(sum((r['direction'] == 'positive' for r in significant)), len(tested)), 'negative_and_significant_fraction': ratio(sum((r['direction'] == 'negative' for r in significant)), len(tested)), 'direction_denominator': len(success), 'significance_denominator': len(tested), 'author_direction_comparison': None, 'author_significance_comparison': None}
    if author:
        own_direction = []
        own_sig = []
        for r in success:
            ref = author.get(r['family_id'])
            if not ref or not ref.get('same_scientific_question'):
                continue
            direction = ref.get('author_reported_direction')
            if direction in ['positive', 'negative', 'zero']:
                own_direction.append(r['direction'] == direction)
            status = ref.get('author_significance')
            threshold = ref.get('reported_alpha')
            if r['p_status'] == 'valid' and status in ['significant', 'not_significant'] and (threshold is not None) and math.isclose(threshold, r['alpha'], rel_tol=0, abs_tol=1e-12):
                own_sig.append(r['significant'] == (status == 'significant'))
        out['author_direction_comparison'] = {'eligible_paths': len(own_direction), 'agreement_fraction': ratio(sum(own_direction), len(own_direction))}
        out['author_significance_comparison'] = {'eligible_paths': len(own_sig), 'agreement_fraction': ratio(sum(own_sig), len(own_sig))}
    return out

def evaluate(specifications, records, references):
    specs = {s['spec_id']: s for s in specifications}
    received = {r['spec_id']: r for r in records}
    if len(received) != len(records) or set(received) != set(specs):
        raise ValueError('Every frozen path needs exactly one actual execution receipt')
    refs = {r['family_id']: r for r in references}
    rows = [classify(s, received[sid]) for sid, s in specs.items()]
    groups = defaultdict(list)
    for row in rows:
        groups[row['plot_group']].append(row)
    summaries = []
    for gid, items in groups.items():
        signatures = {(r['plot_unit'], r['effect_kind'], r['null_value'], r['direction_multiplier']) for r in items}
        if len(signatures) != 1:
            raise ValueError('Incompatible frozen axis/null contracts inside plot_group ' + gid)
        unique = {}
        for r in items:
            unique.setdefault(r['configuration_key'], r)
        summaries.append({'plot_group': gid, 'title': items[0]['plot_title'], 'unit': items[0]['plot_unit'], 'null_value': items[0]['null_value'], 'raw_paths': summarize(items, refs), 'structural_configurations': summarize(list(unique.values()), refs), 'unique_numerical_effects_12dp': len({round(r['effect_size'], 12) for r in items if r['status'] == 'success'}), 'deduplication_note': 'Structural frozen analysis/test configuration only; no equivalence claim from equal numerical effects. These fractions are sensitivity summaries, not independent evidence or hypothesis probabilities.'})
    return ({'groups': summaries, 'overall_path_inventory': {'total_paths': len(rows), 'plot_groups': len(groups), 'valid_tests': sum((r['p_status'] == 'valid' for r in rows)), 'failed': sum((r['status'] != 'success' for r in rows))}, 'policy': 'Compare direction and valid-test significance, not author-value distance. NA is excluded from significance denominator, never NS.'}, rows)

def evaluate_run(out):
    out = Path(out)
    load = lambda n: json.loads((out / n).read_text(encoding='utf-8'))
    lock = load('blind_results_lock.json')
    if hashlib.sha256((out / 'execution_results_round_0.json').read_bytes()).hexdigest() != lock['results_sha256']:
        raise ValueError('Independent results changed after freeze')
    result, rows = evaluate(load('specifications.json')['specifications'], load('execution_results_round_0.json')['results'], load('author_reference.json')['references'])
    for name, data in [('evaluation.json', result), ('evaluated_paths.json', rows)]:
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    return result
