"""Trusted Boba worker: scientific module has data arguments, no author files or credentials."""
import ast,hashlib,importlib.util,json,math,os,sys,time,traceback
from pathlib import Path
import numpy as np
import pandas as pd

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def plain(x):
    if isinstance(x,np.generic):return x.item()
    if isinstance(x,np.ndarray):return [plain(v) for v in x.tolist()]
    if isinstance(x,dict):return {str(k):plain(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [plain(v) for v in x]
    return x

def install_guard(runtime,denied,execution_round):
    read_roots=[runtime.resolve(),Path(sys.prefix).resolve(),Path(sys.base_prefix).resolve()]
    write_roots=[(runtime/f'execution_round_{execution_round}/results').resolve(),(runtime/'temp').resolve()]
    def audit(event,args):
        if event in {'socket.connect','socket.bind','subprocess.Popen','os.system'}:
            denied.append({'event':event});raise PermissionError('Analysis network/process access denied')
        if event=='open' and args and isinstance(args[0],(str,bytes,os.PathLike)):
            path=Path(os.fsdecode(args[0])).resolve();mode=args[1] if len(args)>1 else 'r';flags=args[2] if len(args)>2 else 0
            write=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC)))
            allowed=write_roots if write else read_roots
            if not any(path.is_relative_to(root) for root in allowed):
                denied.append({'event':'open','path':str(path),'write':write});raise PermissionError('Analysis file access outside isolated data/runtime libraries denied')
    sys.addaudithook(audit)

def run_one(folder,spec_id,execution_round=0):
    runtime=Path(folder).resolve();dest=runtime/f'execution_round_{execution_round}/results';dest.mkdir(exist_ok=True,parents=True)
    record={'spec_id':spec_id,'round':execution_round};started=time.monotonic();denied=[]
    try:
        lock=json.loads((runtime/'specification_lock.json').read_text(encoding='utf-8'))
        for name,key in [('data.csv','data_sha256'),('specifications.json','specifications_sha256'),('specification_plan.json','plan_sha256')]:assert digest(runtime/name)==lock[key],name
        specs=json.loads((runtime/'specifications.json').read_text(encoding='utf-8'))['specifications'];spec=next(s for s in specs if s['spec_id']==spec_id)
        record.update(group_id=spec['group_id'],choices=spec['choices'],comparison_definition=spec['comparison_definition'])
        source=(runtime/'analysis_round_0.py').read_text(encoding='utf-8');ast.parse(source)
        frame=pd.read_csv(runtime/'data.csv')
        install_guard(runtime,denied,execution_round)
        loader=importlib.util.spec_from_file_location('blind_scientific_module',runtime/'analysis_round_0.py');module=importlib.util.module_from_spec(loader);loader.loader.exec_module(module)
        outcome=plain(module.analyze(frame.copy(),spec))
        for key in ['effect_size','p_value','ci_lower','ci_upper','n','effect_scale','estimand','diagnostics']:
            if key not in outcome:raise ValueError('Result missing '+key)
        if not isinstance(outcome['effect_size'],(float,int)) or not math.isfinite(outcome['effect_size']):raise ValueError('Effect is not finite')
        # A multiyear result can report counts separately by period, rather than one scalar n.
        def counts(value):
            if isinstance(value,dict):
                out=[]
                for k,v in value.items():
                    if k in {'czone_count','n','n_obs','count'} and isinstance(v,(float,int)):out.append(v)
                    elif k in {'czone_count_by_year','n_by_year'} and isinstance(v,dict):out.extend(v.values())
                    elif isinstance(v,(dict,list)):out.extend(counts(v))
                return out
            if isinstance(value,list):return [item for v in value for item in counts(v)]
            return [value] if isinstance(value,(float,int)) else []
        sample_counts=counts(outcome['n'])
        if not sample_counts or any(not isinstance(n,(float,int)) or not math.isfinite(n) or n<=0 for n in sample_counts):raise ValueError('Invalid scalar or per-period sample counts')
        for key in ['p_value','ci_lower','ci_upper']:
            if outcome[key] is not None and (not isinstance(outcome[key],(float,int)) or not math.isfinite(outcome[key])):raise ValueError('Invalid '+key)
        if outcome['p_value'] is not None and not 0<=outcome['p_value']<=1:raise ValueError('P outside 0..1')
        if outcome['ci_lower'] is not None and outcome['ci_upper'] is not None and outcome['ci_lower']>outcome['ci_upper']:raise ValueError('Reversed interval')
        if outcome['effect_scale']!=spec['comparison_definition']['effect_scale'] or outcome['estimand']!=spec['comparison_definition']['estimand']:raise ValueError('Frozen scale/estimand changed')
        record.update(status='success',result=outcome,input_rows=len(frame),code_sha256=hashlib.sha256(source.encode()).hexdigest())
    except Exception as exc:record.update(status='failed',error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc())
    record.update(seconds=round(time.monotonic()-started,3),denied_access_attempts=denied)
    (dest/(spec_id+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');print(spec_id+' '+record['status'],flush=True)
    return record
