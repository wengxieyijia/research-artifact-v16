# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Presentation from recorded model outputs. No scientific edits."""
from pathlib import Path
import json
import semantic_stitch as s
import task_graph as t
ROOT = Path(__file__).resolve().parent

def encode(x):
    return json.dumps(x, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')

def build(out):
    graph = t.read(out / 'inputs/knowledge_graph.json')
    index = t.read(out / 'semantic_index.json')
    c = graph['classification']
    nodes = [{'id': f['id'], 'kind': 'family', 'label': f['id'] + ' ' + f['name']} for f in c['families']]
    nodes += [{'id': m['id'], 'kind': 'method', 'label': m['id'] + ' ' + m['name']} for m in c['methods']]
    nodes += [{'id': ref, 'kind': 'option', 'label': ref + ' ' + o['option']['label']} for ref, o in graph['original_options'].items()]
    edges = [{'from': m['family_id'], 'to': m['id']} for m in c['methods']]
    seen = set()
    for r in c['rows']:
        for comp in r['components']:
            k = (comp['method_id'], r['source_ref'])
            if k not in seen:
                edges.append({'from': k[0], 'to': k[1]})
                seen.add(k)
    data = {name: t.read(out / (name + '.json')) for name in ['research_context', 'column_ranking', 'task_understanding', 'column_task_retrieval', 'operation_retrieval', 'candidate_screening', 'boba_blueprint', 'verification', 'baseline']}
    data['target_graph'] = t.read(out / t.read(out / 'active_graph.json')['file'])
    data['graph_review'] = t.read(out / 'graph_review.json')
    data['graph'] = {'nodes': nodes, 'edges': edges}
    data['methods'] = index['methods']
    data['boba_template'] = (out / 'boba_template.py').read_text(encoding='utf-8')
    dataset = next((d for d in t.read(out / 'data_features.json')['datasets'] if d['dataset_id'] == data['research_context']['dataset_choice']['dataset_id']))
    data['column_features'] = {col['column_id']: col for col in dataset['columns']}
    template = (ROOT / 'task_graph_fragment.html').read_text(encoding='utf-8')
    fragment = template.replace('__DATA__', encode(data))
    if len(fragment.encode('utf-8')) >= 1000000:
        raise ValueError('Inline payload over 1MB: compact metadata without altering results')
    (out / 'task-options.html').write_text(fragment, encoding='utf-8')
    shell = (ROOT / 'semantic_stitch_shell.html').read_text(encoding='utf-8').replace('\u6570\u636e\u5217\u6392\u5e8f、\u73b0\u6709\u56fe\u68c0\u7d22\u4e0e\u6d41\u7a0b\u62fc\u63a5', '\u4efb\u52a1\u9a71\u52a8\u7684Decision–Option\u4e0eBoba\u8349\u6848').replace("document.getElementById('semantic-stitch-lab')", "document.getElementById('task-option-lab')")
    (out / 'index.html').write_text(shell.replace('__COMPONENTS__', encode(index['components'])).replace('__FRAGMENT__', fragment), encoding='utf-8')
    t.save(out / '\u5c55\u793a\u6570\u636e.json', data)
    write_readme(out, data)
    print('Target graph browser built; inline bytes=' + str(len(fragment.encode('utf-8'))), flush=True)

def write_readme(out, d):
    v = d['verification']
    g = d['target_graph']
    screen = d['candidate_screening']
    bp = d['boba_blueprint']
    limits = '\n'.join(('- ' + str(x) for x in g['limitations']))
    unknown = '\n'.join(('- ' + r['method_id'] + '：' + r['reason'] for r in screen['candidates'] if r['status'] == 'conditional'))
    counts = v['screening_counts']
    count_text = f'\u63a5\u53d7{counts['accept']}、\u6709\u6761\u4ef6{counts['conditional']}、\u62d2\u7edd{counts['reject']}、\u672a\u77e5{counts['unknown']}'
    provenance_text = '；'.join((k + ' ' + str(n) + '\u4e2a' for k, n in v['option_provenance'].items()))
    used = '、'.join(v.get('used_existing_method_ids', [])) or '\u65e0'
    text = f'# \u4efb\u52a1\u9a71\u52a8\u7684 Decision–Option \u8bd5\u9519\n\n## \u505a\u4e86\u4ec0\u4e48\n\n\u6cbf\u7528\u4e8c\u5341\u7bc7\u4e4b\u5916\u540c\u4e00\u7bc7\u8bba\u6587、H1\u548c71\u5217\u6392\u5e8f。DeepSeek\u5148\u7406\u89e3\u7814\u7a76\u4efb\u52a1，\u518d\u505a\u5217\u8bed\u4e49\u68c0\u7d22\u548c\u5168\u5e93\u64cd\u4f5c\u68c0\u7d22，\u9010\u9879\u7b5b\u9009\u5168\u90e8\u5019\u9009，\u751f\u6210\u76ee\u6807\u8bba\u6587\u7684\u56fa\u5b9a\u6b65\u9aa4\u4e0eDecision–Option\u56fe，\u6700\u540e\u751f\u6210\u7b2c\u4e00\u7248Boba\u6a21\u677f。\u7a0b\u5e8f\u8d1f\u8d23\u5f15\u7528、\u5217\u540d、\u4f9d\u8d56、\u6765\u6e90\u548c\u8bed\u6cd5\u6821\u9a8c；\u5f00\u53d1\u8005\u6ca1\u6709\u624b\u6539\u79d1\u7814\u5224\u65ad。\n\n## \u7ed3\u679c\n\n- {v['operations']}\u4e2a\u64cd\u4f5c；\u539f16\u4e2a\u5019\u9009\u5168\u90e8\u4fdd\u7559\u5ba1\u6838，\u672c\u8f6e\u5e76\u96c6\u5171{v['screened_candidates']}\u4e2a\u65b9\u6cd5。\u7b5b\u9009：{count_text}。\n- \u76ee\u6807\u56fe{v['steps']}\u6b65、{v['decisions']}\u4e2aDecision、{v['options']}\u4e2aOption。\u6765\u6e90：{provenance_text}。\n- {v['specifications']}\u5957\u8349\u6848\u53caBoba\u6a21\u677f\u5df2\u751f\u6210，Python\u8bed\u6cd5\u68c0\u67e5\u901a\u8fc7。**\u6ca1\u6709\u8fd0\u884c\u6570\u636e\u5206\u6790，\u6ca1\u6709\u4f30\u8ba1\u503c、P\u503c\u6216\u66f2\u7ebf。**\n- \u5f53\u524d\u56fe\u76f4\u63a5\u5f15\u7528\u7684\u65e2\u6709M：{used}；\u672a\u89e3\u51b3\u6b65\u9aa4{v.get('unresolved_steps', 0)}\u4e2a。\u68c0\u7d22\u53ec\u56de\u4e0d\u7b49\u4e8e\u6210\u529f\u590d\u7528，\u672c\u8f6e\u7ed3\u679c\u4e0d\u80fd\u8bc1\u660e\u77e5\u8bc6\u5e93\u5df2\u80fd\u8986\u76d6\u65b0\u4efb\u52a1。\n- \u521d\u7a3f\u81ea\u52a8\u590d\u6838\u53d1\u73b0{v.get('automatic_review_issues', 0)}\u9879\u95ee\u9898，DeepSeek\u636e\u6b64\u751f\u6210\u4fee\u8ba2\u56fe；\u5305\u62ec\u7b49\u4ef7\u5b9e\u73b0\u91cd\u590d、\u76ee\u6807\u6df7\u5408/\u8303\u56f4\u548c\u63a8\u65ad\u53c2\u6570\u95ee\u9898，\u521d\u7a3f\u4e0e\u590d\u6838\u5747\u4fdd\u7559。\u81ea\u52a8\u590d\u6838\u4ecd\u4e0d\u662f\u72ec\u7acb\u79d1\u7814\u6b63\u786e\u6027\u8ba4\u8bc1。\n- \u4e8c\u5341\u7bc7\u77e5\u8bc6\u5e93\u4fdd\u6301\u51bb\u7ed3，\u65b0\u589e\u5185\u5bb9\u53ea\u5b58\u5728\u672c\u8f6e\u76ee\u6807\u56fe。\u989c\u8272\u4e0e\u6587\u5b57\u53cc\u6807\u7b7e；DeepSeek\u65b0\u589e\u66ff\u4ee3Option\u5747\u6807 `proposed`。Method\u6765\u6e90\u4e0e\u6574\u4e2aOption\u6765\u6e90\u5206\u5f00\u8bb0\u5f55。\n\n## \u600e\u4e48\u770b\n\n\u6253\u5f00 [index.html](index.html)，\u4f9d\u6b21\u770b\u4efb\u52a1\u7406\u89e3、\u5217\u6392\u5e8f、\u539f\u56fe\u68c0\u7d22、\u5b8c\u6574\u7b5b\u9009\u8bb0\u5f55、Decision–Option\u56fe\u4e0eBoba\u6a21\u677f。\u70b9\u51fbOption\u5c55\u5f00\u65b9\u6cd5、\u6570\u636e\u7ed1\u5b9a/\u8bed\u4e49、\u5b8c\u6574\u53c2\u6570、\u7ec4\u4ef6\u548c\u6765\u6e90；\u540cDecision\u4e0b\u5c55\u793a\u4e92\u6362\u8bf4\u660e。\u539f\u56feF→M→\u539f\u8bba\u6587Option\u662f\u77e5\u8bc6\u5f52\u5c5e\u7ed3\u6784；\u672c\u8f6e\u56fa\u5b9a\u6b65\u9aa4/Decision→Option\u662f\u76ee\u6807\u5206\u6790\u7ed3\u6784，\u4e24\u8005\u4e0d\u662f\u540c\u4e00\u5c42\u7ea7。\n\n## \u4ecd\u6709\u4ec0\u4e48\u95ee\u9898\n\n\u4e0b\u9762\u662fDeepSeek\u8bb0\u5f55\u7684\u9650\u5236，\u672a\u7531\u5f00\u53d1\u8005\u6539\u6210\u901a\u8fc7：\n\n{limits}\n\n\u6761\u4ef6\u6027\u590d\u7528\u8bb0\u5f55：\n\n{unknown or '- \u65e0\u6761\u4ef6\u6027\u5019\u9009。'}\n\n\u7ed3\u6784\u68c0\u67e5、\u8bed\u6cd5\u68c0\u67e5\u4e0d\u8bc1\u660e\u7edf\u8ba1\u9002\u7528\u6216\u63a8\u65ad\u6709\u6548。`proposed`\u8868\u793a\u6a21\u578b\u5efa\u8bae，\u4e0d\u80fd\u5f53\u4f5c\u539f\u6587\u4f9d\u636e；\u540c\u76ee\u6807\u53ef\u66ff\u6362\u6027\u4ecd\u662f\u6a21\u578b\u5224\u65ad。\u91cd\u65b0\u8c03\u7528\u6a21\u578b\u4e0d\u4fdd\u8bc1\u76f8\u540c\u7ed3\u679c；\u51bb\u7ed3\u7f13\u5b58\u79bb\u7ebf\u91cd\u653e\u4fdd\u8bc1\u672c\u7248\u7ed3\u679c\u53ef\u7559\u5b58。\n\n## \u72ec\u7acb\u8fd0\u884c\n\n\u9879\u76ee\u6839\u76ee\u5f55\u8fd0\u884c `python outputs/decision_option_lab/task_graph.py --replay`；\u666e\u901a\u8fd0\u884c\u53bb\u6389`--replay`。\u9700\u8981\u65b0\u8c03\u7528\u65f6，key\u53ea\u653e`outputs/decision_option_lab/.env`。\u672c\u8f6e\u5165\u53e3\u6309\u5df2\u51bb\u7ed3\u7684\u57fa\u7840\u8bba\u6587、\u5217\u7279\u5f81、H1\u4e0e\u6392\u5e8f\u7ee7\u7eed，\u4e0d\u91cd\u63d0\u4e8c\u5341\u7bc7；\u66f4\u6362\u57fa\u7840\u8f93\u5165\u7528`--baseline`，\u65b0\u7ed3\u679c\u7528`--output`。\u6570\u636e\u91cd\u65b0\u6d4b\u91cf\u6cbf\u7528`semantic_stitch.py`\u51c6\u5907\u9636\u6bb5。\n\n\u4ee3\u7801\u65b0\u589e：task_graph.py、task_graph_view.py、\u72ec\u7acb\u6807\u51c6/\u6307\u4ee4/\u5951\u7ea6\u53ca\u5c55\u793a\u6a21\u677f。\u65e7Decision–Option\u63d0\u53d6、\u4e8c\u5341\u7bc7\u5408\u5e76\u4ee3\u7801\u548c\u65e7\u7ed3\u679c\u672a\u4fee\u6539。\u539f\u6587\u548c\u4f5c\u8005\u4ee3\u7801\u4f5c\u4e3a\u8bc1\u636e\u6587\u5b57，\u672a\u6267\u884c\u4f5c\u8005\u4ee3\u7801。Boba\u683c\u5f0f\u4f9d\u636e[\u5b98\u65b9\u89c4\u8303](https://github.com/uwdata/boba/blob/master/tutorial/rules.md)。\n'
    (out / 'README.md').write_text(text, encoding='utf-8')
    (out / 'run.ps1').write_text("param([switch]$Replay)\n$entry=Join-Path $PSScriptRoot '../decision_option_lab/task_graph.py'\nif($Replay){python $entry --output $PSScriptRoot --replay}else{python $entry --output $PSScriptRoot}\n", encoding='utf-8')
if __name__ == '__main__':
    build(t.DEFAULT)
