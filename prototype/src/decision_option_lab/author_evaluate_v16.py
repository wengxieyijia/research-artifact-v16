# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Pure post-freeze evaluation. Never calls a model, Boba, or an estimator."""
import copy, math
from collections import Counter
ALPHA = 0.05
REASONS = {'execution_failed': '\u672c\u8def\u5f84\u6267\u884c\u5931\u8d25', 'own_p_NA': '\u672c\u8def\u5f84P\u503c\u7f3a\u5931', 'own_p_invalid': '\u672c\u8def\u5f84P\u503c\u4e0d\u5408\u89c4', 'no_matching_scope': '\u4f5c\u8005\u53c2\u7167\u4e0e\u6b64\u8def\u5f84\u7684\u65f6\u95f4/\u7ec4\u522b/\u6d4b\u91cf/\u76ee\u6807\u672a\u5339\u914d', 'ambiguous_reference': '\u540c\u4e00\u8def\u5f84\u5339\u914d\u5230\u591a\u4e2a\u4f5c\u8005\u53c2\u7167', 'author_p_missing': '\u4f5c\u8005\u6ca1\u6709\u53ef\u6309\u7edf\u4e00\u9608\u503c\u5224\u65ad\u7684P\u503c\u6216\u5df2\u6838\u5b9e\u9608\u503c\u6807\u7b7e', 'author_p_bound_ambiguous': '\u4f5c\u8005P\u503c\u754c\u9650\u8de8\u8fc7\u8bc4\u4ef7\u9608\u503c', 'author_p_invalid': '\u4f5c\u8005P\u503c\u683c\u5f0f\u6216\u754c\u9650\u65e0\u6548', 'author_text_missing': '\u4f5c\u8005\u672a\u660e\u786e\u62a5\u544a\u663e\u8457/\u4e0d\u663e\u8457\u7ed3\u8bba', 'author_direction_missing': '\u4f5c\u8005\u65b9\u5411\u672a\u660e\u786e\u62a5\u544a'}

def finite_p(v):
    return isinstance(v, (int, float)) and (not isinstance(v, bool)) and math.isfinite(v) and (0 <= v <= 1)

def reference_common_decision(ref, alpha=ALPHA):
    p = ref.get('reported_p_value')
    op = ref.get('p_operator')
    result = {'decision': None, 'basis': None, 'reason_code': None, 'evaluation_alpha': alpha, 'reported_p_value': p, 'p_operator': op, 'author_reported_alpha': ref.get('reported_alpha')}
    if p is not None:
        if not finite_p(p):
            result['reason_code'] = 'author_p_invalid'
            return result
        op = '=' if op is None else str(op).strip().lower().replace('p', '').replace(' ', '').replace('≤', '<=').replace('≥', '>=')
        result['p_operator'] = op
        if op in ['=', '==']:
            result.update(decision=p < alpha, basis='reported_exact_p')
            return result
        if op == '<' and p > 0 and (p <= alpha) or (op == '<=' and p < alpha):
            result.update(decision=True, basis='reported_p_bound')
            return result
        if op == '>' and p < 1 and (p >= alpha) or (op == '>=' and p >= alpha):
            result.update(decision=False, basis='reported_p_bound')
            return result
        result['reason_code'] = 'author_p_bound_ambiguous' if op in ['<', '<=', '>', '>='] else 'author_p_invalid'
        return result
    label = ref.get('author_significance')
    threshold = ref.get('reported_alpha')
    if label in ['significant', 'not_significant'] and isinstance(threshold, (int, float)) and (not isinstance(threshold, bool)) and math.isclose(threshold, alpha, rel_tol=0, abs_tol=1e-12):
        result.update(decision=label == 'significant', basis='explicit_label_with_verified_same_alpha')
        return result
    result['reason_code'] = 'author_p_missing'
    return result

def matched_rule(row, rules, kind):
    matches = []
    for rule in rules:
        match = rule[kind]
        if rule['family_id'] == row['family_id'] and match['status'] == 'eligible' and all((row['choices'].get(k) in options for k, options in match['allowed_choices'].items())):
            matches.append(rule)
    return (matches[0], None) if len(matches) == 1 else (None, 'ambiguous_reference' if matches else 'no_matching_scope')

def oriented_direction(direction, multiplier):
    if multiplier == 1 or direction == 'zero':
        return direction
    return {'positive': 'negative', 'negative': 'positive'}.get(direction)

def path_record(row, rules, references, alpha):
    record = {'spec_id': row['spec_id'], 'family_id': row['family_id'], 'plot_group': row['plot_group'], 'choices': row['choices'], 'configuration_key': row['configuration_key'], 'execution_status': row['status'], 'own_p_status': row['p_status'], 'own_saved_p': row.get('p_value'), 'own_frozen_alpha': row.get('alpha'), 'direction_reference_index': None, 'significance_reference_index': None, 'direction_agreement': None, 'common_alpha_agreement': None, 'reported_conclusion_agreement': None, 'direction_reason_code': None, 'common_alpha_reason_code': None, 'reported_conclusion_reason_code': None}
    d_rule, d_error = matched_rule(row, rules, 'direction_match')
    s_rule, s_error = matched_rule(row, rules, 'significance_match')
    if d_rule:
        record['direction_reference_index'] = d_rule['reference_index']
    if s_rule:
        record['significance_reference_index'] = s_rule['reference_index']
    if row['status'] != 'success':
        for key in ['direction_reason_code', 'common_alpha_reason_code', 'reported_conclusion_reason_code']:
            record[key] = 'execution_failed'
        return record
    if not d_rule:
        record['direction_reason_code'] = d_error
    else:
        ref = references[d_rule['reference_index']]
        direction = ref.get('author_reported_direction')
        if direction in ['positive', 'negative', 'zero']:
            record['direction_agreement'] = oriented_direction(row['direction'], d_rule['direction_match'].get('row_direction_multiplier', 1)) == direction
        else:
            record['direction_reason_code'] = 'author_direction_missing'
    if not s_rule:
        record['significance_scope_reason_code'] = s_error
        family_refs = [references[r['reference_index']] for r in rules if r['family_id'] == row['family_id']]
        common_available = any((reference_common_decision(ref, alpha)['decision'] is not None for ref in family_refs))
        text_available = any((ref.get('author_significance') in ['significant', 'not_significant'] for ref in family_refs))
        record['common_alpha_reason_code'] = s_error if common_available else 'author_p_missing'
        record['reported_conclusion_reason_code'] = s_error if text_available else 'author_text_missing'
        return record
    ref = references[s_rule['reference_index']]
    common = reference_common_decision(ref, alpha)
    record['author_common_alpha_decision'] = common
    record['author_reported_significance'] = ref.get('author_significance')
    record['method_differences'] = s_rule['significance_match'].get('method_differences', [])
    if row['p_status'] != 'valid' or not finite_p(row.get('p_value')):
        reason = 'own_p_NA' if row['p_status'] == 'NA' else 'own_p_invalid'
        record['common_alpha_reason_code'] = record['reported_conclusion_reason_code'] = reason
        return record
    own_decision = row['p_value'] < alpha
    record['own_decision_at_evaluation_alpha'] = own_decision
    if common['decision'] is not None:
        record['common_alpha_agreement'] = own_decision == common['decision']
    else:
        record['common_alpha_reason_code'] = common['reason_code']
    label = ref.get('author_significance')
    if label in ['significant', 'not_significant']:
        record['reported_conclusion_agreement'] = own_decision == (label == 'significant')
    else:
        record['reported_conclusion_reason_code'] = 'author_text_missing'
    return record

def aggregate(records, key, label, reason_key):
    values = [r[key] for r in records if r[key] is not None]
    reasons = Counter((r.get(reason_key) for r in records if r[key] is None))
    return {'eligible_paths': len(values), 'agreeing_paths': sum(values), 'agreement_fraction': sum(values) / len(values) if values else None, 'metric_label': label, 'excluded_reason_counts': {k: v for k, v in reasons.items() if k}, 'status': 'evaluated' if values else 'unavailable'}

def evaluate_author_conclusions(evaluation, rows, references, rules, alpha=ALPHA):
    if not 0 < alpha < 1:
        raise ValueError('Evaluation alpha must be between zero and one')
    result = copy.deepcopy(evaluation)
    records = [path_record(row, rules, references, alpha) for row in rows]
    by_id = {r['spec_id']: r for r in records}
    changes = []
    for group in result['groups']:
        items = [r for r in rows if r['plot_group'] == group['plot_group']]
        previous = {}
        for mode in ['raw_paths', 'structural_configurations']:
            selected = items
            if mode == 'structural_configurations':
                seen = {}
                for row in items:
                    seen.setdefault(row['configuration_key'], row)
                selected = list(seen.values())
            current = [by_id[r['spec_id']] for r in selected]
            stats = group[mode]
            previous[mode] = {k: copy.deepcopy(stats.get(k)) for k in ['author_direction_comparison', 'author_significance_comparison']}
            direction = aggregate(current, 'direction_agreement', '\u540cH1\u5bf9\u6bd4\u7684\u65b9\u5411\u4e00\u81f4\u7387', 'direction_reason_code')
            common = aggregate(current, 'common_alpha_agreement', '\u7edf\u4e000.05\u663e\u8457\u6027\u4e00\u81f4\u7387', 'common_alpha_reason_code')
            common.update(evaluation_alpha=alpha, metric_kind='common_alpha')
            reported = aggregate(current, 'reported_conclusion_agreement', '\u4f5c\u8005\u62a5\u544a\u7ed3\u8bba\u4e00\u81f4\u7387', 'reported_conclusion_reason_code')
            reported.update(own_evaluation_alpha=alpha, metric_kind='reported_conclusion')
            used = [r for r in current if r['reported_conclusion_agreement'] is not None]
            reported['author_threshold_unknown_paths'] = sum((references[r['significance_reference_index']].get('reported_alpha') is None for r in used))
            reported['not_a_verified_common_threshold_comparison'] = reported['author_threshold_unknown_paths'] > 0
            primary = copy.deepcopy(common if common['eligible_paths'] else reported)
            if not primary['eligible_paths']:
                primary.update(metric_label='\u4f5c\u8005\u663e\u8457\u6027\u4e00\u81f4\u7387（\u6682\u4e0d\u53ef\u8ba1\u7b97）', metric_kind='unavailable')
            elif primary['metric_kind'] == 'reported_conclusion' and reported['author_threshold_unknown_paths']:
                primary['metric_label'] = '\u4f5c\u8005\u62a5\u544a\u7ed3\u8bba\u4e00\u81f4\u7387（\u4f5c\u8005\u9608\u503c\u672a\u6838\u5b9e）'
            primary['selection_policy'] = 'Use common-alpha metric when available; otherwise show explicit author-reported conclusion metric. Never pool these metric bases.'
            stats.update(author_direction_comparison=direction, author_significance_comparison=primary, author_significance_comparison_common_alpha=common, author_reported_conclusion_comparison=reported)
        changes.append({'plot_group': group['plot_group'], 'previous': previous, 'after': {k: group['raw_paths'][k] for k in ['author_direction_comparison', 'author_significance_comparison', 'author_significance_comparison_common_alpha', 'author_reported_conclusion_comparison']}, 'effect_and_p_unchanged': True})
    result['author_evaluation_v16'] = {'evaluation_alpha': alpha, 'scope': 'H1 conclusion agreement on matched outcome/level/time/contrast; no identical-model requirement', 'numeric_and_reported_label_metrics_separate': True, 'author_information_not_returned_to_generator': True}
    return (result, records, changes)
