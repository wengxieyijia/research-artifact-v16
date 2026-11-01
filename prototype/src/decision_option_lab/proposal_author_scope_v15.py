# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Post-freeze author-scope audit. No generated estimates or P values enter the prompt."""
import argparse, copy, json, math
from pathlib import Path
import lab, model_runner
from auto_trial_v8 import read, save, sha, now
INSTRUCTION = '\u4f60\u8d1f\u8d23\u72ec\u7acb\u7ed3\u679c\u51bb\u7ed3\u4e4b\u540e\u7684\u8bc4\u4ef7\u53e3\u5f84\u6838\u67e5，\u4e0d\u751f\u6210\u5206\u6790、\u4e0d\u4fee\u6539\u65b9\u6848。\u53ea\u636e\u63d0\u4f9b\u7684\u51bb\u7ed3H1/\u65b9\u6848/\u4f5c\u8005\u53c2\u7167\u51b3\u5b9a\u9010\u8def\u5f84\u662f\u5426\u53ef\u6bd4\u8f83\u65b9\u5411、\u663e\u8457\u6027。\u6ca1\u6709\u63d0\u4f9b\u672c\u8f6e\u6548\u5e94\u6570\u503c、P\u503c\u6216\u663e\u8457\u6bd4\u4f8b，\u7981\u6b62\u4f9d\u7ed3\u679c\u6311\u53ef\u6bd4\u8f83\u5b50\u96c6。\n\u4f5c\u8005\u539f\u6587\u540c\u4e00\u4e2a\u7814\u7a76\u4e3b\u5f20\u4e0b\u7684\u5408\u7406\u6837\u672c、\u6e05\u6d17、\u534f\u53d8\u91cf\u9009\u62e9\u53ef\u4f5c\u4e3a\u654f\u611f\u6027\u6bd4\u8f83，\u4f46\u4e0d\u540c\u7ed3\u5c40\u5b9a\u4e49（\u4f8b\u5982FTE\u548cheadcount）、\u4e0d\u540c\u5206\u6790\u5c42\u7ea7、\u4e0d\u540c\u6784\u5ff5/\u6d4b\u91cf\u5e74\u4efd\u4e0d\u80fd\u4ec5\u56e0family_id\u76f8\u540c\u5c31\u81ea\u52a8\u5339\u914d。Pearson\u76f8\u5173\u4e0e\u8c03\u6574\u56de\u5f52、\u5bb6\u5ead\u5747\u503c\u4e0e\u540c\u80de\u5dee\u503c\u7b49\u987b\u8ba4\u771f\u533a\u5206，\u4e0d\u80fd\u81ea\u52a8\u4e92\u7528。\u7ed9\u51fa\u65b9\u5411\u4e0e\u663e\u8457\u6027\u5404\u81ea\u79d1\u5b66\u5339\u914d\u8303\u56f4；\u4ec5\u5b9a\u6027\u7684H1\u540c\u5411\u4ecd\u53ef\u5728\u53d9\u8ff0\u4e2d\u62a5\u544a，\u4e0d\u80fd\u5192\u5145\u53ef\u6838\u5b9e\u7684\u9010\u8def\u5f84\u4e00\u81f4\u7387。\n\u6bcf\u4e2a\u539f\u4f5c\u8005reference\u6070\u597d\u4e00\u4e2arule；allowed_choices\u4e3a\u51bb\u7ed3Decision\u952e\u5230\u5141\u8bb8Option ID\u6570\u7ec4，\u6240\u6709\u6761\u4ef6\u4e3aAND，\u672a\u5217\u51fa\u7684Decision\u53ef\u53d8\u5316；\u7a7a\u5b57\u5178\u8868\u793a\u6574\u4e2aFamily\u9002\u7528，\u53ea\u6709\u8bc1\u636e\u652f\u6301\u624d\u5141\u8bb8。status=eligible/not_comparable/unknown。\u65e0\u6cd5\u786e\u5b9a\u5fc5\u987bunknown。\u663e\u8457\u6027\u8fd8\u8981\u6c42\u4f5c\u8005\u660e\u786e\u62a5\u544a\u7684alpha\u4e0e\u8def\u5f84\u51bb\u7ed3alpha\u76f8\u540c；reported_alpha\u4e3anull\u65f6\u4e0d\u5f97\u64c5\u81ea\u8865\u6210.05。\u4e0d\u8981\u81ea\u884c\u6539\u4f5c\u8005\u53c2\u7167、\u65b9\u6848\u548c\u539fP\u503c。\u8f93\u51fa\u7b80\u6d01\u4e2d\u6587\u539f\u56e0\u7684\u5b8c\u6574JSON。'

def audit(batch_path):
    batch = read(batch_path)
    material = []
    lookup = {}
    for item in batch['papers']:
        cfg = read(item['manifest'])
        out = Path(cfg['output'])
        if out.name not in ['03_minwage', '05_nlsy_linked']:
            continue
        lock = read(out / 'blind_results_lock.json')
        assert sha(out / 'execution_results_round_0.json') == lock['results_sha256']
        plan = read(out / 'specification_plan.json')
        refs = read(out / 'author_reference.json')['references']
        lookup[cfg['run_id']] = (out, plan, refs, lock)
        material.append({'run_id': cfg['run_id'], 'h1': read(out / 'h1_public.json'), 'frozen_families': plan['families'], 'author_references': [{'reference_index': i, **r} for i, r in enumerate(refs)]})

    def valid(obj):
        errors = []
        papers = obj.get('papers', [])
        if {p.get('run_id') for p in papers} != set(lookup):
            return ['Exactly the supplied run IDs required']
        for paper in papers:
            out, plan, refs, lock = lookup[paper['run_id']]
            rules = paper.get('reference_rules', [])
            if len(rules) != len(refs) or {r.get('reference_index') for r in rules} != set(range(len(refs))):
                errors.append('Every reference index required exactly once')
                continue
            families = {f['id']: f for f in plan['families']}
            for rule in rules:
                ref = refs[rule['reference_index']]
                if rule.get('family_id') != ref['family_id']:
                    errors.append('Family mismatch')
                    continue
                dims = {d['key']: {o['id'] for o in d['options']} for d in families[ref['family_id']]['dimensions']}
                for kind in ['direction_match', 'significance_match']:
                    match = rule.get(kind, {})
                    if match.get('status') not in ['eligible', 'not_comparable', 'unknown'] or not isinstance(match.get('reason'), str):
                        errors.append('Invalid scope status/reason')
                    allowed = match.get('allowed_choices')
                    if not isinstance(allowed, dict):
                        errors.append('allowed_choices object required')
                        continue
                    if any((k not in dims or not isinstance(v, list) or (not v) or (not set(v) <= dims.get(k, set())) for k, v in allowed.items())):
                        errors.append('Only frozen choice IDs allowed')
                    if kind == 'significance_match' and match.get('status') == 'eligible' and (ref.get('reported_alpha') is None):
                        errors.append('Do not infer author alpha')
        return errors
    contract = {'papers': [{'run_id': 'supplied ID', 'reference_rules': [{'reference_index': 0, 'family_id': 'supplied family', 'direction_match': {'status': 'eligible/not_comparable/unknown', 'allowed_choices': {}, 'reason': 'scope evidence'}, 'significance_match': {'status': 'eligible/not_comparable/unknown', 'allowed_choices': {}, 'reason': 'scope evidence'}}]}]}
    folder = Path(batch_path).parent / 'after_freeze_author_scope_v15'
    folder.mkdir(parents=True, exist_ok=True)
    result = model_runner.run_json('post_freeze_author_scope_v15', INSTRUCTION, {'zone': 'post_freeze_evaluation_only', 'scientific_generation': False, 'current_effects_or_p_supplied': False}, contract, {'papers': material}, lab.read(Path(__file__).with_name('config_high.json')), folder, valid)
    for paper in result['papers']:
        out, plan, refs, lock = lookup[paper['run_id']]
        save(out / 'author_scope_rules_v15.json', {'utc': now(), 'rules': paper['reference_rules'], 'results_sha256': lock['results_sha256'], 'author_reference_sha256': sha(out / 'author_reference.json'), 'no_current_effect_or_p_supplied_to_scope_auditor': True, 'changes_to_frozen_scientific_artifacts': False})
        print('Author scope audit saved', out.name, flush=True)

def apply_rules(evaluation, rows, author, audit):
    result = copy.deepcopy(evaluation)
    refs = author['references']
    records = []
    for group in result['groups']:
        relevant = [r for r in rows if r['plot_group'] == group['plot_group']]
        families = {r['family_id'] for r in relevant}
        if not any((rule['family_id'] in families for rule in audit['rules'])):
            continue

        def selected(row, kind):
            candidates = []
            for rule in audit['rules']:
                m = rule[kind]
                if rule['family_id'] == row['family_id'] and m['status'] == 'eligible' and all((row['choices'].get(k) in v for k, v in m['allowed_choices'].items())):
                    candidates.append(refs[rule['reference_index']])
            return candidates[0] if len(candidates) == 1 else None
        previous = {}
        for mode in ['raw_paths', 'structural_configurations']:
            items = relevant if mode == 'raw_paths' else list({r['configuration_key']: r for r in relevant}.values())
            direction = []
            significance = []
            for row in items:
                if row['status'] != 'success':
                    continue
                ref = selected(row, 'direction_match')
                if ref and ref.get('author_reported_direction') in ['positive', 'negative', 'zero']:
                    direction.append(row['direction'] == ref['author_reported_direction'])
                ref = selected(row, 'significance_match')
                if ref and row['p_status'] == 'valid' and (ref.get('author_significance') in ['significant', 'not_significant']) and (ref.get('reported_alpha') is not None) and math.isclose(ref['reported_alpha'], row['alpha'], abs_tol=1e-12, rel_tol=0):
                    significance.append(row['significant'] == (ref['author_significance'] == 'significant'))
            stats = group[mode]
            previous[mode] = {k: stats[k] for k in ['author_direction_comparison', 'author_significance_comparison']}
            for key, values in [('author_direction_comparison', direction), ('author_significance_comparison', significance)]:
                stats[key] = {'eligible_paths': len(values), 'agreement_fraction': sum(values) / len(values) if values else None, 'status': 'post_freeze_scope_checked' if values else 'scope_matching_pending', 'reason': 'Matched only through saved independent scope rules; qualitative same-direction statements are not exact-scope agreement.'}
        records.append({'plot_group': group['plot_group'], 'superseded_legacy_comparisons': previous, 'own_effects_p_and_counts_changed': False})
    return (result, records)
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--batch', required=True)
    a = p.parse_args()
    audit(a.batch)
