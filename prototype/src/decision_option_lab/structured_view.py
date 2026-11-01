# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Source-only graph reuse/results presentation. Reads model records, never changes scientific choices."""
import base64
import copy
import html
import json
import math
from pathlib import Path
from structured_multiverse import ROOT, read, save, file_sha
from paper_graph_review import layout, lines

def encode(x):
    return json.dumps(x, ensure_ascii=False, separators=(',', ':'), sort_keys=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')

def figures(out, frozen, results):
    good = [r for r in results if r['status'] == 'ok']
    groups = [g for g in frozen['plan']['comparison_groups'] if any((r['group_id'] == g['id'] for r in good))]
    if not good:
        return None
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    font = FontProperties(fname='C:/Windows/Fonts/msyh.ttc') if Path('C:/Windows/Fonts/msyh.ttc').exists() else FontProperties()
    matplotlib.rcParams['svg.hashsalt'] = 'source-only-multiverse-v1'
    cols = min(2, len(groups))
    rows = math.ceil(len(groups) / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(7 * cols, 4.7 * rows), squeeze=False, layout='constrained')
    for ax, g in zip(axes.flat, groups):
        rr = sorted([r for r in good if r['group_id'] == g['id']], key=lambda r: (r['result']['estimate'], r['spec_id']))
        estimates = [r['result']['estimate'] for r in rr]
        ax.plot(range(len(rr)), estimates, 'o-', markersize=3.5, linewidth=0.8, color='#3568a3')
        for i, r in enumerate(rr):
            v = r['result']
            if v['ci_low'] is not None:
                ax.vlines(i, v['ci_low'], v['ci_high'], linewidth=0.9, color='#3568a3', alpha=0.6)
        bounds = [v for r in rr for v in [r['result']['estimate'], r['result']['ci_low'], r['result']['ci_high']] if v is not None] + [g['null_value']]
        lo = min(bounds)
        hi = max(bounds)
        pad = max((hi - lo) * 0.12, 0.005)
        ax.set_ylim(lo - pad, hi + pad)
        ax.set_xlim(-0.6, max(0.6, len(rr) - 0.4))
        ax.axhline(g['null_value'], linewidth=0.7, color='#8d959e')
        if len(rr) <= 8:
            indices = list(range(len(rr)))
        else:
            indices = sorted({0, len(rr) // 4, len(rr) // 2, 3 * len(rr) // 4, len(rr) - 1})
        ax.set_xticks(indices, [rr[i]['spec_id'] for i in indices])
        ax.set_xlabel('\u5206\u6790\u65b9\u6848（\u6309\u771f\u5b9e\u4f30\u8ba1\u503c\u6392\u5e8f）', fontproperties=font)
        ax.set_ylabel(g['effect_scale'], fontproperties=font)
        ax.set_title('\n'.join(lines(g['label'], 42)) + f'\n{len(rr)}\u6761\u5b9e\u9645\u6210\u529f\u8def\u5f84', fontproperties=font)
        ax.spines[['top', 'right']].set_visible(False)
        ax.grid(axis='y', alpha=0.12)
    for ax in list(axes.flat)[len(groups):]:
        ax.axis('off')
    fig.suptitle('Specification \u66f2\u7ebf：\u4ec5\u8fde\u63a5\u771f\u5b9e\u7ed3\u679c，\u6bd4\u8f83\u7ec4\u5206\u522b\u5c55\u793a', fontproperties=font, fontsize=13)
    fig.savefig(out / 'specification_curve.png', dpi=160)
    fig.savefig(out / 'specification_curve.svg', metadata={'Date': None})
    plt.close(fig)
    return out / 'specification_curve.png'

def export_graphs(out, d):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
    from matplotlib.font_manager import FontProperties
    font = FontProperties(fname='C:/Windows/Fonts/msyh.ttc') if Path('C:/Windows/Fonts/msyh.ttc').exists() else FontProperties()
    for key, title in [('original', '\u539f\u8bba\u6587\u5206\u6790\u56fe'), ('expanded', '\u77e5\u8bc6\u5e93\u6269\u5c55\u5206\u6790\u56fe')]:
        g = d['graphs'][key]
        l = d['layouts'][key]
        if not g['decisions']:
            continue
        cw = 248
        gap = 58
        W = l['columns'] * (cw + gap) + 24
        H = l['height']
        fig, ax = plt.subplots(figsize=(W / 90, H / 90), layout='constrained')
        ax.set_xlim(0, W)
        ax.set_ylim(H, 0)
        ax.axis('off')
        blocks = {b['decision_id']: b for b in l['blocks']}
        for e in g['dependency_edges']:
            a = blocks[e['from']]
            b = blocks[e['to']]
            x1 = 18 + a['rank'] * (cw + gap) + cw - 5
            x2 = 18 + b['rank'] * (cw + gap) + 5
            if b['rank'] - a['rank'] > 1:
                ax.plot([x1, x1 + 20, x1 + 20, x2 - 20, x2 - 20], [a['mid_y'], a['mid_y'], 25, 25, b['mid_y']], color='#a0a5ac', linewidth=0.8)
                start = (x2 - 20, b['mid_y'])
            else:
                start = (x1, a['mid_y'])
            ax.add_patch(FancyArrowPatch(start, (x2, b['mid_y']), arrowstyle='-|>', mutation_scale=9, color='#9299a1', linewidth=0.8))
        for b in l['blocks']:
            dec = next((x for x in g['decisions'] if x['id'] == b['decision_id']))
            x = 18 + b['rank'] * (cw + gap)
            ax.text(x + cw / 2, b['y'] + 3, '\n'.join(b['header_lines']), fontproperties=font, fontsize=10, ha='center', va='top')
            for p in b['options']:
                o = next((o for o in dec['options'] if o['id'] == p['id']))
                reported = o['origin'] == 'reported'
                cy = p['y'] + p['height'] / 2
                ax.plot([x + 5, x + 5, x + 17], [b['mid_y'], cy, cy], color='#a0a5ac', linewidth=0.8)
                ax.plot([x + cw - 17, x + cw - 5, x + cw - 5], [cy, cy, b['mid_y']], color='#a0a5ac', linewidth=0.8)
                ax.add_patch(FancyBboxPatch((x + 17, p['y']), cw - 34, p['height'], boxstyle='round,pad=0,rounding_size=4', facecolor='#edf3fb' if reported else '#f3eef9', edgecolor='#c8ced6', linewidth=0.8))
                ax.text(x + cw / 2, p['y'] + 10, o['id'] + ' · ' + ('reported \u539f\u6587\u6709\u636e' if reported else 'adapted \u77e5\u8bc6\u5e93\u6cbf\u7528'), fontproperties=font, fontsize=9, ha='center', va='top')
                ax.text(x + cw / 2, p['y'] + 34, '\n'.join(p['lines']), fontproperties=font, fontsize=10, ha='center', va='top')
        fig.suptitle(title, fontproperties=font, fontsize=13)
        fig.savefig(out / (title + '.png'), dpi=130)
        fig.savefig(out / (title + '.svg'), metadata={'Date': None})
        plt.close(fig)

def payload(out):
    ctx = read(out / 'context.json')
    f = read(out / 'frozen_execution.json')
    review = read(out / 'candidate_review.json')
    idx = read(out / 'retrieval/index.json')
    plan = f['plan']
    execution_rows = read(out / 'execution_results.json')
    outcomes = {r['spec_id']: r for r in execution_rows}
    original = copy.deepcopy(ctx.get('original_graph') or {'hypothesis_text': ctx['h1']['text'], 'decisions': [], 'dependency_edges': [], 'forbidden_combinations': []})
    expanded = copy.deepcopy(original)
    nodes = {d['id']: d for d in expanded['decisions']}
    fixed = {s['id']: s['target_decision_id'] for s in plan['fixed_original_steps']}
    aliases = {d['id']: 'KB_' + d['id'] for d in plan['execution_decisions']}
    stepmap = {**fixed, **aliases}
    for d in plan['execution_decisions']:
        options = []
        for o in d['options']:
            a = f['instances'][d['id'] + '/' + o['id']]
            source = idx['options'][o['source_option_ref']]
            mids = a['source_method_ids']
            core = {'name': '；'.join((idx['methods'][m]['name'] for m in mids)), 'scientific_function': a['target_metric'], 'core': a['core_definition']}
            opts = {'id': o['id'], 'label': o['label'], 'origin': 'adapted', 'method_mode': 'adapted', 'description': a['reason'], 'source_option_ref': o['source_option_ref'], 'triad': {'method': core, 'data_columns': [{'column_id': b.get('column_id'), 'name': b['name'], 'meaning': b['meaning'], 'role': b['role']} for b in a['data_binding']], 'parameters': [{'name': p['name'], 'value': p['value'], 'status': p['status'], 'reason': p['reason']} for p in a['parameters']], 'components': [{'name': c['component_ref'], 'role': c['classification']['scientific_function']} for c in source['components']]}, 'method_refs': [{'method_id': m, 'component_refs': [c for c in a['component_refs'] if any((c == v['component_ref'] and v['classification']['method_id'] == m for v in source['components']))], 'core_preserved': [a['core_definition']], 'adaptation_changes': a['changes']} for m in mids], 'source_decision_refs': d['source_decision_refs'], 'source_component_refs': a['component_refs'], 'adaptation_scope': a.get('adaptation_scope', 'whole_source_option_or_recorded_component'), 'execution_status': o['status'], 'evidence': source['option'].get('evidence', []), 'prerequisites': a['required_inputs'], 'limitations': a['unresolved'] + a['defining_conditions']}
            cases = [outcomes.get(sp['spec_id'], {}) for sp in f['space']['selected_specifications'] if sp.get('execution_choices', sp['choices']).get(d['id']) == o['id']]
            opts['execution_status'] = 'executed' if any((c.get('status') == 'ok' for c in cases)) else 'pre_execution_blocked' if cases and all((c.get('execution_engine') is None for c in cases)) else 'execution_failed' if cases else 'not_selected'
            options.append(opts)
        expanded['decisions'].append({'id': aliases[d['id']], 'label': d['label'], 'why_a_decision': d['reason'], 'source_decision_refs': d['source_decision_refs'], 'options': options})
    edgekeys = {(e['from'], e['to']) for e in expanded['dependency_edges']}
    for step in plan['fixed_original_steps'] + plan['execution_decisions']:
        to = stepmap[step['id']]
        for dep in step['depends_on']:
            start = stepmap[dep]
            if start != to and (start, to) not in edgekeys:
                expanded['dependency_edges'].append({'from': start, 'to': to, 'reason': '\u51bb\u7ed3\u6267\u884c\u8ba1\u5212\u4e2d\u7684\u4f9d\u8d56'})
                edgekeys.add((start, to))
    specs = []
    original_ids = {d['id'] for d in original['decisions']}
    active_fixed = {s['target_decision_id']: s['target_option_id'] for s in plan['fixed_original_steps']}
    for sp in f['space']['selected_specifications']:
        executed = sp.get('execution_choices', sp['choices'])
        choices = {**active_fixed, **{aliases[k]: v for k, v in executed.items()}}
        label = '；'.join((next((o['label'] for d in plan['execution_decisions'] if d['id'] == k for o in d['options'] if o['id'] == v)) for k, v in executed.items()))
        specs.append({**sp, 'choices': choices, 'label': label, 'scientific_rationale': '\u6765\u81ea\u5df2\u6709\u77e5\u8bc6\u5e93Option\u7684\u51bb\u7ed3\u9002\u914d\u7ec4\u5408；\u672a\u6dfb\u52a0\u65e0\u6765\u6e90\u79d1\u5b66\u9009\u9879。', 'status': 'ready' if outcomes.get(sp['spec_id'], {}).get('status') == 'ok' else 'blocked', 'inactive_decisions': [{'decision_id': did, 'reason': '\u539f\u65b9\u6848\u4fdd\u7559，\u5f53\u524d\u6267\u884c\u8def\u5f84\u672a\u91c7\u7528'} for did in sorted(original_ids - set(active_fixed))] + [{'decision_id': aliases[did], 'reason': '\u672c\u6bd4\u8f83\u7ec4\u672a\u91c7\u7528\u7684\u53e6\u4e00\u5206\u652f'} for did in sp.get('inactive_decision_ids', [])]})
    results = copy.deepcopy(execution_rows)
    for r in results:
        if r['status'] == 'ok':
            r['result'].pop('analysis_unit_ids', None)
    usedmethods = {m['method_id'] for d in expanded['decisions'] for o in d['options'] for m in o.get('method_refs', [])}
    path_layouts = {}
    for sp in specs:
        ids = set(sp['choices'])
        subgraph = {**expanded, 'decisions': [d for d in expanded['decisions'] if d['id'] in ids], 'dependency_edges': [e for e in expanded['dependency_edges'] if e['from'] in ids and e['to'] in ids]}
        path_layouts[sp['spec_id']] = layout(subgraph)
    return {'h1': ctx['h1'], 'graphs': {'original': original, 'expanded': expanded}, 'path_layouts': path_layouts, 'layouts': {'original': layout(original) if original['decisions'] else {'blocks': [], 'ranks': {}, 'columns': 1, 'height': 200, 'minimum_column_width': 248, 'column_gap': 58}, 'expanded': layout(expanded) if expanded['decisions'] else {'blocks': [], 'ranks': {}, 'columns': 1, 'height': 200, 'minimum_column_width': 248, 'column_gap': 58}}, 'specifications': specs, 'groups': plan['comparison_groups'], 'results': results, 'methods': {m: idx['methods'][m] for m in sorted(usedmethods)}, 'column_features': {c['column_id']: c for c in ctx['dataset']['columns']}, 'original_option_status': plan['original_option_status'], 'default_spec_id': next((r['spec_id'] for r in results if r['status'] == 'ok'), specs[0]['spec_id'] if specs else 'all'), 'counts': {'new_options': sum((len(d['options']) for d in plan['execution_decisions']))}, 'review_counts': review['adaptation_counts']}

def ledger_markup(out):
    review = read(out / 'candidate_review.json')
    idx = read(out / 'retrieval/index.json')
    ad = {(a['source_option_ref'], a['operation_id']): a for a in review['adaptations']}
    esc = html.escape
    rows = []
    labels = {'applicable': '\u9002\u7528\u5019\u9009', 'conditional': '\u6709\u6761\u4ef6\u9002\u7528', 'inapplicable': '\u4e0d\u9002\u7528', 'ready': '\u9002\u914d\u540e\u53ef\u6267\u884c', 'blocked': '\u9002\u914d\u53d7\u963b'}
    for r in review['assessments']:
        source = idx['options'][r['source_option_ref']]
        for a in r['operation_assessments']:
            adapted = ad.get((r['source_option_ref'], a['operation_id']))
            end = labels.get(adapted['status'], adapted['status']) if adapted else '\u521d\u5ba1/\u6392\u9664\u590d\u6838\u540e\u4e0d\u9002\u7528'
            rows.append('<tr><td>' + esc(r['source_option_ref']) + '<br>' + esc(source['option']['label']) + '<br>' + esc(a['operation_id']) + '</td><td>' + esc(labels[a['status']]) + ' → ' + esc(end) + '</td><td>' + esc(a['adaptation_attempt']) + '<br>' + esc(a['reason']) + ('<details><summary>\u9002\u914d\u914d\u7f6e\u4e0e\u672a\u89e3\u51b3\u6761\u4ef6</summary><p>' + esc(adapted['adaptation_attempt']) + '</p><p>' + esc(adapted['reason']) + '</p><ul>' + ''.join(('<li>' + esc(v) + '</li>' for v in adapted['unresolved'])) + '</ul></details>' if adapted else '') + '</td></tr>')
    return '<details><summary>\u68c0\u7d22\u4e0e\u9002\u914d\u5ba1\u6838\u8bb0\u5f55（' + str(len(rows)) + '\u6761\u64cd\u4f5c—Option\u8bb0\u5f55）</summary><div class="table-responsive"><table class="table table-sm"><thead><tr><th>\u6765\u6e90Decision/Option</th><th>\u72b6\u6001\u53d8\u5316</th><th>\u4fdd\u7559\u6216\u6392\u9664\u7406\u7531</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></details>'

def build(out):
    f = read(out / 'frozen_execution.json')
    results = read(out / 'execution_results.json')
    d = payload(out)
    image = figures(out, f, results)
    export_graphs(out, d)
    d['curve_image'] = 'data:image/png;base64,' + base64.b64encode(image.read_bytes()).decode('ascii') if image else None
    text = (ROOT / 'paper_graph_review_fragment.html').read_text('utf-8')
    text = text.replace('paper-review-lab', 'source-reuse-lab').replace('proposed', 'adapted')
    text = text.replace('DeepSeek\u65b0\u589e\u914d\u7f6e', '\u77e5\u8bc6\u5e93\u6cbf\u7528／\u9002\u914d').replace('DeepSeek\u4e3a\u672c\u6570\u636e\u914d\u7f6e\u7684\u65b0\u589eOption', '\u6cbf\u7528\u5df2\u6709\u6e90Option，\u9488\u5bf9\u5f53\u524d\u5217\u4e0e\u53c2\u6570\u9002\u914d')
    text = text.replace('\u589e\u52a0\u53ef\u66ff\u6362\u7684\u5019\u9009\u65b9\u6848', '\u6cbf\u5df2\u6709Decision→Option\u5173\u7cfb\u5f15\u5165\u5019\u9009')
    text = text.replace('\u76f8\u5173\u7cfb\u6570 / 95%\u533a\u95f4', '\u4f30\u8ba1\u503c / \u533a\u95f4')
    text = text.replace("path=D.specifications.some(s=>s.spec_id===state.path)?state.path:'all'", "path=D.specifications.some(s=>s.spec_id===state.path)?state.path:(state.path==='all'?'all':D.default_spec_id)")
    text = text.replace('l=D.layouts[key],container=', "l=(key==='expanded'&&D.path_layouts[path])||D.layouts[key],container=")
    text = text.replace('for(const e of g.dependency_edges){const a=blocks[e.from]', 'for(const e of g.dependency_edges.filter(e=>blocks[e.from]&&blocks[e.to])){const a=blocks[e.from]')
    text = text.replace("'；\u5176\u4ed6\u9009\u9879\u6de1\u5316。'", "'；\u4ec5\u663e\u793a\u672c\u8def\u5f84\u6240\u9700\u51b3\u7b56，\u540c\u4e00\u51b3\u7b56\u4e0b\u7684\u5176\u4ed6\u9009\u9879\u6de1\u5316。'")
    text = text.replace('；\u5176\u4ed6\u9009\u9879\u6de1\u5316。', '；\u4ec5\u663e\u793a\u672c\u8def\u5f84\u6240\u9700\u51b3\u7b56，\u540c\u4e00\u51b3\u7b56\u4e0b\u5176\u4ed6\u9009\u9879\u6de1\u5316。')
    text = text.replace("pilot.status==='conditional'?'（\u6761\u4ef6\u6027，\u4ecd\u9700\u6838\u5b9e）':''", "pilot.status==='blocked'?'（\u672a\u901a\u8fc7\u6267\u884c\u68c0\u67e5，\u539f\u56e0\u89c1\u7ed3\u679c\u9875）':''")
    text = text.replace("executed_fixed:'", "executed:'\u5df2\u5b9e\u9645\u6267\u884c',pre_execution_blocked:'\u6267\u884c\u524d\u963b\u65ad',execution_failed:'\u6267\u884c\u5931\u8d25',not_selected:'\u672a\u9009\u5165\u53bb\u91cd\u540e\u6267\u884c\u8def\u5f84',executed_fixed:'")
    text = text.replace("adapted:'\u6a21\u578b\u63d0\u51fa'", "adapted:'\u5df2\u6709\u65b9\u6cd5\u7684\u76ee\u6807\u9002\u914d'")
    text = text.replace('\u65b0\u589e${D.counts.new_options}\u4e2a\u914d\u7f6e\u5747\u4e3aadapted', '\u6cbf\u7528${D.counts.new_options}\u4e2a\u6709\u6765\u6e90\u914d\u7f6e，\u5747\u53ef\u56de\u67e5\u6e90Decision/Option')
    text = text.replace('target_bound:', "executed_fixed:'\u5df2\u4f5c\u4e3a\u56fa\u5b9a\u6b65\u9aa4\u6267\u884c',retained_not_executed:'\u4fdd\u7559\u4f46\u672a\u6267\u884c',replaced_by_catalog_instances:'\u7531\u77e5\u8bc6\u5e93\u5b9e\u4f8b\u6267\u884c',target_bound:") if 'target_bound:' in text else text
    start = text.index('function curves(){')
    end = text.index("$('rv-h1').textContent", start)
    text = text[:start] + (ROOT / 'structured_curve_view.js').read_text('utf-8') + '\n' + text[end:]
    text = text.replace('<p class="text-small">\u70b9\u8868\u793a\u4f30\u8ba1\u503c，\u7ad6\u7ebf\u8868\u793a95%\u533a\u95f4。S1\u4e0eS2\u53ea\u5728\u662f\u5426\u8ba1\u7b97\u533a\u95f4\u4e0a\u4e0d\u540c；S3\u4e3a\u6761\u4ef6\u6027\u52a0\u6743\u65b9\u6848，\u5355\u72ec\u5c55\u793a。\u5f53\u524d\u6ca1\u6709\u6b63\u5f0fP\u503c\u68c0\u9a8c，\u4e0d\u80fd\u636e\u6b64\u5224\u65ad\u6574\u4f53\u7a33\u5065\u6027。</p>', '<p class="text-small">\u53ea\u7ed8\u5236\u5b9e\u9645\u6210\u529f\u7ed3\u679c；\u8fde\u7ebf\u4ec5\u8f85\u52a9\u9605\u8bfb，\u4e0d\u8868\u793a\u65b9\u6848\u8fde\u7eed\u53d8\u5316。\u4e0d\u540c\u603b\u4f53\u548c\u6307\u6807\u5206\u7ec4。\u672a\u751f\u6210\u8db3\u591f\u8def\u5f84\u65f6\u5982\u5b9e\u62a5\u544a，\u4e0d\u8865\u9020\u66f2\u7ebf\u70b9。</p>')
    text = text.replace('<div id="rv-path-summary" class="text-small"></div>', '<div id="rv-path-summary" class="text-small"></div>' + ledger_markup(out))
    text = text.replace('html+=\'<div class="rv-detail-columns">\'', 'html+=\'<div class="rv-detail-columns">\'')
    anchor = "let html='<p>'+esc(o.origin==='reported'?'reported：\u8bba\u6587\u6216\u968f\u9644\u4ee3\u7801\u4e2d\u6709\u4f9d\u636e':'adapted：\u6cbf\u7528\u5df2\u6709\u6e90Option，\u9488\u5bf9\u5f53\u524d\u5217\u4e0e\u53c2\u6570\u9002\u914d')+'</p>';"
    text = text.replace(anchor, anchor + "\n if(o.source_option_ref)html+='<p>\u6e90Decision：'+value(o.source_decision_refs)+'；\u6e90Option：'+esc(o.source_option_ref)+'；\u7ec4\u4ef6：'+value(o.source_component_refs)+'；\u590d\u7528\u8303\u56f4：'+value(o.adaptation_scope)+'；\u6267\u884c\u72b6\u6001：'+value(o.execution_status)+'</p>';")
    text = text.replace('<div id="rv-expanded-drawing"', '<details><summary>\u8fd9\u5f20\u56fe\u4e0e\u77e5\u8bc6\u5e93\u5c42\u7ea7\u7684\u5173\u7cfb</summary><p>\u6a2a\u5411\u8282\u70b9\u662f Decision（\u8981\u4f5c\u51fa\u7684\u5206\u6790\u9009\u62e9），\u5206\u652f\u662f Option（\u5019\u9009\u505a\u6cd5）。Option \u5185\u6298\u53e0 Method（\u65b9\u6cd5\u6838\u5fc3）、\u6570\u636e\u5217\u53ca\u8bed\u4e49、\u5b8c\u6574\u53c2\u6570\u548c\u7ec4\u4ef6。\u77e5\u8bc6\u5e93\u4e2d\u7684 Family \u5f52\u7c7b Method；Method \u901a\u8fc7\u7ec4\u4ef6\u4e0e\u8bba\u6587 Option \u5173\u8054，Method \u4e0d\u662f Decision。\u672c\u56fe\u6cbf\u771f\u5b9e Decision→Option→\u7ec4\u4ef6→Method \u5173\u7cfb\u5f15\u5165\u5f53\u524d\u6570\u636e\u7684\u9002\u914d\u5b9e\u4f8b。</p></details><div id="rv-expanded-drawing"')
    if not d['graphs']['original']['decisions']:
        text = text.replace('\u539f\u8bba\u6587\u5206\u6790\u56fe：\u8bba\u6587\u4e0e\u4ee3\u7801\u5b9e\u9645\u62a5\u544a\u7684\u505a\u6cd5', '\u76ee\u6807\u8d77\u70b9：\u672a\u63d0\u4f9b\u539f\u6587reported\u56fe').replace('>\u539f\u8bba\u6587\u5206\u6790\u56fe</button>', '>\u76ee\u6807\u8d77\u70b9（\u539f\u56fe\u672a\u63d0\u4f9b）</button>')
    fragment = text.replace('__DATA__', encode(d))
    if len(fragment.encode('utf-8')) >= 1000000:
        fragment = text.replace(ledger_markup(out), '<p class="text-small">\u5b8c\u6574\u5019\u9009\u5ba1\u6838\u8bb0\u5f55\u89c1\u6d4f\u89c8\u5668\u7248。</p>').replace('__DATA__', encode(d))
    if len(fragment.encode('utf-8')) >= 1000000:
        raise ValueError('Inline display exceeds budget; reduce figure export dpi without altering data')
    (out / 'source-reuse.html').write_text(fragment, encoding='utf-8')
    shell = (ROOT / 'semantic_stitch_shell.html').read_text('utf-8').replace('semantic-stitch-lab', 'source-reuse-lab').replace('\u6570\u636e\u5217\u6392\u5e8f、\u73b0\u6709\u56fe\u68c0\u7d22\u4e0e\u6d41\u7a0b\u62fc\u63a5', '\u77e5\u8bc6\u5e93\u7ed3\u6784\u68c0\u7d22、\u6cbf\u7528\u5206\u6790\u56fe\u4e0eSpecification\u66f2\u7ebf').replace('main{max-width:1240px;margin:auto}', 'main{max-width:1900px;margin:auto}')
    browser_fragment = text.replace('__DATA__', encode(d))
    (out / 'index.html').write_text(shell.replace('__COMPONENTS__', '{}').replace('__FRAGMENT__', browser_fragment), encoding='utf-8')
    save(out / '\u5c55\u793a\u6570\u636e.json', d)
    write_report(out, f, results)
    print('Source-graph reuse browser built', flush=True)

def write_report(out, f, results):
    v = read(out / 'verification.json')
    review = read(out / 'candidate_review.json')
    task = read(out / 'task.json')
    ctx = read(out / 'context.json')
    idx = read(out / 'retrieval/index.json')
    space = f['space']
    reconsider = read(out / 'exclusion_reconsideration.json') if (out / 'exclusion_reconsideration.json').exists() else {'changed_to_retained': 0}
    refs = sorted({o['source_option_ref'] for d in f['plan']['execution_decisions'] for o in d['options'] if o['status'] == 'enabled'})
    good = [r for r in results if r['status'] == 'ok']
    rows = []
    successful_bindings = len({json.dumps(r['choices'], sort_keys=True) for r in good})
    audit = read(out / 'accepted_audit.json') if (out / 'accepted_audit.json').exists() else {}
    blockers = [r for r in results if r['status'] != 'ok']
    runtime_failed = sum((bool(r.get('execution_engine')) for r in blockers))
    blocked_text = '\n'.join(('- ' + r['spec_id'] + ' / ' + r['group_id'] + '：' + str(r.get('error')) for r in blockers))
    for r in good:
        x = r['result']
        ci = '\u672a\u8ba1\u7b97' if x['ci_low'] is None else f'[{x['ci_low']:.6g}, {x['ci_high']:.6g}]'
        rows.append(f'| {r['spec_id']} | {r['group_id']} | {x['estimate']:.7g} | {ci} | {(x['pvalue'] if x['pvalue'] is not None else '\u672a\u8ba1\u7b97')} | {x['nobs']} |')
    resolution_note = ''
    if (out / 'configuration_resolution.json').exists():
        resolution = read(out / 'configuration_resolution.json')
        counts = lambda rows: {s: sum((a['status'] == s for a in rows)) for s in ['ready', 'conditional', 'blocked']}
        resolution_note = '\u672c\u8f6e\u589e\u52a0\u4e86\u81ea\u52a8\u914d\u7f6e\u95ed\u5408：\u9996\u6b21\u9002\u914d\u4e3a' + str(counts(resolution['before'])) + '，DeepSeek\u4f9d\u636e\u4efb\u52a1、\u6765\u6e90\u548c\u666e\u901a\u6570\u636e\u6d4b\u91cf\u91cd\u65b0\u914d\u7f6e\u540e\u4e3a' + str(counts(resolution['after'])) + '。\u5b83\u533a\u5206\u53ef\u914d\u7f6e\u53c2\u6570\u4e0e\u771f\u6b63\u7f3a\u5931\u6761\u4ef6，\u5e76\u5141\u8bb8\u660e\u786e\u8bb0\u5f55\u7684\u6e90\u7ec4\u4ef6Method\u590d\u7528；\u4e0d\u58f0\u79f0\u539fOption\u6574\u5957\u539f\u573a\u666f\u5df2\u7ecf\u590d\u73b0。\u539fMethod\u7684\u5b9a\u4e49\u6027\u6838\u5fc3\u4ecd\u9700\u4fdd\u7559，\u6240\u6709\u79d1\u5b66\u53c2\u6570\u5728\u7ed3\u679c\u4ea7\u751f\u524d\u786e\u5b9a。\u521d\u6b21\u96f6\u8def\u5f84\u8bd5\u9a8c\u53e6\u5b58\u4e8e\u540c\u7ea7 Structured_DAG_Multiverse_20261024，\u672a\u8986\u76d6。'
    txt = f'# \u4ece\u77e5\u8bc6\u5e93\u56fe\u7ed3\u6784\u6cbf\u7528\u65b9\u6848：\u672c\u8f6e\u8ba8\u8bba\u62a5\u544a\n\n\u672c\u8f6e\u6700\u7ec8\u7ed3\u679c：\u7a0b\u5e8f\u53ec\u56de{review['source_options']}\u4e2a\u6765\u6e90Option，\u51bb\u7ed3{len(space['selected_specifications'])}\u6761\u9884\u9009\u8def\u5f84，\u6700\u7ec8\u6210\u529f{len(good)}\u6761，\u5176\u4ed6{len(blockers)}\u6761\u672a\u8fdb\u5165\u6700\u7ec8\u66f2\u7ebf。\u6210\u529f\u7ed3\u679c\u5206\u5c5e{len({r['group_id'] for r in good})}\u4e2a\u6307\u6807\u7ec4，\u76ee\u524d\u4ecd\u672a\u5f97\u5230\u540c\u4e00\u53ef\u6bd4\u6307\u6807\u4e0b\u7684\u5bc6\u96c6Specification Curve。\u539f\u4e8c\u5341\u7bc7DAG\u6ca1\u6709\u4fee\u6539，\u6240\u6709\u79d1\u7814\u9002\u914d\u4e0e\u79d1\u5b66\u8ba1\u7b97\u4ee3\u7801\u7531DeepSeek\u751f\u6210。\n\n## \u672c\u8f6e\u76ee\u6807\u4e0e\u8fb9\u754c\n\u8f93\u5165\u771f\u5b9e\u6570\u636e、\u6570\u636e\u5143\u4fe1\u606f\u548cH1，\u7a0b\u5e8f\u5148\u505a\u7d22\u5f15\u68c0\u7d22\u548c\u56fe\u904d\u5386，DeepSeek\u5206\u6279\u5224\u65ad\u5019\u9009、\u5c1d\u8bd5\u9002\u914d\u5e76\u751f\u6210\u51bb\u7ed3\u6267\u884c\u56fe、\u5b8c\u6574Boba\u6a21\u677f\u4e0e\u5206\u6790\u4ee3\u7801，\u7a0b\u5e8f\u518d\u6821\u9a8c、\u7f16\u8bd1、\u5b9e\u9645\u6267\u884c\u5e76\u4f5c\u56fe。\u5f00\u53d1\u8005\u6ca1\u6709\u624b\u6539\u79d1\u7814\u5206\u7c7b、\u65b9\u6cd5、Option\u6216\u5206\u6790\u6570\u503c。\n\n\u6cbf\u7528\u4e0a\u4e00\u8f6e\u540c\u4e00\u7bc7\u4e8c\u5341\u7bc7\u4e4b\u5916\u7684GEOWEALTH-US\u8bba\u6587\u53ca\u56fa\u5b9aH1：{ctx['h1']['text']}。\u6e90\u8f93\u5165\u662f\u5b8c\u6574{ctx['dataset']['rows']}\u884c、{len(ctx['dataset']['columns'])}\u5217\u7684\u8868，\u539f\u56fe\u4e0e\u8bed\u4e49\u8bb0\u5f55\u7ee7\u7eed\u4fdd\u7559。\u672c\u8f6e\u6ca1\u6709\u589e\u52a0\u8bba\u6587、\u91cd\u65b0\u5408\u5e76\u4e8c\u5341\u7bc7\u6216\u6539\u5199\u5176\u5206\u7c7b。\u539f\u77e5\u8bc6\u5e93\u5feb\u7167\u4fdd\u6301\u51bb\u7ed3。\n\n## \u6bcf\u4e00\u6b65\u600e\u4e48\u505a、\u5f97\u5230\u4e86\u4ec0\u4e48\n1. **\u8fd8\u539f\u771f\u5b9e\u5173\u7cfb。** \u7a0b\u5e8f\u4ece\u539f\u8bb0\u5f55\u673a\u68b0\u8fd8\u539f{len(idx['decisions'])}\u4e2a\u6765\u6e90Decision、{len(idx['options'])}\u4e2areported Option、315\u4e2a\u7ec4\u4ef6\u548c{len(idx['methods'])}\u4e2aMethod\u7684\u5173\u8054，\u4fdd\u7559Family、\u4f9d\u8d56、\u6761\u4ef6\u548c\u53c2\u6570。\u6ca1\u6709\u91cd\u65b0\u7ed9\u65b9\u6cd5\u5206\u7c7b。\n2. **\u7406\u89e3\u4efb\u52a1。** DeepSeek\u53ea\u6839\u636eH1、\u6570\u636e\u5143\u4fe1\u606f\u548c\u539f\u56fe\u63d0\u51fa{len(task['operations'])}\u9879\u68c0\u7d22\u9700\u6c42；\u8fd9\u4e9b\u9700\u6c42\u4e0d\u662f\u65b0\u589e\u79d1\u5b66Decision，\u4e5f\u4e0d\u9884\u5148\u628aH1\u9501\u5b9a\u4e3a\u552f\u4e00Pearson\u6307\u6807。\n3. **\u7a0b\u5e8f\u53ec\u56de\u5e76\u6cbf\u56fe\u5c55\u5f00。** \u672c\u5730\u4e2d\u6587\u5b57\u7b26TF-IDF\u5173\u952e\u8bcd\u68c0\u7d22＋\u56fa\u5b9a\u7248\u672c\u591a\u8bed\u8a00\u5411\u91cf\u4f59\u5f26\u68c0\u7d22，\u5148\u5339\u914dDecision，\u518d\u5b8c\u6574\u5c55\u5f00\u5176Option。Family\u4f5c\u4e3a\u8f85\u52a9\u53ec\u56de；Method\u68c0\u7d22\u53ea\u4f5c\u8865\u5145，\u5e76\u56de\u6eaf\u6e90Option\u4e0eDecision。\u5019\u9009\u4e0d\u8db3\u65f6\u6269\u5927\u53ec\u56de。\u6700\u7ec8\u53ec\u56de{review['retrieval_counts']['source_decisions']}\u4e2a\u6765\u6e90Decision、{review['source_options']}\u4e2aOption。DeepSeek\u6ca1\u6709\u901a\u8bfb262\u4e2aMethod\u540e\u81ea\u4e3b\u5bfb\u627e\u76f8\u4f3c\u8005。\n4. **\u9010\u9879\u5ba1\u6838、\u5c1d\u8bd5\u9002\u914d。** \u6bcf\u6279\u6700\u591a6\u4e2a\u6e90Option，\u8bb0\u5f55\u9002\u7528/\u6761\u4ef6\u6027/\u4e0d\u9002\u7528；\u5168\u90e8\u6392\u9664\u9879\u53e6\u6b21\u590d\u6838，\u9632\u6b62\u4ec5\u56e0\u9886\u57df\u6216\u65e7\u5217\u540d\u4e0d\u540c\u5c31\u62d2\u7edd。\u672c\u8f6e\u6392\u9664\u590d\u6838\u540e\u6709{reconsider['changed_to_retained']}\u6761\u64cd\u4f5c—Option\u8bb0\u5f55\u6539\u4e3a\u4fdd\u7559\u6216\u6761\u4ef6\u6027。\u9002\u914d\u9636\u6bb5\u91cd\u65b0\u7ed1\u5b9a\u5217、\u660e\u786e\u53c2\u6570\u4e0e\u6e90\u6838\u5fc3，\u72b6\u6001\u7edf\u8ba1\u4e3a{review['adaptation_counts']}。\u8fd9\u4e9b\u662f\u6a21\u578b\u5224\u65ad，\u4e0d\u662f\u72ec\u7acb\u79d1\u7814\u6709\u6548\u6027\u8bc1\u660e。\n5. **\u6784\u5efa\u6709\u6765\u6e90\u7684\u6267\u884c\u56fe。** \u539freported\u56fe\u5355\u72ec\u4fdd\u7559。\u6bcf\u4e2a\u65b0\u589e\u6267\u884cDecision\u548cOption\u5fc5\u987b\u56de\u6307\u4e8c\u5341\u7bc7\u65e2\u6709\u8282\u70b9；\u4e0d\u5141\u8bb8\u65e0\u6765\u6e90\u7684\u79d1\u5b66\u81ea\u7531\u5ea6。\u8fdb\u5165\u53ef\u6267\u884c\u56fe\u7684\u6e90Option：{'、'.join(refs) or '\u65e0'}。\u76ee\u6807\u9002\u914d\u5b9e\u4f8b\u4e0e\u539f\u6587reported\u8eab\u4efd\u5206\u522b\u8bb0\u5f55。\u5fc5\u8981\u53c2\u6570\u6216\u6761\u4ef6\u672a\u89e3\u51b3\u65f6\u4e0d\u6267\u884c，\u4e0d\u7528\u6280\u672f\u9ed8\u8ba4\u503c\u8865\u79d1\u5b66\u51b3\u5b9a。\n6. **\u5148\u56fa\u5b9a\u518d\u679a\u4e3e。** \u56fa\u5b9a\u4f30\u8ba1\u91cf、\u603b\u4f53、\u6307\u6807、\u65b9\u5411、\u6837\u672c\u653f\u7b56\u548c\u4f9d\u8d56。\u7ed3\u6784\u7ec4\u5408{space['raw_combinations']}\u4e2a，\u68c0\u67e5{space['examined']}\u4e2a，\u6309\u7ea6\u675f\u4e0e\u6a21\u578b\u7b49\u4ef7\u952e\u53bb\u91cd\u540e{space['valid_unique_paths']}\u6761，\u9884\u9009\u6267\u884c{len(space['selected_specifications'])}\u6761。\u679a\u4e3e{('\u5b8c\u6574' if space['complete'] else '\u8fbe\u5230\u68c0\u67e5\u4e0a\u9650，\u4e0d\u80fd\u58f0\u79f0\u7a77\u4e3e')}。\u6700\u591a100\u6761，\u6309Option/\u7ec4\u8986\u76d6\u7387\u4e0e\u56fa\u5b9a\u54c8\u5e0c\u9009\u53d6，\u4e0d\u63a5\u89e6\u4f30\u8ba1\u7ed3\u679c；\u4e0d\u4f7f\u7528\u79cd\u5b50\u6216\u91cd\u590d\u6b21\u6570\u51d1\u8def\u5f84。\n7. **\u6a21\u578b\u751f\u6210\u6a21\u677f\u4e0e\u4ee3\u7801。** Boba\u6a21\u677f\u5168\u6587\u548c\u79d1\u5b66\u8ba1\u7b97Python\u6a21\u5757\u5747\u7531DeepSeek\u751f\u6210。\u7a0b\u5e8f\u53ea\u4f5c\u7ed3\u6784/\u4ee3\u7801/\u6765\u6e90\u6821\u9a8c\u4e0e\u5b98\u65b9Boba\u7f16\u8bd1；\u901a\u7528\u8fd0\u884c\u6865\u4e0d\u5305\u542b\u9488\u5bf9\u672c\u8bba\u6587\u7684\u79d1\u5b66\u7b97\u6cd5。\u53e6\u4e00\u6b21\u6a21\u578b\u8c03\u7528\u5bf9\u7167\u771f\u5b9e\u4ee3\u7801\u7247\u6bb5\u590d\u6838\u6e90\u6838\u5fc3\u548c\u51bb\u7ed3\u53c2\u6570。\n8. **\u9010\u6761\u590d\u6838\u4ee3\u7801，\u518d\u8fd0\u884c。** \u6a21\u578b\u9010\u6761\u68c0\u67e5{len(space['selected_specifications'])}\u6761\u9884\u9009\u8def\u5f84，\u6700\u7ec8\u6709\u6548\u901a\u8fc7{v.get('pre_execution_approved_specifications', len(audit.get('approved_spec_ids', [])))}\u6761；\u6700\u7ec8\u5b9e\u9645\u6210\u529f{v['successful_specifications']}\u6761、\u8fd0\u884c\u5931\u8d25{runtime_failed}\u6761、\u6267\u884c\u524d\u963b\u65ad{len(blockers) - runtime_failed}\u6761。\u4ec5\u6700\u7ec8\u6210\u529f\u7ed3\u679c\u4f5c\u56fe。\u51bb\u7ed3\u8ba1\u5212\u6709{v['comparison_groups']}\u4e2a\u6bd4\u8f83\u7ec4；\u5176\u4e2d\u6709\u5b9e\u9645\u7ed3\u679c\u7684\u7ec4\u4e3a{len({r['group_id'] for r in good})}\u4e2a。\u4ee3\u7801\u6216\u51bb\u7ed3\u914d\u7f6e\u6709\u51b2\u7a81\u7684\u8def\u5f84\u4fdd\u7559\u539f\u56fe\u4e0e\u7406\u7531，\u4e0d\u7531\u5f00\u53d1\u8005\u6539\u79d1\u7814\u5b57\u6bb5\u6765\u901a\u8fc7。\u524d\u671f\u8bd5\u8dd1\u56de\u6267\u4ecd\u4fdd\u7559，\u4e0d\u8ba1\u5165\u6700\u7ec8\u6210\u529f\u6570。\n9. **Boba\u5b9e\u9645\u6267\u884c。** \u5b98\u65b9\u7f16\u8bd1\u5f97\u5230{v.get('compiled_boba_scripts', 0)}\u4e2a\u4e0d\u540c\u53d8\u91cf\u7ed1\u5b9a\u811a\u672c；\u901a\u7528\u8fd0\u884c\u6865\u53ea\u6267\u884c\u9010\u6761\u590d\u6838\u901a\u8fc7\u7684\u51bb\u7ed3\u6bd4\u8f83\u7ec4。\u76f8\u540cBoba\u53d8\u91cf\u7ed1\u5b9a\u53ef\u80fd\u5bf9\u5e94\u591a\u4e2a\u9884\u5148\u786e\u5b9a\u7684\u6bd4\u8f83\u7ec4，\u56e0\u6b64\u811a\u672c\u6570、\u7ec4\u6570、\u6267\u884c\u8bb0\u5f55\u6570\u4e0d\u662f\u4e00\u56de\u4e8b。\u672c\u8f6e\u5b9e\u9645\u8fd0\u884c\u7f16\u8bd1\u540e\u7684\u811a\u672c，\u5e76\u7531\u5b83\u8c03\u7528DeepSeek\u751f\u6210\u7684\u7edf\u8ba1\u6a21\u5757；\u4e0d\u662f\u4ec5\u7f16\u8bd1\u540e\u53e6\u7531\u5f00\u53d1\u8005\u5206\u6790。\u6a21\u677f\u683c\u5f0f\u82e5\u9700\u4fee\u590d，\u7531DeepSeek\u5355\u72ec\u4fee\u590d，\u4fdd\u6301\u79d1\u5b66\u4ee3\u7801\u4e0d\u53d8。\u5931\u8d25\u65e5\u5fd7\u4fdd\u7559；\u4ec5\u5931\u8d25\u4fe1\u606f\u8fdb\u5165\u4fee\u590d，\u4e0d\u4f20\u6210\u529f\u4f30\u8ba1\u503c/P\u503c。\n\n**\u672c\u8f6e\u6210\u529f\u8bb0\u5f55\u5b9e\u9645\u5bf9\u5e94{successful_bindings}\u79cd\u5b8c\u6574Boba\u53d8\u91cf\u7ed1\u5b9a。** {len(good)}\u4e2a\u6210\u529f\u7ed3\u679c\u4e3b\u8981\u7531\u51bb\u7ed3\u6bd4\u8f83\u7ec4\u53caactive\u5206\u652f\u533a\u5206，\u4e0d\u80fd\u58f0\u79f0\u83b7\u5f97{len(good)}\u79cd\u4e0d\u540cBoba\u7ec4\u5408。\u6a21\u578b\u628a\u82e5\u5e72\u66ff\u4ee3\u65b9\u6cd5\u653e\u5728\u4e0d\u540cDecision\u5206\u652f，\u5c1a\u672a\u5145\u5206\u5f62\u6210“\u540c\u4e00Decision\u4e0b\u591aOption\u7ec4\u5408”\u7684\u76ee\u6807\u56fe；\u5f00\u53d1\u8005\u6ca1\u6709\u624b\u5de5\u91cd\u7ec4\u79d1\u7814\u8282\u70b9\u6765\u7f8e\u5316\u7ed3\u679c。\u8fd9\u662f\u672c\u8f6e\u6ca1\u6709\u5f62\u6210\u5bc6\u96c6\u66f2\u7ebf\u7684\u4e00\u4e2a\u7ed3\u6784\u95ee\u9898。\n\n## \u5b9e\u9645\u7ed3\u679c\n{resolution_note}\n\n| \u8def\u5f84 | \u6bd4\u8f83\u7ec4 | \u4f30\u8ba1\u503c | \u533a\u95f4 | P\u503c | \u5206\u6790\u5355\u5143\u6570 |\n| --- | --- | ---: | --- | --- | ---: |\n{(chr(10).join(rows) if rows else '| \u65e0\u6210\u529f\u7ed3\u679c | — | — | — | — | — |')}\n\n{('\u672c\u8f6e\u4e0d\u8db330\u6761\u6709\u6548\u5b9e\u9645\u8def\u5f84，\u672a\u8fbe\u5230\u5e0c\u671b\u768430—100\u6761；\u6ca1\u6709\u901a\u8fc7\u521b\u9020Option、\u53d8\u66f4seed\u6216\u63d2\u503c\u8865\u9020\u66f2\u7ebf\u70b9\u6765\u51d1\u6570\u91cf。' if len(good) < 30 else '\u5df2\u83b7\u5f97\u8f83\u591a\u5b9e\u9645\u8def\u5f84，\u4f46\u8def\u5f84\u6570\u91cf\u4e0d\u8bc1\u660e\u65b9\u6cd5\u5b9e\u8d28\u5dee\u5f02\u6216\u79d1\u7814\u7a33\u5065\u6027。')} \u66f2\u7ebf\u4ec5\u8fde\u63a5\u6392\u5e8f\u540e\u7684\u771f\u5b9e\u7ed3\u679c；\u8fde\u7ebf\u53ea\u662f\u9605\u8bfb\u8f85\u52a9，\u4e0d\u8868\u793a\u8fd9\u4e9b\u65b9\u6848\u6784\u6210\u8fde\u7eed\u81ea\u53d8\u91cf。\u4e0d\u540c\u76ee\u6807/\u6307\u6807\u5206\u7ec4，\u5931\u8d25\u65b9\u6848\u4e0d\u753b\u6210\u96f6\u503c。\n\n## \u95ee\u9898\u548c\u53ef\u6838\u67e5\u7684\u7f3a\u53e3\n### \u672a\u5f97\u5230\u6210\u529f\u7ed3\u679c\u7684\u9884\u9009\u8def\u5f84\n{blocked_text or '\u5168\u90e8\u9884\u9009\u8def\u5f84\u5747\u5f97\u5230\u6210\u529f\u7ed3\u679c；\u4ecd\u4e0d\u8868\u793a\u79d1\u7814\u6709\u6548\u6027\u5df2\u8bc1\u660e。'}\n\n### \u751f\u6210\u8ba1\u5212\u8bb0\u5f55\u7684\u7f3a\u53e3\n{chr(10).join(('- ' + str(g) for g in f['plan']['gaps'])) or '- \u6a21\u578b\u6267\u884c\u8ba1\u5212\u672a\u62a5\u544a\u7ed3\u6784\u6027\u7f3a\u53e3；\u4ecd\u9700\u68c0\u67e5\u9002\u7528\u6027\u5224\u65ad\u662f\u5426\u6b63\u786e。'}\n{chr(10).join(('- ' + str(x) for x in f['plan']['limitations']))}\n\n- \u4e25\u683c\u4e0d\u65b0\u589e\u6e90Option\u540e，\u73b0\u6709\u5e93\u53ef\u80fd\u65e0\u6cd5\u4e3a\u672c\u6570\u636e/H1\u63d0\u4f9b\u8db3\u591f\u66ff\u4ee3。\u8fd9\u4e0e\u7a0b\u5e8f\u80fd\u5426\u8dd1\u901a\u662f\u4e24\u56de\u4e8b；\u4e0d\u8db3\u65f6\u5fc5\u987b\u66b4\u9732\u7f3a\u53e3。\n- \u53ec\u56de\u91c7\u7528\u7a0b\u5e8f\u7d22\u5f15\u5e76\u6709\u6240\u6269\u5927，\u4ecd\u4e0d\u4fdd\u8bc1\u627e\u5230\u6240\u6709\u79d1\u7814\u4e0a\u5408\u7406\u65b9\u6cd5；\u5411\u91cf\u5206\u6570\u4e0d\u662f\u9002\u7528\u6982\u7387。\u6392\u9664\u590d\u6838\u4ecd\u7531\u540c\u4e00\u6a21\u578b\u63d0\u4f9b，\u4e0d\u662f\u72ec\u7acb\u4e13\u5bb6\u8ba4\u8bc1。\n- \u8de8\u8bba\u6587\u65b9\u6cd5\u80fd\u5426\u4fdd\u7559\u5b9a\u4e49\u6027\u6838\u5fc3、\u5404\u8def\u5f84\u662f\u5426\u771f\u6b63\u53ef\u6bd4，\u4ecd\u662f\u6a21\u578b\u5224\u65ad；\u7a0b\u5e8f\u4e0d\u80fd\u4ec5\u51ed\u6765\u6e90\u7f16\u53f7\u8bc1\u660e\u79d1\u7814\u6b63\u786e。\n- \u539f\u4e09\u7bc7\u67096\u6761\u5386\u53f2Option\u5f15\u6587\u5b57\u9762\u4e0d\u5339\u914d，\u4ecd\u4fdd\u7559\u5728\u4e8c\u5341\u7bc7\u539f\u59cb\u6838\u9a8c\u8bb0\u5f55\u4e2d，\u672c\u8f6e\u6ca1\u6709\u4fee\u6b63。\u6e90\u7f16\u53f7\u53ef\u56de\u67e5\u4e0d\u7b49\u4e8e\u6240\u6709\u5386\u53f2\u5f15\u6587\u548c\u5206\u7c7b\u5df2\u7ecf\u6b63\u786e。\n- \u7b49\u4ef7\u952e\u51b3\u5b9a\u53bb\u91cd，\u4ea6\u7531\u6a21\u578b\u7ed9\u51fa；\u4e0d\u80fd\u628a\u8def\u5f84\u6570\u5f53\u4f5c\u72ec\u7acb\u65b9\u6cd5\u6570。\u5fc5\u8981\u672a\u77e5\u4e0d\u8fdb\u5165\u6267\u884c，\u5176\u4ed6\u672a\u68c0\u9a8c\u6a21\u578b\u5047\u8bbe\u4ecd\u9700\u5728\u7ed3\u679c\u9650\u5236\u4e2d\u9605\u8bfb。\n- \u4ee3\u7801\u590d\u6838\u66fe\u5bf9\u540c\u4e00\u51bb\u7ed3\u8ba1\u5212\u524d\u540e\u7ed9\u51fa\u77db\u76fe\u5224\u65ad。\u7a0b\u5e8f\u4f1a\u4fdd\u7559\u5148\u524d\u660e\u786e\u7684scientific_freeze_conflict：\u4ec5\u6539\u4ee3\u7801\u4e0d\u80fd\u6e05\u9664\u5b83，\u8be5\u8def\u5f84\u5728\u672c\u8f6e\u9694\u79bb。freeze_conflict_guard.json\u8bb0\u5f55\u6765\u6e90；\u540e\u7eed\u82e5\u8981\u89e3\u51b3，\u9700\u5355\u72ec\u590d\u6838\u51bb\u7ed3\u8ba1\u5212，\u672c\u8f6e\u6ca1\u6709\u624b\u6539\u516c\u5f0f。\n- \u4e0d\u540c\u6307\u6807\u5206\u7ec4\u540e，\u6bcf\u7ec4\u53ef\u80fd\u4ecd\u7136\u53ea\u6709\u4e00\u4e2a\u6216\u4e24\u4e2a\u70b9；\u5373\u4f7f\u603b\u6267\u884c\u8bb0\u5f55\u589e\u52a0，\u4e5f\u6ca1\u6709\u5f62\u6210\u540c\u4e00\u53ef\u6bd4\u6307\u6807\u4e0b\u7684\u5bc6\u96c6Specification Curve。\u8de8\u7ec4\u57fa\u7ebf\u53ef\u80fd\u91cd\u590d，\u4e0d\u80fd\u7d2f\u8ba1\u6210\u66f4\u591a\u72ec\u7acb\u65b9\u6cd5。\n- \u539f\u4e8c\u5341\u7bc7\u5206\u7c7b\u7c92\u5ea6\u548c\u6536\u655b\u95ee\u9898\u672a\u5728\u672c\u8f6e\u89e3\u51b3。\u7a0b\u5e8f\u6d4b\u8bd5\u548c\u771f\u5b9e\u8fd0\u884c\u53ea\u8bc1\u660e\u76f8\u5173\u673a\u68b0\u68c0\u67e5\u548c\u6267\u884c\u8bb0\u5f55，\u4e0d\u8bc1\u660eH1\u6210\u7acb。\n\n## \u5c55\u793a\u4e0e\u72ec\u7acb\u8fd0\u884c\n\u6253\u5f00index.html，\u53ea\u4fdd\u7559“\u539f\u8bba\u6587\u5206\u6790\u56fe”“\u77e5\u8bc6\u5e93\u6269\u5c55\u5206\u6790\u56fe”“Specification\u66f2\u7ebf”。\u6a2a\u56fe\u53ef\u70b9\u9009\u8def\u5f84、\u67e5\u770bOption\u91cc\u7684\u65b9\u6cd5—\u6570\u636e\u5217/\u8bed\u4e49/\u6d4b\u91cf\u7279\u5f81—\u5b8c\u6574\u53c2\u6570；\u6269\u5c55\u56fe\u4e0b\u6298\u53e0\u5168\u90e8\u5019\u9009\u5ba1\u6838\u548c\u6392\u9664\u7406\u7531。\n\n\u5df2\u6709\u7ed3\u679c\u4e25\u683c\u91cd\u653e：`python outputs/decision_option_lab/structured_multiverse.py --output outputs/{out.name} --replay`，\u4e0d\u8c03\u7528API、\u4e0d\u91cd\u65b0\u7edf\u8ba1。\u5b9e\u9645\u91cd\u590d\u5206\u6790\u4f7f\u7528`--rerun`；\u65e7\u56de\u6267\u7559\u5b58。\u65b0\u6570\u636e\u4f7f\u7528`--data \u6570\u636e.csv --metadata \u5143\u4fe1\u606f.json --hypothesis H1.json --output \u65b0\u76ee\u5f55`，\u53ef\u9009`--target-graph`\u4e0e`--sources`；\u4e0d\u63d0\u4f9b\u539f\u6587\u56fe\u65f6\u4e0d\u80fd\u628a\u8d77\u70b9\u79f0\u4e3a\u539f\u8bba\u6587reported\u56fe，\u53ea\u80fd\u4ece\u5e93\u4e2d\u6cbf\u7528\u5b9e\u4f8b。H1.json\u4f7f\u7528\u542btext\u5b57\u6bb5\u7684\u5bf9\u8c61。\n\n\u65b0\u8c03\u7528\u53ea\u8bfb\u672c\u5730.env\u6700\u65b0key，\u4e0d\u8fdb\u5165\u62a5\u544a/\u7f13\u5b58/\u4ea4\u4ed8。\u56fa\u5b9a\u6570\u636e、\u7d22\u5f15\u6a21\u578b\u7248\u672c/\u54c8\u5e0c、\u53ec\u56de\u5206\u6570、\u6e90\u5f15\u7528、\u6a21\u578b\u54cd\u5e94、\u51bb\u7ed3\u53c2\u6570、\u4ee3\u7801、\u73af\u5883\u4e0e\u771f\u5b9e\u7ed3\u679c\u624d\u80fd\u7559\u5b58\u672c\u7248；\u5168\u65b0API\u8c03\u7528\u4e0d\u4fdd\u8bc1\u9010\u5b57\u4e00\u81f4。\u6267\u884c\u5ba1\u8ba1\u94a9\u5b50\u548c\u5b50\u8fdb\u7a0b\u4e0d\u662f\u64cd\u4f5c\u7cfb\u7edf\u7ea7\u5b89\u5168\u6c99\u7bb1。\n\n\u672c\u5730\u5411\u91cf\u6a21\u578b：[Sentence Transformers\u6a21\u578b\u53ca\u56fa\u5b9a\u7248\u672c\u6765\u6e90](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)；\u8fd0\u884c\u65b9\u5f0f\u53c2\u8003[\u5b98\u65b9ONNX\u8bf4\u660e](https://www.sbert.net/docs/sentence_transformer/usage/efficiency.html)。\u6a21\u578b\u7528\u4e8e\u53ec\u56de\u5206\u6570，\u4e0d\u4f5c\u79d1\u7814\u9002\u7528\u6027\u88c1\u51b3。\n'
    (out / 'README.md').write_text(txt, encoding='utf-8')
    (out / '\u8ba8\u8bba\u7b80\u62a5.md').write_text(txt, encoding='utf-8')
