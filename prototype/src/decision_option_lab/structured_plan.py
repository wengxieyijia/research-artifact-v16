# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Validate source-only execution plans and enumerate pre-outcome, nonredundant paths."""
import copy
import itertools
import math
from structured_multiverse import ROOT, read, save, ask, digest, unique

def topo(steps):
    done = []
    pending = list(steps)
    while pending:
        ready = [s for s in pending if set(s.get('depends_on', [])) <= set(done)]
        if not ready:
            raise ValueError('Execution dependency cycle/missing step')
        for s in ready:
            done.append(s['id'])
            pending.remove(s)
    return done

def errors(x, ctx, task, index, review):
    e = []
    fixed = x.get('fixed_original_steps', [])
    ds = x.get('execution_decisions', [])
    groups = x.get('comparison_groups', [])
    steps = fixed + ds
    ids = {s.get('id') for s in steps}
    gids = {g.get('id') for g in groups}
    ops = {op['id'] for op in task['operations']}
    orig = {d['id']: d for d in (ctx.get('original_graph') or {}).get('decisions', [])}
    transfers = {(r['source_option_ref'], r['operation_id']): r for r in review['adaptations']}
    cols = {c['column_id'] for c in ctx['dataset']['columns']}
    if not unique(steps, 'id') or not unique(groups, 'id'):
        e.append('Unique graph steps and comparison groups required')
    try:
        topo(steps)
    except ValueError as exc:
        e.append(str(exc))
    used = set()
    pairs = set()
    for s in fixed:
        d = orig.get(s.get('target_decision_id'))
        if not d or s.get('target_option_id') not in {o['id'] for o in d['options']}:
            e.append('Fixed steps require actual original reported D/O')
        for b in s.get('data_binding', []):
            if b.get('column_id') is not None and b['column_id'] not in cols:
                e.append('Invented fixed input column')
        if any(('value' not in p or p.get('value') is None or (not p.get('basis')) for p in s.get('parameters', []))):
            e.append('Fixed scientific parameters must be explicit and grounded before freeze')
    all_instances = []
    for d in ds:
        refs = set(d.get('source_decision_refs', []))
        if not refs or not refs <= set(index['decisions']):
            e.append('No invented execution Decision: source refs required')
        if d.get('target_decision_id') is not None and d['target_decision_id'] not in orig:
            e.append('Target anchor must exist or null')
        if not d.get('options') or not unique(d['options'], 'id'):
            e.append('Nonempty unique source Option instances required')
        for o in d.get('options', []):
            key = (o.get('source_option_ref'), o.get('operation_id'))
            t = transfers.get(key)
            if key[0] not in index['options'] or index['options'][key[0]]['source_decision_ref'] not in refs:
                e.append('Option must follow a true source Decision->Option edge')
            if not t:
                e.append('Every instance must reference an actual reviewed adaptation')
            else:
                if o.get('equivalence_key') != t['equivalence_key']:
                    e.append('Do not change frozen adaptation equivalence keys')
                if o.get('status') == 'enabled' and (t['status'] != 'ready' or t['core_preserved'] is not True):
                    e.append('Only ready, core-preserving adaptations can execute')
            if o.get('status') not in ['enabled', 'conditional', 'blocked']:
                e.append('Execution option state required')
            if not set(o.get('comparison_group_ids', [])) <= gids:
                e.append('Unknown option group')
            used.add(key)
            pairs.add((d['id'], o['id']))
            all_instances.append(o)
    excluded = [(r.get('source_option_ref'), r.get('operation_id')) for r in x.get('rejected_ready_adaptations', [])]
    ready = {key for key, t in transfers.items() if t['status'] == 'ready'}
    if ready - used - set(excluded):
        e.append('Account for every ready adaptation; do not silently pick one best path: ' + str(sorted(ready - used - set(excluded))))
    if any((not r.get('reason') for r in x.get('rejected_ready_adaptations', []))):
        e.append('Every excluded ready candidate needs reason')
    dids = {d['id'] for d in ds}
    for g in groups:
        inactive = set(g.get('inactive_decision_ids', []))
        if not inactive <= dids:
            e.append('Unknown inactive Decision')
        if inactive == dids:
            e.append('A scalar comparison group requires at least one active execution Decision')
        for step in steps:
            if step['id'] not in inactive and set(step.get('depends_on', [])) & inactive:
                e.append('Active step ' + step['id'] + ' depends on inactive branch in group ' + str(g.get('id')))
        for k in ['label', 'estimand', 'population', 'analysis_unit', 'metric_id', 'effect_scale', 'direction', 'inference_scope']:
            if not g.get(k):
                e.append('Comparable group missing ' + k)
        if g.get('sample_policy') not in ['same', 'documented_variation']:
            e.append('Sample policy required')
        if type(g.get('null_value')) not in [int, float]:
            e.append('Numeric null reference required')
        if set(g.get('allowed_choices', {})) != dids:
            e.append('Each group must define allowed choices for all execution Decisions; group ' + str(g.get('id')) + ' expected=' + str(sorted(dids)) + ' returned=' + str(sorted(g.get('allowed_choices', {}))))
        for did, oids in g.get('allowed_choices', {}).items():
            if did in inactive and oids:
                e.append('Inactive group Decisions must have no scientific choices')
            if did not in inactive and (not oids):
                e.append('An active Decision requires at least one group Option; declare other branches explicitly inactive')
            for oid in oids:
                if (did, oid) not in pairs:
                    e.append('Nonexistent allowed Option')
                else:
                    o = next((o for d in ds if d['id'] == did for o in d['options'] if o['id'] == oid))
                    if o['status'] != 'enabled' or g['id'] not in o['comparison_group_ids']:
                        e.append('Group may execute enabled, group-bound Options only')
    for c in x.get('forbidden_combinations', []):
        if not c.get('choices') or not c.get('reason') or any(((d, o) not in pairs for d, o in c['choices'].items())):
            e.append('Invalid forbidden combination')
    for c in x.get('option_dependencies', []):
        if not c.get('if_choice') or not c.get('reason'):
            e.append('Conditional dependency needs trigger/reason')
        if any(((d, o) not in pairs for d, o in c.get('if_choice', {}).items())):
            e.append('Nonexistent dependency trigger')
        if any(((d, o) not in pairs for d, os in c.get('requires_choices', {}).items() for o in os)):
            e.append('Nonexistent required choice')
    original_pairs = {(d['id'], o['id']) for d in orig.values() for o in d['options']}
    st = [(r.get('decision_id'), r.get('option_id')) for r in x.get('original_option_status', [])]
    if len(st) != len(set(st)) or set(st) != original_pairs:
        e.append('Account for every immutable original Option')
    if not ds and (not x.get('gaps')):
        e.append('No executable choices requires explicit gap report')
    return e

def enumerate_specs(plan, review, limit=100, examine_limit=100000):
    ds = plan['execution_decisions']
    lookup = {(d['id'], o['id']): o for d in ds for o in d['options']}
    specs = []
    seen = set()
    examined = 0
    raw = 0
    if not ds:
        return {'raw_combinations': 0, 'examined': 0, 'valid_unique_paths': 0, 'selected_specifications': [], 'complete': True}
    for g in plan['comparison_groups']:
        inactive = set(g.get('inactive_decision_ids', []))
        active = [d for d in ds if d['id'] not in inactive]
        choicesets = [g['allowed_choices'].get(d['id'], []) for d in active]
        raw += math.prod(map(len, choicesets))
        for options in itertools.product(*choicesets):
            if examined >= examine_limit:
                break
            examined += 1
            execution_choices = {d['id']: o for d, o in zip(active, options)}
            choices = {d['id']: execution_choices.get(d['id'], d['options'][0]['id']) for d in ds}
            if any((all((execution_choices.get(k) == v for k, v in c['choices'].items())) for c in plan['forbidden_combinations'])):
                continue
            if any((all((execution_choices.get(k) == v for k, v in c['if_choice'].items())) and any((execution_choices.get(k) not in v for k, v in c['requires_choices'].items())) for c in plan['option_dependencies'])):
                continue
            signature = (g['id'], tuple(((d['id'], lookup[d['id'], execution_choices[d['id']]]['equivalence_key']) for d in active)))
            if signature in seen:
                continue
            seen.add(signature)
            specs.append({'group_id': g['id'], 'choices': choices, 'execution_choices': execution_choices, 'active_decision_ids': [d['id'] for d in active], 'inactive_decision_ids': sorted(inactive), 'signature_sha256': digest(signature)})
    remaining = sorted(specs, key=lambda s: s['signature_sha256'])
    selected = []
    covered = set()
    while remaining and len(selected) < limit:
        best = max(range(len(remaining)), key=lambda i: (sum(((k, v) not in covered for k, v in remaining[i]['execution_choices'].items())) + int(('group', remaining[i]['group_id']) not in covered), -i))
        sp = remaining.pop(best)
        covered.update(sp['execution_choices'].items())
        covered.add(('group', sp['group_id']))
        selected.append(sp)
    for i, sp in enumerate(selected, 1):
        sp['spec_id'] = 'S' + str(i).zfill(3)
    return {'raw_combinations': raw, 'examined': examined, 'valid_unique_paths': len(specs), 'complete': examined == raw, 'selected_specifications': selected, 'execution_limit': limit, 'examined_limit': examine_limit, 'selection': 'fixed before outcomes; greedy Option/group coverage, stable hash tiebreak', 'no_seed_or_repetition_count_variants': True, 'source_equivalence_keys_are_model_judgments': True}

def plan(out, ctx, task, index, review, replay=False):
    used = {r['source_option_ref'] for r in review['adaptations']}
    material = {'context': ctx, 'task': task, 'adaptation_records': review['adaptations'], 'source_options': {r: index['options'][r] for r in sorted(used)}, 'source_decisions': {index['options'][r]['source_decision_ref']: index['decisions'][index['options'][r]['source_decision_ref']] for r in sorted(used)}}
    x = ask('source_plan', 'plan', read(ROOT / 'contracts/structured_plan.json'), material, lambda v: errors(v, ctx, task, index, review), out, replay)
    space = enumerate_specs(x, review)
    save(out / 'specification_space.json', space)
    freeze = {'input_manifest_sha256': digest(read(out / 'input_manifest.json')), 'plan_sha256': digest(x), 'review_sha256': digest(review), 'space_sha256': digest(space)}
    freeze['freeze_sha256'] = digest(freeze)
    if (out / 'analysis_freeze.json').exists() and read(out / 'analysis_freeze.json') != freeze:
        raise ValueError('Scientific plan changed after freeze; use a new output directory')
    save(out / 'analysis_freeze.json', freeze)
    instances = {d['id'] + '/' + o['id']: next((r for r in review['adaptations'] if r['source_option_ref'] == o['source_option_ref'] and r['operation_id'] == o['operation_id'])) for d in x['execution_decisions'] for o in d['options']}
    result = {'plan': x, 'space': space, 'freeze': freeze, 'instances': instances}
    save(out / 'frozen_execution.json', result)
    return result
