# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Task-first retrieval, audited Decision–Option application graph and Boba draft. Never executes analysis."""
import argparse
import ast
import itertools
import json
from pathlib import Path
import re
import shutil
import sys
import lab
import model_runner
import semantic_stitch as s
ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / 'Column_Retrieval_Stitch_20261024'
DEFAULT = ROOT.parent / 'Task_Decision_Option_20261024'

def read(p):
    return lab.read(p)

def save(p, x):
    lab.save(p, x)

def standard():
    return read(ROOT / 'standards/task_graph_v1.json')

def nonempty(value):
    return isinstance(value, str) and bool(value.strip())

def unique(rows, key, expected=None):
    vals = [r.get(key) for r in rows]
    return len(vals) == len(set(vals)) and (expected is None or set(vals) == set(expected))

def require(obj, keys, where):
    return [where + ': missing ' + k for k in keys if k not in obj]
TASK_CONTRACT = {'target': {'estimand': '\u64cd\u4f5c\u5316\u76ee\u6807，\u533a\u5206\u7ebf\u6027/\u79e9\u5173\u8054\u7b49', 'population': '\u5206\u6790\u5355\u5143/\u8303\u56f4', 'direction': '\u65b9\u5411', 'interpretation': '\u63cf\u8ff0/\u56e0\u679c\u7b49', 'unresolved': ['\u672a\u77e5\u5185\u5bb9']}, 'operations': [{'id': 'T1', 'label': '\u4eceH1\u63a8\u5bfc\u7684\u64cd\u4f5c', 'necessity': 'required | optional', 'form': 'fixed | decision | unresolved', 'goal': '\u79d1\u5b66\u529f\u80fd', 'input_columns': ['\u771f\u5b9ecolumn_id'], 'input_artifacts': [], 'outputs': [{'artifact_id': 'A1', 'meaning': '\u6d3e\u751f\u6570\u636e/\u7ed3\u679c\u8bed\u4e49', 'schema': ['\u8f93\u51fa\u5217\u4e0e\u89d2\u8272']}], 'depends_on': [], 'retrieval_need': '\u8981\u68c0\u7d22\u7684\u901a\u7528\u64cd\u4f5c\u4e0e\u673a\u5236', 'applicability_conditions': ['\u6570\u636e\u5c42\u7ea7\u548c\u7edf\u8ba1\u524d\u63d0'], 'choice_question': '\u53ef\u66ff\u6362\u7684\u51b3\u7b56\u95ee\u9898\u6216\u7a7a\u5b57\u7b26\u4e32', 'evidence': [{'source_id': 'pdf:1', 'quote': '\u8fde\u7eed\u539f\u6587'}], 'reason': '\u4e3a\u4f55\u5fc5\u8981\u6216\u53ef\u9009'}], 'limitations': ['\u660e\u786e\u672a\u6267\u884c\u4e0e\u4e0d\u53ef\u68c0\u9a8c\u90e8\u5206']}
REVIEW_CONTRACT = {'issues': [{'id': 'I1', 'severity': 'major | minor', 'category': 'task_completeness | redundancy | estimand | provenance | method_transfer | applicability | scope | parameters', 'step_ids': ['S1'], 'evidence': '\u5f15\u7528\u56fe\u5b57\u6bb5\u6216\u6765\u6e90\u5185\u5bb9', 'reason': '\u79d1\u7814\u5224\u65ad\u7406\u7531', 'recommendation': '\u5982\u4f55\u4fee\u6b63'}], 'overall': '\u603b\u4f53\u5224\u65ad', 'limitations': ['\u590d\u6838\u672c\u8eab\u4e5f\u662f\u6a21\u578b\u5224\u65ad，\u672a\u6267\u884c']}

def task_errors(x, ranking, sources):
    e = require(x, ['target', 'operations', 'limitations'], 'task') + s.quote_errors(x, sources)
    ops = x.get('operations', [])
    cols = {c['column_id'] for c in ranking['columns']}
    ids = {o.get('id') for o in ops}
    if not ops or not unique(ops, 'id'):
        e.append('Nonempty operations with unique IDs required')
    artifacts = [a.get('artifact_id') for o in ops for a in o.get('outputs', [])]
    if len(artifacts) != len(set(artifacts)):
        e.append('Unique output artifact IDs')
    owners = {a.get('artifact_id'): o.get('id') for o in ops for a in o.get('outputs', [])}
    ancestors = {o['id']: set(o.get('depends_on', [])) for o in ops}
    for _ in ops:
        for key in ancestors:
            ancestors[key] |= set().union(*(ancestors.get(k, set()) for k in list(ancestors[key]))) if ancestors[key] else set()
    for o in ops:
        e += require(o, ['id', 'label', 'necessity', 'form', 'goal', 'input_columns', 'input_artifacts', 'outputs', 'depends_on', 'retrieval_need', 'applicability_conditions', 'choice_question', 'evidence', 'reason'], 'operation')
        if o.get('necessity') not in ['required', 'optional'] or o.get('form') not in ['fixed', 'decision', 'unresolved']:
            e.append('Invalid operation necessity/form')
        if not set(o.get('input_columns', [])) <= cols:
            e.append('Task uses fabricated input column')
        if not set(o.get('depends_on', [])) <= ids or o.get('id') in ancestors.get(o.get('id'), set()):
            e.append('Invalid/cyclic task dependencies')
        for a in o.get('input_artifacts', []):
            if a not in owners or owners[a] not in ancestors.get(o.get('id'), set()):
                e.append('Input artifact must be produced by a dependency')
        if not o.get('outputs') or not o.get('reason'):
            e.append('Operation outputs and reason required')
    return e

def bootstrap(out, base, replay):
    names = ['selection.json', 'data_features.json', 'research_context.json', 'column_ranking.json', 'semantic_index.json', 'model_metadata.json', 'retrieval_queries.json']
    paths = names + ['inputs/knowledge_graph.json', 'inputs/sources.json']
    frozen = {name: s.sha(base / name) for name in paths + ['semantic_retrieval.json']}
    record = {'version': standard()['version'], 'baseline_directory': base.name, 'frozen_inputs': frozen, 'old_candidate_method_ids': sorted({c['method_id'] for q in read(base / 'semantic_retrieval.json')['queries'] for c in q['candidates']})}
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'baseline.json').exists() and read(out / 'baseline.json') != record:
        raise ValueError('Frozen baseline changed; use a new output directory')
    save(out / 'baseline.json', record)
    for name in paths:
        dest = out / name
        if dest.exists():
            if s.sha(dest) != frozen[name]:
                raise ValueError('Local frozen input changed: ' + name)
        elif replay:
            raise ValueError('Replay input missing: ' + name)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(base / name, dest)
    if not (out / 'legacy_retrieval.json').exists():
        if replay:
            raise ValueError('Missing legacy retrieval')
        shutil.copy2(base / 'semantic_retrieval.json', out / 'legacy_retrieval.json')
    if s.sha(out / 'legacy_retrieval.json') != frozen['semantic_retrieval.json']:
        raise ValueError('Legacy retrieval changed')
    original_graph = ROOT.parent / 'DAG_20papers_20261023/\u5c55\u793a\u6570\u636e\u5feb\u7167.json'
    if original_graph.exists() and s.sha(original_graph) != read(out / 'selection.json')['frozen_graph_sha256']:
        raise ValueError('Original twenty-paper graph changed')
    return record

def ask(name, material, validator, out, replay):
    contract = TASK_CONTRACT if name == 'task_understanding' else REVIEW_CONTRACT if name == 'graph_review' else read(ROOT / 'contracts/task_graph.json')['target_graph' if name == 'reviewed_graph' else name]
    instruction = (ROOT / 'instructions' / (name + '.txt')).read_text(encoding='utf-8')
    cfg = read(ROOT / 'config_high.json')
    cfg['max_structural_repairs'] = 3
    return model_runner.run_json(name, instruction, standard(), contract, material, cfg, out, validator, replay)

def retrieval_errors(x, task, index, second=False):
    e = require(x, ['operations', 'limitations'], 'retrieval')
    rows = x.get('operations', [])
    if not unique(rows, 'operation_id', [o['id'] for o in task['operations']]):
        e.append('Every operation exactly once')
    mids = {m['method_id'] for m in index['methods']}
    for row in rows:
        cs = row.get('candidates', [])
        if len(cs) > (8 if second else 4) or not unique(cs, 'method_id'):
            e.append('Candidate limit or duplicate')
        if second and row.get('whole_catalog_searched') is not True:
            e.append('operations[' + str(row.get('operation_id')) + '] is missing whole_catalog_searched=true. Re-scan the complete supplied method index for THIS operation and include this Boolean at the operation object level, outside candidates. Every operation, including those with candidates, needs this field.')
        for c in cs:
            e += require(c, ['method_id', 'component_refs', 'data_semantic_fit', 'task_fit', 'applicability', 'conditions', 'reason'], 'candidate')
            if c.get('method_id') not in mids:
                e.append('Unknown catalog Method')
            if c.get('applicability') not in ['candidate', 'conditional', 'not_applicable', 'unknown']:
                e.append('Invalid applicability')
            if not c.get('component_refs'):
                e.append('Candidate source component references required')
            for ref in c.get('component_refs', []):
                if index['components'].get(ref, {}).get('method_id') != c.get('method_id'):
                    e.append('Component does not belong to Method')
    return e

def screening_errors(x, mids, task, index):
    e = require(x, ['candidates', 'operation_coverage', 'gaps', 'limitations'], 'screening')
    rows = x.get('candidates', [])
    ops = {o['id'] for o in task['operations']}
    if not unique(rows, 'method_id', mids):
        e.append('Every union candidate including every frozen baseline candidate must occur exactly once')
    for r in rows:
        e += require(r, ['operation_ids', 'criteria', 'status', 'component_refs', 'reason', 'unresolved'], 'screened candidate')
        if r.get('status') not in ['accept', 'conditional', 'reject', 'unknown']:
            e.append('Invalid screening status')
        if not set(r.get('operation_ids', [])) <= ops:
            e.append('Unknown screened operation')
        for k in ['task_fit', 'data_semantics', 'input_granularity', 'mechanism_and_assumptions', 'parameters', 'target_compatibility']:
            if not nonempty(r.get('criteria', {}).get(k)):
                e.append('Screening criterion missing: ' + k)
        for ref in r.get('component_refs', []):
            if index['components'].get(ref, {}).get('method_id') != r.get('method_id'):
                e.append('Screening source mismatch')
    cov = x.get('operation_coverage', [])
    if not unique(cov, 'operation_id', ops):
        e.append('Coverage must account for each task operation')
    by = {r['method_id']: r for r in rows}
    for c in cov:
        if c.get('status') not in ['covered', 'conditional', 'gap', 'not_applicable'] or not c.get('reason'):
            e.append('Invalid coverage status/reason')
        for mid in c.get('usable_method_ids', []):
            r = by.get(mid, {})
            if r.get('status') not in ['accept', 'conditional'] or c['operation_id'] not in r.get('operation_ids', []):
                e.append('Coverage references rejected/unknown/unrelated method')
        if c.get('status') in ['covered', 'conditional'] and (not c.get('usable_method_ids')):
            e.append('Method coverage requires usable methods')
    if not unique(x.get('gaps', []), 'id'):
        e.append('Unique gap IDs')
    for g in x.get('gaps', []):
        if g.get('operation_id') not in ops or g.get('kind') not in ['missing_operation', 'no_applicable_method', 'no_compatible_alternative']:
            e.append('Invalid gap')
        if not g.get('reason') or not set(g.get('searched_method_ids', [])) <= set(mids):
            e.append('Gap reason/references required')
    return e

def graph_errors(x, task, screen, ranking, index, graph, sources):
    e = require(x, ['title', 'executed', 'target', 'steps', 'interchangeability', 'constraints', 'operation_coverage', 'limitations'], 'graph') + s.quote_errors(x, sources)
    if x.get('executed') is not False:
        e.append('executed must be false')
    steps = x.get('steps', [])
    ids = {r.get('id') for r in steps}
    opmap = {o['id']: o for o in task['operations']}
    cols = {c['column_id'] for c in ranking['columns']}
    artifacts = {a['artifact_id']: o['id'] for o in task['operations'] for a in o['outputs']}
    gaps = {g['id']: g for g in screen['gaps']}
    eligible = {r['method_id']: r for r in screen['candidates'] if r['status'] in ['accept', 'conditional']}
    if not steps or not unique(steps, 'id'):
        e.append('Unique nonempty steps')
    ancestors = {r['id']: set(r.get('depends_on', [])) for r in steps}
    for _ in steps:
        for k in ancestors:
            ancestors[k] |= set().union(*(ancestors.get(v, set()) for v in list(ancestors[k]))) if ancestors[k] else set()
    owners = {a: r['id'] for r in steps for a in r.get('output_artifacts', [])}
    alloids = []
    for st in steps:
        sid = st.get('id')
        opid = st.get('operation_id')
        e += require(st, ['operation_id', 'kind', 'label', 'depends_on', 'input_artifacts', 'output_artifacts', 'status', 'reason', 'options'], 'step')
        if not re.fullmatch('[A-Za-z][A-Za-z0-9_]*', str(sid)):
            e.append('Boba-safe step ID required')
        if opid not in opmap or st.get('kind') not in ['fixed', 'decision', 'unresolved']:
            e.append('Unknown operation/kind')
        if not set(st.get('depends_on', [])) <= ids or sid in ancestors.get(sid, set()):
            e.append('Execution dependencies invalid/cyclic')
        for a in st.get('input_artifacts', []):
            if a not in artifacts or owners.get(a) not in ancestors.get(sid, set()):
                e.append('Step derived input lacks producer dependency: ' + str(a))
        for a in st.get('output_artifacts', []):
            if artifacts.get(a) != opid:
                e.append('Step output artifact not declared by corresponding task')
        options = st.get('options', [])
        if st.get('kind') == 'decision' and len(options) < 2:
            e.append('Decision needs at least two alternatives; otherwise fixed/unresolved')
        if st.get('kind') == 'fixed' and len(options) != 1:
            e.append('Fixed step needs one component Option')
        if st.get('status') not in ['ready_draft', 'conditional', 'blocked']:
            e.append('Invalid step draft status')
        for o in options:
            alloids.append(o.get('id'))
            origin = o.get('origin')
            method = o.get('method', {})
            e += require(o, ['id', 'label', 'origin', 'source_option_refs', 'source_evidence', 'gap_ids', 'proposal_reason', 'method', 'data_binding', 'parameters', 'components', 'status', 'assumptions', 'target_compatibility', 'limitations'], 'Option')
            if not re.fullmatch('[A-Za-z][A-Za-z0-9_]*', str(o.get('id'))):
                e.append('Boba-safe Option ID required')
            if origin not in ['existing_knowledge', 'target_reported', 'proposed']:
                e.append('Explicit Option provenance required')
            if origin == 'existing_knowledge' and (not o.get('source_option_refs')):
                e.append('Existing complete Option requires exact source refs')
            if not set(o.get('source_option_refs', [])) <= set(graph['original_options']):
                e.append('Unknown source Option')
            if origin == 'target_reported' and (not o.get('source_evidence')):
                e.append('Target reported Option requires literal evidence')
            if origin == 'proposed':
                if not o.get('gap_ids') or not o.get('proposal_reason'):
                    e.append('Proposed Option needs documented gap and reason')
                for g in o.get('gap_ids', []):
                    if g not in gaps or gaps[g]['operation_id'] != opid:
                        e.append('Proposed gap must belong to this operation')
            if o.get('status') not in ['ready_draft', 'conditional', 'blocked']:
                e.append('Invalid Option status')
            if method.get('origin') == 'existing_knowledge':
                mid = method.get('id')
                if mid not in eligible or opid not in eligible[mid]['operation_ids']:
                    e.append('Only screened usable method for this task may be applied')
                if not method.get('component_refs'):
                    e.append('Existing Method requires components')
                for ref in method.get('component_refs', []):
                    if index['components'].get(ref, {}).get('method_id') != mid:
                        e.append('Option Method component mismatch')
            elif method.get('origin') in ['target_reported', 'proposed']:
                if not str(method.get('id', '')).startswith('NEW'):
                    e.append('New Method IDs must start NEW, do not mutate frozen M')
            else:
                e.append('Explicit Method provenance required')
            if not o.get('data_binding') or not o.get('parameters') or (not o.get('components')):
                e.append('Option three-part components must be present')
            for b in o.get('data_binding', []):
                if bool(b.get('column_id')) == bool(b.get('artifact_id')):
                    e.append('Binding must select one real column OR derived artifact')
                if b.get('column_id') and b['column_id'] not in cols:
                    e.append('Invented measured column')
                if b.get('artifact_id') and (b['artifact_id'] not in artifacts or owners.get(b['artifact_id']) not in ancestors.get(sid, set())):
                    e.append('Undeclared or non-ancestor derived binding')
                if not b.get('meaning') or not b.get('role'):
                    e.append('Binding semantic/role required')
            for p in o.get('parameters', []):
                if p.get('status') not in ['target_supported', 'proposed', 'unknown', 'source_only', 'not_applicable'] or not p.get('name') or 'value' not in p or (not p.get('reason')):
                    e.append('Explicit parameter value/status/reason required')
    if len(alloids) != len(set(alloids)):
        e.append('Globally unique Option IDs required')
    decisions = {r['id']: r for r in steps if r['kind'] == 'decision'}
    ix = x.get('interchangeability', [])
    if not unique(ix, 'decision_id', decisions):
        e.append('Each Decision needs an interchangeability assessment')
    for item in ix:
        opts = {o['id'] for o in decisions.get(item.get('decision_id'), {}).get('options', [])}
        if set(item.get('option_ids', [])) != opts or item.get('status') not in ['compatible', 'conditional', 'incompatible'] or (not item.get('reason')):
            e.append('Interchangeability must account for every alternative')
        if item.get('status') == 'incompatible':
            e.append('Incompatible targets cannot be alternatives in one Decision; separate or block')
    cov = x.get('operation_coverage', [])
    if not unique(cov, 'operation_id', opmap):
        e.append('Graph must account for every required/optional operation')
    for c in cov:
        if not set(c.get('step_ids', [])) <= ids:
            e.append('Coverage references unknown step')
        if c.get('status') in ['covered', 'conditional'] and (not c.get('step_ids')):
            e.append('Covered operation requires step')
        if c.get('status') == 'covered' and any((next((st for st in steps if st['id'] == sid))['status'] == 'blocked' for sid in c.get('step_ids', []) if sid in ids)):
            e.append('Blocked step cannot claim covered executable operation')
        for sid in c.get('step_ids', []):
            if next((st for st in steps if st['id'] == sid))['operation_id'] != c['operation_id']:
                e.append('Coverage step belongs to wrong operation')
    for c in x.get('constraints', []):
        if not c.get('reason') or not c.get('forbidden_choices'):
            e.append('Constraint reason and choices required')
        for sid, oid in c.get('forbidden_choices', {}).items():
            if sid not in decisions or oid not in {o['id'] for o in decisions[sid]['options']}:
                e.append('Constraint references unknown Decision/Option')
    return e

def ordered_steps(graph):
    remaining = list(graph['steps'])
    done = []
    result = []
    while remaining:
        ready = [r for r in remaining if set(r['depends_on']) <= set(done)]
        if not ready:
            raise ValueError('No acyclic executable block order')
        for r in ready:
            result.append(r)
            done.append(r['id'])
            remaining.remove(r)
    return result

def choice_errors(choices, graph):
    ds = {r['id']: r for r in graph['steps'] if r['kind'] == 'decision'}
    e = []
    if set(choices) != set(ds):
        e.append('Each specification must select every Decision exactly once')
    for sid, oid in choices.items():
        if sid not in ds or oid not in {o['id'] for o in ds[sid]['options']}:
            e.append('Unknown specification choice')
    for c in graph['constraints']:
        if all((choices.get(k) == v for k, v in c['forbidden_choices'].items())):
            e.append('Specification violates forbidden combination')
    return e

def execution_graph(blueprint, graph):
    ids = set(blueprint.get('execution_step_ids', [st['id'] for st in graph['steps']]))
    return {**graph, 'steps': [st for st in graph['steps'] if st['id'] in ids], 'constraints': [c for c in graph['constraints'] if set(c['forbidden_choices']) <= ids]}

def blueprint_errors(x, graph):
    e = require(x, ['language', 'executed', 'execution_step_ids', 'deferred_steps', 'template_status', 'setup_code', 'step_code', 'output_code', 'specifications', 'dependencies', 'parameter_audit', 'limitations'], 'blueprint')
    if x.get('language') != 'python' or x.get('executed') is not False:
        e.append('Python draft only; executed=false')
    all_steps = {st['id']: st for st in graph['steps']}
    included = x.get('execution_step_ids', [])
    deferred = x.get('deferred_steps', [])
    if len(included) != len(set(included)) or not set(included) <= set(all_steps):
        e.append('Execution scope must list unique graph step IDs')
    if not unique(deferred, 'step_id', set(all_steps) - set(included)):
        e.append('Every omitted graph step needs an explicit deferred explanation')
    for st in graph['steps']:
        if st['id'] in included and (not st['options'] or not set(st['depends_on']) <= set(included)):
            e.append('Included code step needs Options and all producer dependencies included')
    for item in deferred:
        if not item.get('reason') or type(item.get('prevents_h1_analysis')) is not bool:
            e.append('Deferred reason and H1-blocking flag required')
    if x.get('template_status') not in ['conditional', 'blocked']:
        e.append('Untested template can only be conditional or blocked')
    if any((item.get('prevents_h1_analysis') for item in deferred)) and x.get('template_status') != 'blocked':
        e.append('Missing necessary H1 operation must block template')
    graph = execution_graph(x, graph)
    steps = {r['id']: r for r in graph['steps']}
    rows = x.get('step_code', [])
    if not unique(rows, 'step_id', steps):
        e.append('Every graph step code exactly once')
    bodies = {}
    for row in rows:
        sid = row['step_id']
        expected = {o['id'] for o in steps.get(sid, {}).get('options', [])}
        if not unique(row.get('options', []), 'option_id', expected):
            e.append('Every graph Option code exactly once')
        for o in row.get('options', []):
            if not nonempty(o.get('code')) or '{{' in o.get('code', '') or '# ---' in o.get('code', ''):
                e.append('Python body only, no Boba markers/placeholders')
            bodies[sid, o['option_id']] = o.get('code', '')
    specs = x.get('specifications', [])
    if not 2 <= len(specs) <= 3 or not unique(specs, 'id'):
        e.append('Two or three unique pilot specifications required')
    if len({json.dumps(r.get('choices', {}), sort_keys=True) for r in specs}) != len(specs):
        e.append('Pilot specifications must differ')
    for sp in specs:
        e += choice_errors(sp.get('choices', {}), graph)
    expected = {(sid, o['id']) for sid, st in steps.items() for o in st['options']}
    audit = x.get('parameter_audit', [])
    pairs = [(r.get('step_id'), r.get('option_id')) for r in audit]
    if len(pairs) != len(set(pairs)) or set(pairs) != expected:
        e.append('Parameter audit exactly once for every Option')
    for r in audit:
        if not r.get('arguments') or 'unresolved' not in r:
            e.append('Explicit argument audit required')
    try:
        ast.parse(x.get('setup_code', ''))
        ast.parse(x.get('output_code', ''))
        for code in bodies.values():
            ast.parse(code)
        for sp in specs:
            code = x.get('setup_code', '') + '\n' + '\n'.join((bodies[st['id'], sp['choices'][st['id']] if st['kind'] == 'decision' else st['options'][0]['id']] for st in ordered_steps(graph) if st.get('options'))) + '\n' + x.get('output_code', '')
            ast.parse(code)
    except (SyntaxError, KeyError, IndexError, ValueError) as exc:
        e.append('Generated Python syntax/reference: ' + str(exc))
    return e

def review_errors(x, graph):
    e = require(x, ['issues', 'overall', 'limitations'], 'graph review')
    ids = {r['id'] for r in graph['steps']}
    if not unique(x.get('issues', []), 'id'):
        e.append('Unique issue IDs required')
    for r in x.get('issues', []):
        if r.get('severity') not in ['major', 'minor'] or not set(r.get('step_ids', [])) <= ids:
            e.append('Invalid issue severity/step reference')
        if not r.get('reason') or not r.get('recommendation') or (not r.get('evidence')):
            e.append('Issue evidence/reason/recommendation required')
    return e

def render_boba(out, graph, blueprint):
    graph = execution_graph(blueprint, graph)
    steps = ordered_steps(graph)
    by = {r['step_id']: {o['option_id']: o['code'] for o in r['options']} for r in blueprint['step_code']}
    order = ['Setup'] + [r['id'] for r in steps] + ['Output']
    constraints = []
    position = {r['id']: i for i, r in enumerate(steps)}
    for c in graph['constraints']:
        choices = c['forbidden_choices']
        latest = max(choices, key=lambda k: position[k])
        other = {k: v for k, v in choices.items() if k != latest}
        condition = ' or '.join((k + ' != ' + v for k, v in other.items())) or '1 == 0'
        constraints.append({'block': latest, 'option': choices[latest], 'condition': condition})
    decisions = [st for st in steps if st['kind'] == 'decision']
    if decisions:
        last = decisions[-1]['id']
        previous = [st['id'] for st in decisions[:-1]]
        total = 1
        for st in decisions:
            total *= len(st['options'])
        if len(blueprint['specifications']) < total:
            for opt in decisions[-1]['options']:
                matching = [sp for sp in blueprint['specifications'] if sp['choices'][last] == opt['id']]
                expressions = ['(' + ' and '.join((k + ' == ' + sp['choices'][k] for k in previous)) + ')' for sp in matching] if previous else []
                condition = ' or '.join(expressions) if expressions else '1 == 1' if matching else '1 == 0'
                constraints.append({'block': last, 'option': opt['id'], 'condition': condition})
    config = {'graph': ['->'.join(order)], 'constraints': constraints}
    guard = "raise RuntimeError('Template blocked: unresolved required H1 operations; see boba_blueprint.json')\n" if blueprint.get('template_status') == 'blocked' else ''
    chunks = ['# --- (BOBA_CONFIG)\n' + json.dumps(config, ensure_ascii=False, indent=2), '# --- (Setup)\n# DRAFT ONLY: generated by DeepSeek; not run or statistically certified.\n' + guard + blueprint['setup_code']]
    for st in steps:
        for opt in st['options']:
            marker = '# --- (' + st['id'] + ')' + (' ' + opt['id'] if st['kind'] == 'decision' else '')
            chunks.append(marker + '\n# Option ' + opt['id'] + ' | origin=' + opt['origin'] + ' | method_origin=' + opt['method']['origin'] + '\n' + by[st['id']][opt['id']])
    chunks.append('# --- (Output)\n' + blueprint['output_code'])
    (out / 'boba_template.py').write_text('\n\n'.join(chunks) + '\n', encoding='utf-8')
    save(out / 'boba_config.json', config)
    save(out / 'pilot_specifications.json', blueprint['specifications'])
    dest = out / 'syntax_only'
    dest.mkdir(exist_ok=True)
    for sp in blueprint['specifications']:
        code = '# SYNTAX-ONLY DRAFT, NOT EXECUTED\n' + blueprint['setup_code'] + '\n' + '\n'.join((by[st['id']][sp['choices'][st['id']] if st['kind'] == 'decision' else st['options'][0]['id']] for st in steps)) + '\n' + blueprint['output_code']
        ast.parse(code)
        (dest / (sp['id'] + '.py')).write_text(code, encoding='utf-8')

def remaining(out, common, task, sources, index, graph, baseline, replay, stage):
    queries = read(out / 'retrieval_queries.json')['columns']
    material = {**common, 'task': task, 'query_columns': queries, 'existing_method_index': index['methods']}
    first = ask('column_task_retrieval', material, lambda x: retrieval_errors(x, task, index), out, replay)
    second = ask('operation_retrieval', {**material, 'round1': first}, lambda x: retrieval_errors(x, task, index, True), out, replay)
    if stage == 'retrieve':
        return
    mids = sorted(set(baseline['old_candidate_method_ids']) | {c['method_id'] for r in [first, second] for op in r['operations'] for c in op['candidates']})
    candidate_methods = [m for m in index['methods'] if m['method_id'] in mids]
    refs = {ref for m in candidate_methods for ref in m['component_refs']}
    components = {ref: index['components'][ref] for ref in sorted(refs)}
    screenmat = {**common, 'task': task, 'round1': first, 'round2': second, 'legacy_retrieval': read(out / 'legacy_retrieval.json'), 'candidate_method_ids': mids, 'methods': candidate_methods, 'historical_components': components}
    screen = ask('candidate_screening', screenmat, lambda x: screening_errors(x, mids, task, index), out, replay)
    if stage == 'screen':
        return
    eligible = {r['method_id'] for r in screen['candidates'] if r['status'] in ['accept', 'conditional']}
    eligible_refs = {ref for m in candidate_methods if m['method_id'] in eligible for ref in m['component_refs']}
    source_refs = {index['components'][ref]['source_ref'] for ref in eligible_refs}
    graphmat = {**common, 'task': task, 'screening': screen, 'sources': sources, 'usable_methods': [m for m in candidate_methods if m['method_id'] in eligible], 'historical_options': {ref: graph['original_options'][ref] for ref in sorted(source_refs)}, 'historical_components': {ref: graph['enriched_components'][ref] for ref in sorted(eligible_refs)}}
    target = ask('target_graph', graphmat, lambda x: graph_errors(x, task, screen, common['column_ranking'], index, graph, sources), out, replay)
    review = ask('graph_review', {**graphmat, 'target_graph': target}, lambda x: review_errors(x, target), out, replay)
    active = 'target_graph.json'
    if review['issues']:
        target = ask('reviewed_graph', {**graphmat, 'previous_graph': target, 'automatic_review': review}, lambda x: graph_errors(x, task, screen, common['column_ranking'], index, graph, sources), out, replay)
        active = 'reviewed_graph.json'
    save(out / 'active_graph.json', {'file': active, 'scientific_revision': 'DeepSeek automatic evidence review; no developer scientific edits'})
    if stage == 'graph':
        return
    blueprint = ask('boba_blueprint', {**common, 'task': task, 'target_graph': target}, lambda x: blueprint_errors(x, target), out, replay)
    render_boba(out, target, blueprint)
    report = {'all_structural_checks_passed': True, 'baseline_unchanged': True, 'frozen_twenty_unchanged': s.sha(out / 'inputs/knowledge_graph.json') == read(out / 'selection.json')['frozen_graph_sha256'], 'operations': len(task['operations']), 'legacy_candidates': len(baseline['old_candidate_method_ids']), 'screened_candidates': len(mids), 'screening_counts': {k: sum((r['status'] == k for r in screen['candidates'])) for k in ['accept', 'conditional', 'reject', 'unknown']}, 'steps': len(target['steps']), 'decisions': sum((st['kind'] == 'decision' for st in target['steps'])), 'options': sum((len(st['options']) for st in target['steps'])), 'option_provenance': {k: sum((o['origin'] == k for st in target['steps'] for o in st['options'])) for k in ['existing_knowledge', 'target_reported', 'proposed']}, 'used_existing_method_ids': sorted({o['method']['id'] for st in target['steps'] for o in st['options'] if o['method']['origin'] == 'existing_knowledge'}), 'unresolved_steps': sum((st['kind'] == 'unresolved' for st in target['steps'])), 'automatic_review_issues': len(review['issues']), 'specifications': len(blueprint['specifications']), 'boba_template_generated': True, 'python_syntax_checked': True, 'analysis_executed': False, 'curve_generated': False, 'scientific_accuracy_certified': False}
    if not report['frozen_twenty_unchanged']:
        raise ValueError('Frozen graph changed')
    save(out / 'verification.json', report)
    import task_graph_view
    task_graph_view.build(out)

def run(out=DEFAULT, base=BASE, replay=False, stage='all'):
    baseline = bootstrap(out, base, replay)
    context = read(out / 'research_context.json')
    ranking = read(out / 'column_ranking.json')
    features = read(out / 'data_features.json')
    dataset = next((d for d in features['datasets'] if d['dataset_id'] == context['dataset_choice']['dataset_id']))
    sources = read(out / 'inputs/sources.json')['sources']
    index = read(out / 'semantic_index.json')
    graph = read(out / 'inputs/knowledge_graph.json')
    common = {'research_context': context, 'dataset': dataset, 'column_ranking': ranking}
    task = ask('task_understanding', {**common, 'sources': sources}, lambda x: task_errors(x, ranking, sources), out, replay)
    if stage == 'task':
        return
    return remaining(out, common, task, sources, index, graph, baseline, replay, stage)
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=DEFAULT)
    p.add_argument('--baseline', type=Path, default=BASE)
    p.add_argument('--replay', action='store_true')
    p.add_argument('--stage', choices=['task', 'retrieve', 'screen', 'graph', 'all'], default='all')
    a = p.parse_args()
    run(a.output.resolve(), a.baseline.resolve(), a.replay, a.stage)
