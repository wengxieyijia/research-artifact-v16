# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Mechanical source-graph indexing, local multilingual vectors, lexical retrieval and graph traversal."""
import json
import os
from pathlib import Path
import re
import time
import urllib.request
import numpy as np
from structured_multiverse import ROOT, read, save, digest, file_sha
MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
MODEL_REVISION = 'e8f8c211226b894fcb81acc59f3b34ba3efd5f42'
ASSETS = ROOT.parents[1] / 'work/retrieval_models/multilingual-minilm'

def assets():
    ASSETS.mkdir(parents=True, exist_ok=True)
    manifest = ASSETS / 'manifest.json'
    if manifest.exists():
        m = read(manifest)
        if all(((ASSETS / name).exists() and file_sha(ASSETS / name) == h for name, h in m['files'].items())):
            return m
        raise ValueError('Frozen embedding assets changed')
    with urllib.request.urlopen('https://huggingface.co/api/models/' + MODEL + '/revision/' + MODEL_REVISION, timeout=60) as r:
        info = json.load(r)
    revision = info['sha']
    files = ['tokenizer.json', 'config.json', 'sentence_bert_config.json', 'onnx/model_quint8_avx2.onnx']
    hashes = {}
    for name in files:
        dest = ASSETS / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            print('Download local retrieval model ' + name, flush=True)
            url = 'https://huggingface.co/' + MODEL + '/resolve/' + revision + '/' + name + '?download=true'
            temp = dest.with_suffix(dest.suffix + '.part')
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(url, timeout=120) as r, temp.open('wb') as f:
                        while True:
                            chunk = r.read(1024 * 1024)
                            if not chunk:
                                break
                            f.write(chunk)
                    temp.replace(dest)
                    break
                except Exception:
                    if attempt == 2:
                        raise
        hashes[name] = file_sha(dest)
    m = {'model_id': MODEL, 'revision': revision, 'backend': 'onnxruntime CPU, AVX2 uint8', 'pooling': 'attention-mask mean pooling then L2 normalization', 'token_limit': 128, 'long_documents': 'all token chunks averaged; no scientific text summarization', 'files': hashes, 'model_documentation': 'https://huggingface.co/' + MODEL, 'library_documentation': 'https://www.sbert.net/docs/sentence_transformer/usage/efficiency.html'}
    save(manifest, m)
    return m

class Encoder:

    def __init__(self):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.manifest = assets()
        self.tokenizer = Tokenizer.from_file(str(ASSETS / 'tokenizer.json'))
        self.special = self.tokenizer.encode('', add_special_tokens=True).ids
        self.pad = self.tokenizer.token_to_id('<pad>')
        if len(self.special) != 2 or self.pad is None:
            raise ValueError('Unexpected frozen model tokenizer boundary/pad tokens')
        settings = ort.SessionOptions()
        settings.intra_op_num_threads = min(4, os.cpu_count() or 1)
        settings.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(ASSETS / 'onnx/model_quint8_avx2.onnx'), sess_options=settings, providers=['CPUExecutionProvider'])
        self.input_names = {i.name for i in self.session.get_inputs()}

    def encode(self, texts):
        enc = self.tokenizer.encode_batch(texts, add_special_tokens=False)
        flat = []
        owners = []
        for i, e in enumerate(enc):
            toks = e.ids or [0]
            for start in range(0, len(toks), 126):
                flat.append([self.special[0]] + toks[start:start + 126] + [self.special[1]])
                owners.append(i)
        pooled = []
        for start in range(0, len(flat), 16):
            rows = flat[start:start + 16]
            length = max(map(len, rows))
            ids = np.full((len(rows), length), self.pad, dtype=np.int64)
            mask = np.zeros_like(ids)
            for j, row in enumerate(rows):
                ids[j, :len(row)] = row
                mask[j, :len(row)] = 1
            feed = {'input_ids': ids, 'attention_mask': mask, 'token_type_ids': np.zeros_like(ids)}
            feed = {k: v for k, v in feed.items() if k in self.input_names}
            hidden = self.session.run(None, feed)[0]
            if hidden.ndim == 3:
                v = (hidden * mask[:, :, None]).sum(axis=1) / mask.sum(axis=1)[:, None]
            else:
                v = hidden
            pooled.extend(v)
        pooled = np.asarray(pooled, dtype=np.float32)
        result = np.zeros((len(texts), pooled.shape[1]), dtype=np.float32)
        counts = np.zeros(len(texts))
        for i, v in zip(owners, pooled):
            result[i] += v
            counts[i] += 1
        result /= counts[:, None]
        result /= np.maximum(np.linalg.norm(result, axis=1, keepdims=True), 1e-12)
        return result

def strings(x):
    if isinstance(x, str):
        return [x]
    if isinstance(x, dict):
        return [s for v in x.values() for s in strings(v)]
    if isinstance(x, list):
        return [s for v in x for s in strings(v)]
    return []

def reconstruct(g):
    families = {x['id']: x for x in g['classification']['families']}
    methods = {x['id']: {**x, 'option_refs': [], 'decision_refs': []} for x in g['classification']['methods']}
    rows = {r['source_ref']: r for r in g['classification']['rows']}
    options = {}
    decisions = {}
    papers = {p['alias']: p for p in g['papers']}
    for ref, original in g['original_options'].items():
        dref = original['decision_ref']
        paper = papers[original['paper']]
        source_dec = next((d for d in paper['space']['decisions'] if d['id'] == dref.split(':')[-1]))
        components = []
        for c in rows[ref]['components']:
            cref = ref + '/' + c['id']
            en = g['enriched_components'][cref]
            components.append({'component_ref': cref, 'classification': c, 'source_parameters': en['parameters'], 'data_columns': en['data_columns'], 'method': g['classification']['methods'][next((i for i, m in enumerate(g['classification']['methods']) if m['id'] == c['method_id']))]})
            m = methods[c['method_id']]
            m['option_refs'].append(ref)
            m['decision_refs'].append(dref)
        mids = list(dict.fromkeys((c['classification']['method_id'] for c in components)))
        fids = list(dict.fromkeys((methods[mid]['family_id'] for mid in mids)))
        options[ref] = {'source_option_ref': ref, 'source_decision_ref': dref, 'paper_alias': original['paper'], 'paper_title': paper['title'], 'decision_label': original['decision_label'], 'decision_reason': original['decision_reason'], 'option': original['option'], 'components': components, 'method_ids': mids, 'family_ids': fids, 'retained_conditions': rows[ref].get('retained_conditions', []), 'source_uncertainties': rows[ref].get('uncertainties', []), 'source_forbidden_combinations': original['original_forbidden_combinations']}
        if dref not in decisions:
            edges = [{'from': original['paper'] + ':' + e['from'], 'to': original['paper'] + ':' + e['to'], 'reason': e['reason']} for e in paper['space']['dependency_edges'] if source_dec['id'] in [e['from'], e['to']]]
            decisions[dref] = {'source_decision_ref': dref, 'paper_alias': original['paper'], 'label': source_dec['label'], 'reason': source_dec['why_a_decision'], 'stage': source_dec['stage'], 'option_refs': [], 'method_ids': [], 'family_ids': [], 'source_edges': edges}
        d = decisions[dref]
        d['option_refs'].append(ref)
        d['method_ids'] = list(dict.fromkeys(d['method_ids'] + mids))
        d['family_ids'] = list(dict.fromkeys(d['family_ids'] + fids))
    for m in methods.values():
        m['decision_refs'] = list(dict.fromkeys(m['decision_refs']))
        m['option_refs'] = list(dict.fromkeys(m['option_refs']))
    docs = []
    for ref, d in decisions.items():
        parts = [d['label'], d['reason']]
        for oref in d['option_refs']:
            o = options[oref]
            parts += [o['option']['label'], o['option']['description']]
            for c in o['components']:
                parts += strings({k: c['classification'].get(k) for k in ['scientific_function', 'operation_object', 'mechanism', 'applicability_conditions']})
                parts += strings([{k: v.get(k) for k in ['meaning', 'role']} for v in c['data_columns']])
        docs.append({'kind': 'decision', 'id': ref, 'text': ' '.join(dict.fromkeys(parts))})
    for mid, m in methods.items():
        parts = strings({k: m.get(k) for k in ['name', 'definition', 'scientific_function', 'operation_object', 'mechanism', 'aliases']})
        docs.append({'kind': 'method', 'id': mid, 'text': ' '.join(dict.fromkeys(parts))})
    for fid, f in families.items():
        docs.append({'kind': 'family', 'id': fid, 'text': ' '.join(strings(f))})
    return {'decisions': decisions, 'options': options, 'methods': methods, 'families': families, 'documents': docs, 'policy': 'verbatim graph reconstruction and descriptor concatenation; no model relabeling or new scientific entities'}

def build_index(out, g, replay=False):
    index = reconstruct(g)
    path = out / 'retrieval/index.json'
    npy = out / 'retrieval/document_vectors.npy'
    if path.exists():
        if read(path) != index:
            raise ValueError('Frozen catalog index changed')
    elif replay:
        raise ValueError('Missing index snapshot')
    else:
        save(path, index)
    if not npy.exists():
        if replay:
            raise ValueError('Missing local vector cache')
        encoder = Encoder()
        started = time.monotonic()
        vectors = encoder.encode([d['text'] for d in index['documents']])
        np.save(npy, vectors)
        save(out / 'retrieval/model_manifest.json', {**encoder.manifest, 'index_documents': len(vectors), 'seconds': round(time.monotonic() - started, 3), 'vectors_sha256': file_sha(npy)})
    if file_sha(npy) != read(out / 'retrieval/model_manifest.json')['vectors_sha256']:
        raise ValueError('Frozen vectors changed')
    return index

def rank_scores(index, task, out):
    from sklearn.feature_extraction.text import TfidfVectorizer
    encoder = Encoder()
    queries = []
    if encoder.manifest['revision'] != read(out / 'retrieval/model_manifest.json')['revision']:
        raise ValueError('Query/document embedding model revision mismatch')
    for op in task['operations']:
        queries.append(op['query_text'] + ' ' + op['query_en'] + ' ' + op['scientific_function'] + ' ' + op['operation_object'])
    qvec = encoder.encode(queries)
    vectors = np.load(out / 'retrieval/document_vectors.npy', allow_pickle=False)
    vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2, 4), sublinear_tf=True, max_features=100000)
    tf = vectorizer.fit_transform([d['text'] for d in index['documents']])
    lex = (vectorizer.transform(queries) @ tf.T).toarray()
    dense = qvec @ vectors.T
    return {op['id']: [{'id': d['id'], 'kind': d['kind'], 'lexical': float(lex[i, j]), 'vector': float(dense[i, j])} for j, d in enumerate(index['documents'])] for i, op in enumerate(task['operations'])}

def recall(index, task, scores, k):
    operations = []
    union = {}
    routes = []
    for op in task['operations']:
        rows = scores[op['id']]
        hits = {}

        def add(dref, route, origin, score):
            if dref not in index['decisions']:
                raise ValueError('Missing source Decision during graph traversal')
            hits.setdefault(dref, []).append({'route': route, 'origin': origin, 'score': score})
        ds = [x for x in rows if x['kind'] == 'decision']
        ms = [x for x in rows if x['kind'] == 'method']
        fs = [x for x in rows if x['kind'] == 'family']
        for metric in ['lexical', 'vector']:
            for x in sorted(ds, key=lambda x: (-x[metric], x['id']))[:k]:
                add(x['id'], 'decision_' + metric, x['id'], x[metric])
            for x in sorted(ms, key=lambda x: (-x[metric], x['id']))[:max(2, k // 2)]:
                for dref in index['methods'][x['id']]['decision_refs']:
                    add(dref, 'method_' + metric + '->source_option->decision', x['id'], x[metric])
        family_hits = sorted(fs, key=lambda x: (-x['vector'], x['id']))[:2]
        for f in family_hits:
            members = [x for x in ds if f['id'] in index['decisions'][x['id']]['family_ids']]
            for x in sorted(members, key=lambda x: (-x['vector'], x['id']))[:max(1, k // 3)]:
                add(x['id'], 'family_membership_then_decision_vector', f['id'], x['vector'])
        orefs = []
        for dref, why in hits.items():
            d = index['decisions'][dref]
            for oref in d['option_refs']:
                orefs.append(oref)
                r = union.setdefault(oref, {'source_option_ref': oref, 'operation_ids': [], 'decision_refs': [], 'retrieval_routes': []})
                if op['id'] not in r['operation_ids']:
                    r['operation_ids'].append(op['id'])
                if dref not in r['decision_refs']:
                    r['decision_refs'].append(dref)
                r['retrieval_routes'] += [{'operation_id': op['id'], 'source_decision_ref': dref, **w} for w in why]
        operations.append({'operation_id': op['id'], 'decision_hits': hits, 'source_option_refs': list(dict.fromkeys(orefs))})
    return {'retrieval_k': k, 'operations': operations, 'candidates': sorted(union.values(), key=lambda r: r['source_option_ref']), 'counts': {'source_decisions': len({d for r in union.values() for d in r['decision_refs']}), 'source_options': len(union)}, 'meaning': 'program-generated recall only; no applicability exclusions; all Options under each hit Decision retained'}

def retrieve(out, index, task, replay=False, k=4):
    score_path = out / 'retrieval/query_scores.json'
    result = out / ('retrieval/recall_k' + str(k) + '.json')
    if score_path.exists():
        scores = read(score_path)
    elif replay:
        raise ValueError('Missing retrieval scores')
    else:
        scores = rank_scores(index, task, out)
        save(score_path, scores)
    found = recall(index, task, scores, k)
    if result.exists() and read(result) != found:
        raise ValueError('Retrieval replay differs')
    if not result.exists() and replay:
        raise ValueError('Missing recall ledger')
    save(result, found)
    return found
if __name__ == '__main__':
    print(json.dumps(assets(), ensure_ascii=False, indent=2))
