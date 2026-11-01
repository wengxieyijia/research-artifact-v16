# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Read-only presentation revision: landscape graphs and a plain-language discussion report."""
import argparse
import hashlib
import json
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'Paper_Graph_Expansion_20261024'
DEFAULT = ROOT.parent / 'Paper_Graph_Review_20261024'

def read(p):
    return json.loads(p.read_text('utf-8'))

def save(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2), encoding='utf-8')

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def encode(x):
    return json.dumps(x, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')

def protected(base):
    paths = list(base.rglob('*'))
    paths += [ROOT.parent / 'DAG_20papers_20261023/\u5c55\u793a\u6570\u636e\u5feb\u7167.json']
    paths += [ROOT / n for n in ['reported_extract.py', 'scale_trial.py', 'standard_pipeline.py', 'method_tables.py', 'paper_graph_trial.py', 'paper_graph_view.py', 'paper_graph_fragment.html']]
    return {str(p.resolve()): sha(p) for p in paths if p.is_file() and '__pycache__' not in p.parts}

def rank_graph(g):
    pending = {d['id'] for d in g['decisions']}
    ranks = {}
    for e in g['dependency_edges']:
        if e['from'] not in pending or e['to'] not in pending:
            raise ValueError('Missing dependency endpoint')
    while pending:
        ready = [d['id'] for d in g['decisions'] if d['id'] in pending and all((e['from'] in ranks for e in g['dependency_edges'] if e['to'] == d['id']))]
        if not ready:
            raise ValueError('Cannot display cyclic execution dependencies as a ranked graph')
        for did in ready:
            ranks[did] = max([ranks[e['from']] + 1 for e in g['dependency_edges'] if e['to'] == did], default=0)
            pending.remove(did)
    return ranks

def lines(text, width=24):
    """Character-width wrapping for visible labels only; underlying scientific strings stay intact."""
    result = []
    buf = ''
    count = 0
    for c in re.findall('[A-Za-z0-9_.%+–-]+|.', str(text)):
        weight = sum((2 if ord(ch) > 255 else 1 for ch in c))
        if count + weight > width and buf:
            result.append(buf)
            buf = ''
            count = 0
        buf += c
        count += weight
    if buf:
        result.append(buf)
    return result or ['']

def layout(g):
    ranks = rank_graph(g)
    layers = sorted(set(ranks.values()))
    blocks = []
    for d in g['decisions']:
        header_lines = lines(d['id'] + ' · ' + d['label'], 29)
        opts = []
        for o in d['options']:
            label_lines = lines(o['label'], 27)
            opts.append({'id': o['id'], 'lines': label_lines, 'height': max(108, 58 + len(label_lines) * 23)})
        header_height = len(header_lines) * 23 + 22
        blocks.append({'decision_id': d['id'], 'rank': ranks[d['id']], 'header_lines': header_lines, 'header_height': header_height, 'height': header_height + sum((o['height'] for o in opts)) + 12 * (len(opts) - 1), 'options': opts})
    totals = {rank: sum((b['height'] for b in blocks if b['rank'] == rank)) + 28 * (sum((b['rank'] == rank for b in blocks)) - 1) for rank in layers}
    height = max(totals.values()) + 112
    for rank in layers:
        y = 68 + (height - 112 - totals[rank]) / 2
        for b in blocks:
            if b['rank'] != rank:
                continue
            b['y'] = y
            b['mid_y'] = y + b['header_height'] + (b['height'] - b['header_height']) / 2
            opt_y = y + b['header_height']
            for o in b['options']:
                o['y'] = opt_y
                opt_y += o['height'] + 12
            y += b['height'] + 28
    return {'ranks': ranks, 'columns': len(layers), 'height': height, 'blocks': blocks, 'minimum_column_width': 248, 'column_gap': 58}

def export_figures(out, d):
    """Standalone figures for reporting; draw existing graphs/results, never re-run analysis."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
    from matplotlib.font_manager import FontProperties
    font = FontProperties(fname='C:/Windows/Fonts/msyh.ttc') if Path('C:/Windows/Fonts/msyh.ttc').exists() else FontProperties()
    matplotlib.rcParams['svg.hashsalt'] = 'paper-graph-review-v1'
    for key, title, filename in [('original', '\u539f\u8bba\u6587\u5206\u6790\u56fe：\u8bba\u6587\u4e0e\u4ee3\u7801\u5b9e\u9645\u62a5\u544a\u7684\u9009\u62e9', '\u539f\u8bba\u6587\u5206\u6790\u56fe'), ('expanded', '\u77e5\u8bc6\u5e93\u6269\u5c55\u5206\u6790\u56fe：\u4fdd\u7559\u539f\u6587\u5e76\u589e\u52a0\u5019\u9009\u65b9\u6848', '\u77e5\u8bc6\u5e93\u6269\u5c55\u5206\u6790\u56fe')]:
        g = d['graphs'][key]
        l = d['layouts'][key]
        cw = 248
        gap = 58
        W = l['columns'] * (cw + gap) + 24
        H = l['height']
        fig, ax = plt.subplots(figsize=(W / 90, H / 90), layout='constrained')
        ax.set_xlim(0, W)
        ax.set_ylim(H, 0)
        ax.axis('off')
        bs = {b['decision_id']: b for b in l['blocks']}
        for e in g['dependency_edges']:
            a = bs[e['from']]
            b = bs[e['to']]
            x1 = 18 + a['rank'] * (cw + gap) + cw - 5
            x2 = 18 + b['rank'] * (cw + gap) + 5
            if b['rank'] - a['rank'] > 1:
                ax.plot([x1, x1 + 20, x1 + 20, x2 - 20, x2 - 20], [a['mid_y'], a['mid_y'], 25, 25, b['mid_y']], color='#a0a5ac', linewidth=1)
                start = (x2 - 20, b['mid_y'])
            else:
                start = (x1, a['mid_y'])
            ax.add_patch(FancyArrowPatch(start, (x2, b['mid_y']), arrowstyle='-|>', mutation_scale=9, color='#9299a1', linewidth=1, connectionstyle='arc3,rad=0' if b['rank'] - a['rank'] > 1 else 'arc3,rad=.08'))
        for b in l['blocks']:
            did = b['decision_id']
            dec = next((x for x in g['decisions'] if x['id'] == did))
            x = 18 + b['rank'] * (cw + gap)
            ax.text(x + cw / 2, b['y'] + 3, '\n'.join(b['header_lines']), fontproperties=font, fontsize=10, ha='center', va='top')
            for o in b['options']:
                source = next((z for z in dec['options'] if z['id'] == o['id']))
                cy = o['y'] + o['height'] / 2
                reported = source['origin'] == 'reported'
                ax.plot([x + 5, x + 5, x + 17], [b['mid_y'], cy, cy], color='#a0a5ac', linewidth=1)
                ax.plot([x + cw - 17, x + cw - 5, x + cw - 5], [cy, cy, b['mid_y']], color='#a0a5ac', linewidth=1)
                ax.add_patch(FancyBboxPatch((x + 17, o['y']), cw - 34, o['height'], boxstyle='round,pad=0,rounding_size=4', facecolor='#edf3fb' if reported else '#fbf0e0', edgecolor='#c8ced6', linewidth=0.8))
                ax.text(x + cw / 2, o['y'] + 11, o['id'] + ' · ' + ('reported \u539f\u6587\u6709\u636e' if reported else 'proposed \u6a21\u578b\u65b0\u589e'), fontproperties=font, fontsize=9, ha='center', va='top')
                ax.text(x + cw / 2, o['y'] + 35, '\n'.join(o['lines']), fontproperties=font, fontsize=10, ha='center', va='top')
        fig.suptitle(title, fontproperties=font, fontsize=13)
        fig.savefig(out / (filename + '.png'), dpi=160)
        fig.savefig(out / (filename + '.svg'), metadata={'Date': None})
        plt.close(fig)
    groups = d['groups']
    rows = d['results']
    plan = d['specifications']
    graph = d['graphs']['expanded']
    ok = [r for r in rows if r['status'] == 'ok']
    gs = [g for g in groups if any((r['group_id'] == g['id'] for r in ok))]
    varying = [dec for dec in graph['decisions'] if len({sp['choices'][dec['id']] for sp in plan}) > 1]
    if not ok:
        return
    fig, axs = plt.subplots(2, len(gs), figsize=(12, 6), gridspec_kw={'height_ratios': [3, 1]}, layout='constrained', squeeze=False)
    bounds = [v for r in ok for v in [r['result']['estimate'], r['result']['ci_low'], r['result']['ci_high']] if v is not None] + [g['null_value'] for g in gs]
    lo = min(bounds)
    hi = max(bounds)
    pad = (hi - lo or 1) * 0.12
    for j, g in enumerate(gs):
        ax, mat = (axs[0, j], axs[1, j])
        rr = sorted([r for r in ok if r['group_id'] == g['id']], key=lambda r: (r['result']['estimate'], r['spec_id']))
        for i, r in enumerate(rr):
            v = r['result']
            ax.plot(i, v['estimate'], 'o', color='#3568a3')
            if v['ci_low'] is not None:
                ax.vlines(i, v['ci_low'], v['ci_high'], color='#3568a3', linewidth=1.6)
            ax.annotate(f'r={v['estimate']:.4f}', (i, v['estimate']), xytext=(7, 9), textcoords='offset points', fontsize=10)
        ax.axhline(g['null_value'], color='#9299a1', linewidth=0.8)
        ax.set_ylim(lo - pad, hi + pad)
        ax.set_xlim(-0.5, len(rr) - 0.3)
        ax.set_xticks(range(len(rr)), [r['spec_id'] for r in rr])
        ax.set_xlabel('\u5206\u6790\u65b9\u6848（\u6309\u4f30\u8ba1\u503c\u6392\u5e8f）', fontproperties=font)
        ax.set_ylabel('\u76f8\u5173\u7cfb\u6570', fontproperties=font)
        ax.set_title('\n'.join(lines(g['id'] + ' · ' + g['label'], 48)), fontproperties=font)
        ax.spines[['top', 'right']].set_visible(False)
        mat.set_xlim(-0.5, len(rr) - 0.3)
        mat.set_ylim(len(varying) - 0.5, -0.5)
        mat.axis('off')
        for y, dec in enumerate(varying):
            for i, r in enumerate(rr):
                sp = next((s for s in plan if s['spec_id'] == r['spec_id']))
                o = next((o for o in dec['options'] if o['id'] == sp['choices'][dec['id']]))
                mat.text(i, y, dec['id'] + '/' + o['id'] + '\n' + ('\u6761\u4ef6\u6027' if sp['status'] == 'conditional' else ''), fontproperties=font, ha='center', va='center', fontsize=10)
    fig.suptitle('Specification \u66f2\u7ebf：\u4e24\u4e2a\u6bd4\u8f83\u7ec4\u5206\u522b\u5c55\u793a', fontproperties=font, fontsize=14)
    fig.savefig(out / 'specification_curve.png', dpi=180)
    fig.savefig(out / 'specification_curve.svg', metadata={'Date': None})
    plt.close(fig)

def build(base=BASE, out=DEFAULT):
    before = protected(base)
    out.mkdir(parents=True, exist_ok=True)
    src = read(base / '\u5c55\u793a\u6570\u636e.json')
    d = {'h1': src['research_context']['h1'], 'graphs': {'original': src['graph1_reported'], 'expanded': src['graph2_expanded']}, 'specifications': src['specification_plan']['specifications'], 'groups': src['specification_plan']['comparison_groups'], 'results': src['execution_results'], 'original_option_status': src['graph2_expansion']['original_option_status'], 'column_features': src['column_features'], 'methods': {m['method_id']: m for m in src['methods'] if m['method_id'] in src['verification']['catalog_method_ids_used']}, 'counts': src['verification']}
    d['layouts'] = {key: layout(g) for key, g in d['graphs'].items()}
    save(out / '\u5c55\u793a\u6570\u636e.json', d)
    fragment = (ROOT / 'paper_graph_review_fragment.html').read_text('utf-8').replace('__DATA__', encode(d))
    if len(fragment.encode('utf-8')) >= 1000000:
        raise ValueError('Inline view exceeds 1MB')
    (out / 'paper-graph-review.html').write_text(fragment, encoding='utf-8')
    shell = (ROOT / 'semantic_stitch_shell.html').read_text('utf-8').replace('\u6570\u636e\u5217\u6392\u5e8f、\u73b0\u6709\u56fe\u68c0\u7d22\u4e0e\u6d41\u7a0b\u62fc\u63a5', '\u539f\u8bba\u6587\u5206\u6790\u56fe、\u77e5\u8bc6\u5e93\u6269\u5c55\u5206\u6790\u56fe\u4e0eSpecification\u66f2\u7ebf').replace('semantic-stitch-lab', 'paper-review-lab')
    shell = shell.replace('main{max-width:1240px;margin:auto}', 'main{max-width:1900px;margin:auto}')
    (out / 'index.html').write_text(shell.replace('__COMPONENTS__', '{}').replace('__FRAGMENT__', fragment), encoding='utf-8')
    export_figures(out, d)
    report = (ROOT / 'reports/paper_graph_review.md').read_text('utf-8')
    (out / '\u8ba8\u8bba\u7b80\u62a5.md').write_text(report, encoding='utf-8')
    (out / 'README.md').write_text(report, encoding='utf-8')
    (out / '\u5237\u65b0\u5c55\u793a.ps1').write_text("$entry=Join-Path $PSScriptRoot '../decision_option_lab/paper_graph_review.py'\npython $entry --output $PSScriptRoot\n", encoding='utf-8')
    if before != protected(base):
        raise ValueError('Frozen scientific outputs or earlier programs changed')
    save(out / '\u5c55\u793a\u6539\u7248\u6838\u9a8c.json', {'presentation_only': True, 'api_calls': 0, 'analysis_reruns': 0, 'frozen_files_unchanged': len(before), 'source_directory': base.name, 'source_hashes': before, 'graph1_same': d['graphs']['original'] == read(base / 'graph1_reported.json'), 'graph2_same': d['graphs']['expanded'] == read(base / 'graph2_expanded.json'), 'results_same': d['results'] == read(base / '\u5c55\u793a\u6570\u636e.json')['execution_results'], 'visible_figures': ['\u539f\u8bba\u6587\u5206\u6790\u56fe', '\u77e5\u8bc6\u5e93\u6269\u5c55\u5206\u6790\u56fe', 'Specification\u66f2\u7ebf'], 'graph_direction': 'left-to-right', 'layout_uses_actual_dependencies': True})
    print('Read-only landscape review built: ' + str(out), flush=True)
if __name__ == '__main__':
    a = argparse.ArgumentParser()
    a.add_argument('--source', type=Path, default=BASE)
    a.add_argument('--output', type=Path, default=DEFAULT)
    x = a.parse_args()
    build(x.source.resolve(), x.output.resolve())
