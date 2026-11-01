import numpy as np
import pandas as pd
from scipy import stats

def _require(cond,msg):
    if not cond:
        raise ValueError(msg)

def _selected_option(spec,dim):
    so=spec.get('selected_options',{})
    if isinstance(so,dict) and dim in so and isinstance(so[dim],dict):
        return so[dim]
    for st in spec.get('steps',[]) or []:
        if isinstance(st,dict) and st.get('dimension')==dim:
            return st
    raise ValueError('missing frozen selected option for dimension '+str(dim))

def _choice_id(spec,dim,opt):
    choices=spec.get('choices',{})
    if isinstance(choices,dict) and dim in choices:
        return str(choices[dim])
    return str(opt.get('id'))

def _params(opt):
    p=opt.get('parameters',{})
    return p if isinstance(p,dict) else {}

def _qtype7(x,p):
    a=np.sort(np.asarray(x,dtype=float))
    n=a.size
    if n==0:
        raise ValueError('cannot compute quantile of empty array')
    h=(n-1)*float(p)
    lo=int(np.floor(h))
    hi=int(np.ceil(h))
    if lo==hi:
        return float(a[lo])
    return float(a[lo]+(h-lo)*(a[hi]-a[lo]))

def analyze(data,spec):
    _require(isinstance(data,pd.DataFrame),'data must be a pandas DataFrame')
    _require(isinstance(spec,dict),'spec must be a dict for one expanded specification')
    comp=spec.get('comparison_definition',{})
    _require(isinstance(comp,dict),'comparison_definition missing')
    effect_scale=comp.get('effect_scale')
    estimand=comp.get('estimand')
    null_value=comp.get('null_value')
    _require(effect_scale is not None,'comparison_definition.effect_scale missing')
    _require(estimand is not None,'comparison_definition.estimand missing')
    _require(null_value is not None,'comparison_definition.null_value missing')
    out_contract=spec.get('output_contract',{})
    inf_contract=out_contract.get('inference',{}) if isinstance(out_contract,dict) else {}
    sample_opt=_selected_option(spec,'D_SAMPLE')
    weight_opt=_selected_option(spec,'D_WEIGHT')
    adjust_opt=_selected_option(spec,'D_ADJUST')
    inf_opt=_selected_option(spec,'D_INFERENCE')
    sample_id=_choice_id(spec,'D_SAMPLE',sample_opt)
    weight_id=_choice_id(spec,'D_WEIGHT',weight_opt)
    adjust_id=_choice_id(spec,'D_ADJUST',adjust_opt)
    inf_id=_choice_id(spec,'D_INFERENCE',inf_opt)
    sp=_params(sample_opt)
    wp=_params(weight_opt)
    ap=_params(adjust_opt)
    ip=_params(inf_opt)
    age_min=sp.get('age_min')
    age_max=sp.get('age_max')
    _require(age_min is not None and age_max is not None,'D_SAMPLE age_min/age_max missing')
    age_min=float(age_min)
    age_max=float(age_max)
    covariates=ap.get('covariates',[])
    if covariates is None:
        covariates=[]
    _require(isinstance(covariates,list),'D_ADJUST parameters.covariates must be a list')
    covariates=[str(c) for c in covariates]
    weight_col=wp.get('weight','none')
    if weight_col is None:
        weight_col='none'
    weight_col=str(weight_col)
    winsor_text=str(wp.get('winsorization','none')).lower()
    winsorize=('winsor' in winsor_text) or ('99' in winsor_text) or (weight_id.upper()=='WINSOR99')
    alternative=inf_contract.get('alternative',ip.get('alternative'))
    alpha=inf_contract.get('alpha',ip.get('alpha'))
    _require(alternative is not None,'inference alternative not specified')
    _require(alpha is not None,'inference alpha not specified')
    alternative=str(alternative)
    alpha=float(alpha)
    _require(alternative=='two_sided','this frozen implementation supports the frozen two_sided alternative only')
    required=['nearc4','ed76','age76']+covariates
    weighted=(weight_col not in ('','none','None','NONE'))
    if weighted:
        required.append(weight_col)
    missing_cols=[c for c in required if c not in data.columns]
    _require(len(missing_cols)==0,'required columns missing: '+','.join(missing_cols))
    req_cols=list(dict.fromkeys(required))
    df=data.loc[:,req_cols].copy()
    total_rows=int(len(df))
    base_mask=df['nearc4'].notna() & df['ed76'].notna()
    base_n=int(base_mask.sum())
    dfb=df.loc[base_mask].copy()
    age_num=pd.to_numeric(dfb['age76'],errors='coerce')
    age_mask=(age_num>=age_min) & (age_num<=age_max)
    dfa=dfb.loc[age_mask].copy()
    n=int(len(dfa))
    _require(n>0,'analysis sample is empty after frozen sample restriction')
    missing_cov=[c for c in covariates if dfa[c].isna().any()]
    _require(len(missing_cov)==0,'frozen covariates have missing values in analysis sample; no missing-data rule frozen: '+','.join(missing_cov))
    if weighted:
        _require(dfa[weight_col].notna().all(),'frozen weight has missing values in analysis sample; no missing-data rule frozen')
    y=pd.to_numeric(dfa['ed76'],errors='coerce').to_numpy(dtype=float)
    near=pd.to_numeric(dfa['nearc4'],errors='coerce').to_numpy(dtype=float)
    _require(np.isfinite(y).all(),'ed76 contains non-finite values after sample restriction')
    _require(np.isfinite(near).all(),'nearc4 contains non-finite values after sample restriction')
    uniq=np.unique(near)
    _require(set([float(v) for v in uniq]).issubset(set([0.0,1.0])),'nearc4 must be coded 0/1 under frozen exposure definition')
    _require(len(uniq)==2,'nearc4 has only one observed level; contrast is not estimable')
    if weighted:
        w_orig=pd.to_numeric(dfa[weight_col],errors='coerce').to_numpy(dtype=float)
        _require(np.isfinite(w_orig).all(),'weight contains non-finite values')
        _require(np.all(w_orig>0),'weight must be positive for weighted WLS')
        if winsorize:
            q99=_qtype7(w_orig,0.99)
            w=np.minimum(w_orig,q99)
        else:
            q99=None
            w=w_orig.copy()
    else:
        w_orig=np.ones(n,dtype=float)
        w=np.ones(n,dtype=float)
        q99=None
    cov_cols=[]
    for c in covariates:
        v=pd.to_numeric(dfa[c],errors='coerce').to_numpy(dtype=float)
        _require(np.isfinite(v).all(),'covariate '+c+' contains non-finite values')
        cov_cols.append(v)
    X_cols=[np.ones(n,dtype=float),near]+cov_cols
    X=np.column_stack(X_cols)
    _require(np.isfinite(X).all(),'design matrix contains non-finite values')
    k=int(X.shape[1])
    _require(n>k,'residual degrees of freedom must be positive')
    rank=int(np.linalg.matrix_rank(X))
    if rank<k:
        raise ValueError('design matrix is rank deficient: rank '+str(rank)+' < '+str(k)+'; the frozen nearc4 coefficient is not identified')
    XtWX=X.T @ (w[:,None]*X)
    XtWy=X.T @ (w*y)
    try:
        XtWX_inv=np.linalg.inv(XtWX)
    except np.linalg.LinAlgError:
        raise ValueError('weighted cross-product matrix is singular; the frozen nearc4 coefficient is not identified')
    beta=XtWX_inv @ XtWy
    resid=y-X @ beta
    idx=1
    effect=float(beta[idx])
    _require(np.isfinite(effect),'nearc4 point estimate is not finite')
    dfree=int(n-k)
    if inf_id=='HC1':
        meat=X.T @ ((w*w*resid*resid)[:,None]*X)
        V=XtWX_inv @ meat @ XtWX_inv
        V=V*(float(n)/float(n-k))
    elif inf_id=='CLASSICAL':
        s2=float(np.sum(w*resid*resid)/float(n-k))
        V=s2*XtWX_inv
    else:
        raise ValueError('unsupported frozen D_INFERENCE option: '+str(inf_id))
    se=float(np.sqrt(V[idx,idx]))
    _require(np.isfinite(se) and se>0,'standard error for nearc4 is not positive/finite; frozen t-test not available')
    tstat=float(effect/se)
    tcrit=float(stats.t.ppf(1.0-alpha/2.0,dfree))
    p_value=float(2.0*stats.t.sf(abs(tstat),dfree))
    ci_lower=float(effect-tcrit*se)
    ci_upper=float(effect+tcrit*se)
    _require(np.isfinite(p_value),'p value is not finite')
    mean1=float(np.mean(y[near==1.0]))
    mean0=float(np.mean(y[near==0.0]))
    raw_diff=float(mean1-mean0)
    cond_num=float(np.linalg.cond(X))
    w_desc={'weight_id':weight_id,'weighted':bool(weighted),'weight_variable':None if not weighted else weight_col,'winsorize_99':bool(winsorize),'winsor_threshold_type7_q99':q99,'weight_min':float(np.min(w)),'weight_max':float(np.max(w))}
    missing_diag={'total_rows':total_rows,'nearc4_missing_total':int(df['nearc4'].isna().sum()),'ed76_missing_total':int(df['ed76'].isna().sum()),'base_complete_on_nearc4_ed76':base_n,'age_excluded_from_base':int((~age_mask).sum()),'analysis_n':n,'covariate_missing_after_sample':missing_cov,'weight_missing_after_sample':False if not weighted else bool(dfa[weight_col].isna().any())}
    diagnostics={'group_id':spec.get('group_id'),'spec_id':spec.get('spec_id'),'estimator':'WLS' if weighted else 'OLS','point_estimate_computed':True,'frozen_test_implemented':True,'linear_system_solved':True,'rank_full':True,'design_matrix_rank':rank,'n_coefficients':k,'residual_df':dfree,'analysis_n':n,'base_sample_n':base_n,'sample_restriction':{'D_SAMPLE':sample_id,'age_min':age_min,'age_max':age_max,'age76_missing_in_base':int(age_num.isna().sum())},'exposure_contrast':{'variable':'nearc4','nearc4_1_n':int(np.sum(near==1.0)),'nearc4_0_n':int(np.sum(near==0.0)),'mean_ed76_nearc4_1':mean1,'mean_ed76_nearc4_0':mean0,'unadjusted_raw_mean_difference':raw_diff},'adjustment':{'D_ADJUST':adjust_id,'covariates':covariates},'inference_setting':{'D_INFERENCE':inf_id,'standard_error':inf_id,'alternative':alternative,'alpha':alpha,'ci_level':1.0-alpha,'reference_distribution':'Student t','df':dfree},'weighting':w_desc,'missingness':missing_diag,'singularity_condition_number_X':cond_num,'notes':['closed-form OLS/WLS solved directly; no iterative convergence required','no multiple imputation or complex survey clustering/stratification was applied because none was frozen','p value corresponds to the single nearc4 coefficient contrast, not an omnibus test']}
    policy=str(inf_contract.get('policy','formal_test'))
    inference={'status':policy,'policy':policy,'execution_status':'ok','test_name':inf_contract.get('test_name'),'null_hypothesis':inf_contract.get('null_hypothesis'),'alternative':alternative,'alpha':alpha,'null_value':null_value,'p_value_available':True,'ci_level':1.0-alpha,'reference_distribution':'Student t','degrees_of_freedom':dfree,'standard_error':se,'statistic':tstat,'reason':None,'missing_p_reason':None}
    return {'effect_size':effect,'p_value':p_value,'ci_lower':ci_lower,'ci_upper':ci_upper,'n':int(n),'effect_scale':effect_scale,'estimand':estimand,'diagnostics':diagnostics,'inference':inference}
