# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Render recorded method-core transfer decisions without modifying scientific results."""
import copy
import re
from pathlib import Path
import priority_trial as p
import task_graph_view as old
ROOT = Path(__file__).resolve().parent

def payload(out):
    graph = p.read(out / 'inputs/knowledge_graph.json')
    index = p.read(out / 'semantic_index.json')
    classification = graph['classification']
    d = {name: p.read(out / (name + '.json')) for name in ['research_context', 'column_ranking', 'reuse_audit', 'previous_candidates', 'plan_lock', 'implementation_review', 'verification']}
    d['task_understanding'] = p.read(out / 'priority_task.json')
    d['boba_blueprint'] = p.read(out / 'locked_blueprint.json')
    d['target_graph'] = copy.deepcopy(p.read(out / 'frozen_plan.json'))
    for st in d['target_graph']['steps']:
        for o in st['options']:
            o['source_option_refs'] = sorted({ref.split('/')[0] for ref in o['method']['component_refs']})
            o['source_evidence'] = []
            o['proposal_reason'] = o['priority_reason']
    nodes = [{'id': f['id'], 'kind': 'family', 'label': f['id'] + ' ' + f['name']} for f in classification['families']]
    nodes += [{'id': m['id'], 'kind': 'method', 'label': m['id'] + ' ' + m['name']} for m in classification['methods']]
    nodes += [{'id': ref, 'kind': 'option', 'label': ref + ' ' + o['option']['label']} for ref, o in graph['original_options'].items()]
    edges = [{'from': m['family_id'], 'to': m['id']} for m in classification['methods']]
    seen = set()
    for row in classification['rows']:
        for c in row['components']:
            key = (c['method_id'], row['source_ref'])
            if key not in seen:
                edges.append({'from': key[0], 'to': key[1]})
                seen.add(key)
    d['graph'] = {'nodes': nodes, 'edges': edges}
    d['methods'] = index['methods']
    dataset = next((x for x in p.read(out / 'data_features.json')['datasets'] if x['dataset_id'] == d['research_context']['dataset_choice']['dataset_id']))
    d['column_features'] = {c['column_id']: c for c in dataset['columns']}
    d['boba_template'] = (out / 'boba_template.py').read_text('utf-8')
    d['baseline'] = {'old_candidate_method_ids': d['previous_candidates']['method_ids']}
    d['verification']['screened_candidates'] = d['verification']['audited_candidates']
    d['graph_review'] = {'overall': '\u51bb\u7ed3\u8ba1\u5212\u5230\u4ee3\u7801\u7684\u9010\u9879\u590d\u6838', 'issues': []}
    retrieval = []
    for op in d['task_understanding']['operations']:
        cs = []
        for r in d['reuse_audit']['candidates']:
            for a in r['operation_assessments']:
                if a['operation_id'] == op['id']:
                    cs.append({'method_id': r['method_id'], 'applicability': a['mode'] + ' / ' + a['status'], 'reason': a['reason'], 'data_semantic_fit': a['capability'], 'task_fit': r['method_core']['definition'], 'conditions': a['unresolved'], 'component_refs': r['component_refs']})
        checks = next((c for c in d['reuse_audit']['operation_checks'] if c['operation_id'] == op['id']))
        retrieval.append({'operation_id': op['id'], 'candidates': cs, 'unmatched_need': '；'.join((g['reason'] for g in checks['gaps']))})
    d['column_task_retrieval'] = {'operations': retrieval}
    d['operation_retrieval'] = {'operations': [{'operation_id': o['id'], 'candidates': []} for o in d['task_understanding']['operations']]}
    return (d, index)

def build(out):
    d, index = payload(out)
    text = (ROOT / 'task_graph_fragment.html').read_text('utf-8')
    text = text.replace('\u7814\u7a76\u4efb\u52a1 → \u68c0\u7d22\u5ba1\u6838 → Decision–Option', '\u65b9\u6cd5\u6838\u5fc3：\u590d\u7528 → \u9002\u914d → \u6269\u5c55')
    text = text.replace('① \u4efb\u52a1\u7406\u89e3', '① H1＋\u4ee3\u7801＋\u6570\u636e').replace('④ \u5168\u90e8\u5019\u9009\u5ba1\u6838', '④ \u65b9\u6cd5\u6838\u5fc3\u4e0e\u4f18\u5148\u7ea7')
    text = text.replace('\u672c\u64cd\u4f5c\u4e24\u8f6e\u547d\u4e2d', '\u672c\u64cd\u4f5c\u6838\u5fc3\u5ba1\u6838\u5019\u9009').replace('\u4e24\u8f6e\u5171\u547d\u4e2d', '\u6838\u5fc3\u5ba1\u6838\u5019\u9009')
    text = text.replace("['column_task_retrieval','operation_retrieval'].map((r,i)", "['column_task_retrieval'].map((r,i)")
    text = text.replace('\u7b2c\u4e00\u8f6e：\u5217\u8bed\u4e49 + \u64cd\u4f5c + \u9002\u7528\u6761\u4ef6', '\u6309H1\u64cd\u4f5c、\u8bed\u4e49\u4e0e\u53ef\u590d\u7528\u6838\u5fc3\u8054\u5408\u68c0\u7d22')
    text = text.replace('<th>\u5bf9\u5e94\u64cd\u4f5c</th><th>\u7b5b\u9009\u7ed3\u8bba</th><th>\u7edf\u4e00\u516d\u9879\u4f9d\u636e</th>', '<th>\u5bf9\u5e94\u64cd\u4f5c / \u91c7\u7528\u65b9\u5f0f</th><th>\u5224\u65ad\u7406\u7531</th><th>\u6838\u5fc3 / \u4e0a\u4e0b\u6587 / \u53d8\u5316</th>')
    start = text.index('function ledger(){')
    end = text.index('function drawTarget(){', start)
    text = text[:start] + (ROOT / 'priority_ledger.js').read_text('utf-8') + '\n' + text[end:]
    a = text.index('<div class="viz-row to-legend">')
    b = text.index('</div>', a) + 6
    legend = '<div class="viz-row to-legend"><span><i class="to-dot to-existing-origin"></i>reused \u76f4\u63a5\u91c7\u7528Method</span><span><i class="to-dot to-reported-origin"></i>adapted \u4fdd\u7559\u6838\u5fc3\u91cd\u65b0\u914d\u7f6e</span><span><i class="to-dot to-proposed-origin"></i>proposed \u65b0\u589e\u65b9\u6cd5／\u6280\u672f\u914d\u7f6e</span></div>'
    text = text[:a] + legend + text[b:]
    text = text.replace('\u6765\u6e90\u6807\u7b7e\u5c5e\u4e8e\u6574\u4e2aOption，\u5185\u90e8Method\u7684\u6765\u6e90\u53e6\u5217；\u6240\u6709\u8fde\u63a5\u90fd\u662f\u672c\u8f6e\u5efa\u8bae\u7684\u5206\u6790\u4f9d\u8d56。', '\u8282\u70b9\u989c\u8272\u8868\u793a\u65b9\u6cd5\u91c7\u7528\u65b9\u5f0f；Option\u914d\u7f6e\u6765\u6e90\u53e6\u5217，adapted\u4e0d\u8981\u6c42\u65e7Option\u53ef\u76f4\u63a5\u8fd0\u884c。')
    text = text.replace('\u521d\u7a3f\u95ee\u9898\u8bb0\u5f55', '\u65b9\u6cd5\u6838\u5fc3\u4e0e\u771f\u5b9e\u4ee3\u7801').replace('\u81ea\u52a8\u590d\u6838\u53d1\u73b0\u4e86\u4ec0\u4e48', '\u51bb\u7ed3\u65b9\u6cd5\u5230\u4ee3\u7801\u7684\u81ea\u52a8\u590d\u6838')
    text = text.replace("proposed:'proposed · DeepSeek\u589e\u8865'", "proposed:'Option\u914d\u7f6e proposed · \u4e3a\u65b0\u6570\u636e\u751f\u6210'")
    text = text.replace('sub:origin[o.origin],className:o.origin', "sub:o.reuse_mode+' · '+((o.reuse_mode==='proposed'&&['data_preparation','result_output'].includes(st.operation_kind))?'\u6280\u672f\u914d\u7f6e':o.method.id),className:o.reuse_mode")
    text = text.replace('activeOp=opmap[saved.operation]?saved.operation:ops[0].id', "activeOp=opmap[saved.operation]?saved.operation:(DATA.target_graph.steps.find(s=>s.operation_kind==='statistical_method'&&s.options.some(o=>o.reuse_mode==='reused'||o.reuse_mode==='adapted'))?.operation_id||ops[0].id)")
    text = text.replace('\u5df2\u6709Option ', '\u65b9\u6cd5\u539f\u5b9e\u4f8b ')
    text = text.replace('<div id="to-feature-detail"></div>', '<div id="to-feature-detail"></div><div id="to-core-detail"></div>')
    css = '#task-option-lab .to-diagram rect.reused{fill:color-mix(in srgb,var(--viz-series-1) 13%,var(--background))}#task-option-lab .to-diagram rect.adapted{fill:color-mix(in srgb,var(--viz-series-2) 16%,var(--background))}'
    text = text.replace('</style>', css + '\n</style>')
    text = text.replace('\nranking();ledger();drawKB();drawTarget();inspectOption();', '\n' + (ROOT / 'priority_extension.js').read_text('utf-8') + '\nranking();ledger();drawKB();drawTarget();inspectOption();')
    text = text.replace('task-option-lab', 'priority-reuse-lab').replace('to-', 'pr-')
    fragment = text.replace('__DATA__', old.encode(d))
    if len(fragment.encode('utf-8')) >= 1000000:
        raise ValueError('Inline view exceeds 1MB')
    (out / 'reuse-adapt.html').write_text(fragment, encoding='utf-8')
    shell = (ROOT / 'semantic_stitch_shell.html').read_text('utf-8').replace('\u6570\u636e\u5217\u6392\u5e8f、\u73b0\u6709\u56fe\u68c0\u7d22\u4e0e\u6d41\u7a0b\u62fc\u63a5', '\u65b9\u6cd5\u6838\u5fc3\u590d\u7528\u4e0e\u9002\u914d\u4f18\u5148\u8bd5\u9519').replace('semantic-stitch-lab', 'priority-reuse-lab')
    (out / 'index.html').write_text(shell.replace('__COMPONENTS__', old.encode(index['components'])).replace('__FRAGMENT__', fragment), encoding='utf-8')
    p.save(out / '\u5c55\u793a\u6570\u636e.json', d)
    readme(out, d)
    print('Reuse/adaptation view built', flush=True)

def readme(out, d):
    v = d['verification']
    plan = p.read(out / 'frozen_plan.json')
    bp = d['boba_blueprint']
    modes = v['template_method_modes']
    stat = v['template_statistical_method_modes']
    stat_text = f'\u76f4\u63a5\u91c7\u7528{stat['reused']}、\u4fdd\u7559\u6838\u5fc3\u9002\u914d{stat['adapted']}、\u65b0\u589e\u7edf\u8ba1\u65b9\u6cd5{stat['proposed']}'
    text = f'# \u590d\u7528 → \u9002\u914d → \u6269\u5c55：\u672c\u8f6e\u7b80\u62a5\n\n\u672c\u8f6e\u6ca1\u6709\u4fee\u6539\u539f\u4e8c\u5341\u7bc7Decision–Option、\u5206\u7c7b\u6216DAG，\u4e5f\u6ca1\u6709\u5efa\u7acb\u901a\u7528\u53ef\u6267\u884c\u7ec4\u4ef6\u5e93。\u65e7\u7248\u7559\u5b58，\u65b0\u7248\u53e6\u5b58。\n\n## \u505a\u4e86\u4ec0\u4e48\n\nDeepSeek\u7ed3\u5408\u539fH1、\u8bba\u6587\u6b63\u6587/\u4ee3\u7801\u4e0e\u771f\u5b9e\u6570\u636e\u7279\u5f81，\u5148\u7406\u89e3\u9700\u8981\u7684\u64cd\u4f5c，\u518d\u68c0\u7d22\u65e2\u6709Method。\u5bf9\u65b9\u6cd5\u533a\u5206“\u5fc5\u987b\u4fdd\u7559\u7684\u6838\u5fc3”\u548c“\u539f\u8bba\u6587\u7684\u7279\u5b9a\u4e0a\u4e0b\u6587”，\u6309\u7167reused→adapted→proposed\u4f5c\u5224\u65ad；\u4e0d\u80fd\u56e0\u65e7Option\u65e0\u6cd5\u76f4\u63a5\u8fd0\u884c\u6216\u65b0\u5217/\u53c2\u6570\u4e0d\u540c\u5c31\u5224\u6210\u65b0\u65b9\u6cd5。\u968f\u540e\u51bb\u7ed3\u65b9\u6cd5\u9009\u7528\u6e05\u5355，\u4ee3\u7801\u53ea\u80fd\u5f15\u7528\u6e05\u5355\u4e2d\u7684\u65b9\u6cd5，\u53e6\u4e00\u6b21DeepSeek\u8c03\u7528\u7528\u5b9e\u9645\u4ee3\u7801\u7247\u6bb5\u590d\u6838\u6838\u5fc3\u662f\u5426\u4fdd\u7559。\n\n## \u7ed3\u679c\n\n- {v['operations']}\u4e2a\u64cd\u4f5c；\u539f{v['prior_candidates_preserved']}\u4e2a\u5019\u9009\u5168\u90e8\u4fdd\u7559，\u672c\u8f6e\u5ba1\u6838{v['audited_candidates']}\u4e2a。\n- \u56fe{v['steps']}\u6b65、{v['decisions']}\u4e2aDecision、{v['options']}\u4e2aOption。\n- \u6a21\u677f\u4e2d\u7684\u91c7\u7528\u65b9\u5f0f：\u76f4\u63a5\u91c7\u7528{modes['reused']}、\u4fdd\u7559\u6838\u5fc3\u9002\u914d{modes['adapted']}、\u65b0\u589e\u6280\u672f\u914d\u7f6e/\u65b9\u6cd5{modes['proposed']}。\u7edf\u8ba1\u65b9\u6cd5\u90e8\u5206\u5355\u5217：{stat_text}，\u907f\u514d\u628a\u6570\u636e\u51c6\u5907\u7b97\u6210\u79d1\u7814\u65b9\u6cd5\u590d\u7528\u7387。\n- \u8fdb\u5165\u6a21\u677f\u7684\u65e2\u6709M：{'、'.join(v['template_existing_method_ids']) or '\u65e0'}；{v['specifications']}\u5957\u6761\u4ef6\u6027\u8349\u6848。\u51bb\u7ed3\u6838\u5fc3\u5230\u4ee3\u7801\u7684\u81ea\u52a8\u590d\u6838：{('\u901a\u8fc7（\u4ecd\u6709\u6761\u4ef6）' if v['implementation_review_passed'] else '\u672a\u901a\u8fc7，\u9700\u68c0\u67e5\u963b\u65ad')}。\n- \u672a\u8fd0\u884c\u7edf\u8ba1，\u6ca1\u6709\u4f30\u8ba1\u503c、P\u503c\u6216\u66f2\u7ebf。\u9002\u914d\u6b63\u786e\u6027\u4ecd\u662f\u6a21\u578b\u5224\u65ad，\u4e0d\u80fd\u628a\u6765\u6e90\u7559\u75d5\u5f53\u6210\u6570\u5b66\u8bc1\u660e\u6216\u7edf\u8ba1\u6709\u6548\u8bc1\u660e。\n- \u5f53\u524d\u6ca1\u6709\u5f62\u6210\u975e\u5197\u4f59Decision\u66ff\u4ee3，\u4e5f\u672a\u89c4\u5212\u5b8c\u6574\u6b63\u5f0f\u63a8\u65ad；\u672c\u8f6e\u4ec5\u9a8c\u8bc1\u77e5\u8bc6\u5e93\u6838\u5fc3\u80fd\u8fdb\u5165\u6a21\u677f，\u4e0d\u80fd\u58f0\u79f0\u5b8c\u6210\u7a33\u5065\u6027\u5206\u6790。\n\n## \u9875\u9762\u600e\u6837\u68c0\u67e5\n\n\u6253\u5f00[index.html](index.html)。\u91cd\u70b9\u770b④\u7684\u539f\u65b9\u6cd5\u6838\u5fc3/\u4e0a\u4e0b\u6587/\u53d8\u5316\u9879，⑤Option\u7684reused/adapted/proposed\u989c\u8272\u4e0e\u6807\u7b7e，⑥\u5b9e\u9645\u4ee3\u7801\u548c\u53c2\u6570。\u6bcf\u4e2a\u65b0\u589eMethod\u5fc5\u987b\u6709\u76f4\u63a5\u590d\u7528、\u4fdd\u6301\u6838\u5fc3\u9002\u914d\u5747\u4e0d\u53ef\u884c\u7684\u7f3a\u53e3\u8bf4\u660e。\n\n\u6ce8\u610f\u4e24\u4e2a\u6807\u7b7e：**\u65b9\u6cd5\u91c7\u7528\u65b9\u5f0f**\u662freused/adapted/proposed；**Option\u914d\u7f6e\u6765\u6e90**\u4e3aproposed\u8868\u793a\u8fd9\u5957\u65b0\u6570\u636e\u65b9\u6848\u7531\u6a21\u578b\u914d\u7f6e，\u4e0d\u80fd\u8bef\u8bfb\u4e3a\u5176\u4e2d\u7684\u65b9\u6cd5\u5168\u662f\u65b0\u589e，\u4e5f\u4e0d\u80fd\u5192\u5145\u539f\u6587\u65b9\u6848。\n\n## \u4ecd\u9700\u8ba8\u8bba\u7684\u6761\u4ef6\n\n{chr(10).join(('- ' + str(x) for x in plan['limitations']))}\n\n## \u72ec\u7acb\u8fd0\u884c\n\n\u9879\u76ee\u6839\u76ee\u5f55\u6267\u884c `python outputs/decision_option_lab/priority_trial.py --replay`。\u4e25\u683c\u79bb\u7ebf\u7f13\u5b58\u91cd\u653e；\u65b0\u8c03\u7528\u53bb\u6389--replay，\u6700\u65b0key\u53ea\u4ece\u672c\u5730.env\u8bfb\u53d6。\u66f4\u6362\u57fa\u7840\u6570\u636e\u7528--baseline，\u65b0\u7ed3\u679c\u7528--output，\u51bb\u7ed3\u8ba1\u5212\u6539\u53d8\u987b\u53e6\u5b58。\u5168\u65b0\u8c03\u7528\u4e0d\u4fdd\u8bc1\u76f8\u540c\u7b54\u6848，\u7f13\u5b58\u7559\u5b58\u4fdd\u8bc1\u672c\u7248\u53ef\u590d\u73b0。\n\n\u65b0\u589e\u72ec\u7acbpriority_trial.py、priority_view.py、\u6807\u51c6/\u6307\u4ee4/\u5951\u7ea6；\u65e7\u4e8c\u5341\u7bc7\u4ee3\u7801\u4e0e\u79d1\u7814\u7ed3\u679c\u672a\u4fee\u6539。\u672c\u8f6e\u672a\u4e0a\u4f20Gitee。\n'
    (out / 'README.md').write_text(text, encoding='utf-8')
if __name__ == '__main__':
    build(p.DEFAULT)
