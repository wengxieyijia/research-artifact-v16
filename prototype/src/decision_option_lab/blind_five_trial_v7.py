# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Fresh five-input experiment; no prior target semantics, ranks, plans or outcomes are used."""
import argparse, concurrent.futures, copy, datetime, hashlib, itertools, json, re, shutil, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import lab, model_runner
ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'outputs/DAG_20papers_20261023'
OUT = ROOT / 'outputs/Blind_Five_Input_v7_20261027'
PRIVATE = ROOT / 'work/Blind_Five_Input_v7_quarantine_20261027'
PUBLIC = Path('external_workspace/2026-10-25/dag20-restart/outputs/Blind_Five_Input_Full_Report_20261027')
CFG = lab.read(Path(__file__).with_name('config_high.json'))
KEYS = ['input_1_h1', 'input_2_data', 'input_3_route_a', 'input_4_route_b', 'input_5_effect_scope']
RETRIEVAL_RUN_ID = 'blind-five-v7-20261027'
WORKER_SOURCE_PATH = None
sys.stdout.reconfigure(encoding='utf-8')

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(name, obj):
    lab.save(OUT / name, obj)

def read(name):
    return lab.read(OUT / name)

def event(stage, **fields):
    OUT.mkdir(exist_ok=True, parents=True)
    with (OUT / 'events.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps({'utc': now(), 'stage': stage, **fields}, ensure_ascii=False) + '\n')

def unwrap(obj, key):
    if key not in obj and isinstance(obj.get('output_contract'), dict) and (key in obj['output_contract']):
        real = obj['output_contract']
        obj.clear()
        obj.update(real)
STANDARD = {'version': 'fresh-five-v7-20261027', 'developer_role': '\u673a\u68b0\u8bfb\u53d6、\u6d4b\u91cf、\u6821\u9a8c、\u6267\u884c\u548c\u7ed8\u56fe。\u79d1\u7814\u5047\u8bbe、\u8bed\u4e49、\u6307\u6807、\u65b9\u6848、\u53c2\u6570、\u7edf\u8ba1\u4ee3\u7801、\u6765\u6e90\u5224\u5b9a\u5168\u90e8\u7531DeepSeek\u4f9d\u636e\u5141\u8bb8\u8f93\u5165\u751f\u6210。', 'hypothesis': '\u53ea\u7814\u7a76\u4e00\u4e2a\u539f\u6587\u53ef\u8ffd\u6eaf\u547d\u9898；\u4f5c\u8005\u65e0\u7f16\u53f7H1\u5219\u660e\u786e\u65e0\u7f16\u53f7\u63cf\u8ff0\u6027\u4e3b\u5f20，\u4e0d\u62fc\u5168\u6587\u53d1\u73b0，\u4e0d\u628a\u7ed3\u8bba\u5192\u5145\u5148\u9a8c\u5047\u8bbe。', 'blind_policy': '\u65b9\u6848\u9636\u6bb5\u5916\u90e8\u79d1\u7814\u8d44\u6599\u4e25\u683c\u53ea\u6709H1、\u5e72\u51c0Data、\u5386\u53f2A、\u5386\u53f2B、\u5141\u8bb8\u6548\u5e94\u53e3\u5f84；\u4ec5\u53ef\u53e6\u7528\u7531\u4e94\u9879\u8f93\u5165\u4ea7\u751f\u7684\u672c\u8f6e\u8349\u7a3f/\u4ee3\u7801/\u8bca\u65ad，\u4e0d\u8bfb\u76ee\u6807PDF、\u4f5c\u8005\u4ee3\u7801、\u4f5c\u8005\u6570\u503c、\u65e7\u8bd5\u9a8c\u65b9\u6848\u4e0e\u7ed3\u679c。', 'public_target_metadata': '\u7528\u6237\u660e\u786e\u5141\u8bb8\u6548\u5e94\u53e3\u5f84\u77e5\u60c5；\u4e0d\u662f\u5b8c\u5168\u4e0d\u63a5\u89e6\u4f5c\u8005\u4fe1\u606f。\u4f5c\u8005\u7ed3\u679c\u6570\u503c\u548c\u5206\u6790\u65b9\u6848\u5fc5\u987b\u9694\u79bb。', 'scientific_policy': '\u5728\u76f8\u540c\u660e\u786eH1\u548c\u6548\u5e94\u53e3\u5f84\u4e0b\u5c3d\u91cf\u5145\u5206\u679a\u4e3e\u5408\u7406\u654f\u611f\u6027\u5206\u652f，\u5148\u67e5\u7ed9\u5b9a\u5386\u53f2\u65b9\u6cd5\u80fd\u5426\u590d\u7528/\u6539\u7f16，\u518d\u65b0\u63d0\u51fa；\u4e0d\u4e3a\u4e86\u5bc6\u5ea6\u6df7\u5408\u4e0d\u540c\u5355\u4f4d/\u76ee\u6807、\u4e0d\u634f\u9020\u72ec\u7acb\u65b9\u6cd5\u6216\u7edf\u8ba1\u63a8\u65ad。', 'reuse': 'Decision、\u5b8c\u6574Option\u914d\u7f6e、Method\u6838\u5fc3\u4e09\u4e2a\u6765\u6e90\u8f74\u5206\u5f00；ID\u5b58\u5728\u4e0d\u8bc1\u660e\u79d1\u5b66\u652f\u6301，\u4e0d\u6309\u7ec4\u5408\u91cd\u590d\u6b21\u6570\u81a8\u80c0\u590d\u7528\u7387。', 'reporting': '\u63a8\u6d4b、\u672a\u77e5、\u6a21\u578b\u5206\u6b67、\u62d2\u7edd\u7406\u7531、\u65e0\u6548/\u91cd\u590d\u7ec4\u5408、\u5931\u8d25、\u7f3a\u5931\u4f5c\u8005\u6548\u5e94\u5fc5\u987b\u5b8c\u6574\u4fdd\u7559。\u65e0\u6709\u6548P\u503c\u5219null/NA，\u4e0d\u80fd\u6807\u6210NS。'}

def task(stage, instruction, contract, material, validator, zone='blind', replay=False):
    folder = PRIVATE / 'model_tasks' / stage if zone == 'target_extractor' else OUT / 'model_tasks' / stage
    folder.mkdir(parents=True, exist_ok=True)
    if zone == 'blind':
        if (OUT / 'author_extraction_receipt.json').exists():
            raise RuntimeError('Author numerical references have been opened; no further blind scientific-generation calls are allowed in this run')
        if set(material) != set(KEYS):
            raise ValueError('Scientific planning requires exactly the five public source slots')
        if (OUT / 'public_inputs_lock.json').exists():
            assert sha(OUT / 'five_inputs.json') == read('public_inputs_lock.json')['sha256']
    lab.save(folder / 'input.json', material)
    lab.save(folder / 'standard.json', STANDARD)
    lab.save(folder / 'instruction.json', {'instruction': instruction, 'zone': zone, 'utc': now()})

    def validate(obj):
        primary = next(iter(contract))
        unwrap(obj, primary)
        return validator(obj)
    result = model_runner.run_json(stage, instruction + '\n\u8f93\u51fa\u5df2\u586b\u5145\u6839JSON；\u79d1\u7814\u89e3\u91ca\u7528\u4e2d\u6587。\u4e0d\u8981\u56de\u663e\u7a7a\u5951\u7ea6。', STANDARD, contract, material, CFG, folder, validate, replay=replay)
    lab.save(folder / 'zone.json', {'zone': zone, 'material_sha256': sha(folder / 'input.json'), 'current_conversation_forwarded': False, 'external_source_slots': list(material)})
    save(stage + '.json', result) if zone != 'target_extractor' else lab.save(PRIVATE / (stage + '.json'), result)
    event('model_stage_completed', model_stage=stage, zone=zone)
    return result

def protect():
    files = list(BASE.rglob('*'))
    for folder in ['Neo4j_ColumnBinding_Provenance_v2_20261025', 'Single_H1_Multiverse_v3_20261025', 'Strict_Four_Input_v5_20261026', 'H1_Gated_Independent_v6_20261026']:
        p = ROOT / 'outputs' / folder
        files.extend((f for f in p.iterdir() if f.is_file() and f.suffix in ('.json', '.py', '.csv'))) if p.exists() else None
    files.extend((p for p in Path(__file__).parent.glob('*.py') if p.name not in ('blind_five_trial_v7.py', 'blind_five_report_v7.py', 'blind_five_worker_v7.py')))
    return {str(p): sha(p) for p in files if p.is_file() and '__pycache__' not in p.parts}

def prepare():
    OUT.mkdir(exist_ok=True, parents=True)
    PRIVATE.mkdir(exist_ok=True, parents=True)
    if not (OUT / 'protected_before.json').exists():
        save('protected_before.json', protect())
    if not (OUT / 'data.csv').exists():
        shutil.copy2(ROOT / 'outputs/Neo4j_Semantic_Trial_20261025/data.csv', OUT / 'data.csv')
    if not (OUT / 'data_structure_profile.json').exists():
        frame = pd.read_csv(OUT / 'data.csv')
        cols = []
        for name in frame.columns:
            series = frame[name]
            c = {'name': name, 'dtype': str(series.dtype), 'rows': len(series), 'missing': int(series.isna().sum()), 'unique': int(series.nunique(dropna=True))}
            if pd.api.types.is_numeric_dtype(series):
                a = pd.to_numeric(series, errors='coerce')
                finite = a[np.isfinite(a)]
                c.update(min=float(finite.min()) if len(finite) else None, max=float(finite.max()) if len(finite) else None, nonpositive=int((finite <= 0).sum()), quantiles={str(k): float(v) for k, v in finite.quantile([0, 0.25, 0.5, 0.75, 1]).items()})
            cols.append(c)
        profile = {'rows': len(frame), 'column_count': len(cols), 'columns': cols, 'data_sha256': sha(OUT / 'data.csv'), 'preview_rows': json.loads(frame.head(12).to_json(orient='records')), 'preview_policy': 'Only first 12 actual rows plus complete column measurements are sent to the model; program executes full CSV.'}
        save('data_structure_profile.json', profile)
        save('input_origin_ledger.json', {'allowed_data': {'source': 'original selected dataset CSV, not prior semantics', 'sha256': sha(OUT / 'data.csv')}, 'rejected_target_derivatives': ['all previous column dictionaries', 'all previous top-five rankings', 'all previous route A/B results', 'all previous target scientific plans/codes/results', 'all previous author code-derived baselines'], 'target_paper_extractor': 'PDF sources only, in separate quarantined model calls; no author code supplied', 'history': 'Frozen 20-paper DAG and history-only independently verified preprocessing; historical data/quotes are explicitly permitted.'})
        event('clean_data_prepared', rows=len(frame), columns=len(cols))

def target_metadata():
    prepare()
    if (OUT / 'h1_public.json').exists():
        return
    raw = lab.read(ROOT / 'outputs/Neo4j_Semantic_Trial_20261025/target_sources.json')
    pdf = [s for s in raw['sources'] if s.get('kind') == 'pdf']
    material = {'paper_identity': {k: raw['paper'][k] for k in ('paper_id', 'title')}, 'pdf_sources': pdf, 'instruction_boundary': '\u672c\u63d0\u53d6\u5668\u53ef\u8bfb\u76ee\u6807\u8bba\u6587，\u4f46\u8f93\u51fa\u7684\u4f5c\u8005\u7ed3\u679c\u548c\u65b9\u6cd5\u53ea\u80fd\u7559\u5728\u9694\u79bb\u533a；\u751f\u6210\u5668\u53ea\u80fd\u6536\u5230\u7a0b\u5e8f\u767d\u540d\u5355\u7684\u5355\u4e00H1\u548c\u6548\u5e94\u53e3\u5f84。\u6ca1\u6709\u63d0\u4f9b\u4f5c\u8005\u4ee3\u7801、\u65e7H1/\u5b57\u5178/\u65b9\u6848/\u7ed3\u679c，\u4e5f\u4e0d\u4f9d\u636e\u65e7\u8fd0\u884c\u4fbf\u5229\u6027\u9009H1。'}
    contract = {'h1': {'text': '\u4e00\u53e5\u53ef\u68c0\u9a8c\u547d\u9898，\u4e0d\u542b\u89c2\u5bdf\u5230\u7684\u6548\u5e94\u5927\u5c0f、P\u503c\u6216\u4f5c\u8005\u5206\u6790\u914d\u65b9；\u5e74\u4efd/\u4eba\u7fa4\u5982\u547d\u9898\u672c\u8eab\u5fc5\u8981\u53ef\u4fdd\u7559', 'status': 'author_numbered_hypothesis/author_unnumbered_claim/no_claim', 'author_label': None, 'original_quote': '\u9010\u5b57\u539f\u6587', 'source_id': 'pdf:N', 'section': '\u5b9e\u9645\u7ae0\u8282', 'kind': 'descriptive/associational/causal/other', 'selection_rationale': '\u53ea\u9009\u4e00\u6761\u7684\u7406\u7531'}, 'effect_scope': {'metric_family': '\u7edf\u8ba1\u91cf/\u6548\u5e94\u79cd\u7c7b；\u4e0d\u77e5\u9053\u5c31unknown', 'quantity': '\u6d4b\u91cf\u7684\u79d1\u5b66\u91cf，\u4e0d\u5305\u542b\u4f5c\u8005\u7ed3\u679c\u5927\u5c0f', 'contrast': '\u5bf9\u6bd4\u5b9a\u4e49，\u4e0d\u542b\u4f5c\u8005\u7279\u6709\u6a21\u578b/\u6743\u91cd/\u5220\u6837\u914d\u65b9', 'scale': '\u539f\u59cb/\u76f8\u5bf9\u53d8\u5316/\u5bf9\u6570\u7b49\u6548\u5e94\u8868\u793a', 'unit': '\u5355\u4f4d\u6216unknown', 'null_value': 0, 'definition': '\u4ec5\u7edf\u8ba1\u6548\u5e94\u53e3\u5f84\u7684\u901a\u7528\u5b9a\u4e49，\u4e0d\u80fd\u653e\u4f5c\u8005\u5206\u6790\u914d\u65b9', 'identification_limits': '\u4ec5\u53e3\u5f84\u4e0d\u8db3\u4e4b\u5904；\u4e0d\u80fd\u900f\u9732\u4f5c\u8005\u7ed3\u679c\u6570\u503c'}, 'author_reference': {'available': False, 'value': None, 'unit': None, 'kind': 'directly_reported/no_scalar_reported/figure_only', 'quote': '\u539f\u6587\u7ed3\u679c\u5f15\u6587\u6216null', 'source_id': 'pdf:N\u6216null', 'comparability_to_scope': '\u662f\u5426\u660e\u786e\u5bf9\u5e94\u540c\u4e00\u53e3\u5f84', 'uncertainty': '\u4e0d\u80fd\u51ed\u4ee3\u7801\u6216\u65e7\u7ed3\u679c\u8865\u4f5c\u8005\u503c'}, 'other_claims_not_selected': [], 'limitations': []}
    source = {s['source_id']: s['text'] for s in pdf}

    def validate(o):
        errs = []
        h = o.get('h1', {})
        ef = o.get('effect_scope', {})
        if h.get('status') not in ['author_numbered_hypothesis', 'author_unnumbered_claim', 'no_claim']:
            errs.append('h1 status invalid')
        if not h.get('text'):
            errs.append('h1 text missing')
        if h.get('status') != 'no_claim':
            q = lab.normalize(h.get('original_quote', ''))
            s = source.get(h.get('source_id'), '')
            if not q or q not in lab.normalize(s):
                errs.append('H1 original_quote must match supplied PDF literally after whitespace normalization')
        if set(ef) != set(contract['effect_scope']):
            errs.append('effect_scope fields must be exactly the public whitelist')
        if not isinstance(o.get('author_reference', {}).get('available'), bool):
            errs.append('author_reference.available must be boolean')
        return errs
    result = task('extract_single_target_and_effect_scope', '\u4f60\u662f\u4e0e\u65b9\u6848\u751f\u6210\u9694\u79bb\u7684\u8bba\u6587\u63d0\u53d6\u5668。\u4f18\u5148\u4f5c\u8005\u660e\u786e\u7f16\u53f7H1；\u6ca1\u6709\u5c31\u636e\u5b9e\u9009\u62e9\u4e00\u6761\u72ec\u7acb、\u539f\u6587\u53ef\u8ffd\u6eaf\u4e14\u9002\u5408\u72ec\u7acb\u68c0\u9a8c\u7684\u4e3b\u5f20，\u4e0d\u62fc\u591a\u4e2a\u53d1\u73b0，\u4e0d\u865a\u6784\u4f5c\u8005\u7f16\u53f7。\u63cf\u8ff0\u6027\u6570\u636e\u5e93\u8bba\u6587\u4e0d\u5f97\u6539\u6210\u56e0\u679c\u5047\u8bbe；\u5982\u4ec5\u6765\u81ea\u5df2\u62a5\u544a\u53d1\u73b0，status\u4e3aauthor_unnumbered_claim，\u4e0d\u80fd\u58f0\u79f0\u5148\u9a8c\u5047\u8bbe。\n\u6548\u5e94\u53e3\u5f84\u662f\u7528\u6237\u660e\u786e\u5141\u8bb8\u62ab\u9732\u7ed9\u751f\u6210\u5668\u7684\u6700\u5c0f\u5143\u4fe1\u606f：\u7c7b\u578b、\u79d1\u5b66\u91cf、\u5bf9\u6bd4、\u8868\u793a\u5c3a\u5ea6、\u5355\u4f4d、\u96f6\u503c、\u901a\u7528\u5b9a\u4e49\u548c\u53ef\u8fa8\u8bc6\u6027\u8fb9\u754c。\u4e25\u7981\u5728h1.text\u548ceffect_scope\u4e2d\u900f\u9732\u8bba\u6587\u89c2\u5bdf\u5230\u7684\u6548\u5e94\u503c、P\u503c、CI、\u4f18\u9009\u8bbe\u5b9a、\u4f5c\u8005\u6a21\u578b/\u6743\u91cd/\u63a7\u5236\u53d8\u91cf/\u7b5b\u6837\u4ee3\u7801。\n\u53ef\u5c06\u5bf9\u5e94\u4f5c\u8005\u7ed3\u679c\u6570\u503c\u5355\u72ec\u4fdd\u5b58author_reference，\u4f46\u4ec5\u4f7f\u7528\u672c\u6587\u660e\u786e\u62a5\u544a\u7684\u53ef\u6838\u5b9e\u7ed3\u679c；\u6ca1\u6709\u5355\u4e2a\u5bf9\u5e94\u6548\u5e94\u6216\u65e0\u6cd5\u786e\u8ba4\u53e3\u5f84，\u5c31available=false，\u6807\u660e\u7f3a\u5931/figure_only，\u4e0d\u80fd\u4ece\u4f5c\u8005\u4ee3\u7801、\u65e7\u5b9e\u9a8c\u6216\u60f3\u8c61\u4e2d\u8865\u51fa\u6570\u503c，\u4e5f\u4e0d\u80fd\u628a\u4e0d\u540c\u53c2\u7167\u671f/\u7edf\u8ba1\u91cf\u7684\u6570\u5b57\u5f3a\u914d\u7ed9\u672cH1。\u79d1\u5b66\u7c7b\u578b\u4e0d\u80fd\u4ec5\u56e0\u90fd\u65e0\u91cf\u7eb2\u5c31\u5ba3\u79f0\u4e00\u81f4。\n\u9009\u62e9H1\u53ca\u6548\u5e94\u53e3\u5f84\u65f6\u4f18\u5148\u672c\u8bba\u6587\u79d1\u5b66\u76ee\u7684，\u4e0d\u5f97\u57fa\u4e8e\u65e7\u4f5c\u8005\u8bbe\u5b9a、\u65e7\u5b9e\u9a8c\u5bc6\u5ea6\u6216\u6570\u503c\u547d\u4e2d\u5012\u63a8。\u53ea\u8f93\u51faJSON。', contract, material, validate, zone='target_extractor')
    if result['h1']['status'] == 'no_claim':
        raise RuntimeError('Target has no identifiable single claim; report the source limitation')
    save('h1_public.json', {k: result['h1'][k] for k in ('text', 'status', 'author_label', 'kind')})
    save('effect_scope_public.json', result['effect_scope'])
    save('target_public_release_receipt.json', {'source_zone': 'quarantined PDF extractor', 'h1_fields_released': ['text', 'status', 'author_label', 'kind'], 'effect_fields_released': list(contract['effect_scope']), 'original_quotes_results_methods_not_forwarded': True, 'author_numeric_reference_loaded_by_generator': False})
    event('public_target_metadata_released', h1_sha256=sha(OUT / 'h1_public.json'), effect_scope_sha256=sha(OUT / 'effect_scope_public.json'))

def data_semantics():
    prepare()
    if (OUT / 'clean_data_dictionary.json').exists():
        return
    profile = read('data_structure_profile.json')
    names = {c['name'] for c in profile['columns']}
    contract = {'columns': [{'name': '\u5b9e\u9645\u5217\u540d', 'meaning': '\u4ec5\u6570\u503c\u6d4b\u91cf\u542b\u4e49；\u4e0d\u77e5\u9053\u5c31\u672a\u77e5', 'semantic_core_english': '\u82f1\u6587\u7eaf\u503c\u8bed\u4e49；\u4e0d\u77e5\u9053Unknown meaning', 'unit': None, 'role': '\u4ec5\u6570\u636e\u89d2\u8272，\u4e0d\u63a8\u8350\u5206\u6790\u65b9\u6cd5', 'certainty': 'inferred_from_name_and_values/unknown', 'uncertainty': '\u65e0\u72ec\u7acb\u4ee3\u7801\u672c\u8bc1\u5b9e\u65f6\u7684\u8fb9\u754c'}], 'dataset_interpretation': '\u53ea\u636e\u8868\u683c\u89c2\u5bdf，\u4e0d\u80fd\u5ba3\u79f0\u4f5c\u8005\u65b9\u6cd5\u5df2\u77e5', 'limitations': []}

    def validate(o):
        cs = o.get('columns', [])
        if len(cs) != len(names) or {c.get('name') for c in cs} != names:
            return ['Return each actual column exactly once']
        return [] if all((c.get('certainty') in ('inferred_from_name_and_values', 'unknown') and c.get('semantic_core_english') for c in cs)) else ['All semantics are inferred or unknown; no documented certainty without a codebook']
    task('clean_data_dictionary', '\u4f60\u53ea\u6536\u5230\u539f\u59cbCSV\u7684\u5217\u540d、\u7c7b\u578b、\u7f3a\u5931/\u8303\u56f4/\u5206\u4f4d\u6570\u53ca\u524d12\u884c。\u6ca1\u6709H1、\u8bba\u6587、\u4f5c\u8005\u4ee3\u7801、\u4ee5\u524d\u5217\u5b57\u5178。\u6839\u636e\u8fd9\u4e9b\u6570\u636e\u672c\u8eab\u4fdd\u5b88\u89e3\u91ca\u6bcf\u5217\u503c\u6d4b\u91cf\u4ec0\u4e48；\u4e0d\u63a8\u65ad\u4f5c\u8005\u5206\u6790\u7528\u9014，\u4e0d\u63a8\u8350Gini\u6216\u6743\u91cd\u7528\u6cd5，\u4e0d\u5f15\u7528\u4efb\u4f55\u8bba\u6587/\u56fe/\u4ee3\u7801，\u4e0d\u51ed\u9884\u8bad\u7ec3\u8bb0\u5fc6\u6062\u590d\u539f\u8bba\u6587。\u65e0\u72ec\u7acb\u4ee3\u7801\u672c，\u56e0\u6b64\u4e0d\u80fd\u58f0\u79f0documented；\u542b\u4e49\u53ef\u5408\u7406\u63a8\u6d4b\u5219\u6807inferred_from_name_and_values，\u4e0d\u80fd\u786e\u5b9a\u5c31unknown，\u5355\u4f4d\u4e5f\u4e0d\u80fd\u786e\u5b9a\u5c31null。\u5b57\u6bb5\u672c\u6765\u6d4b\u91cf\u67d0\u79cd\u7edf\u8ba1\u91cf\u5982gini\u53ef\u5982\u5b9e\u89e3\u91ca\u5176\u53ef\u80fd\u8eab\u4efd，\u4f46\u4e0d\u80fd\u628a\u8be5\u5b57\u6bb5\u8eab\u4efd\u5f53\u6210\u63a8\u8350\u5206\u6790\u65b9\u6cd5。\u82f1\u6587\u6838\u5fc3\u63cf\u8ff0\u5fc5\u987b\u4ec5\u4e3a\u5217\u503c\u8bed\u4e49，\u4e0d\u542bH1、\u65b9\u6cd5\u7528\u9014\u6216\u5386\u53f2\u76ee\u6807。', contract, {'raw_data_measurements': profile}, validate, zone='clean_data_only')

def historical_preparation():
    prepare()
    import neo4j_twenty as db
    rows = db.query('MATCH (b:DAG20:ColumnBinding {import_scope:$scope}) RETURN b.uid AS uid,b.logical_id AS binding_ref,b.name AS column_name,b.meaning AS meaning,b.paper_alias AS paper ORDER BY binding_ref', {'scope': db.SCOPE})
    assert len(rows) == 3507
    texts = list(dict.fromkeys((r['meaning'] for r in rows)))
    allowed = set(texts)
    if (OUT / 'historical_semantics.json').exists():
        return
    old = ROOT / 'outputs/Neo4j_ColumnBinding_Provenance_v2_20261025'
    core = {}
    receipts = []
    for provenance in sorted(old.glob('column_semantic_core_english_*_provenance.json')):
        pr = lab.read(provenance)
        cache = old / 'cache' / pr['cache_key']
        reqs = sorted(cache.glob('request_*.json'))
        if not reqs:
            continue
        request = lab.read(reqs[0])
        try:
            payload = json.loads(request['messages'][1]['content'])
            material = payload['source_material']
            entries = material['columns']
        except (KeyError, TypeError):
            continue
        pure = set(material) == {'columns'} and all((set(e) == {'id', 'meaning'} and e['meaning'] in allowed for e in entries))
        receipts.append({'stage': provenance.stem, 'history_only': pure, 'source_request_sha256': sha(reqs[0]), 'entries': len(entries), 'cache_key': pr['cache_key']})
        if not pure:
            continue
        answer = lab.read(cache / 'accepted.json')
        answer = answer.get('output_contract', answer) if 'records' not in answer else answer
        mapped = {r['id']: r['core_meaning'] for r in answer['records']}
        for e in entries:
            core[e['meaning']] = mapped[e['id']]
        dst = OUT / 'history_only_cache_ancestors' / provenance.stem
        dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(reqs[0], dst / 'request.json')
        lab.save(dst / 'accepted.json', answer)
    missing = [t for t in texts if t not in core]
    batches = [missing[i:i + 250] for i in range(0, len(missing), 250)]

    def run(pair):
        index, batch = pair
        entries = [{'id': str(i), 'meaning': t} for i, t in enumerate(batch)]
        contract = {'records': [{'id': '\u539fid', 'core_meaning': '\u7eaf\u503c\u8bed\u4e49\u82f1\u6587\u4e00\u53e5\u8bdd'}]}

        def validate(o):
            rs = o.get('records', [])
            return [] if len(rs) == len(entries) and {r.get('id') for r in rs} == {e['id'] for e in entries} and all((r.get('core_meaning') for r in rs)) else ['Cover every history id exactly once with nonempty core_meaning']
        answer = task('history_value_semantics_' + str(index), '\u53ea\u6536\u5230\u539f20\u7bc7\u5386\u53f2\u5217meaning，\u4e0d\u542b\u76ee\u6807\u8bba\u6587\u4fe1\u606f。\u4ec5\u63d0\u70bc\u5217\u4e2d\u6570\u503c/\u7c7b\u522b\u672c\u8eab\u7684\u8bed\u4e49，\u7edf\u4e00\u82f1\u6587；\u4fdd\u7559\u672c\u6765\u5c31\u6784\u9020\u597d\u7684\u7edf\u8ba1\u91cf\u8eab\u4efd\u53ca\u5df2\u8bf4\u660e\u5355\u4f4d/\u5c42\u7ea7，\u5220\u9664\u5206\u6790\u7528\u9014、\u65b9\u6cd5\u6d41\u7a0b、H1、\u56fe\u53f7、\u4ee3\u7801、\u7ed3\u679c\u548c\u53c2\u6570。\u4e0d\u8981\u51ed\u7528\u9014\u63a8\u6d4b\u672a\u77e5\u7684\u6d4b\u91cf\u542b\u4e49。', contract, {'columns': entries}, validate, zone='history_only')
        mapped = {r['id']: r['core_meaning'] for r in answer['records']}
        return {e['meaning']: mapped[e['id']] for e in entries}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for mapped in pool.map(run, enumerate(batches)):
            core.update(mapped)
    assert set(core) == allowed
    save('historical_semantics.json', {'rows': [{**r, 'semantic_core': core[r['meaning']]} for r in rows], 'independent_ancestor_checks': receipts, 'reused_history_only_requests': sum((r['history_only'] for r in receipts)), 'rejected_mixed_ancestor_requests': sum((not r['history_only'] for r in receipts)), 'new_history_only_meanings': len(missing), 'target_semantics_or_rankings_reused': False})
    event('historical_value_semantics_ready', bindings=len(rows), new_meanings=len(missing))

def foundation():
    prepare()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(f) for f in (target_metadata, data_semantics, historical_preparation)]
        for future in futures:
            future.result()
    print('FOUNDATION READY', flush=True)

def refined_scope():
    if (OUT / 'refined_effect_scope.json').exists():
        return
    ef = read('effect_scope_public.json')
    h = read('h1_public.json')
    contract = {'effect_scope': {k: v for k, v in ef.items()}, 'changes': [], 'limitations': []}

    def validate(o):
        return [] if set(o.get('effect_scope', {})) == set(ef) and all((o['effect_scope'].get(k) for k in ('metric_family', 'quantity', 'contrast', 'scale', 'unit', 'definition'))) else ['Keep exactly the public effect-scope schema and define a usable common effect']
    result = task('refine_public_effect_contract', '\u53ea\u63a5\u6536\u5141\u8bb8\u62ab\u9732\u7684\u5355\u4e00H1、\u6548\u5e94\u53e3\u5f84\u8349\u7a3f\u548c\u539f\u59cbData\u7279\u5f81，\u6ca1\u6709\u76ee\u6807PDF、\u4f5c\u8005\u65b9\u6cd5\u6216\u6570\u503c。\u5c06“\u4f8b\u5982/\u7c7b\u4f3c\u6307\u6807”\u7b49\u6a21\u7cca\u8868\u8ff0\u6574\u7406\u4e3a\u53ef\u68c0\u9a8c、\u53ef\u6bd4\u8f83\u7684\u4e00\u79cd\u6838\u5fc3\u6548\u5e94\u53e3\u5f84\u53ca\u53ef\u516c\u5f00\u5141\u8bb8\u7684\u6570\u5b66\u8868\u793a\u53d8\u4f53，\u4e0d\u80fd\u628aGini、\u65b9\u5dee、\u76f8\u5173\u7cfb\u6570\u4ec5\u56e0\u65e0\u91cf\u7eb2\u653e\u5728\u540c\u4e00\u7eb5\u8f74。\u6548\u5e94\u5b9a\u4e49\u987b\u660e\u786e\u79d1\u5b66\u5bf9\u8c61、\u5dee\u6216\u6bd4/\u901f\u7387/\u6c34\u5e73\u533a\u522b、\u5355\u4f4d；\u5e74\u4efd/\u7a7a\u95f4\u5c42\u7ea7\u53ea\u53d6H1\u548c\u7ed9\u5b9aData\u53ef\u8fa8\u8bc6\u5185\u5bb9。\u82e5H1\u672a\u552f\u4e00\u89c4\u5b9a\u64cd\u4f5c\u5316，\u660e\u786e\u7531\u672c\u8f6e\u63d0\u51fa\u800c\u975e\u4f5c\u8005\u5df2\u6307\u5b9a；\u4e0d\u8981\u628a\u6570\u636e\u7f3a\u5c11\u660e\u6587\u4ee3\u7801\u672c\u63a8\u65ad\u6210\u4f5c\u8005\u65b9\u6848。\u4e0d\u8981\u5728\u6548\u5e94\u53e3\u5f84\u4e2d\u9884\u5b9a\u4f5c\u8005\u5f0f\u6837\u672c\u6743\u91cd、\u5177\u4f53\u6a21\u578b、\u63a7\u5236\u53d8\u91cf\u6216\u5f02\u5e38\u503c\u5220\u9664\u914d\u65b9。\u5c3d\u53ef\u80fd\u7ed9\u540e\u7eed\u5408\u7406\u5904\u7406/\u4f30\u8ba1\u5668\u9009\u62e9\u7559\u4e0b\u7a7a\u95f4，\u4e0d\u56e0\u4e3a\u65b9\u6848\u672a\u5b8c\u5168\u76f8\u540c\u5c31\u8fc7\u5ea6\u62c6\u5206；\u4f46\u5171\u540c\u76ee\u6807\u4e0e\u91cf\u7eb2\u987b\u4e00\u81f4。\u53ea\u8f93\u51fa\u5143\u5b9a\u4e49，\u4e0d\u63d0\u51fa\u5b8c\u6574\u5206\u6790\u65b9\u6848。', contract, {'h1': h, 'allowed_effect_scope_draft': ef, 'clean_data_dictionary': read('clean_data_dictionary.json'), 'data_measurements': read('data_structure_profile.json')}, validate, zone='public_metadata_only')
    save('refined_effect_scope.json', result)
    event('effect_contract_refined_without_author_private_material')

def history_catalog(decision_ids):
    frozen = lab.read(BASE / '\u5c55\u793a\u6570\u636e\u5feb\u7167.json')
    papers = {p['alias']: p for p in frozen['papers']}
    rows = {r['source_ref']: r for r in frozen['classification']['rows']}
    methods = {m['id']: m for m in frozen['classification']['methods']}
    catalog = {}
    for ref, orig in frozen['original_options'].items():
        dref = orig['decision_ref']
        if dref not in decision_ids:
            continue
        p = papers[orig['paper']]
        d = next((d for d in p['space']['decisions'] if dref.endswith(':' + d['id'])))
        catalog.setdefault(dref, {'kind': 'Decision', 'ref': dref, 'paper_alias': p['alias'], 'name': d['label'], 'question': d['why_a_decision'], 'stage': d['stage'], 'option_refs': []})
        catalog[dref]['option_refs'].append(ref)
        catalog[ref] = {'kind': 'Option', 'ref': ref, 'decision_ref': dref, 'paper_alias': p['alias'], 'option': orig['option'], 'component_refs': [], 'option_parameters': rows[ref].get('option_parameters', []), 'constraints': orig.get('original_forbidden_combinations', [])}
        for comp in rows[ref]['components']:
            cref = ref + '/' + comp['id']
            mid = comp['method_id']
            en = frozen['enriched_components'][cref]
            catalog[ref]['component_refs'].append(cref)
            catalog[cref] = {'kind': 'Component', 'ref': cref, 'option_ref': ref, 'decision_ref': dref, 'method_id': mid, 'classification': comp, 'parameters': en['parameters'], 'columns': en['data_columns']}
            catalog[mid] = {'kind': 'Method', 'ref': mid, 'record': methods[mid]}
    return catalog

def retrieve():
    if (OUT / 'five_inputs.json').exists():
        return
    foundation()
    refined_scope()
    import neo4j_twenty as db
    from structured_retrieval import Encoder
    encoder = Encoder()
    encoder.tokenizer.no_padding()
    encoder.tokenizer.no_truncation()
    raw_encode = encoder.encode
    encoder.encode = lambda docs: np.stack([raw_encode([d])[0] for d in docs])
    h1 = read('h1_public.json')
    dictionary = read('clean_data_dictionary.json')
    cols = {c['name']: c for c in dictionary['columns']}
    contract = {'top5': [{'rank': 1, 'name': '\u5b9e\u9645\u5217\u540d', 'reason': '\u4ec5\u636eH1\u4e0e\u5217\u503c\u8bed\u4e49\u7684\u76f8\u5173\u6027，\u672a\u77e5\u542b\u4e49\u8c28\u614e'}], 'limitations': []}

    def validate(o):
        rs = o.get('top5', [])
        return [] if len(rs) == 5 and len({r.get('name') for r in rs}) == 5 and all((r.get('name') in cols for r in rs)) and (sorted((r.get('rank') for r in rs)) == [1, 2, 3, 4, 5]) else ['Rank exactly five distinct actual columns with ranks 1..5']
    ranking = task('fresh_column_ranking', '\u6839\u636e\u4e00\u4e2aH1，\u4ece\u5168\u90e8\u5e72\u51c0\u5217\u503c\u8bed\u4e49\u53ca\u5b9e\u9645\u6570\u636e\u7279\u5f81\u9009\u76f8\u5173\u6027\u6700\u9ad8\u76845\u5217\u5e76\u6392\u5e8f。\u4f60\u6ca1\u6709\u8bba\u6587、\u4f5c\u8005\u4ee3\u7801、\u4f5c\u8005\u7ed3\u679c\u6216\u65e7\u6392\u5e8f。\u4e0d\u8981\u628a\u63a8\u6d4b\u8bed\u4e49\u5f53\u6587\u6863\u4e8b\u5b9e；\u660e\u786e\u6807\u8bc6\u7b26\u4e0e\u79d1\u5b66\u6d4b\u91cf\u91cf\u7684\u4f5c\u7528，\u4e0d\u80fd\u628a\u5730\u533a\u5185\u4e0d\u5e73\u7b49\u76f4\u63a5\u89c6\u4e3a\u5730\u533a\u95f4\u4e0d\u5e73\u7b49。\u53ea\u9009\u5217，\u4e0d\u63a8\u8350\u4f5c\u8005\u914d\u65b9\u6216\u540e\u9a8c\u6570\u503c。', contract, {'h1': h1, 'clean_data_dictionary': dictionary, 'data_measurements': read('data_structure_profile.json')}, validate, zone='clean_ranking_only')
    rows = read('historical_semantics.json')['rows']
    unique = list(dict.fromkeys((r['semantic_core'] for r in rows)))
    vecpath = OUT / 'history_vectors.npz'
    if vecpath.exists():
        cached = np.load(vecpath, allow_pickle=False)
        assert cached['texts'].tolist() == unique
        vectors = cached['vectors']
    else:
        old = np.load(ROOT / 'outputs/Neo4j_ColumnBinding_Provenance_v2_20261025/column_binding_embeddings.npz', allow_pickle=False)
        existing = {t: v for t, v in zip(old['texts'].tolist(), old['vectors'])}
        computed = {}
        for i, text in enumerate(unique):
            computed[text] = existing[text] if text in existing else encoder.encode([text])[0]
            if i % 300 == 0:
                print('History embeddings', i, '/', len(unique), flush=True)
        vectors = np.stack([computed[t] for t in unique])
        np.savez_compressed(vecpath, texts=np.array(unique), vectors=vectors)
        save('embedding_cache_receipt.json', {'exact_historical_text_vectors_reused': sum((t in existing for t in unique)), 'new_history_text_vectors': sum((t not in existing for t in unique)), 'policy': 'Only exact historical strings, single-document encodings. No prior target query/ranking/route is reused.', 'model': encoder.manifest, 'hidden_tokenizer_padding': None, 'hidden_tokenizer_truncation': None})
    vecs = dict(zip(unique, vectors))
    run = RETRIEVAL_RUN_ID
    label = 'BlindHistoryColumnVectorV7'
    node_records = [{'uid': run + ':' + r['binding_ref'], 'target_uid': r['uid'], 'run_id': run, 'text': r['semantic_core'], 'binding_ref': r['binding_ref'], 'embedding': vecs[r['semantic_core']].tolist()} for r in rows]
    for offset in range(0, len(node_records), 100):
        db.query(f'UNWIND $rows AS row MATCH (b:DAG20:ColumnBinding {{uid:row.target_uid}}) MERGE (v:{label} {{uid:row.uid}}) SET v += row MERGE (v)-[:EMBEDDING_OF]->(b) RETURN count(v) AS count', {'rows': node_records[offset:offset + 100]})
    db.query(f"CREATE VECTOR INDEX blind_history_column_v7 IF NOT EXISTS FOR (v:{label}) ON (v.embedding) OPTIONS {{indexConfig: {{`vector.dimensions`:384,`vector.similarity_function`:'cosine'}}}}")
    graph_nodes = db.query('MATCH (d:DAG20:Decision {import_scope:$scope}) RETURN d.logical_id AS id,d.name AS name,d.paper_alias AS paper,d.method AS method,d.parameters AS parameters,d.column_semantics AS column_semantics,d.h1 AS h1', {'scope': db.SCOPE})
    graph_edges = db.query('MATCH (a:DAG20:Decision {import_scope:$scope})-[r:DECISION_DEPENDENCY]->(b:DAG20:Decision) RETURN a.logical_id AS from,b.logical_id AS to,r.reason AS reason', {'scope': db.SCOPE})
    save('full_original_graph.json', {'nodes': graph_nodes, 'edges': graph_edges})
    lookup = {n['id']: n for n in graph_nodes}
    per = []
    union_ids = set()
    union_edges = {}
    views = []
    query = f'MATCH (v:{label} {{run_id:$run}})-[:EMBEDDING_OF]->(b:DAG20:ColumnBinding)\n      WITH b,v.text AS semantic_core,vector.similarity.cosine(v.embedding,$vector) AS score ORDER BY score DESC,b.logical_id LIMIT 3\n      MATCH (d:DAG20:Decision)-[:HAS_OPTION]->(o:DAG20:Option)-[:HAS_COMPONENT]->(c:DAG20:Component)-[:HAS_COLUMN]->(b)\n      MATCH (c)-[:USES_METHOD]->(m:DAG20:Method)\n      RETURN b.logical_id AS binding_ref,b.name AS column_name,b.meaning AS raw_historical_meaning,semantic_core,score,\n       d.logical_id AS id,d.name AS name,d.paper_alias AS paper,o.logical_id AS option_ref,c.logical_id AS component_ref,m.id AS method_id,m.name AS method_name ORDER BY score DESC,binding_ref'
    for top in sorted(ranking['top5'], key=lambda r: r['rank']):
        col = cols[top['name']]
        qtext = col['semantic_core_english']
        vector = encoder.encode([qtext])[0]
        hits = db.query(query, {'run': run, 'vector': vector.tolist()})
        assert len(hits) == 3
        retained = {h['id'] for h in hits}
        edges = {}
        paths = []
        for seed in sorted(retained.copy()):
            found = db.query('MATCH p=(d:DAG20:Decision {import_scope:$scope,logical_id:$seed})-[:DECISION_DEPENDENCY*1..2]->(b:DAG20:Decision) RETURN [n IN nodes(p)|n.logical_id] AS nodes,[e IN relationships(p)|{from:startNode(e).logical_id,to:endNode(e).logical_id,reason:e.reason}] AS edges', {'scope': db.SCOPE, 'seed': seed})
            hop = {seed: 0}
            for path in found:
                assert 1 <= len(path['edges']) <= 2
                paths.append({'seed': seed, **path})
                retained.update(path['nodes'])
                for i, n in enumerate(path['nodes']):
                    hop[n] = min(hop.get(n, i), i)
                for e in path['edges']:
                    edges[e['from'], e['to']] = e
            states = {(seed, 0)}
            state_edges = set()
            for path in found:
                for i, n in enumerate(path['nodes']):
                    states.add((n, i))
                for i, e in enumerate(path['edges']):
                    state_edges.add((e['from'], i, e['to'], i + 1))
            views.append({'column': col['name'], 'seed': seed, 'paths': found, 'hop_minimum': hop, 'states': [{'id': n + '@' + str(i), 'logical_id': n, 'hop': i} for n, i in sorted(states, key=lambda x: (x[1], x[0]))], 'state_edges': [{'from': a + '@' + str(i), 'to': b + '@' + str(j)} for a, i, b, j in sorted(state_edges)]})
        union_ids.update(retained)
        union_edges.update(edges)
        per.append({'rank': top['rank'], 'column': col, 'ranking_reason': top['reason'], 'query_text': qtext, 'hits': hits, 'retained_ids': sorted(retained), 'paths': paths, 'edges': list(edges.values()), 'unique_seed_decisions': len({h['id'] for h in hits})})
    route_a = {'protocol': {'column_k': 3, 'max_outgoing_hops': 2, 'ranking_unit': 'ColumnBinding', 'embedding_fields': 'data-value semantic core only', 'edge_policy': 'actual traversed path-edge union; no induced extra edges', 'combined_graph_warning': 'Multiple two-hop path unions may contain longer chains; seed views are explicitly unrolled into hops 0/1/2.'}, 'per_column': per, 'combined': {'nodes': [lookup[i] for i in sorted(union_ids)], 'edges': list(union_edges.values())}, 'seed_views': views}
    hypotheses = []
    ancestor = []
    frozen = lab.read(BASE / '\u5c55\u793a\u6570\u636e\u5feb\u7167.json')
    for paper in frozen['papers']:
        alias = paper['alias']
        folder = ROOT / 'outputs/Single_H1_Multiverse_v3_20261025/model_tasks' / ('h1_' + alias)
        text = paper['research_context']['h1']['text']
        record = {'text': text, 'status': 'original_frozen_historical_h1', 'author_label': None}
        provenances = list(folder.glob('*_provenance.json')) if folder.exists() else []
        if provenances:
            pr = lab.read(provenances[0])
            cache = folder / 'cache' / pr['cache_key']
            req = lab.read(sorted(cache.glob('request_*.json'))[0])
            payload = json.loads(req['messages'][1]['content'])['source_material']
            if payload.get('paper', {}).get('alias') == alias and 'author_code_sources' not in payload:
                ans = lab.read(cache / 'accepted.json')
                ans = ans.get('output_contract', ans) if 'target' not in ans else ans
                record = ans['target']
                text = record['target_text']
                ancestor.append({'paper': alias, 'history_only': True, 'cache_key': pr['cache_key']})
        hypotheses.append({'id': alias + ':H1', 'paper': alias, 'h1': text, 'record': record})
    hvec = encoder.encode([h['h1'] for h in hypotheses])
    qvec = encoder.encode([h1['text']])[0]
    for h, v in zip(hypotheses, hvec):
        h['embedding'] = v.tolist()
    for offset in range(0, len(hypotheses), 50):
        data = [{'uid': run + ':' + h['id'], 'target_uid': db.SCOPE + ':H1:' + h['id'], 'run_id': run, 'logical_id': h['id'], 'paper': h['paper'], 'text': h['h1'], 'embedding': h['embedding']} for h in hypotheses[offset:offset + 50]]
        db.query('UNWIND $rows AS row MATCH (h:DAG20:H1 {uid:row.target_uid}) MERGE (v:BlindHistoryH1VectorV7 {uid:row.uid}) SET v += row MERGE (v)-[:EMBEDDING_OF]->(h) RETURN count(v) AS count', {'rows': data})
    btop = db.query('MATCH (v:BlindHistoryH1VectorV7 {run_id:$run}) RETURN v.logical_id AS id,v.paper AS paper,v.text AS h1,vector.similarity.cosine(v.embedding,$vector) AS score ORDER BY score DESC,id LIMIT 3', {'run': run, 'vector': qvec.tolist()})
    matches = []
    b_decisions = set()
    for hit in btop:
        records = db.query('MATCH (d:DAG20:Decision {import_scope:$scope,paper_alias:$paper})-[:HAS_OPTION]->(o:DAG20:Option)-[:HAS_COMPONENT]->(c:DAG20:Component)-[:USES_METHOD]->(m:DAG20:Method) RETURN d.logical_id AS decision_ref,o.logical_id AS option_ref,c.logical_id AS component_ref,m.id AS method_id,m.name AS method_name,m.kind AS kind,m.record_json AS method_record,c.record_json AS component_record,c.enrichment_json AS enrichment ORDER BY component_ref', {'scope': db.SCOPE, 'paper': hit['paper']})
        for r in records:
            r['method_record'] = json.loads(r['method_record'])
            r['component_record'] = json.loads(r['component_record'])
            r['enrichment'] = json.loads(r['enrichment'])
            b_decisions.add(r['decision_ref'])
        matches.append({'h1_hit': hit, 'historical_methods': records})
    route_b = {'h1_query': h1['text'], 'top_k': 3, 'matches': matches, 'association_limit': 'All method components of matched historical papers are returned as candidates; no claim that every one directly tests that single historical H1. Roles are separately audited.', 'historical_h1_ancestor_checks': ancestor, 'historical_hypotheses': [{k: v for k, v in h.items() if k != 'embedding'} for h in hypotheses]}
    pool = history_catalog(union_ids | b_decisions)
    route_a['retrieved_historical_source_catalog'] = {k: v for k, v in pool.items() if v.get('decision_ref', v.get('ref')) in union_ids or v.get('kind') == 'Method'}
    route_b['retrieved_historical_source_catalog'] = {k: v for k, v in pool.items() if v.get('decision_ref', v.get('ref')) in b_decisions or v.get('kind') == 'Method'}
    save('route_a.json', route_a)
    save('route_b.json', route_b)
    save('historical_source_catalog.json', pool)
    packet = dict(zip(KEYS, [h1, {'columns': dictionary['columns'], 'dataset_interpretation': dictionary['dataset_interpretation'], 'measurements': read('data_structure_profile.json'), 'csv_sha256': sha(OUT / 'data.csv'), 'full_csv_for_execution': 'data.csv', 'dictionary_limitations': dictionary['limitations']}, route_a, route_b, {'contract': read('refined_effect_scope.json')['effect_scope'], 'derived_current_trial': {}}]))
    save('five_inputs.json', packet)
    save('public_inputs_lock.json', {'utc': now(), 'sha256': sha(OUT / 'five_inputs.json'), 'data_sha256': sha(OUT / 'data.csv'), 'source_slots': KEYS, 'old_target_ranks_or_routes_reused': False})
    save('retrieval_verification.json', {'new_top5': [r['name'] for r in ranking['top5']], 'bindings': 3507, 'nodes': len(union_ids), 'edges': len(union_edges), 'seed_views': len(views), 'all_saved_paths_hops_at_most_two': all((len(p['edges']) <= 2 for c in per for p in c['paths'])), 'only_traversed_edges_used': True, 'old_DAG20_nodes_modified': False, 'history_source_refs': len(pool), 'historical_method_ids': len([v for v in pool.values() if v['kind'] == 'Method'])})
    event('five_inputs_frozen', packet_sha256=sha(OUT / 'five_inputs.json'), nodes=len(union_ids), edges=len(union_edges))
    print('FIVE INPUTS READY', len(pool), 'source records', flush=True)

def seal_inputs():
    """Correct an over-prescriptive metadata draft before any scientific plan is generated."""
    retrieve()
    if (OUT / 'clean_five_inputs_sealed.json').exists():
        return
    initial = read('effect_scope_public.json')
    contract = {'effect_scope': copy.deepcopy(initial), 'boundary_notes': []}

    def validate(o):
        ef = o.get('effect_scope', {})
        errors = []
        if set(ef) != set(initial):
            errors.append('Keep precisely the effect metadata whitelist')
        text = json.dumps(ef, ensure_ascii=False)
        if re.search('`(?:mean|median|gini|hhlds|year|czone)`|Fig\\.?\\s*\\d|\\.R\\b|::', text):
            errors.append('No target CSV binding, figure reference or code recipe in the effect-type-only contract')
        return errors
    result = task('minimal_effect_type_contract', '\u5c06\u8fd9\u4efd\u5df2\u5141\u8bb8\u62ab\u9732\u7684\u6548\u5e94\u5143\u4fe1\u606f\u660e\u786e\u4e3a\u4e00\u79cd\u53ef\u6267\u884c\u7684\u6838\u5fc3\u6548\u5e94\u7c7b\u578b\u4e0e\u5408\u6cd5\u7b80\u5355\u6570\u5b66\u53d8\u4f53，\u4e0d\u8bfb\u53d6Data、\u4e0d\u8bfb\u53d6\u4f5c\u8005\u65b9\u6cd5\u6216\u6570\u503c，\u4e0d\u8bbe\u8ba1\u5206\u6790\u65b9\u6848。\u53ea\u8bf4\u660e\u79d1\u5b66\u91cf、\u7edf\u8ba1\u91cf\u79cd\u7c7b、\u5dee/\u6bd4/\u901f\u7387\u533a\u522b、\u5355\u4f4d\u53ca\u6548\u5e94\u6982\u5ff5\u5b9a\u4e49。H1\u5305\u542b\u7684\u65f6\u95f4\u53c2\u7167\u53ef\u4ee5\u4fdd\u7559，\u4f46\u4e0d\u5f97\u6307\u5b9aCSV\u5217\u540d、\u6743\u91cd、\u6837\u672c\u5254\u9664、\u4f30\u8ba1\u5668、\u6a21\u578b、\u63a7\u5236\u53d8\u91cf、\u4ee3\u8868\u503c\u9009\u62e9\u6216\u9700\u8981\u6309\u4ec0\u4e48Decision\u62c6\u7ec4。\u4e0d\u8981\u5199“\u5982Gini\u6216\u7c7b\u4f3c\u6307\u6807”\u4f7f\u4e0d\u540c\u7edf\u8ba1\u91cf\u6df7\u4e3a\u4e00\u7c7b；\u4e0d\u80fd\u786e\u8ba4\u7edf\u8ba1\u91cf\u5219\u8bda\u5b9e\u5199\u672a\u77e5。\u4e0d\u8981\u628a\u672c\u8f6e\u63d0\u8bae\u7684\u5177\u4f53\u64cd\u4f5c\u5316\u63cf\u8ff0\u6210\u4f5c\u8005\u5b9a\u4e49。\u539f\u59cb\u5b57\u6bb5\u5982unit\u7406\u8bba\u8303\u56f4\u82e5\u4e0d\u666e\u904d\u6210\u7acb，\u5e94\u8c28\u614e\u8bf4\u660e\u6761\u4ef6；\u6709\u8d1f\u503c\u7684\u8d22\u5bccGini\u4e0d\u4fdd\u8bc10–1。\u7ed9\u540e\u7eed\u5408\u7406\u5206\u6790\u9009\u62e9\u7559\u7a7a\u95f4，\u4e0d\u80fd\u5728\u5143\u5b9a\u4e49\u5185\u66ff\u751f\u6210\u5668\u9884\u5148\u7ed1\u5b9a\u67d0\u4e2a\u6570\u636e\u5217。', contract, {'h1': read('h1_public.json'), 'allowed_effect_metadata': initial}, validate, zone='effect_definition_only')
    archive = OUT / 'input_packet_revision_0'
    archive.mkdir(exist_ok=True)
    for name in ['five_inputs.json', 'public_inputs_lock.json', 'refined_effect_scope.json']:
        shutil.copy2(OUT / name, archive / name)
    original = read('five_inputs.json')
    pool = read('historical_source_catalog.json')
    projected = {}
    for ref, record in pool.items():
        r = copy.deepcopy(record)
        if r['kind'] == 'Component':
            r['columns'] = [{k: v for k, v in c.items() if k in ('name', 'meaning', 'role', 'unit', 'availability', 'evidence', 'uncertainty')} for c in r['columns']]
        projected[ref] = r
    a = copy.deepcopy(original[KEYS[2]])
    b = copy.deepcopy(original[KEYS[3]])
    a.pop('retrieved_historical_source_catalog', None)
    b.pop('retrieved_historical_source_catalog', None)
    for node in a['combined']['nodes']:
        dref = node['id']
        components = [v for v in projected.values() if v.get('kind') == 'Component' and v.get('decision_ref') == dref]
        node['method'] = [{'method_id': v['method_id'], 'component_ref': v['ref']} for v in components]
        node['parameters'] = {'resolve_component_parameters': [v['ref'] for v in components]}
        node['column_semantics'] = {'resolve_component_columns': [v['ref'] for v in components]}
        node['h1'] = {'historical_h1_ref': node['paper'] + ':H1'}
    for match in b['matches']:
        match['historical_methods'] = [{k: v for k, v in r.items() if k not in ('enrichment', 'component_record', 'method_record')} for r in match['historical_methods']]
    a['historical_source_catalog'] = projected
    b['source_resolution'] = 'Method/Component/Option refs resolve to input_3_route_a.historical_source_catalog; these are retrieved historical A/B records, not target-paper sources.'
    a['projection_note'] = 'Four node fields are preserved as explicit structured references into the one complete projected catalog. Raw visual graph is separately available. Only generic measured_features/h1_relation fields of historical columns were omitted; supplied name/meaning/role/unit/availability/evidence remain.'
    packet = copy.deepcopy(original)
    packet[KEYS[2]] = a
    packet[KEYS[3]] = b
    packet[KEYS[4]] = {'contract': result['effect_scope'], 'derived_current_trial': {}}
    save('five_inputs.json', packet)
    save('public_inputs_lock.json', {'utc': now(), 'sha256': sha(OUT / 'five_inputs.json'), 'data_sha256': sha(OUT / 'data.csv'), 'source_slots': KEYS, 'input_revision': 1, 'old_target_ranks_or_routes_reused': False})
    save('clean_five_inputs_sealed.json', {'utc': now(), 'five_inputs_sha256': sha(OUT / 'five_inputs.json'), 'previous_input_revision_preserved': True, 'changes': ['Removed model-proposed CSV bindings and split rules from effect-type metadata before any plan generation', 'Historical evidence de-duplicated by explicit references; full raw records retained for inspection'], 'author_numeric_candidates_policy': 'Multiple candidates may be extracted in quarantine from paper+H1; no candidate numbers or preferred author analysis enter these five inputs; comparison only after plan/code/results freeze.'})
    event('clean_five_inputs_sealed', revision=1, bytes=(OUT / 'five_inputs.json').stat().st_size)

def packet(derived=None):
    result = copy.deepcopy(read('five_inputs.json'))
    result[KEYS[4]]['derived_current_trial'] = derived or {}
    return result

def verified_effect_scope():
    seal_inputs()
    if (OUT / 'effect_type_sealed_v2.json').exists():
        return
    fields = {k: '\u6309\u5141\u8bb8\u8d44\u6599\u586b\u5199\u672c\u5b57\u6bb5，\u4e0d\u80fd\u56de\u663e\u5360\u4f4d\u8bf4\u660e' for k in read('effect_scope_public.json')}
    fields['null_value'] = 0
    contract = {'effect_scope': fields, 'notes': []}

    def validate(o):
        ef = o.get('effect_scope', {})
        err = []
        if set(ef) != set(fields):
            err.append('All public effect fields required, exactly once')
        if re.search('\u7c7b\u4f3c\u79bb\u6563\u5ea6|\u5982Gini|\u5982.?Gini|\u7b49\u6307\u6807|\u6216\u7c7b\u4f3c', str(ef.get('metric_family', ''))):
            err.append('Select a single explicitly supported metric family, not a list of unrelated indices')
        if re.search('`(?:mean|median|gini|hhlds|year|czone)`|\\.R\\b|::|CSV\u5217|\u6570\u636e\u5217.?\u7ed1\u5b9a', json.dumps(ef, ensure_ascii=False)):
            err.append('No column binding or author recipe in effect metadata')
        return err
    result = task('minimal_effect_definition_v2', '\u8f93\u51fa\u4e2d\u6bcf\u4e2a\u5b57\u6bb5\u5fc5\u987b\u5b9e\u9645\u586b\u5199。\u7ed9\u5b9a\u53e3\u5f84\u8349\u7a3f\u540c\u65f6\u8bf4“Gini\u6216\u7c7b\u4f3c\u6307\u6807”，\u4e0d\u8db3\u4ee5\u9650\u5b9a\u5171\u540c\u6548\u5e94\u91cf。\u8bf7\u9009\u62e9\u539f\u5141\u8bb8\u6587\u5b57\u5df2\u7ecf\u660e\u786e\u652f\u6301\u7684\u4e00\u4e2a\u6838\u5fc3\u7edf\u8ba1\u91cf\u79cd\u7c7b，\u5b9a\u4e49\u5176\u53d8\u5316\u6548\u5e94（\u5dee、\u6bd4、\u901f\u7387\u53ea\u9009\u4e00\u79cd\u6838\u5fc3\u8868\u8ff0\u5e76\u8bf4\u660e\u53d8\u4f53\u754c\u9650）。\u4e0d\u8981\u628a\u6240\u6709\u4e0d\u5e73\u7b49\u6307\u6807\u5f53\u6210\u540c\u4e00\u6548\u5e94；\u4e0d\u80fd\u9009\u62e9\u6700\u5bb9\u6613\u547d\u4e2d\u672a\u77e5\u4f5c\u8005\u6570\u503c\u7684\u79cd\u7c7b。\u53ea\u6536\u5230H1\u548c\u5141\u8bb8\u5143\u4fe1\u606f，\u4e0d\u8bfb\u6570\u636e、\u4e0d\u8bbe\u8ba1\u5206\u6790。\u4e0d\u5f97\u5199CSV\u5217\u7ed1\u5b9a、\u4ee3\u8868\u503c\u9009\u62e9、\u5177\u4f53\u6743\u91cd、\u5220\u6837、\u63a7\u5236\u53d8\u91cf\u6216\u4f30\u8ba1\u5668。\u539fH1\u5fc5\u9700\u76841970\u65f6\u95f4\u53c2\u7167\u53ef\u4ee5\u8bf4\u660e，\u5176\u4ed6\u5177\u4f53\u5bf9\u6bd4\u7531\u751f\u6210\u5668\u4f9d\u636eData\u660e\u786e\u5e76\u4fdd\u6301\u7ec4\u5185\u53ef\u6bd4。H1\u4e0d\u552f\u4e00\u89c4\u5b9a\u7684\u90e8\u5206\u6807\u660e\u672c\u8f6e\u7ea6\u5b9a\u800c\u975e\u4f5c\u8005\u5df2\u6307\u5b9a。\u4fdd\u6301\u5143\u5b9a\u4e49\u7b80\u6d01。', contract, {'h1': read('h1_public.json'), 'allowed_metadata_draft': read('effect_scope_public.json')}, validate, zone='effect_definition_only')
    rev = OUT / 'input_packet_revision_1'
    rev.mkdir(exist_ok=True)
    for name in ['five_inputs.json', 'public_inputs_lock.json', 'clean_five_inputs_sealed.json']:
        shutil.copy2(OUT / name, rev / name)
    material = read('five_inputs.json')
    material[KEYS[4]] = {'contract': result['effect_scope'], 'derived_current_trial': {}}
    save('five_inputs.json', material)
    save('public_inputs_lock.json', {'utc': now(), 'sha256': sha(OUT / 'five_inputs.json'), 'data_sha256': sha(OUT / 'data.csv'), 'source_slots': KEYS, 'input_revision': 2, 'old_target_ranks_or_routes_reused': False})
    save('effect_type_sealed_v2.json', {'utc': now(), 'five_inputs_sha256': sha(OUT / 'five_inputs.json'), 'effect_contract': result['effect_scope'], 'author_numeric_candidates_not_used': True})
    event('effect_type_sealed_v2', packet_sha256=sha(OUT / 'five_inputs.json'))

def validate_plan(o):
    unwrap(o, 'families')
    errs = []
    families = o.get('families', [])
    catalog = read('historical_source_catalog.json')
    if not families:
        return ['Filled nonempty root families required']
    if len({f.get('id') for f in families}) != len(families):
        errs.append('Duplicate family ids')
    for f in families:
        fid = f.get('id')
        dims = f.get('dimensions', [])
        keys = [d.get('key') for d in dims]
        if not dims or len(keys) != len(set(keys)):
            errs.append(str(fid) + ' unique nonempty dimensions required')
        cd = f.get('comparison_definition', {})
        if any((k not in cd for k in ['outcome', 'exposure', 'estimand', 'effect_scale', 'analysis_unit', 'null_value', 'direction', 'interpretation'])):
            errs.append(str(fid) + ' complete comparison_definition required')
        allowed_order = set(keys) | {'common:' + str(i) for i in range(len(f.get('common_steps', [])))} | {'fixed:' + s.get('key', '') for s in f.get('fixed_steps', [])}
        order = f.get('step_order', [])
        if len(order) != len(set(order)) or set(order) != allowed_order:
            errs.append(str(fid) + ' step_order must exactly cover ' + str(sorted(allowed_order)))
        items = f.get('common_steps', []) + f.get('fixed_steps', []) + dims + [v for d in dims for v in d.get('options', [])]
        for d in dims:
            ops = d.get('options', [])
            if not ops or len({x.get('id') for x in ops}) != len(ops):
                errs.append(str(fid) + ' unique option ids required')
        for item in items:
            if item.get('origin') not in ('reused', 'adapted', 'proposed'):
                errs.append(str(fid) + ' valid origin required for ' + str(item.get('key', item.get('id'))))
            refs = item.get('source_refs', [])
            if not isinstance(refs, list) or any((r not in catalog for r in refs)):
                errs.append(str(fid) + ' use exact supplied historical source refs only')
            if item.get('origin') != 'proposed' and (not refs):
                errs.append(str(fid) + ' claimed historical origin needs references')
            if not item.get('source_contribution'):
                errs.append(str(fid) + ' explain retained/new content for every item')
        for rule in f.get('constraints', []):
            cond = rule.get('forbid_when', {})
            if not cond or any((k not in keys for k in cond)):
                errs.append(str(fid) + ' invalid constraint keys')
            for k, vs in cond.items():
                valid = next(({x['id'] for x in d['options']} for d in dims if d['key'] == k), set())
                if not isinstance(vs, list) or not set(vs) <= valid:
                    errs.append(str(fid) + ' invalid constraint options')
    return sorted(set(errs))

def plan():
    verified_effect_scope()
    if (OUT / 'candidate_plan_raw.json').exists():
        return read('candidate_plan_raw.json')
    option = {'id': 'O1', 'label': '\u5177\u4f53\u9009\u62e9', 'description': '\u5b8c\u6574\u79d1\u5b66\u64cd\u4f5c', 'parameters': {}, 'data_binding': {'columns': []}, 'source_refs': [], 'origin': 'reused/adapted/proposed', 'method_origin': 'reused/adapted/proposed', 'method_refs': [], 'source_contribution': '\u5386\u53f2\u5b9e\u9645\u652f\u6301\u90e8\u5206、\u5f53\u524d\u66f4\u6539\u4e0e\u65b0\u589e\u914d\u7f6e\u5206\u522b\u8bf4\u660e'}
    step = {'key': 'unique_key', 'stage': 'input/sample/processing/model/inference', 'decision_question': '\u6b64\u56fa\u5b9a\u6b65\u9aa4\u89e3\u51b3\u7684\u95ee\u9898', 'description': '\u5b8c\u6574\u64cd\u4f5c', 'parameters': {}, 'data_binding': {'columns': []}, 'source_refs': [], 'origin': 'reused/adapted/proposed', 'method_origin': 'reused/adapted/proposed', 'method_refs': [], 'source_contribution': '\u4fdd\u7559\u548c\u65b0\u589e\u8fb9\u754c'}
    contract = {'target_interpretation': {'h1': '\u4fdd\u6301\u8f93\u5165\u5355\u4e00\u547d\u9898', 'measurement_assumptions': [], 'limits': []}, 'families': [{'id': 'F1', 'name': '\u660e\u786e\u540c\u76ee\u6807\u53ef\u6bd4\u65b9\u6848\u7ec4', 'comparison_definition': {'outcome': '', 'exposure': '', 'estimand': '', 'effect_scale': '', 'analysis_unit': '', 'null_value': 0, 'direction': '', 'interpretation': ''}, 'common_steps': [step], 'dimensions': [{'key': 'D_KEY', 'stage': 'sample/processing/model/inference', 'question': '\u5206\u6790\u9009\u62e9\u95ee\u9898', 'source_refs': [], 'origin': 'proposed', 'source_contribution': '\u95ee\u9898\u6765\u6e90', 'options': [option]}], 'fixed_steps': [], 'step_order': ['common:0', 'D_KEY'], 'constraints': [{'id': 'K1', 'forbid_when': {'D_KEY': ['incompatible_option_id']}, 'reason': '\u591a\u4e2a\u952e\u540c\u65f6\u5339\u914d\u5219\u62d2\u7edd\u8be5\u7ec4\u5408；\u65e0\u7ea6\u675f\u65f6\u7a7a\u5217\u8868'}], 'output_contract': {'effect': 'effect_size', 'p_value': 'actual or null with reason', 'ci': 'actual or null with reason', 'n': 'actual unit'}, 'inference_limitations': []}], 'historical_reuse_search': [{'scientific_need': '\u5f53\u524d\u9700\u8981', 'considered_method_refs': [], 'retained_or_adapted_core': '\u5b9e\u9645\u652f\u6301', 'why_new_design_needed': '\u6ca1\u6709\u5386\u53f2\u652f\u6301\u624d\u65b0\u63d0'}], 'considered_but_not_adopted_options': [], 'generation_notes': [], 'limitations': []}
    result = task('generate_broad_historical_multiverse', '\u4f60\u662f\u8fd9\u4e00\u8f6e\u72ec\u7acb\u5206\u6790\u65b9\u6848\u8bbe\u8ba1\u8005。\u5916\u90e8\u79d1\u7814\u8f93\u5165\u53ea\u6709\u6240\u7ed9\u4e94\u9879，\u6ca1\u6709\u76ee\u6807\u8bba\u6587、\u4f5c\u8005\u4ee3\u7801/\u7ed3\u679c、\u65e7\u5b9e\u9a8c\u65b9\u6848\u6216\u66f2\u7ebf；\u4e0d\u5f97\u6839\u636e\u9884\u8bad\u7ec3\u8bb0\u5fc6\u6062\u590d\u4f5c\u8005\u65b9\u6cd5。\u76ee\u6807\u662f\u5bf9\u540c\u4e00\u4e2aH1\u548c\u5141\u8bb8\u6548\u5e94\u53e3\u5f84\u5f62\u6210\u5c3d\u53ef\u80fd\u5145\u5206、\u6709\u79d1\u5b66\u7406\u7531\u7684\u591a\u8def\u5f84\u5206\u6790\u7a7a\u95f4。\n\u5148\u9010\u9879\u68c0\u67e5A/B\u5b9e\u9645\u63d0\u4f9b\u7684\u5386\u53f2Method、\u7ec4\u4ef6、Decision\u548cOption\u80fd\u652f\u6301\u4ec0\u4e48；\u53ef\u590d\u7528\u6838\u5fc3\u4f18\u5148\u4e8e\u5168\u65b0\u8bbe\u8ba1，\u914d\u7f6e\u53d8\u5316\u5982\u65b0\u6570\u636e\u7ed1\u5b9a/\u53c2\u6570\u987b\u5982\u5b9eadapted，\u4e0d\u80fd\u4ec5\u672f\u8bed\u76f8\u8fd1\u5c31\u79f0\u6574\u5957reused。\u6240\u6709\u5f15\u7528\u7528\u5b9e\u9645catalog\u952e，\u65b9\u6cd5\u6838\u5fc3\u5355\u72ecmethod_refs\u4e0emethod_origin，\u4e0d\u80fd\u4e3a\u4e86\u6bd4\u4f8b\u9020\u5f15\u7528。\n\u8ba4\u771f\u8003\u8651\u5408\u7406\u7684\u6d4b\u91cf\u64cd\u4f5c\u5316、\u6837\u672c/\u6570\u636e\u5904\u7406、\u6743\u91cd、\u6a21\u578b/\u4f30\u8ba1\u5668\u4e0e\u63a8\u65ad\u9009\u62e9，\u5c3d\u91cf\u4e0d\u628a\u5408\u7406\u654f\u611f\u6027\u5168\u90e8\u56fa\u5b9a。\u4e0d\u540c\u64cd\u4f5c\u5316\u82e5\u56de\u7b54\u5171\u540c\u6784\u5ff5\u4e14\u6548\u5e94\u53e3\u5f84\u53ef\u89e3\u91ca，\u53ef\u4ee5\u5728\u660e\u786e\u5dee\u5f02\u7684\u524d\u63d0\u4e0b\u6bd4\u8f83，\u4e0d\u8981\u6c42\u6240\u6709\u914d\u7f6e\u76f8\u540c；\u4e0d\u540c\u5355\u4f4d\u6216\u79d1\u5b66\u95ee\u9898\u5fc5\u987b\u53e6\u7ec4。\u6bcf\u4e2a\u9009\u62e9\u5e94\u6709\u6750\u6599\u652f\u6301\u6216\u660e\u786e\u65b0\u589e\u7406\u7531。\u4e0d\u80fd\u7528\u53ea\u6539\u53d8\u663e\u793a\u683c\u5f0f、\u968f\u673a\u79cd\u5b50\u6216\u91cd\u590d\u540c\u4e00\u7b97\u6cd5\u5145\u6570。\nData\u53ea\u6709\u6309\u5217\u540d\u548c\u6570\u503c\u63a8\u65ad\u7684\u8bed\u4e49，\u6ca1\u6709\u72ec\u7acb\u4ee3\u7801\u672c：\u6240\u6709\u8d22\u5bcc/\u5730\u533a\u89e3\u91ca\u4e0e\u6743\u91cd\u542b\u4e49\u5e94\u5217\u4e3a\u53ef\u68c0\u67e5\u5047\u8bbe，\u4e0d\u80fd\u5192\u5145\u4f5c\u8005\u5df2\u786e\u8ba4。\u5c24\u5176\u884c\u5185Gini\u4e0e\u8de8\u5730\u533aGini\u4e0d\u7b49\u540c。\u53ef\u4f7f\u7528\u5b8c\u6574Data\u5217，\u4e0d\u5c40\u9650\u4e8eA\u6700\u521d5\u5217，\u4f46\u5386\u53f2\u65b9\u6cd5\u6765\u6e90\u5fc5\u987b\u5728\u5141\u8bb8A/B\u4e2d。\u4e0d\u5f97\u4e3a\u4e86\u7a20\u5bc6\u5f3a\u884c\u5f15\u5165\u4e0d\u540c\u6307\u6807、\u4e0d\u540c\u6548\u5e94\u6216\u4e0d\u5408\u7406\u5220\u6837。\n\u6bcf\u6761\u8def\u5f84\u987b\u6709\u5b8c\u6574\u5904\u7406/\u5efa\u6a21/\u53c2\u6570\u4e0e\u660e\u786e\u6548\u5e94\u5b9a\u4e49。\u5bf9\u4e0d\u786e\u5b9a\u6216\u4e0d\u9002\u7528\u5206\u652f\u7ed9\u7ea6\u675f\u548c\u539f\u56e0，\u4e0d\u80fd\u9690\u85cf\u5220\u9664。\u5168\u7ec4\u5408\u539f\u5219\u4e0a\u5c3d\u91cf\u4e30\u5bcc，\u57281024\u6761\u53ef\u8fd0\u884c\u8def\u5f84\u4ee5\u5185\u9009\u62e9\u6709\u7406\u7531\u7684\u5206\u652f\u6570\u91cf，\u4e0d\u8981\u6c42\u6700\u4f4e\u6761\u6570；\u4e0d\u5f97\u5148\u634f\u4e00\u4e2a\u6f02\u4eae\u8def\u5f84\u6570\u518d\u586bOption。\u53c2\u6570\u4ec5\u4f5c\u63a8\u65ad\u7cbe\u5ea6\u53d8\u5316\u4e0e\u5f71\u54cd\u70b9\u4f30\u8ba1\u7684\u7ef4\u5ea6\u8981\u8bf4\u660e。\u91cd\u91c7\u6837\u6ce8\u610f\u8ba1\u7b97\u89c4\u6a21，\u53ef\u7528200\u6b21\u7684\u63a2\u7d22\u6027\u7cbe\u5ea6，\u4f46\u4e0d\u80fd\u5ba3\u79f0\u6b63\u5f0f\u7a33\u5065\u6027；\u65e0\u6709\u6548\u63a8\u65ad\u4f9d\u636e\u5219P/CI\u4e3anull\u5e76\u89e3\u91ca。\u4e0d\u5f97\u7f16\u9020P\u503c。\nstep_order\u4f7f\u7528common:0\u7b49\u5171\u540c\u6b65\u9aa4\u7d22\u5f15、\u6bcf\u4e2adimension.key、fixed:\u56fa\u5b9akey，\u6070\u597d\u5404\u4e00\u6b21；\u4e0d\u4f7f\u7528\u522b\u7684\u522b\u540d。\u65e0\u7ea6\u675f\u65f6constraints=[]，\u4e0d\u8981\u7167\u6284\u793a\u4f8bK1。\u8f93\u51fa\u5b8c\u6574\u53ef\u679a\u4e3e\u7ed3\u6784，\u4e0d\u505a\u7edf\u8ba1\u8ba1\u7b97。', contract, packet(), validate_plan)
    save('candidate_plan_raw.json', result)
    event('candidate_plan_generated', families=len(result['families']))
    return result

def data_conditions():
    path = OUT / 'current_data_conditions.json'
    if path.exists():
        return read(path.name)
    d = pd.read_csv(OUT / 'data.csv')
    result = {'duplicate_full_rows': int(d.duplicated().sum()), 'by_year': []}
    if 'year' in d:
        for year, g in d.groupby('year', sort=True):
            record = {'year': int(year), 'rows': len(g), 'numeric_columns': {}}
            if 'czone' in g:
                record.update(unique_czone=int(g['czone'].nunique()), duplicate_year_czone=int(g['czone'].duplicated().sum()))
            for name in g.select_dtypes(include='number').columns:
                x = g[name]
                record['numeric_columns'][name] = {'missing': int(x.isna().sum()), 'nonpositive': int((x <= 0).sum()), 'unique': int(x.nunique()), 'min': float(x.min()), 'max': float(x.max())}
            result['by_year'].append(record)
    save(path.name, result)
    return result

def effect_kind_from_code():
    """New explicit permission: the quarantined extractor may read author code; release type only."""
    plan()
    if (OUT / 'author_code_effect_type_release.json').exists():
        return
    raw = lab.read(ROOT / 'outputs/Neo4j_Semantic_Trial_20261025/target_sources.json')
    sources = raw['sources']
    lookup = {s['source_id']: s['text'] for s in sources}
    template = {k: '\u586b\u5199\u516c\u5f00\u6548\u5e94\u5143\u4fe1\u606f，\u4e0d\u5f97\u653e\u4f5c\u8005\u6570\u636e\u5217/\u6743\u91cd/\u6a21\u578b/\u6570\u503c' for k in read('effect_scope_public.json')}
    template['null_value'] = 0
    contract = {'effect_scope_public': template, 'private_source_evidence': [{'source_id': 'code:N/pdf:N', 'quote': '\u9010\u5b57\u51fa\u5904；\u53ea\u7559\u9694\u79bb\u533a'}], 'source_interpretation_private': '\u4ee3\u7801\u5b9e\u9645\u8f93\u51fa\u4ec0\u4e48，\u4f5c\u8005\u6709\u65e0\u5355\u4e00\u6548\u5e94；\u4e0d\u8ba1\u7b97\u6216\u8f6c\u53d1\u5927\u5c0f', 'numeric_baseline_deferred': True, 'limitations': []}

    def validate(o):
        ef = o.get('effect_scope_public', {})
        errs = []
        if set(ef) != set(template):
            errs.append('Exact public effect-scope whitelist required')
        text = json.dumps(ef, ensure_ascii=False)
        if re.search('\\bhhlds\\b|\\bmean_raw\\b|\\bmean\\b|\\bmedian\\b|reldist|\\.R\\b|Fig\\.?\\s*\\d|::|source_id', text, re.I):
            errs.append('No author binding, source excerpt, function call or analysis recipe in public effect metadata')
        for e in o.get('private_source_evidence', []):
            if lab.normalize(e.get('quote', '')) not in lab.normalize(lookup.get(e.get('source_id'), '')):
                errs.append('Private quote must match the supplied source literally')
        if o.get('numeric_baseline_deferred') is not True:
            errs.append('No numerical baseline is requested at this stage')
        return errs
    result = task('author_code_effect_type_only', '\u7528\u6237\u73b0\u5728\u660e\u786e\u5141\u8bb8\u9694\u79bb\u63d0\u53d6\u5668\u8bfb\u53d6\u76ee\u6807\u8bba\u6587\u548c\u4f5c\u8005\u4ee3\u7801；\u72ec\u7acb\u751f\u6210\u5668\u4ecd\u7136\u4e0d\u80fd\u770b\u5230\u8fd9\u4e9b\u8d44\u6599。\u672c\u8c03\u7528\u53ea\u786e\u8ba4H1\u5bf9\u5e94\u7684\u6548\u5e94\u79cd\u7c7b\u548c\u5355\u4f4d，\u4f5c\u8005\u6570\u503c\u7a0d\u540e\u5728\u72ec\u7acb\u7ed3\u679c\u51bb\u7ed3\u540e\u53e6\u884c\u8ba1\u7b97。\u4e0d\u8981\u63d0\u4f9b\u6216\u731c\u6d4b\u4efb\u4f55\u6548\u5e94\u5927\u5c0f。\u4f60\u53ef\u4ee5\u5728private\u5b57\u6bb5\u8bf4\u660e\u4f5c\u8005\u4ee3\u7801\u5b9e\u9645\u6d4b\u5ea6\u4e0e\u65b9\u6cd5，\u4f46\u516c\u5f00effect_scope_public\u53ea\u80fd\u662f\u5141\u8bb8\u7684\u6700\u5c0f\u5143\u4fe1\u606f：\u79d1\u5b66\u91cf、\u7edf\u8ba1\u91cf\u79cd\u7c7b、\u53d8\u5316\u6548\u5e94\u8868\u793a、\u5355\u4f4d、\u96f6\u503c、\u901a\u7528\u5b9a\u4e49\u548c\u8fa8\u8bc6\u9650\u5236。\u4e0d\u80fd\u516c\u5f00\u4f5c\u8005\u4f7f\u7528\u7684\u5217\u540d、\u5730\u533a\u4ee3\u8868\u503c\u662f\u5747\u503c/\u4e2d\u4f4d\u6570、\u5177\u4f53\u6743\u91cd、\u6a21\u578b、\u63a7\u5236\u9879、\u6837\u672c\u5220\u9664、\u5305/\u51fd\u6570、\u539f\u6587\u56fe\u53f7\u6216\u4ee3\u7801\u51fa\u5904。\u4e0d\u8981\u5c06\u8fd9\u4e9b\u914d\u65b9\u7528\u81ea\u7136\u8bed\u8a00\u6539\u5199\u540e\u5939\u5e26\u8fdb\u53bb。H1\u5fc5\u8981\u76841970\u57fa\u51c6\u53ef\u4fdd\u7559，\u5176\u4ed6\u6bd4\u8f83\u671f\u7531\u540e\u7eed\u660e\u786e。\u82e5\u4f5c\u8005\u4ee3\u7801\u53ea\u4ea7\u751f\u5e74\u5ea6\u6307\u6570\u800c\u4e0d\u4ea7\u751f\u5355\u6807\u91cf，\u660e\u786e\u533a\u5206\u539f\u4f5c\u8005\u5e74\u5ea6\u91cf\u4e0e\u672c\u8f6e\u5141\u8bb8\u7684\u5dee\u503c\u6295\u5f71，\u4e0d\u80fd\u79f0\u539f\u6587\u76f4\u63a5\u62a5\u544a。\u516c\u5f00\u5b57\u6bb5\u4e0d\u80fd\u6cc4\u9732\u4f5c\u8005\u7ed3\u679c、P\u503c\u6216\u7f6e\u4fe1\u533a\u95f4。', contract, {'selected_h1': read('h1_public.json'), 'target_paper_and_author_code_sources': sources}, validate, zone='target_extractor')
    rev = OUT / 'input_packet_revision_2'
    rev.mkdir(exist_ok=True)
    for name in ['five_inputs.json', 'public_inputs_lock.json', 'effect_type_sealed_v2.json']:
        shutil.copy2(OUT / name, rev / name)
    material = read('five_inputs.json')
    material[KEYS[4]] = {'contract': result['effect_scope_public'], 'derived_current_trial': {}}
    save('five_inputs.json', material)
    save('public_inputs_lock.json', {'utc': now(), 'sha256': sha(OUT / 'five_inputs.json'), 'data_sha256': sha(OUT / 'data.csv'), 'source_slots': KEYS, 'input_revision': 3, 'author_code_released_to_generator': False})
    save('author_code_effect_type_release.json', {'utc': now(), 'scope': result['effect_scope_public'], 'no_author_bindings_or_numeric_reference_forwarded': True, 'independent_candidate_plan_already_generated': True, 'candidate_must_pass_review_against_updated_public_effect_type': True})
    event('author_code_type_only_released', packet_sha256=sha(OUT / 'five_inputs.json'))

def preflight():
    candidate = plan()
    effect_kind_from_code()
    if (OUT / 'preflight_audit.json').exists():
        return read('preflight_audit.json')
    contract = {'family_reviews': [{'family_id': 'F1', 'accept': True, 'reason': 'H1\u4e0e\u6548\u5e94\u53ef\u6bd4\u6027', 'option_reviews': [{'decision_key': 'D_KEY', 'option_id': 'O1', 'accept': True, 'reason': '\u5408\u7406\u9009\u62e9\u6216\u660e\u786e\u62d2\u7edd\u7406\u7531', 'changes_strict_estimand': False, 'comparison_interpretation': '\u82e5\u4e0d\u540c\u64cd\u4f5c\u5316\u8bf4\u660e\u5171\u540c\u6784\u5ff5\u4e0e\u8fb9\u754c'}], 'additional_constraints': [], 'equivalent_options_on_current_data': [], 'warnings': []}], 'diversity_assessment': '\u4e0d\u8981\u4ec5\u770b\u6570\u91cf，\u8bf4\u660e\u771f\u5b9e\u53ef\u66ff\u6362\u65b9\u6cd5/\u6570\u636e\u5904\u7406\u5dee\u5f02', 'missed_reasonable_historical_options': [], 'overall_ready': True, 'blocking_issues': [], 'limitations': []}

    def validate(o):
        reviews = o.get('family_reviews', [])
        if {r.get('family_id') for r in reviews} != {f['id'] for f in candidate['families']}:
            return ['Cover every family exactly once']
        errs = []
        for f in candidate['families']:
            r = next((r for r in reviews if r['family_id'] == f['id']))
            expected = {(d['key'], p['id']) for d in f['dimensions'] for p in d['options']}
            actual = [(x.get('decision_key'), x.get('option_id')) for x in r.get('option_reviews', [])]
            if len(actual) != len(expected) or set(actual) != expected:
                errs.append(f['id'] + ' cover every Decision-Option once')
            if not isinstance(r.get('accept'), bool) or any((not isinstance(x.get('accept'), bool) for x in r.get('option_reviews', []))):
                errs.append('accept fields must be boolean')
            copyf = copy.deepcopy(f)
            copyf['constraints'] = r.get('additional_constraints', [])
            if validate_plan({'families': [copyf]}):
                errs.append('Additional constraints must use the same forbid_when format and valid option ids')
        return errs
    result = task('independent_preflight_choice_audit', '\u72ec\u7acb\u6838\u5bf9\u672c\u8f6e\u8349\u6848\u7684H1\u4e00\u81f4\u6027、\u6548\u5e94\u53e3\u5f84、Option\u5408\u7406\u6027/\u4f9d\u8d56\u4e0e\u6570\u636e\u6761\u4ef6；\u4e0d\u8bfb\u4f5c\u8005\u4fe1\u606f，\u4e0d\u4ee5\u672a\u77e5\u4f5c\u8005\u914d\u7f6e\u4e3a\u6807\u51c6，\u4e0d\u8981\u6c42\u65b9\u6848\u4e0e\u4f5c\u8005\u76f8\u540c。\u5bf9\u5171\u540c\u79d1\u5b66\u6784\u5ff5\u7684\u5408\u7406\u64cd\u4f5c\u5316/\u4f30\u8ba1\u5668/\u5904\u7406\u654f\u611f\u6027，\u4e0d\u80fd\u4ec5\u56e0\u4e3a\u914d\u7f6e\u6216\u4e25\u683c\u51fd\u6570\u578bestimand\u7565\u6709\u5dee\u5f02\u5c31\u5168\u90e8\u62d2\u7edd；\u5e94\u8bf4\u660e\u53ef\u6bd4\u8f83\u8303\u56f4。\u5bf9\u4e0d\u540c\u79d1\u5b66\u95ee\u9898、\u5355\u4f4d\u6216\u6548\u5e94\u542b\u4e49\u5219\u5fc5\u987b\u62d2\u7edd\u540c\u7ec4\u6216\u6307\u51fa\u963b\u65ad。\u4e0d\u8981\u5728\u672c\u5ba1\u6838\u91cc\u6539\u5199\u539f\u8349\u6848，\u9010Option\u8bf4\u660e\u4fdd\u7559/\u62d2\u7edd。\u68c0\u67e5\u5386\u53f2\u6750\u6599\u662f\u5426\u8fd8\u6709\u6f0f\u6389\u7684\u5408\u7406\u66ff\u4ee3\u65b9\u6cd5\u4ee5\u4e30\u5bcc\u7a7a\u95f4，\u4e0d\u9760\u91cd\u590d\u7b97\u6cd5\u6216\u65e0\u5b9e\u9645\u4f5c\u7528\u9608\u503c\u5145\u6570。\u6570\u636e\u7279\u5f81\u662f\u5b9e\u6d4b\u5143\u4fe1\u606f；\u5f53\u4e24\u4e2a\u7b5b\u6837\u89c4\u5219\u5728\u5f53\u524d\u6570\u636e\u7b49\u4ef7\u65f6\u8bb0\u5f55\u7b49\u4ef7，\u4e0d\u5fc5\u5047\u88c5\u589e\u52a0\u72ec\u7acb\u8bc1\u636e，\u4f46\u4e5f\u4e0d\u8981\u636e\u6b64\u8bef\u5220\u5176\u4ed6\u6709\u533a\u522b\u65b9\u6cd5。\u5141\u8bb8\u660e\u786e\u5047\u8bbe\u4e0b\u7684\u63a2\u7d22\u6027\u5206\u6790，\u4e0d\u58f0\u79f0\u6570\u636e\u8bed\u4e49\u5df2\u6709\u4ee3\u7801\u672c\u8bc1\u5b9e。additional_constraints\u53ea\u80fd\u6309\u7ed9\u5b9a\u673a\u68b0\u683c\u5f0f\u5199，\u4e0d\u80fd\u8f93\u51fa\u4ee3\u7801\u8868\u8fbe\u5f0f。', contract, packet({'candidate_plan': candidate, 'measured_data_conditions': data_conditions()}), validate)
    save('preflight_audit.json', result)
    return result

def freeze():
    if (OUT / 'specification_lock.json').exists():
        return
    candidate = plan()
    review = preflight()
    specs = []
    manifest = []
    approved = []
    for f in candidate['families']:
        ar = next((r for r in review['family_reviews'] if r['family_id'] == f['id']))
        opreview = {(r['decision_key'], r['option_id']): r for r in ar['option_reviews']}
        rules = f.get('constraints', []) + ar.get('additional_constraints', [])
        accepted_ops = {}
        for d in f['dimensions']:
            accepted_ops[d['key']] = [p for p in d['options'] if opreview[d['key'], p['id']]['accept']]
        start = len(specs)
        for combo in itertools.product(*(d['options'] for d in f['dimensions'])):
            selected = {d['key']: v for d, v in zip(f['dimensions'], combo)}
            choices = {k: v['id'] for k, v in selected.items()}
            reasons = []
            if not ar['accept']:
                reasons.append(ar['reason'])
            for key, p in selected.items():
                if not opreview[key, p['id']]['accept']:
                    reasons.append(key + '=' + p['id'] + ': ' + opreview[key, p['id']]['reason'])
            for rule in rules:
                if all((choices.get(k) in vs for k, vs in rule['forbid_when'].items())):
                    reasons.append(rule['id'] + ': ' + rule['reason'])
            entry = {'combination_id': 'C' + str(len(manifest) + 1).zfill(5), 'group_id': f['id'], 'choices': choices, 'accepted': not reasons, 'rejection_reasons': reasons}
            if not reasons:
                fixed = {s['key']: s for s in f['fixed_steps']}
                steps = []
                for key in f['step_order']:
                    if key.startswith('common:'):
                        steps.append(f['common_steps'][int(key.split(':')[1])])
                    elif key.startswith('fixed:'):
                        steps.append(fixed[key.split(':', 1)[1]])
                    else:
                        steps.append({'dimension': key, **selected[key]})
                sid = 'S' + str(len(specs) + 1).zfill(4)
                entry['spec_id'] = sid
                specs.append({'spec_id': sid, 'combination_id': entry['combination_id'], 'group_id': f['id'], 'group_name': f['name'], 'choices': choices, 'selected_options': selected, 'steps': steps, 'comparison_definition': f['comparison_definition'], 'output_contract': f['output_contract']})
            manifest.append(entry)
        if len(specs) > start:
            new = copy.deepcopy(f)
            new['constraints'] = rules
            for d in new['dimensions']:
                d['options'] = accepted_ops[d['key']]
            approved.append(new)
    save('combination_manifest.json', manifest)
    if not specs:
        raise RuntimeError('No approved path; raw drafts and rejection reasons preserved, no statistics executed')
    if len(specs) > 1024:
        raise RuntimeError('More than 1024 paths; no silent truncation. Scientific space requires an explicit new resource/design revision.')
    if review.get('blocking_issues') or not review.get('overall_ready'):
        raise RuntimeError('Preflight has explicit blocking issues; do not execute silently')
    save('specification_plan.json', {**candidate, 'families': approved, 'preflight_applied': True})
    save('specifications.json', {'count': len(specs), 'generation': 'Complete Cartesian enumeration of approved configurations; rejected combinations preserved', 'specifications': specs})
    save('specification_lock.json', {'utc': now(), 'plan_sha256': sha(OUT / 'specification_plan.json'), 'specifications_sha256': sha(OUT / 'specifications.json'), 'data_sha256': sha(OUT / 'data.csv'), 'five_inputs_sha256': sha(OUT / 'five_inputs.json'), 'preflight_sha256': sha(OUT / 'preflight_audit.json'), 'count': len(specs), 'author_numeric_candidates_opened': False})
    event('scientific_plan_frozen', count=len(specs), rejected=sum((not x['accepted'] for x in manifest)))
    print('FROZEN', len(specs), 'specifications', flush=True)

def code_errors(source):
    from neo4j_semantic_worker import audit
    import ast
    errors = audit(source)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return errors
    forbidden = {'getattr', 'setattr', 'globals', 'locals', 'vars', 'dir'}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and (n.func.id in forbidden):
            errors.append('No dynamic introspection: ' + n.func.id)
        if isinstance(n, ast.Attribute) and n.attr in {'os', 'sys', 'environ', 'ctypes', 'subprocess', 'socket', 'getenv'}:
            errors.append('No runtime/system escape attributes: ' + n.attr)
    return sorted(set(errors))

def implement():
    freeze()
    if (OUT / 'blind_code_lock.json').exists():
        return
    plan_data = read('specification_plan.json')
    specs = read('specifications.json')['specifications']
    contract = {'source_code': '\u5b8c\u6574Python\u6a21\u5757，\u5fc5\u987b\u5b9a\u4e49analyze(data,spec)', 'implementation_notes': [], 'dependencies': []}
    feedback = {}
    start = 0
    max_rounds = 3
    if (OUT / 'inference_clarification_lock.json').exists():
        start = 3
        feedback = {'previous_source': (OUT / 'analysis_revision_2.py').read_text(encoding='utf-8'), 'scientific_review': read('scientific_code_review_revision_1.json'), 'new_frozen_clarification': read('preexecution_inference_clarification.json'), 'instruction': '\u65e7\u6e90\u7801\u4ec5\u4f9b\u4fee\u590d，\u5fc5\u987b\u5b9e\u65bd\u65b0\u51bb\u7ed3\u65b9\u6848\u7684\u660e\u786e\u91cd\u91c7\u6837\u53c2\u6570；\u4e0d\u8981\u590d\u7528\u65e7\u5ba1\u6838\u901a\u8fc7\u72b6\u6001。'}
    for revision in range(start, start + max_rounds):
        result = task('scientific_implementation_revision_' + str(revision), '\u53ea\u4f9d\u636e\u4e94\u9879\u516c\u5f00\u8f93\u5165\u53ca\u672c\u8f6e\u51bb\u7ed3\u65b9\u6848，\u5b9e\u73b0\u5b8c\u6574\u79d1\u7814\u7edf\u8ba1\u6a21\u5757analyze(data,spec)。\u6240\u6709\u79d1\u5b66\u64cd\u4f5c/\u516c\u5f0f/\u53c2\u6570\u7531\u4f60\u5b9e\u73b0，\u5f00\u53d1\u8005\u4e0d\u4f1a\u624b\u6539\u7b97\u6cd5。\u5fe0\u5b9e\u6267\u884c\u5168\u90e8\u51bb\u7ed3Decision-Option、\u7ed1\u5b9a\u4e0e\u53c2\u6570，\u4e0d\u6539H1、\u4e0d\u53e6\u5b9a\u76ee\u6807、\u4e0d\u7b5b\u9009\u8def\u5f84、\u4e0d\u8981\u6c42\u547d\u4e2d\u4efb\u4f55\u4f5c\u8005\u7ed3\u679c。\ndata\u662f\u5b8c\u6574CSV\u5df2\u7ecf\u8bfb\u5165\u7684pandas.DataFrame，spec\u6709group_id、choices、selected_options、steps、comparison_definition。\u51fd\u6570\u5185\u4e0d\u8bfb/\u5199\u6587\u4ef6，\u4e0d\u8054\u7f51，\u4e0d\u8bbf\u95ee\u73af\u5883\u53d8\u91cf、\u4f5c\u8005\u6587\u4ef6\u6216\u5386\u53f2\u7ed3\u679c，\u4e0d\u52a8\u6001\u53cd\u5c04。\u53ea\u7528numpy/pandas/scipy/statsmodels/sklearn/math/warnings/collections/itertools/functools/typing/hashlib/json；\u6240\u6709\u5bfc\u5165/\u8f85\u52a9\u51fd\u6570\u90fd\u7ed9\u5168。\u4e0d\u8981\u4f7f\u7528getattr/vars/globals\u7b49\u53cd\u5c04。\n\u8fd4\u56deeffect_size、p_value、ci_lower、ci_upper、n、effect_scale、estimand、diagnostics。effect_scale\u548cestimand\u9010\u5b57\u7b49\u4e8espec.comparison_definition\u5bf9\u5e94\u5b57\u6bb5。\u6548\u5e94\u5fc5\u987b\u7531\u5f53\u524dData\u548c\u51bb\u7ed3\u9009\u62e9\u5b9e\u9645\u8ba1\u7b97；\u65e0\u6cd5\u8ba1\u7b97\u5c31\u660e\u786e\u629b\u9519；\u63a8\u65ad\u672a\u5b9a\u4e49\u53efnull\u5e76\u5177\u4f53\u89e3\u91ca，\u4e0d\u634f\u9020P\u503c/\u533a\u95f4，\u4e0d\u62ffbootstrap\u5206\u5e03\u7b26\u53f7\u6bd4\u4f8b\u81ea\u52a8\u5f53\u6709\u6548\u96f6\u5047\u8bbe\u68c0\u9a8c。\u533a\u95f4\u548c\u6548\u5e94\u5355\u4f4d\u5fc5\u987b\u4e00\u81f4。\u8bca\u65ad\u8bb0\u5f55\u5b9e\u9645\u884c/\u5730\u533a/\u5e74\u4efd\u6570\u91cf、\u6837\u672c\u9009\u62e9、\u4f30\u8ba1\u5668、\u53c2\u6570\u4e0e\u968f\u673a\u79cd\u5b50。\n\u65e2\u6709\u68c0\u7d22\u5386\u53f2\u53ef\u53c2\u8003\u4f46\u4e0d\u6267\u884c\u539f\u8bba\u6587\u4ee3\u7801。Data\u89e3\u91ca\u7684\u4e0d\u786e\u5b9a\u6027\u5217\u660e，\u4e0d\u80fd\u8865\u4f5c\u8005\u914d\u65b9。\u6ce8\u610f\u8fd0\u884c\u89c4\u6a21：\u5c3d\u91cf\u7528numpy\u5411\u91cf\u5316，\u91cd\u91c7\u6837\u5faa\u73af\u4e0d\u8981\u53cd\u590d\u590d\u5236/\u5206\u7ec4DataFrame；\u540c\u4e00spec\u5185\u53ef\u7f13\u5b58\u7eaf\u51fd\u6570\u7ed3\u679c，\u4e0d\u589e\u52a0\u8ba1\u5212\u672a\u58f0\u660e\u79d1\u5b66\u8fd1\u4f3c。\u8f93\u51fa\u7eafJSON，source_code\u4e3a\u5b8c\u6574\u6e90\u7801\u5b57\u7b26\u4e32。\u82e5\u7ed9\u4e86\u4ee3\u7801\u5ba1\u6838\u53cd\u9988，\u53ea\u4fee\u5b9e\u73b0\u9519\u8bef，\u51bb\u7ed3\u65b9\u6848\u4e0d\u53d8。', contract, packet({'frozen_plan': plan_data, 'example_specs': specs[:2], 'data_conditions': data_conditions(), 'implementation_feedback': feedback}), lambda o: code_errors(o.get('source_code', '')))
        source = result['source_code']
        (OUT / f'analysis_revision_{revision}.py').write_text(source, encoding='utf-8')
        review_contract = {'ready': True, 'blocking_issues': [], 'checks': {'all_frozen_choices_executed': True, 'same_effect_meaning_and_units': True, 'p_and_ci_valid_or_explicitly_null': True, 'no_target_author_access': True}, 'nonblocking_limitations': []}
        review = task('scientific_code_review_revision_' + str(revision), '\u72ec\u7acb\u5bf9\u7167\u51bb\u7ed3\u65b9\u6848、\u4e94\u9879\u516c\u5f00\u8d44\u6599\u548c\u771f\u5b9ePython\u6e90\u7801\u68c0\u67e5：\u9009\u9879\u662f\u5426\u5168\u90e8\u5b9e\u65bd、\u6709\u65e0\u9ed8\u9ed8\u5ffd\u7565、\u516c\u5f0f/\u6743\u91cd/\u533a\u95f4\u5355\u4f4d/P\u503c\u662f\u5426\u6b63\u786e、\u4e0d\u540c\u914d\u7f6e\u662f\u5426\u4ecd\u53ef\u6bd4、\u4ee3\u7801\u662f\u5426\u5f15\u5165\u672a\u51bb\u7ed3\u79d1\u5b66\u9009\u62e9，\u4ee5\u53ca\u6587\u4ef6/\u7f51\u7edc/\u4f5c\u8005\u4fe1\u606f\u8bbf\u95ee。\u5ba1\u6838\u79d1\u5b66\u5b9e\u73b0\u800c\u975e\u4ec5\u8bed\u6cd5。\u4e0d\u80fd\u8bbf\u95ee\u4f5c\u8005\u914d\u65b9/\u6548\u5e94，\u4e0d\u80fd\u56e0\u4e3a\u63a5\u8fd1\u672a\u77e5\u4f5c\u8005\u7ed3\u679c\u5c31\u901a\u8fc7。\u5173\u952e\u95ee\u9898\u7ed9\u5177\u4f53\u51fd\u6570/\u8bed\u53e5\u53ca\u65b9\u6848\u4f9d\u636e；\u53ea\u63d0\u5b9e\u73b0\u4fee\u590d，\u4e0d\u6539\u51bb\u7ed3\u7814\u7a76\u76ee\u6807。\u65e0\u6709\u6548\u63a8\u65ad\u5c31\u660e\u786enull，\u4e0d\u628a\u6570\u503c\u80fd\u7b97\u5f53\u79d1\u5b66\u6709\u6548。', review_contract, packet({'frozen_plan': plan_data, 'source_code': source, 'data_conditions': data_conditions()}), lambda o: [] if isinstance(o.get('ready'), bool) and isinstance(o.get('blocking_issues'), list) else ['ready boolean and blocking_issues list required'])
        if review['ready'] and (not review['blocking_issues']):
            (OUT / 'analysis_round_0.py').write_text(source, encoding='utf-8')
            save('implementation_round_0.json', result)
            save('blind_code_lock.json', {'utc': now(), 'revision': revision, 'source_sha256': sha(OUT / 'analysis_round_0.py'), 'plan_sha256': sha(OUT / 'specification_plan.json'), 'review_stage': 'scientific_code_review_revision_' + str(revision)})
            event('scientific_code_frozen', revision=revision)
            return
        feedback = {'previous_source': source, 'scientific_review': review}
        event('code_revision_requested', revision=revision, blocking_issues=review['blocking_issues'])
    raise RuntimeError('Scientific code review remains blocked after preserved model revisions')

def execute():
    implement()
    if (OUT / 'blind_results_lock.json').exists():
        return read('execution_results_round_0.json')
    import os, subprocess, ast
    from importlib.metadata import version
    runtime = OUT / 'isolated_execution'
    runtime.mkdir(exist_ok=True)
    for name in ['data.csv', 'specifications.json', 'specification_plan.json', 'specification_lock.json', 'analysis_round_0.py']:
        target = runtime / name
        if target.exists():
            assert sha(target) == sha(OUT / name)
        else:
            shutil.copy2(OUT / name, target)
    shutil.copy2(WORKER_SOURCE_PATH or Path(__file__).with_name('blind_five_worker_v7.py'), runtime / 'blind_five_worker_v7.py')
    execution_round = read('technical_execution_revision.json')['execution_round'] if (OUT / 'technical_execution_revision.json').exists() else 0
    specs = read('specifications.json')['specifications']
    work = runtime / f'execution_round_{execution_round}'
    work.mkdir(exist_ok=True)
    config = {'graph': ['Run'], 'decisions': [{'var': 'SPEC_ID', 'options': [repr(s['spec_id']) for s in specs]}]}
    template = '# --- (BOBA_CONFIG)\n' + lab.dumps(config) + '\n\n# --- (Run)\nimport sys\nsys.path.insert(0,' + repr(str(runtime)) + ')\nfrom blind_five_worker_v7 import run_one\nSPEC_ID = {{SPEC_ID}}\nrun_one(' + repr(str(runtime)) + ',SPEC_ID,execution_round=' + str(execution_round) + ')\n'
    path = work / 'boba_template.py'
    path.write_text(template, encoding='utf-8')
    if not (work / 'multiverse').exists():
        p = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'boba.cli', 'compile', '--script', str(path), '--out', str(work)], capture_output=True, text=True, encoding='utf-8', timeout=180)
        (work / 'compiler.log').write_text(p.stdout + '\n' + p.stderr, encoding='utf-8')
        if p.returncode:
            raise RuntimeError('Official Boba compile failed; see saved compiler.log')
    multiverse = work / 'multiverse'
    scripts = list(multiverse.rglob('universe_*.py'))
    bindings = []
    for script in scripts:
        tree = ast.parse(script.read_text(encoding='utf-8'))
        assign = next((n for n in tree.body if isinstance(n, ast.Assign) and any((isinstance(t, ast.Name) and t.id == 'SPEC_ID' for t in n.targets))))
        bindings.append(ast.literal_eval(assign.value))
    assert sorted(bindings) == sorted((s['spec_id'] for s in specs))
    lab.save(multiverse / 'lang.json', {'python': {'ext': ['py'], 'run': [sys.executable, '-X', 'utf8', '{{script_name}}']}})
    safe = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT'}}
    tmp = runtime / 'temp'
    tmp.mkdir(exist_ok=True)
    safe.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', TEMP=str(tmp), TMP=str(tmp))
    if not (OUT / 'execution_results_round_0.json').exists():
        with (work / 'boba_run.log').open('w', encoding='utf-8') as log:
            p = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'boba.cli', 'run', '--all', '--jobs', '8', '--dir', str(multiverse)], cwd=runtime, env=safe, stdout=log, stderr=subprocess.STDOUT, timeout=7200)
        results = [lab.read(p) for p in sorted((work / 'results').glob('S*.json'))]
        if len(results) != len(specs):
            raise RuntimeError(f'Only {len(results)}/{len(specs)} Boba receipts; partial logs preserved')
        save('execution_results_round_0.json', {'execution_attempt': execution_round, 'boba_version': version('boba'), 'official_boba_compile': True, 'official_boba_run': True, 'boba_returncode': p.returncode, 'count': len(results), 'success': sum((r['status'] == 'success' for r in results)), 'failed': sum((r['status'] != 'success' for r in results)), 'results': results})
    result = read('execution_results_round_0.json')
    save('blind_results_lock.json', {'utc': now(), 'results_sha256': sha(OUT / 'execution_results_round_0.json'), 'plan_sha256': sha(OUT / 'specification_plan.json'), 'source_sha256': sha(OUT / 'analysis_round_0.py'), 'success': result['success'], 'failed': result['failed'], 'author_numeric_candidates_accessed': False})
    event('blind_results_frozen', success=result['success'], failed=result['failed'])
    print('BOBA RESULTS', result['success'], result['failed'], flush=True)
    return result
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['prepare', 'target', 'data', 'history', 'foundation', 'retrieve', 'seal-inputs', 'plan', 'effect-kind', 'freeze', 'implement', 'execute'])
    args = parser.parse_args()
    {'prepare': prepare, 'target': target_metadata, 'data': data_semantics, 'history': historical_preparation, 'foundation': foundation, 'retrieve': retrieve, 'seal-inputs': seal_inputs, 'plan': plan, 'effect-kind': effect_kind_from_code, 'freeze': freeze, 'implement': implement, 'execute': execute}[args.stage]()
