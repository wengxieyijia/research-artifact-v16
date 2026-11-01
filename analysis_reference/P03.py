import math
import numpy as np
import pandas as pd
from scipy import stats

ALPHA = 0.05
MICE_SEED = 20261029
MICE_M = 20
MICE_MAXIT = 10
PMM_K = 5


def _choice(spec, dim):
    c = spec.get('choices', {})
    if dim in c:
        v = c[dim]
        return str(v.get('id')) if isinstance(v, dict) else str(v)
    s = spec.get('selected_options', {})
    if dim in s:
        v = s[dim]
        return str(v.get('id')) if isinstance(v, dict) else str(v)
    for st in spec.get('steps', []):
        if st.get('dimension') == dim:
            return str(st.get('id'))
    raise ValueError('Missing choice ' + dim)


def _finite(x):
    try:
        x = float(x)
    except Exception:
        return None
    if np.isfinite(x):
        return x
    return None


def _result(effect, p, lo, hi, n, scale, estimand, diag, status, test, reason, assumptions):
    return {
        'effect_size': _finite(effect),
        'p_value': _finite(p),
        'ci_lower': _finite(lo),
        'ci_upper': _finite(hi),
        'n': int(n),
        'effect_scale': scale,
        'estimand': estimand,
        'diagnostics': diag,
        'inference': {
            'status': status,
            'test_name': test,
            'alternative': 'two_sided',
            'alpha': ALPHA,
            'null_value': 0,
            'assumptions': assumptions,
            'reason': reason
        }
    }


def _ni(tau, reason, n, test, design):
    return {
        'status': 'not_identifiable',
        'tau': tau,
        'p': None,
        'ci_lower': None,
        'ci_upper': None,
        'var': None,
        'n': int(n),
        'df': None,
        'test_name': test,
        'reason': reason,
        'design': design if design is not None else []
    }


def _prep(data, outcols):
    base = ['SHEET', 'CHAIN', 'STATE', 'CO_OWNED']
    req = base + list(outcols)
    for c in req:
        if c not in data.columns:
            raise ValueError('Required column missing from data: ' + c)
    d0 = data.copy()
    for c in req + ['OPEN', 'HRSOPEN']:
        if c in d0.columns:
            d0[c] = pd.to_numeric(d0[c], errors='coerce')
    v = d0.dropna(subset=base).copy()
    v = v[v['STATE'].isin([0, 1])].copy()
    dup = d0['SHEET'].notna() & d0['SHEET'].duplicated(keep=False)
    dup_sheets = set(d0.loc[dup, 'SHEET'].unique())
    d = v[~v['SHEET'].isin(dup_sheets)].copy()
    diag = {
        'input_rows': int(len(data)),
        'valid0_rows_before_duplicate_exclusion': int(len(v)),
        'duplicate_sheet_count': int(d0.loc[dup, 'SHEET'].nunique()),
        'duplicate_full_rows': int(dup.sum()),
        'duplicate_sheet_excluded_rows': int(len(v) - len(d)),
        'valid_rows_after_duplicate_exclusion': int(len(d)),
        'alpha': ALPHA,
        'alternative': 'two_sided',
        'null_value': 0
    }
    return d, diag


def _sample(d, opt):
    note = None
    if opt == 'CHAIN_OVERLAP':
        allc = list(d['CHAIN'].dropna().unique())
        chains = []
        for c in allc:
            sub = d[d['CHAIN'] == c]
            if (sub['STATE'] == 1).any() and (sub['STATE'] == 0).any():
                chains.append(c)
        if len(chains) == len(allc) and len(allc) > 0:
            note = 'All observed CHAIN have both NJ and PA stores; CHAIN_OVERLAP equals ALL_VALID on this data.'
        d = d[d['CHAIN'].isin(chains)].copy()
    elif opt == 'FRANCHISE_ONLY':
        d = d[d['CO_OWNED'] == 0].copy()
    return d, note


def _design(df, target, outcols):
    cols = [np.ones(len(df))]
    names = ['intercept']
    for c in outcols:
        if c == target:
            continue
        cols.append(pd.to_numeric(df[c], errors='coerce').values.astype(float))
        names.append(c)
    cols.append(pd.to_numeric(df['STATE'], errors='coerce').values.astype(float))
    names.append('STATE')
    dum = pd.get_dummies(pd.to_numeric(df['CHAIN'], errors='coerce'), prefix='CHAIN', drop_first=True, dtype=float)
    for c in dum.columns:
        cols.append(dum[c].values.astype(float))
        names.append(str(c))
    for c in ['CO_OWNED', 'OPEN', 'HRSOPEN']:
        cols.append(pd.to_numeric(df[c], errors='coerce').values.astype(float))
        names.append(c)
    return np.column_stack(cols), names


def _mice(df, outcols):
    df = df.reset_index(drop=True).copy()
    for c in outcols:
        if df[c].notna().sum() == 0:
            return None, 'No observed values for ' + c + '; PMM not defined.'
    rng = np.random.default_rng(MICE_SEED)
    base = df.copy()
    init = df.copy()
    for c in outcols:
        obs_c = init[c].notna()
        overall_med = float(init.loc[obs_c, c].median()) if obs_c.any() else None
        for st in [0, 1]:
            vals = init.loc[(init['STATE'] == st) & init[c].notna(), c]
            med = float(vals.median()) if len(vals) > 0 else overall_med
            if med is not None:
                mask = (init['STATE'] == st) & init[c].isna()
                init.loc[mask, c] = med
    if init[outcols].isna().any().any():
        return None, 'Initialization left missing employment component values.'
    datasets = []
    for mi in range(MICE_M):
        cur = init.copy()
        for it in range(MICE_MAXIT):
            for target in outcols:
                obs = base[target].notna().values
                miss = ~obs
                if not miss.any():
                    continue
                Xall, names = _design(cur, target, outcols)
                Xobs = Xall[obs]
                y = cur.loc[obs, target].values.astype(float)
                if len(y) == 0:
                    return None, 'No observed rows for PMM regression for ' + target
                beta = np.linalg.lstsq(Xobs, y, rcond=None)[0]
                eta = Xall @ beta
                for idx in np.where(miss)[0]:
                    st = cur.loc[idx, 'STATE']
                    cand = np.where(obs & (cur['STATE'].values == st))[0]
                    if len(cand) == 0:
                        cand = np.where(obs)[0]
                    if len(cand) == 0:
                        return None, 'No donor for ' + target
                    dist = np.abs(eta[cand] - eta[idx])
                    order = np.argsort(dist)
                    kth = dist[order[min(PMM_K - 1, len(order) - 1)]]
                    take = cand[dist <= kth]
                    chosen = int(rng.choice(take))
                    cur.loc[idx, target] = float(cur.loc[chosen, target])
        datasets.append(cur.copy())
    return datasets, None


def _winsor(df, cols):
    d = df.copy()
    thr = {}
    for c in cols:
        s = pd.to_numeric(d[c], errors='coerce')
        vals = s.dropna().values.astype(float)
        if len(vals) >= 2:
            lo, hi = np.percentile(vals, [1, 99])
            d[c] = s.clip(lower=lo, upper=hi)
            thr[c] = (float(lo), float(hi))
        else:
            thr[c] = (None, None)
    return d, thr


def _derive(df, pre, post):
    d = df.copy()
    for c in pre + post:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d['pre_employment'] = d[pre].sum(axis=1, min_count=len(pre))
    d['post_employment'] = d[post].sum(axis=1, min_count=len(post))
    d['delta'] = d['post_employment'] - d['pre_employment']
    d['T'] = (d['STATE'] == 1).astype(int)
    return d


def _chain_both(d):
    for c in d['CHAIN'].dropna().unique():
        sub = d[d['CHAIN'] == c]
        if (sub['T'] == 1).any() and (sub['T'] == 0).any():
            return True
    return False


def _stratum_both(d):
    d = d.copy()
    d['stratum'] = d['CHAIN'].astype(str) + '_' + d['CO_OWNED'].astype(str)
    for s in d['stratum'].unique():
        sub = d[d['stratum'] == s]
        if (sub['T'] == 1).any() and (sub['T'] == 0).any():
            return True
    return False


def _select_basis(X):
    n, p = X.shape
    idx = []
    for j in range(p):
        col = X[:, j]
        if len(idx) == 0:
            if np.linalg.norm(col) > 1e-12:
                idx.append(j)
        else:
            A = X[:, idx + [j]]
            if np.linalg.matrix_rank(A) > len(idx):
                idx.append(j)
    return idx


def _fit_hc2_with_treatment(Z, T, y):
    Z = np.asarray(Z, dtype=float)
    T = np.asarray(T, dtype=float).reshape(-1)
    y = np.asarray(y, dtype=float).reshape(-1)
    n0 = len(y)
    keep = np.ones(n0, dtype=bool)
    for _ in range(4):
        Zr = Z[keep]
        Tr = T[keep]
        yr = y[keep]
        n = len(yr)
        if n == 0:
            raise ValueError('No observations remain for HC2 model.')
        idxZ = _select_basis(Zr)
        if len(idxZ) > 0:
            Zb = Zr[:, idxZ]
            coefT = np.linalg.lstsq(Zb, Tr, rcond=None)[0]
            rT = Tr - Zb @ coefT
        else:
            Zb = np.empty((n, 0))
            rT = Tr.copy()
        scaleT = float(np.dot(Tr, Tr))
        if scaleT <= 0:
            raise ValueError('Treatment contrast is not identified: treatment has no variation.')
        if float(np.dot(rT, rT)) <= 1e-10 * max(1.0, scaleT):
            raise ValueError('Treatment contrast is not identified: treatment lies in the nuisance column span.')
        tol_r = 1e-9 * max(1.0, float(np.max(np.abs(Tr))))
        remove = np.abs(rT) <= tol_r
        if not np.any(remove):
            break
        orig = np.where(keep)[0]
        keep[orig[remove]] = False
        if not np.any(keep):
            raise ValueError('All observations have zero treatment residual; treatment is not identified.')
    Zr = Z[keep]
    Tr = T[keep]
    yr = y[keep]
    n = len(yr)
    idxZ = _select_basis(Zr)
    if len(idxZ) > 0:
        Zb = Zr[:, idxZ]
        coefT = np.linalg.lstsq(Zb, Tr, rcond=None)[0]
        rT = Tr - Zb @ coefT
    else:
        Zb = np.empty((n, 0))
        rT = Tr.copy()
    if float(np.dot(rT, rT)) <= 1e-10 * max(1.0, float(np.dot(Tr, Tr))):
        raise ValueError('Treatment contrast is not identified after removing zero-information rows.')
    X = np.column_stack([Zb, Tr])
    pmod = X.shape[1]
    if n <= pmod:
        raise ValueError('Too few observations relative to model rank for HC2 inference.')
    inv = np.linalg.pinv(X.T @ X)
    beta = inv @ (X.T @ yr)
    tau = float(beta[-1])
    if not np.isfinite(tau):
        raise ValueError('HC2 treatment coefficient is not finite.')
    resid = yr - X @ beta
    h = np.einsum('ij,jk,ik->i', X, inv, X)
    df = int(n - pmod)
    if df <= 0:
        raise ValueError('Nonpositive residual degrees of freedom for HC2.')
    if np.any(1.0 - h <= 1e-12):
        return {'status': 'not_identifiable', 'tau': tau, 'var': None, 'df': float(df),
                'n': int(n), 'reason': 'HC2 variance undefined because at least one leverage equals 1.',
                'dropped_zero_info': int(n0 - n)}
    adj = (resid ** 2) / (1.0 - h)
    meat = X.T @ (adj[:, None] * X)
    cov = inv @ meat @ inv
    var = float(cov[-1, -1])
    if not np.isfinite(var) or var <= 0:
        return {'status': 'not_identifiable', 'tau': tau, 'var': None, 'df': float(df),
                'n': int(n), 'reason': 'HC2 variance is zero or nonfinite.',
                'dropped_zero_info': int(n0 - n)}
    return {'status': 'conditional_formal_test', 'tau': tau, 'var': var, 'df': float(df),
            'n': int(n), 'reason': 'Computed HC2 variance using a full-rank basis representation.',
            'dropped_zero_info': int(n0 - n)}


def _estimate(d, adjust, inference):
    d = d.copy()
    d = d.dropna(subset=['delta', 'T', 'STATE'])
    d = d[d['T'].isin([0, 1])].copy()
    if d['T'].nunique() < 2:
        raise ValueError('No NJ-PA contrast available after processing.')
    if adjust == 'COVARIATE_DID':
        d = d.dropna(subset=['CHAIN', 'CO_OWNED', 'OPEN', 'HRSOPEN']).copy()
    elif adjust == 'STRATIFIED_DID':
        d = d.dropna(subset=['CHAIN', 'CO_OWNED']).copy()
    elif adjust == 'BASELINE_EMP_DID':
        d = d.dropna(subset=['CHAIN', 'CO_OWNED', 'OPEN', 'HRSOPEN', 'pre_employment']).copy()
    if len(d) == 0:
        raise ValueError('No observations remain after adjustment variable handling.')
    if d['T'].nunique() < 2:
        raise ValueError('No NJ-PA contrast available after adjustment variable handling.')
    if adjust in ('COVARIATE_DID', 'BASELINE_EMP_DID') and not _chain_both(d):
        raise ValueError('No CHAIN has both NJ and PA stores; STATE coefficient not identified.')
    if adjust == 'STRATIFIED_DID' and not _stratum_both(d):
        raise ValueError('No stratum has both NJ and PA stores; tau not identified.')
    n = len(d)
    y = d['delta'].values.astype(float)
    T = d['T'].values.astype(float)
    if inference == 'WELCH_T':
        if adjust != 'UNADJUSTED_DID':
            raise ValueError('WELCH_T is only compatible with UNADJUSTED_DID.')
        d0 = d[d['T'] == 0]['delta'].values.astype(float)
        d1 = d[d['T'] == 1]['delta'].values.astype(float)
        n0 = len(d0)
        n1 = len(d1)
        if n0 == 0 or n1 == 0:
            raise ValueError('No NJ-PA contrast for Welch test.')
        tau = float(np.mean(d1) - np.mean(d0))
        if n0 < 2 or n1 < 2:
            return _ni(tau, 'Too few observations in one state for Welch variance.', n, 'Welch two-sample t-test', [])
        v0 = float(np.var(d0, ddof=1) / n0)
        v1 = float(np.var(d1, ddof=1) / n1)
        U = v0 + v1
        if not np.isfinite(U) or U <= 0:
            return _ni(tau, 'Welch variance is zero or nonfinite.', n, 'Welch two-sample t-test', [])
        df = (U ** 2) / ((v1 ** 2 / (n1 - 1)) + (v0 ** 2 / (n0 - 1)))
        if not np.isfinite(df) or df <= 0:
            return _ni(tau, 'Welch degrees of freedom nonpositive or nonfinite.', n, 'Welch two-sample t-test', [])
        t = tau / math.sqrt(U)
        p = float(2 * stats.t.sf(abs(t), df))
        crit = float(stats.t.ppf(1 - ALPHA / 2, df))
        return {'status': 'conditional_formal_test', 'tau': tau, 'p': p,
                'ci_lower': float(tau - crit * math.sqrt(U)),
                'ci_upper': float(tau + crit * math.sqrt(U)),
                'var': float(U), 'n': n, 'df': float(df),
                'test_name': 'Welch two-sample t-test',
                'reason': 'Computed two-sided Welch test.', 'design': []}
    cols = [np.ones(n, dtype=float)]
    names = ['intercept']
    if adjust == 'COVARIATE_DID':
        dum = pd.get_dummies(d['CHAIN'].astype(int), prefix='CHAIN', drop_first=True, dtype=float)
        for c in dum.columns:
            cols.append(dum[c].values.astype(float))
            names.append(str(c))
        for c in ['CO_OWNED', 'OPEN', 'HRSOPEN']:
            cols.append(d[c].values.astype(float))
            names.append(c)
    elif adjust == 'STRATIFIED_DID':
        d['stratum'] = d['CHAIN'].astype(str) + '_' + d['CO_OWNED'].astype(str)
        dum = pd.get_dummies(d['stratum'], prefix='STRATUM', drop_first=True, dtype=float)
        for c in dum.columns:
            cols.append(dum[c].values.astype(float))
            names.append(str(c))
    elif adjust == 'BASELINE_EMP_DID':
        cols.append(d['pre_employment'].values.astype(float))
        names.append('pre_employment')
        dum = pd.get_dummies(d['CHAIN'].astype(int), prefix='CHAIN', drop_first=True, dtype=float)
        for c in dum.columns:
            cols.append(dum[c].values.astype(float))
            names.append(str(c))
        for c in ['CO_OWNED', 'OPEN', 'HRSOPEN']:
            cols.append(d[c].values.astype(float))
            names.append(c)
    Z = np.column_stack(cols)
    res = _fit_hc2_with_treatment(Z, T, y)
    res['test_name'] = 'HC2 robust OLS t-test'
    res['design'] = names
    if res.get('status') == 'conditional_formal_test':
        tau = float(res['tau'])
        var = float(res['var'])
        df = float(res['df'])
        t = tau / math.sqrt(var)
        p = float(2 * stats.t.sf(abs(t), df))
        crit = float(stats.t.ppf(1 - ALPHA / 2, df))
        res.update({'p': p, 'ci_lower': float(tau - crit * math.sqrt(var)),
                    'ci_upper': float(tau + crit * math.sqrt(var))})
    else:
        res.update({'p': None, 'ci_lower': None, 'ci_upper': None})
    return res


def analyze(data, spec):
    if not isinstance(data, pd.DataFrame):
        raise TypeError('data must be a pandas DataFrame')
    if not isinstance(spec, dict):
        raise TypeError('spec must be a dict')
    comp = spec.get('comparison_definition')
    if not isinstance(comp, dict):
        raise ValueError('spec.comparison_definition is required')
    scale = comp.get('effect_scale')
    estimand = comp.get('estimand')
    if scale is None or estimand is None:
        raise ValueError('comparison_definition must contain effect_scale and estimand')
    gid = spec.get('group_id')
    if gid == 'F1_TOTAL_EMPLOYMENT_DID':
        pre = ['EMPFT', 'EMPPT', 'NMGRS']
        post = ['EMPFT2', 'EMPPT2', 'NMGRS2']
    elif gid == 'F2_NONMANAGERIAL_EMPLOYMENT_DID':
        pre = ['EMPFT', 'EMPPT']
        post = ['EMPFT2', 'EMPPT2']
    else:
        raise ValueError('Unsupported group_id: ' + str(gid))
    outcols = pre + post
    choices = {k: _choice(spec, k) for k in ['D_SAMPLE', 'D_MISSING', 'D_OUTLIER', 'D_ADJUST', 'D_INFERENCE']}
    if choices['D_SAMPLE'] not in ('ALL_VALID', 'CHAIN_OVERLAP', 'FRANCHISE_ONLY'):
        raise ValueError('Unsupported D_SAMPLE: ' + choices['D_SAMPLE'])
    if choices['D_MISSING'] not in ('COMPLETE_CASE', 'MICE_MI'):
        raise ValueError('Unsupported D_MISSING: ' + choices['D_MISSING'])
    if choices['D_OUTLIER'] not in ('RAW', 'WINSOR_1_99'):
        raise ValueError('Unsupported D_OUTLIER: ' + choices['D_OUTLIER'])
    if choices['D_ADJUST'] not in ('UNADJUSTED_DID', 'COVARIATE_DID', 'STRATIFIED_DID', 'BASELINE_EMP_DID'):
        raise ValueError('Unsupported D_ADJUST: ' + choices['D_ADJUST'])
    if choices['D_INFERENCE'] not in ('HC2_OLS', 'WELCH_T'):
        raise ValueError('Unsupported D_INFERENCE: ' + choices['D_INFERENCE'])
    if choices['D_INFERENCE'] == 'WELCH_T' and choices['D_ADJUST'] != 'UNADJUSTED_DID':
        raise ValueError('WELCH_T is only compatible with UNADJUSTED_DID.')
    assumptions = [
        'Absent the NJ minimum-wage increase, NJ and PA store employment changes would be comparable conditional on the selected design and adjustment.',
        'Treatment is defined by STATE and is not endogenous to post-wave employment within the adopted design.',
        'Stores are independent conditional on adjustment variables or strata after duplicate-SHEET exclusion.',
        'Missingness assumptions are correct for complete-case or MICE paths; MI uses Barnard-Rubin df for HC2/Welch.',
        'The selected headcount operationalization measures the intended store employment concept.',
        'For COVARIATE_DID and BASELINE_EMP_DID, at least one CHAIN must contain both NJ and PA stores.'
    ]
    d, diag = _prep(data, outcols)
    diag.update(choices)
    d, note = _sample(d, choices['D_SAMPLE'])
    diag['chain_overlap_note'] = note
    diag['sample_rows_after_D_SAMPLE'] = int(len(d))
    if len(d) == 0:
        raise ValueError('No valid store records after duplicate-SHEET exclusion and D_SAMPLE.')
    if choices['D_MISSING'] == 'MICE_MI':
        dm = d.dropna(subset=['CHAIN', 'CO_OWNED', 'OPEN', 'HRSOPEN']).copy()
        diag['mice_sample_rows_after_covariate_complete'] = int(len(dm))
        if len(dm) == 0:
            raise ValueError('MICE_MI leaves no stores after requiring complete covariates.')
        datasets, err = _mice(dm, outcols)
        if datasets is None:
            raise ValueError('MICE_MI failed: ' + str(err))
        taus = []
        vars_ = []
        ns = []
        dfs = []
        tests = []
        designs = []
        reasons = []
        winsor_thresholds = []
        for cur in datasets:
            if choices['D_OUTLIER'] == 'WINSOR_1_99':
                d2, thr = _winsor(cur, outcols)
                winsor_thresholds.append(thr)
            else:
                d2 = cur.copy()
            d2 = _derive(d2, pre, post)
            r = _estimate(d2, choices['D_ADJUST'], choices['D_INFERENCE'])
            tau = r.get('tau')
            if tau is None or not np.isfinite(float(tau)):
                raise ValueError('MICE completed dataset has nonfinite effect: ' + str(r.get('reason')))
            taus.append(float(tau))
            ns.append(int(r.get('n', 0)))
            tests.append(r.get('test_name', 'not identifiable'))
            designs.append(r.get('design', []))
            if r.get('status') == 'conditional_formal_test' and _finite(r.get('var')) is not None:
                vars_.append(float(r['var']))
                dfs.append(float(r['df']))
            else:
                vars_.append(None)
                dfs.append(None)
                reasons.append(str(r.get('reason', 'not identifiable completed dataset')))
        if choices['D_OUTLIER'] == 'WINSOR_1_99':
            diag['winsor_thresholds_by_completed_dataset'] = winsor_thresholds
        m = len(taus)
        taubar = float(np.mean(taus))
        n_rep = int(round(float(np.mean(ns)))) if ns else 0
        if n_rep <= 0:
            raise ValueError('MICE pooling produced nonpositive n.')
        all_vars = len(vars_) == m and all(v is not None for v in vars_)
        if all_vars:
            W = float(np.mean(vars_))
            B = float(np.var(taus, ddof=1)) if m > 1 else 0.0
            if B > 0:
                T = W + (1.0 + 1.0 / m) * B
                dfbr = (m - 1) * (1.0 + W / ((1.0 + 1.0 / m) * B)) ** 2
            else:
                T = W
                dfbr = float(m - 1)
            if not np.isfinite(T) or T <= 0 or not np.isfinite(dfbr) or dfbr <= 0:
                reason = 'MI pooled variance or Barnard-Rubin df nonfinite/nonpositive.'
                diag.update({'n': n_rep, 'mice_m': MICE_M, 'mice_maxit': MICE_MAXIT,
                             'mice_seed': MICE_SEED, 'mice_pmm_donor_count': PMM_K,
                             'mice_tau_mean': taubar, 'mice_within_variance_W': W,
                             'mice_between_variance_B': B, 'mice_total_variance_T': T,
                             'mice_df_Barnard_Rubin': dfbr, 'n_by_dataset': ns,
                             'reason': reason})
                return _result(taubar, None, None, None, n_rep, scale, estimand, diag, 'not_identifiable', 'Barnard-Rubin MI pooling', reason, assumptions)
            t = taubar / math.sqrt(T)
            p = float(2 * stats.t.sf(abs(t), dfbr))
            crit = float(stats.t.ppf(1 - ALPHA / 2, dfbr))
            diag.update({'n': n_rep, 'mice_m': MICE_M, 'mice_maxit': MICE_MAXIT,
                         'mice_seed': MICE_SEED, 'mice_pmm_donor_count': PMM_K,
                         'mice_tau_mean': taubar, 'mice_within_variance_W': W,
                         'mice_between_variance_B': B, 'mice_total_variance_T': T,
                         'mice_df_Barnard_Rubin': dfbr, 'n_by_dataset': ns,
                         'design_matrix_columns_first_completed_dataset': designs[0] if designs else [],
                         'test_name': 'Barnard-Rubin MI pooling of ' + str(choices['D_INFERENCE']),
                         'status': 'conditional_formal_test',
                         'reason': 'Computed two-sided MI pooled test with Barnard-Rubin degrees of freedom.'})
            reason2 = 'Computed MI pooled test. Direction and significance are reported separately; P<alpha is not treated as directional confirmation of H1.'
            return _result(taubar, p, taubar - crit * math.sqrt(T), taubar + crit * math.sqrt(T), n_rep, scale, estimand, diag, 'conditional_formal_test', diag['test_name'], reason2, assumptions)
        else:
            reason = 'MICE completed but at least one completed dataset lacked a finite HC2/Welch variance; pooled formal test unavailable. ' + '; '.join(reasons)
            diag.update({'n': n_rep, 'mice_m': MICE_M, 'mice_maxit': MICE_MAXIT,
                         'mice_seed': MICE_SEED, 'mice_pmm_donor_count': PMM_K,
                         'mice_tau_mean': taubar, 'n_by_dataset': ns,
                         'status': 'not_identifiable', 'reason': reason,
                         'design_matrix_columns_first_completed_dataset': designs[0] if designs else []})
            return _result(taubar, None, None, None, n_rep, scale, estimand, diag, 'not_identifiable', 'Barnard-Rubin MI pooling unavailable', reason, assumptions)
    d2 = d.dropna(subset=outcols).copy()
    if choices['D_ADJUST'] != 'UNADJUSTED_DID':
        req = ['CHAIN', 'CO_OWNED', 'OPEN', 'HRSOPEN']
        d2 = d2.dropna(subset=req).copy()
    diag['analysis_sample_n_after_missing_handling'] = int(len(d2))
    if len(d2) == 0:
        raise ValueError('COMPLETE_CASE leaves no stores for the selected outcome.')
    if choices['D_OUTLIER'] == 'WINSOR_1_99':
        d2, thr = _winsor(d2, outcols)
        diag['winsor_thresholds_first_completed_dataset'] = thr
    d2 = _derive(d2, pre, post)
    r = _estimate(d2, choices['D_ADJUST'], choices['D_INFERENCE'])
    n = int(r.get('n', 0))
    tau = r.get('tau')
    p = r.get('p')
    lo = r.get('ci_lower')
    hi = r.get('ci_upper')
    status = r.get('status', 'not_identifiable')
    reason = r.get('reason', 'Not identifiable.')
    test = r.get('test_name', 'not identifiable')
    if tau is None or not np.isfinite(float(tau)):
        raise ValueError('Effect is not finite or identifiable: ' + str(reason))
    diag.update({'n': n,
                 'state_counts': {str(s): int((d2['STATE'] == s).sum()) for s in [0, 1]},
                 'chain_counts': {str(int(k)): int(v) for k, v in d2['CHAIN'].value_counts().sort_index().items()},
                 'test_name': test,
                 'design_matrix_columns_first_completed_dataset': r.get('design', []),
                 'dropped_zero_information_observations': int(r.get('dropped_zero_info', 0)),
                 'status': status,
                 'reason': reason})
    if status != 'conditional_formal_test':
        return _result(tau, None, None, None, n, scale, estimand, diag, 'not_identifiable', test, reason, assumptions)
    reason2 = reason + ' Direction and significance are reported separately; P<alpha is not treated as directional confirmation of H1.'
    return _result(tau, p, lo, hi, n, scale, estimand, diag, 'conditional_formal_test', test, reason2, assumptions)
