# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Map existing decisions using DeepSeek, then conservatively contract their DAGs.
No paper-specific mappings or semantic decisions are authored in this program.
"""
import argparse
from collections import Counter
import datetime as dt
import html
import itertools
import os
from pathlib import Path
import sys
import lab
ROOT = Path(__file__).resolve().parent

def load_papers(input_dir):
    selection = lab.read(input_dir / 'selection.json')['selected']
    papers = []
    for i, item in enumerate(selection, 1):
        folder = input_dir / item['paper_id']
        context, space = (lab.read(folder / 'context.json'), lab.read(folder / 'options.json'))
        if lab.validate_space(space, context['hypothesis']['text']):
            raise ValueError(f'Invalid input DAG: {item['paper_id']}')
        papers.append({'alias': f'P{i}', 'paper_id': item['paper_id'], 'title': item['title'], 'context': context, 'space': space, 'checks': lab.read(folder / 'checks.json'), 'sources': lab.read(folder / 'sources.json')['sources']})
    return papers

def mapping_errors(obj, refs):
    errors = []
    mappings = obj.get('mappings', [])
    actual = [m.get('source_ref') for m in mappings]
    if Counter(actual) != Counter(refs):
        errors.append('mappings must cover each original source_ref exactly once')
    for m in mappings:
        for k in ('source_ref', 'category', 'standard_question', 'operation', 'object_role', 'inputs', 'outputs', 'estimand_impact', 'scope_conditions', 'context_specific', 'mapping_rationale', 'upstream_uncertainties'):
            if k not in m:
                errors.append(f'Missing mapping.{k}')
        if m.get('category') not in ('sample', 'missingness', 'measurement', 'model', 'adjustment', 'inference', 'evaluation', 'other'):
            errors.append('Invalid category')
        if m.get('estimand_impact') not in ('preserves', 'conditional', 'changes', 'unclear'):
            errors.append('Invalid estimand_impact')
        for k in ('inputs', 'outputs', 'scope_conditions', 'context_specific', 'upstream_uncertainties'):
            if not isinstance(m.get(k), list):
                errors.append(f'{k} must be array')
        if not m.get('inputs') or not m.get('outputs') or (not m.get('standard_question')):
            errors.append('Non-empty inputs/outputs/standard_question required')
    if not isinstance(obj.get('limitations'), list):
        errors.append('limitations array required')
    return errors

def relation_errors(obj, pair_ids):
    rows = obj.get('assessments', [])
    errors = []
    if Counter((r.get('pair_id') for r in rows)) != Counter(pair_ids):
        errors.append('Assess each candidate pair exactly once, no missing/extra/duplicate pairs')
    for r in rows:
        for k in ('pair_id', 'relation', 'reason', 'shared_question', 'reuse_conditions'):
            if k not in r:
                errors.append(f'Missing assessment.{k}')
        if r.get('relation') not in ('same', 'related', 'different', 'uncertain'):
            errors.append('Invalid relation')
        if not isinstance(r.get('reuse_conditions'), list) or not r.get('reason'):
            errors.append('reason and reuse_conditions array required')
        if r.get('relation') == 'same' and (not r.get('shared_question') or not r.get('reuse_conditions')):
            errors.append('same requires shared_question and reuse_conditions')
    if not isinstance(obj.get('limitations'), list):
        errors.append('limitations array required')
    return errors

def acyclic(nodes, edges):
    parents = {n: set() for n in nodes}
    for a, b in edges:
        if a == b or a not in parents or b not in parents:
            return False
        parents[b].add(a)
    done = set()
    while True:
        ready = {n for n in parents if n not in done and parents[n] <= done}
        if not ready:
            return len(done) == len(parents)
        done |= ready

def contract(refs, edges, pairs, assessments):
    """Accept only pairwise-complete same groups with distinct paper contexts and no cycles."""
    pairmap = {p['pair_id']: p for p in pairs}
    lookup = {frozenset((pairmap[r['pair_id']]['a'], pairmap[r['pair_id']]['b'])): r for r in assessments}
    groups = [{ref} for ref in refs]
    accepted, rejected = ([], [])
    for row in sorted(assessments, key=lambda r: r['pair_id']):
        if row['relation'] != 'same':
            continue
        pair = pairmap[row['pair_id']]
        ga = next((g for g in groups if pair['a'] in g))
        gb = next((g for g in groups if pair['b'] in g))
        if ga is gb:
            accepted.append(row['pair_id'])
            continue
        reason = None
        combined = ga | gb
        if len({r.split(':', 1)[0] for r in combined}) != len(combined):
            reason = 'same_paper_collision: would collapse two distinct decisions in one paper'
        elif not all((lookup.get(frozenset((a, b)), {}).get('relation') == 'same' for a in ga for b in gb)):
            reason = 'nontransitive_same: not every pair in combined group was judged same'
        else:
            tentative = [g for g in groups if g is not ga and g is not gb] + [combined]
            owner = {ref: i for i, g in enumerate(tentative) for ref in g}
            if not acyclic(range(len(tentative)), {(owner[a], owner[b]) for a, b in edges}):
                reason = 'cycle_after_contraction: preserve separate context nodes and all original edges'
        if reason:
            rejected.append({'pair_id': row['pair_id'], 'reason': reason})
        else:
            groups = [g for g in groups if g is not ga and g is not gb] + [combined]
            accepted.append(row['pair_id'])
    return (sorted([sorted(g) for g in groups], key=lambda g: g[0]), accepted, rejected)

def assemble(papers, mappings, pairs, relations):
    originals = {}
    edge_records = []
    original_constraints = []
    for p in papers:
        alias = p['alias']
        for d in p['space']['decisions']:
            ref = f'{alias}:{d['id']}'
            originals[ref] = {'ref': ref, 'paper': alias, 'paper_id': p['paper_id'], 'decision': d, 'mapping': mappings[ref]}
        for e in p['space']['dependency_edges']:
            edge_records.append({'from': f'{alias}:{e['from']}', 'to': f'{alias}:{e['to']}', 'paper': alias, 'reason': e['reason']})
        original_constraints.extend(({'paper': alias, 'constraint': c} for c in p['space']['forbidden_combinations']))
    groups, accepted, rejected = contract(list(originals), [(e['from'], e['to']) for e in edge_records], pairs, relations['assessments'])
    owner = {ref: f'M{i}' for i, g in enumerate(groups, 1) for ref in g}
    pairmap = {x['pair_id']: x for x in pairs}
    nodes = []
    for i, g in enumerate(groups, 1):
        related_rows = [r for r in relations['assessments'] if r['relation'] == 'same' and pairmap[r['pair_id']]['a'] in g and (pairmap[r['pair_id']]['b'] in g)]
        label = related_rows[0]['shared_question'] if related_rows else mappings[g[0]]['standard_question']
        nodes.append({'id': f'M{i}', 'label': label, 'shared': len(g) > 1, 'members': g, 'categories': sorted({mappings[r]['category'] for r in g}), 'merge_assessments': [r['pair_id'] for r in related_rows], 'reuse_conditions': list(dict.fromkeys((c for r in related_rows for c in r['reuse_conditions']))), 'option_occurrences': [{'source_ref': r, 'paper': originals[r]['paper'], 'option': o} for r in g for o in originals[r]['decision']['options']]})
    projected = {}
    for e in edge_records:
        key = (owner[e['from']], owner[e['to']])
        if key not in projected:
            projected[key] = {'from': key[0], 'to': key[1], 'sources': []}
        projected[key]['sources'].append(e)
    graph_edges = list(projected.values())
    for c in original_constraints:
        c['projected_choices'] = [{'node': owner[f'{c['paper']}:{d}'], 'source_ref': f'{c['paper']}:{d}', 'option_id': o} for d, o in c['constraint']['choices'].items()]
    recon = {}
    for p in papers:
        alias = p['alias']
        expected = {(e['from'], e['to']) for e in p['space']['dependency_edges']}
        recovered = {(s['from'].split(':')[1], s['to'].split(':')[1]) for e in graph_edges for s in e['sources'] if s['paper'] == alias}
        recon[alias] = {'original_decisions': len(p['space']['decisions']), 'projected_decisions': len({owner[r] for r in originals if originals[r]['paper'] == alias}), 'edge_reconstruction_identical': expected == recovered}
    checks = {'original_nodes': len(originals), 'merged_nodes': len(nodes), 'shared_nodes': sum((n['shared'] for n in nodes)), 'original_edges': len(edge_records), 'merged_edges': len(graph_edges), 'option_occurrences_before': sum((len(x['decision']['options']) for x in originals.values())), 'option_occurrences_after': sum((len(n['option_occurrences']) for n in nodes)), 'constraint_count_before': sum((len(p['space']['forbidden_combinations']) for p in papers)), 'constraint_count_after': len(original_constraints), 'candidate_pair_count': len(pairs), 'assessed_pair_count': len(relations['assessments']), 'relation_counts': dict(Counter((r['relation'] for r in relations['assessments']))), 'dag_acyclic': acyclic([n['id'] for n in nodes], [(e['from'], e['to']) for e in graph_edges]), 'paper_reconstruction': recon, 'accepted_same_pair_ids': accepted, 'blocked_same_pairs': rejected, 'option_equivalence': 'not_evaluated', 'scientific_validity': 'not_evaluated', 'cross_paper_path_execution': 'disabled: template union is not a specification space'}
    if not checks['dag_acyclic'] or any((not v['edge_reconstruction_identical'] or v['original_decisions'] != v['projected_decisions'] for v in recon.values())):
        raise ValueError('Merge preservation invariant failed')
    return {'nodes': nodes, 'edges': graph_edges, 'originals': originals, 'owner': owner, 'constraints': original_constraints, 'checks': checks}

def wrap(text, size=20):
    return [text[i:i + size] for i in range(0, len(text), size)] or ['']

def svg_graph(graph, paper=None):
    nodes = [n for n in graph['nodes'] if paper is None or any((r.startswith(paper + ':') for r in n['members']))]
    edges = [e for e in graph['edges'] if paper is None or any((s['paper'] == paper for s in e['sources']))]
    ranks, pending = ({}, list(nodes))
    while pending:
        for n in list(pending):
            parents = [e['from'] for e in edges if e['to'] == n['id']]
            if all((p in ranks for p in parents)):
                ranks[n['id']] = max([ranks[p] + 1 for p in parents] or [0])
                pending.remove(n)
    pos, layer_y = ({}, {})
    for n in nodes:
        rank = ranks[n['id']]
        y = layer_y.get(rank, 28)
        h = 108 + len(wrap(n['label'])) * 19
        pos[n['id']] = (24 + rank * 340, y, h)
        layer_y[rank] = y + h + 34
    width = (max(ranks.values(), default=0) + 1) * 340 + 24
    height = max(layer_y.values(), default=200)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="\u8de8\u8bba\u6587\u51b3\u7b56\u6a21\u677f\u4f9d\u8d56\u56fe"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#8799b0"/></marker></defs>']
    for e in edges:
        x, y, h = pos[e['from']]
        xx, yy, hh = pos[e['to']]
        a, b, c, d = (x + 300, y + h / 2, xx, yy + hh / 2)
        tip = '; '.join((s['paper'] + ': ' + s['reason'] for s in e['sources']))
        out.append(f'<path d="M{a},{b} C{a + 22},{b} {c - 22},{d} {c},{d}" fill="none" stroke="#8799b0" stroke-width="2" marker-end="url(#arrow)"><title>{html.escape(tip)}</title></path>')
    for n in nodes:
        x, y, h = pos[n['id']]
        color = '#dff2ed' if n['shared'] else '#fff'
        out.append(f'<g><rect x="{x}" y="{y}" width="300" height="{h}" rx="12" fill="{color}" stroke="#b8ced4"/><text x="{x + 15}" y="{y + 25}" font-size="12" fill="#466577">{n['id']} · {('\u5171\u4eab\u6a21\u677f' if n['shared'] else '\u72ec\u7acb\u6a21\u677f')}</text>')
        for j, line in enumerate(wrap(n['label'])):
            out.append(f'<text x="{x + 15}" y="{y + 53 + j * 19}" font-size="14" fill="#19384c">{html.escape(line)}</text>')
        members = ' · '.join(n['members'])
        oy = y + 62 + len(wrap(n['label'])) * 19
        for j, line in enumerate(wrap(members, 34)):
            out.append(f'<text x="{x + 15}" y="{oy + j * 16}" font-size="11" fill="#4f6979">{html.escape(line)}</text>')
        out.append(f'<title>{html.escape(n['label'] + ' | ' + members)}</title></g>')
    return ''.join(out) + '</svg>'

def run(args):
    cfg = lab.read(args.config)
    cfg['max_tokens'] = 28000
    out = args.output.resolve()
    if args.fresh and out.exists() and any(out.iterdir()):
        raise ValueError('--fresh requires new or empty output folder')
    out.mkdir(parents=True, exist_ok=True)
    papers = load_papers(args.input)
    input_hashes = {str(p.relative_to(args.input)): lab.sha(p.read_bytes()) for p in sorted(args.input.glob('paper_*/*.json')) if p.name in ('context.json', 'options.json', 'sources.json', 'checks.json')}
    lab.save(out / 'input_manifest.json', {'files_sha256': input_hashes, 'paper_aliases': [{k: p[k] for k in ('alias', 'paper_id', 'title')} for p in papers]})
    mappings = {}
    mapping_limitations = []
    for p in papers:
        refs = [f'{p['alias']}:{d['id']}' for d in p['space']['decisions']]
        material = {'paper_alias': p['alias'], 'context': p['context'], 'decisions': [{'source_ref': r, **d} for r, d in zip(refs, p['space']['decisions'])], 'dependency_edges': p['space']['dependency_edges'], 'upstream_checks': p['checks'], 'sources': p['sources']}
        print(f'Mapping {p['alias']}: {len(refs)} decisions', flush=True)
        if args.mapping_cache:
            old_manifest = lab.read(args.mapping_cache / 'input_manifest.json')
            if old_manifest['files_sha256'] != input_hashes:
                raise ValueError('Reused mappings refer to different original input files')
            source_path = args.mapping_cache / p['alias'] / 'mapping.json'
            obj = lab.read(source_path)
            errors = mapping_errors(obj, refs)
            if errors:
                raise ValueError(str(errors))
            lab.save(out / p['alias'] / 'mapping.json', obj)
            lab.save(out / p['alias'] / 'mapping_provenance.json', {'mode': 'reuse_frozen_mapping', 'source': str(source_path.resolve()), 'sha256': lab.sha(source_path.read_bytes())})
            print('  mapping: reuse frozen first-trial output', flush=True)
        else:
            obj = lab.generate('mapping', material, cfg, out / p['alias'], lambda x: mapping_errors(x, refs), args.fresh, args.replay)
        mappings.update({m['source_ref']: m for m in obj['mappings']})
        mapping_limitations += obj['limitations']
    originals = [{'source_ref': f'{p['alias']}:{d['id']}', 'paper_alias': p['alias'], 'hypothesis': p['context']['hypothesis'], 'decision': d, 'mapping': mappings[f'{p['alias']}:{d['id']}']} for p in papers for d in p['space']['decisions']]
    pairs = []
    for a, b in itertools.combinations(originals, 2):
        if a['paper_alias'] != b['paper_alias']:
            pairs.append({'pair_id': f'C{len(pairs) + 1:03}', 'a': a['source_ref'], 'b': b['source_ref']})
    if len(pairs) > 500:
        raise ValueError('Quick-test limit: >500 pairs. Use a smaller input selection.')
    print(f'Comparing ALL {len(pairs)} cross-paper pairs (no category blocking)', flush=True)
    relation_stage = 'relations_functional' if args.relation_mode == 'functional' else 'relations'
    relations = lab.generate(relation_stage, {'decisions': originals, 'candidate_pairs': pairs}, cfg, out, lambda x: relation_errors(x, [p['pair_id'] for p in pairs]), args.fresh, args.replay)
    if relation_stage != 'relations':
        lab.save(out / 'relations.json', relations)
    lab.save(out / 'mappings.json', {'mappings': mappings, 'limitations': mapping_limitations})
    lab.save(out / 'candidate_pairs.json', pairs)
    graph = assemble(papers, mappings, pairs, relations)
    graph['relation_mode'] = args.relation_mode
    graph['checks']['relation_mode'] = args.relation_mode
    graph['mapping_limitations'] = mapping_limitations
    graph['relation_limitations'] = relations['limitations']
    lab.save(out / 'merged_graph.json', graph)
    lab.save(out / 'checks.json', graph['checks'])
    svgs = {'all': svg_graph(graph)}
    for p in papers:
        svgs[p['alias']] = svg_graph(graph, p['alias'])
    for name, svg in svgs.items():
        (out / f'dag_{name}.svg').write_text(svg, encoding='utf-8')
    comparison = None
    if args.mapping_cache and (args.mapping_cache / 'checks.json').exists():
        comparison = lab.read(args.mapping_cache / 'checks.json')
    data = {'graph': graph, 'papers': [{k: v for k, v in p.items() if k not in ('sources',)} for p in papers], 'comparison': comparison, 'input_base': os.path.relpath(args.input.resolve(), out).replace(os.sep, '/'), 'pairs': pairs, 'relations': relations, 'svgs': svgs}
    template = (ROOT / 'merge_report.html').read_text(encoding='utf-8')
    payload = lab.dumps(data).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    (out / 'index.html').write_text(template.replace('__DATA_JSON__', payload), encoding='utf-8')
    if (out / 'error.json').exists():
        (out / 'error.json').unlink()
    print(lab.dumps(graph['checks']), flush=True)
    print(f'Report: {out / 'index.html'}', flush=True)
if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config.json')
    parser.add_argument('--input', type=Path, default=ROOT / 'results')
    parser.add_argument('--output', type=Path, default=ROOT / 'cross_paper_results')
    parser.add_argument('--relation-mode', choices=['strict', 'functional'], default='strict')
    parser.add_argument('--mapping-cache', type=Path, help='Reuse frozen first-trial mappings with matching source hashes')
    parser.add_argument('--replay', action='store_true')
    parser.add_argument('--fresh', action='store_true')
    args = parser.parse_args()
    if args.fresh and args.replay:
        parser.error('Cannot combine --fresh and --replay')
    try:
        run(args)
    except Exception as exc:
        lab.save(args.output / 'error.json', {'error': str(exc)})
        raise
