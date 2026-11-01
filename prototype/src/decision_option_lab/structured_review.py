# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Batched, cached scientific applicability and explicit adaptation. Never edits model science locally."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from structured_multiverse import ROOT, read, save, ask, unique, digest

def check_assess(x, batch, index, task):
    errors = []
    expected = {r['source_option_ref']: r for r in batch}
    rows = x.get('assessments', [])
    if not unique(rows, 'source_option_ref') or {r.get('source_option_ref') for r in rows} != set(expected):
        return ['Assess every supplied source Option exactly once']
    for row in rows:
        r = expected[row['source_option_ref']]
        checks = row.get('operation_assessments', [])
        if not unique(checks, 'operation_id') or {v.get('operation_id') for v in checks} != set(r['operation_ids']):
            errors.append('Assess every recalled operation exactly once for ' + row['source_option_ref'] + '; expected operation_id list=' + str(r['operation_ids']) + '; returned=' + str([v.get('operation_id') for v in checks]) + '. Return only the exact requested IDs, not all task operations or previously reviewed IDs.')
        refs = {c['component_ref'] for c in index['options'][row['source_option_ref']]['components']}
        for a in checks:
            if a.get('status') not in ['applicable', 'conditional', 'inapplicable']:
                errors.append('Three-way applicability required')
            for key in ['scientific_function_fit', 'object_role_fit', 'semantic_fit', 'method_core_fit', 'adaptation_attempt', 'dependency_check', 'comparability_check', 'reason']:
                if not a.get(key):
                    errors.append('Every candidate needs ' + key)
            if not set(a.get('required_source_components', [])) <= refs:
                errors.append('Use source Option component refs only')
    return errors

def check_adapt(x, requests, index, ctx):
    errors = []
    expected = {(r['source_option_ref'], r['operation_id']) for r in requests}
    rows = x.get('adaptations', [])
    found = [(r.get('source_option_ref'), r.get('operation_id')) for r in rows]
    if len(found) != len(set(found)) or set(found) != expected:
        return ['Return every requested source Option/operation adaptation exactly once']
    cols = {c['column_id'] for c in ctx['dataset']['columns']}
    for row in rows:
        o = index['options'][row['source_option_ref']]
        refs = {c['component_ref'] for c in o['components']}
        if row.get('status') not in ['ready', 'conditional', 'blocked']:
            errors.append('Explicit ready/conditional/blocked adaptation state required')
        if not set(row.get('source_method_ids', [])) <= set(o['method_ids']) or not set(row.get('component_refs', [])) <= refs:
            errors.append('No invented source Method/component')
        for b in row.get('data_binding', []):
            if b.get('column_id') is not None and b['column_id'] not in cols:
                errors.append('Use real measured column IDs')
        for p in row.get('parameters', []):
            if p.get('status') not in ['source_supported', 'target_configured', 'unknown'] or 'value' not in p or (not p.get('reason')):
                errors.append('Explicit scientific parameter value/status/reason required')
        for key in ['adaptation_attempt', 'core_definition', 'target_metric', 'population', 'equivalence_key', 'reason']:
            if not row.get(key):
                errors.append('Adaptation missing ' + key)
        if row.get('status') == 'ready':
            if row.get('core_preserved') is not True or not row.get('source_method_ids') or (not row.get('component_refs')):
                errors.append('Ready scientific adaptation must preserve source Method core and cite it')
            if row.get('unresolved'):
                errors.append('Unresolved necessary conditions cannot be marked ready; keep conditional/blocked')
            if any((p.get('status') == 'unknown' for p in row.get('parameters', []))):
                errors.append('Unknown execution parameters cannot be ready')
    return errors

def review(out, ctx, task, index, recalled, replay=False):
    contracts = read(ROOT / 'contracts/structured_multiverse.json')
    common = {'h1': ctx['h1'], 'dataset': ctx['dataset'], 'column_semantics': ctx['column_semantics'], 'task': task, 'original_graph': ctx['original_graph']}
    candidates = recalled['candidates']
    bank_path = out / 'assessment_bank.json'
    bank = read(bank_path) if bank_path.exists() else {}
    pending = []
    for r in candidates:
        missing = [op for op in r['operation_ids'] if op not in bank.get(r['source_option_ref'], {})]
        if missing:
            pending.append({**r, 'operation_ids': missing})
    batches = [pending[i:i + 6] for i in range(0, len(pending), 6)]
    jobs = []
    for batch in batches:
        key = digest(batch)[:12]
        material = {**common, 'candidates': [{'retrieval': r, 'source_record': index['options'][r['source_option_ref']]} for r in batch]}
        jobs.append(('assess_' + key, batch, material))
    results = {}

    def work(job):
        stage, batch, material = job
        return (stage, ask(stage, 'assess', contracts['assess'], material, lambda x: check_assess(x, batch, index, task), out, replay))
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(work, j) for j in jobs]
        for f in as_completed(futures):
            stage, x = f.result()
            results[stage] = x
            for row in x['assessments']:
                byop = bank.setdefault(row['source_option_ref'], {})
                for a in row['operation_assessments']:
                    byop[a['operation_id']] = a
            save(bank_path, bank)
    initial_ledger = [{'source_option_ref': r['source_option_ref'], 'operation_assessments': [bank[r['source_option_ref']][op] for op in r['operation_ids']]} for r in candidates]
    recheck_path = out / 'reconsider_bank.json'
    recheck = read(recheck_path) if recheck_path.exists() else {}
    appeals = []
    for r in candidates:
        missing = [op for op in r['operation_ids'] if bank[r['source_option_ref']][op]['status'] == 'inapplicable' and op not in recheck.get(r['source_option_ref'], {})]
        if missing:
            appeals.append({**r, 'operation_ids': missing})
    appeal_batches = [appeals[i:i + 2] for i in range(0, len(appeals), 2)]

    def reconsider_work(batch):
        stage = 'reconsider_' + digest(batch)[:12]
        material = {**common, 'candidates': [{'retrieval': r, 'expected_operation_ids': r['operation_ids'], 'source_record': index['options'][r['source_option_ref']], 'previous_exclusions': [bank[r['source_option_ref']][op] for op in r['operation_ids']]} for r in batch]}
        return (stage, ask(stage, 'reconsider', contracts['assess'], material, lambda x: check_assess(x, batch, index, task), out, replay))
    with ThreadPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(reconsider_work, b) for b in appeal_batches]):
            stage, x = f.result()
            for row in x['assessments']:
                dest = recheck.setdefault(row['source_option_ref'], {})
                for a in row['operation_assessments']:
                    dest[a['operation_id']] = a
            save(recheck_path, recheck)
    ledger = [{'source_option_ref': r['source_option_ref'], 'operation_assessments': [recheck.get(r['source_option_ref'], {}).get(op, bank[r['source_option_ref']][op]) for op in r['operation_ids']]} for r in candidates]
    save(out / 'exclusion_reconsideration.json', {'initial_assessments': initial_ledger, 'after_reconsideration': ledger, 'changed_to_retained': sum((bank[r['source_option_ref']][a['operation_id']]['status'] == 'inapplicable' and a['status'] != 'inapplicable' for r in ledger for a in r['operation_assessments'])), 'purpose': 'independently recheck all exclusions, especially domain/old-context barriers; no developer scientific edits'})
    save(out / 'candidate_assessments.json', {'assessments': ledger, 'candidates': candidates, 'counts': {status: sum((a['status'] == status for r in ledger for a in r['operation_assessments'])) for status in ['applicable', 'conditional', 'inapplicable']}})
    requests = [{'source_option_ref': r['source_option_ref'], **a} for r in ledger for a in r['operation_assessments'] if a['status'] in ['applicable', 'conditional']]
    adapted = {}
    adapt_path = out / 'adaptation_bank.json'
    adapt_bank = read(adapt_path) if adapt_path.exists() else {}
    pending_adapt = [r for r in requests if r['source_option_ref'] + '|' + r['operation_id'] not in adapt_bank]
    abatches = [pending_adapt[i:i + 5] for i in range(0, len(pending_adapt), 5)]

    def adapt_work(batch):
        stage = 'adapt_' + digest(batch)[:12]
        material = {**common, 'adaptation_requests': [{'initial_assessment': r, 'source_record': index['options'][r['source_option_ref']]} for r in batch]}
        return (stage, ask(stage, 'adapt', contracts['adapt'], material, lambda x: check_adapt(x, batch, index, ctx), out, replay))
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(adapt_work, b) for b in abatches]
        for f in as_completed(futures):
            stage, x = f.result()
            adapted[stage] = x
            for row in x['adaptations']:
                adapt_bank[row['source_option_ref'] + '|' + row['operation_id']] = row
            save(adapt_path, adapt_bank)
    transfers = [adapt_bank[r['source_option_ref'] + '|' + r['operation_id']] for r in requests]
    final = {'assessments': ledger, 'adaptations': transfers, 'retrieval_counts': recalled['counts'], 'source_options': len(candidates), 'adaptation_counts': {st: sum((r['status'] == st for r in transfers)) for st in ['ready', 'conditional', 'blocked']}}
    save(out / 'candidate_review.json', final)
    required = [op['id'] for op in task['operations'] if op['necessity'] == 'required']
    uncovered = [op for op in required if not any((r['operation_id'] == op and r['status'] == 'ready' for r in transfers))]
    save(out / 'retrieval_coverage.json', {'required_operations_without_ready_catalog_adaptation': uncovered, 'note': 'Original reported fixed steps may cover some operations; index expansion is recall, not fabricated coverage'})
    if uncovered and recalled['retrieval_k'] < 8:
        from structured_retrieval import retrieve
        wider = retrieve(out, index, task, replay, k=8)
        if len(wider['candidates']) > len(candidates):
            return review(out, ctx, task, index, wider, replay)
    if (out / 'configuration_resolution_enabled.json').exists():
        from structured_resolve import resolve
        transfers = resolve(out, ctx, task, index, transfers, replay)
        final['adaptations'] = transfers
        final['adaptation_counts'] = {st: sum((r['status'] == st for r in transfers)) for st in ['ready', 'conditional', 'blocked']}
        final['configuration_resolution'] = 'explicit model target configuration; partial source-Method reuse is recorded'
        save(out / 'candidate_review.json', final)
    return final
