# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Read-only five-paper delivery. Does not call a model or run statistics."""
import argparse, collections, hashlib, html, json, shutil
from pathlib import Path
from proposal_report_layout_v14 import build_report
from proposal_batch_report_v10 import build_batch
from proposal_reference_checks_v13 import checked_evaluation
from proposal_author_scope_v15 import apply_rules
from auto_evaluate_v8 import summarize
from auto_report_v8 import result_summary, load
ROOT = Path(__file__).resolve().parents[2]

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(p, v):
    Path(p).write_text(json.dumps(v, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def esc(v):
    return html.escape(str(v))

def update_embedded(page, updates):
    text = page.read_text(encoding='utf-8')
    start = text.index('const R=') + len('const R=')
    r, end = json.JSONDecoder().raw_decode(text[start:])
    r.update(updates)
    text = text[:start] + json.dumps(r, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('</', '<' + chr(92) + '/') + text[start + end:]
    page.write_text(text, encoding='utf-8')

def build(batch_path):
    batch = read(batch_path)
    dest = Path(batch['output'])
    dest.mkdir(parents=True, exist_ok=True)
    if len(batch['papers']) != 5:
        raise ValueError('This delivery requires exactly five papers')
    checks = []
    for item in batch['papers']:
        cfg = read(item['manifest'])
        out = Path(cfg['output'])
        report = Path(item['report_override'])
        state = read(out / 'run_state.json')
        if state['status'] != 'complete':
            raise RuntimeError('Not complete yet: ' + cfg['run_id'])
        if state.get('scientific_eligibility') == 'not_approved_for_confirmatory_testset_summary':
            raise RuntimeError('Unresolved protocol conflict; cannot silently include this run')
        lock = read(out / 'blind_results_lock.json')
        execution = read(out / 'execution_results_round_0.json')
        if sha(out / 'execution_results_round_0.json') != lock['results_sha256']:
            raise RuntimeError('Result freeze changed')
        if not execution['official_boba_run'] or not execution['official_boba_compile']:
            raise RuntimeError('Actual official Boba execution required')
        build_report(out, report, Path(cfg['quarantine']))
        rows = read(out / 'evaluated_paths.json')
        byid = {r['spec_id']: r for r in execution['results']}
        unavailable = []
        other_na = []
        evaluation, scope_audit = checked_evaluation(read(out / 'evaluation.json'), rows, read(out / 'author_reference.json'))
        if (out / 'author_scope_rules_v15.json').exists():
            rules = read(out / 'author_scope_rules_v15.json')
            if rules['results_sha256'] != lock['results_sha256'] or rules['author_reference_sha256'] != sha(out / 'author_reference.json'):
                raise RuntimeError('Stale author scope audit')
            evaluation, scoped = apply_rules(evaluation, rows, read(out / 'author_reference.json'), rules)
            scope_audit['post_freeze_scoped_groups'] = scoped
            scope_audit['rule_file'] = 'author_scope_rules_v15.json'
        save(report / 'evaluation_legacy.json', read(out / 'evaluation.json'))
        save(report / 'evaluation.json', evaluation)
        save(report / 'author_scope_check.json', scope_audit)
        for row in rows:
            if row['status'] != 'success' or row['p_status'] != 'NA':
                continue
            inf = byid[row['spec_id']]['result'].get('inference', {})
            entry = {'spec_id': row['spec_id'], 'status': inf.get('status'), 'reason': inf.get('reason')}
            (unavailable if inf.get('status') == 'unavailable' else other_na).append(entry)
        completeness = {'successful_point_estimates': sum((r['status'] == 'success' for r in rows)), 'paths_with_accepted_p': sum((r['p_status'] == 'valid' for r in rows)), 'inference_implementation_unavailable': len(unavailable), 'other_p_na': len(other_na), 'failed_paths': sum((r['status'] != 'success' for r in rows)), 'unavailable_details': unavailable, 'other_na_details': other_na, 'policy': 'Point-estimate success is not a claim that every frozen inference backend ran. NA is never NS.'}
        save(report / 'implementation_status_summary.json', completeness)
        summary = result_summary(state, read(out / 'specification_plan.json'), evaluation, rows, execution, read(out / 'specifications.json'), read(out / 'author_reference.json'))
        summary['execution_completeness'] = completeness
        save(report / 'summary.json', summary)
        update_embedded(report / 'index.html', {'summary': summary, 'evaluation': evaluation, 'implementation_completeness': completeness, 'author_scope_check': scope_audit})
        notice = '<article><h2>\u6267\u884c\u5b8c\u6574\u5ea6\u4e0e\u672c\u7bc7\u89e3\u91ca\u8fb9\u754c</h2><p>\u53ef\u8ba1\u7b97\u6548\u5e94 ' + str(completeness['successful_point_estimates']) + ' \u6761；\u6709\u53ef\u8ba1\u5165\u7edf\u8ba1\u7684P\u503c ' + str(completeness['paths_with_accepted_p']) + ' \u6761；\u63a8\u65ad\u5b9e\u73b0\u4e0d\u53ef\u7528 ' + str(len(unavailable)) + ' \u6761；\u5176\u4ed6P\u4e3aNA ' + str(len(other_na)) + ' \u6761；\u5931\u8d25 ' + str(completeness['failed_paths']) + ' \u6761。</p>'
        if unavailable:
            notice += '<p class="warning">\u90e8\u5206\u6a21\u578b\u5df2\u53d6\u5f97\u6709\u6548\u70b9\u4f30\u8ba1，\u4f46\u6307\u5b9a\u63a8\u65ad\u540e\u7aef\u6ca1\u6709\u5b9e\u73b0；\u8fd9\u4e9b\u70b9\u7684P\u503c\u53ca\u7f6e\u4fe1\u533a\u95f4\u4e3aNA，\u4e0d\u7b97\u4e0d\u663e\u8457，\u4e5f\u4e0d\u5192\u79f0\u5df2\u5b8c\u6210KR\u7b49\u6307\u5b9a\u68c0\u9a8c。<a href="implementation_status_summary.json">\u9010\u8def\u5f84\u539f\u56e0</a></p>'
        if scope_audit['ambiguous_groups']:
            notice += '<p class="warning">\u4f5c\u8005\u62a5\u544a\u5305\u542b\u4e0d\u540c\u6ce2\u6b21、\u7ec4\u522b\u5bf9\u6bd4\u6216\u68c0\u9a8c，\u5c1a\u672a\u9010\u8def\u5f84\u552f\u4e00\u5339\u914d。\u672c\u62a5\u544a\u5c06\u4f5c\u8005\u4e00\u81f4\u7387\u8bbe\u4e3aNA，\u907f\u514d\u628a\u6700\u540e\u4e00\u6761\u4f5c\u8005\u53c2\u7167\u9519\u8bef\u5e94\u7528\u5230\u6240\u6709\u8def\u5f84。\u4f5c\u8005\u539f\u59cb\u53c2\u7167\u4fdd\u7559\u4f9b\u4eba\u5de5\u6838\u5bf9；\u672c\u8f6e\u6548\u5e94、P\u503c\u548c\u81ea\u8eab\u663e\u8457\u6bd4\u4f8b\u5747\u672a\u6539\u53d8。<a href="author_scope_check.json">\u5339\u914d\u4fee\u6b63\u8bb0\u5f55</a></p>'
        plan = read(out / 'specification_plan.json')
        if scope_audit.get('post_freeze_scoped_groups'):
            notice += '<p class="warning">\u4f5c\u8005\u65b9\u5411/\u663e\u8457\u6027\u4e00\u81f4\u7387\u5df2\u6309\u72ec\u7acb\u7684\u4e8b\u540e\u53e3\u5f84\u5ba1\u6838\u9650\u5b9a\u8def\u5f84；FTE\u4e0e\u603b\u4eba\u6570、\u4e0d\u540c\u6d4b\u91cf\u5e74\u4efd、\u76f8\u5173\u4e0e\u8c03\u6574\u56de\u5f52\u4e0d\u81ea\u52a8\u4e92\u7528。\u4e0d\u80fd\u5339\u914d\u7684\u6bd4\u8f83\u4e3aNA。\u5ba1\u6838\u4e0d\u8bfb\u53d6\u672c\u8f6e\u6548\u5e94/P\u503c，\u4e5f\u4e0d\u56de\u6d41\u751f\u6210\u5668。<a href="author_scope_rules_v15.json">\u9010\u53c2\u7167\u89c4\u5219\u4e0e\u539f\u56e0</a></p>'
        if completeness['failed_paths']:
            notice += '<p class="warning">' + str(completeness['failed_paths']) + '\u6761\u8def\u5f84\u4fdd\u7559\u771f\u5b9e\u5931\u8d25\u56de\u6267，\u4e0d\u7ed8\u5236\u865a\u6784\u6548\u5e94，\u4e0d\u8fdb\u5165\u65b9\u5411/\u663e\u8457\u6027\u5206\u6bcd。<a href="declared_unavailable_paths.json">\u9884\u6267\u884c\u80fd\u529b\u58f0\u660e\u4e0e\u5931\u8d25\u539f\u56e0</a></p>'
        if out.name == '03_minwage':
            notice += '<p class="warning">\u672c\u8f6e\u7ed3\u679c\u4e3a\u4eba\u6570\u53e3\u5f84\u7684DiD；\u4f5c\u8005\u4e3b\u8981\u62a5\u544aFTE\u53e3\u5f84。\u672a\u53d1\u73b0\u8d1f\u65b9\u5411、\u68c0\u9a8c\u4e0d\u663e\u8457，\u5747\u4e0d\u80fd\u5355\u72ec\u8bc1\u660e\u65e0\u6548\u5e94、\u7b49\u4ef7\u6216\u56e0\u679c\u5047\u8bbe\u6210\u7acb。</p>'
        if any((d['key'] == 'D_DEPRESSION' for f in plan['families'] for d in f['dimensions'])):
            strata = []
            for f in plan['families']:
                dimension = next((d for d in f['dimensions'] if d['key'] == 'D_DEPRESSION'), None)
                if dimension:
                    for o in dimension['options']:
                        subset = [r for r in rows if r['family_id'] == f['id'] and r['choices'].get('D_DEPRESSION') == o['id']]
                        strata.append({'family_id': f['id'], 'measurement': o['label'], 'option_id': o['id'], 'stats': summarize(subset)})
            save(report / 'measurement_strata.json', {'strata': strata, 'plots_unchanged': True, 'policy': 'Measurement-specific summaries required by the frozen plan; broad curve summaries are exploratory sensitivity summaries.'})
            notice += '<h3>\u6309\u6d4b\u91cf\u53e3\u5f84\u5206\u5c42\u7edf\u8ba1</h3><p>\u6cbf\u7528\u603b\u4f53、\u5bb6\u5ead\u5185、\u5bb6\u5ead\u95f4\u4e09\u5f20\u66f2\u7ebf；\u5404\u66f2\u7ebf\u7684\u6574\u4f53\u6bd4\u4f8b\u4ec5\u4e3a\u63a2\u7d22\u6027\u654f\u611f\u6027\u6982\u89c8。\u6309\u7167\u51bb\u7ed3\u65b9\u6848，\u4e09\u79cd\u6291\u90c1\u6d4b\u91cf\u5206\u522b\u7edf\u8ba1，\u4e0d\u5408\u5e76\u4e3a\u5355\u4e00\u786e\u8ba4\u8bc1\u636e。</p><div class="scroll"><table><tr><th>\u7814\u7a76\u5c42\u7ea7</th><th>Measurement</th><th>\u6210\u529f/\u5931\u8d25</th><th>\u6b63/\u8d1f</th><th>P&lt;0.05/\u6709\u6548P</th></tr>'
            for item in strata:
                t = item['stats']
                notice += '<tr><td>' + esc(item['family_id']) + '</td><td>' + esc(item['measurement']) + '</td><td>' + str(t['successful_effects']) + '/' + str(t['failed_paths']) + '</td><td>' + str(t['positive_count']) + '/' + str(t['negative_count']) + '</td><td>' + str(t['significant_count']) + '/' + str(t['valid_tests']) + '</td></tr>'
            notice += '</table></div><p><a href="measurement_strata.json">\u5b8c\u6574\u5206\u5c42\u5206\u6bcd</a></p>'
        for f in plan['families']:
            notice += '<details><summary>' + esc(f['id']) + '：\u51bb\u7ed3\u7684\u89e3\u91ca\u8303\u56f4</summary><p>' + esc(f['comparison_definition']['interpretation']) + '</p></details>'
        notice += '<p><a href="../\u4fee\u6539\u6e05\u5355.html">\u5168\u90e8\u4fee\u6539、\u5907\u4efd\u4e0e\u9694\u79bb\u68c0\u67e5</a> · <a href="../README.md">\u672c\u6b21\u4ea4\u4ed8\u8bf4\u660e</a></p></article>'
        text = (report / 'index.html').read_text(encoding='utf-8')
        text = text.replace('<article id="curves">', notice + '<article id="curves">', 1)
        (report / 'index.html').write_text(text, encoding='utf-8')
        for foldername in ['case_adapter_v10']:
            if (out / foldername).exists():
                shutil.copytree(out / foldername, report / foldername, dirs_exist_ok=True)
        checks.append({'run_id': cfg['run_id'], 'result_sha256': lock['results_sha256'], 'successful_point_estimates': completeness['successful_point_estimates'], 'valid_p_paths': completeness['paths_with_accepted_p'], 'inference_unavailable': len(unavailable), 'report': str(report)})
    build_batch(batch_path)
    save(dest / 'delivery_integrity.json', {'papers': checks, 'target_five_papers_met': True, 'new_statistical_execution_in_report_builder': False, 'author_result_adaptive_selection': False})
    index = dest / 'index.html'
    text = index.read_text(encoding='utf-8').replace('<h1>\u6d4b\u8bd5\u96c6 · \u81ea\u52a8\u5316\u591a\u8def\u5f84\u5206\u6790</h1>', '<h1>\u4e94\u7bc7\u8bba\u6587 · Specification Curve \u7ed3\u679c\u62a5\u544a</h1>')
    banner = '<article><h2>\u672c\u8f6e\u4ea4\u4ed8：\u4e94\u7bc7\u771f\u5b9e\u6267\u884c\u7ed3\u679c</h2><p>\u672c\u8f6e\u5b8c\u6210\u4e94\u7bc7，\u4e0d\u7ee7\u7eed\u6269\u5c55\u6d4b\u8bd5\u96c6。\u5404\u7bc7\u4fdd\u7559H1、\u5b8c\u6574\u8f93\u5165、\u8def\u7ebfA/B、\u66f2\u7ebf、\u65b9\u5411\u4e0e\u663e\u8457\u6bd4\u4f8b\u53ca\u5b9e\u9645Prompt。</p><p>“\u6210\u529f\u8def\u5f84”\u8868\u793a\u83b7\u5f97\u6709\u9650\u7684\u6709\u6548\u70b9\u4f30\u8ba1；\u6709P\u503c\u7684\u8def\u5f84\u4e0e\u63a8\u65ad\u5b9e\u73b0\u4e0d\u53ef\u7528\u7684\u8def\u5f84\u53e6\u5217。\u5931\u8d25\u8def\u5f84\u4e0d\u4f5c\u4e3a\u96f6\u6548\u5e94\u6216\u4e0d\u663e\u8457，\u5355\u72ec\u4fdd\u7559。\u6761\u4ef6\u6027P\u503c\u53d7\u5404\u81ea\u6a21\u578b\u548c\u6570\u636e\u5047\u8bbe\u9650\u5236，\u6bd4\u4f8b\u4e0d\u662fH1\u6210\u7acb\u6982\u7387。</p><p><a href="\u4fee\u6539\u6e05\u5355.html">\u4ee3\u7801\u4fee\u6539\u4e0e\u539f\u6587\u4ef6\u5907\u4efd</a> · <a href="README.md">\u8bf4\u660e\u548c\u91cd\u65b0\u6253\u5f00\u65b9\u5f0f</a> · <a href="delivery_integrity.json">\u4ea4\u4ed8\u6838\u9a8c</a></p></article>'
    text = text.replace('<main>', '<main>' + banner, 1)
    index.write_text(text, encoding='utf-8')
    return index
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', required=True)
    a = parser.parse_args()
    print(build(a.batch))
