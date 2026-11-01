# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Held-out data-column semantics -> frozen knowledge graph -> workflow sketch. Never executes analysis."""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import zipfile
import lab
import model_runner
import scale_trial as s
ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT.parent / 'Column_Retrieval_Stitch_20261024'
STAGES = [{'id': 'sample', 'label': '\u6837\u672c\u4e0e\u5217\u51c6\u5907'}, {'id': 'missingness', 'label': '\u7f3a\u5931\u503c\u5904\u7406'}, {'id': 'measurement', 'label': '\u53d8\u91cf\u6784\u9020'}, {'id': 'model', 'label': '\u6a21\u578b\u4f30\u8ba1'}, {'id': 'inference', 'label': '\u63a8\u65ad\u4e0e\u8bca\u65ad'}]
POLICY = {'version': 'semantic-retrieval-stitch-v1', 'scientific_judgment': 'DeepSeek only; no human-authored paper answers', 'ranking': 'H1-related scientific role, not measured predictive importance; no outcome fitting', 'graph': 'frozen reported-only twenty-paper catalog; no added method or Option', 'node_semantics': 'verbatim projection and deduplicated references from existing component data semantics', 'retrieval': 'model semantic ranking; score is not embedding cosine or a calibrated probability', 'stitch': 'new workflow proposal referencing existing M; does not prove applicability or executability', 'cycles': 'allowed at knowledge/proposal level; record cycles without claiming an executable plan', 'stop': 'no Boba template, no code generation, no analysis, no estimates, P values or specification curve'}

def read(p):
    return lab.read(p)

def save(p, x):
    lab.save(p, x)

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def prepare(out, graph, archive, replay=False):
    record = out / 'selection.json'
    if record.exists():
        return read(record)
    if replay:
        raise RuntimeError('Missing frozen selection')
    old = read(graph / 'selection.json')
    used = {x['paper_id'] for x in old['papers']}
    candidates = [x for x in read(graph / 'inventory.json') if x['paper_id'] not in used and x['data_files'] and x['languages']]
    if not candidates:
        raise ValueError('No remaining paper with recognized code and data files')
    paper = min(candidates, key=lambda x: (sum((f['bytes'] for f in x['data_files'])), x['source_bytes'], x['archive_index']))
    if paper['pdf_bytes'] > 100000000:
        raise ValueError('PDF exceeds bounded 100MB preparation limit')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'inputs').mkdir(exist_ok=True)
    shutil.copy2(graph / '\u5c55\u793a\u6570\u636e\u5feb\u7167.json', out / 'inputs/knowledge_graph.json')
    cfg = read(ROOT / 'config.json')
    cfg.update(max_pdf_chars=500000, max_code_chars=1500000)
    with zipfile.ZipFile(archive) as z:
        raw = z.read(paper['pdf_member'])
        import pymupdf
        with pymupdf.open(stream=raw, filetype='pdf') as doc:
            if len(doc) > 1000:
                raise ValueError('PDF page limit exceeded')
            sources = []
            coverage = []
            chars = 0
            for i, page in enumerate(doc, 1):
                text = page.get_text()
                chars += len(text)
                if chars > cfg['max_pdf_chars']:
                    raise ValueError('PDF text exceeds source budget; chunking required')
                if text.strip():
                    sources.append({'source_id': 'pdf:' + str(i), 'kind': 'pdf', 'location': paper['pdf_member'] + '#page=' + str(i), 'text': text})
                coverage.append({'location': 'pdf:' + str(i), 'original_chars': len(text), 'included_chars': len(text), 'low_text': len(text.strip()) < 80})
            pages = len(doc)
        chars = 0
        lab.TEXT_EXT.update({'.f', '.f90', '.qmd', '.sql'})
        for member in paper['code_members']:
            with zipfile.ZipFile(io.BytesIO(z.read(member))) as inner:
                for inf in sorted(inner.infolist(), key=lambda x: x.filename.lower()):
                    p = PurePosixPath(inf.filename)
                    if inf.is_dir() or '__MACOSX' in p.parts or p.suffix.lower() not in lab.TEXT_EXT:
                        continue
                    if inf.file_size > 5000000:
                        raise ValueError('Source file exceeds 5MB limit: ' + inf.filename)
                    text = lab.decode(inner.read(inf))
                    if p.suffix.lower() == '.ipynb':
                        nb = json.loads(text)
                        text = '\n\n'.join((''.join(c.get('source', [])) for c in nb.get('cells', [])))
                    chars += len(text)
                    if chars > cfg['max_code_chars']:
                        raise ValueError('Code text exceeds bounded budget')
                    if text.strip():
                        sources.append({'source_id': 'code:' + str(1 + sum((x['kind'] == 'code' for x in sources))), 'kind': 'code', 'location': member + '!' + inf.filename, 'text': text})
                    coverage.append({'location': member + '!' + inf.filename, 'original_chars': len(text), 'included_chars': len(text)})
    save(out / 'inputs/sources.json', {'paper': paper, 'sources': sources, 'coverage': coverage, 'pdf_pages': pages, 'pdf_sha256': hashlib.sha256(raw).hexdigest(), 'pdf_reader': 'PyMuPDF ' + pymupdf.VersionBind})
    result = {'paper': paper, 'rule': 'remaining recognized code + data files; ascending data bytes, source bytes, archive index', 'candidate_count': len(candidates), 'outside_frozen_twenty': paper['paper_id'] not in used, 'frozen_graph_sha256': sha(out / 'inputs/knowledge_graph.json'), 'frozen_paper_count': len(old['papers']), 'source_graph_directory': graph.name, 'no_manual_paper_selection': True}
    save(record, result)
    return result

def measure(out, paper, archive, replay=False):
    dest = out / 'data_features.json'
    if dest.exists():
        return read(dest)
    if replay:
        raise RuntimeError('Frozen feature measurements missing')
    import pandas as pd
    datasets = []
    files = []
    with zipfile.ZipFile(archive) as z:
        for i, item in enumerate(paper['data_files'], 1):
            with zipfile.ZipFile(io.BytesIO(z.read(item['member']))) as inner:
                raw = inner.read(item['path'])
            path = out / 'data' / ('d' + str(i) + '_' + hashlib.sha256(raw).hexdigest()[:12] + item['extension'])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            rec = {**item, 'file': path.relative_to(out).as_posix(), 'sha256': sha(path), 'errors': []}
            try:
                ext = item['extension']
                frames = {}
                if ext in ['.rdata', '.rds']:
                    import pyreadr
                    frames = dict(pyreadr.read_r(str(path)))
                elif ext in ['.csv', '.tsv']:
                    frames[None] = pd.read_csv(path, sep='\t' if ext == '.tsv' else ',', low_memory=False)
                elif ext == '.dta':
                    frames[None] = pd.read_stata(path, convert_categoricals=False)
                elif ext in ['.xls', '.xlsx']:
                    frames = pd.read_excel(path, sheet_name=None)
                elif ext == '.parquet':
                    frames[None] = pd.read_parquet(path)
                else:
                    raise ValueError('No nonexecuting reader for ' + ext)
                for j, (name, frame) in enumerate(frames.items(), 1):
                    if not isinstance(frame, pd.DataFrame):
                        continue
                    try:
                        columns = s.feature_frame(frame)
                        dsid = 'd' + str(i) + 't' + str(j)
                        for k, col in enumerate(columns, 1):
                            col['column_id'] = dsid + ':c' + str(k)
                        datasets.append({'dataset_id': dsid, 'table': str(name) if name is not None else None, 'file': rec['file'], 'archive_location': item['member'] + '!' + item['path'], 'sha256': rec['sha256'], 'rows': len(frame), 'column_count': len(columns), 'columns': columns})
                    except Exception as exc:
                        rec['errors'].append(str(name) + ': ' + type(exc).__name__ + ': ' + str(exc))
                rec['status'] = 'measured' if any((d['file'] == rec['file'] for d in datasets)) else 'not_measured'
            except Exception as exc:
                rec.update(status='not_measured', errors=[type(exc).__name__ + ': ' + str(exc)])
            files.append(rec)
    result = {'datasets': datasets, 'files': files, 'measurement': 'ordinary code, no paper code or outcome analysis executed'}
    if not datasets:
        raise ValueError('No readable rectangular data table in selected package')
    save(dest, result)
    print('Measured ' + str(len(datasets)) + ' tables', flush=True)
    return result

def semantic_index(graph):
    c = graph['classification']
    original = graph['original_options']
    entries = {}
    for row in c['rows']:
        for comp in row['components']:
            key = row['source_ref'] + '/' + comp['id']
            en = graph['enriched_components'][key]
            entries[key] = {'component_ref': key, 'source_ref': row['source_ref'], 'component_id': comp['id'], 'method_id': comp['method_id'], 'paper': original[row['source_ref']]['paper'], 'columns': [{k: x.get(k) for k in ['name', 'role', 'meaning', 'unit', 'h1_relation', 'availability', 'evidence']} for x in en['data_columns']], 'function': comp['scientific_function'], 'object_role': comp['operation_object'], 'mechanism': comp['mechanism']}
    nodes = []
    for method in c['methods']:
        refs = [key for key, x in entries.items() if x['method_id'] == method['id']]
        meanings = list(dict.fromkeys((x['meaning'] for key in refs for x in entries[key]['columns'] if x['meaning'])))
        roles = list(dict.fromkeys((x['role'] for key in refs for x in entries[key]['columns'] if x['role'])))
        nodes.append({'method_id': method['id'], 'family_id': method['family_id'], 'name': method['name'], 'kind': method['kind'], 'scientific_function': method['scientific_function'], 'operation_object': method['operation_object'], 'mechanism': method['mechanism'], 'column_meanings': meanings, 'column_roles': roles, 'component_refs': refs, 'semantic_status': 'inherited_component_semantics' if meanings else 'no_reported_column_meaning'})
    return {'policy': 'verbatim projection; no generated semantics or scientific relabeling', 'methods': nodes, 'components': entries}

def quote_errors(obj, sources):
    return s.triad.quote_errors(obj, sources)

def context_errors(x, paper, features, sources):
    e = quote_errors(x, sources)
    if x.get('paper_id') != paper['paper_id']:
        e.append('paper_id mismatch')
    for key in ['original_claim', 'h1', 'difference_from_original', 'dataset_choice', 'limitations']:
        if key not in x:
            e.append('Missing ' + key)
    if e:
        return e
    if x['dataset_choice'].get('dataset_id') not in {d['dataset_id'] for d in features['datasets']}:
        e.append('Select an actual measured dataset ID')
    if not x['h1'].get('text') or not x['h1'].get('evidence') or (not x['dataset_choice'].get('reason')):
        e.append('H1 evidence and dataset choice explanation required')
    return e

def ranking_errors(x, dataset, sources):
    e = quote_errors(x, sources)
    rows = x.get('columns', [])
    actual = {c['column_id']: c for c in dataset['columns']}
    if x.get('dataset_id') != dataset['dataset_id']:
        e.append('dataset_id mismatch')
    if {r.get('column_id') for r in rows} != set(actual) or len(rows) != len(actual):
        e.append('Every actual column exactly once')
    if sorted((r.get('rank', 0) for r in rows)) != list(range(1, len(actual) + 1)):
        e.append('Ranks must be unique contiguous 1..N')
    for r in rows:
        if r.get('name') != actual.get(r.get('column_id'), {}).get('name'):
            e.append('Exact column name required')
        for k in ['meaning', 'role', 'h1_relation', 'importance_reason', 'semantic_basis', 'evidence']:
            if k not in r:
                e.append('Missing column ' + k)
        if r.get('semantic_basis') not in ['source_grounded', 'unknown']:
            e.append('semantic_basis must be source_grounded or unknown')
        if r.get('semantic_basis') == 'source_grounded' and (not r.get('evidence')):
            e.append('Known semantics needs literal source evidence')
    return e

def retrieval_errors(x, queries, index):
    e = []
    qids = {q['column_id'] for q in queries}
    mids = {m['method_id'] for m in index['methods']}
    seen = set()
    if {r.get('column_id') for r in x.get('queries', [])} != qids or len(x.get('queries', [])) != len(qids):
        e.append('Each query column exactly once')
    for q in x.get('queries', []):
        candidates = q.get('candidates', [])
        if len(candidates) > 4:
            e.append('At most four candidates per query')
        if sorted((c.get('rank', 0) for c in candidates)) != list(range(1, len(candidates) + 1)):
            e.append('Contiguous candidate rank')
        ms = [c.get('method_id') for c in candidates]
        if len(ms) != len(set(ms)):
            e.append('No duplicate method in a query')
        for c in candidates:
            if c.get('method_id') not in mids:
                e.append('Method must exist in frozen graph')
            if c.get('applicability') not in ['candidate', 'conditional', 'not_applicable', 'unknown']:
                e.append('Invalid applicability')
            if type(c.get('semantic_relevance')) not in [int, float] or not 0 <= c['semantic_relevance'] <= 100:
                e.append('Semantic relevance 0..100 required')
            if not c.get('reason') or not c.get('support_component_refs'):
                e.append('Reason and existing component refs required')
            for ref in c.get('support_component_refs', []):
                if ref not in index['components'] or index['components'][ref]['method_id'] != c.get('method_id'):
                    e.append('Evidence component does not belong to method')
    return e

def stitch_errors(x, retrieval, ranking, graph):
    if 'output_contract' in x or 'stitch' in x or 'workflow' in x:
        return ['JSON ROOT SHAPE ERROR: output the fields label, executed, nodes, edges, stage_checks, limitations directly at the JSON root. DO NOT wrap them inside output_contract, stitch, or workflow. Return the complete unwrapped object with executed=false. Preserve source-grounded scientific content and fix the root shape.']
    e = []
    methods = {m['id'] for m in graph['classification']['methods']}
    original_components = {r['source_ref'] + '/' + c['id']: c['method_id'] for r in graph['classification']['rows'] for c in r['components']}
    allowed = {c['method_id'] for q in retrieval['queries'] for c in q['candidates'] if c['applicability'] in ['candidate', 'conditional']}
    colids = {c['column_id'] for c in ranking['columns']}
    nodes = x.get('nodes', [])
    ids = [n.get('id') for n in nodes]
    if len(ids) != len(set(ids)):
        e.append('Unique application node IDs required')
    if len(nodes) > 18:
        e.append('Pilot at most 18 application nodes; express remaining gaps separately')
    for n in nodes:
        if n.get('method_id') not in methods or n.get('method_id') not in allowed:
            e.append('Use retrieved existing candidate/conditional methods only')
        if n.get('stage') not in {p['id'] for p in STAGES}:
            e.append('Unknown generic stage')
        if n.get('status') not in ['candidate', 'conditional', 'blocked']:
            e.append('Status required, no executed/validated claims')
        if not n.get('label'):
            e.append('Application label required')
        for binding in n.get('column_bindings', []):
            if binding.get('column_id') not in colids:
                e.append('Binding must refer to actual ranked column')
            if not binding.get('expected_role') or not binding.get('reason'):
                e.append('Column binding role and reason required')
        if not n.get('column_bindings') or not n.get('reason') or (not isinstance(n.get('unresolved_conditions'), list)):
            e.append('Bindings/reason/unresolved conditions required')
        if not n.get('historical_component_refs'):
            e.append('Historical source component references required')
        for ref in n.get('historical_component_refs', []):
            if original_components.get(ref) != n.get('method_id'):
                e.append('Historical source component must belong to application method')
    for edge in x.get('edges', []):
        if edge.get('from') not in ids or edge.get('to') not in ids:
            e.append('Edge endpoint missing')
        if edge.get('origin') != 'proposed_stitch':
            e.append('New workflow edges must be marked proposed_stitch')
        if edge.get('kind') not in ['data_flow', 'stage_order', 'alternative', 'feedback']:
            e.append('Typed workflow relation required')
        if not edge.get('reason'):
            e.append('Edge explanation required')
    if {g.get('stage') for g in x.get('stage_checks', [])} != {s['id'] for s in STAGES}:
        e.append('Account for every generic stage including gaps/not applicable')
    recorded = []
    for g in x.get('stage_checks', []):
        if g.get('status') not in ['covered', 'gap', 'not_applicable'] or not g.get('reason'):
            e.append('Stage status and reason required')
        if g.get('status') == 'covered' and (not g.get('node_ids')):
            e.append('Covered stage needs actual application nodes')
        for nid in g.get('node_ids', []):
            recorded.append(nid)
            if nid not in ids or next((n for n in nodes if n['id'] == nid))['stage'] != g.get('stage'):
                e.append('Stage check references wrong application node')
    if sorted(recorded) != sorted(ids):
        e.append('Stage checks must cover each application node exactly once')
    if x.get('executed') is not False:
        e.append('Must explicitly say executed=false')
    return e

def has_cycle(nodes, edges):
    adjacency = {n['id']: [] for n in nodes}
    for edge in edges:
        adjacency[edge['from']].append(edge['to'])
    color = {k: 0 for k in adjacency}

    def visit(n):
        color[n] = 1
        for target in adjacency[n]:
            if color[target] == 1 or (color[target] == 0 and visit(target)):
                return True
        color[n] = 2
        return False
    return any((color[n] == 0 and visit(n) for n in adjacency))

def ask(stage, instruction, contract, material, out, validator, replay):
    cfg = read(ROOT / 'config_high.json')
    cfg['max_structural_repairs'] = 3
    text = (ROOT / 'instructions' / instruction).read_text(encoding='utf-8')
    return model_runner.run_json(stage, text, POLICY, contract, material, cfg, out, validator, replay)

def run(out, graph_dir, archive, stage='all', replay=False, top_k=5):
    selection = prepare(out, graph_dir, archive, replay)
    paper = selection['paper']
    if top_k < 1:
        raise ValueError('top_k must be positive')
    settings = {'policy_version': POLICY['version'], 'top_k': top_k, 'frozen_graph_sha256': selection['frozen_graph_sha256']}
    if (out / 'run_settings.json').exists() and read(out / 'run_settings.json') != settings:
        raise ValueError('Frozen run settings changed; use a new output directory')
    save(out / 'run_settings.json', settings)
    sources = read(out / 'inputs/sources.json')['sources']
    features = measure(out, paper, archive, replay)
    graph = read(out / 'inputs/knowledge_graph.json')
    index = semantic_index(graph)
    save(out / 'semantic_index.json', index)
    save(out / 'workflow_scaffold.json', {'origin': 'developer-defined generic stage scaffold, not paper-specific scientific judgment', 'stages': STAGES, 'policy': POLICY})
    if stage == 'prepare':
        return
    cfg = read(ROOT / 'config_high.json')
    model_runner.verify_provider(cfg, out, replay)
    contracts = read(ROOT / 'contracts/semantic_stitch.json')
    context = ask('research_context', 'semantic_context.txt', contracts['context'], {'paper': paper, 'sources': sources, 'measured_datasets': features['datasets']}, out, lambda x: context_errors(x, paper, features, sources), replay)
    dataset = next((d for d in features['datasets'] if d['dataset_id'] == context['dataset_choice']['dataset_id']))
    if stage == 'context':
        return
    ranking = ask('column_ranking', 'semantic_ranking.txt', contracts['ranking'], {'research_context': context, 'dataset': dataset, 'sources': sources}, out, lambda x: ranking_errors(x, dataset, sources), replay)
    queries = sorted(ranking['columns'], key=lambda c: c['rank'])[:top_k]
    save(out / 'retrieval_queries.json', {'top_k': top_k, 'columns': queries, 'criterion': 'model H1 priority ranking; no fitted outcome or predictive importance'})
    if stage == 'ranking':
        return
    retrieval = ask('semantic_retrieval', 'semantic_retrieval.txt', contracts['retrieval'], {'research_context': context, 'dataset': dataset, 'query_columns': queries, 'existing_method_index': index['methods']}, out, lambda x: retrieval_errors(x, queries, index), replay)
    if stage == 'retrieve':
        return
    hit_ids = {c['method_id'] for q in retrieval['queries'] for c in q['candidates']}
    evidence_refs = {ref for q in retrieval['queries'] for c in q['candidates'] for ref in c['support_component_refs']}
    stitch = ask('stitched_workflow', 'semantic_workflow.txt', contracts['stitch'], {'research_context': context, 'dataset': dataset, 'column_ranking': ranking, 'retrieval': retrieval, 'generic_stages': STAGES, 'retrieved_methods': [m for m in graph['classification']['methods'] if m['id'] in hit_ids], 'historical_component_semantics': {ref: index['components'][ref] for ref in sorted(evidence_refs)}}, out, lambda x: stitch_errors(x, retrieval, ranking, graph), replay)
    verify(out, graph_dir, write=True)
    import semantic_stitch_view
    semantic_stitch_view.build(out)

def verify(out, graph_dir, write=False):
    selection = read(out / 'selection.json')
    graph = read(out / 'inputs/knowledge_graph.json')
    if sha(out / 'inputs/knowledge_graph.json') != selection['frozen_graph_sha256']:
        raise ValueError('Frozen graph input modified')
    if sha(graph_dir / '\u5c55\u793a\u6570\u636e\u5feb\u7167.json') != selection['frozen_graph_sha256']:
        raise ValueError('Original graph changed')
    if selection['paper']['paper_id'] in {p['paper_id'] for p in graph['papers']}:
        raise ValueError('Target is not held out')
    source = read(out / 'inputs/sources.json')
    sources = source['sources']
    features = read(out / 'data_features.json')
    context = read(out / 'research_context.json')
    dataset = next((d for d in features['datasets'] if d['dataset_id'] == context['dataset_choice']['dataset_id']))
    ranking = read(out / 'column_ranking.json')
    retrieval = read(out / 'semantic_retrieval.json')
    stitch = read(out / 'stitched_workflow.json')
    index = semantic_index(graph)
    if index != read(out / 'semantic_index.json'):
        raise ValueError('Semantic projection differs from frozen graph')
    if any(((out / name).exists() for name in ['runs', 'analysis.py', 'boba_template.py', 'specification_curve.svg'])):
        raise ValueError('Output exceeds approved retrieval-and-stitch-only scope')
    queries = read(out / 'retrieval_queries.json')['columns']
    errors = context_errors(context, selection['paper'], features, sources) + ranking_errors(ranking, dataset, sources) + retrieval_errors(retrieval, queries, index) + stitch_errors(stitch, retrieval, ranking, graph)
    if errors:
        raise ValueError(lab.dumps(errors))
    report = {'all_checks_passed': True, 'frozen_twenty_unchanged': True, 'held_out_paper': selection['paper']['paper_id'], 'ranked_columns': len(ranking['columns']), 'queries': len(queries), 'unique_retrieved_methods': len({c['method_id'] for q in retrieval['queries'] for c in q['candidates']}), 'application_nodes': len(stitch['nodes']), 'proposed_workflow_edges': len(stitch['edges']), 'proposal_has_cycle': has_cycle(stitch['nodes'], stitch['edges']), 'cycles_allowed_in_proposal': True, 'source_text_truncations': 0, 'analysis_executed': False, 'boba_template_generated': False, 'specification_curve_generated': False, 'semantic_judgment_independently_certified': False, 'frozen_graph_sha256': selection['frozen_graph_sha256']}
    if write:
        save(out / 'verification.json', report)
    return report
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=DEFAULT)
    p.add_argument('--graph', type=Path, default=ROOT.parent / 'DAG_20papers_20261023')
    p.add_argument('--archive', type=Path, default=Path(read(ROOT / 'config.json')['archive']))
    p.add_argument('--stage', choices=['prepare', 'context', 'ranking', 'retrieve', 'all'], default='all')
    p.add_argument('--replay', action='store_true')
    p.add_argument('--top-k', type=int, default=5)
    a = p.parse_args()
    run(a.output.resolve(), a.graph.resolve(), a.archive, a.stage, a.replay, a.top_k)
