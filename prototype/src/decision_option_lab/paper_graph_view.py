# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Display recorded scientific outputs only; never infer or alter graph content."""
import json
from pathlib import Path
import lab
import paper_graph_trial as p
from task_graph_view import encode
ROOT = Path(__file__).resolve().parent

def curve(out, rows, groups):
    successful = [r for r in rows if r['status'] == 'ok']
    if not successful:
        return None
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    matplotlib.rcParams['svg.hashsalt'] = 'paper-graph-frozen-pilot'
    gs = [g for g in groups if any((r['group_id'] == g['id'] for r in successful))]
    fig, axes = plt.subplots(len(gs), 1, figsize=(8, 3.5 * len(gs)), squeeze=False, layout='constrained')
    for ax, g in zip(axes[:, 0], gs):
        rr = sorted([r for r in successful if r['group_id'] == g['id']], key=lambda r: (r['result']['estimate'], r['spec_id']))
        for i, r in enumerate(rr):
            v = r['result']
            ax.plot(i, v['estimate'], 'o', color='#2369b6')
            if v['ci_low'] is not None:
                ax.vlines(i, v['ci_low'], v['ci_high'], color='#2369b6', linewidth=1.5)
            ax.annotate(f'{v['estimate']:.4f}', xy=(i, v['estimate']), xytext=(9, 8), textcoords='offset points')
        ax.axhline(g['null_value'], color='#777777', linewidth=0.8)
        ax.set_xticks(range(len(rr)), [r['spec_id'] for r in rr])
        ax.set_xlim(-0.6, len(rr) - 0.4)
        ax.set_title(g['id'] + ' | ' + g['metric_id'])
        ax.set_xlabel('Preselected specification (sorted by estimate)')
        ax.set_ylabel('Correlation coefficient')
        ax.grid(axis='y', alpha=0.15)
        ax.spines[['top', 'right']].set_visible(False)
    fig.suptitle('Pilot specification curve — separate target groups')
    fig.savefig(out / 'specification_curve.png', dpi=180)
    fig.savefig(out / 'specification_curve.svg', metadata={'Date': None})
    plt.close(fig)
    return 'specification_curve.png'

def build(out):
    r = lambda n: p.read(out / (n + '.json'))
    d = {n: r(n) for n in ['research_context', 'column_ranking', 'graph1_reported', 'graph2_expanded', 'graph2_expansion', 'specification_plan', 'analysis_freeze', 'verification', 'execution_results', 'accepted_audit', 'accepted_code', 'path_space', 'boba_compiler_verification']}
    d['path_space'].pop('choices', None)
    kg = p.read(out / 'inputs/knowledge_graph.json')
    idx = r('semantic_index')
    c = kg['classification']
    nodes = [{'id': f['id'], 'kind': 'family', 'label': f['id'] + ' ' + f['name']} for f in c['families']]
    nodes += [{'id': m['id'], 'kind': 'method', 'label': m['id'] + ' ' + m['name']} for m in c['methods']]
    nodes += [{'id': ref, 'kind': 'option', 'label': ref + ' ' + o['option']['label']} for ref, o in kg['original_options'].items()]
    edges = [{'from': m['family_id'], 'to': m['id']} for m in c['methods']]
    seen = set()
    for row in c['rows']:
        for comp in row['components']:
            key = (comp['method_id'], row['source_ref'])
            if key not in seen:
                edges.append({'from': key[0], 'to': key[1]})
                seen.add(key)
    d['knowledge_graph'] = {'nodes': nodes, 'edges': edges}
    d['methods'] = idx['methods']
    dataset = next((x for x in r('data_features')['datasets'] if x['dataset_id'] == d['research_context']['dataset_choice']['dataset_id']))
    d['column_features'] = {col['column_id']: col for col in dataset['columns']}
    for row in d['execution_results']:
        if row['status'] == 'ok':
            row['result'].pop('analysis_unit_ids', None)
    d['boba_config'] = r('boba_config')
    p.save(out / '\u5c55\u793a\u6570\u636e.json', d)
    html = (ROOT / 'paper_graph_fragment.html').read_text('utf-8').replace('__DATA__', encode(d))
    if len(html.encode('utf-8')) >= 1000000:
        raise ValueError('Inline view exceeds 1MB')
    (out / 'paper-graph-expansion.html').write_text(html, encoding='utf-8')
    shell = (ROOT / 'semantic_stitch_shell.html').read_text('utf-8').replace('\u6570\u636e\u5217\u6392\u5e8f、\u73b0\u6709\u56fe\u68c0\u7d22\u4e0e\u6d41\u7a0b\u62fc\u63a5', '\u539f\u8bba\u6587\u56fe1 → \u77e5\u8bc6\u5e93\u6269\u5c55\u56fe2 → \u5206\u6790\u8def\u5f84').replace('semantic-stitch-lab', 'paper-graph-lab')
    (out / 'index.html').write_text(shell.replace('__COMPONENTS__', encode(idx['components'])).replace('__FRAGMENT__', html), encoding='utf-8')
    curve(out, p.read(out / 'execution_results.json'), d['specification_plan']['comparison_groups'])
    readme(out, d)
    print('Graph1/graph2 browser built; inline bytes=' + str(len(html.encode('utf-8'))), flush=True)

def readme(out, d):
    v = d['verification']
    groups = d['specification_plan']['comparison_groups']
    patch = d['graph2_expansion']
    result = []
    for row in d['execution_results']:
        if row['status'] == 'ok':
            x = row['result']
            result.append(f'- {row['spec_id']} / {row['group_id']}：\u4f30\u8ba1\u503c{x['estimate']:.6g}，P\u503c{x['pvalue']}，\u533a\u95f4[{x['ci_low']}, {x['ci_high']}]，\u5b9e\u9645\u5206\u6790\u5355\u5143{x['nobs']}。')
        else:
            result.append('- ' + row['spec_id'] + '：' + row['status'] + '；' + str(row.get('error', '')))
    text = f'# \u56fe1 → \u56fe2 → Boba：\u5feb\u901f\u8bd5\u9519\n\n## \u505a\u4e86\u4ec0\u4e48\n\u6cbf\u7528\u4e8c\u5341\u7bc7\u4e4b\u5916\u7684GEOWEALTH-US\u8bba\u6587\u53ca\u5df2\u63d0\u53d6H1。DeepSeek\u91cd\u65b0\u63d0\u53d6\u8be5H1\u7684\u539f\u6587reported Decision–Option\u4e3a\u56fe1，\u518d\u5339\u914d\u51bb\u7ed3\u4e8c\u5341\u7bc7\u77e5\u8bc6\u5e93\u7684\u65b9\u6cd5\u6838\u5fc3，\u4e3a\u65b0\u6570\u636e\u914d\u7f6e\u6269\u5c55\u56fe2，\u51bb\u7ed3\u7814\u7a76\u76ee\u6807、\u6bd4\u8f83\u7ec4\u548c2—3\u6761\u8bd5\u8dd1\u8def\u5f84，\u751f\u6210\u4ee3\u7801\u5e76\u53e6\u6b21\u81ea\u52a8\u590d\u6838，\u6700\u540e\u8fd0\u884c\u5b9e\u9645\u6570\u636e。\n\n\u5f00\u53d1\u8005\u53ea\u5b9e\u73b0\u7a0b\u5e8f、\u7ed3\u6784/\u6765\u6e90\u68c0\u67e5、\u8fd0\u884c\u548c\u5c55\u793a，\u6ca1\u6709\u624b\u6539\u8bba\u6587\u79d1\u7814\u5224\u65ad、Option\u6216\u6620\u5c04。\u539f\u4e8c\u5341\u7bc7\u63d0\u53d6、\u5408\u5e76\u4ee3\u7801\u4e0e\u77e5\u8bc6\u5e93\u672a\u4fee\u6539。\n\n## \u7ed3\u679c\n- \u56fe1：{v['graph1_decisions']}\u4e2aDecision、{v['graph1_reported_options']}\u4e2areported Option；\u5355\u4e00Option\u8868\u793a\u53ea\u63d0\u53d6\u5230\u4e00\u79cd\u62a5\u544a\u65b9\u5f0f，\u4e0d\u4ee3\u8868\u5df2\u7ecf\u5b58\u5728\u591a\u79cd\u65b9\u6848。\n- \u56fe2：{v['graph2_decisions']}\u4e2aDecision、{v['graph2_options']}\u4e2aOption；\u65b0\u589e{v['new_options']}\u4e2a\u914d\u7f6e，\u5747\u6807proposed。\u5f15\u7528\u65e2\u6709\u65b9\u6cd5：{'、'.join(v['catalog_method_ids_used']) or '\u65e0'}。\n- \u7ed3\u6784\u7ec4\u5408{d['path_space']['raw_combinations']}\u4e2a；\u901a\u8fc7\u56fe\u4e2d\u663e\u5f0f\u7981\u914d\u7ea6\u675f{d['path_space']['constraint_feasible_examined']}\u4e2a。\u8fd9\u4e0d\u662f\u5df2\u901a\u8fc7\u79d1\u7814\u9002\u7528\u6027\u5ba1\u6838\u7684\u65b9\u6848\u6570；\u53ea\u9884\u9009{v['preselected_paths']}\u6761\u5b9e\u9645\u8bd5\u8dd1，\u6210\u529f{v['successful_paths']}\u6761。\n- \u9884\u5148\u5206{v['comparison_groups']}\u4e2a\u6bd4\u8f83\u7ec4，\u4e0d\u628a\u603b\u4f53\u6216\u6307\u6807\u4e0d\u540c\u7684\u7ed3\u679c\u5e76\u6210\u4e00\u6761\u66f2\u7ebf。Boba\u5b98\u65b9\u7f16\u8bd1\u4e0e\u51bb\u7ed3\u9009\u62e9\u6838\u5bf9\u89c1boba_compiler_verification.json。\u6a21\u677f\u7ecf\u5b98\u65b9\u7f16\u8bd1，\u5b9e\u9645\u5206\u6790\u7531\u53d7\u9650\u6267\u884c\u5668\u8c03\u7528\u540c\u4e00analyze\u51fd\u6570\u548c\u51bb\u7ed3\u9009\u62e9；\u672a\u8c03\u7528Boba\u7684\u6279\u91cf\u8fd0\u884c\u8c03\u5ea6\u5668。\n\n{chr(10).join(result)}\n\n## \u600e\u6837\u68c0\u67e5\n\u6253\u5f00[index.html](index.html)：①\u56fe1/\u56fe2\u53ca\u5c42\u7ea7\u89e3\u91ca；②H1\u4e0e71\u5217\u6392\u5e8f、\u666e\u901a\u4ee3\u7801\u6d4b\u91cf\u7279\u5f81；③\u539f\u4e8c\u5341\u7bc7\u5b8c\u6574F→M→O\u56fe\u548c\u672c\u8f6e\u547d\u4e2d；④\u6bcf\u4e2a\u5019\u9009\u7edf\u4e00\u7b5b\u9009\u8bb0\u5f55；⑤\u8def\u5f84、\u5b9e\u9645\u7ed3\u679c\u4e0e\u66f2\u7ebf；⑥\u4ee3\u7801、\u5b8c\u6574\u53c2\u6570\u53ca\u81ea\u52a8\u590d\u6838。\n\n\u989c\u8272\u548c\u6587\u5b57\u540c\u65f6\u533a\u5206：reported\u4e3a\u539f\u8bba\u6587\u6709\u636e；proposed\u4e3aDeepSeek\u4e3a\u76ee\u6807\u8bba\u6587\u63d0\u51fa\u7684Option\u914d\u7f6e。\u914d\u7f6e\u5185\u90e8\u7684Method\u53e6\u6807reused/adapted/technical_glue，\u5e76\u4fdd\u7559M\u548c\u539f\u7ec4\u4ef6\u7f16\u53f7。\u539f\u6587Option\u4fdd\u6301\u539f\u6837，\u539f\u6587\u6ca1\u6709\u62a5\u544a\u7684\u53c2\u6570\u4ecd\u4e3aunknown；\u6269\u5c55\u4e0d\u4f1a\u628a\u5b83\u4eec\u6539\u6210\u4f5c\u8005\u62a5\u544a。\n\n\u77e5\u8bc6\u5e93F→M→\u539fOption\u662f\u77e5\u8bc6\u5f52\u5c5e；\u76ee\u6807\u56feDecision→Option\u662f\u5206\u6790\u9009\u62e9；Method\u5728Option\u5185\u90e8。\u5355\u4e00\u9009\u9879\u662f\u5f53\u524d\u56fa\u5b9a\u914d\u7f6e；\u6709\u591a\u4e2a\u9009\u9879\u624d\u5f62\u6210\u9009\u62e9\u5206\u652f。Option\u5185\u6298\u53e0\u65b9\u6cd5、\u6570\u636e\u5217（\u6d4b\u91cf\u7279\u5f81\u4e0e\u8bed\u4e49）、\u5b8c\u6574\u53c2\u6570、\u7ec4\u4ef6、\u6765\u6e90。\u56fe\u95f4\u7bad\u5934\u662f\u5206\u6790\u4f9d\u8d56，\u4e0d\u662f\u56e0\u679c\u5173\u7cfb。\n\n## \u5c40\u9650，\u9700\u4e0e\u79d1\u7814\u52a9\u624b\u8ba8\u8bba\n- \u8fd9\u662f2—3\u6761\u65b9\u6848\u7684\u6d41\u7a0b\u8bd5\u9519，\u4e0d\u8db3\u4ee5\u5224\u65ad\u6574\u4f53\u7a33\u5065\u6027，\u4e5f\u672a\u8bc1\u660e\u5927\u578b\u77e5\u8bc6\u5e93\u5206\u7c7b\u5df2\u7ecf\u6536\u655b\u6216\u7c92\u5ea6\u6b63\u786e。\n- \u540c\u7ec4\u82e5\u4ec5\u6539\u53d8\u63a8\u65ad\u65b9\u5f0f，\u70b9\u4f30\u8ba1\u76f8\u540c\u662f\u6b63\u5e38\u7ed3\u679c；“\u4e0d\u62a5\u544a\u533a\u95f4”\u4e0d\u7b49\u4e8e\u53d1\u73b0\u53e6\u4e00\u79cd\u4f30\u8ba1\u65b9\u6cd5，\u4e0d\u80fd\u636e\u6b64\u5938\u5927\u65b9\u6cd5\u591a\u6837\u6027。\n- \u672c\u8f6e\u5168\u90e8P\u503c\u4e3a\u7a7a（null），\u6a21\u578b\u4ec5\u89c4\u5212\u4e86\u63cf\u8ff0\u6027\u4f30\u8ba1/\u533a\u95f4，\u6ca1\u6709\u5b9e\u65bd\u6b63\u5f0f\u96f6\u5047\u8bbe\u68c0\u9a8c；\u4e0d\u80fd\u58f0\u79f0\u5df2\u7ecf\u7528P\u503c\u9a8c\u8bc1H1。\u6a21\u578b\u672a\u5b9a\u4e49“\u4e2d\u7b49\u5f3a\u5ea6”\u7684\u7edf\u4e00\u9608\u503c，\u66f2\u7ebf\u4e0d\u80fd\u81ea\u52a8\u5224\u5b9a\u8be5\u90e8\u5206H1\u6210\u7acb。\n- \u81ea\u52a8\u590d\u6838\u4ecd\u662f\u6a21\u578b\u5224\u65ad，\u7ed3\u6784\u4e0e\u4ee3\u7801\u68c0\u67e5\u4e0d\u8bc1\u660e\u7edf\u8ba1\u6709\u6548。\u6d4b\u91cf/\u63d2\u8865\u4e0d\u786e\u5b9a\u6027、\u7a7a\u95f4\u4f9d\u8d56\u4e0e\u9002\u7528\u6761\u4ef6\u5e94\u6309\u6bcf\u6761\u7ed3\u679c\u8b66\u544a\u548c\u5206\u7ec4\u9650\u5236\u89e3\u8bfb。\n- \u56fe\u89c4\u5212\u9636\u6bb5\u8bb0\u5f55\u4e2d\u7684“\u672a\u6267\u884c”\u53ea\u63cf\u8ff0\u5f53\u65f6\u9636\u6bb5；\u672c\u8f6e\u6267\u884c\u72b6\u6001\u4ee5execution_results.json\u548cverification.json\u4e3a\u51c6。\u539fH1/\u6570\u636e\u8bed\u4e49\u8bb0\u5f55\u6ca1\u6709\u8ffd\u6539。\n\nDeepSeek\u8bb0\u5f55\u7684\u6269\u5c55\u9650\u5236（\u539f\u6837）：\n{chr(10).join(('- ' + str(x) for x in patch['limitations']))}\n\n## \u72ec\u7acb\u8fd0\u884c\u548c\u7559\u5b58\n\u9879\u76ee\u6839\u76ee\u5f55\u6267\u884c `python outputs/decision_option_lab/paper_graph_trial.py --replay`：\u4e25\u683c\u79bb\u7ebf\u91cd\u653eAPI\u7f13\u5b58、\u5df2\u4fdd\u5b58\u5b9e\u9645\u7ed3\u679c\u4e0eBoba\u7f16\u8bd1\u56de\u6267，\u4e0d\u91cd\u65b0\u5206\u6790。\u53bb\u6389--replay\u4f1a\u590d\u7528\u5df2\u6709\u7f13\u5b58；`--rerun`\u660e\u786e\u91cd\u65b0\u8fd0\u884c\u5206\u6790；\u5168\u65b0API\u7b54\u6848\u4e0d\u4fdd\u8bc1\u9010\u5b57\u76f8\u540c。`--output`\u53ef\u53e6\u5b58\u7ed3\u679c，`--baseline`\u6307\u5b9a\u57fa\u7840\u4e0a\u4e0b\u6587\u76ee\u5f55。\u51bb\u7ed3\u540e\u4e0d\u5f97\u4fee\u6539\u65b9\u6848，\u53ea\u53ef\u4e3a\u9519\u8bef\u4fee\u590d\u751f\u6210\u65b0\u4ee3\u7801；\u5931\u8d25\u8bb0\u5f55\u4fdd\u7559。\n\n\u65b0API\u8c03\u7528\u7684key\u53ea\u4ece\u672c\u5730.env\u8bfb\u53d6，\u4e0d\u8fdb\u5165\u62a5\u544a、\u7f51\u9875\u6216\u4ea4\u4ed8\u5305。\u8fd0\u884c\u6a21\u578b\u751f\u6210\u4ee3\u7801\u4f7f\u7528\u9759\u6001\u68c0\u67e5、\u53d7\u9650\u5b50\u8fdb\u7a0b、\u53bb\u5bc6\u94a5\u73af\u5883\u4e0e\u5ba1\u8ba1\u94a9\u5b50；\u4e0d\u662f\u64cd\u4f5c\u7cfb\u7edf\u7ea7\u5b89\u5168\u6c99\u7bb1。\n\n\u5b8c\u6574\u6570\u636e\u7ed3\u679c：execution_results.json；\u8ba1\u5212：specification_plan.json；\u51bb\u7ed3\u6458\u8981：analysis_freeze.json；\u5b98\u65b9Boba\u6a21\u677f：boba_template.py；\u53ef\u5bfc\u51fa\u66f2\u7ebf：specification_curve.png/svg。\u672c\u8f6e\u672a\u4e0a\u4f20Gitee。\n'
    (out / 'README.md').write_text(text, encoding='utf-8')
    (out / 'run.ps1').write_text("param([switch]$Rerun)\n$entry=Join-Path $PSScriptRoot '../decision_option_lab/paper_graph_trial.py'\nif($Rerun){python $entry --output $PSScriptRoot --rerun}else{python $entry --output $PSScriptRoot --replay}\n", encoding='utf-8')
if __name__ == '__main__':
    build(p.DEFAULT)
