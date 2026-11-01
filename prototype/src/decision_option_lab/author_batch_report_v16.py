# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Offline multi-paper homepage/navigation. Never calls a model or executes statistics.

Usage: python batch_report_v9.py --manifest batch.json
batch.json: {"output":".../batch-report", "papers":[{"manifest":".../trial.json","label":"Paper 1"}]}
Use each single-trial manifest's report path for its page, normally under output/paper_01/.
"""
import argparse, html, json, os
from pathlib import Path

def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')

def esc(v):
    return html.escape(str(v), quote=True)

def pct(v):
    return 'NA' if v is None else f'{100 * v:.1f}%'

def rel(target, start):
    return Path(os.path.relpath(target, start)).as_posix()

def inject_page(report, navigation, summary, state):
    """Keep report's saved data/downloads; only add links and its mechanical summary."""
    report.mkdir(exist_ok=True, parents=True)
    write(report / 'paper_navigation.json', navigation)
    index = report / 'index.html'
    if not index.exists():
        index.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>\u8fd0\u884c\u5c1a\u672a\u5b8c\u6210</title><body style="font:16px/1.8 Arial,sans-serif;padding:30px;background:#f3f6f8"><nav>' + ''.join(('<a style="margin-right:18px" href="' + esc(n['href']) + '">' + esc(n['label']) + '</a>' for n in navigation)) + '<h1>\u5c1a\u65e0\u5b8c\u6574\u62a5\u544a</h1><p>\u6b64\u8bba\u6587\u5c1a\u672a\u5b8c\u6210\u8fd0\u884c。\u7f3a\u5c11\u7ed3\u679c\u4e0d\u4ee3\u8868\u6548\u5e94\u4e3a\u96f6\u6216\u4e0d\u663e\u8457。</p></body></html>', encoding='utf-8')
        return
    text = index.read_text(encoding='utf-8')
    if 'const R=' not in text:
        return
    start = text.index('const R=') + len('const R=')
    data, end = json.JSONDecoder().raw_decode(text[start:])
    data['navigation'] = navigation
    data['state'] = state
    if summary is not None:
        data['summary'] = summary
        write(report / 'summary.json', summary)
    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('</', '<' + chr(92) + '/')
    index.write_text(text[:start] + encoded + text[start + end:], encoding='utf-8')

def group_card(group):
    s = group['stats']
    d = s.get('author_direction_comparison') or {}
    z = s.get('author_significance_comparison') or {}
    sig = f'{s['significant_count']}/{s['significance_denominator']}＝{pct(s['significant_fraction'])}' if s['significance_denominator'] else 'NA（\u65e0\u53ef\u7528P\u503c\u5206\u6bcd）'
    body = f'<b>{esc(group['title'])}</b><ul><li>\u6210\u529f\u6548\u5e94 {s['successful_effects']} \u6761；\u7edf\u4e00\u7f16\u7801\u6b63\u65b9\u5411 {s['positive_count']}/{s['direction_denominator']}＝{pct(s['positive_fraction'])}，\u8d1f\u65b9\u5411 {s['negative_count']}/{s['direction_denominator']}＝{pct(s['negative_fraction'])}。</li><li>\u663e\u8457\u6bd4\u4f8b {sig}；P\u4e3aNA {s['p_unavailable']} \u6761，\u65e0\u6548 {s['p_invalid']} \u6761。</li><li>\u4f5c\u8005\u65b9\u5411\u4e00\u81f4\u7387：{pct(d.get('agreement_fraction'))}（\u53ef\u6bd4{d.get('eligible_paths', 0)}\u6761）；{esc(z.get('metric_label', '\u4f5c\u8005\u663e\u8457\u6027\u4e00\u81f4\u7387'))}：{pct(z.get('agreement_fraction'))}（\u4e00\u81f4/\u53ef\u6bd4 {z.get('agreeing_paths', 0)}/{z.get('eligible_paths', 0)}）。</li></ul>'
    common = s.get('author_significance_comparison_common_alpha') or {}
    reported = s.get('author_reported_conclusion_comparison') or {}
    if common or reported:
        body += '<p class="muted">\u7edf\u4e000.05：' + pct(common.get('agreement_fraction')) + '（' + str(common.get('agreeing_paths', 0)) + '/' + str(common.get('eligible_paths', 0)) + '）；\u4f5c\u8005\u62a5\u544a\u7ed3\u8bba：' + pct(reported.get('agreement_fraction')) + '（' + str(reported.get('agreeing_paths', 0)) + '/' + str(reported.get('eligible_paths', 0)) + '）。\u4e24\u79cd\u53e3\u5f84\u5206\u5f00，\u4e0d\u6df7\u5408\u5206\u6bcd。</p>'
    direction = group.get('direction_encoding')
    raw = group.get('raw_effect_sign_counts')
    if direction:
        body += '<p class="muted">\u7edf\u4e00\u7f16\u7801\u65b9\u5411＝（\u539f\u59cb\u6548\u5e94 − ' + esc(direction['null_value']) + '）× ' + esc(' / '.join(map(str, direction['direction_multipliers']))) + '。\u6b63\u65b9\u5411\u542b\u4e49：' + esc('；'.join(direction['positive_meanings'])) + '</p>'
    if raw:
        body += f"<p class='muted'>\u539f\u59cb\u66f2\u7ebf\u76f8\u5bf9\u96f6\u6548\u5e94\u57fa\u51c6\u7684\u7b26\u53f7：\u6b63 {raw['positive']}／\u8d1f {raw['negative']}／\u96f6 {raw['zero']}（\u5206\u6bcd {raw['denominator']}），\u5c1a\u672a\u4e58\u65b9\u5411\u7f16\u7801。</p>"
    if group.get('conditional_test_count'):
        years = group.get('conditional_test_observed_year_counts', [])
        body += f"<p class='warning'>{group['conditional_test_count']} \u6761P\u503c\u4e3a\u6761\u4ef6\u6027\u68c0\u9a8c。" + ('\u5df2\u8bb0\u5f55\u5b9e\u9645\u68c0\u9a8c\u65f6\u671f\u6570：' + esc(' / '.join(map(str, years))) + '。' if years else '') + '\u6bd4\u4f8b\u53d7\u51bb\u7ed3\u6a21\u578b\u548c\u6837\u672c\u524d\u63d0\u9650\u5236，\u4e0d\u80fd\u89e3\u91ca\u4e3a\u63a8\u65ad\u53ef\u9760\u6027\u5df2\u83b7\u9a8c\u8bc1。</p>'
    return '<div class="group">' + body + '</div>'

def build_batch(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    config = read(manifest_path)
    dest = Path(config['output']).resolve()
    dest.mkdir(exist_ok=True, parents=True)
    papers = []
    for item in config['papers']:
        source = Path(item['manifest'])
        source = source if source.is_absolute() else manifest_path.parent / source
        cfg = read(source)
        report = Path(item.get('report_override', cfg['report'])).resolve()
        out = Path(cfg['output']).resolve()
        if report == dest:
            raise ValueError('Batch homepage and a single-paper page cannot share one directory')
        state = read(out / 'run_state.json', {})
        ingest = read(out / 'ingestion_receipt.json', {})
        summary = read(report / 'summary.json')
        if summary is not None:
            summary['run_status'] = state.get('status', 'pending')
        errors = [{'stage': k, 'error': v.get('error')} for k, v in state.get('stages', {}).items() if v.get('status') == 'blocked']
        papers.append({'label': item.get('label') or ingest.get('paper', {}).get('title') or cfg['run_id'], 'title': ingest.get('paper', {}).get('title') or item.get('label', cfg['run_id']), 'run_id': cfg['run_id'], 'h1': read(out / 'h1_public.json', {}).get('text'), 'status': state.get('status', 'pending'), 'report_path': str(report), 'href': rel(report / 'index.html', dest), 'summary': summary, 'state': state, 'blocked_stages': errors, 'manifest': str(source.resolve())})
    if len({p['report_path'] for p in papers}) != len(papers):
        raise ValueError('Each paper needs an independent report directory')
    for current in papers:
        report = Path(current['report_path'])
        navigation = [{'label': '← \u6d4b\u8bd5\u96c6\u603b\u89c8', 'href': rel(dest / 'index.html', report)}] + [{'label': p['label'] + ('（\u5f53\u524d）' if p is current else ''), 'href': rel(Path(p['report_path']) / 'index.html', report)} for p in papers]
        inject_page(report, navigation, current['summary'], current['state'])
    cards = []
    for i, p in enumerate(papers, 1):
        summary = p['summary']
        headline = '\u5c1a\u65e0\u6267\u884c\u7ed3\u679c'
        if summary:
            headline = f'\u51bb\u7ed3 {(summary['frozen_paths'] if summary['frozen_paths'] is not None else '\u5f85\u5b8c\u6210')} \u6761；\u6267\u884c {summary['executed_paths']} \u6761；\u6210\u529f {summary['successful_paths']} \u6761；\u5931\u8d25 {summary['failed_paths']} \u6761；\u66f2\u7ebf {summary['curve_groups']} \u7ec4'
        error = ''.join(('<p class="warning">' + esc(r['stage']) + '：' + esc(r['error']) + '</p>' for r in p['blocked_stages']))
        groups = ''.join((group_card(g) for g in (summary or {}).get('groups', [])))
        if not groups:
            groups = '<p class="muted">\u7edf\u8ba1\u9636\u6bb5\u5c1a\u672a\u5b8c\u6210。\u8bf7\u6253\u5f00\u8be5\u7bc7\u62a5\u544a\u67e5\u770b\u5df2\u5b8c\u6210\u7684\u68c0\u67e5\u70b9\u548c\u963b\u65ad\u539f\u56e0。</p>'
        cards.append(f'<article><div class="paperhead"><span class="number">{i:02}</span><div><h2>{esc(p['label'])}</h2><span class="tag {('blocked' if p['status'] == 'blocked' else '')}">{esc(p['status'])}</span></div></div><p>{esc(p['title'])}</p><p><b>H1：</b>{esc(p['h1'] or '\u5c1a\u672a\u5b8c\u6210\u5355\u4e00H1\u6838\u9a8c')}</p><p class="headline">{esc(headline)}</p>{error}{groups}<p><a class="button" href="{esc(p['href'])}">\u6253\u5f00\u672c\u7bc7\u5b8c\u6574\u4ea4\u4e92\u62a5\u544a →</a></p></article>')
    nav = ''.join((f'<a href="{esc(p['href'])}">{i + 1}. {esc(p['label'])}</a>' for i, p in enumerate(papers)))
    page = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>\u591a\u7bc7\u8bba\u6587 · \u81ea\u52a8\u5316\u591a\u8def\u5f84\u5206\u6790</title><style>\n*{box-sizing:border-box}body{margin:0;background:#f3f6f8;color:#243e50;font:14px/1.8 \'Microsoft YaHei\',Arial,sans-serif}header{background:#1c5268;color:white;padding:30px max(24px,6vw)}header h1{margin:0;font-size:28px}nav{display:flex;flex-wrap:wrap;gap:16px}nav a{color:#d1edf2}main{max-width:1300px;margin:auto;padding:24px}article{background:white;border:1px solid #dce6eb;border-radius:9px;padding:24px;margin-bottom:23px}h2{font-size:22px;margin:0}a{color:#187490;text-decoration:none}a:hover{text-decoration:underline}.paperhead{display:flex;gap:16px;align-items:center}.number{font-size:34px;color:#538e9b}.tag{font-size:12px;background:#e4f1ea;border-radius:12px;padding:3px 10px;display:inline-block}.blocked{background:#ffe4da;color:#8a443a}.headline{font-size:16px;background:#edf5f7;padding:12px}.group{border-top:1px solid #e5edf1;padding-top:15px;margin-top:16px}.warning{background:#fff4dd;border-left:3px solid #c69a42;padding:12px}.notice{background:#edf5f7;border-left:3px solid #538e9b;padding:15px;margin-bottom:24px}.muted{color:#607987}.button{display:inline-block;background:#1c5268;color:white;border-radius:5px;padding:9px 15px}ul{padding-left:24px}@media(max-width:600px){main{padding:12px}article{padding:17px}header h1{font-size:24px}}\n</style></head><body><header><h1>\u6d4b\u8bd5\u96c6 · \u81ea\u52a8\u5316\u591a\u8def\u5f84\u5206\u6790</h1><p>\u540c\u4e00\u5165\u53e3、\u9010\u7bc7\u9694\u79bb；\u6309\u5171\u540c\u7814\u7a76\u95ee\u9898\u7ed8\u5236\u66f2\u7ebf\u5e76\u8bc4\u4ef7\u65b9\u5411\u4e0e\u663e\u8457\u6bd4\u4f8b。</p><nav>' + nav + '</nav></header><main><div class="notice">\u6bcf\u7bc7\u4fdd\u7559\u72ec\u7acbH1、Data、\u8def\u7ebfA/B、\u65b9\u6848\u4e0e\u4f5c\u8005\u53c2\u7167\u5f00\u653e\u8bb0\u5f55。\u5408\u7406Option\u7559\u5728\u540c\u4e00\u53ef\u6bd4\u8f83\u95ee\u9898\u4e2d；\u4e0d\u540c\u8bba\u6587／\u7814\u7a76\u95ee\u9898\u4e0d\u5408\u5e76\u4e3a\u4e00\u6761\u66f2\u7ebf，\u4e5f\u4e0d\u6c47\u6210\u4e00\u4e2a\u6574\u4f53\u663e\u8457\u6bd4\u4f8b。P\u4e3aNA\u4e0d\u7b49\u4e8e\u4e0d\u663e\u8457。\u6765\u6e90、\u5b8c\u6574\u4e94\u9879\u8f93\u5165\u548c\u5b9e\u9645Prompt\u5728\u5404\u7bc7\u9875\u9762\u4e2d\u4fdd\u7559。</div>' + ''.join(cards) + '<p class="muted">\u6b64\u9996\u9875\u4ec5\u6c47\u603b\u5df2\u4fdd\u5b58\u7ed3\u679c，\u4e0d\u8c03\u7528\u6a21\u578b，\u4e0d\u91cd\u65b0\u6267\u884c\u7edf\u8ba1。<a href="batch_summary.json">\u5b8c\u6574\u6279\u6b21\u72b6\u6001\u4e0e\u5206\u6bcd</a></p></main></body></html>'
    (dest / 'index.html').write_text(page, encoding='utf-8')
    write(dest / 'batch_summary.json', {'papers': papers, 'policy': 'No pooling across different papers/questions; NA excluded from significance denominators; no result estimation in this report module.'})
    return dest / 'index.html'
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True)
    args = parser.parse_args()
    print(build_batch(args.manifest))
