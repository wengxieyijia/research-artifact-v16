# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Resolve target configuration with model-selected measurements; never supply scientific defaults."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from structured_multiverse import ROOT, read, save, ask, digest
MEASURE_CONTRACT = {'filters': [{'column_id': 'real ID', 'values': ['model selected observed values']}], 'key_column_ids': ['real IDs'], 'value_column_ids': ['real IDs'], 'reason': 'why these ordinary measurements are needed'}

def measurement_errors(x, ctx):
    cols = {c['column_id'] for c in ctx['dataset']['columns']}
    errors = []
    refs = x.get('key_column_ids', []) + x.get('value_column_ids', []) + [f.get('column_id') for f in x.get('filters', [])]
    if not set(refs) <= cols:
        errors.append('Measurements require existing column IDs')
    if not x.get('key_column_ids') or not x.get('value_column_ids'):
        errors.append('Supply measured key and value columns')
    if len(x.get('filters', [])) > 3:
        errors.append('At most three small measurement filters')
    if any((not f.get('values') or len(f['values']) > 20 for f in x.get('filters', []))):
        errors.append('Each filter needs 1-20 literal values')
    varying = {f['column_id'] for f in x.get('filters', []) if len(set(map(str, f.get('values', [])))) > 1}
    if varying & set(x.get('key_column_ids', [])):
        errors.append('Cross-group matching keys must exclude varying filter columns: ' + str(sorted(varying)) + '. Use the stable analysis-unit identifier; filter columns already define the group.')
    return errors

def measure(out, ctx, replay=False):
    path = out / 'configuration_measurements.json'
    req = ask('configuration_measurement_request', 'measure', MEASURE_CONTRACT, {'context': ctx}, lambda x: measurement_errors(x, ctx), out, replay)
    if path.exists():
        previous = read(path)
        if previous['model_measurement_request'] == req:
            return previous
        history = out / 'measurement_history'
        history.mkdir(exist_ok=True)
        save(history / (digest(previous)[:16] + '.json'), previous)
    if replay:
        raise ValueError('Saved ordinary configuration measurements missing')
    import pandas as pd
    import itertools
    names = {c['column_id']: c['name'] for c in ctx['dataset']['columns']}
    df = pd.read_csv(out / 'inputs/analysis_data.csv')
    keys = [names[c] for c in req['key_column_ids']]
    values = [names[c] for c in req['value_column_ids']]
    frames = []
    rows = []
    for combination in itertools.product(*[f['values'] for f in req['filters']]):
        sub = df
        filters = {names[f['column_id']]: v for f, v in zip(req['filters'], combination)}
        for name, value in filters.items():
            sub = sub.loc[sub[name] == value]
        frames.append(sub)
        rows.append({'filter_values': filters, 'rows': len(sub), 'missing_keys': int(sub[keys].isna().any(axis=1).sum()), 'duplicate_key_rows': int(sub.duplicated(keys, keep=False).sum()), 'distinct_keys': int(len(sub[keys].drop_duplicates())), 'value_features': {v: {'nonmissing': int(sub[v].notna().sum()), 'missing': int(sub[v].isna().sum()), 'distinct_nonmissing': int(sub[v].nunique()), 'min': float(sub[v].min()) if pd.api.types.is_numeric_dtype(sub[v]) and sub[v].notna().any() else None, 'max': float(sub[v].max()) if pd.api.types.is_numeric_dtype(sub[v]) and sub[v].notna().any() else None} for v in values}})
    keysets = [set(map(tuple, sub[keys].dropna().drop_duplicates().itertuples(index=False, name=None))) for sub in frames]
    common = set.intersection(*keysets) if keysets else set()
    complete = {}
    for v in values:
        sets = [set(map(tuple, sub.loc[sub[v].notna(), keys].dropna().drop_duplicates().itertuples(index=False, name=None))) for sub in frames]
        complete[v] = len(set.intersection(*sets)) if sets else 0
    result = {'model_measurement_request': req, 'groups': rows, 'common_keys_across_groups': len(common), 'complete_keys_by_value': complete, 'scope': 'ordinary counts and missingness only; not estimates, pvalues or causal/missingness assumptions'}
    save(path, result)
    return result

def resolve(out, ctx, task, index, transfers, replay=False):
    from structured_review import check_adapt
    measurements = measure(out, ctx, replay)
    path = out / 'configuration_resolution_bank.json'
    bank = read(path) if path.exists() else {}
    pending = [a for a in transfers if a['status'] == 'conditional' and a['source_option_ref'] + '|' + a['operation_id'] not in bank]
    batches = [pending[i:i + 3] for i in range(0, len(pending), 3)]

    def work(batch):
        material = {'context': ctx, 'task': task, 'ordinary_measurements': measurements, 'adaptation_requests': [{'previous_adaptation': a, 'source_record': index['options'][a['source_option_ref']]} for a in batch]}
        return ask('resolve_' + digest(batch)[:12], 'resolve', read(ROOT / 'contracts/structured_multiverse.json')['adapt'], material, lambda x: check_adapt(x, batch, index, ctx), out, replay)
    with ThreadPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(work, b) for b in batches]):
            for a in f.result()['adaptations']:
                bank[a['source_option_ref'] + '|' + a['operation_id']] = a
            save(path, bank)
    result = [bank.get(a['source_option_ref'] + '|' + a['operation_id'], a) for a in transfers]
    save(out / 'configuration_resolution.json', {'before': transfers, 'after': result, 'policy': 'model resolves target parameter slots before freeze; method cores and source graph identities unchanged'})
    return result
