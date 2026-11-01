# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Paper/code -> DeepSeek research contract -> candidate decision DAG -> offline report.
Never executes supplied paper code. No human-authored per-paper analysis is used.
"""
import argparse
import datetime as dt
import hashlib
import html
import io
import itertools
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parent
TEXT_EXT = {'.r', '.rmd', '.py', '.do', '.ado', '.sas', '.sps', '.m', '.jl', '.txt', '.md', '.sthlp', '.ipynb'}

def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(obj), encoding='utf-8')

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def sha(data):
    return hashlib.sha256(data).hexdigest()

def normalize(s):
    return re.sub('\\s+', ' ', s).strip()

def decode(data):
    for enc in ('utf-8-sig', 'utf-16', 'cp1252'):
        try:
            return data.decode(enc)
        except UnicodeError:
            pass
    return data.decode('utf-8', errors='replace')

def select_papers(z, cfg):
    rows = [json.loads(s) for s in z.read('metadata.jsonl').decode('utf-8-sig').splitlines() if s.strip()]
    meta = {r['paper_id']: r for r in rows}
    selected, inventory = ([], [])
    for name in z.namelist():
        p = PurePosixPath(name)
        if p.suffix.lower() != '.pdf' or len(p.parts) != 3:
            continue
        pid = p.parts[1]
        codes = [n for n in z.namelist() if n.startswith(f'papers/{pid}/code/') and n.lower().endswith('.zip')]
        code_size = sum((z.getinfo(n).file_size for n in codes))
        item = {'paper_id': pid, 'title': meta.get(pid, {}).get('title', p.stem), 'pdf_member': name, 'code_members': codes, 'pdf_bytes': z.getinfo(name).file_size, 'code_zip_bytes': code_size}
        inventory.append(item)
        eligible = codes and 100000 <= item['pdf_bytes'] <= cfg['max_pdf_bytes'] and (code_size <= cfg['max_code_zip_bytes'])
        if cfg.get('paper_ids') and pid in cfg['paper_ids'] or (not cfg.get('paper_ids') and eligible and (len(selected) < cfg['count'])):
            selected.append(item)
    if cfg.get('paper_ids'):
        missing = set(cfg['paper_ids']) - {p['paper_id'] for p in selected}
        if missing:
            raise ValueError(f'Paper IDs not found: {sorted(missing)}')
    if not selected:
        raise ValueError('No papers matched selection rules')
    return (selected, inventory)

def extract_sources(z, item, cfg):
    sources, coverage = ([], [])
    pdf = z.read(item['pdf_member'])
    reader = PdfReader(io.BytesIO(pdf))
    remaining = cfg['max_pdf_chars']
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ''
        kept = text[:max(0, remaining)]
        remaining -= len(kept)
        if kept.strip():
            sources.append({'source_id': f'pdf:{i}', 'kind': 'pdf', 'location': f'{item['pdf_member']}#page={i}', 'text': kept})
        coverage.append({'location': f'pdf:{i}', 'original_chars': len(text), 'included_chars': len(kept), 'low_text': len(text.strip()) < 80})
    remaining = cfg['max_code_chars']
    for member in item['code_members']:
        with zipfile.ZipFile(io.BytesIO(z.read(member))) as inner:
            for inf in sorted(inner.infolist(), key=lambda x: x.filename.lower()):
                p = PurePosixPath(inf.filename)
                if inf.is_dir() or p.suffix.lower() not in TEXT_EXT or '__MACOSX' in p.parts:
                    continue
                if inf.file_size > 5000000:
                    coverage.append({'location': inf.filename, 'skipped': 'source exceeds 5 MB safety limit'})
                    continue
                text = decode(inner.read(inf))
                if p.suffix.lower() == '.ipynb':
                    nb = json.loads(text)
                    text = '\n\n'.join((f'[cell {i} {c['cell_type']}]\n{''.join(c.get('source', []))}' for i, c in enumerate(nb.get('cells', []), 1)))
                kept = text[:max(0, remaining)]
                remaining -= len(kept)
                if kept.strip():
                    n = sum((s['kind'] == 'code' for s in sources)) + 1
                    sources.append({'source_id': f'code:{n}', 'kind': 'code', 'location': f'{member}!{inf.filename}', 'text': kept})
                coverage.append({'location': f'{member}!{inf.filename}', 'original_chars': len(text), 'included_chars': len(kept)})
    if not any((s['kind'] == 'pdf' for s in sources)):
        raise ValueError('No usable PDF text. OCR is required; extraction stopped.')
    return {'paper': item, 'sources': sources, 'coverage': coverage, 'pdf_sha256': sha(pdf), 'pdf_pages': len(reader.pages)}

def evidence_audit(obj, sources):
    lookup = {s['source_id']: normalize(s['text']) for s in sources}
    checks = []

    def walk(v, path='$'):
        if isinstance(v, dict):
            if 'source_id' in v and 'quote' in v:
                quote = v['quote']
                ok = isinstance(quote, str) and len(quote.strip()) >= 8 and (v['source_id'] in lookup) and (normalize(quote) in lookup[v['source_id']])
                checks.append({'path': path, 'source_id': v['source_id'], 'quote': quote, 'matched': bool(ok)})
            for k, child in v.items():
                walk(child, path + '.' + k)
        elif isinstance(v, list):
            for i, child in enumerate(v):
                walk(child, f'{path}[{i}]')
    walk(obj)
    return {'total': len(checks), 'matched': sum((c['matched'] for c in checks)), 'checks': checks, 'meaning': '\u4ec5\u68c0\u67e5\u539f\u6587\u951a\u70b9\u5b58\u5728，\u4e0d\u4ee3\u8868\u8bed\u4e49\u6b63\u786e、\u7406\u8bba\u5408\u7406\u6216\u7edf\u8ba1\u6709\u6548。'}

def validate_context(obj):
    errors = []
    for k in ('title', 'hypothesis', 'data_facts', 'baseline_pipeline', 'code_coverage', 'unknowns', 'scope_warnings'):
        if k not in obj:
            errors.append(f'Missing context.{k}')
    h = obj.get('hypothesis', {})
    for k in ('text', 'origin', 'population', 'exposure', 'outcome', 'estimand', 'evidence'):
        if k not in h:
            errors.append(f'Missing hypothesis.{k}')
    if h.get('origin') not in ('user_supplied', 'model_inferred'):
        errors.append('Invalid hypothesis origin')
    return errors

def validate_space(obj, hypothesis=None):
    errors = []
    for k in ('hypothesis_text', 'decisions', 'dependency_edges', 'forbidden_combinations', 'excluded_choices', 'limitations'):
        if k not in obj:
            errors.append(f'Missing space.{k}')
    if hypothesis is not None and obj.get('hypothesis_text') != hypothesis:
        errors.append('hypothesis_text must exactly equal fixed context hypothesis')
    ds = obj.get('decisions', [])
    if not isinstance(ds, list):
        return errors + ['decisions must be an array']
    ids, opts = ([], {})
    for d in ds:
        did = d.get('id', '')
        ids.append(did)
        if not re.fullmatch('D[1-9][0-9]*', did):
            errors.append(f'Invalid decision ID: {did}')
        for k in ('label', 'stage', 'why_a_decision', 'options'):
            if k not in d:
                errors.append(f'Missing {did}.{k}')
        os_ = d.get('options', [])
        opts[did] = [o.get('id') for o in os_]
        if len(os_) < 2:
            errors.append(f'{did}: fewer than two options; remove fixed choices or justify another option')
        if len(set(opts[did])) != len(opts[did]):
            errors.append(f'{did}: duplicate option IDs')
        for o in os_:
            for k in ('id', 'label', 'description', 'origin', 'rationale', 'prerequisites', 'evidence'):
                if k not in o:
                    errors.append(f'Missing {did} option.{k}')
            if not re.fullmatch('O[1-9][0-9]*', str(o.get('id', ''))):
                errors.append(f'{did}: invalid option ID')
            if o.get('origin') not in ('reported', 'proposed'):
                errors.append(f'{did}: invalid option origin')
            if o.get('origin') == 'reported' and (not o.get('evidence')):
                errors.append(f'{did}/{o.get('id')}: reported option requires evidence')
    if len(set(ids)) != len(ids):
        errors.append('Duplicate decision IDs')
    incoming = {i: set() for i in ids}
    for e in obj.get('dependency_edges', []):
        a, b = (e.get('from'), e.get('to'))
        if a not in incoming or b not in incoming or a == b:
            errors.append(f'Invalid edge {a}->{b}')
        else:
            incoming[b].add(a)
        if not e.get('reason'):
            errors.append('Edge reason required')
    visited = set()
    while True:
        ready = {i for i in ids if i not in visited and incoming[i] <= visited}
        if not ready:
            break
        visited |= ready
    if len(visited) < len(ids):
        errors.append('Dependency graph contains a cycle')
    for c in obj.get('forbidden_combinations', []):
        choices = c.get('choices', {})
        if len(choices) < 2 or not c.get('reason'):
            errors.append('Forbidden combination requires at least two choices and a reason')
        for d, o in choices.items():
            if d not in opts or o not in opts[d]:
                errors.append(f'Unknown constraint reference {d}/{o}')
    return errors

def count_space(obj, limit=200000):
    ds = obj['decisions']
    if not ds:
        return {'cartesian_candidates': 0, 'after_model_constraints': 0, 'enumerated': True, 'validity': '\u672a\u8bc4\u4f30'}
    total = math.prod((len(d['options']) for d in ds))
    if total > limit:
        return {'cartesian_candidates': total, 'after_model_constraints': None, 'enumerated': False, 'validity': '\u672a\u8bc4\u4f30'}
    count = 0
    for values in itertools.product(*(d['options'] for d in ds)):
        assignment = {d['id']: o['id'] for d, o in zip(ds, values)}
        bad = any((all((assignment[d] == o for d, o in c['choices'].items())) for c in obj['forbidden_combinations']))
        count += not bad
    return {'cartesian_candidates': total, 'after_model_constraints': count, 'enumerated': True, 'validity': '\u4ec5\u6ee1\u8db3\u6a21\u578b\u5efa\u8bae\u7684\u7ec4\u5408\u7ea6\u675f；\u7406\u8bba、\u7edf\u8ba1、\u5197\u4f59\u5747\u672a\u5ba1\u67e5'}

def api_key():
    key = None
    if not key:
        envfile = ROOT / '.env'
        if envfile.exists():
            for line in envfile.read_text(encoding='utf-8-sig').splitlines():
                if line.startswith('DEEPSEEK_API_KEY='):
                    key = line.split('=', 1)[1].strip().strip('"').strip("'")
    if not key:
        key = os.getenv('DEEPSEEK_API_KEY')
    if not key:
        raise RuntimeError('Set DEEPSEEK_API_KEY or create .env from .env.example')
    return key

def request_api(body, cfg):
    req = urllib.request.Request(cfg['base_url'].rstrip('/') + '/chat/completions', data=json.dumps(body, ensure_ascii=False).encode('utf-8'), headers={'Authorization': 'Bearer ' + api_key(), 'Content-Type': 'application/json'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=cfg['timeout_seconds']) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                detail = exc.read().decode('utf-8', errors='replace')[:800]
                raise RuntimeError(f'DeepSeek HTTP {exc.code}: {detail}') from None
        except (TimeoutError, urllib.error.URLError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)

def generate(stage, material, cfg, out, validator, fresh=False, replay=False):
    prompt = (ROOT / 'prompts' / f'{stage}.txt').read_text(encoding='utf-8')
    body = {'model': cfg['model'], 'messages': [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': dumps(material)}], 'temperature': 0, 'thinking': {'type': 'disabled'}, 'response_format': {'type': 'json_object'}, 'max_tokens': cfg['max_tokens']}
    fingerprint = sha(dumps({'body': body, 'endpoint': cfg['base_url'], 'repairs': cfg['max_structural_repairs'], 'validator_version': 1}).encode('utf-8'))
    cache = out / 'cache' / fingerprint
    accepted = cache / 'accepted.json'
    if accepted.exists() and (not fresh):
        obj = read(accepted)
        errs = validator(obj)
        if errs:
            raise ValueError(f'Cached response invalid: {errs}')
        print(f'  {stage}: replay {fingerprint[:12]}', flush=True)
        save(out / f'{stage}.json', obj)
        save(out / f'{stage}_provenance.json', {'cache_key': fingerprint, 'mode': 'replay', 'cache_path': str(cache.relative_to(out))})
        return obj
    if replay:
        raise RuntimeError(f'No matching cache for {stage}. Replay never calls the API.')
    cache.mkdir(parents=True, exist_ok=True)
    if fresh and accepted.exists():
        raise RuntimeError('Fresh runs must use a new --output folder; preserving existing responses')
    for attempt in range(cfg['max_structural_repairs'] + 1):
        save(cache / f'request_{attempt}.json', body)
        print(f'  {stage}: DeepSeek request {attempt + 1}', flush=True)
        t = time.monotonic()
        response = request_api(body, cfg)
        save(cache / f'response_{attempt}.json', response)
        save(cache / f'timing_{attempt}.json', {'seconds': round(time.monotonic() - t, 2), 'utc': dt.datetime.now(dt.timezone.utc).isoformat()})
        choice = response['choices'][0]
        content = choice['message'].get('content') or ''
        try:
            obj = json.loads(content)
            errors = validator(obj)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            errors = [f'Malformed output: {exc}']
        if choice.get('finish_reason') != 'stop':
            errors.append(f'Incomplete response finish_reason={choice.get('finish_reason')}')
        save(cache / f'validation_{attempt}.json', {'errors': errors})
        if not errors:
            save(accepted, obj)
            save(out / f'{stage}.json', obj)
            save(out / f'{stage}_provenance.json', {'cache_key': fingerprint, 'mode': 'api', 'accepted_attempt': attempt, 'cache_path': str(cache.relative_to(out))})
            return obj
        if attempt < cfg['max_structural_repairs']:
            body['messages'].extend([{'role': 'assistant', 'content': content}, {'role': 'user', 'content': '\u4ec5\u4fee\u590d\u4ee5\u4e0b\u7ed3\u6784\u95ee\u9898，\u4ecd\u8f93\u51fa\u5b8c\u6574 JSON。\u4e0d\u8981\u6539\u53d8\u56fa\u5b9a H1，\u4e0d\u8981\u634f\u9020\u8bc1\u636e：\n' + dumps(errors)}])
    raise ValueError(f'{stage} validation failed: {errors}')

def graph_svg(space):
    ds = space['decisions']
    if not ds:
        return '<p>\u672a\u63d0\u53d6\u5230\u53ef\u5206\u652f\u51b3\u7b56。</p>'
    ranks, remaining = ({}, list(ds))
    while remaining:
        progressed = False
        for d in list(remaining):
            parents = [e['from'] for e in space['dependency_edges'] if e['to'] == d['id']]
            if all((p in ranks for p in parents)):
                ranks[d['id']] = max([ranks[p] + 1 for p in parents] or [0])
                remaining.remove(d)
                progressed = True
        if not progressed:
            raise ValueError('Cannot draw cyclic DAG')
    layers = {}
    for d in ds:
        layers.setdefault(ranks[d['id']], []).append(d)
    pos, width = ({}, (max(layers) + 1) * 360 + 32)
    height = 0
    for rank, layer in layers.items():
        y = 36
        for d in layer:
            h = 64 + len(d['options']) * 56
            pos[d['id']] = (24 + rank * 360, y, h)
            y += h + 40
        height = max(height, y)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="Decision Option \u8ba1\u7b97\u4f9d\u8d56\u56fe"><defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#8294ab"/></marker></defs>']
    for e in space['dependency_edges']:
        x1, y1, h1 = pos[e['from']]
        x2, y2, h2 = pos[e['to']]
        a, b, c, d = (x1 + 318, y1 + h1 / 2, x2, y2 + h2 / 2)
        parts.append(f'<path d="M{a},{b} C{a + 25},{b} {c - 25},{d} {c},{d}" stroke="#8294ab" stroke-width="2" fill="none" marker-end="url(#arrow)"><title>{html.escape(e['reason'])}</title></path>')
    for dec in ds:
        x, y, h = pos[dec['id']]
        label = html.escape(dec['id'] + ' ' + dec['label'])
        parts.append(f'<g><rect x="{x}" y="{y}" width="318" height="{h}" rx="14" fill="white" stroke="#c8d6e5"/><text x="{x + 14}" y="{y + 28}" font-size="15" font-weight="700" fill="#172d48">{label[:38]}</text><title>{html.escape(dec['why_a_decision'])}</title>')
        for i, o in enumerate(dec['options']):
            oy = y + 46 + i * 56
            color = '#e7f4f0' if o['origin'] == 'reported' else '#fff2db'
            label = f'{o['id']} {o['label']}'
            lines = [label[j:j + 22] for j in range(0, len(label), 22)][:2]
            parts.append(f'<rect x="{x + 12}" y="{oy}" width="294" height="48" rx="7" fill="{color}"/><text x="{x + 22}" y="{oy + 19}" font-size="12" fill="#233b50">')
            for j, line in enumerate(lines):
                parts.append(f'<tspan x="{x + 22}" dy="{(0 if j == 0 else 17)}">{html.escape(line)}</tspan>')
            parts.append(f'</text><title>{html.escape(o['description'])}</title>')
        parts.append('</g>')
    return ''.join(parts) + '</svg>'

def render_report(results, out):
    template = (ROOT / 'report.html').read_text(encoding='utf-8')
    data = json.dumps(results, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    (out / 'index.html').write_text(template.replace('__DATA_JSON__', data), encoding='utf-8')

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'results')
    parser.add_argument('--fresh', action='store_true', help='Call API in a NEW output folder')
    parser.add_argument('--replay', action='store_true', help='Strict offline replay; never call API')
    args = parser.parse_args()
    if args.fresh and args.replay:
        parser.error('--fresh and --replay are mutually exclusive')
    cfg = read(args.config)
    out = args.output.resolve()
    if args.fresh and out.exists() and any(out.iterdir()):
        parser.error('--fresh requires a new or empty --output directory')
    out.mkdir(parents=True, exist_ok=True)
    results = []
    with zipfile.ZipFile(cfg['archive']) as z:
        selected, inventory = select_papers(z, cfg)
        save(out / 'inventory.json', inventory)
        save(out / 'selection.json', {'rule': 'archive order; all code ZIPs combined <= configured byte limit; PDF 100KB..configured limit, first count; explicit paper_ids override', 'config': cfg, 'selected': selected})
        for item in selected:
            pid = item['paper_id']
            print(f'[{len(results) + 1}/{len(selected)}] {pid}: {item['title']}', flush=True)
            dest = out / pid
            dest.mkdir(parents=True, exist_ok=True)
            try:
                material = extract_sources(z, item, cfg)
                save(dest / 'sources.json', material)
                h1 = cfg.get('hypotheses', {}).get(pid)
                input_material = {'user_h1': h1, 'paper_title': item['title'], 'sources': material['sources'], 'coverage': material['coverage']}

                def context_validator(obj):
                    errs = validate_context(obj)
                    if h1 and (obj.get('hypothesis', {}).get('text') != h1 or obj.get('hypothesis', {}).get('origin') != 'user_supplied'):
                        errs.append('User H1 must be preserved exactly with user_supplied origin')
                    return errs
                context = generate('context', input_material, cfg, dest, context_validator, args.fresh, args.replay)
                space = generate('options', {'research_contract': context, **input_material}, cfg, dest, lambda obj: validate_space(obj, context['hypothesis']['text']), args.fresh, args.replay)
                audits = {'context': evidence_audit(context, material['sources']), 'options': evidence_audit(space, material['sources'])}
                counts = count_space(space)
                trunc = [c for c in material['coverage'] if c.get('skipped') or c.get('included_chars', 0) < c.get('original_chars', 0)]
                checks = {'structure_errors': [], 'dag_acyclic': True, 'evidence': audits, 'counts': counts, 'truncated_sources': trunc, 'low_text_pages': [c for c in material['coverage'] if c.get('low_text')], 'review_status': {'theoretical': 'not_evaluated', 'statistical': 'not_evaluated', 'redundancy': 'not_evaluated'}}
                save(dest / 'checks.json', checks)
                svg = graph_svg(space)
                (dest / 'dag.svg').write_text(svg, encoding='utf-8')
                entry = {'paper_id': pid, 'title': item['title'], 'status': 'ok', 'context': context, 'space': space, 'checks': checks, 'graph_svg': svg, 'source_locations': {s['source_id']: s['location'] for s in material['sources']}}
                if (dest / 'error.json').exists():
                    (dest / 'error.json').unlink()
                print(f'  OK: {len(space['decisions'])} decisions; {counts}', flush=True)
            except Exception as exc:
                entry = {'paper_id': pid, 'title': item['title'], 'status': 'error', 'error': str(exc)}
                save(dest / 'error.json', entry)
                print(f'  ERROR: {exc}', flush=True)
            results.append(entry)
            save(out / 'summary.json', [{k: v for k, v in r.items() if k not in ('graph_svg', 'context', 'space', 'source_locations')} for r in results])
            render_report(results, out)
    print(f'Report: {out / 'index.html'}', flush=True)
    return 0 if all((r['status'] == 'ok' for r in results)) else 1
if __name__ == '__main__':
    sys.exit(main())
