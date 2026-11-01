# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""A compact output adapter; existing scientific records are never regenerated here."""
import copy
import auto_trial_v8 as base
from auto_trial_v8 import legacy, read

def merge_delta(before, delta):
    plan = copy.deepcopy(before)
    families = {f['id']: f for f in plan['families']}
    for entry in delta.get('additional_options', []):
        family = families[entry['family_id']]
        dimension = next((d for d in family['dimensions'] if d['key'] == entry['decision_key']))
        if any((o['id'] == entry['option']['id'] for o in dimension['options'])):
            raise ValueError('An added Option ID already exists')
        dimension['options'].append(copy.deepcopy(entry['option']))
    for entry in delta.get('additional_constraints', []):
        family = families[entry['family_id']]
        if any((c['id'] == entry['constraint']['id'] for c in family.get('constraints', []))):
            raise ValueError('An added constraint ID already exists')
        family.setdefault('constraints', []).append(copy.deepcopy(entry['constraint']))
    return {'expanded_plan': plan, 'expansion_review': delta['expansion_review']}

def expand_with_delta(runner, before, contract):
    option = {'id': 'new unique Option ID', 'label': 'English label', 'description': 'complete operation', 'parameters': {}, 'data_binding': {'columns': []}, 'source_refs': [], 'origin': 'reused/adapted/proposed', 'method_origin': 'reused/adapted/proposed', 'method_refs': [], 'source_contribution': 'actual retained/adapted/new parts'}
    delta_contract = {'additional_options': [{'family_id': 'F1', 'decision_key': 'existing key', 'option': option}], 'additional_constraints': [{'family_id': 'F1', 'constraint': {'id': 'new constraint ID', 'forbid_when': {'actual key': ['actual Option ID']}, 'reason': 'specific incompatibility'}}], 'expansion_review': contract['expansion_review']}
    instruction = base.PLAN_PROMPT + '\n\u672c\u9636\u6bb5\u4ec5\u68c0\u67e5\u73b0\u6709Decision\u662f\u5426\u9057\u6f0f\u6709\u4f9d\u636e\u7684Option，\u8f93\u51fa\u5c0f\u578b\u589e\u91cfJSON。\u4e0d\u8981\u91cd\u65b0\u8f93\u51fa/\u6539\u5199expanded_plan、\u539fDecision/Option、H1、\u53e3\u5f84\u6216\u539f\u53c2\u6570，\u4e5f\u4e0d\u8981\u56de\u663esource_material。\u5df2\u6709\u65b9\u6848\u7531\u7a0b\u5e8f\u6309\u5b57\u8282\u4fdd\u7559；\u53ea\u8ffd\u52a0\u4f60\u5728additional_options\u4e2d\u5b8c\u6574\u5b9a\u4e49\u7684\u65b0Option\u53ca\u5fc5\u8981additional_constraints。\u4e0d\u65b0\u589eDecision，\u771f\u6b63\u7684\u5b9a\u4e49\u7f3a\u53e3\u4ea4\u4e4b\u540e\u72ec\u7acb\u9884\u5ba1\u5904\u7406。\u82e5\u65e0\u5b89\u5168\u65b0\u589e，\u4e24\u4e2a\u6570\u7ec4\u53ef\u7a7a\u5e76\u586b\u5199\u5177\u4f53no_safe_expansion_reason。\n\u6bcf\u4e2a\u65b0\u589eOption\u5fc5\u987b\u5728expansion_review.change_ledger\u4e2d\u6709\u4e14\u4ec5\u6709\u4e00\u6761kind=new_option/status=accepted\u7684\u5bf9\u5e94\u8bb0\u5f55。\u4e5f\u4fdd\u7559\u88ab\u4f60\u8003\u8651\u4f46\u62d2\u7edd\u7684\u5019\u9009\u53ca\u7406\u7531。basis\u53ea\u80fdhistorical/adapted/general_methodological，source_refs\u7cbe\u786e\u6765\u81ea\u5f53\u524dcatalog；\u5386\u53f2\u914d\u7f6e\u4e0eMethod\u6838\u5fc3\u6765\u6e90\u5206\u5f00。\u6bcf\u6761accepted\u8bb0\u5f55\u5199\u6e05distinctness、parameter_domain、data_equivalence=not_equivalent/unknown、equivalence_reason、changes_point_estimate\u548cinference_only。\n\u5148\u4f9d\u636e\u5b9e\u9645Data、\u5386\u53f2\u6765\u6e90\u548c\u65b9\u6cd5\u5b66\u7406\u7531\u8003\u8651\u5408\u7406\u53c2\u6570/\u6837\u672c/\u6d4b\u91cf/\u4f30\u8ba1\u9009\u62e9，\u4e0d\u6309\u6570\u5b57\u76ee\u6807\u51d1\u70b9。\u5df2\u77e5\u5f53\u524d\u6570\u636e\u7b49\u4ef7\u7684\u9608\u503c、\u91cd\u590d\u6570\u5b66\u7b97\u6cd5、\u968f\u673a\u79cd\u5b50、\u8f93\u51fa\u6837\u5f0f\u7b49\u5fc5\u987b\u62d2\u7edd。\u4e0d\u80fd\u89c2\u6d4b\u4efb\u4f55\u8def\u5f84\u6548\u5e94/P\u6216\u4f5c\u8005\u53c2\u7167\u540e\u6269\u91cf。\u4fdd\u6301\u540c\u4e00\u7814\u7a76\u95ee\u9898\u7684\u5408\u7406\u9009\u9879\u5728\u5bbd\u66f2\u7ebf\u5185，\u4e0d\u80fd\u6df7\u5165\u4e0d\u517c\u5bb9\u6548\u5e94。\u5168\u90e8\u79d1\u5b66\u53c2\u6570\u548c\u63a8\u65ad/\u91cd\u91c7\u6837\u7ec6\u8282\u5b8c\u6574\u5b9a\u4e49，\u65b0\u589eOption\u8bf7\u7528\u82f1\u6587\u77ed\u6807\u7b7e。\n\u6309\u539f\u6709\u7ec4\u5408\u6570\u91cf\u4e58\u79ef\u8ba1\u7b97\u52a0\u5165\u540e\u7684\u603b\u539f\u59cb\u7ec4\u5408，\u4e0d\u5f97\u8d85\u8fc7evaluation_policy.max_specifications，\u4e0d\u9759\u9ed8\u622a\u65ad。\u65b0\u589e\u7ea6\u675f\u4f7f\u7528forbid_when\u5b57\u5178，\u591a\u4e2a\u952e\u8868\u793aAND。\u8f93\u51fa\u4e25\u683c\u4e14\u53ea\u6709additional_options、additional_constraints、expansion_review\u4e09\u4e2a\u6839\u5b57\u6bb5。\n'

    def valid(delta):
        if set(delta) != {'additional_options', 'additional_constraints', 'expansion_review'}:
            return ['Return exactly the three compact delta root fields; never echo the full source or plan']
        if not isinstance(delta['additional_options'], list) or not isinstance(delta['additional_constraints'], list):
            return ['Delta additions must be lists']
        try:
            expanded = merge_delta(before, delta)
        except (ValueError, KeyError, TypeError, StopIteration) as exc:
            return ['Invalid delta target/ID/schema: ' + str(exc)]
        return runner.validate_expansion(expanded, before)
    delta = runner.call('independent_option_coverage_delta', instruction, delta_contract, legacy.packet({'current_candidate_plan': before, 'evaluation_policy': runner.policy(), 'measured_data_conditions': runner.data_conditions()}), valid)
    return merge_delta(before, delta)
