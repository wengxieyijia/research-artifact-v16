# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Incremental reported-only 10-paper trial. No hand-authored scientific answers."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import zipfile
import lab
import model_runner
import reported_extract
import standard_pipeline
ROOT = Path(__file__).resolve().parent
TRIAD_ROOT = next((p for p in [ROOT.parent / 'DAG_reported_20261023', ROOT.parent / 'reported_pipeline'] if (p / 'pipeline.py').exists()))
spec = importlib.util.spec_from_file_location('triad_baseline', TRIAD_ROOT / 'pipeline.py')
triad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(triad)
LANG = {'.r': 'R', '.rmd': 'R', '.qmd': 'R', '.py': 'Python', '.ipynb': 'Python', '.do': 'Stata', '.ado': 'Stata', '.m': 'MATLAB/Octave', '.sas': 'SAS', '.sps': 'SPSS', '.jl': 'Julia'}
DATA_EXT = {'.csv', '.tsv', '.dta', '.xlsx', '.xls', '.rds', '.rdata', '.sav', '.mat', '.parquet'}

def read(p):
    return lab.read(p)

def save(p, x):
    lab.save(p, x)

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def baseline(out):
    dest = out / 'inputs/baseline.json'
    if not dest.exists():
        save(dest, read(TRIAD_ROOT / '\u5c55\u793a\u6570\u636e\u5feb\u7167.json'))
    return read(dest)

def prepare(out, archive, count):
    base = baseline(out)
    known = {p['paper_id'] for p in base['papers']}
    selection_path = out / 'selection.json'
    if selection_path.exists():
        saved = read(selection_path)
        if len(saved['papers']) != count:
            raise ValueError('Requested paper count differs from frozen selection; use a new output directory')
        return saved
    if count < len(known):
        raise ValueError('Paper count must include all frozen baseline papers')
    cfg = read(ROOT / 'config.json')
    cfg.update(count=100, max_code_zip_bytes=10 ** 10, max_pdf_bytes=10 ** 8, max_pdf_chars=200000, max_code_chars=180000)
    with zipfile.ZipFile(archive) as z:
        _, inventory = lab.select_papers(z, cfg)
        records = []
        for index, item in enumerate(inventory):
            extensions = {}
            data_files = []
            source_bytes = 0
            for member in item['code_members']:
                with zipfile.ZipFile(io.BytesIO(z.read(member))) as inner:
                    for inf in inner.infolist():
                        if inf.is_dir() or '__MACOSX' in PurePosixPath(inf.filename).parts:
                            continue
                        ext = PurePosixPath(inf.filename).suffix.lower()
                        extensions[ext] = extensions.get(ext, 0) + 1
                        if ext in LANG:
                            source_bytes += inf.file_size
                        if ext in DATA_EXT:
                            data_files.append({'member': member, 'path': inf.filename, 'bytes': inf.file_size, 'extension': ext})
            records.append({**item, 'archive_index': index, 'languages': sorted({LANG[e] for e in extensions if e in LANG}), 'source_bytes': source_bytes, 'data_files': data_files})
        candidates = [r for r in records if r['paper_id'] not in known and r['languages'] and r['data_files'] and (0 < r['source_bytes'] <= 150000) and (100000 <= r['pdf_bytes'] <= 5000000)]
        seen = {l for r in records if r['paper_id'] in known for l in r['languages']}
        additions = []
        while len(additions) < count - len(known):
            remaining = [r for r in candidates if r['paper_id'] not in {x['paper_id'] for x in additions}]
            if not remaining:
                raise ValueError('Not enough candidates under selection rule; change config explicitly')
            pick = min(remaining, key=lambda r: (-len(set(r['languages']) - seen), r['source_bytes'], r['archive_index']))
            additions.append(pick)
            seen.update(pick['languages'])
        papers = []
        for p in base['papers']:
            item = next((r for r in records if r['paper_id'] == p['paper_id']))
            papers.append({**item, 'alias': p['alias'], 'baseline': True})
            source = TRIAD_ROOT / 'inputs' / p['paper_id'] / 'sources.json'
            save(out / 'inputs' / p['paper_id'] / 'sources.json', read(source))
        lab.TEXT_EXT.update({'.sthlp', '.qmd', '.sql', '.f', '.f90'})
        for i, item in enumerate(additions, len(papers) + 1):
            alias = 'P' + str(i)
            papers.append({**item, 'alias': alias, 'baseline': False})
            material = lab.extract_sources(z, item, cfg)
            save(out / 'inputs' / item['paper_id'] / 'sources.json', material)
    record = {'rule': {'base': 'existing 3 papers, unchanged', 'additional': 'has source code and a data-file extension; source bytes <=150000; PDF 100KB..5MB', 'order': 'greedy new language coverage, then source bytes ascending, then archive order', 'no_content_judgment': True, 'selected_data_file_does_not_guarantee_raw_microdata': True, 'budgeted_language_extensions': sorted(LANG), 'source_budget_note': '\u7b5b\u9009\u5b57\u8282\u6570\u9488\u5bf9\u8fd9\u4e9b\u4e3b\u811a\u672c\u6269\u5c55\u540d；\u5176\u4ed6\u53ef\u8bfb\u4ee3\u7801\u5982Fortran\u53e6\u5728\u8bfb\u53d6\u9636\u6bb5\u68c0\u6d4b、\u81ea\u52a8\u6269\u5145\u4e0a\u4e0b\u6587'}, 'papers': papers, 'source_limits': {'pdf_chars': 200000, 'code_chars': 180000}, 'languages': sorted(seen)}
    save(selection_path, record)
    save(out / 'inventory.json', records)
    return record

def prepare_extension(out, archive, count, seed):
    """Freeze an earlier trial and select remaining papers by recorded mechanical rules."""
    if (out / 'selection.json').exists():
        return prepare(out, archive, count)
    seed = seed.resolve()
    old = read(seed / 'selection.json')
    snapshot = read(seed / '\u5c55\u793a\u6570\u636e\u5feb\u7167.json')
    if count <= len(old['papers']):
        raise ValueError('Extension count must exceed seed paper count')
    if not (seed / 'verification.json').exists() or not read(seed / 'verification.json')['all_checks_passed']:
        raise ValueError('Seed trial must have passed verification')
    baseline(out)
    save(out / 'inputs/seed.json', snapshot)
    save(out / 'inputs/seed_selection.json', old)
    known = {p['paper_id'] for p in old['papers']}
    inventory = read(seed / 'inventory.json')
    candidates = [r for r in inventory if r['paper_id'] not in known and r['languages'] and (r['source_bytes'] > 0) and (r['pdf_bytes'] <= 10000000)]
    seen = {l for p in old['papers'] for l in p['languages']}
    additions = []
    while len(additions) < count - len(known):
        remaining = [r for r in candidates if r['paper_id'] not in {x['paper_id'] for x in additions}]
        if not remaining:
            raise ValueError('Insufficient unused papers with readable source code in current archive')
        pick = min(remaining, key=lambda r: (-len(set(r['languages']) - seen), -bool(r['data_files']), r['source_bytes'], r['archive_index']))
        additions.append(pick)
        seen.update(pick['languages'])
    papers = []
    for p in old['papers']:
        papers.append({**p, 'seed_frozen': True})
        src = seed / 'inputs' / p['paper_id'] / 'sources.json'
        save(out / 'inputs' / p['paper_id'] / 'sources.json', read(src))
        shutil.copytree(seed / 'records' / p['alias'], out / 'records' / p['alias'], dirs_exist_ok=True)
    save(out / '\u6570\u636e\u5143\u7279\u5f81.json', read(seed / '\u6570\u636e\u5143\u7279\u5f81.json'))
    cfg = read(ROOT / 'config.json')
    cfg.update(max_pdf_chars=400000, max_code_chars=1000000)
    lab.TEXT_EXT.update({'.sthlp', '.qmd', '.sql', '.f', '.f90'})
    with zipfile.ZipFile(archive) as z:
        for i, item in enumerate(additions, len(papers) + 1):
            paper = {**item, 'alias': 'P' + str(i), 'baseline': False, 'seed_frozen': False}
            papers.append(paper)
            save(out / 'inputs' / paper['paper_id'] / 'sources.json', lab.extract_sources(z, item, cfg))
    result = {'rule': {'base': str(len(known)) + ' verified papers frozen, including catalog IDs, mappings, H1, options and triads', 'additional': 'unused archive papers with recognized source-code extensions and PDF <=10MB; data availability preferred, not compulsory', 'order': 'greedy new language coverage, then data-file presence, then primary source bytes ascending, then archive order', 'changed_from_ten': 'removed source-size/PDF-size/data-presence exclusion to obtain ten additional papers; two original seed papers also lack measured data', 'no_content_judgment': True, 'selection_does_not_measure_true_method_coverage': True, 'selected_data_file_does_not_guarantee_raw_microdata': True}, 'papers': papers, 'seed_count': len(known), 'seed_snapshot_sha256': sha(seed / '\u5c55\u793a\u6570\u636e\u5feb\u7167.json'), 'excluded_by_pdf_size': [{'paper_id': r['paper_id'], 'pdf_bytes': r['pdf_bytes']} for r in inventory if r['paper_id'] not in known and r['pdf_bytes'] > 10000000], 'source_limits': {'pdf_chars': 400000, 'code_chars': 1000000}, 'languages': sorted(seen)}
    save(out / 'selection.json', result)
    save(out / 'inventory.json', inventory)
    return result

def frozen(paper):
    return paper.get('seed_frozen', False) or paper['baseline']

def ensure_complete_sources(selection, out, archive, replay=False):
    """Detect character-budget truncation mechanically and expand, never hand-select source passages."""
    rule = selection['rule']
    rule.setdefault('budgeted_language_extensions', sorted(LANG))
    rule.setdefault('source_budget_note', '\u7b5b\u9009\u5b57\u8282\u6570\u9488\u5bf9\u9884\u5b9a\u4e3b\u811a\u672c\u6269\u5c55\u540d；\u5176\u4ed6\u53ef\u8bfb\u4ee3\u7801\u5982Fortran\u5728\u8bfb\u53d6\u9636\u6bb5\u68c0\u6d4b，\u8d85\u51fa\u521d\u59cb\u4e0a\u4e0b\u6587\u989d\u5ea6\u5219\u7a0b\u5e8f\u81ea\u52a8\u6269\u5145。')
    incomplete = []
    for p in selection['papers']:
        if frozen(p):
            continue
        material = read(out / 'inputs' / p['paper_id'] / 'sources.json')
        truncated = [x for x in material.get('coverage', []) if x.get('included_chars', 0) < x.get('original_chars', 0)]
        if truncated:
            incomplete.append((p, material, truncated))
    if not incomplete:
        save(out / 'selection.json', selection)
        return selection
    if replay:
        raise RuntimeError('Frozen sources still contain budget truncation; complete source preparation before strict replay')
    cfg = read(ROOT / 'config.json')
    cfg.update(max_pdf_chars=400000, max_code_chars=1000000)
    lab.TEXT_EXT.update({'.sthlp', '.qmd', '.sql', '.f', '.f90'})
    history = selection.setdefault('automatic_source_expansions', [])
    with zipfile.ZipFile(archive) as z:
        for p, old, truncated in incomplete:
            save(out / 'inputs_history' / p['paper_id'] / (lab.sha(lab.dumps(old).encode()) + '.json'), old)
            expanded = lab.extract_sources(z, p, cfg)
            remains = [x for x in expanded['coverage'] if x.get('included_chars', 0) < x.get('original_chars', 0)]
            if remains:
                raise ValueError('Source still exceeds bounded expansion limits for ' + p['alias'])
            save(out / 'inputs' / p['paper_id'] / 'sources.json', expanded)
            detected = set(p['languages'])
            if any((PurePosixPath(x['location'].split('!')[-1]).suffix.lower() in ['.f', '.f90'] for x in expanded['sources'] if x['kind'] == 'code')):
                detected.add('Fortran')
            p['languages'] = sorted(detected)
            history.append({'paper': p['alias'], 'previous_truncated_records': len(truncated), 'remaining_truncated_records': len(remains), 'max_pdf_chars': 400000, 'max_code_chars': 1000000, 'new_total_source_chars': sum((len(x['text']) for x in expanded['sources'])), 'reason': 'automatic character-budget coverage check; no human reading or passage selection'})
            print(p['alias'] + ': automatically expanded source budget; all text included within bounds', flush=True)
    selection['languages'] = sorted({l for p in selection['papers'] for l in p['languages']})
    save(out / 'selection.json', selection)
    return selection

def h1_one(paper, out, cfg, replay):
    alias = paper['alias']
    dest = out / 'records' / alias
    dest.mkdir(parents=True, exist_ok=True)
    sources = read(out / 'inputs' / paper['paper_id'] / 'sources.json')['sources']
    if paper.get('seed_frozen'):
        return
    if paper['baseline']:
        h = read(TRIAD_ROOT / 'records' / alias / 'h1.json')
        save(dest / 'h1.json', h)
        space = next((p['space'] for p in baseline(out)['papers'] if p['alias'] == alias))
        save(dest / 'options.json', space)
        return
    h = model_runner.run_json('h1', triad.H1_INSTRUCTION, triad.POLICY, triad.H1_CONTRACT, {'paper_id': paper['paper_id'], 'title': paper['title'], 'sources': sources}, cfg, dest, lambda obj: triad.h1_validate(obj, {'paper_id': paper['paper_id'], 'sources': sources}), replay)
    fixed = h['h1']['text']
    instruction = (ROOT / 'prompts/options_reported.txt').read_text(encoding='utf-8')
    space = model_runner.run_json('options', instruction, reported_extract.STANDARD, {'schema': 'Complete Decision–Option JSON from instruction. Only reported; singleton allowed.'}, {'research_contract': {'hypothesis': {'text': fixed}, 'paper_h1': h}, 'sources': sources}, cfg, dest, lambda obj: reported_extract.errors(obj, fixed, sources), replay)
    save(dest / 'extraction_checks.json', {'only_reported': True, 'evidence': lab.evidence_audit(space, sources), 'decisions': len(space['decisions']), 'options': sum((len(d['options']) for d in space['decisions'])), 'dependencies': len(space['dependency_edges']), 'counts': lab.count_space(space)})

def extract(selection, out, cfg, replay, workers):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(h1_one, p, out, cfg, replay): p['alias'] for p in selection['papers']}
        for future in as_completed(pending):
            alias = pending[future]
            future.result()
            print(alias + ': extraction accepted', flush=True)

def feature_frame(frame):
    import pandas as pd
    import numpy as np
    columns = []
    frame.columns = [str(x) for x in frame.columns]
    for j, name in enumerate(frame.columns):
        v = frame.iloc[:, j]
        f = {'name': name, 'dtype': str(v.dtype), 'rows': len(v), 'nonmissing': int(v.notna().sum()), 'missing': int(v.isna().sum()), 'missing_rate': float(v.isna().mean()) if len(v) else None, 'distinct_nonmissing': int(v.nunique(dropna=True)), 'measurement_status': 'computed_from_file', 'unit': None, 'unit_note': '\u79d1\u7814\u5355\u4f4d\u4e0d\u80fd\u4ece\u6570\u503c\u672c\u8eab\u5224\u65ad；\u53e6\u89c1\u6709\u8bc1\u636e\u7684\u6570\u636e\u8bed\u4e49\u8bb0\u5f55'}
        if pd.api.types.is_numeric_dtype(v) and (not pd.api.types.is_complex_dtype(v)) and v.notna().any():
            for key, value in [('min', v.min()), ('max', v.max()), ('mean', v.mean()), ('std', v.std())]:
                f[key] = float(value) if pd.notna(value) and np.isfinite(value) else None
        if f['distinct_nonmissing'] <= 12:
            f['observed_values'] = [str(x) for x in v.dropna().unique()]
        columns.append(f)
    return columns

def profile(selection, out, archive, replay=False):
    import pandas as pd
    path = out / '\u6570\u636e\u5143\u7279\u5f81.json'
    existing = read(path) if path.exists() else {}
    if all((p['alias'] in existing for p in selection['papers'])):
        return existing
    if replay:
        raise RuntimeError('Missing frozen machine feature profile; offline mode cannot reconstruct absent raw data')
    profiles = existing
    base = baseline(out)
    for p in base['papers']:
        profiles[p['alias']] = p['data_profile']
        for ds in p['data_profile']['datasets']:
            src = TRIAD_ROOT / ds['file']
            dest = out / ds['file']
            if src.exists() and (not dest.exists()):
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
    with zipfile.ZipFile(archive) as z:
        for paper in selection['papers']:
            if paper['baseline']:
                continue
            datasets = []
            file_records = []
            alias = paper['alias']
            if alias in profiles:
                continue
            for i, item in enumerate(paper['data_files'], 1):
                dsid = 'd' + str(i)
                with zipfile.ZipFile(io.BytesIO(z.read(item['member']))) as inner:
                    raw = inner.read(item['path'])
                suffix = item['extension']
                dest = out / 'data' / alias / (dsid + '_' + hashlib.sha256(raw).hexdigest()[:12] + suffix)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(raw)
                record = {**item, 'sha256': sha(dest), 'local_file': dest.relative_to(out).as_posix()}
                frames = {}
                try:
                    if suffix in ['.csv', '.tsv']:
                        sep = '\t' if suffix == '.tsv' else ','
                        try:
                            frames[None] = pd.read_csv(dest, sep=sep, low_memory=False)
                        except UnicodeDecodeError:
                            frames[None] = pd.read_csv(dest, sep=sep, encoding='cp1252', low_memory=False)
                    elif suffix == '.dta':
                        frames[None] = pd.read_stata(dest, convert_categoricals=False)
                    elif suffix in ['.xls', '.xlsx']:
                        frames = pd.read_excel(dest, sheet_name=None)
                    elif suffix == '.parquet':
                        frames[None] = pd.read_parquet(dest)
                    elif suffix in ['.rdata', '.rds']:
                        import pyreadr
                        frames = dict(pyreadr.read_r(str(dest)))
                    elif suffix == '.mat':
                        import numpy as np
                        from scipy.io import loadmat
                        mat = loadmat(dest)
                        for key, value in mat.items():
                            if key.startswith('__') or not isinstance(value, np.ndarray):
                                continue
                            if value.ndim == 2 and value.dtype.kind in 'biuf' and (value.shape[1] <= 1000):
                                frames[key] = pd.DataFrame(value, columns=[key + '[' + str(j + 1) + ']' for j in range(value.shape[1])])
                        record['mat_column_note'] = '\u77e9\u9635\u6ca1\u6709\u539f\u59cb\u5217\u540d\u65f6\u53ea\u4f7f\u7528\u6570\u7ec4\u540d[\u5217\u53f7]，\u4e0d\u5f97\u81ea\u52a8\u5f53\u4f5c\u6709\u79d1\u7814\u8bed\u4e49\u7684\u53d8\u91cf\u540d'
                    else:
                        raise ValueError('No nonexecuting reader for ' + suffix)
                    if not frames:
                        raise ValueError('No table-like objects extracted')
                    for k, (table, frame) in enumerate(frames.items(), 1):
                        if not isinstance(frame, pd.DataFrame):
                            continue
                        dataset_id = dsid if len(frames) == 1 else dsid + 's' + str(k)
                        cols = feature_frame(frame)
                        datasets.append({'dataset_id': dataset_id, 'file': dest.relative_to(out).as_posix(), 'archive_location': item['member'] + '!' + item['path'], 'table': str(table) if table is not None else None, 'sha256': record['sha256'], 'rows': int(frame.shape[0]), 'column_count': len(cols), 'reader': 'ordinary Python data reader; no paper code execution', 'columns': cols})
                    record['status'] = 'measured'
                except Exception as exc:
                    record.update(status='not_measured', reason=type(exc).__name__ + ': ' + str(exc))
                file_records.append(record)
            profiles[alias] = {'status': 'measured' if datasets else 'data_not_readable', 'datasets': datasets, 'file_records': file_records, 'scope_note': '\u6587\u4ef6\u53ef\u8bfb\u53d6\u4e0d\u7b49\u4e8e\u672c\u6587\u539f\u59cb\u5fae\u89c2\u6570\u636e\u5df2\u53ef\u7528；\u53ef\u80fd\u53ea\u662f\u8f93\u51fa\u8868\u6216\u4e2d\u95f4\u91cf，\u8bed\u4e49\u7531\u6a21\u578b\u4f9d\u636e\u8bba\u6587/\u4ee3\u7801\u5224\u65ad'}
            save(path, profiles)
            print(alias + ': profiled ' + str(len(datasets)) + ' tables', flush=True)
    save(path, profiles)
    return profiles

def original_options(selection, out):
    originals = {}
    for p in selection['papers']:
        space = read(out / 'records' / p['alias'] / 'options.json')
        for d in space['decisions']:
            for o in d['options']:
                if o['origin'] != 'reported':
                    raise ValueError('Non-reported Option in current input')
                originals[p['alias'] + ':' + d['id'] + ':' + o['id']] = {'paper': p['alias'], 'paper_id': p['paper_id'], 'decision_ref': p['alias'] + ':' + d['id'], 'decision_label': d['label'], 'decision_reason': d['why_a_decision'], 'option': o, 'original_forbidden_combinations': [x for x in space['forbidden_combinations'] if x['choices'].get(d['id']) == o['id']]}
    return originals

def counters(c):

    def next_id(prefix, values):
        return max([int(x['id'][1:]) for x in values if x['id'].startswith(prefix)] or [0]) + 1
    return {'family': next_id('F', c['families']), 'method': next_id('M', c['methods']), 'component': next_id('C', [x for r in c['rows'] for x in r['components']])}

def patch_contract():
    full = read(ROOT / 'contracts/classification.json')['output_shape']
    full['rows'][0]['components'][0]['evidence'] = [{'source_id': 'given source ID', 'quote': 'literal contiguous original quotation >=8 chars'}]
    return {'new_families': full['families'], 'new_methods': full['methods'], 'rows': full['rows'], 'reuse_audits': [{'source_ref': 'Option ref', 'component_id': 'C ID', 'method_id': 'existing M ID', 'function_compatible': True, 'object_role_compatible': True, 'mechanism_compatible': True, 'relation': 'same_method | parameter_variant', 'reason': 'source-grounded explanation, not just similar names', 'evidence': [{'source_id': 'existing source ID', 'quote': 'literal contiguous original quote >=8 chars'}]}], 'limitations': ['uncertainties; no forced sharing']}

def apply_patch_catalog(c, patch):
    result = copy.deepcopy(c)
    result['families'] += copy.deepcopy(patch['new_families'])
    result['methods'] += copy.deepcopy(patch['new_methods'])
    result['rows'] += copy.deepcopy(patch['rows'])
    result['limitations'] += patch.get('limitations', [])
    result['suggested_pairs'] = []
    return result

def patch_errors(patch, c, refs, sources):
    errs = triad.quote_errors(patch, sources)
    if not all((k in patch for k in ['new_families', 'new_methods', 'rows', 'reuse_audits', 'limitations'])):
        return errs + ['Missing patch keys']
    combined = apply_patch_catalog(c, patch)
    errs += standard_pipeline.classification_errors(combined, [r['source_ref'] for r in c['rows']] + refs)
    old_f = {f['id'] for f in c['families']}
    old_m = {m['id'] for m in c['methods']}
    old_c = {x['id'] for r in c['rows'] for x in r['components']}
    if old_f & {f['id'] for f in patch['new_families']}:
        errs.append('New family IDs collide with existing catalog')
    if old_m & {m['id'] for m in patch['new_methods']}:
        errs.append('New method IDs collide with existing catalog')
    if old_c & {x['id'] for r in patch['rows'] for x in r['components']}:
        errs.append('New component IDs collide with existing catalog')
    expected = {(r['source_ref'], x['id'], x['method_id']) for r in patch['rows'] for x in r['components'] if x['method_id'] in old_m}
    actual = [(a['source_ref'], a['component_id'], a['method_id']) for a in patch['reuse_audits']]
    if set(actual) != expected or len(actual) != len(set(actual)):
        errs.append('Each assignment to a preexisting method needs exactly one reuse_audit')
    for a in patch['reuse_audits']:
        if not all((a.get(k) is True for k in ['function_compatible', 'object_role_compatible', 'mechanism_compatible'])):
            errs.append('A conflicting reuse cannot be accepted; retain uncertainty or create an evidence-grounded distinct method')
        if a.get('relation') not in ['same_method', 'parameter_variant'] or not a.get('evidence') or (not a.get('reason')):
            errs.append('Reuse needs relation, explanation and literal evidence')
    for row in patch['rows']:
        for comp in row['components']:
            if not comp.get('evidence'):
                errs.append(row['source_ref'] + '/' + comp['id'] + ': component must have source evidence')
            if any((p.get('basis') not in ['input_reported', 'unknown'] for p in comp['parameters'])):
                errs.append('New component parameters cannot invent inferred default values')
    return errs

def classify(selection, out, cfg, replay):
    c = copy.deepcopy(read(out / 'inputs/seed.json')['classification'] if (out / 'inputs/seed.json').exists() else baseline(out)['classification'])
    c['suggested_pairs'] = []
    originals = original_options(selection, out)
    standard = read(ROOT / 'standards/method_classification_v1.json')
    instruction = (ROOT / 'instructions/classify_incremental.txt').read_text(encoding='utf-8')
    save(out / 'classification_standard.json', standard)
    steps = []
    for p in selection['papers']:
        alias = p['alias']
        before = copy.deepcopy(c)
        if not frozen(p):
            sources = read(out / 'inputs' / p['paper_id'] / 'sources.json')['sources']
            refs = [ref for ref, x in originals.items() if x['paper'] == alias]
            mat = {'paper_id': p['paper_id'], 'paper_alias': alias, 'h1': read(out / 'records' / alias / 'h1.json'), 'original_options': {ref: originals[ref] for ref in refs}, 'option_refs': refs, 'existing_catalog': {'families': c['families'], 'methods': c['methods']}, 'existing_component_ids': [x['id'] for r in c['rows'] for x in r['components']], 'next_id_hints': counters(c), 'sources': sources}
            patch = model_runner.run_json('classification', instruction, standard, patch_contract(), mat, cfg, out / 'records' / alias, lambda obj: patch_errors(obj, c, refs, sources), replay)
            c = apply_patch_catalog(c, patch)
            save(out / 'records' / alias / 'catalog_after.json', c)
            steps.append({'paper': alias, 'new_family_ids': [f['id'] for f in patch['new_families']], 'new_method_ids': [m['id'] for m in patch['new_methods']], 'reused_method_ids': sorted({a['method_id'] for a in patch['reuse_audits']}), 'reused_component_instances': len(patch['reuse_audits']), 'component_instances': sum((len(r['components']) for r in patch['rows']))})
            print(alias + ': catalog accepted; ' + str(len(patch['new_methods'])) + ' new methods, ' + str(len(patch['reuse_audits'])) + ' reused components', flush=True)
    save(out / 'classification.json', c)
    save(out / 'incremental_steps.json', steps)
    save(out / 'original_options.json', originals)
    return (c, originals)

def enrichment_errors(obj, paper, expected, features):
    errs = []
    if not isinstance(obj.get('components'), list):
        errs.append('Missing top-level components array')
    if not isinstance(obj.get('limitations'), list):
        errs.append('Missing top-level limitations array; it must be alongside paper_id and components, not nested inside a component')
    if errs:
        return errs
    for comp in obj['components']:
        for key in ['source_ref', 'component_id', 'data_columns', 'parameters', 'slot_coverage', 'parameter_completeness']:
            if key not in comp:
                errs.append('Missing component field ' + key)
        for col in comp.get('data_columns', []):
            for key in ['name', 'dataset_id', 'availability', 'role', 'meaning', 'unit', 'h1_relation', 'evidence']:
                if key not in col:
                    errs.append('Missing data-column field ' + key)
        for par in comp.get('parameters', []):
            for key in ['name', 'value', 'basis', 'scope', 'evidence']:
                if key not in par:
                    errs.append('Missing parameter field ' + key)
    if errs:
        return errs
    return triad.triad_validate(obj, paper, expected, features)

def enrich_one(paper, c, originals, features, out, cfg, replay):
    alias = paper['alias']
    dest = out / 'records' / alias
    if paper.get('seed_frozen'):
        return
    if paper['baseline']:
        value = read(TRIAD_ROOT / 'records' / alias / 'triads.json')
        save(dest / 'triads.json', value)
        return
    sources = read(out / 'inputs' / paper['paper_id'] / 'sources.json')['sources']
    h1 = read(dest / 'h1.json')
    methods = {m['id']: m for m in c['methods']}
    expected = {}
    for row in c['rows']:
        if originals[row['source_ref']]['paper'] != alias:
            continue
        for comp in row['components']:
            slots = list(dict.fromkeys(methods[comp['method_id']]['parameter_slots'] + [p['name'] for p in comp['parameters']]))
            expected[row['source_ref'], comp['id']] = {'source_ref': row['source_ref'], 'component_id': comp['id'], 'original_option': originals[row['source_ref']], 'original_component': comp, 'method': methods[comp['method_id']], 'required_parameter_slots': slots}
    values = list(expected.values())
    batch_size = 6
    combined = {'paper_id': paper['paper_id'], 'components': [], 'limitations': []}
    contract = copy.deepcopy(triad.TRIAD_CONTRACT)
    contract['components'][0]['data_columns'][0]['dataset_id'] = 'exact dataset_id from actual_column_inventory; null for no measured binding'
    instruction = triad.TRIAD_INSTRUCTION.replace('dataset_id=d1', 'dataset_id=\u7ed9\u5b9a\u5b9e\u9645\u6570\u636e\u96c6ID')
    catalog = {'status': features['status'], 'datasets': [{k: d[k] for k in ['dataset_id', 'file', 'sha256', 'rows', 'column_count']} | {'table': d.get('table'), 'archive_location': d.get('archive_location'), 'columns': [{'name': x['name'], 'dtype': x['dtype']} for x in d['columns']]} for d in features['datasets']]}
    for i in range(0, len(values), batch_size):
        batch = values[i:i + batch_size]
        keys = {(x['source_ref'], x['component_id']) for x in batch}
        expected_batch = {k: v for k, v in expected.items() if k in keys}
        obj = model_runner.run_json('triads_' + str(i // batch_size + 1), instruction, triad.POLICY, contract, {'paper_id': paper['paper_id'], 'h1_record': h1, 'actual_column_inventory': catalog, 'components': batch, 'sources': sources}, cfg, dest, lambda obj: enrichment_errors(obj, {'paper_id': paper['paper_id'], 'sources': sources}, expected_batch, features), replay)
        combined['components'] += obj['components']
        combined['limitations'] += obj['limitations']
    save(dest / 'triads.json', combined)
    print(alias + ': triads accepted (' + str(len(values)) + ' components)', flush=True)

def enrich(selection, c, originals, profiles, out, cfg, replay, workers):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = [pool.submit(enrich_one, p, c, originals, profiles[p['alias']], out, cfg, replay) for p in selection['papers']]
        for job in as_completed(jobs):
            job.result()

def convergence(selection, c, originals):
    methods = {m['id']: m for m in c['methods']}
    seen_m = set()
    seen_f = set()
    growth = []
    for i, p in enumerate(selection['papers'], 1):
        rows = [r for r in c['rows'] if originals[r['source_ref']]['paper'] == p['alias']]
        components = [x for r in rows for x in r['components']]
        mids = {x['method_id'] for x in components}
        fids = {methods[m]['family_id'] for m in mids}
        new_m = mids - seen_m
        new_f = fids - seen_f
        reused = sum((x['method_id'] in seen_m for x in components))
        growth.append({'n': i, 'paper': p['alias'], 'paper_id': p['paper_id'], 'title': p['title'], 'new_methods': len(new_m), 'new_families': len(new_f), 'new_method_ids': sorted(new_m), 'reused_method_types': len(mids & seen_m), 'reused_component_instances': reused, 'component_instances': len(components), 'reuse_rate': reused / len(components) if components else 0, 'cumulative_methods': len(seen_m | mids), 'cumulative_families': len(seen_f | fids), 'baseline_frozen': p['baseline']})
        seen_m |= mids
        seen_f |= fids
    last = growth[-3:]
    new_m = sum((x['new_methods'] for x in last))
    new_f = sum((x['new_families'] for x in last))
    return {'growth': growth, 'last_three_new_methods': new_m, 'last_three_new_families': new_f, 'method_plateau_observed_last_three': new_m == 0, 'family_plateau_observed_last_three': new_f == 0, 'summary': f'\u6700\u540e\u4e09\u7bc7\u4ecd\u65b0\u589e {new_f} \u4e2a\u5bb6\u65cf、{new_m} \u4e2a\u5177\u4f53\u65b9\u6cd5。' + ('\u672c\u987a\u5e8f\u4e0b\u89c2\u5bdf\u5230\u4e09\u7bc7\u65e0\u65b0\u589e\u65b9\u6cd5，\u4e0d\u80fd\u636e\u6b64\u8bc1\u660e\u603b\u4f53\u5df2\u6536\u655b。' if new_m == 0 else '\u672c\u987a\u5e8f\u4e0b\u5c1a\u672a\u51fa\u73b0\u5177\u4f53\u65b9\u6cd5\u6570\u91cf\u7684\u5e73\u53f0。'), 'limits': ['\u4ec5\u4e00\u4e2a\u9884\u5148\u8bb0\u5f55\u7684\u52a0\u5165\u987a\u5e8f，\u6ca1\u6709\u987a\u5e8f\u654f\u611f\u6027\u8bd5\u9a8c。', '\u539f\u4e09\u7bc7\u76ee\u5f55\u51bb\u7ed3，\u65b0\u589e\u4e03\u7bc7\u4e3areported-only\u65b0\u63d0\u53d6，\u63d0\u53d6\u7248\u672c\u4e0d\u540c。' if not selection.get('seed_count') else '\u524d\u5341\u7bc7\u63d0\u53d6、\u76ee\u5f55\u548c\u6620\u5c04\u51bb\u7ed3；\u540e\u5341\u7bc7\u6309\u540c\u4e00\u89c4\u8303\u589e\u91cf\u5f52\u7c7b，\u672a\u91cd\u65b0\u4f30\u8ba1\u5386\u53f2\u5206\u7c7b。', '\u6837\u672c\u6309\u4ee3\u7801\u89c4\u6a21/\u8bed\u8a00/\u6570\u636e\u6587\u4ef6\u53ef\u7528\u6027\u7b5b\u9009，\u4e0d\u4ee3\u8868\u5168\u90e8\u79d1\u7814\u9886\u57df。', '\u590d\u7528\u7387\u6765\u81ea\u6a21\u578b\u5f52\u7c7b，\u4e0d\u662f\u4e13\u5bb6\u51c6\u786e\u7387，\u4e5f\u4e0d\u7b49\u4e8e\u7edf\u8ba1\u5206\u6790\u6709\u6548\u6027。', '\u65e2\u5b58\u7c7b\u522b\u5b9a\u4e49\u4e0d\u91cd\u5199，\u5206\u7c7b\u7c92\u5ea6\u4e0e\u521d\u59cb\u76ee\u5f55\u4f1a\u5f71\u54cd\u65b0\u589e\u91cf；\u4e0d\u5f3a\u8feb\u6536\u655b。']}

def method_coverage(selection, c, originals, out):
    """ID-based reuse measurements; no claim of scientific recall or semantic accuracy."""
    seed = read(out / 'inputs/seed.json')
    seed_m = {m['id'] for m in seed['classification']['methods']}
    seed_p = {p['alias'] for p in seed['papers']}
    seen = set()
    per_paper = []
    method_papers = {m['id']: set() for m in c['methods']}
    for p in selection['papers']:
        comps = [x for r in c['rows'] if originals[r['source_ref']]['paper'] == p['alias'] for x in r['components']]
        mids = {x['method_id'] for x in comps}
        prior = mids & seen
        baseline = mids & seed_m
        for m in mids:
            method_papers[m].add(p['alias'])
        per_paper.append({'paper': p['alias'], 'seed_frozen': p['alias'] in seed_p, 'distinct_methods': len(mids), 'covered_by_prior_methods': len(prior), 'prior_method_type_coverage': len(prior) / len(mids) if mids else None, 'covered_by_frozen_ten_methods': len(baseline), 'frozen_ten_type_coverage': len(baseline) / len(mids) if mids else None, 'component_instances': len(comps), 'covered_components_by_prior': sum((x['method_id'] in seen for x in comps)), 'covered_components_by_frozen_ten': sum((x['method_id'] in seed_m for x in comps)), 'method_ids': sorted(mids), 'prior_covered_method_ids': sorted(prior), 'frozen_ten_covered_method_ids': sorted(baseline)})
        seen |= mids
    new = [x for x in per_paper if not x['seed_frozen']]
    total = sum((x['distinct_methods'] for x in new))
    comp_total = sum((x['component_instances'] for x in new))
    union = set().union(*(set(x['method_ids']) for x in new))

    def rate(a, b):
        return a / b if b else None
    summary = {'seed_papers': len(seed_p), 'added_papers': len(new), 'seed_methods': len(seed_m), 'added_paper_method_occurrences': total, 'added_paper_distinct_methods': len(union), 'added_component_instances': comp_total, 'prior_covered_method_occurrences': sum((x['covered_by_prior_methods'] for x in new)), 'prior_type_coverage': rate(sum((x['covered_by_prior_methods'] for x in new)), total), 'frozen_ten_covered_method_occurrences': sum((x['covered_by_frozen_ten_methods'] for x in new)), 'frozen_ten_type_coverage': rate(sum((x['covered_by_frozen_ten_methods'] for x in new)), total), 'frozen_ten_union_covered_types': len(union & seed_m), 'frozen_ten_union_type_coverage': rate(len(union & seed_m), len(union)), 'prior_component_coverage': rate(sum((x['covered_components_by_prior'] for x in new)), comp_total), 'frozen_ten_component_coverage': rate(sum((x['covered_components_by_frozen_ten'] for x in new)), comp_total), 'shared_method_types_all_papers': sum((len(v) > 1 for v in method_papers.values())), 'method_types_seen_in_new_papers_and_seed': len(union & seed_m)}
    by_kind = []
    for kind in ['method', 'strategy', 'metric']:
        kind_ids = {m['id'] for m in c['methods'] if m.get('kind', 'method') == kind}
        occurrences = sum((len(set(x['method_ids']) & kind_ids) for x in new))
        previous = sum((len(set(x['prior_covered_method_ids']) & kind_ids) for x in new))
        initial = sum((len(set(x['frozen_ten_covered_method_ids']) & kind_ids) for x in new))
        by_kind.append({'kind': kind, 'seed_catalog_types': len(seed_m & kind_ids), 'final_catalog_types': len(kind_ids), 'added_paper_method_occurrences': occurrences, 'prior_covered_occurrences': previous, 'frozen_ten_covered_occurrences': initial, 'prior_type_coverage': rate(previous, occurrences), 'frozen_ten_type_coverage': rate(initial, occurrences)})
    result = {'metric': 'model-assigned Method-ID reuse coverage; not recall against external scientific method inventory', 'definitions': {'prior_type_coverage': '\u540e\u5341\u7bc7\u4e2d，\u5f52\u5165\u6b64\u524d\u8bba\u6587\u5df2\u51fa\u73b0M\u7684\u7bc7\u5185\u65b9\u6cd5\u79cd\u7c7b\u6570\u4e4b\u548c / \u540e\u5341\u7bc7\u7bc7\u5185\u65b9\u6cd5\u79cd\u7c7b\u6570\u4e4b\u548c；\u540c\u4e00M\u8de8\u7bc7\u91cd\u590d\u8ba1\u6570，\u540c\u7bc7\u4ec5\u8ba1\u4e00\u6b21', 'frozen_ten_type_coverage': '\u540e\u5341\u7bc7\u4e2d，\u5f52\u5165\u524d\u5341\u7bc7\u51bb\u7ed3\u76ee\u5f55M\u7684\u7bc7\u5185\u65b9\u6cd5\u79cd\u7c7b\u6570\u4e4b\u548c / \u540e\u5341\u7bc7\u7bc7\u5185\u65b9\u6cd5\u79cd\u7c7b\u6570\u4e4b\u548c', 'component_coverage': '\u6309\u7ec4\u4ef6\u5b9e\u4f8b\u52a0\u6743；\u4e0d\u80fd\u66ff\u4ee3\u6309\u7bc7\u5185\u65b9\u6cd5\u79cd\u7c7b\u8ba1\u6570', 'true_method_coverage': '\u6ca1\u6709\u72ec\u7acb\u65b9\u6cd5\u5168\u96c6\u6216\u91d1\u6807\u51c6，\u65e0\u6cd5\u6d4b\u5f97\u771f\u5b9e\u65b9\u6cd5\u8986\u76d6\u7387'}, 'summary': summary, 'by_kind': by_kind, 'per_paper': per_paper, 'method_paper_coverage': [{'method_id': m['id'], 'name': m['name'], 'family_id': m['family_id'], 'kind': m.get('kind', 'method'), 'papers': sorted(method_papers[m['id']], key=lambda x: int(x[1:])), 'paper_count': len(method_papers[m['id']])} for m in c['methods']], 'limits': ['\u8ba1\u6570\u53d6\u51b3\u4e8e\u6a21\u578b\u5206\u7c7b\u7c92\u5ea6、\u51bb\u7ed3\u76ee\u5f55\u548c\u52a0\u5165\u987a\u5e8f；\u672a\u6392\u9664\u8bed\u4e49\u8bef\u62c6\u5206\u6216\u8bef\u5408\u5e76。', '\u65b0\u589e\u8bba\u6587\u6309\u8bed\u8a00、\u6570\u636e\u6587\u4ef6\u4e0e\u4ee3\u7801\u5927\u5c0f\u673a\u68b0\u7b5b\u9009，\u975e\u65b9\u6cd5\u603b\u4f53\u7684\u968f\u673a\u6837\u672c。', '\u5171\u7528\u6e90\u7801\u5305\u7684\u8bba\u6587\u53ef\u80fd\u91cd\u590d\u51fa\u73b0\u76f8\u540c\u5b9e\u73b0；\u4fdd\u7559\u6765\u6e90，\u4e0d\u5f53\u4f5c\u72ec\u7acb\u65b9\u6cd5\u591a\u6837\u6027\u7684\u8bc1\u660e。']}
    save(out / '\u65b9\u6cd5\u8986\u76d6\u7387.json', result)
    return result

def build(selection, c, originals, profiles, out):
    class_errors = standard_pipeline.classification_errors(c, list(originals))
    if class_errors:
        raise ValueError('Final classification invalid: ' + lab.dumps(class_errors))
    enriched = {}
    papers = []
    evidence = {}
    reuse = []
    for p in selection['papers']:
        alias = p['alias']
        source_material = read(out / 'inputs' / p['paper_id'] / 'sources.json')
        sources = source_material['sources']
        lookup = {s['source_id']: s for s in sources}
        record = read(out / 'records' / alias / 'triads.json')
        for x in record['components']:
            comp = copy.deepcopy(x)
            for col in comp['data_columns']:
                ds = next((d for d in profiles[alias]['datasets'] if d['dataset_id'] == col['dataset_id']), None)
                col['measured_features'] = next((f for f in ds['columns'] if f['name'] == col['name']), None) if ds else None
            comp['h1_ref'] = alias + '/research_context/H1'
            enriched[comp['source_ref'] + '/' + comp['component_id']] = comp
        space = read(out / 'records' / alias / 'options.json')
        papers.append({'alias': alias, 'paper_id': p['paper_id'], 'title': p['title'], 'space': space, 'research_context': read(out / 'records' / alias / 'h1.json'), 'data_profile': profiles[alias], 'languages': p['languages'], 'baseline_frozen': p['baseline'], 'enrichment_limits': record['limitations'], 'source_coverage': {'sources': len(sources), 'included_chars': sum((len(s['text']) for s in sources)), 'truncated_records': sum((x.get('included_chars', 0) < x.get('original_chars', 0) for x in source_material.get('coverage', []))), 'skipped_records': sum((bool(x.get('skipped')) for x in source_material.get('coverage', []))), 'low_text_pages': sum((bool(x.get('low_text')) for x in source_material.get('coverage', [])))}})
        for ref, x in originals.items():
            if x['paper'] != alias:
                continue
            evidence[ref] = [{**e, 'kind': lookup[e['source_id']]['kind'], 'location': lookup[e['source_id']]['location'], 'text_matched': not triad.quote_errors(e, sources)} for e in x['option'].get('evidence', [])]
        patch_path = out / 'records' / alias / 'classification.json'
        if patch_path.exists():
            reuse += read(patch_path)['reuse_audits']
    methods = {m['id']: m for m in c['methods']}
    coverage = []
    for f in c['families']:
        refs = [r['source_ref'] for r in c['rows'] if any((methods[x['method_id']]['family_id'] == f['id'] for x in r['components']))]
        coverage.append({'family_id': f['id'], 'name': f['name'], 'papers': sorted({originals[r]['paper'] for r in refs}), 'counts': {p['alias']: sum((originals[r]['paper'] == p['alias'] for r in refs)) for p in papers}})
    stats = {'papers': len(papers), 'decisions': sum((len(p['space']['decisions']) for p in papers)), 'options': len(originals), 'families': len(c['families']), 'methods': len(methods), 'components': len(enriched), 'column_bindings': sum((len(x['data_columns']) for x in enriched.values())), 'measured_column_bindings': sum((col['measured_features'] is not None for x in enriched.values() for col in x['data_columns'])), 'parameters': sum((len(x['parameters']) for x in enriched.values())), 'reported_parameters': sum((p['basis'] == 'reported' for x in enriched.values() for p in x['parameters'])), 'unknown_parameters': sum((p['basis'] == 'unknown' for x in enriched.values() for p in x['parameters'])), 'shared_families': sum((len(x['papers']) > 1 for x in coverage)), 'shared_methods': sum((len({originals[r['source_ref']]['paper'] for r in c['rows'] if any((x['method_id'] == m['id'] for x in r['components']))}) > 1 for m in c['methods']))}
    conv = convergence(selection, c, originals)
    payload = {'version': '20261023-ten-paper-incremental' if len(papers) == 10 else '20261023-' + str(len(papers)) + '-paper-incremental', 'policy': triad.POLICY, 'classification': c, 'original_options': originals, 'papers': papers, 'enriched_components': enriched, 'evidence': evidence, 'coverage': coverage, 'stats': stats, 'convergence': conv, 'reuse_audits': reuse, 'selection_rule': selection['rule']}
    if (out / 'inputs/seed.json').exists():
        payload['method_coverage'] = method_coverage(selection, c, originals, out)
        for paper in papers:
            paper['seed_frozen'] = paper['alias'] in {p['alias'] for p in read(out / 'inputs/seed.json')['papers']}
    expected = {r['source_ref'] + '/' + x['id'] for r in c['rows'] for x in r['components']}
    if set(enriched) != expected:
        raise ValueError('Component enrichment coverage mismatch')
    save(out / '\u5c55\u793a\u6570\u636e\u5feb\u7167.json', payload)
    save(out / '\u6536\u655b\u8bb0\u5f55.json', conv)
    template = (out / 'template.html').read_text(encoding='utf-8')
    js = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    (out / 'index.html').write_text(template.replace('__DATA__', js), encoding='utf-8')
    save(out / 'checks.json', {'only_reported': all((x['option']['origin'] == 'reported' for x in originals.values())), 'classification_errors': class_errors, 'components_exact_coverage': set(enriched) == expected, 'stats': stats, 'old_snapshot_sha256': sha(out / 'inputs/baseline.json'), 'source_snapshot_unchanged': read(out / 'inputs/baseline.json') == read(TRIAD_ROOT / '\u5c55\u793a\u6570\u636e\u5feb\u7167.json'), 'reuse_audits': len(reuse), 'scientific_accuracy': 'not independently established'})
    print(lab.dumps(stats), flush=True)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT.parent / 'DAG_10papers_20261023')
    p.add_argument('--archive', type=Path, default=Path(read(ROOT / 'config.json')['archive']))
    p.add_argument('--count', type=int, default=10)
    p.add_argument('--workers', type=int, default=3)
    p.add_argument('--stage', choices=['prepare', 'extract', 'profile', 'classify', 'enrich', 'build', 'all'], default='all')
    p.add_argument('--seed', type=Path, help='Verified earlier trial to freeze and extend')
    p.add_argument('--replay', action='store_true')
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cfg = read(ROOT / 'config_high.json')
    cfg['max_structural_repairs'] = 3
    save(out / 'config.json', cfg)
    selection = prepare_extension(out, args.archive, args.count, args.seed) if args.seed and (not (out / 'selection.json').exists()) else prepare(out, args.archive, args.count)
    selection = ensure_complete_sources(selection, out, args.archive, args.replay)
    if not (out / 'template.html').exists():
        import scale_view
        scale_view.build_template(out)
    if args.stage == 'prepare':
        return
    if args.stage == 'profile':
        profile(selection, out, args.archive, args.replay)
        return
    if args.stage == 'build':
        build(selection, read(out / 'classification.json'), read(out / 'original_options.json'), read(out / '\u6570\u636e\u5143\u7279\u5f81.json'), out)
        return
    model_runner.verify_provider(cfg, out, args.replay)
    if args.stage in ['all', 'extract']:
        extract(selection, out, cfg, args.replay, args.workers)
    if args.stage == 'extract':
        return
    if args.stage == 'enrich':
        c = read(out / 'classification.json')
        originals = read(out / 'original_options.json')
    else:
        c, originals = classify(selection, out, cfg, args.replay)
    if args.stage == 'classify':
        return
    profiles = profile(selection, out, args.archive, args.replay)
    enrich(selection, c, originals, profiles, out, cfg, args.replay, args.workers)
    build(selection, c, originals, profiles, out)
if __name__ == '__main__':
    main()
