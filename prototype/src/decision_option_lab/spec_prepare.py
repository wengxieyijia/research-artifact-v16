# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Select empirical paper packages by availability, snapshot original data/code, infer feasibility via DeepSeek."""
import io
import json
from pathlib import Path, PurePosixPath
from concurrent.futures import ThreadPoolExecutor
import sys
import zipfile
import pandas as pd
import lab
import model_runner
ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'specification_results'
TABULAR = {'.csv', '.dta'}

def inventory(z):
    selected, items = lab.select_papers(z, {**lab.read(ROOT / 'config.json'), 'count': 9999, 'max_code_zip_bytes': 100000000, 'max_pdf_bytes': 10000000})
    lookup = {x['paper_id']: x for x in items}
    rows = []
    for name in z.namelist():
        if '/code/' not in name or not name.lower().endswith('.zip') or z.getinfo(name).file_size > 50000000:
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(z.read(name))) as inner:
                fs = [{'name': f.filename, 'bytes': f.file_size} for f in inner.infolist() if not f.is_dir() and '__MACOSX' not in f.filename]
        except zipfile.BadZipFile:
            continue
        data = [f for f in fs if PurePosixPath(f['name']).suffix.lower() in TABULAR and f['bytes'] > 10000 and (not any((t in f['name'].lower() for t in ['/results/', '/figures_data/', '/out/'])))]
        rows.append({'paper_id': name.split('/')[1], 'member': name, 'files': fs, 'data_files': data, 'raw_bytes': sum((f['bytes'] for f in data)), 'zip_bytes': z.getinfo(name).file_size, 'paper': lookup.get(name.split('/')[1])})
    return rows

def profile(path):
    if path.suffix == '.csv':
        df = pd.read_csv(path)
    else:
        df = pd.read_stata(path, convert_categoricals=False)
    cols = []
    for name in df:
        s = df[name]
        row = {'name': name, 'dtype': str(s.dtype), 'missing': int(s.isna().sum()), 'unique': int(s.nunique())}
        if pd.api.types.is_numeric_dtype(s):
            row.update(min=None if not s.notna().any() else float(s.min()), max=None if not s.notna().any() else float(s.max()))
        if s.nunique() <= 12:
            row['values'] = [str(x) for x in s.dropna().unique().tolist()]
        cols.append(row)
    return {'file': path.name, 'rows': len(df), 'columns': cols}

def prepare(archive):
    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        rows = inventory(z)
        existing = {p.name for p in (ROOT / 'results').glob('paper*') if (p / 'options.json').exists()}
        within = next((x for x in rows if x['paper_id'] in existing and x['data_files']))
        outside = next((x for x in rows if x['paper_id'] not in existing and 100000 <= x['raw_bytes'] <= 8000000 and (x['zip_bytes'] < 10000000) and (len(x['files']) <= 50) and x['paper']))
        lab.save(OUT / 'selection.json', {'rule': 'archive order; within old three: first with CSV/DTA >10KB; outside: first with raw CSV/DTA 0.1–8MB, code ZIP <10MB, <=50 files; actual usability checked by model and execution', 'selected': [{'group': group, **{k: v for k, v in x.items() if k != 'files'}} for group, x in [('within', within), ('outside', outside)]]})
        for group, x in [('within', within), ('outside', outside)]:
            out = OUT / x['paper_id']
            out.mkdir(exist_ok=True)
            input_dir = out / 'inputs'
            input_dir.mkdir(exist_ok=True)
            manifests = []
            for member in x['paper']['code_members']:
                with zipfile.ZipFile(io.BytesIO(z.read(member))) as inner:
                    for f in inner.infolist():
                        pp = PurePosixPath(f.filename)
                        if f.is_dir() or pp.suffix.lower() not in TABULAR or '__MACOSX' in pp.parts:
                            continue
                        target = input_dir / pp.name
                        if target.exists() and lab.sha(target.read_bytes()) != lab.sha(inner.read(f)):
                            raise ValueError('Ambiguous input basename ' + pp.name)
                        payload = inner.read(f)
                        target.write_bytes(payload)
                        manifests.append({'file': target.name, 'archive_location': member + '!' + f.filename, 'sha256': lab.sha(payload), 'bytes': len(payload)})
            sources = lab.extract_sources(z, x['paper'], {**lab.read(ROOT / 'config.json'), 'max_pdf_chars': 800000, 'max_code_chars': 300000})
            lab.save(out / 'sources.json', sources)
            profiles = []
            for f in sorted(input_dir.iterdir()):
                try:
                    profiles.append(profile(f))
                except Exception as exc:
                    profiles.append({'file': f.name, 'read_error': str(exc)})
            lab.save(out / 'data_profiles.json', profiles)
            lab.save(out / 'data_manifest.json', manifests)
            lab.save(out / 'paper.json', {'group': group, **x['paper']})
            original = ROOT / 'results' / x['paper_id']
            if (original / 'options.json').exists():
                lab.save(out / 'input_dag.json', lab.read(original / 'options.json'))
                lab.save(out / 'original_context.json', lab.read(original / 'context.json'))

def intake_errors(obj, sources, profiles, space=None):
    errors = []
    if type(obj.get('feasible')) is not bool:
        errors.append('feasible bool required')
    h = obj.get('hypothesis', {})
    for key in ('text', 'origin', 'population', 'exposure', 'outcome', 'estimand'):
        if not h.get(key):
            errors.append('hypothesis ' + key + ' required')
    if h.get('direction') not in ('positive', 'negative', 'two_sided'):
        errors.append('invalid direction')
    if obj.get('relationship_to_original_h1') not in ('same_main_claim', 'empirical_subquestion', 'infeasible'):
        errors.append('invalid H1 relationship')
    available = {p['file'] for p in profiles if 'read_error' not in p}
    if not obj.get('data_files') or not set(obj['data_files']) <= available:
        errors.append('data files must exist and parse')
    audit = lab.evidence_audit(h, sources)
    if not audit['total'] or audit['total'] != audit['matched']:
        errors.append('H1 needs actual verbatim source evidence')
    for k in ('dag_applicability', 'fixed_execution_settings', 'limitations'):
        if not isinstance(obj.get(k), list):
            errors.append(k + ' array required')
    if space:
        ids = [d['id'] for d in space['decisions']]
        if sorted((x.get('decision_id') for x in obj['dag_applicability'])) != sorted(ids):
            errors.append('cover each existing Decision once')
        if any((x.get('status') not in ('active', 'conditional_noop', 'inactive') or not x.get('reason') for x in obj['dag_applicability'])):
            errors.append('invalid applicability projection')
    return errors

def intake_one(out, replay=False):
    profiles = lab.read(out / 'data_profiles.json')
    sources = lab.read(out / 'sources.json')['sources']
    space = lab.read(out / 'input_dag.json') if (out / 'input_dag.json').exists() else None
    material = {'data_profiles': profiles, 'sources': sources, 'existing_dag': space, 'original_context': lab.read(out / 'original_context.json') if (out / 'original_context.json').exists() else None, 'h1_mode': 'model_inferred_operational_if_main_claim_not_testable', 'user_h1': None}
    cfg = lab.read(ROOT / 'config_high.json')
    return model_runner.run_json('intake', (ROOT / 'instructions/execution_intake.txt').read_text(encoding='utf-8'), lab.read(ROOT / 'execution_policy.json'), {}, material, cfg, out, lambda x: intake_errors(x, sources, profiles, space), replay)
if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    prepare(lab.read(ROOT / 'config.json')['archive'])
    dirs = [OUT / x['paper_id'] for x in lab.read(OUT / 'selection.json')['selected']]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(intake_one, dirs))
    for path, obj in zip(dirs, results):
        print(path.name, lab.dumps(obj), flush=True)
