# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Frozen-catalog Method reuse/adaptation first; no executable component library or analysis."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import lab
import model_runner
import semantic_stitch as s
import task_graph as t
ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT.parent / 'Method_Reuse_Adapt_20261024'
BASE = t.BASE
PREVIOUS = t.DEFAULT

def read(p):
    return lab.read(p)

def save(p, x):
    lab.save(p, x)

def standard():
    return read(ROOT / 'standards/method_reuse_v2.json')

def ask(stage, material, validator, out, replay):
    contract = t.TASK_CONTRACT if stage == 'priority_task' else read(ROOT / 'contracts/method_reuse_v2.json')[stage]
    cfg = read(ROOT / 'config_high.json')
    cfg['max_structural_repairs'] = 2
    return model_runner.run_json(stage, (ROOT / 'instructions' / (stage + '.txt')).read_text('utf-8'), standard(), contract, material, cfg, out, validator, replay)

def prepare(out, base, previous, replay):
    baseline = t.bootstrap(out, base, replay)
    if (out / 'previous_candidates.json').exists():
        old = read(out / 'previous_candidates.json')
    elif replay:
        raise ValueError('Frozen prior candidate list missing')
    else:
        old = {'method_ids': sorted((r['method_id'] for r in read(previous / 'candidate_screening.json')['candidates'])), 'prior_result_sha256': s.sha(previous / 'verification.json'), 'prior_output': previous.name}
        save(out / 'previous_candidates.json', old)
    manifest = {'policy': standard()['version'], 'baseline': baseline, 'previous_candidates': old, 'no_executable_component_library': True}
    if (out / 'priority_settings.json').exists() and read(out / 'priority_settings.json') != manifest:
        raise ValueError('Frozen priority inputs changed; use a new directory')
    save(out / 'priority_settings.json', manifest)
    return old

def core_basis(graph, index):
    rows = []
    for r in graph['classification']['rows']:
        for comp in r['components']:
            ref = r['source_ref'] + '/' + comp['id']
            en = graph['enriched_components'][ref]
            rows.append({'component_ref': ref, 'method_id': comp['method_id'], 'scientific_function': comp['scientific_function'], 'operation_object': comp['operation_object'], 'mechanism': comp['mechanism'], 'applicability_conditions': comp['applicability_conditions'], 'source_parameters': en['parameters'], 'column_semantics': [{k: col.get(k) for k in ['name', 'role', 'meaning']} for col in index['components'][ref]['columns']]})
    return rows

def strings(x):
    if isinstance(x, str):
        return [x]
    if isinstance(x, dict):
        return [s for v in x.values() for s in strings(v)]
    if isinstance(x, list):
        return [s for v in x for s in strings(v)]
    return []

def audit_errors(x, task, index, basis, previous):
    e = t.require(x, ['candidates', 'operation_checks', 'limitations'], 'reuse audit')
    rows = x.get('candidates', [])
    mids = {m['method_id'] for m in index['methods']}
    by = {r.get('method_id'): r for r in rows}
    ops = {o['id'] for o in task['operations']}
    if not t.unique(rows, 'method_id') or not set(previous) <= set(by) or (not set(by) <= mids):
        e.append('Every frozen prior candidate exactly once; additional candidates must be real M IDs')
    bank = {m['method_id']: m for m in index['methods']}
    bank.update({r['component_ref']: r for r in basis})
    for row in rows:
        mid = row.get('method_id')
        core = row.get('method_core', {})
        e += t.require(row, ['component_refs', 'method_core', 'operation_assessments', 'reason'], 'candidate')
        if not core.get('definition') or not core.get('invariants') or 'source_context' not in core or (not core.get('evidence')):
            e.append('Core, invariants, separable context and literal record evidence required: ' + str(mid))
        for ev in core.get('evidence', []):
            key = ev.get('record_id')
            record = bank.get(key)
            quote = ev.get('quote', '')
            if record is None or (key != mid and record.get('method_id') != mid):
                e.append('Core evidence record must belong to source M')
            elif not quote or not any((' '.join(quote.split()) in ' '.join(v.split()) for v in strings(record))):
                e.append('Core evidence quote not found in record ' + str(key))
        for ref in row.get('component_refs', []):
            if index['components'].get(ref, {}).get('method_id') != mid:
                e.append('Source component/M mismatch')
        assessments = row.get('operation_assessments', [])
        if not t.unique(assessments, 'operation_id'):
            e.append('At most one assessment per M/operation')
        for a in assessments:
            e += t.require(a, ['operation_id', 'mode', 'status', 'coverage', 'capability', 'core_preserved', 'changes', 'reason', 'unresolved'], 'assessment')
            if a.get('operation_id') not in ops or a.get('mode') not in ['reused', 'adapted', 'unavailable', 'unknown']:
                e.append('Unknown assessment operation/mode')
            if a.get('status') not in ['eligible', 'conditional', 'not_applicable', 'unknown'] or a.get('coverage') not in ['complete', 'partial']:
                e.append('Assessment applicability/coverage invalid')
            if a.get('mode') in ['reused', 'adapted']:
                if a.get('core_preserved') is not True or a.get('status') not in ['eligible', 'conditional']:
                    e.append('Reuse/adaptation needs explicitly preserved core and eligibility')
                if a.get('mode') == 'adapted' and (not a.get('changes')):
                    e.append('Adaptation must specify source-to-target changes')
    checks = x.get('operation_checks', [])
    if not t.unique(checks, 'operation_id', ops):
        e.append('Priority checks cover every task operation exactly once')
    gaps = []
    for c in checks:
        if c.get('whole_catalog_reviewed') is not True or not c.get('priority_reason'):
            e.append('Whole-catalog review and priority explanation required')
        for mode in ['reused', 'adapted']:
            wanted = {mid for mid, r in by.items() for a in r.get('operation_assessments', []) if a['operation_id'] == c['operation_id'] and a['mode'] == mode}
            if set(c.get(mode + '_method_ids', [])) != wanted:
                e.append('Priority usable M list must match detailed assessments: ' + c['operation_id'] + ' ' + mode)
        for g in c.get('gaps', []):
            gaps.append(g.get('id'))
            if not all((g.get(k) for k in ['id', 'capability', 'reused_check', 'adapted_check', 'reason'])):
                e.append('A gap needs explicit failed reuse AND adaptation checks')
    if len(gaps) != len(set(gaps)):
        e.append('Globally unique gap IDs required')
    return e

def plan_errors(x, task, audit, ranking, index):
    e = t.require(x, ['title', 'executed', 'target', 'steps', 'interchangeability', 'constraints', 'operation_coverage', 'limitations'], 'plan')
    if x.get('executed') is not False:
        e.append('No analysis execution')
    rows = x.get('steps', [])
    ids = {r.get('id') for r in rows}
    ops = {o['id'] for o in task['operations']}
    colids = {c['column_id'] for c in ranking['columns']}
    am = {r['method_id']: r for r in audit['candidates']}
    gapmap = {g['id']: (c['operation_id'], g) for c in audit['operation_checks'] for g in c.get('gaps', [])}
    artifacts = {a['artifact_id']: o['id'] for o in task['operations'] for a in o['outputs']}
    if not rows or not t.unique(rows, 'id'):
        e.append('Nonempty unique graph steps required')
    ancestors = {r['id']: set(r.get('depends_on', [])) for r in rows}
    for _ in rows:
        for k in ancestors:
            ancestors[k] |= set().union(*(ancestors.get(v, set()) for v in list(ancestors[k]))) if ancestors[k] else set()
    owners = {a: r['id'] for r in rows for a in r.get('output_artifacts', [])}
    oids = []
    for st in rows:
        e += t.require(st, ['operation_id', 'kind', 'operation_kind', 'label', 'depends_on', 'input_artifacts', 'output_artifacts', 'status', 'reason', 'options'], 'step')
        sid = st['id']
        opid = st.get('operation_id')
        if opid not in ops or not set(st.get('depends_on', [])) <= ids or sid in ancestors[sid]:
            e.append('Invalid operation or dependency cycle')
        if st.get('kind') not in ['fixed', 'decision', 'unresolved'] or st.get('operation_kind') not in ['data_preparation', 'statistical_method', 'result_output', 'diagnostic']:
            e.append('Unknown step/operation kind')
        if st.get('kind') == 'decision' and len(st.get('options', [])) < 2:
            e.append('Decision requires genuine alternatives, otherwise fixed')
        if st.get('kind') == 'fixed' and len(st.get('options', [])) != 1:
            e.append('Fixed operation requires one Option')
        for a in st.get('input_artifacts', []):
            if a not in artifacts or owners.get(a) not in ancestors[sid]:
                e.append('Artifact input lacks declared producer dependency')
        for a in st.get('output_artifacts', []):
            if artifacts.get(a) != opid:
                e.append('Output artifact must belong to task operation')
        for o in st.get('options', []):
            oids.append(o.get('id'))
            mode = o.get('reuse_mode')
            m = o.get('method', {})
            mid = m.get('id')
            e += t.require(o, ['id', 'label', 'origin', 'reuse_mode', 'capability', 'method', 'core_invariants', 'adaptation_changes', 'gap_ids', 'priority_reason', 'data_binding', 'parameters', 'components', 'status', 'assumptions', 'target_compatibility', 'limitations'], 'Option')
            if o.get('origin') != 'proposed':
                e.append('New target configuration must remain explicitly model-configured/proposed; method mode is separate')
            if mode in ['reused', 'adapted']:
                if mid not in am or m.get('origin') != 'existing_knowledge':
                    e.append('Reused/adapted method must retain real catalog M')
                else:
                    assessment = next((a for a in am[mid]['operation_assessments'] if a['operation_id'] == opid and a['mode'] == mode), None)
                    if not assessment:
                        e.append('Plan used M/mode not authorized by this operation audit')
                    if o.get('core_invariants') != am[mid]['method_core']['invariants']:
                        e.append('Core invariants cannot change after audit: ' + str(mid))
                if mode == 'adapted' and (not o.get('adaptation_changes')):
                    e.append('Adapted Option needs explicit data/parameter/context changes')
                if not m.get('component_refs'):
                    e.append('Source Method components required')
                for ref in m.get('component_refs', []):
                    if index['components'].get(ref, {}).get('method_id') != mid:
                        e.append('Source Method/component mismatch')
            elif mode == 'proposed':
                if m.get('origin') != 'proposed' or not str(mid).startswith('NEW'):
                    e.append('Proposed method must use a new ID, not a disguised catalog M')
                if st.get('operation_kind') in ['statistical_method', 'diagnostic'] and (not o.get('gap_ids')):
                    e.append('New scientific method forbidden without two-level gap check: ' + sid + '/' + str(o.get('id')))
                for gid in o.get('gap_ids', []):
                    if gid not in gapmap or gapmap[gid][0] != opid:
                        e.append('Proposed gap must belong to this operation')
            else:
                e.append('Only reused/adapted/proposed method modes allowed')
            if not o.get('core_invariants') or not o.get('priority_reason'):
                e.append('Method core and priority justification required')
            if not o.get('data_binding') or not o.get('parameters') or (not o.get('components')):
                e.append('Method/data/parameter components must be complete')
            for b in o.get('data_binding', []):
                if bool(b.get('column_id')) == bool(b.get('artifact_id')):
                    e.append('Bind exactly one real column OR declared artifact, not both: ' + sid + '/' + str(o.get('id')))
                if b.get('column_id') and b['column_id'] not in colids:
                    e.append('Invented real column')
                if b.get('artifact_id') and (b['artifact_id'] not in artifacts or owners.get(b['artifact_id']) not in ancestors[sid]):
                    e.append('Derived binding lacks producer dependency')
                if not b.get('meaning') or not b.get('role'):
                    e.append('Binding semantics/role required')
            for p in o.get('parameters', []):
                if p.get('status') not in ['target_supported', 'proposed', 'unknown', 'source_only', 'not_applicable'] or not p.get('name') or 'value' not in p or (not p.get('reason')):
                    e.append('Explicit parameter value/status/reason required')
    if len(oids) != len(set(oids)):
        e.append('Globally unique Option IDs')
    decisions = {r['id']: r for r in rows if r['kind'] == 'decision'}
    if not t.unique(x.get('interchangeability', []), 'decision_id', decisions):
        e.append('Every Decision needs a target-compatibility check')
    for r in x.get('interchangeability', []):
        if set(r.get('option_ids', [])) != {o['id'] for o in decisions.get(r.get('decision_id'), {}).get('options', [])} or r.get('status') not in ['compatible', 'conditional'] or (not r.get('reason')):
            e.append('Incompatible or incomplete interchangeability assessment')
    if not t.unique(x.get('operation_coverage', []), 'operation_id', ops):
        e.append('Every task operation needs coverage/deferral')
    for c in x.get('operation_coverage', []):
        if not set(c.get('step_ids', [])) <= ids:
            e.append('Coverage has nonexistent step')
        for sid in c.get('step_ids', []):
            if next((r for r in rows if r['id'] == sid))['operation_id'] != c['operation_id']:
                e.append('Coverage step belongs to wrong operation')
    for c in x.get('constraints', []):
        if not c.get('forbidden_choices') or not c.get('reason'):
            e.append('Constraints need explicit forbidden choices and explanation')
        for sid, oid in c.get('forbidden_choices', {}).items():
            if sid not in decisions or oid not in {o['id'] for o in decisions[sid]['options']}:
                e.append('Unknown Decision/Option in constraints')
    return e

def lock_plan(out, plan):
    value = {'plan_file': 'frozen_plan.json', 'sha256': s.sha(out / 'frozen_plan.json'), 'scientific_content_frozen_before_code': True, 'no_catalog_modification': True}
    if (out / 'plan_lock.json').exists() and read(out / 'plan_lock.json') != value:
        raise ValueError('Frozen method plan changed; use a new output directory')
    save(out / 'plan_lock.json', value)
    return value['sha256']

def blueprint_errors(x, plan, lock):
    e = [err for err in t.blueprint_errors(x, plan) if err != 'Two or three unique pilot specifications required']
    specs = x.get('specifications', [])
    if not 1 <= len(specs) <= 3 or not t.unique(specs, 'id'):
        e.append('One to three unique specifications; do not manufacture redundant alternatives')
    if len(specs) == 1 and (not x.get('limitations')):
        e.append('A single specification needs an explicit limitation explaining lack of nonredundant alternatives')
    decision_ids = {st['id'] for st in plan['steps'] if st['kind'] == 'decision'}
    for sp in specs:
        if set(sp.get('choices', {})) != decision_ids:
            e.append('specifications[' + str(sp.get('id')) + '].choices must contain ONLY Decision IDs ' + repr(sorted(decision_ids)) + '. Fixed steps are automatic, NEVER put them in choices. When there are no Decisions, choices must be the empty object {}.')
    if 'language' not in x or 'executed' not in x:
        e.append('At the JSON ROOT explicitly include language="python" and executed=false. The type=json_object field is not a replacement for these fields.')
    if x.get('plan_sha256') != lock:
        e.append('Code must reference the immutable plan hash')
    opts = {(st['id'], o['id']): o for st in plan['steps'] for o in st['options']}
    for st in x.get('step_code', []):
        for o in st.get('options', []):
            ref = opts.get((st['step_id'], o['option_id']))
            if not ref or o.get('method_id') != ref['method']['id'] or o.get('reuse_mode') != ref['reuse_mode']:
                e.append('Code cannot add/swap/rename the frozen Method or mode')
    return e

def implementation_errors(x, plan, blueprint, lock):
    e = t.require(x, ['plan_sha256', 'checks', 'issues', 'limitations'], 'implementation review')
    if x.get('plan_sha256') != lock:
        e.append('Review must refer to frozen plan')
    bodies = {'setup_code': blueprint['setup_code'], 'output_code': blueprint['output_code']}
    expected = {}
    opts = {(st['id'], o['id']): o for st in plan['steps'] for o in st['options']}
    for st in blueprint['step_code']:
        for o in st['options']:
            bodies['step_code:' + st['step_id'] + ':' + o['option_id']] = o['code']
            expected[st['step_id'], o['option_id']] = o
    actual = [(r.get('step_id'), r.get('option_id')) for r in x.get('checks', [])]
    if len(actual) != len(set(actual)) or set(actual) != set(expected):
        e.append('Every generated Option must receive one implementation check')
    for r in x.get('checks', []):
        o = opts.get((r.get('step_id'), r.get('option_id')), {})
        mid = o.get('method', {}).get('id')
        if r.get('method_id') != mid or r.get('reuse_mode') != o.get('reuse_mode'):
            e.append('Review changed method identity')
        if r.get('status') not in ['pass', 'conditional', 'fail'] or r.get('core_preserved') not in [True, False, None]:
            e.append('Invalid review result')
        if r.get('status') in ['pass', 'conditional'] and r.get('core_preserved') is not True:
            e.append('Passing/conditional core check must explicitly preserve the core')
        if not r.get('code_evidence') or not r.get('reason'):
            e.append('Literal implementation evidence and reasoning required')
        for ev in r.get('code_evidence', []):
            code = bodies.get(ev.get('location'), '')
            quote = ev.get('quote', '')
            if not quote or quote not in code:
                e.append('Review code evidence is not a literal substring: ' + str(ev.get('location')))
    if not t.unique(x.get('issues', []), 'id'):
        e.append('Unique review issue IDs required')
    for i in x.get('issues', []):
        if (i.get('step_id'), i.get('option_id')) not in expected or i.get('severity') not in ['major', 'minor'] or (not i.get('reason')):
            e.append('Invalid implementation issue reference/severity')
    return e

def remaining(out, common, task, sources, index, graph, old, replay, stage, base=BASE):
    basis = core_basis(graph, index)
    save(out / 'method_core_basis.json', basis)
    audit = ask('reuse_audit', {**common, 'task': task, 'existing_method_index': index['methods'], 'source_component_records': basis, 'previous_candidate_ids': old['method_ids']}, lambda x: audit_errors(x, task, index, basis, old['method_ids']), out, replay)
    if stage == 'audit':
        return
    selected_refs = {ref for row in audit['candidates'] for ref in row['component_refs'] if row['operation_assessments']}
    planmat = {**common, 'task': task, 'reuse_audit': audit, 'target_sources': sources, 'source_components': [r for r in basis if r['component_ref'] in selected_refs]}
    plan = ask('frozen_plan', planmat, lambda x: plan_errors(x, task, audit, common['column_ranking'], index), out, replay)
    lock = lock_plan(out, plan)
    if stage == 'plan':
        return
    material = {**common, 'task': task, 'frozen_plan': plan, 'plan_sha256': lock, 'reuse_audit': audit, 'source_components': [r for r in basis if r['component_ref'] in selected_refs]}
    blueprint = None
    review = None
    for attempt in range(3):
        bp_material = material if attempt == 0 else {**material, 'previous_blueprint': blueprint, 'implementation_feedback': review}
        blueprint = ask('locked_blueprint', bp_material, lambda x: blueprint_errors(x, plan, lock), out, replay)
        save(out / ('blueprint_round_' + str(attempt) + '.json'), blueprint)
        review = ask('implementation_review', {**material, 'blueprint': blueprint}, lambda x: implementation_errors(x, plan, blueprint, lock), out, replay)
        save(out / ('implementation_review_round_' + str(attempt) + '.json'), review)
        if not any((r['status'] == 'fail' for r in review['checks'])) and (not any((i['severity'] == 'major' for i in review['issues']))):
            break
    render(out, plan, blueprint, lock)
    verify(out, base=base, write=True)
    import priority_view
    priority_view.build(out)

def render(out, plan, blueprint, lock):
    t.render_boba(out, plan, blueprint)
    text = (out / 'boba_template.py').read_text('utf-8')
    for st in plan['steps']:
        for o in st['options']:
            old = '# Option ' + o['id'] + ' | origin=' + o['origin'] + ' | method_origin=' + o['method']['origin']
            text = text.replace(old, old + ' | method_mode=' + o['reuse_mode'] + ' | source_method=' + o['method']['id'])
    (out / 'boba_template.py').write_text(text, encoding='utf-8')
    save(out / 'code_method_trace.json', {'plan_sha256': lock, 'options': [{'step_id': st['step_id'], 'option_id': o['option_id'], 'method_id': o['method_id'], 'reuse_mode': o['reuse_mode']} for st in blueprint['step_code'] for o in st['options']], 'meaning': 'frozen identity links plus separate DeepSeek literal-code review; not an executable component library or mathematical proof'})

def verify(out, base=BASE, write=False):
    settings = read(out / 'priority_settings.json')
    old = read(out / 'previous_candidates.json')
    task = read(out / 'priority_task.json')
    graph = read(out / 'inputs/knowledge_graph.json')
    index = read(out / 'semantic_index.json')
    sources = read(out / 'inputs/sources.json')['sources']
    ranking = read(out / 'column_ranking.json')
    audit = read(out / 'reuse_audit.json')
    plan = read(out / 'frozen_plan.json')
    bp = read(out / 'locked_blueprint.json')
    review = read(out / 'implementation_review.json')
    lock = read(out / 'plan_lock.json')['sha256']
    if s.sha(out / 'frozen_plan.json') != lock:
        raise ValueError('Frozen plan modified after code generation')
    for name, expected in settings['baseline']['frozen_inputs'].items():
        local = 'legacy_retrieval.json' if name == 'semantic_retrieval.json' else name
        if s.sha(out / local) != expected or s.sha(base / name) != expected:
            raise ValueError('Frozen baseline changed: ' + name)
    if s.sha(out / 'inputs/knowledge_graph.json') != read(out / 'selection.json')['frozen_graph_sha256']:
        raise ValueError('Frozen catalog changed')
    errors = t.task_errors(task, ranking, sources) + audit_errors(audit, task, index, read(out / 'method_core_basis.json'), old['method_ids']) + plan_errors(plan, task, audit, ranking, index) + blueprint_errors(bp, plan, lock) + implementation_errors(review, plan, bp, lock)
    if errors:
        raise ValueError(lab.dumps(errors))
    if any(((out / name).exists() for name in ['runs', 'analysis_results.json', 'specification_curve.svg'])):
        raise ValueError('Unexpected statistical execution outputs')
    opts = [o for st in plan['steps'] for o in st['options']]
    execids = set(bp['execution_step_ids'])
    executed_opts = [o for st in plan['steps'] if st['id'] in execids for o in st['options']]
    stat_opts = [o for st in plan['steps'] if st['id'] in execids and st['operation_kind'] == 'statistical_method' for o in st['options']]
    count = lambda rows: {mode: sum((o['reuse_mode'] == mode for o in rows)) for mode in ['reused', 'adapted', 'proposed']}
    report = {'structural_checks_passed': True, 'frozen_twenty_unchanged': True, 'frozen_plan_sha256': lock, 'operations': len(task['operations']), 'prior_candidates_preserved': len(old['method_ids']), 'audited_candidates': len(audit['candidates']), 'steps': len(plan['steps']), 'decisions': sum((st['kind'] == 'decision' for st in plan['steps'])), 'options': len(opts), 'graph_method_modes': count(opts), 'template_method_modes': count(executed_opts), 'template_statistical_method_modes': count(stat_opts), 'template_existing_method_ids': sorted({o['method']['id'] for o in executed_opts if o['reuse_mode'] in ['reused', 'adapted']}), 'specifications': len(bp['specifications']), 'implementation_review_passed': not any((r['status'] == 'fail' for r in review['checks'])) and (not any((i['severity'] == 'major' for i in review['issues']))), 'unresolved_steps': sum((st['kind'] == 'unresolved' for st in plan['steps'])), 'analysis_executed': False, 'curve_generated': False, 'executable_component_library_built': False, 'scientific_validity_certified': False}
    if write:
        save(out / 'verification.json', report)
    return report

def run(out=DEFAULT, base=BASE, previous=PREVIOUS, replay=False, stage='all'):
    old = prepare(out, base, previous, replay)
    ctx = read(out / 'research_context.json')
    ranking = read(out / 'column_ranking.json')
    dataset = next((d for d in read(out / 'data_features.json')['datasets'] if d['dataset_id'] == ctx['dataset_choice']['dataset_id']))
    sources = read(out / 'inputs/sources.json')['sources']
    index = read(out / 'semantic_index.json')
    graph = read(out / 'inputs/knowledge_graph.json')
    common = {'research_context': ctx, 'dataset': dataset, 'column_ranking': ranking}
    task = ask('priority_task', {**common, 'sources': sources}, lambda x: t.task_errors(x, ranking, sources), out, replay)
    if stage == 'task':
        return
    return remaining(out, common, task, sources, index, graph, old, replay, stage, base)
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=DEFAULT)
    p.add_argument('--baseline', type=Path, default=BASE)
    p.add_argument('--previous', type=Path, default=PREVIOUS)
    p.add_argument('--stage', choices=['task', 'audit', 'plan', 'all'], default='all')
    p.add_argument('--replay', action='store_true')
    a = p.parse_args()
    run(a.output.resolve(), a.baseline.resolve(), a.previous.resolve(), a.replay, a.stage)
