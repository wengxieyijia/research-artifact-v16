# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Independent scientific standard + configurable model runner; human review workflow cancelled."""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import random
import sys
import lab
import method_tables as tables
import model_runner
ROOT = Path(__file__).resolve().parent
RELATIONS = ('synonym', 'parameter_variant', 'subtype', 'part_of', 'different', 'uncertain')
LABELS = {'synonym': '\u540c\u4e00\u79cd\u505a\u6cd5，\u53ea\u662f\u53eb\u6cd5\u4e0d\u540c', 'parameter_variant': '\u540c\u4e00\u79cd\u505a\u6cd5，\u53ea\u6539\u4e86\u53c2\u6570\u6216\u8bbe\u7f6e', 'subtype': '\u5927\u7c7b\u4e0e\u5176\u4e2d\u4e00\u79cd\u5177\u4f53\u505a\u6cd5', 'part_of': '\u4e00\u4e2a\u6d41\u7a0b\u4e0e\u5176\u4e2d\u4e00\u6b65', 'different': '\u4e0d\u540c\u505a\u6cd5', 'uncertain': '\u4fe1\u606f\u4e0d\u591f／\u6211\u6682\u65f6\u5224\u65ad\u4e0d\u4e86'}

def classification_errors(obj, refs):
    errors = [e for e in tables.classification_errors(obj, refs) if 'signature must match assigned specific method' not in e]
    for row in obj.get('rows', []):
        for comp in row.get('components', []):
            for key in ('scientific_function', 'operation_object', 'mechanism'):
                if not isinstance(comp.get(key), str) or not comp[key].strip():
                    errors.append(comp.get('id', '?') + ' needs independent ' + key)
            if not tables.signature_ok(comp.get('semantic_signature')):
                errors.append('Instance semantic signature required')
    return errors

def comparison_errors(obj, pairs, standard):
    errors = []
    lookup = {p['pair_id']: p for p in pairs}
    rule_ids = {r['id'] for r in standard['rules']}
    if not isinstance(obj.get('assessments'), list) or not isinstance(obj.get('limitations'), list):
        return ['assessments/limitations arrays required']
    if Counter((a.get('pair_id') for a in obj['assessments'])) != Counter(list(lookup)):
        errors.append('Each candidate pair exactly once')
    for a in obj['assessments']:
        if a.get('relation') not in RELATIONS:
            errors.append('Unknown relation')
        if a.get('recommendation') not in ('merge_aliases', 'share_method_keep_parameters', 'retain_parent_child', 'retain_composition', 'keep_separate', 'manual_review'):
            errors.append('Unknown recommendation')
        if any((type(a.get(k)) is not bool for k in ('function_same', 'object_same', 'mechanism_same'))):
            errors.append('Three boolean comparisons required')
        if not a.get('reason') or not isinstance(a.get('conditions_to_keep'), list):
            errors.append('Reason/conditions required')
        ids = a.get('rule_ids')
        if not isinstance(ids, list) or not ids or (not set(ids) <= rule_ids):
            errors.append('Reference existing standard rule IDs')
        p = lookup.get(a.get('pair_id'))
        if not p:
            continue
        for key in ('parent_id', 'child_id', 'whole_id', 'part_id'):
            if key not in a:
                errors.append('Missing direction field ' + key)
        if a.get('relation') == 'subtype':
            if {a.get('parent_id'), a.get('child_id')} != {p['a'], p['b']}:
                errors.append('subtype direction invalid')
            if a.get('whole_id') is not None or a.get('part_id') is not None:
                errors.append('subtype is not part_of')
        elif a.get('relation') == 'part_of':
            if {a.get('whole_id'), a.get('part_id')} != {p['a'], p['b']}:
                errors.append('part_of direction invalid')
            if a.get('parent_id') is not None or a.get('child_id') is not None:
                errors.append('part_of is not subtype')
        elif any((a.get(key) is not None for key in ('parent_id', 'child_id', 'whole_id', 'part_id'))):
            errors.append('Nonhierarchical relation has direction fields')
    return errors

def sample_errors(obj, originals):
    items = obj.get('items', [])
    errors = []
    if not isinstance(items, list) or len(items) != 10:
        return ['Exactly ten review pairs required']
    buckets = Counter((x.get('selection_bucket') for x in items))
    if buckets != Counter({'confusing': 4, 'clear_different': 3, 'suspected_parameter': 3}):
        errors.append('Sampling quotas must be 4/3/3')
    seen = set()
    papers = set()
    for item in items:
        a, b = (item.get('a_ref'), item.get('b_ref'))
        key = frozenset((a, b))
        if a not in originals or b not in originals or a == b or (key in seen):
            errors.append('Invalid/duplicate original Option pair')
        seen.add(key)
        for ref in (a, b):
            if ref in originals:
                papers.add(originals[ref]['paper'])
        for k in ('a_plain', 'b_plain', 'selection_reason'):
            if not isinstance(item.get(k), str) or not item[k].strip():
                errors.append('Nonempty ' + k + ' required')
        if not isinstance(item.get('terms'), list) or not isinstance(item.get('source_information_to_compare'), list):
            errors.append('Terms/information arrays required')
        for t in item.get('terms', []):
            if not t.get('term') or not t.get('meaning'):
                errors.append('Term/meaning required')
        if any((k in item for k in ('answer', 'gold_label', 'correct_answer', 'recommended_answer'))):
            errors.append('No answer field in sampling output')
    if papers != {o['paper'] for o in originals.values()}:
        errors.append('Sample must cover all input papers')
    if not isinstance(obj.get('limitations'), list):
        errors.append('Sample limitations array required')
    return errors

def rule_check(a, pair, methods):
    if a['recommendation'] not in ('merge_aliases', 'share_method_keep_parameters'):
        reasons = ['\u4ec5\u4f9b\u5ba1\u6838，\u672a\u4fee\u6539\u77e5\u8bc6\u5e93。']
        if a['relation'] == 'part_of':
            reasons.append('\u8fd9\u662f\u6d41\u7a0b\u7ec4\u6210\u5173\u7cfb，\u4e0d\u662f\u65b9\u6cd5\u5b50\u7c7b\u578b。')
        if a['relation'] == 'subtype':
            reasons.append('\u8fd9\u662f\u5206\u7c7b\u4e0a\u7684\u4e00\u822c/\u7279\u6b8a\u5173\u7cfb，\u4e0d\u662f\u6d41\u7a0b\u6b65\u9aa4。')
        return {'status': 'review_only', 'reasons': reasons}
    return tables.rule_check(a, pair, methods)

def standard_readme(standard):
    lines = ['# \u79d1\u7814\u65b9\u6cd5\u5206\u7c7b\u89c4\u8303', '', f'\u7248\u672c：{standard['version']}；\u72b6\u6001：\u5019\u9009\u89c4\u8303，\u5f85\u4eba\u5de5\u5ba1\u6838。', '', standard['purpose'], '', '## \u62bd\u8c61\u5c42\u6b21']
    for level in standard['levels']:
        lines += ['', f'- **{level['name']}**：{level['definition']}']
    lines += ['', '## \u5bf9\u8c61\u6027\u8d28'] + [f'- **{k}**：{v}' for k, v in standard['entity_kinds'].items()]
    lines += ['', '## \u79d1\u7814\u5224\u65ad\u89c4\u5219']
    for rule in standard['rules']:
        lines += ['', f'### {rule['id']} {rule['title']}', '', rule['text']]
    lines += ['', '## \u4e24\u4e2a\u9009\u9879\u4e4b\u95f4\u7684\u5173\u7cfb'] + [f'- **{k}**：{v}' for k, v in standard['pair_relations'].items()]
    lines += ['', '## \u7a0b\u5e8f\u80fd\u68c0\u67e5\u4ec0\u4e48'] + ['- ' + x for x in standard['machine_checks']] + ['', standard['machine_check_limit'], '', '## \u4eba\u5de5\u6807\u6ce8\u653f\u7b56', '', standard['human_testset_policy'], '']
    return '\n'.join(lines)

def make_review_package(selection, originals, standard, source_hash):
    items = copy.deepcopy(selection['items'])
    random.Random(source_hash).shuffle(items)
    questions = []
    for i, item in enumerate(items, 1):

        def side(ref, plain):
            o = originals[ref]
            return {'source_ref': ref, 'paper': o['paper'], 'decision_label': o['decision_label'], 'original_label': o['option']['label'], 'original_description': o['option']['description'], 'original_conditions': o['option']['prerequisites'], 'plain': plain}
        questions.append({'question_id': f'H{i:02}', 'a': side(item['a_ref'], item['a_plain']), 'b': side(item['b_ref'], item['b_plain']), 'terms': item['terms'], 'source_information_to_compare': item['source_information_to_compare']})
    digest = lab.sha(lab.dumps(questions).encode('utf-8'))
    return {'review_version': 1, 'standard_id': standard['standard_id'], 'standard_version': standard['version'], 'standard_sha256': lab.sha(lab.dumps(standard).encode('utf-8')), 'source_sha256': source_hash, 'question_set_sha256': digest, 'answer_choices': LABELS, 'questions': questions, 'status': 'pending_human_confirmation', 'gold_labels_created': False}

def language_errors(obj, pair_ids):
    items = obj.get('items', [])
    errors = []
    if not isinstance(items, list) or Counter((x.get('pair_id') for x in items)) != Counter(pair_ids):
        return ['Cover the same ten pair IDs exactly once']
    for item in items:
        for k in ('a_plain', 'b_plain'):
            if not isinstance(item.get(k), str) or not 1 <= len(item[k]) <= 100:
                errors.append('Plain description must be 1..100 characters')
        if not isinstance(item.get('terms'), list):
            errors.append('Terms array required')
        elif any((not t.get('term') or not t.get('meaning') for t in item['terms'])):
            errors.append('Term/meaning required')
        if any((k in item for k in ('answer', 'relation', 'correct_answer', 'recommended_answer'))):
            errors.append('No answer/conclusion field permitted')
    if not isinstance(obj.get('limitations'), list):
        errors.append('limitations array required')
    return errors

def validate_answers(answers, package):
    if answers.get('user_confirmed') is not True:
        raise ValueError('\u9700\u8981\u5ba1\u6838\u8005\u660e\u786e\u786e\u8ba4\u7b54\u6848，\u6a21\u578b\u5efa\u8bae\u6216\u672a\u786e\u8ba4\u8349\u7a3f\u4e0d\u80fd\u5bfc\u5165。')
    for key in ('question_set_sha256', 'standard_sha256', 'source_sha256'):
        if answers.get(key) != package[key]:
            raise ValueError('\u7b54\u6848\u4e0e\u5f53\u524d\u9898\u76ee/\u89c4\u8303/\u6765\u6e90\u4e0d\u5339\u914d：' + key)
    rows = answers.get('responses', [])
    if Counter((r.get('question_id') for r in rows)) != Counter((q['question_id'] for q in package['questions'])):
        raise ValueError('\u9700\u898110\u9898\u5404\u6709\u4e14\u4ec5\u6709\u4e00\u4e2a\u7b54\u6848。')
    for r in rows:
        if r.get('relation') not in RELATIONS:
            raise ValueError('\u5b58\u5728\u672a\u4f5c\u7b54\u6216\u672a\u77e5\u7b54\u6848。')
    return rows

def import_answers(path, out):
    raise ValueError('\u4eba\u5de5\u5ba1\u6838\u4e0e\u6d4b\u8bd5\u96c6\u8def\u7ebf\u5df2\u6309\u7528\u6237\u8981\u6c42\u53d6\u6d88，\u4e0d\u518d\u5bfc\u5165\u7b54\u6848\u6216\u5efa\u7acb\u6d4b\u8bd5\u6807\u7b7e。')

def render_review(package, out):
    payload = lab.dumps(package).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    page = (ROOT / 'human_review_template.html').read_text(encoding='utf-8').replace('__DATA_JSON__', payload)
    (out / '\u4eba\u5de5\u5ba1\u6838\u8868_10\u9898.html').write_text(page, encoding='utf-8')
    (out / 'human_review.html').write_text(page, encoding='utf-8')
    lines = ['# 10\u5bf9 Option \u4eba\u5de5\u5ba1\u6838\u8868', '', '\u6bcf\u9898\u5148\u770bA、B\u7684\u767d\u8bdd\u8bf4\u660e，\u518d\u9009\u4e00\u79cd\u5173\u7cfb。\u4e0d\u61c2\u5c31\u9009“\u4fe1\u606f\u4e0d\u591f”，\u65e0\u9700\u731c\u7b54\u6848。\u8bf7\u5148\u505a\u9898，\u518d\u770b\u6a21\u578b\u7ed3\u679c，\u907f\u514d\u88ab\u5176\u5f71\u54cd。', '', '## \u4f60\u53ef\u4ee5\u9009\u4ec0\u4e48']
    letters = dict(zip(RELATIONS, 'ABCDEF'))
    lines += ['- ' + letters[k] + '：' + v for k, v in LABELS.items()]
    lines += ['', '\u586b\u5199\u65b9\u6cd5：\u7f51\u9875\u53ef\u4ee5\u70b9\u9009\u5e76\u4e0b\u8f7d\u7b54\u6848；\u4e5f\u53ef\u76f4\u63a5\u56de\u590d“H01=B、H02=F……”\u6216\u628a\u4e0b\u6587“\u6211\u7684\u7b54\u6848”\u586b\u4e3aA—F。\u6ca1\u6709\u9884\u586b\u7b54\u6848。']
    for q in package['questions']:
        lines += ['', f'## {q['question_id']}', '', '**A：** ' + q['a']['plain'], '', '**B：** ' + q['b']['plain']]
        if q['terms']:
            lines += ['', '**\u5c0f\u8bcd\u5178：**'] + ['- ' + t['term'] + '：' + t['meaning'] for t in q['terms']]
        lines += ['', '**\u9700\u8981\u5bf9\u7167\u7684\u4fe1\u606f：**'] + ['- ' + x for x in q['source_information_to_compare']]
        lines += ['', '**\u539f\u59cb\u51fa\u5904：** ' + q['a']['source_ref'] + '（' + q['a']['original_label'] + '） / ' + q['b']['source_ref'] + '（' + q['b']['original_label'] + '）', '', '**\u6211\u7684\u7b54\u6848：** ______', '', '**\u539f\u56e0\u6216\u7591\u95ee（\u53ef\u4e0d\u586b）：** ______']
    lines += ['', '\u5168\u90e8\u586b\u5199\u540e，\u8bf7\u8bf4\u660e“\u6211\u786e\u8ba4\u4ee5\u4e0a\u7b54\u6848，\u53ef\u7528\u4e8e\u5efa\u7acb\u4eba\u5de5\u6807\u6ce8\u6d4b\u8bd5\u96c6”。\u9009F\u7684\u9898\u53ea\u8bb0\u5f55\u4e3a\u5f85\u8fdb\u4e00\u6b65\u5ba1\u6838，\u4e0d\u8ba1\u5165\u5df2\u786e\u8ba4\u7684\u5173\u7cfb\u7b54\u6848。\u5728\u4f60\u786e\u8ba4\u524d，\u7a0b\u5e8f\u4e0d\u4f1a\u628a\u4efb\u4f55\u6a21\u578b\u5224\u65ad\u5f53\u4f5c\u6807\u51c6\u7b54\u6848。', '']
    (out / '\u4eba\u5de5\u5ba1\u6838\u8868_10\u9898.md').write_text('\n'.join(lines), encoding='utf-8')

def run(args):
    out = args.output.resolve()
    if args.import_answers:
        return import_answers(args.import_answers, out)
    if args.fresh and out.exists() and any(out.iterdir()):
        raise ValueError('Fresh output must be new or empty')
    out.mkdir(parents=True, exist_ok=True)
    cfg = lab.read(args.config)
    standard = lab.read(args.standard)
    if cfg.get('thinking', {}).get('type') != 'enabled' or cfg.get('reasoning_effort') != 'high':
        raise ValueError('This trial requires enabled thinking and High effort')
    metadata = model_runner.verify_provider(cfg, out, args.replay)
    previous = lab.read(args.previous / 'trial_result.json')
    old = lab.read(args.knowledge / 'knowledge_library.json')
    originals = previous['original_options']
    source_hash = lab.sha(lab.dumps(originals).encode('utf-8'))
    inputs = [args.previous / 'trial_result.json', args.knowledge / 'knowledge_library.json', args.standard]
    hashes = {str(p.resolve()): lab.sha(p.read_bytes()) for p in inputs}
    lab.save(out / 'classification_standard.json', standard)
    (out / 'CLASSIFICATION_STANDARD.md').write_text(standard_readme(standard), encoding='utf-8')
    contracts = {name: lab.read(ROOT / 'contracts' / filename) for name, filename in [('classification', 'classification.json'), ('comparison', 'comparison.json'), ('review', 'review_sample.json')]}
    material = {'original_options': originals, 'option_refs': list(originals), 'old_classification': previous['classification'], 'previous_review': old.get('model_review'), 'original_constraints': previous.get('original_constraints', {})}

    def call(stage, instruction, contract, data, validator):
        return model_runner.run_json(stage, (ROOT / 'instructions' / instruction).read_text(encoding='utf-8'), standard, contract, data, cfg, out, validator, args.replay)
    classified = call('classification_high', 'classify.txt', contracts['classification'], material, lambda x: classification_errors(x, list(originals)))
    pairs = tables.candidates(classified, old)
    compared = call('comparison_high', 'compare.txt', contracts['comparison'], {'classification': classified, 'original_options': originals, 'candidate_pairs': pairs}, lambda x: comparison_errors(x, pairs, standard))
    lab.save(out / 'annotation_status.json', {'status': 'cancelled_by_user', 'gold_labels_created': False, 'active_test_labels': 0, 'human_review_enabled': False})
    methods = {m['id']: m for m in classified['methods']}
    lookup = {p['pair_id']: p for p in pairs}
    conflicts = [{'source_ref': r['source_ref'], 'component': c['id'], 'method_id': c['method_id'], 'note': '\u5b9e\u4f8b\u4e0e\u76ee\u5f55\u7b7e\u540d\u7528\u8bcd\u4e0d\u540c，\u9700\u8bed\u4e49\u5ba1\u67e5；\u672a\u6539\u5199\u5b9e\u4f8b\u63cf\u8ff0。'} for r in classified['rows'] for c in r['components'] if c['semantic_signature'] != methods[c['method_id']]['semantic_signature']]
    checks = {'papers': len({o['paper'] for o in originals.values()}), 'option_instances': len(originals), 'classification_rows': len(classified['rows']), 'families': len(classified['families']), 'specific_methods': len(classified['methods']), 'components': sum((len(r['components']) for r in classified['rows'])), 'assessed_pairs': len(compared['assessments']), 'entity_kind_counts': dict(Counter((r['entity_kind'] for r in classified['rows']))), 'relation_counts': dict(Counter((a['relation'] for a in compared['assessments']))), 'automatic_merges_executed': 0, 'gold_labels_created': False, 'human_review_questions': 0, 'human_review_enabled': False, 'thinking': 'enabled', 'reasoning_effort': 'high', 'provider_model_name': metadata['selected'].get('name'), 'requested_model': cfg['model'], 'semantic_accuracy': 'not_evaluated', 'instance_catalog_signature_differences': len(conflicts), 'input_files_unchanged': all((lab.sha(Path(p).read_bytes()) == h for p, h in hashes.items())), 'merge_rule_counts': dict(Counter((rule_check(a, lookup[a['pair_id']], methods)['status'] for a in compared['assessments'])))}
    if not checks['input_files_unchanged']:
        raise ValueError('Input changed')
    result = {'classification': classified, 'comparison': compared, 'candidate_pairs': pairs, 'original_options': originals, 'checks': checks, 'standard': standard, 'instance_signature_review': conflicts}
    lab.save(out / 'trial_result.json', result)
    lab.save(out / 'checks.json', checks)
    lab.save(out / 'input_manifest.json', {'files_sha256': hashes, 'option_source_sha256': source_hash})
    lab.save(out / 'method_classify.json', classified)
    lab.save(out / 'method_compare.json', compared)
    lab.save(out / 'candidate_pairs.json', pairs)
    tables.export_tables(out, result, rule_checker=rule_check)
    (out / 'index.html').write_text((out / 'index.html').read_text(encoding='utf-8').replace('<h2>\u672c\u8f6e\u7ed3\u679c</h2>', '<h2>\u89c4\u8303\u9a71\u52a8 · V4.1 Flash High \u8bd5\u8dd1</h2><p>\u4eba\u5de5\u5ba1\u6838\u548c\u6d4b\u8bd5\u96c6\u8def\u7ebf\u5df2\u53d6\u6d88。\u5f53\u524d\u4ec5\u4e3a\u6a21\u578b\u5019\u9009\u5206\u7c7b，\u5c1a\u672a\u9a8c\u8bc1\u8bed\u4e49\u51c6\u786e\u7387。 · <a href="CLASSIFICATION_STANDARD.md">\u72ec\u7acb\u79d1\u7814\u5206\u7c7b\u89c4\u8303</a></p>'), encoding='utf-8')
    if (out / 'error.json').exists():
        (out / 'error.json').unlink()
    print(lab.dumps(checks), flush=True)
if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--previous', type=Path, default=ROOT / 'method_table_results')
    p.add_argument('--knowledge', type=Path, default=ROOT / 'knowledge_results')
    p.add_argument('--output', type=Path, default=ROOT / 'standard_high_results')
    p.add_argument('--standard', type=Path, default=ROOT / 'standards' / 'method_classification_v1.json')
    p.add_argument('--config', type=Path, default=ROOT / 'config_high.json')
    p.add_argument('--import-answers', type=Path)
    p.add_argument('--replay', action='store_true')
    p.add_argument('--fresh', action='store_true')
    args = p.parse_args()
    if args.replay and args.fresh:
        p.error('Cannot combine --fresh and --replay')
    try:
        run(args)
    except Exception as exc:
        lab.save(args.output / 'error.json', {'error': str(exc)})
        raise
