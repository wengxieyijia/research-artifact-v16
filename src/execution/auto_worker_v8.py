"""Inference-contract validation around the unchanged v7 isolated scientific worker."""
import json,math
from pathlib import Path
from blind_five_worker_base_v7 import run_one as run_base

def run_one(folder,spec_id,execution_round=0):
    record=run_base(folder,spec_id,execution_round)
    if record['status']!='success':return record
    runtime=Path(folder);spec=next(s for s in json.loads((runtime/'specifications.json').read_text(encoding='utf-8'))['specifications'] if s['spec_id']==spec_id)
    expected=dict(spec.get('output_contract',{}).get('inference',{}))
    for option in spec.get('selected_options',{}).values():
        p=option.get('parameters',{})
        if p.get('inference_policy') in ['formal_test','conditional_formal_test','not_identifiable']:
            expected['policy']=p['inference_policy']
            for k in ['test_name','alternative','alpha','null_hypothesis','assumptions']:
                if k in p:expected[k]=p[k]
    value=record['result'];inf=value.get('inference',{});p=value['p_value'];errors=[]
    if not isinstance(inf,dict) or not inf.get('status'):errors.append('Returned inference metadata missing')
    elif p is None:
        if inf['status'] not in ['not_identifiable','unavailable','not_applicable']:errors.append('Missing P must have explicit unavailability status')
        if not inf.get('reason'):errors.append('Missing P requires a specific reason, never NS')
    else:
        if expected.get('policy') not in ['formal_test','conditional_formal_test']:errors.append('P supplied for a path without a frozen formal-test policy')
        if inf.get('status')!=expected.get('policy'):errors.append('Returned inference status differs from frozen policy')
        if inf.get('alternative')!=expected.get('alternative'):errors.append('Alternative differs from frozen test')
        if inf.get('alpha')!=expected.get('alpha'):errors.append('Alpha differs from frozen test')
        if inf.get('null_value')!=spec['comparison_definition']['evaluation']['null_value']:errors.append('Null differs from frozen effect null')
        if not inf.get('test_name'):errors.append('P has no declared test name')
    record['inference_contract_checked']=True
    if errors:record.update(status='failed',error_type='InferenceContractError',error='; '.join(errors),inference_contract_errors=errors)
    (runtime/f'execution_round_{execution_round}'/'results'/(spec_id+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return record
