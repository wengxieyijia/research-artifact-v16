# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Small offline checkpoint report. No API and no statistical execution."""
import csv, html, json, math, re, shutil, textwrap
from collections import Counter
from pathlib import Path

def load(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def e(v):
    return html.escape(str(v), quote=True)

def pretty(v):
    return json.dumps(v, ensure_ascii=False, indent=2)

def english(value, fallback):
    return value if isinstance(value, str) and (not re.search('[\u3400-\u9fff]', value)) else fallback

def result_summary(state, plan, evaluation, rows, execution, specifications, author):
    """Describe saved receipts only; never estimate an effect or infer a missing P."""
    records = {r['spec_id']: r for r in execution.get('results', [])}
    references = {r['family_id']: r for r in author.get('references', [])}
    groups = []
    for group in evaluation.get('groups', []):
        selected = [r for r in rows if r['plot_group'] == group['plot_group']]
        families = sorted({r['family_id'] for r in selected})
        conditional = [r for r in selected if r.get('p_status') == 'valid' and r.get('inference_kind', r.get('frozen_inference_policy')) == 'conditional_formal_test']
        year_counts = set()
        for row in conditional:
            diagnostics = records.get(row['spec_id'], {}).get('result', {}).get('diagnostics', {})
            n_years = diagnostics.get('n_years_used_in_contrast')
            if isinstance(n_years, (int, float)) and (not isinstance(n_years, bool)) and math.isfinite(n_years):
                year_counts.add(n_years)
        definitions = [f for f in plan.get('families', []) if f['id'] in families]
        inference_limits = list(dict.fromkeys((str(note) for f in definitions for note in f.get('output_contract', {}).get('inference', {}).get('limitations', []))))
        raw_signs = Counter()
        for row in selected:
            value = row.get('effect_size')
            null = row.get('null_value', group.get('null_value'))
            if row.get('status') != 'success' or isinstance(value, bool) or (not isinstance(value, (int, float))) or (not math.isfinite(value)) or (not isinstance(null, (int, float))):
                continue
            raw_signs['positive' if value > null else 'negative' if value < null else 'zero'] += 1
        multipliers = sorted({r['direction_multiplier'] for r in selected if r.get('direction_multiplier') in (-1, 1)})
        if not multipliers:
            multipliers = sorted({f.get('comparison_definition', {}).get('evaluation', {}).get('direction_multiplier') for f in definitions if f.get('comparison_definition', {}).get('evaluation', {}).get('direction_multiplier') in (-1, 1)})
        positive_meanings = list(dict.fromkeys((f.get('comparison_definition', {}).get('evaluation', {}).get('positive_meaning', '\u672a\u586b\u5199') for f in definitions)))
        groups.append({'plot_group': group['plot_group'], 'title': group['title'], 'unit': group['unit'], 'stats': group['raw_paths'], 'direction_encoding': {'formula': '(raw effect - null_value) * direction_multiplier', 'null_value': group.get('null_value'), 'direction_multipliers': multipliers, 'positive_meanings': positive_meanings}, 'raw_effect_sign_counts': {'positive': raw_signs['positive'], 'negative': raw_signs['negative'], 'zero': raw_signs['zero'], 'denominator': sum(raw_signs.values()), 'meaning': 'Raw curve effect relative to its null, before the frozen direction multiplier; not an H1 support classification.'}, 'conditional_test_count': len(conditional), 'conditional_test_observed_year_counts': sorted(year_counts), 'test_alphas': sorted({r['alpha'] for r in selected if r.get('p_status') == 'valid' and isinstance(r.get('alpha'), (float, int))}), 'author_reported_directions': sorted({references[f]['author_reported_direction'] for f in families if f in references}), 'author_reported_significance': sorted({references[f]['author_significance'] for f in families if f in references}), 'inference_limitations': inference_limits})
    return {'run_status': state.get('status', 'pending'), 'frozen_paths': specifications.get('count'), 'executed_paths': execution.get('count', len(records)), 'successful_paths': execution.get('success', sum((r.get('status') == 'success' for r in records.values()))), 'failed_paths': execution.get('failed', sum((r.get('status') != 'success' for r in records.values()))), 'curve_groups': sum((g['stats']['successful_effects'] > 0 for g in groups)), 'comparison_groups': len(groups), 'groups': groups, 'comparison_policy': 'Each group retains its own direction/significance denominator; no pooling of different questions, effect units or papers.'}

def reuse_inventory(plan):
    inventory = []
    for family in plan['families']:
        categories = {'decisions': family['dimensions'], 'options': [o for d in family['dimensions'] for o in d['options']], 'common_and_fixed_steps': family.get('common_steps', []) + family.get('fixed_steps', [])}
        for kind, items in categories.items():
            configs = Counter((i.get('origin', 'unspecified') for i in items))
            methods = Counter((i.get('method_origin', 'unspecified') for i in items))
            inventory.append({'family_id': family['id'], 'kind': kind, 'count': len(items), 'configuration_origin': dict(Counter((i.get('origin', 'unspecified') for i in items))), 'method_origin': dict(Counter((i.get('method_origin', 'unspecified') for i in items))), 'strict_configuration_reuse_fraction': configs['reused'] / len(items) if items else None, 'configuration_reused_or_adapted_fraction': (configs['reused'] + configs['adapted']) / len(items) if items else None, 'method_core_reused_or_adapted_fraction': (methods['reused'] + methods['adapted']) / len(items) if items and methods['unspecified'] == 0 else None, 'method_refs': sorted({m for i in items for m in i.get('method_refs', [])})})
    return {'inventory': inventory, 'counting_unit': 'Each frozen family Decision/Option/common-or-fixed-step once; not multiplied by path frequency. Labels are DeepSeek provenance claims, not independent semantic verification.'}

def refresh_state(dest, state):
    dest = Path(dest)
    p = dest / 'index.html'
    text = p.read_text(encoding='utf-8')
    start = text.index('const R=') + len('const R=')
    data, end = json.JSONDecoder().raw_decode(text[start:])
    data['state'] = state
    if 'summary' in data:
        data['summary']['run_status'] = state.get('status', 'pending')
        (dest / 'summary.json').write_text(pretty(data['summary']), encoding='utf-8')
    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('</', '<' + chr(92) + '/')
    p.write_text(text[:start] + encoded + text[start + end:], encoding='utf-8')
    (dest / 'run_state.json').write_text(pretty(state), encoding='utf-8')

def draw_curves(out, dest, plan, rows, evaluation):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    names = {f.name for f in font_manager.fontManager.ttflist}
    font = next((f for f in ['Arial', 'DejaVu Sans'] if f in names))
    plt.rcParams.update({'font.family': font, 'svg.fonttype': 'none', 'axes.unicode_minus': False, 'font.size': 9})
    specs = {s['spec_id']: s for s in load(out / 'specifications.json', {'specifications': []})['specifications']}
    overlay = load(out / 'display_labels_en.json', {})
    overlay = overlay.get('labels', overlay)
    if not isinstance(overlay, dict):
        raise ValueError('English display labels must be a key-to-text mapping')
    colors = ['#a04961', '#7e67a9', '#429383', '#d09235', '#637c40', '#386b89', '#7a6a57']
    figures = []
    for index, g in enumerate(evaluation.get('groups', []), 1):
        good = sorted([r for r in rows if r['plot_group'] == g['plot_group'] and r['status'] == 'success'], key=lambda r: (r['effect_size'], r['spec_id']))
        if not good:
            continue
        N = len(good)
        dimensions = []
        seen = {}
        for r in good:
            s = specs[r['spec_id']]
            for key, o in s['selected_options'].items():
                identity = (s['group_id'], key)
                if identity not in seen:
                    seen[identity] = {'key': key, 'family_id': s['group_id'], 'options': {}}
                    dimensions.append(seen[identity])
                seen[identity]['options'][o['id']] = o
        total_rows = sum((len(d['options']) + 1 for d in dimensions))
        fig, (top, bottom) = plt.subplots(2, 1, figsize=(16, max(8, 4 + total_rows * 0.26)), sharex=True, gridspec_kw={'height_ratios': [1, max(1.5, total_rows * 0.12)], 'hspace': 0.08})
        for i, r in enumerate(good, 1):
            color = '#151515' if r['p_status'] == 'valid' and r['significant'] else '#73b6d4' if r['p_status'] == 'valid' else '#738590'
            if r['ci_lower'] is not None and r['ci_upper'] is not None:
                top.vlines(i, r['ci_lower'], r['ci_upper'], color='#c0cdd3', lw=0.6, alpha=0.6)
            top.scatter(i, r['effect_size'], s=14, color=color, zorder=3)
        top.axhline(g['null_value'], color='#6c7e87', lw=0.9)
        top.set_title(english(g['title'], g['plot_group']) + f' | {N} specifications', loc='left', fontsize=15, pad=18)
        top.set_ylabel(english(g['unit'], 'Effect'))
        multiplier = good[0].get('direction_multiplier', 1)
        top.text(0.01, 0.98, 'Black: valid P < alpha   Blue: valid P >= alpha   Gray: P unavailable/invalid\n' + f'Y axis: raw effect. Encoded direction = (effect - null) x {multiplier}.\n' + 'Intervals follow each frozen inference contract; no author-value matching.', transform=top.transAxes, va='top', fontsize=8, bbox={'facecolor': 'white', 'edgecolor': 'none', 'alpha': 0.85})
        row = 0
        ys = []
        labels = []
        for j, d in enumerate(dimensions):
            row += 1
            label = next((x['question'] for f in plan['families'] if f['id'] == d['family_id'] for x in f['dimensions'] if x['key'] == d['key']), d['key'])
            display_key = d['family_id'] + ':' + d['key']
            label = overlay.get(display_key, label)
            if len({x['family_id'] for x in dimensions}) > 1:
                label = d['family_id'] + ': ' + english(label, d['key'].replace('_', ' ').title())
            bottom.text(-0.012, row, textwrap.fill(english(label, d['key'].replace('_', ' ').title()), width=65), ha='right', va='center', transform=bottom.get_yaxis_transform(), fontweight='bold', fontsize=8.5)
            for oid, o in d['options'].items():
                row += 1
                ys.append(row)
                labels.append(textwrap.fill(english(overlay.get(display_key + ':' + oid, o.get('label')), oid), width=67))
                xs = [i for i, r in enumerate(good, 1) if specs[r['spec_id']]['group_id'] == d['family_id'] and specs[r['spec_id']]['choices'].get(d['key']) == oid]
                bottom.scatter(xs, [row] * len(xs), s=10, color=colors[j % len(colors)])
            bottom.axhline(row + 0.6, color='#edf1f3', lw=0.7)
        bottom.set_yticks(ys, labels)
        bottom.tick_params(axis='y', length=0, labelsize=8.5)
        bottom.set_ylim(row + 1, 0)
        bottom.set_xlim(0, N + 2)
        ticks = sorted({1, N, *[x for x in range(25, N, 25) if N - x >= 8]}) if N > 25 else sorted({1, N})
        bottom.set_xticks(ticks)
        bottom.set_xlabel('Specification (sorted by effect; columns aligned across panels)')
        for ax in [top, bottom]:
            ax.spines[['right', 'top']].set_visible(False)
        fig.patch.set_facecolor('#f3f7f8')
        fig.subplots_adjust(left=0.34, right=0.98, top=0.93, bottom=0.065)
        stem = 'curve_' + str(index)
        for ext in ['png', 'svg']:
            fig.savefig(dest / (stem + '.' + ext), dpi=170, facecolor=fig.get_facecolor(), bbox_inches='tight', pad_inches=0.18)
        plt.close(fig)
        figures.append({'plot_group': g['plot_group'], 'title': g['title'], 'png': stem + '.png', 'svg': stem + '.svg', 'spec_order': [r['spec_id'] for r in good]})
    return figures

def build_report(out, dest, private, partial=False):
    out = Path(out)
    dest = Path(dest)
    private = Path(private)
    dest.mkdir(exist_ok=True, parents=True)
    version = load(out / 'run_state.json', {}).get('version', '')
    guide = Path(__file__).with_name('README_AUTO_V9.md' if 'v9' in version.lower() else 'README_AUTO_V8.md')
    if not guide.exists():
        guide = Path(__file__).with_name('README_AUTO_V8.md')
    shutil.copy2(guide, dest / '\u81ea\u52a8\u5316\u4f7f\u7528\u8bf4\u660e.md')
    for p in out.iterdir():
        if p.is_file() and p.suffix.lower() in ['.json', '.jsonl', '.csv', '.py']:
            shutil.copy2(p, dest / p.name)
    plan = load(out / 'specification_plan.json', {'families': []})
    rows = load(out / 'evaluated_paths.json', [])
    evaluation = load(out / 'evaluation.json', {'groups': []})
    reuse = reuse_inventory(plan)
    (dest / 'reuse_statistics.json').write_text(pretty(reuse), encoding='utf-8')
    state = load(out / 'run_state.json', {})
    h1 = load(out / 'h1_public.json', {})
    ra = load(out / 'route_a.json', {})
    rb = load(out / 'route_b.json', {})
    author = load(out / 'author_reference.json', {})
    summary = result_summary(state, plan, evaluation, rows, load(out / 'execution_results_round_0.json', {}), load(out / 'specifications.json', {}), author)
    (dest / 'summary.json').write_text(pretty(summary), encoding='utf-8')
    figures = draw_curves(out, dest, plan, rows, evaluation) if rows else []
    prompts = []
    for label, root in [('pipeline', out / 'model_tasks'), ('isolated_extractor', private / 'model_tasks')]:
        if not root.exists():
            continue
        for request in sorted(root.rglob('request_*.json')):
            relative = Path('prompts') / label / request.relative_to(root)
            target = dest / relative
            target.parent.mkdir(exist_ok=True, parents=True)
            shutil.copy2(request, target)
            for source in request.parent.glob('response_*.json'):
                shutil.copy2(source, target.parent / source.name)
            stage = request.relative_to(root).parts[0]
            instruction = root / stage / 'instruction.json'
            zone = load(instruction, {}).get('zone', label)
            prompts.append({'stage': stage, 'zone': zone, 'path': relative.as_posix(), 'attempt': request.name})
    packet = load(out / 'five_inputs.json', {})
    for key, value in packet.items():
        (dest / (key + '.json')).write_text(pretty(value), encoding='utf-8')
    events = [json.loads(line) for line in (out / 'orchestration.jsonl').read_text(encoding='utf-8').splitlines()] if (out / 'orchestration.jsonl').exists() else []
    coverage_review = load(out / 'option_coverage_review.json', {})
    amendments = []
    for folder in sorted(out.glob('preexecution_amendment_*')):
        if not folder.is_dir():
            continue
        record = {'name': folder.name, 'receipt': load(folder / 'receipt.json'), 'archive_manifest': load(folder / 'archive_manifest.json'), 'files': []}
        for name in ['receipt.json', 'archive_manifest.json']:
            source = folder / name
            if source.exists():
                relative = Path(folder.name) / name
                (dest / relative).parent.mkdir(exist_ok=True, parents=True)
                shutil.copy2(source, dest / relative)
                record['files'].append(relative.as_posix())
        amendments.append(record)
    data = {'state': state, 'events': [r for r in events if r.get('event') in ['stage_blocked', 'model_transport_retry', 'automatic_runtime_repair']], 'h1': h1, 'effect_scope': load(out / 'effect_scope_public.json', {}), 'data_profile': load(out / 'data_structure_profile.json', {}), 'route_a': {k: v for k, v in ra.items() if k != 'retrieved_historical_source_catalog'}, 'route_b': {'matches': [{'h1_hit': m['h1_hit'], 'methods': [{k: v for k, v in r.items() if k in ['decision_ref', 'option_ref', 'component_ref', 'method_id', 'method_name', 'kind']} for r in m['historical_methods']]} for m in rb.get('matches', [])], 'association_limit': rb.get('association_limit')}, 'graph': load(out / 'full_original_graph.json', {'nodes': [], 'edges': []}), 'evaluation': evaluation, 'summary': summary, 'navigation': load(dest / 'paper_navigation.json', []), 'density': load(out / 'option_coverage_receipt.json'), 'density_review': coverage_review.get('expansion_review'), 'display_labels_en': load(out / 'display_labels_en.json'), 'preexecution_amendments': amendments, 'rows': rows, 'figures': figures, 'author': author, 'boundary': load(out / 'request_boundary_ledger.jsonl', None) if False else None, 'prompts': prompts, 'allowed_inputs': packet, 'reuse': reuse, 'science_limits': [{'family_id': f['id'], 'comparison_definition': f['comparison_definition'], 'inference': f.get('output_contract', {}).get('inference'), 'limitations': f.get('inference_limitations', [])} for f in plan['families']], 'policy': load(out / 'evaluation_policy.json', {}), 'run_id': state.get('run_id'), 'partial': partial}
    serialized = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('</', '<' + chr(92) + '/')
    here = Path(__file__)
    template = here.with_suffix('.html').read_text(encoding='utf-8')
    page = template.replace('__DATA__', serialized)
    if partial:

        def missing_link(match):
            path = match.group(1)
            if not path.startswith(('#', 'http:', 'https:')) and (not (dest / path).exists()):
                return '<span class="small">' + match.group(2) + '（\u5c1a\u672a\u751f\u6210）</span>'
            return match.group(0)
        page = re.sub('<a href="([^"]+)">([^<]+)</a>', missing_link, page)
    (dest / 'index.html').write_text(page, encoding='utf-8')
    with (dest / 'evaluated_paths.csv').open('w', encoding='utf-8-sig', newline='') as f:
        fields = ['spec_id', 'family_id', 'plot_group', 'status', 'effect_size', 'direction', 'p_value', 'p_status', 'significant', 'alpha', 'reason']
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    (dest / 'README.md').write_text('# \u81ea\u52a8\u6d41\u7a0b\u68c0\u67e5\u70b9\u62a5\u544a\n\n\u4e00\u6b21\u5165\u53e3\u81ea\u52a8\u987a\u5e8f\u8c03\u5ea6\u5404\u9636\u6bb5；\u539f20\u7bc7\u4e0d\u53d8。Checkpoint\u8868\u533a\u5206\u672c\u6b21\u5b8c\u6210、\u7f13\u5b58\u91cd\u7528\u53ca\u963b\u65ad。\n\u751f\u6210\u7aef\u4ec5\u6709\u4e94\u9879\u5916\u90e8\u79d1\u7814\u8f93\u5165；\u4f5c\u8005\u8bba\u6587/\u4ee3\u7801\u53ea\u5728\u9694\u79bb\u63d0\u53d6\u533a\u5904\u7406。\u4f5c\u8005\u89c2\u6d4b\u65b9\u5411\u548c\u663e\u8457\u6027\u5728\u72ec\u7acb\u7ed3\u679c\u51bb\u7ed3\u540e\u624d\u6253\u5f00，\u4f5c\u8005\u63d0\u53d6\u5668\u672a\u6536\u5230\u72ec\u7acb\u6548\u5e94\u6216P\u503c。\u6570\u636e\u672c\u8eab\u53ca\u83b7\u51c6\u7684H1/\u6548\u5e94\u53e3\u5f84\u4ecd\u662f\u76ee\u6807\u4fe1\u606f，\u4e0d\u80fd\u58f0\u79f0\u6ca1\u6709\u9884\u8bad\u7ec3\u8bb0\u5fc6\u6216\u4fe1\u606f\u8bba\u610f\u4e49\u7684\u5b8c\u5168\u72ec\u7acb。\n\u79d1\u5b66\u5224\u65ad\u548c\u7edf\u8ba1\u6e90\u7801\u7531DeepSeek\u751f\u6210；\u5f00\u53d1\u8005\u8d1f\u8d23\u8f93\u5165\u9002\u914d、\u673a\u68b0\u6821\u9a8c、\u8c03\u5ea6、\u6267\u884c\u4e0e\u8bc4\u4ef7。Python AST/\u6587\u4ef6\u4e0e\u7f51\u7edc\u5ba1\u8ba1\u4e0d\u662f\u64cd\u4f5c\u7cfb\u7edf\u7ea7\u6076\u610f\u539f\u751f\u4ee3\u7801\u5b89\u5168\u8bc1\u660e。\n\u66f2\u7ebf\u6309\u4e8b\u5148\u51bb\u7ed3\u7684\u5171\u540c\u7814\u7a76\u95ee\u9898\u5206\u7ec4；\u65f6\u95f4、\u6837\u672c、\u6743\u91cd、\u4f30\u8ba1/\u63a8\u65ad\u65b9\u6cd5\u7b49\u5408\u7406\u9009\u9879\u7559\u5728\u7ec4\u5185。\u4e0d\u540c\u4f30\u8ba1\u5bf9\u8c61\u7684\u64cd\u4f5c\u5316\u5dee\u5f02\u4ecd\u9700\u6309\u6807\u7b7e\u89e3\u8bfb，\u4e0d\u5408\u6210\u4e00\u4e2a\u5e73\u5747\u6548\u5e94。\nP\u7f3a\u5931\u6216\u65e0\u6548\u6392\u9664\u51fa\u663e\u8457\u6bd4\u4f8b\u5206\u6bcd，\u4e0d\u80fd\u7b97\u4e0d\u663e\u8457。\u63a2\u7d22\u6027\u533a\u95f4\u4e0d\u81ea\u52a8\u6210\u4e3aP\u68c0\u9a8c。\u65b9\u5411\u4ee5\u5404\u81ea\u96f6\u6548\u5e94\u57fa\u51c6\u53ca\u7f16\u7801\u65b9\u5411\u5224\u65ad。\u62a5\u544a\u6bd4\u4f8b\u63cf\u8ff0\u5206\u6790\u9009\u62e9\u654f\u611f\u6027，\u4e0d\u662f\u72ec\u7acb\u8bc1\u636e\u6570\u91cf\u6216\u5047\u8bbe\u6210\u7acb\u6982\u7387。\u6570\u503c\u76f8\u540c\u7684\u70b9\u4e0d\u81ea\u52a8\u5f53\u7b49\u4ef7\u914d\u7f6e。\n\u672c\u8f6e\u4e0d\u4ee5\u4e0e\u4f5c\u8005\u6548\u5e94\u6570\u503c\u4e00\u81f4\u4e3a\u76ee\u6807；\u4f5c\u8005\u663e\u8457\u6027\u6ca1\u62a5\u544a\u5219NA，\u4e0d\u628ameaningful\u7406\u89e3\u4e3a\u7edf\u8ba1\u663e\u8457。\n', encoding='utf-8')
    return dest / 'index.html'
