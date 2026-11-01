# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Apply v16 author evaluation to the saved report; no model calls or analyses here."""
import argparse, csv, datetime, hashlib, html, json, re, shutil
from pathlib import Path
from author_evaluate_v16 import evaluate_author_conclusions, REASONS, reference_common_decision
from author_batch_report_v16 import build_batch
ROOT = Path(__file__).resolve().parents[2]
BACKUP = ROOT / 'work/source_backups/20261030_evaluation_v16'
LABELS = {'significant': '\u663e\u8457', 'not_significant': '\u4e0d\u663e\u8457', 'not_reported': '\u672a\u62a5\u544a', 'unclear': '\u4e0d\u660e\u786e', 'eligible': '\u53ef\u6309H1\u7ed3\u8bba\u5bf9\u7167', 'not_comparable': '\u76ee\u6807\u4e0d\u540c，\u4e0d\u6bd4\u8f83', 'unknown': '\u8bc1\u636e\u5c1a\u4e0d\u8db3'}

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def save(p, v):
    Path(p).write_text(json.dumps(v, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def esc(v):
    return html.escape(str(v), quote=True)

def pct(v):
    return 'NA' if v is None else f'{100 * v:.1f}%'

def number(v):
    return 'NA' if v is None else f'{v:.6g}'

def metric(v):
    return pct(v.get('agreement_fraction')) + f'（{v.get('agreeing_paths', 0)}/{v.get('eligible_paths', 0)}）'

def decode_page(text):
    start = text.index('const R=') + len('const R=')
    data, end = json.JSONDecoder().raw_decode(text[start:])
    return (data, start, end)

def scope_label(rule, families, kind):
    match = rule[kind]
    dims = {d['key']: d for d in families[rule['family_id']]['dimensions']}
    pieces = []
    for key, ids in match['allowed_choices'].items():
        options = {o['id']: o['label'] for o in dims[key]['options']}
        pieces.append(key + ': ' + ' / '.join((options[v] for v in ids)))
    return LABELS[match['status']] + '；' + ('；'.join(pieces) if pieces else 'Family\u8303\u56f4')

def panel(evaluation, records, references, rules, plan):
    h = '<article id="author-evaluation-v16"><h2>\u4f5c\u8005\u7ed3\u8bba\u8bc4\u4ef7 · v16</h2><p>\u672c\u6b21\u53ea\u4fee\u8bc4\u4ef7\u548c\u9875\u9762，\u539f\u65b9\u6848、\u6548\u5e94\u91cf、P\u503c、Boba\u56de\u6267\u548c8\u5f20\u66f2\u7ebf\u4e0d\u91cd\u7b97。\u4f5c\u8005\u8d44\u6599\u4ec5\u5728\u72ec\u7acb\u7ed3\u679c\u51bb\u7ed3\u540e\u8fdb\u5165\u8bc4\u4ef7\u7aef。</p>'
    h += '<div class="notice"><b>\u4e24\u79cd\u6bd4\u8f83\u53e3\u5f84\u5206\u5f00：</b>①\u7edf\u4e000.05：\u7528\u53cc\u65b9\u5df2\u4fdd\u5b58/\u5df2\u62a5\u544aP\u503c\u6309P&lt;0.05\u5206\u7c7b；\u4f5c\u8005\u65e0\u9700\u53e6\u5916\u62a5\u544aalpha，P\u754c\u9650\u5fc5\u987b\u8db3\u4ee5\u5224\u65ad。②\u4f5c\u8005\u62a5\u544a\u7ed3\u8bba：\u5bf9\u7167\u4f5c\u8005\u660e\u786e\u7684“\u663e\u8457/\u4e0d\u663e\u8457”\u6587\u5b57；\u4f5c\u8005\u9608\u503c\u672a\u77e5\u65f6\u660e\u786e\u6ce8\u660e，\u4e0d\u80fd\u5192\u79f0\u53cc\u65b9\u90fd\u63090.05。\u4e3b\u663e\u793a\u4f18\u5148①，①\u4e0d\u53ef\u7b97\u800c②\u53ef\u7b97\u65f6\u663e\u793a②；\u4e8c\u8005\u4e0d\u6df7\u5408\u5206\u6bcd。</div>'
    h += '<p>\u5339\u914d\u7684\u662f\u540cH1、\u7ed3\u5c40、\u7814\u7a76\u5c42\u7ea7\u53ca\u5bf9\u5e94\u65f6\u95f4/\u7ec4\u522b。\u5408\u7406\u65b9\u6cd5\u548c\u8c03\u6574\u5dee\u5f02\u5141\u8bb8\u4f5c\u4e3a\u7ed3\u8bba\u5bf9\u7167，\u5dee\u5f02\u9010\u6761\u5217\u51fa；\u4e0d\u80fd\u5c06\u6b64\u89e3\u91ca\u4e3a\u7edf\u8ba1\u68c0\u9a8c\u7b49\u4ef7、\u590d\u73b0\u6210\u529f\u6216H1\u6210\u7acb\u6982\u7387。\u672a\u5339\u914d、\u7f3aP\u548c\u5931\u8d25\u4e0d\u4f1a\u7b97\u4f5c\u4e0d\u663e\u8457。</p>'
    h += '<div class="scroll"><table><tr><th>\u7814\u7a76\u95ee\u9898</th><th>\u5f53\u524d\u4e3b\u663e\u793a</th><th>\u7edf\u4e000.05\u4e00\u81f4\u7387</th><th>\u4f5c\u8005\u62a5\u544a\u7ed3\u8bba\u4e00\u81f4\u7387</th><th>\u4f5c\u8005\u9608\u503c\u672a\u6838\u5b9e\u7684\u6587\u5b57\u6bd4\u8f83\u6570</th></tr>'
    for g in evaluation['groups']:
        s = g['raw_paths']
        primary = s['author_significance_comparison']
        common = s['author_significance_comparison_common_alpha']
        reported = s['author_reported_conclusion_comparison']
        h += '<tr><td>' + esc(g['title']) + '<br>' + esc(g['plot_group']) + '</td><td>' + esc(primary['metric_label']) + '<br><b>' + metric(primary) + '</b></td><td>' + metric(common) + '</td><td>' + metric(reported) + '</td><td>' + str(reported.get('author_threshold_unknown_paths', 0)) + '</td></tr>'
    h += '</table></div><p class="small">\u62ec\u53f7\u4e3a\u4e00\u81f4\u8def\u5f84\u6570/\u53ef\u6bd4\u8f83\u8def\u5f84\u6570；\u5206\u6bcd\u4e3a0\u65f6\u662fNA。\u4f5c\u8005P\u503c\u4fdd\u7559\u5176\u539f\u59cb“&lt;”\u7b49\u754c\u9650，\u4e0d\u628aP&lt;0.001\u6539\u6210\u7cbe\u786eP=0.001。</p>'
    families = {f['id']: f for f in plan['families']}
    h += '<details><summary>\u4f5c\u8005\u53c2\u7167、\u5339\u914d\u8303\u56f4\u53ca\u65b9\u6cd5\u5dee\u5f02（\u5b8c\u6574）</summary><div class="scroll"><table><tr><th>\u4f5c\u8005\u53c2\u7167</th><th>\u663e\u8457\u6027\u8bc1\u636e</th><th>\u9002\u7528\u8def\u5f84\u4e0e\u7406\u7531</th><th>\u65b9\u6cd5/\u96f6\u5047\u8bbe\u7b49\u5dee\u5f02</th></tr>'
    for rule in rules:
        i = rule['reference_index']
        ref = references[i]
        common = reference_common_decision(ref)
        p = ref.get('reported_p_value')
        evidence = 'P ' + str(ref.get('p_operator') or '=') + ' ' + number(p) if p is not None else '\u672a\u62a5\u544a\u53ef\u7528P'
        evidence += '；\u539f\u6587\u7ed3\u8bba：' + LABELS.get(ref.get('author_significance'), str(ref.get('author_significance'))) + '；\u4f5c\u8005alpha：' + number(ref.get('reported_alpha'))
        h += '<tr><td>#' + str(i) + ' · ' + esc(rule['family_id']) + '</td><td>' + esc(evidence) + '</td><td>' + esc(scope_label(rule, families, 'significance_match')) + '<br>' + esc(rule['significance_match']['reason']) + '</td><td>' + '<br>'.join((esc(x) for x in rule['significance_match'].get('method_differences', []))) + '</td></tr>'
    h += '</table></div><p><a href="author_reference.json">\u539f\u59cb\u4f5c\u8005\u53c2\u7167\u53ca\u539f\u6587\u5f15\u53e5</a> · <a href="author_evaluation_v16.json">\u672c\u8f6e\u5168\u90e8\u89c4\u5219/\u7edf\u8ba1/\u539f\u56e0</a></p></details>'
    h += '<details><summary>\u54ea\u4e9b\u8def\u5f84\u6ca1\u6709\u8fdb\u5165\u4e00\u81f4\u7387\u5206\u6bcd？</summary>'
    for g in evaluation['groups']:
        h += '<h3>' + esc(g['plot_group']) + '</h3>'
        for key in ['author_significance_comparison_common_alpha', 'author_reported_conclusion_comparison']:
            s = g['raw_paths'][key]
            items = s.get('excluded_reason_counts', {})
            h += '<p><b>' + esc(s['metric_label']) + '</b>：' + ('；'.join((esc(REASONS.get(k, k)) + ' ' + str(v) + '\u6761' for k, v in items.items())) if items else '\u6ca1\u6709\u6392\u9664\u8def\u5f84') + '</p>'
    h += '</details><details><summary>\u9010\u8def\u5f84\u6838\u5bf9\u4f5c\u8005\u53c2\u7167\u4e0e\u663e\u8457\u6027\u5224\u65ad</summary><div class="scroll"><table><tr><th>Specification</th><th>\u4f5c\u8005Ref</th><th>\u672c\u8f6e\u4fdd\u5b58P</th><th>\u4f5c\u8005P</th><th>\u7edf\u4e000.05\u4e00\u81f4</th><th>\u4f5c\u8005\u62a5\u544a\u7ed3\u8bba\u4e00\u81f4</th><th>\u672a\u7eb3\u5165\u539f\u56e0</th></tr>'
    flag = lambda v: 'NA' if v is None else '\u4e00\u81f4' if v else '\u4e0d\u4e00\u81f4'
    for r in records:
        idx = r['significance_reference_index']
        ref = references[idx] if idx is not None else {}
        p = ref.get('reported_p_value')
        author_p = str(ref.get('p_operator') or '=') + ' ' + number(p) if p is not None else '\u672a\u62a5\u544a'
        reasons = {r.get('common_alpha_reason_code'), r.get('reported_conclusion_reason_code')} - {None}
        h += '<tr><td>' + esc(r['spec_id']) + '</td><td>' + ('\u672a\u5339\u914d' if idx is None else '#' + str(idx)) + '</td><td>' + number(r.get('own_saved_p')) + '</td><td>' + esc(author_p) + '</td><td>' + flag(r['common_alpha_agreement']) + '</td><td>' + flag(r['reported_conclusion_agreement']) + '</td><td>' + '；'.join((esc(REASONS.get(k, k)) for k in sorted(reasons))) + '</td></tr>'
    h += '</table></div></details><p><a href="author_evaluation_paths_v16.json">\u9010\u8def\u5f84JSON</a> · <a href="author_evaluation_paths_v16.csv">\u9010\u8def\u5f84CSV</a> · <a href="../evaluation_v16/model_tasks/scope_match_v16/instruction.json">\u72ec\u7acb\u5339\u914dPrompt</a> · <a href="../evaluation_v16/model_tasks/scope_review_v16/instruction.json">\u72ec\u7acb\u590d\u6838Prompt</a> · <a href="../\u8bc4\u4ef7\u5c42\u4fee\u6539\u8bf4\u660e_v16.html">\u4fee\u6539\u8bf4\u660e\u53ca\u7248\u672c\u524d\u540e\u5bf9\u7167</a></p></article>'
    return h

def patch_script_labels(text):
    old = '\u663e\u8457\u6027\u4e00\u81f4\u7387 ${pct(z?.agreement_fraction)}（\u53ef\u6bd4\u8f83 ${z?.eligible_paths??0} \u6761）'
    new = "${esc(z?.metric_label||'\u4f5c\u8005\u663e\u8457\u6027\u4e00\u81f4\u7387')} ${pct(z?.agreement_fraction)}（\u4e00\u81f4/\u53ef\u6bd4 ${z?.agreeing_paths??0}/${z?.eligible_paths??0}）"
    assert old in text
    text = text.replace(old, new, 1)
    old = '<td>${pct(d?.agreement_fraction)} / ${pct(z?.agreement_fraction)}<br>\u53ef\u6bd4\u8f83\u8def\u5f84 ${d?.eligible_paths??0} / ${z?.eligible_paths??0}</td>'
    new = "<td>\u65b9\u5411 ${pct(d?.agreement_fraction)}（\u53ef\u6bd4${d?.eligible_paths??0}）<br>${esc(z?.metric_label||'\u4f5c\u8005\u663e\u8457\u6027\u4e00\u81f4\u7387')}：${pct(z?.agreement_fraction)}<br>\u4e00\u81f4/\u53ef\u6bd4 ${z?.agreeing_paths??0}/${z?.eligible_paths??0}</td>"
    assert old in text
    text = text.replace(old, new, 1)
    return text.replace('<th>\u4f5c\u8005\u65b9\u5411/\u663e\u8457\u6027\u4e00\u81f4\u6bd4\u4f8b</th>', '<th>\u4f5c\u8005\u65b9\u5411／\u663e\u8457\u6027\u7ed3\u8bba\u5bf9\u7167（\u53e3\u5f84\u53e6\u5217）</th>', 1)

def apply(batch_path):
    batch_path = Path(batch_path)
    task = batch_path.parent
    batch = read(batch_path)
    dest = Path(batch['output'])
    match = read(task / 'author_match_rules_v16.json')
    matches = {p['run_id']: p for p in match['papers']}
    policy = read(task / 'evaluation_policy_v16.json')
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    all_changes = []
    for item in batch['papers']:
        cfg = read(item['manifest'])
        out = Path(cfg['output'])
        report = Path(item['report_override'])
        baseline = BACKUP / 'report_v15' / report.name
        lock = read(out / 'blind_results_lock.json')
        for name, h in match['input_fingerprints'][cfg['run_id']].items():
            assert sha(out / name) == h, 'Frozen inputs changed: ' + name
        assert sha(out / 'execution_results_round_0.json') == lock['results_sha256']
        old_evaluation = read(baseline / 'evaluation.json')
        rows = read(out / 'evaluated_paths.json')
        author = read(out / 'author_reference.json')
        plan = read(out / 'specification_plan.json')
        rules = matches[cfg['run_id']]['reference_rules']
        evaluation, records, changes = evaluate_author_conclusions(old_evaluation, rows, author['references'], rules, policy['evaluation_alpha'])
        old_summary = read(baseline / 'summary.json')
        summary = copy_json(old_summary)
        groups = {g['plot_group']: g for g in evaluation['groups']}
        for g in summary['groups']:
            g['stats'] = groups[g['plot_group']]['raw_paths']
        summary['author_evaluation_v16'] = {'version': 'v16', 'updated': now, **evaluation['author_evaluation_v16']}
        detail = {'version': 'v16', 'updated': now, 'policy': policy, 'rules': rules, 'author_reference_sha256': sha(out / 'author_reference.json'), 'frozen_results_sha256': lock['results_sha256'], 'group_changes': changes, 'own_effects_p_and_counts_unchanged': True}
        save(report / 'evaluation.json', evaluation)
        save(report / 'summary.json', summary)
        save(report / 'author_evaluation_v16.json', detail)
        save(report / 'author_evaluation_paths_v16.json', records)
        shutil.copy2(baseline / 'author_scope_check.json', report / 'author_scope_check_v15.json')
        save(report / 'author_scope_check.json', detail)
        before = report / 'evaluation_v16_before'
        before.mkdir(exist_ok=True)
        for name in ['index.html', 'evaluation.json', 'summary.json', 'author_scope_check.json']:
            shutil.copy2(baseline / name, before / name)
        with (report / 'author_evaluation_paths_v16.csv').open('w', encoding='utf-8-sig', newline='') as f:
            fields = ['spec_id', 'family_id', 'plot_group', 'execution_status', 'own_p_status', 'own_saved_p', 'significance_reference_index', 'direction_reference_index', 'direction_agreement', 'common_alpha_agreement', 'reported_conclusion_agreement', 'common_alpha_reason_code', 'reported_conclusion_reason_code']
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(records)
        text = (baseline / 'index.html').read_text(encoding='utf-8')
        text = patch_script_labels(text)
        data, start, end = decode_page(text)
        data.update(evaluation=evaluation, summary=summary, author_scope_check=detail, author_evaluation_v16=detail)
        encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('</', '<' + chr(92) + '/')
        text = text[:start] + encoded + text[start + end:]
        text = re.sub('<p class="warning">\u4f5c\u8005\u62a5\u544a\u5305\u542b\u4e0d\u540c\u6ce2\u6b21.*?</p>', '<p class="notice">\u5df2\u6309\u5e74\u4efd\u4e0e\u7ec4\u522b\u9010\u8def\u5f84\u5339\u914d\u591a\u4e2a\u4f5c\u8005\u53c2\u7167，\u4e0d\u518d\u56e0Family\u7f16\u53f7\u76f8\u540c\u800c\u6574\u7ec4\u7f6eNA。\u5f53\u524d\u89c4\u5219\u548c\u5206\u6bcd\u89c1\u4f5c\u8005\u7ed3\u8bba\u8bc4\u4ef7v16。</p>', text, flags=re.S)
        text = re.sub('<p class="warning">\u4f5c\u8005\u65b9\u5411/\u663e\u8457\u6027\u4e00\u81f4\u7387\u5df2\u6309\u72ec\u7acb\u7684\u4e8b\u540e\u53e3\u5f84\u5ba1\u6838\u9650\u5b9a\u8def\u5f84.*?</p>', '<p class="notice">\u4f5c\u8005\u6bd4\u8f83\u5df2\u66f4\u65b0\u4e3a\u540cH1\u7ed3\u8bba\u5c42\u5bf9\u7167，\u5141\u8bb8\u6709\u4f9d\u636e\u7684\u5206\u6790\u65b9\u6cd5\u5dee\u5f02；\u4e0d\u540c\u7ed3\u5c40/\u5c42\u7ea7/\u5177\u4f53\u5bf9\u6bd4\u4ecd\u9700\u533a\u5206。\u7edf\u4e000.05\u4e0e\u4f5c\u8005\u6587\u5b57\u7ed3\u8bba\u72ec\u7acb\u5c55\u793a。</p>', text, flags=re.S)
        text = text.replace('<article id="checkpoints">', panel(evaluation, records, author['references'], rules, plan) + '<article id="checkpoints">', 1)
        text = text.replace('<a href="#resultsummary">\u7ed3\u679c\u6458\u8981</a>', '<a href="#resultsummary">\u7ed3\u679c\u6458\u8981</a><a href="#author-evaluation-v16">\u4f5c\u8005\u7ed3\u8bba\u8bc4\u4ef7v16</a>', 1)
        (report / 'index.html').write_text(text, encoding='utf-8')
        all_changes.append({'run_id': cfg['run_id'], 'report': report.name, 'groups': changes})
    shared = dest / 'evaluation_v16'
    shared.mkdir(exist_ok=True)
    shutil.copytree(task / 'model_tasks', shared / 'model_tasks', dirs_exist_ok=True)
    for name in ['evaluation_policy_v16.json', 'author_match_rules_v16.json', 'scope_match_draft_v16.json', 'scope_review_v16.json']:
        shutil.copy2(task / name, shared / name)
    save(shared / 'before_after.json', all_changes)
    sources = ['author_match_v16.py', 'author_evaluate_v16.py', 'author_report_v16.py', 'author_batch_report_v16.py', 'test_author_evaluate_v16.py', 'check_author_v16.cjs']
    for name in sources:
        shutil.copy2(Path(__file__).with_name(name), dest / 'code/adapters' / name)
    shutil.copytree(BACKUP, dest / 'code/before/evaluation_v16', dirs_exist_ok=True, ignore=shutil.ignore_patterns('report_v15'))
    build_batch(batch_path)
    page = dest / 'index.html'
    text = page.read_text(encoding='utf-8').replace('<h1>\u6d4b\u8bd5\u96c6 · \u81ea\u52a8\u5316\u591a\u8def\u5f84\u5206\u6790</h1>', '<h1>\u4e94\u7bc7\u5b9e\u9a8c\u7ed3\u679c · \u4f5c\u8005\u7ed3\u8bba\u8bc4\u4ef7\u4fee\u6b63\u7248 v16</h1>')
    banner = '<article><h2>\u672c\u8f6e\u4ec5\u4fee\u8bc4\u4ef7\u5c42</h2><p>504\u6761\u6267\u884c\u56de\u6267、480\u4e2a\u6210\u529f\u6548\u5e94、24\u6761\u5931\u8d25\u53ca8\u5f20\u539f\u66f2\u7ebf\u5168\u90e8\u4fdd\u7559。\u6ca1\u6709\u91cd\u65b0\u751f\u6210Specifications，\u6ca1\u6709\u91cd\u8dd1Boba，\u6ca1\u6709\u6539\u53d8\u4efb\u4f55\u6548\u5e94\u91cf\u6216P\u503c。</p><p>\u4f5c\u8005\u6bd4\u8f83\u66f4\u65b0\u4e3a\u540cH1\u7814\u7a76\u4e3b\u5f20\u7684\u7ed3\u8bba\u5bf9\u7167。\u4e3b\u663e\u793a\u4f18\u5148\u7edf\u4e000.05\u5224\u65ad；\u53ea\u6709\u660e\u786e\u6587\u5b57\u7ed3\u8bba\u65f6\u5355\u72ec\u6807\u6ce8\u5176\u53e3\u5f84。\u672a\u62a5\u544a、\u76ee\u6807\u4e0d\u5339\u914d、\u7f3aP\u548c\u5931\u8d25\u5747\u660e\u786e\u5217\u539f\u56e0，\u4e0d\u5f3a\u884c\u586b\u6ee1\u4e00\u81f4\u7387。</p><p><a href="\u8bc4\u4ef7\u5c42\u4fee\u6539\u8bf4\u660e_v16.html">\u672c\u6b21\u4fee\u6539\u548c\u524d\u540e\u5bf9\u7167</a> · <a href="evaluation_v16/before_after.json">\u5b8c\u6574\u6bd4\u8f83\u6570\u636e</a> · <a href="\u4fee\u6539\u6e05\u5355.html">\u5168\u90e8\u5386\u53f2\u4fee\u6539\u4e0e\u5907\u4efd</a></p></article>'
    text = text.replace('<main>', '<main>' + banner, 1)
    page.write_text(text, encoding='utf-8')
    save(task / 'apply_receipt.json', {'updated': now, 'report': str(page), 'new_scientific_generation': 0, 'new_boba_or_statistical_execution': 0, 'changes': all_changes})
    return page

def copy_json(v):
    return json.loads(json.dumps(v, ensure_ascii=False, allow_nan=False))
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--batch', required=True)
    a = p.parse_args()
    print(apply(a.batch))
