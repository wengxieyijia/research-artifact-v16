# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Data+metadata+H1 -> indexed source-graph reuse -> generated multiverse. Research judgments: DeepSeek."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import csv
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import lab
import model_runner
ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT.parent / 'Structured_DAG_Multiverse_20261024_v3'
BASE = ROOT.parent / 'Paper_Graph_Expansion_20261024'
CATALOG = ROOT.parent / 'DAG_20papers_20261023/\u5c55\u793a\u6570\u636e\u5feb\u7167.json'

def read(p):
    return lab.read(p)

def save(p, x):
    lab.save(p, x)

def digest(x):
    return lab.sha(lab.dumps(x).encode('utf-8'))

def file_sha(p):
    return lab.sha(p.read_bytes())

def unique(rows, key):
    return len(rows) == len({r.get(key) for r in rows})

def ask(stage, prompt, contract, material, validator, out, replay=False):
    cfg = read(ROOT / 'config_high.json')
    cfg.update(max_tokens=32000, max_structural_repairs=2)
    if prompt == 'code':
        cfg['max_tokens'] = 64000
    return model_runner.run_json(stage, (ROOT / 'instructions' / ('structured_' + prompt + '.txt')).read_text('utf-8'), read(ROOT / 'standards/structured_multiverse_v1.json'), contract, material, cfg, out, validator, replay)

def prepare(out, base, catalog, data=None, metadata=None, hypothesis=None, target_graph=None, sources=None, replay=False):
    out.mkdir(parents=True, exist_ok=True)
    dest = out / 'inputs'
    dest.mkdir(exist_ok=True)
    manifest = out / 'input_manifest.json'
    if manifest.exists():
        x = read(manifest)
        for name, sha in x['files'].items():
            if file_sha(out / name) != sha:
                raise ValueError('Frozen input changed: ' + name)
        if catalog.exists() and file_sha(catalog) != x['catalog_sha256']:
            raise ValueError('Original catalog changed')
        if data is not None:
            raise ValueError('This output already contains frozen inputs. Use a new --output for explicit --data/metadata/hypothesis; replay/rerun omits new input arguments.')
        return read(out / 'context.json')
    if replay:
        raise ValueError('Input snapshot missing in replay')
    if data is None:
        context = read(base / 'research_context.json')
        features = read(base / 'data_features.json')
        ranking = read(base / 'column_ranking.json')
        table = next((d for d in features['datasets'] if d['dataset_id'] == context['dataset_choice']['dataset_id']))
        source_data = base / 'analysis_input/analysis_data.csv'
        original = read(base / 'graph1_reported.json')
        source_text = read(base / 'inputs/sources.json')
        source_data_manifest = read(base / 'analysis_input_manifest.json')
        if file_sha(source_data) != source_data_manifest['csv_sha256']:
            raise ValueError('Trial data hash mismatch')
        info = {'h1': context['h1'], 'dataset': table, 'column_semantics': ranking, 'research_context': context, 'original_graph': original, 'source_context': 'fixed held-out paper and independently extracted H1; no manual paper selection/relabeling'}
    else:
        if metadata is None or hypothesis is None:
            raise ValueError('--data requires --metadata and --hypothesis JSON files')
        import pandas as pd
        source_data = data
        frame = pd.read_csv(data)
        meta = read(metadata)
        hyp = read(hypothesis)
        table = {'dataset_id': 'input', 'rows': len(frame), 'columns': []}
        for i, name in enumerate(frame.columns, 1):
            col = frame[name]
            table['columns'].append({'column_id': 'input:c' + str(i), 'name': name, 'dtype': str(col.dtype), 'rows': len(col), 'nonmissing': int(col.notna().sum()), 'missing': int(col.isna().sum()), 'distinct_nonmissing': int(col.nunique()), 'measurement_status': 'computed_from_file'})
        info = {'h1': hyp if isinstance(hyp, dict) else {'text': hyp}, 'dataset': table, 'column_semantics': meta, 'research_context': {'user_metadata': meta}, 'original_graph': read(target_graph) if target_graph else None, 'source_context': 'user-provided data/metadata/H1; source-reported target graph only if supplied'}
        source_text = read(sources) if sources else {'sources': []}
    shutil.copy2(source_data, dest / 'analysis_data.csv')
    shutil.copy2(catalog, dest / 'knowledge_graph.json')
    save(dest / 'sources.json', source_text)
    save(out / 'context.json', info)
    paths = [dest / 'analysis_data.csv', dest / 'knowledge_graph.json', dest / 'sources.json', out / 'context.json']
    save(manifest, {'files': {p.relative_to(out).as_posix(): file_sha(p) for p in paths}, 'catalog_sha256': file_sha(catalog), 'catalog_source': str(catalog.resolve()), 'source_data_sha256': file_sha(source_data), 'credential_values_included': False})
    save(out / 'configuration_resolution_enabled.json', {'enabled': True, 'reason': 'Model resolves target parameter slots before freeze; Method core reuse differs from complete source Option execution'})
    return info

def task_errors(x, ctx):
    e = []
    ops = x.get('operations', [])
    columns = {c['column_id'] for c in ctx['dataset']['columns']}
    ds = {d['id'] for d in (ctx.get('original_graph') or {}).get('decisions', [])}
    if not ops or not unique(ops, 'id') or len(ops) > 12:
        e.append('Need 1-12 unique retrieval operations')
    for op in ops:
        if op.get('target_decision_id') is not None and op['target_decision_id'] not in ds:
            e.append('Target Decision must exist or null; operations do not invent graph Decisions')
        if not set(op.get('column_ids', [])) <= columns:
            e.append('Use real column IDs')
        for k in ['label', 'scientific_function', 'operation_object', 'query_text', 'query_en', 'family_query', 'reason']:
            if not op.get(k):
                e.append('Operation missing ' + k)
        if op.get('necessity') not in ['required', 'optional']:
            e.append('Operation necessity required')
    return e

def run(out=DEFAULT, base=BASE, catalog=CATALOG, replay=False, stage='all', rerun=False, **inputs):
    if not catalog.exists() and (out / 'input_manifest.json').exists():
        catalog = out / 'inputs/knowledge_graph.json'
    started = time.monotonic()
    ctx = prepare(out, base, catalog, replay=replay, **inputs)
    contract = read(ROOT / 'contracts/structured_multiverse.json')
    task = ask('task', 'task', contract['task'], ctx, lambda x: task_errors(x, ctx), out, replay)
    if stage == 'task':
        return
    from structured_retrieval import build_index, retrieve
    index = build_index(out, read(out / 'inputs/knowledge_graph.json'), replay)
    recalled = retrieve(out, index, task, replay)
    if stage == 'retrieve':
        return
    from structured_review import review
    reviewed = review(out, ctx, task, index, recalled, replay)
    if stage == 'review':
        return
    from structured_plan import plan
    frozen = plan(out, ctx, task, index, reviewed, replay)
    if stage == 'plan':
        return
    from structured_execution import execute_plan
    execute_plan(out, ctx, index, frozen, replay, rerun)
    save(out / 'pipeline_status.json', {'status': 'complete', 'elapsed_seconds': round(time.monotonic() - started, 2), 'source_catalog_unchanged': file_sha(catalog) == read(out / 'input_manifest.json')['catalog_sha256']})
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=DEFAULT)
    p.add_argument('--trial-baseline', type=Path, default=BASE)
    p.add_argument('--catalog', type=Path, default=CATALOG)
    p.add_argument('--stage', choices=['task', 'retrieve', 'review', 'plan', 'all'], default='all')
    p.add_argument('--replay', action='store_true')
    p.add_argument('--rerun', action='store_true')
    for name in ['data', 'metadata', 'hypothesis', 'target-graph', 'sources']:
        p.add_argument('--' + name, type=Path)
    a = p.parse_args()
    run(a.output.resolve(), a.trial_baseline.resolve(), a.catalog.resolve(), a.replay, a.stage, a.rerun, data=a.data, metadata=a.metadata, hypothesis=a.hypothesis, target_graph=a.target_graph, sources=a.sources)
