# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Offline presentation of frozen v7 evidence. Never calls models or statistics."""
import collections, copy, csv, hashlib, json, math, shutil, sys
from pathlib import Path
import blind_five_trial_v7 as b
import lab
HERE = Path(__file__)
DEST = b.PUBLIC

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))

def dump(name, obj):
    p = DEST / name
    p.parent.mkdir(exist_ok=True, parents=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def short(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'), allow_nan=True)

def requests_pack():
    index = []
    values = {}
    for zone, root in [('public_pipeline', b.OUT / 'model_tasks'), ('isolated_target', b.PRIVATE / 'model_tasks')]:
        for stage in sorted(root.iterdir()):
            if not stage.is_dir():
                continue
            zone_file = stage / 'zone.json'
            instruction_file = stage / 'instruction.json'
            z = read(zone_file).get('zone', zone) if zone_file.exists() else read(instruction_file).get('zone', zone) if instruction_file.exists() else zone
            for request in sorted(stage.rglob('request_*.json')):
                raw = read(request)
                encoded = copy.deepcopy(raw)
                for m in encoded.get('messages', []):
                    if not isinstance(m.get('content'), str):
                        continue
                    try:
                        payload = json.loads(m['content'])
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(payload, dict) or 'source_material' not in payload:
                        continue
                    refs = {}
                    for k, v in payload['source_material'].items():
                        h = hashlib.sha256(short(v).encode()).hexdigest()
                        values.setdefault(h, v)
                        refs[k] = h
                    payload['source_material'] = {'__stored_slot_refs': refs}
                    m['content'] = {'__parsed_request_payload': payload}
                target = Path('prompt_archive') / zone / stage.name / request.parent.name / request.name
                path = DEST / target
                path.parent.mkdir(exist_ok=True, parents=True)
                shutil.copy2(request, path)
                adjacent = {}
                for p in request.parent.iterdir():
                    if p.is_file() and p.suffix in ('.json', '.txt') and (p.name != request.name):
                        dst = path.parent / p.name
                        shutil.copy2(p, dst)
                        adjacent[p.name] = dst.relative_to(DEST).as_posix()
                index.append({'stage': stage.name, 'zone': z, 'attempt': request.stem, 'path': target.as_posix(), 'sha256': b.sha(request), 'request': encoded, 'adjacent': adjacent})
    return (index, values)

def activity(specs, results, plan):
    outcomes = {r['spec_id']: r for r in results if r['status'] == 'success'}
    answer = []
    for f in plan['families']:
        family = [s for s in specs if s['group_id'] == f['id']]
        for d in f['dimensions']:
            groups = collections.defaultdict(list)
            for s in family:
                if s['spec_id'] not in outcomes:
                    continue
                key = tuple(((k, v) for k, v in sorted(s['choices'].items()) if k != d['key']))
                groups[key].append(s)
            changed = equal = 0
            for group in groups.values():
                for i, a in enumerate(group):
                    for bb in group[i + 1:]:
                        ea = outcomes[a['spec_id']]['result']['effect_size']
                        eb = outcomes[bb['spec_id']]['result']['effect_size']
                        if math.isclose(ea, eb, rel_tol=0, abs_tol=1e-12):
                            equal += 1
                        else:
                            changed += 1
            answer.append({'family': f['id'], 'decision': d['key'], 'other_choices_fixed_pairs': equal + changed, 'same_point_estimate_pairs': equal, 'different_point_estimate_pairs': changed})
    return answer

def author_markers(specs, results, candidates, audit):
    reviews = {str(x['candidate_id']): x for x in audit.get('candidate_reviews', [])}
    bindings = {str(x['candidate_id']): x for x in audit.get('configuration_bindings', [])}
    outcomes = {r['spec_id']: r for r in results if r['status'] == 'success'}
    markers = []
    for c in candidates.get('candidates', []):
        r = reviews.get(str(c.get('id')), {})
        binding = bindings.get(str(c.get('id')), {})
        cs = binding.get('matching_choice_constraints', {})
        matches = []
        if binding.get('mapping_ready') and cs:
            assert r.get('same_metric_and_units') and r.get('comparable_as_sensitivity_reference'), 'Binding must agree with independent unit/comparability audit'
            for s in specs:
                if s['spec_id'] in outcomes and all((s['choices'].get(k) in vs for k, vs in cs.items())):
                    matches.append(s['spec_id'])
        value = c.get('value')
        aligned = []
        if isinstance(value, (int, float)):
            aligned = [sid for sid in matches if math.isclose(outcomes[sid]['result']['effect_size'], value, rel_tol=1e-09, abs_tol=1e-10)]
        markers.append({'candidate': c, 'audit': r, 'configuration_binding': binding, 'configuration_matching_spec_ids': matches, 'numerically_verified_matching_spec_ids': aligned, 'plot_mode': 'at_verified_configuration' if aligned else 'separate_reference' if r.get('comparable_as_sensitivity_reference') and r.get('same_metric_and_units') else 'not_on_common_axis', 'not_selected_by_nearest_effect': True})
    return markers

def plot(R):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    names = {f.name for f in font_manager.fontManager.ttflist}
    font = next((s for s in ['Microsoft YaHei', 'SimHei', 'Noto Sans CJK SC'] if s in names), 'DejaVu Sans')
    plt.rcParams.update({'font.family': font, 'axes.unicode_minus': False, 'svg.fonttype': 'none', 'font.size': 9})
    good = sorted([r for r in R['results']['results'] if r['status'] == 'success'], key=lambda r: (r['result']['effect_size'], r['spec_id']))
    specs = {s['spec_id']: s for s in R['specs']['specifications']}
    family = R['plan']['families'][0]
    dims = family['dimensions']
    N = len(good)
    fig, (ax, bottom) = plt.subplots(2, 1, figsize=(17, 11), sharex=True, gridspec_kw={'height_ratios': [1, 2.4], 'hspace': 0.05})
    colors = ['#a04961', '#7e67a9', '#429383', '#d09235', '#637c40', '#386b89']
    xs = list(range(1, N + 1))
    for i, r in enumerate(good, 1):
        value = r['result']
        p = value['p_value']
        color = '#1b1b1b' if p is not None and p < 0.05 else '#75b9d8' if p is not None else '#5f7784'
        if value['ci_lower'] is not None:
            ax.vlines(i, value['ci_lower'], value['ci_upper'], color='#a8bbc2', alpha=0.25, lw=0.5)
        ax.scatter(i, value['effect_size'], s=11, c=color, zorder=4)
    ax.axhline(0, color='#596a70', lw=0.8)
    ax.set_ylabel('\u8f83\u665a\u671f − 1970：Gini\u6307\u6570\u70b9')
    ax.set_title(f'\u5355\u4e00\u63cf\u8ff0\u6027\u4e3b\u5f20\u7684\u64cd\u4f5c\u5316\u654f\u611f\u6027\u7a7a\u95f4 · {N}\u6761Specification', loc='left', fontsize=15, pad=18)
    positions = {r['spec_id']: i for i, r in enumerate(good, 1)}
    refs = []
    for m in R['author_markers']:
        hits = m['numerically_verified_matching_spec_ids']
        if hits:
            sid = sorted(hits)[0]
            x = positions[sid]
            v = m['candidate']['value']
            ax.scatter(x, v, s=85, c='black', edgecolors='white', linewidths=0.8, zorder=8)
            c = m['candidate']
            label = str(c['terminal_year']) + '−' + str(c['baseline_year']) if c.get('terminal_year') is not None else '\u4e24\u671f\u5747\u503c−1970'
            ax.annotate(label, xy=(x, v), xytext=(6, 10), textcoords='offset points', fontsize=8, color='black')
            refs.append(m['candidate'].get('id'))
    ax.text(0.01, 0.97, '\u7070\u70b9：P\u503c\u672a\u5b9a\u4e49（NA）；\u7ec6\u7ebf：\u63a2\u7d22\u6027bootstrap\u533a\u95f4\n\u5927\u9ed1\u70b9：\u7ecf\u914d\u7f6e\u53ca\u6570\u503c\u53cc\u91cd\u6838\u9a8c\u7684\u4f5c\u8005\u4ee3\u7801\u6d3e\u751f\u53c2\u7167，\u975e\u8bba\u6587\u76f4\u63a5\u62a5\u544a\u6807\u91cf', transform=ax.transAxes, ha='left', va='top', fontsize=8, bbox={'facecolor': 'white', 'edgecolor': 'none', 'alpha': 0.85})
    labels = []
    ys = []
    row = 0
    for j, d in enumerate(dims):
        row += 1
        bottom.text(-0.01, row, d['question'], ha='right', va='center', transform=bottom.get_yaxis_transform(), fontweight='bold', fontsize=8.5)
        for o in d['options']:
            row += 1
            labels.append(o['label'])
            ys.append(row)
            chosen = [i for i, r in enumerate(good, 1) if specs[r['spec_id']]['choices'][d['key']] == o['id']]
            bottom.scatter(chosen, [row] * len(chosen), s=8, color=colors[j % len(colors)], alpha=0.85)
        bottom.axhline(row + 0.6, color='#e9eef0', lw=0.7)
    bottom.set_yticks(ys, labels)
    bottom.tick_params(axis='y', length=0, labelsize=8.5)
    bottom.set_ylim(row + 1, 0)
    bottom.set_xlim(-2, N + 4)
    bottom.set_xlabel('Specification（\u6309\u6548\u5e94\u503c\u6392\u5e8f；\u4e0a\u4e0b\u56fe\u9010\u5217\u4e00\u4e00\u5bf9\u5e94）')
    bottom.set_xticks(sorted(set([1, N] + list(range(50, N, 50)))))
    for axes in [ax, bottom]:
        axes.spines[['right', 'top']].set_visible(False)
        axes.set_facecolor('white')
    fig.patch.set_facecolor('#f3f7f8')
    fig.subplots_adjust(left=0.32, right=0.98, top=0.93, bottom=0.065)
    for ext in ['png', 'svg']:
        fig.savefig(DEST / ('Specification_Curve.' + ext), dpi=170, facecolor=fig.get_facecolor())
    plt.close(fig)
    dump('\u7ed8\u56fe\u8bf4\u660e.json', {'points': N, 'author_inline_marker_candidates': refs, 'rank_order': [r['spec_id'] for r in good], 'p_values_all_missing': all((r['result']['p_value'] is None for r in good)), 'inferential_claim': False, 'curve_connecting_interpolation': False, 'comparison': 'Broad operationalization sensitivity; summaries, weighting populations and periods differ and must not be pooled as one fixed-parameter estimate.'})

def integrity():
    protected = b.read('protected_before.json')
    changed = [p for p, h in protected.items() if not Path(p).is_file() or b.sha(p) != h]
    assert not changed, 'Protected historical file changed'
    spec_lock = b.read('specification_lock.json')
    result_lock = b.read('blind_results_lock.json')
    code_lock = b.read('blind_code_lock.json')
    for n, k in [('data.csv', 'data_sha256'), ('specification_plan.json', 'plan_sha256'), ('specifications.json', 'specifications_sha256'), ('five_inputs.json', 'five_inputs_sha256')]:
        assert b.sha(b.OUT / n) == spec_lock[k], n
    assert b.sha(b.OUT / 'execution_results_round_0.json') == result_lock['results_sha256']
    assert b.sha(b.OUT / 'analysis_round_0.py') == code_lock['source_sha256']
    attempts = []
    for stage in (b.OUT / 'model_tasks').iterdir():
        if not (stage / 'zone.json').exists():
            continue
        zone = read(stage / 'zone.json')
        if zone['zone'] != 'blind':
            continue
        material = read(stage / 'input.json')
        assert set(material) == set(b.KEYS)
        attempts.append({'stage': stage.name, 'top_level_source_slots': list(material), 'material_sha256': b.sha(stage / 'input.json')})
    guard = b.read('execution_results_round_0.json')
    denied = [{'spec_id': r['spec_id'], 'attempts': r['denied_access_attempts']} for r in guard['results'] if r.get('denied_access_attempts')]
    return {'protected_file_count': len(protected), 'protected_changes': changed, 'frozen_hashes_verified': True, 'blind_stage_source_slot_checks': attempts, 'analysis_denied_access_attempts': denied, 'author_numerics_opened_only_after_blind_result_lock': b.read('author_extraction_receipt.json'), 'limits': ['\u672c\u6838\u9a8c\u8986\u76d6\u8bb0\u5f55\u7684\u6587\u4ef6\u548c\u5b9e\u9645\u8bf7\u6c42，\u4e0d\u8bc1\u660e\u79d1\u7814\u8bed\u4e49\u6b63\u786e。', '\u751f\u6210\u7aef\u53ea\u63a5\u6536\u4e94\u9879\u5916\u90e8\u79d1\u7814\u8d44\u6599\u53ca\u7531\u5b83\u4eec\u4ea7\u751f\u7684\u672c\u8f6e\u8349\u7a3f、\u4ee3\u7801、\u8bca\u65ad；\u6570\u636e\u672c\u8eab、H1\u539f\u53e5\u548c\u5141\u8bb8\u7684\u6548\u5e94\u53e3\u5f84\u4ecd\u53ef\u643a\u5e26\u76ee\u6807\u4fe1\u606f。', '\u672a\u63a5\u6536\u76ee\u6807\u4f5c\u8005\u8d44\u6599\u4e0d\u4fdd\u8bc1\u6a21\u578b\u9884\u8bad\u7ec3\u4e2d\u4ece\u672a\u89c1\u8fc7\u8be5\u8bba\u6587。', 'Python AST/IO\u5ba1\u8ba1\u548c\u8fdb\u7a0b\u73af\u5883\u9694\u79bb\u4e0d\u662f\u64cd\u4f5c\u7cfb\u7edf\u7ea7\u6076\u610f\u4ee3\u7801\u5b89\u5168\u8bc1\u660e。']}

def build():
    assert (b.OUT / 'author_reference_audit.json').exists(), 'Finish isolated author audit before report'
    DEST.mkdir(exist_ok=True, parents=True)
    for p in b.OUT.iterdir():
        if p.is_file() and p.suffix in ['.json', '.jsonl', '.csv', '.py']:
            shutil.copy2(p, DEST / p.name)
    for folder in ['input_packet_revision_0', 'input_packet_revision_1', 'input_packet_revision_2', 'preexecution_freeze_revision_0', 'history_only_cache_ancestors', 'historical_h1_cache_ancestors', 'neo4j_original_integrity']:
        if (b.OUT / folder).exists():
            shutil.copytree(b.OUT / folder, DEST / folder, dirs_exist_ok=True)
    private = b.PRIVATE / 'author_reproduction'
    refdir = DEST / 'isolated_author_reference'
    refdir.mkdir(exist_ok=True)
    for p in private.iterdir():
        if p.is_file():
            shutil.copy2(p, refdir / p.name)
    for p in b.PRIVATE.glob('*.json'):
        shutil.copy2(p, refdir / p.name)
    runtime = b.OUT / 'isolated_execution'
    attempt = b.read('execution_results_round_0.json').get('execution_attempt', 0)
    shutil.copytree(runtime / f'execution_round_{attempt}', DEST / 'official_boba', dirs_exist_ok=True)
    if attempt:
        shutil.copytree(runtime / 'execution_round_0', DEST / 'failed_technical_trial_attempt_0', dirs_exist_ok=True)
    requests, values = requests_pack()
    dump('\u5b9e\u9645Prompt\u76ee\u5f55.json', [{k: v for k, v in r.items() if k != 'request'} for r in requests])
    five = b.read('five_inputs.json')
    plan = b.read('specification_plan.json')
    specs = b.read('specifications.json')
    results = b.read('execution_results_round_0.json')
    route_a = b.read('route_a.json')
    route_a.pop('retrieved_historical_source_catalog', None)
    route_b = b.read('route_b.json')
    route_b.pop('retrieved_historical_source_catalog', None)
    candidates = read(private / 'author_candidates.json')
    audit = b.read('author_reference_audit.json')
    audit['configuration_bindings'] = b.read('author_reference_bindings.json')['bindings']
    good = [r for r in results['results'] if r['status'] == 'success']
    R = {'h1': b.read('h1_public.json'), 'five_inputs': five, 'plan': plan, 'specs': specs, 'results': results, 'route_a': route_a, 'route_b': route_b, 'graph': b.read('full_original_graph.json'), 'catalog': b.read('historical_source_catalog.json'), 'ranking': b.read('fresh_column_ranking.json'), 'preflight': b.read('preflight_audit.json'), 'lineage': b.read('lineage_audit.json'), 'author_candidates': candidates, 'author_reference_audit': audit, 'author_markers': author_markers(specs['specifications'], results['results'], candidates, audit), 'requests': requests, 'stored_values': values, 'events': [json.loads(line) for line in (b.OUT / 'events.jsonl').read_text(encoding='utf-8').splitlines() if line], 'activity': activity(specs['specifications'], results['results'], plan), 'integrity': integrity(), 'summary': {'candidate_combinations': len(b.read('combination_manifest.json')), 'frozen': specs['count'], 'success': results['success'], 'failed': results['failed'], 'unique_effects_12dp': len({round(r['result']['effect_size'], 12) for r in good}), 'p_available': sum((r['result']['p_value'] is not None for r in good)), 'interval_available': sum((r['result']['ci_lower'] is not None for r in good)), 'negative': sum((r['result']['effect_size'] < 0 for r in good)), 'effect_min': min((r['result']['effect_size'] for r in good)), 'effect_max': max((r['result']['effect_size'] for r in good))}, 'history_semantics_receipt': {k: v for k, v in b.read('historical_semantics.json').items() if k != 'rows'}, 'input_revisions': [], 'clarification': b.read('preexecution_inference_clarification.json')}
    R['historical_method_roles'] = b.read('historical_h1_method_roles.json')
    R['option_equivalence_audit'] = b.read('posthoc_option_equivalence_audit.json')
    R['integrity']['original_neo4j_readback'] = b.read('neo4j_original_integrity/\u5bfc\u5165\u6838\u9a8c.json')
    R['integrity']['historical_h1_ancestors'] = b.read('historical_h1_ancestor_verification.json')
    R['integrity']['independent_curve_frozen_before_author'] = b.read('independent_curve_data_lock.json')
    R['integrity']['fresh_author_data_identity'] = read(private / 'data_identity_check.json')
    R['integrity']['author_export_precision_fix'] = read(private / 'precision_export_receipt.json')
    assert b.sha(b.OUT / 'independent_curve_before_author.json') == R['integrity']['independent_curve_frozen_before_author']['sha256']
    expected_order = [r['spec_id'] for r in sorted(good, key=lambda r: (r['result']['effect_size'], r['spec_id']))]
    assert expected_order == [p['spec_id'] for p in b.read('independent_curve_before_author.json')['points']]
    R['integrity']['raw_message_measurement_note'] = 'current_data_conditions\u9010\u5e74\u5b9e\u6d4b\u4e2d，\u5168\u7f3a\u5931\u5b57\u6bb5\u7684min/max\u5728\u90e8\u5206\u539f\u59cb\u8bf7\u6c42\u5185\u5199\u4e3aNaN；\u8fd9\u91cc\u4fdd\u7559\u539f\u6807\u8bb0，\u539f\u59cb\u8bf7\u6c42\u672a\u6539。\u5b9e\u9645\u4e94\u9879\u5305\u7684Data profile\u5bf9\u4e0d\u53ef\u5f97\u8303\u56f4\u4f7f\u7528null，\u7edf\u8ba1\u6548\u5e94\u5fc5\u987b\u6709\u9650。'
    dump('\u8f93\u5165\u6765\u6e90\u6700\u7ec8\u5206\u533a\u8bf4\u660e.json', {'initial_ledger_preserved': 'input_origin_ledger.json', 'initial_target_extraction': 'PDF only', 'later_user_authorized_code_reading': 'Isolated extractor released effect type/units only, no column bindings or author numbers; draft generated independently before this update, then preflight rerun', 'numeric_author_extraction': 'Only after blind_results_lock.json, no target plan/results supplied to candidate extractor', 'generator_external_inputs': b.KEYS, 'derived_materials': 'Only current-trial drafts/code/measured conditions from those inputs', 'guard_scope': 'Recorded file/request/hash checks and Python AST/IO/clean process environment; not a proof of semantic independence or lack of pretrained knowledge'})
    for i in range(3):
        p = b.OUT / f'input_packet_revision_{i}/five_inputs.json'
        if p.exists():
            R['input_revisions'].append({'revision': i, 'effect_scope': read(p)[b.KEYS[4]], 'path': f'input_packet_revision_{i}/five_inputs.json', 'sha256': b.sha(p)})
    dump('\u5b8c\u6574\u6027\u4e0e\u8f93\u5165\u8fb9\u754c\u6838\u9a8c.json', R['integrity'])
    dump('\u7ed3\u679c\u6458\u8981.json', R['summary'])
    dump('Decision\u5b9e\u9645\u6548\u5e94\u53d8\u5316\u6838\u9a8c.json', R['activity'])
    dump('\u4f5c\u8005\u53c2\u7167\u4e0e\u65b9\u6848\u6620\u5c04.json', R['author_markers'])
    with (DEST / '\u5168\u90e8\u6267\u884c\u7ed3\u679c.csv').open('w', encoding='utf-8-sig', newline='') as file:
        fields = ['spec_id', 'status', 'effect_size', 'p_value', 'ci_lower', 'ci_upper', 'n'] + list(specs['specifications'][0]['choices'])
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for r in results['results']:
            writer.writerow({'spec_id': r['spec_id'], 'status': r['status'], **{k: r.get('result', {}).get(k) for k in fields[2:7]}, **r['choices']})
    plot(R)
    html = HERE.with_suffix('.html').read_text(encoding='utf-8').replace('__CSS__', HERE.with_suffix('.css').read_text(encoding='utf-8')).replace('__JS__', HERE.with_suffix('.js').read_text(encoding='utf-8'))
    html = html.replace('__DATA__', short(R).replace('</', '<' + chr(92) + '/'))
    (DEST / 'index.html').write_text(html, encoding='utf-8')
    source = DEST / '\u5f00\u53d1\u4ee3\u7801'
    source.mkdir(exist_ok=True)
    for prefix in ['blind_five_trial_v7', 'blind_five_worker_v7', 'blind_five_audit_v7', 'blind_five_report_v7']:
        for p in HERE.parent.glob(prefix + '.*'):
            shutil.copy2(p, source / p.name)
    shutil.copy2(b.ROOT / 'work/blind_five_display_qa.js', source / 'blind_five_display_qa.js')
    (DEST / '\u9605\u8bfb\u8bf4\u660e.md').write_text(f'# \u5355\u4e00\u4e3b\u5f20\u4e0e\u4e94\u9879\u8f93\u5165\u72ec\u7acb\u8bd5\u9a8c v7\n\n\u6253\u5f00index.html。{specs['count']}\u6761\u51bb\u7ed3\u65b9\u6848，{results['success']}\u6210\u529f、{results['failed']}\u5931\u8d25，{R['summary']['unique_effects_12dp']}\u4e2a\u4e0d\u540c\u70b9\u4f30\u8ba1（12\u4f4d\u5c0f\u6570\u6bd4\u8f83）。\u539f20\u7bc7\u53ca\u8bb0\u5f55\u8303\u56f4\u5185\u65e7\u6587\u4ef6\u4fdd\u6301\u4e0d\u53d8。\n\n\u672c\u8f6e\u91cd\u65b0\u751f\u6210\u76ee\u6807\u5217\u8bed\u4e49、\u6392\u5e8f、A/B，\u4e0d\u6cbf\u7528\u5df2\u53d1\u73b0\u53d7\u76ee\u6807\u4f5c\u8005\u4fe1\u606f\u6c61\u67d3\u7684\u65e7\u76ee\u6807\u884d\u751f\u7269。\u5386\u53f2\u7f13\u5b58\u4ec5\u590d\u7528\u7ecf\u9010\u8bf7\u6c42\u786e\u8ba4\u7eaf\u5386\u53f2\u76846\u6279；\u6df7\u6709\u76ee\u6807\u5185\u5bb9\u7684\u4e00\u6279371\u6761\u5386\u53f2\u8bed\u4e49\u91cd\u65b0\u751f\u6210。\u6570\u636e\u4e3a5174\u884c71\u5217；\u6a21\u578b\u770b\u5230\u5b8c\u6574\u5217\u5143\u4fe1\u606f\u548c12\u884c\u9884\u89c8，\u6267\u884c\u7a0b\u5e8f\u4f7f\u7528\u5168\u8868。\u542b\u4e49\u5747\u4e3a\u57fa\u4e8e\u5217\u540d/\u6570\u503c\u7684\u63a8\u6d4b，\u7f3a\u5c11\u72ec\u7acb\u4ee3\u7801\u672c。\n\n\u72ec\u7acb\u751f\u6210\u7aef\u7684\u5916\u90e8\u79d1\u7814\u8d44\u6599\u4e25\u683c\u4e3aH1、Data、\u5386\u53f2A、\u5386\u53f2B、\u6548\u5e94\u53e3\u5f84\u4e94\u9879；\u672c\u8f6e\u8349\u7a3f/\u4ee3\u7801/\u8bca\u65ad\u653e\u5728\u7b2c\u4e94\u9879\u7684derived_current_trial。\u62a5\u544a\u5c55\u793a\u6bcf\u6b21\u5b9e\u9645\u8bf7\u6c42\u53ca\u6240\u6709\u8f93\u5165\u7248\u672c，\u4e0d\u628a“\u4e94\u4e2a\u9876\u5c42\u952e”\u672c\u8eab\u5f53\u4f5c\u6ca1\u6709\u6cc4\u9732\u7684\u8bc1\u660e。\u516c\u5f00\u6548\u5e94\u53e3\u5f84\u5f97\u5230\u7528\u6237\u6388\u6743；\u5b83\u4ecd\u662f\u76ee\u6807\u77e5\u60c5\u5143\u4fe1\u606f。\u65e9\u671f\u5143\u4fe1\u606f\u8349\u7a3f\u66fe\u8fc7\u5ea6\u6307\u5b9a\u5217\u548c\u62c6\u7ec4\u89c4\u5219，\u672a\u7528\u4e8e\u6700\u7ec8\u65b9\u6848\u751f\u6210，\u4fdd\u7559\u4f9b\u68c0\u67e5。\n\n216\u6761\u8def\u5f84\u4e3a\u4e00\u4e2a\u5e7f\u4e49\u64cd\u4f5c\u5316\u654f\u611f\u6027\u7a7a\u95f4；\u8d22\u5bcc\u6c47\u603b、\u6743\u91cd\u603b\u4f53、\u65f6\u95f4\u7a97、\u6837\u672c\u4e0e\u6781\u7aef\u503c\u5904\u7406\u5404\u6709\u79d1\u5b66\u542b\u4e49。\u5171\u540cGini\u6307\u6570\u70b9\u5355\u4f4d\u4e0d\u610f\u5473\u7740\u5b83\u4eec\u662f\u5b8c\u5168\u76f8\u540c\u7684\u56fa\u5b9aestimand；\u4e0d\u5f97\u6c47\u603b\u6210\u4e00\u4e2a\u5e73\u5747\u4f30\u8ba1\u6216\u4f5c\u6b63\u5f0f\u6574\u4f53\u7a33\u5065\u6027\u58f0\u660e。P\u503c\u5747\u7f3a\u5931，\u7070\u70b9\u8868\u793aNA；\u90e8\u5206\u6709\u63a2\u7d22\u6027bootstrap\u533a\u95f4。\u539f\u8349\u6848\u9057\u6f0f\u91cd\u91c7\u6837\u914d\u5bf9\u89c4\u5219，\u6267\u884c\u524d\u7531DeepSeek\u8865\u8db3、\u53e6\u5b58\u65b0\u51bb\u7ed3\u7248\u672c，\u65e7\u7248\u4fdd\u7559；\u4e0d\u9690\u85cf\u8be5\u53d8\u5316。\n\n\u4f5c\u8005PDF/\u4ee3\u7801\u53ea\u5728\u9694\u79bb\u63d0\u53d6\u7aef\u4f7f\u7528，\u4f5c\u8005\u6570\u503c\u5728\u72ec\u7acb\u65b9\u6848、\u4ee3\u7801\u548c\u7ed3\u679c\u51bb\u7ed3\u540e\u91cd\u65b0\u63d0\u53d6\u53ca\u6267\u884c。\u5019\u9009\u63d0\u53d6\u5668\u672a\u83b7\u5f97\u672c\u8f6e\u65b9\u6848\u6216\u6570\u503c，\u4e0d\u6309\u6700\u63a5\u8fd1\u6548\u5e94\u7b5b\u9009。\u4f5c\u8005\u4ee3\u7801\u5e74\u5ea6\u5e8f\u5217\u4e0e\u672c\u8f6e\u5dee\u503c\u6295\u5f71\u5fc5\u987b\u533a\u5206：\u6d3e\u751f\u53c2\u7167\u4e0d\u80fd\u5192\u5145\u8bba\u6587\u76f4\u63a5\u62a5\u544a\u503c。\u9ed1\u70b9\u53ea\u6709\u914d\u7f6e\u5339\u914d\u4e14\u6570\u503c\u590d\u6838\u4e00\u81f4\u624d\u80fd\u843d\u5728\u66f2\u7ebf\u4e0a，\u5426\u5219\u72ec\u7acb\u5217\u4e3a\u53c2\u7167。\u5b8c\u6574\u4f5c\u8005\u539f\u59cb\u6570\u636e\u4e0a\u6e38\u4f30\u8ba1\u8fc7\u7a0b\u6ca1\u6709\u91cd\u65b0\u6267\u884c。\n\n\u6e90\u7801\u4fdd\u5b58\u5728\u539f\u5de5\u4f5c\u533aoutputs/decision_option_lab\u7684\u56db\u7ec4blind_five_*_v7\u6587\u4ef6；\u62a5\u544a\u5185\u5f00\u53d1\u4ee3\u7801\u7528\u4e8e\u67e5\u770b。\u79bb\u7ebf\u91cd\u5efa\u5c55\u793a：\u5728\u539f\u5de5\u4f5c\u533a\u8fd0\u884cwork/spec_runtime/Scripts/python.exe outputs/decision_option_lab/blind_five_report_v7.py，\u4e0d\u8c03\u7528API、\u4e0d\u91cd\u8dd1\u7edf\u8ba1。\u539f20\u7bc7\u672a\u8986\u76d6，\u672c\u8f6e\u672a\u4e0a\u4f20Gitee。\n', encoding='utf-8')
    dump('\u6587\u4ef6\u6e05\u5355.json', [{'path': p.relative_to(DEST).as_posix(), 'bytes': p.stat().st_size, 'sha256': b.sha(p)} for p in sorted(DEST.rglob('*')) if p.is_file() and p.name != '\u6587\u4ef6\u6e05\u5355.json'])
    print('REPORT', DEST / 'index.html', R['summary'], flush=True)
if __name__ == '__main__':
    build()
