import numpy as np
import pandas as pd
from scipy import stats
import math

def _opt(spec, key):
    if 'choices' in spec and key in spec['choices']:
        v = spec['choices'][key]
        if isinstance(v, dict):
            return str(v.get('id'))
        return str(v)
    if 'selected_options' in spec and key in spec['selected_options']:
        v = spec['selected_options'][key]
        if isinstance(v, dict):
            return str(v.get('id'))
        return str(v)
    raise ValueError('Missing option for ' + key)

def _py(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, dict):
        return {str(k): _py(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_py(x) for x in v]
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    return v

def _pearson(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x = x[m]
    y = y[m]
    n = x.size
    if n < 2:
        raise ValueError('Pearson correlation needs at least 2 complete observations')
    if np.var(x, ddof=0) <= 0 or np.var(y, ddof=0) <= 0:
        raise ValueError('Pearson correlation undefined because exposure or outcome has zero variance')
    r = float(np.corrcoef(x, y)[0, 1])
    if not np.isfinite(r):
        raise ValueError('Pearson correlation is not finite')
    return r, n

def _cr1_zero_slope(x, y, clusters):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    c = np.asarray(clusters, dtype=object)
    m = np.isfinite(x) & np.isfinite(y) & pd.notna(c)
    x = x[m]
    y = y[m]
    c = c[m]
    n = int(x.size)
    out = {'n': n}
    if n < 4:
        out['reason'] = 'n < 4'
        return None, None, out
    if np.var(x, ddof=0) <= 0:
        out['reason'] = 'zero variance in exposure'
        return None, None, out
    X = np.column_stack([np.ones(n), x])
    XtX = X.T @ X
    try:
        inv = np.linalg.inv(XtX)
    except np.linalg.LinAlgError:
        out['reason'] = 'singular design matrix'
        return None, None, out
    beta = inv @ (X.T @ y)
    resid = y - X @ beta
    tmp = pd.DataFrame({'cluster': c, 's0': resid, 's1': x * resid})
    sums = tmp.groupby('cluster', sort=False)[['s0', 's1']].sum().to_numpy()
    G = int(sums.shape[0])
    out['G'] = G
    if G <= 1:
        out['reason'] = 'G <= 1'
        return beta, None, out
    K = 2
    if n <= K:
        out['reason'] = 'n <= K'
        return beta, None, out
    meat = sums.T @ sums
    corr = (G / (G - 1.0)) * ((n - 1.0) / (n - K))
    V = corr * inv @ meat @ inv
    vb = V[1, 1]
    out['beta_dep'] = float(beta[1])
    out['beta_intercept'] = float(beta[0])
    out['finite_sample_correction'] = float(corr)
    out['var_beta_dep'] = float(vb)
    if not np.isfinite(vb) or vb <= 0:
        out['reason'] = 'nonpositive cluster-robust variance'
        return beta, None, out
    se = math.sqrt(vb)
    tstat = beta[1] / se
    df = G - 1
    p = float(2.0 * stats.t.sf(abs(tstat), df))
    out['se'] = float(se)
    out['t'] = float(tstat)
    out['df'] = int(df)
    return beta, p, out

def _subject_level(df, dep_var, dedup, group_id):
    missing_cols = [c for c in ['SubjectTag', dep_var, 'DELIN_AVERAGE'] if c not in df.columns]
    if missing_cols:
        raise ValueError('Missing required column(s): ' + ', '.join(missing_cols))
    if dedup:
        given = ['SubjectTag', 'R', 'RelationshipPath', 'MINORITY', 'SEX', 'CESD20_1992', 'DELIN_AVERAGE', 'CESD7_1994', 'CESD7_1992', 'AGE_1979', 'ExtendedID']
        subset = [c for c in given if c in df.columns]
        before = len(df)
        df = df.drop_duplicates(subset=subset, keep='first').copy()
        dedup_removed = int(before - len(df))
    else:
        dedup_removed = 0
    families = df[['SubjectTag', 'ExtendedID']].dropna(subset=['ExtendedID']).drop_duplicates()
    fam_counts = families.groupby('SubjectTag', sort=False)['ExtendedID'].nunique()
    first_fam = families.groupby('SubjectTag', sort=False)['ExtendedID'].first()
    agg = {}
    for c in ['CESD20_1992', 'CESD7_1992', 'CESD7_1994']:
        if c in df.columns:
            agg[c] = 'mean'
    agg[dep_var] = 'mean'
    agg['DELIN_AVERAGE'] = 'mean'
    for c in ['SEX', 'MINORITY', 'AGE_1979']:
        if c in df.columns:
            agg[c] = 'first'
    sub = df.groupby('SubjectTag', sort=False, dropna=False).agg(agg).reset_index()
    sub['ExtendedID'] = sub['SubjectTag'].map(first_fam)
    sub['n_distinct_ExtendedID'] = sub['SubjectTag'].map(fam_counts).fillna(0).astype(int)
    sub['multi_family'] = sub['n_distinct_ExtendedID'] > 1
    sub['ambiguous_family'] = sub['n_distinct_ExtendedID'] != 1
    multi_count = int(sub['multi_family'].sum())
    amb_count = int(sub['ambiguous_family'].sum())
    if group_id == 'F_TOTAL':
        sid = sub['SubjectTag'].astype(str)
        fid = sub['ExtendedID'].astype(str)
        sub['cluster'] = np.where(sub['ambiguous_family'], 'S' + sid, 'F' + fid)
    else:
        sub = sub[~sub['ambiguous_family']].copy()
        sub['cluster'] = 'F' + sub['ExtendedID'].astype(str)
    return sub, dedup_removed, multi_count, amb_count

def _winsorize(df, cols, lo=0.01, hi=0.99):
    bounds = {}
    for c in cols:
        if c not in df.columns:
            continue
        s = df[c]
        valid = s.dropna()
        if len(valid) == 0:
            continue
        qlo = float(valid.quantile(lo))
        qhi = float(valid.quantile(hi))
        df[c] = df[c].clip(lower=qlo, upper=qhi)
        bounds[c] = [qlo, qhi]
    return df, bounds

def analyze(data, spec):
    if not isinstance(data, pd.DataFrame):
        raise TypeError('data must be a pandas DataFrame')
    if not isinstance(spec, dict):
        raise TypeError('spec must be a dict')
    group_id = spec.get('group_id')
    if group_id not in ('F_TOTAL', 'F_WITHIN', 'F_BETWEEN'):
        raise ValueError('Unsupported group_id: ' + str(group_id))
    choice_unit = _opt(spec, 'D_UNIT')
    choice_dep = _opt(spec, 'D_DEPRESSION')
    choice_out = _opt(spec, 'D_OUTLIER')
    choice_mis = _opt(spec, 'D_MISSING')
    if choice_mis not in ('O1',):
        if choice_mis == 'O2':
            raise ValueError('D_MISSING O2 (MICE 2l.pmm) is not implemented because the frozen plan does not define the predictive mean matching donor count k; implementing it would require an unfrozen scientific parameter.')
        raise ValueError('Unsupported D_MISSING option: ' + choice_mis)
    if choice_unit not in ('O1', 'O3'):
        raise ValueError('Unsupported D_UNIT option: ' + choice_unit)
    if choice_out not in ('O1', 'O2'):
        raise ValueError('Unsupported D_OUTLIER option: ' + choice_out)
    dep_map = {'O1': 'CESD20_1992', 'O2': 'CESD7_1992', 'O3': 'CESD7_1994',
               'CESD20_1992': 'CESD20_1992', 'CESD7_1992': 'CESD7_1992', 'CESD7_1994': 'CESD7_1994'}
    if choice_dep not in dep_map:
        raise ValueError('Unsupported D_DEPRESSION option: ' + choice_dep)
    dep_var = dep_map[choice_dep]
    if dep_var not in data.columns:
        raise ValueError('Missing selected depression column: ' + dep_var)
    df = data.copy()
    for c in ['SubjectTag', 'ExtendedID', 'CESD20_1992', 'CESD7_1992', 'CESD7_1994', 'DELIN_AVERAGE', 'AGE_1979', 'SEX']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    sub, dedup_removed, multi_count, amb_count = _subject_level(df, dep_var, choice_unit == 'O3', group_id)
    n_subject = int(len(sub))
    winsor_bounds = {}
    if choice_out == 'O2':
        sub, winsor_bounds = _winsorize(sub, [dep_var, 'DELIN_AVERAGE'])
    n_before_missing = int(len(sub))
    sub = sub.dropna(subset=[dep_var, 'DELIN_AVERAGE']).copy()
    missing_removed = int(n_before_missing - len(sub))
    if len(sub) == 0:
        raise ValueError('No complete analysis units remain after subject aggregation, outlier handling, and missing-data rule')
    diagnostics = {
        'point_estimate_computed': True,
        'frozen_test_implemented': True,
        'p_estimable': None,
        'group_id': group_id,
        'choices': {'D_UNIT': choice_unit, 'D_DEPRESSION': choice_dep, 'D_OUTLIER': choice_out, 'D_MISSING': choice_mis},
        'selected_depression_variable': dep_var,
        'delinquency_variable': 'DELIN_AVERAGE',
        'deduplication_removed_rows': int(dedup_removed),
        'n_subject_level_rows_before_missing': int(n_subject),
        'n_rows_before_missing_after_outlier': int(n_before_missing),
        'missing_rows_removed_complete_case': int(missing_removed),
        'multi_family_subject_count': int(multi_count),
        'ambiguous_family_subject_count': int(amb_count),
        'winsorization_bounds': winsor_bounds,
        'n_analysis_units': int(len(sub))
    }
    if group_id == 'F_TOTAL':
        x = sub[dep_var].to_numpy(dtype=float)
        y = sub['DELIN_AVERAGE'].to_numpy(dtype=float)
        r, n_used = _pearson(x, y)
        beta, p, cr1 = _cr1_zero_slope(x, y, sub['cluster'].to_numpy(dtype=object))
        diagnostics.update({'cluster_count_G': cr1.get('G'), 'cr1_details': cr1, 'p_estimable': p is not None})
        reason = cr1.get('reason', 'cluster-robust test not estimable') if p is None else None
        n_out = int(n_used)
    elif group_id == 'F_WITHIN':
        counts = sub.groupby('ExtendedID', sort=False).size()
        keep = set(counts[counts >= 2].index)
        sub = sub[sub['ExtendedID'].isin(keep)].copy()
        if len(sub) == 0:
            raise ValueError('No ExtendedID family has at least two complete analysis units for within-family correlation')
        sub['dep_within'] = sub[dep_var] - sub.groupby('ExtendedID', sort=False)[dep_var].transform('mean')
        sub['del_within'] = sub['DELIN_AVERAGE'] - sub.groupby('ExtendedID', sort=False)['DELIN_AVERAGE'].transform('mean')
        x = sub['dep_within'].to_numpy(dtype=float)
        y = sub['del_within'].to_numpy(dtype=float)
        r, n_used = _pearson(x, y)
        beta, p, cr1 = _cr1_zero_slope(x, y, sub['cluster'].to_numpy(dtype=object))
        diagnostics.update({'n_families_with_at_least_two_units': int(sub['ExtendedID'].nunique()), 'cluster_count_G': cr1.get('G'), 'cr1_details': cr1, 'p_estimable': p is not None})
        reason = cr1.get('reason', 'cluster-robust test not estimable') if p is None else None
        n_out = int(n_used)
    else:
        fam = sub.groupby('ExtendedID', sort=False).agg({dep_var: 'mean', 'DELIN_AVERAGE': 'mean'}).reset_index()
        if len(fam) == 0:
            raise ValueError('No ExtendedID family means available for between-family correlation')
        x = fam[dep_var].to_numpy(dtype=float)
        y = fam['DELIN_AVERAGE'].to_numpy(dtype=float)
        r, n_used = _pearson(x, y)
        K = int(len(fam))
        p = None
        reason = None
        if K <= 2:
            reason = 'K <= 2 for Pearson correlation t test'
        elif np.var(x, ddof=0) <= 0 or np.var(y, ddof=0) <= 0:
            reason = 'zero variance in family means'
        else:
            if abs(r) >= 1.0 - 1e-12:
                p = 0.0
            else:
                tstat = r * math.sqrt((K - 2.0) / (1.0 - r * r))
                p = float(2.0 * stats.t.sf(abs(tstat), K - 2))
        diagnostics.update({'n_family_means_K': K, 'p_estimable': p is not None})
        n_out = int(n_used)
    cd = spec.get('comparison_definition', {})
    effect_scale = cd.get('effect_scale')
    estimand = cd.get('estimand')
    if not isinstance(effect_scale, str) or not isinstance(estimand, str):
        raise ValueError('comparison_definition.effect_scale and estimand must be present strings')
    ic = spec.get('output_contract', {}).get('inference', {})
    policy = ic.get('policy', 'conditional_formal_test' if group_id != 'F_BETWEEN' else 'formal_test')
    alt = ic.get('alternative', 'two_sided')
    alpha = ic.get('alpha', 0.05)
    null_value = cd.get('null_value', 0)
    test_name = ic.get('test_name')
    if p is not None and np.isfinite(p):
        status = str(policy)
        reason_out = None
    else:
        status = 'unavailable'
        reason_out = reason if reason is not None else 'P not estimable under frozen test'
    inference = {
        'status': status,
        'policy': str(policy),
        'test_name': test_name,
        'null_hypothesis': ic.get('null_hypothesis'),
        'alternative': str(alt),
        'alpha': float(alpha),
        'null_value': float(null_value) if null_value is not None else None,
        'reason': reason_out,
        'ci_policy': 'null: no pre-specified confidence interval beyond the formal test; not replaced by bootstrap interval.'
    }
    return {
        'effect_size': float(r),
        'p_value': None if p is None else float(p),
        'ci_lower': None,
        'ci_upper': None,
        'n': int(n_out),
        'effect_scale': effect_scale,
        'estimand': estimand,
        'diagnostics': _py(diagnostics),
        'inference': _py(inference)
    }
