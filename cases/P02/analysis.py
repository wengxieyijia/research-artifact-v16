import warnings
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from statsmodels.regression.mixed_linear_model import MixedLM


def _jsonify(x):
    if x is None:
        return None
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        v = float(x)
        return v if np.isfinite(v) else None
    if isinstance(x, np.ndarray):
        return [_jsonify(v) for v in x.tolist()]
    if isinstance(x, dict):
        return {str(k): _jsonify(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonify(v) for v in x]
    return x


def _opt_id(opt):
    if isinstance(opt, dict):
        return str(opt.get('id', ''))
    if opt is None:
        return ''
    return str(opt)


def _selected_option(spec, dim):
    sel = spec.get('selected_options', {})
    v = None
    if isinstance(sel, dict):
        v = sel.get(dim)
    if isinstance(v, dict):
        return v
    choices = spec.get('choices', {})
    oid = None
    if isinstance(choices, dict):
        oid = choices.get(dim)
    if oid is None and isinstance(v, str):
        oid = v
    if oid is None and isinstance(v, dict):
        oid = v.get('id')
    if oid is None:
        return {}
    return {'id': str(oid)}


def _get_param(opt, name, default=None):
    if isinstance(opt, dict):
        p = opt.get('parameters')
        if isinstance(p, dict) and name in p:
            return p[name]
        if name in opt:
            return opt[name]
    return default


def _parse_contrast(opt):
    p = _get_param(opt, 'first_level', None)
    q = _get_param(opt, 'second_level', None)
    if p is not None and q is not None:
        return int(p), int(q)
    oid = _opt_id(opt)
    if 'STATUS3_MINUS_STATUS2' in oid:
        return 3, 2
    if 'STATUS3_MINUS_STATUS1' in oid:
        return 3, 1
    if 'STATUS2_MINUS_STATUS1' in oid:
        return 2, 1
    raise ValueError('Cannot parse D_CONTRAST')


def _parse_waves(opt):
    p = _get_param(opt, 'waves', None)
    if p is not None:
        return [int(w) for w in p]
    oid = _opt_id(opt)
    if 'EXCLUDE_2020' in oid or 'O5' in oid:
        return [2018, 2022]
    if '2018' in oid:
        return [2018]
    if '2020' in oid:
        return [2020]
    if '2022' in oid:
        return [2022]
    return [2018, 2020, 2022]


def _parse_covariates(opt):
    p = _get_param(opt, 'covariates', None)
    if p is not None:
        return list(p)
    oid = _opt_id(opt)
    if 'UNADJ' in oid or 'O1' in oid:
        return []
    if 'AGE_SQ' in oid or 'O4' in oid:
        return ['Age_c', 'Age_sq_c', 'Gender', 'Education_tri']
    if 'O2' in oid:
        return ['Age', 'Gender']
    return ['Age', 'Gender', 'Education_tri']


def _build_design(df, first_level, second_level, wave_levels, covariates):
    n = len(df)
    y = df['Total_p'].to_numpy(dtype=float)
    status = df['status'].to_numpy(dtype=int)
    wave = df['wave'].to_numpy(dtype=int)
    levels = sorted(set(int(s) for s in status))
    if first_level not in levels:
        raise ValueError(f'first_level {first_level} absent')
    if second_level not in levels:
        raise ValueError(f'second_level {second_level} absent')
    items = []
    cdict = {}
    items.append(('const', np.ones(n, dtype=float)))
    for s in levels:
        if s == second_level:
            continue
        name = f'status_{s}_vs_{second_level}'
        items.append((name, (status == s).astype(float)))
        if s == first_level:
            cdict[name] = 1.0
    if len(wave_levels) > 1:
        for w in wave_levels[1:]:
            items.append((f'wave_{w}', (wave == w).astype(float)))
    age_center = None
    for cov in covariates:
        if cov == 'Age':
            items.append(('Age', df['Age'].to_numpy(dtype=float)))
        elif cov == 'Age_c':
            a = df['Age'].to_numpy(dtype=float)
            age_center = float(a.mean())
            items.append(('Age_c', a - age_center))
        elif cov == 'Age_sq_c':
            a = df['Age'].to_numpy(dtype=float)
            if age_center is None:
                age_center = float(a.mean())
            items.append(('Age_sq_c', (a - age_center) ** 2))
        elif cov == 'Age_sq':
            a = df['Age'].to_numpy(dtype=float)
            items.append(('Age_sq', a ** 2))
        elif cov == 'Gender':
            items.append(('Gender', df['Gender'].to_numpy(dtype=float)))
        elif cov == 'Education_tri':
            edu = df['Education_tri'].to_numpy(dtype=float)
            for lev in [1, 2]:
                items.append((f'edu_{lev}', (edu == lev).astype(float)))
    names = []
    cols = []
    c = []
    contrast_zero = False
    for name, col in items:
        col = np.asarray(col, dtype=float)
        if name != 'const' and np.all(np.abs(col) < 1e-15):
            if abs(cdict.get(name, 0.0)) > 1e-15:
                contrast_zero = True
            continue
        names.append(name)
        cols.append(col)
        c.append(cdict.get(name, 0.0))
    if contrast_zero:
        raise ValueError('Contrast column all zero after dropping zero columns')
    if len(cols) == 0:
        raise ValueError('No design columns')
    X = np.column_stack(cols)
    c = np.asarray(c, dtype=float)
    if not np.any(np.abs(c) > 1e-20):
        raise ValueError('Zero contrast vector')
    return X, y, c, names


def _fit_ols(X, y, groups, c, multi_wave):
    n, p = X.shape
    if np.linalg.matrix_rank(X) < p:
        raise ValueError('Design matrix rank deficient')
    bread = np.linalg.pinv(X.T @ X)
    beta = bread @ (X.T @ y)
    resid = y - X @ beta
    if multi_wave:
        unique_groups = np.unique(groups)
        G = len(unique_groups)
        if G < 2:
            raise ValueError('Need at least 2 clusters for CR2')
        meat = np.zeros((p, p), dtype=float)
        for g in unique_groups:
            idx = np.where(groups == g)[0]
            Xg = X[idx]
            eg = resid[idx]
            Hgg = Xg @ bread @ Xg.T
            M = np.eye(len(idx)) - Hgg
            evals, evecs = np.linalg.eigh(M)
            evals = np.maximum(evals, 1e-10)
            A = evecs @ np.diag(1.0 / np.sqrt(evals)) @ evecs.T
            u = A @ eg
            v = Xg.T @ u
            meat += np.outer(v, v)
        cov = bread @ meat @ bread
        df = float(G - 1)
        method = 'OLS_CR2_cluster_robust'
    else:
        h = np.sum(X * (X @ bread), axis=1)
        h = np.clip(h, 0.0, 1.0 - 1e-10)
        wts = resid ** 2 / (1.0 - h)
        meat = (X * wts[:, None]).T @ X
        cov = bread @ meat @ bread
        df = float(n - p)
        method = 'OLS_HC2_robust'
    if df <= 0:
        raise ValueError('Non-positive residual df')
    est = float(c @ beta)
    var = float(c @ cov @ c)
    se = float(np.sqrt(max(var, 1e-20)))
    tval = est / se if se > 0 else 0.0
    pval = float(2 * stats.t.sf(abs(tval), df))
    tcrit = float(stats.t.ppf(0.975, df))
    return dict(est=est, var=var, se=se, df=df, pval=pval,
                ci_lower=est - tcrit * se, ci_upper=est + tcrit * se,
                method=method, converged=True, n=n, p=p)


def _fit_lmm_point(X, y, groups, c):
    n, p = X.shape
    if np.linalg.matrix_rank(X) < p:
        raise ValueError('Design matrix rank deficient')
    try:
        model = MixedLM(y, X, groups=groups)
        fit = model.fit(reml=True, method='lbfgs', maxiter=1000)
    except Exception as e:
        raise RuntimeError(f'LMM fitting failed: {e}')
    try:
        conv = fit.converged
    except AttributeError:
        conv = None
    if conv is False:
        raise RuntimeError('LMM did not converge')
    params = np.asarray(fit.params, dtype=float)
    if params.size < p:
        raise RuntimeError('LMM parameter vector too short')
    est = float(c @ params[:p])
    return dict(est=est, var=None, se=None, df=None, pval=None,
                ci_lower=None, ci_upper=None,
                method='LMM_REML_point_only_no_KR', converged=True, n=n, p=p)


def _fit_single(df, first_level, second_level, wave_levels, covariates, model_id):
    if len(df) == 0:
        raise ValueError('Empty data')
    status_arr = df['status'].to_numpy(dtype=int)
    if first_level not in status_arr:
        raise ValueError(f'first_level {first_level} absent in final fit')
    if second_level not in status_arr:
        raise ValueError(f'second_level {second_level} absent in final fit')
    X, y, c, names = _build_design(df, first_level, second_level, wave_levels, covariates)
    groups = df['ID'].to_numpy()
    if model_id == 'O1_LMM_RANDOM_INTERCEPT':
        return _fit_lmm_point(X, y, groups, c)
    if model_id == 'O2_OLS_ROBUST':
        return _fit_ols(X, y, groups, c, multi_wave=(len(wave_levels) > 1))
    raise ValueError(f'Unknown model {model_id}')


def _imputation_design(df):
    n = len(df)
    status = df['status'].to_numpy(dtype=int)
    wave = df['wave'].to_numpy(dtype=int)
    cols = [np.ones(n, dtype=float)]
    for s in [2, 3]:
        cols.append((status == s).astype(float))
    wave_vals = sorted(set(int(w) for w in wave))
    for w in wave_vals[1:]:
        cols.append((wave == w).astype(float))
    cols.append(df['Age'].to_numpy(dtype=float))
    cols.append(df['Gender'].to_numpy(dtype=float))
    cols.append(df['Total_p'].to_numpy(dtype=float))
    return np.column_stack(cols)


def _mice_impute_education(df, m=20, maxit=20, seed=20261029):
    edu = df['Education_tri'].to_numpy(dtype=float)
    miss = np.isnan(edu)
    if not miss.any():
        return [df.copy() for _ in range(m)], {'maxit_used': 0, 'successful_datasets': m, 'failed_datasets': []}
    X_pred = _imputation_design(df)
    X_obs = X_pred[~miss]
    y_obs = edu[~miss].astype(int)
    classes = np.unique(y_obs)
    if len(classes) < 2:
        fill = float(classes[0]) if len(classes) == 1 else 0.0
        out = []
        for i in range(m):
            d = df.copy()
            d.loc[miss, 'Education_tri'] = fill
            out.append(d)
        return out, {'maxit_used': 0, 'successful_datasets': m, 'failed_datasets': []}
    try:
        try:
            clf = LogisticRegression(multi_class='multinomial', solver='lbfgs',
                                     max_iter=2000, random_state=seed)
            clf.fit(X_obs, y_obs)
        except Exception:
            clf = LogisticRegression(solver='lbfgs', max_iter=2000, random_state=seed)
            clf.fit(X_obs, y_obs)
        proba = clf.predict_proba(X_pred[miss])
        clf_classes = np.array(clf.classes_, dtype=float)
        fit_ok = True
    except Exception as e:
        warnings.warn(f'MICE polyreg fitting failed: {e}; using observed-frequency fallback')
        probs = np.array([np.mean(y_obs == c) for c in classes], dtype=float)
        if probs.sum() <= 0:
            probs = np.ones_like(probs) / len(probs)
        else:
            probs = probs / probs.sum()
        proba = np.tile(probs, (int(miss.sum()), 1))
        clf_classes = classes.astype(float)
        fit_ok = False
    datasets = []
    rng = np.random.default_rng(seed)
    for i in range(m):
        draws = None
        for it in range(max(1, int(maxit))):
            draws_local = np.empty(int(miss.sum()), dtype=float)
            for j in range(int(miss.sum())):
                p = np.asarray(proba[j], dtype=float)
                p = np.maximum(p, 0.0)
                s = p.sum()
                if s <= 0:
                    p = np.ones_like(p) / len(p)
                else:
                    p = p / s
                draws_local[j] = rng.choice(clf_classes, p=p)
            draws = draws_local
        d = df.copy()
        d.loc[miss, 'Education_tri'] = draws
        datasets.append(d)
    meta = {'maxit_used': int(maxit), 'successful_datasets': m, 'failed_datasets': [], 'polyreg_fit_ok': fit_ok}
    return datasets, meta


def _pool_mi_ols(estimates, variances, dfs, m):
    qbar = float(np.mean(estimates))
    Ubar = float(np.mean(variances))
    B = float(np.var(estimates, ddof=1)) if m > 1 else 0.0
    T = Ubar + (1.0 + 1.0 / m) * B
    if T <= 0:
        T = max(Ubar, 1e-20)
    se = float(np.sqrt(T))
    if B > 1e-20:
        df = (m - 1) * (1.0 + Ubar / ((1.0 + 1.0 / m) * B)) ** 2
    else:
        valid = [float(d) for d in dfs if d is not None and np.isfinite(d)]
        df = float(np.mean(valid)) if valid else 1.0
    df = max(1.0, float(df))
    tval = qbar / se if se > 0 else 0.0
    pval = float(2 * stats.t.sf(abs(tval), df))
    tcrit = float(stats.t.ppf(0.975, df))
    return dict(est=qbar, var=T, se=se, df=df, pval=pval,
                ci_lower=qbar - tcrit * se, ci_upper=qbar + tcrit * se,
                method='OLS_MI_Rubin')


def _pool_mi_point(estimates, m):
    qbar = float(np.mean(estimates))
    return dict(est=qbar, var=None, se=None, df=None, pval=None,
                ci_lower=None, ci_upper=None,
                method='LMM_MI_Rubin_point_only_no_KR')


def analyze(data, spec):
    if not isinstance(data, pd.DataFrame):
        raise TypeError('data must be a pandas DataFrame')
    df = data.copy()
    rows_input = int(len(df))
    required = ['ID', 'wave', 'status', 'Total_p']
    for col in required:
        if col not in df.columns:
            raise ValueError(f'Required column missing: {col}')
    for col in ['ID', 'wave', 'status', 'Total_p']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df[df['status'].isin([1, 2, 3]) & df['Total_p'].notna() &
            df['ID'].notna() & df['wave'].notna()].copy()
    rows_base = int(len(df))
    if rows_base == 0:
        raise ValueError('No rows after base filter')
    contrast_opt = _selected_option(spec, 'D_CONTRAST')
    wave_opt = _selected_option(spec, 'D_WAVE')
    adjust_opt = _selected_option(spec, 'D_ADJUST')
    missing_opt = _selected_option(spec, 'D_MISSING')
    model_opt = _selected_option(spec, 'D_MODEL')
    first_level, second_level = _parse_contrast(contrast_opt)
    waves = _parse_waves(wave_opt)
    covariates = _parse_covariates(adjust_opt)
    adjust_id = _opt_id(adjust_opt)
    missing_id = _opt_id(missing_opt)
    model_id = _opt_id(model_opt)
    df = df[df['wave'].isin(waves)].copy()
    rows_wave = int(len(df))
    if rows_wave == 0:
        raise ValueError('No rows after wave filter')
    observed = sorted(set(int(s) for s in df['status'].unique()))
    if first_level not in observed:
        raise ValueError(f'first_level {first_level} missing after filtering (observed: {observed})')
    if second_level not in observed:
        raise ValueError(f'second_level {second_level} missing after filtering (observed: {observed})')
    if missing_id == 'O2_MULTIPLE_IMPUTATION' and ('Education_tri' not in covariates):
        raise ValueError('K1: MI requires Education_tri in model')
    if len(waves) == 1 and model_id == 'O1_LMM_RANDOM_INTERCEPT':
        raise ValueError('K2: LMM requires multiple waves')
    needed_original = ['Total_p', 'status', 'ID', 'wave']
    if any(c in covariates for c in ['Age', 'Age_c', 'Age_sq_c']):
        needed_original.append('Age')
    if 'Gender' in covariates:
        needed_original.append('Gender')
    if 'Education_tri' in covariates:
        needed_original.append('Education_tri')
    needed_original = list(dict.fromkeys(needed_original))
    for cov in covariates:
        if cov in ['Age_c', 'Age_sq_c'] and 'Age' not in df.columns:
            raise ValueError('Age column missing')
        if cov in ['Age', 'Gender', 'Education_tri'] and cov not in df.columns:
            raise ValueError(f'{cov} column missing')
    non_impute = [v for v in needed_original if v != 'Education_tri']
    df_base = df.dropna(subset=non_impute).copy()
    if len(df_base) == 0:
        raise ValueError('No rows left after dropping baseline NAs')
    wave_levels = sorted(int(w) for w in pd.unique(df_base['wave']))
    if model_id == 'O1_LMM_RANDOM_INTERCEPT' and len(wave_levels) < 2:
        raise ValueError('LMM requires at least two waves in the fitted data')
    n_education_dropped = 0
    n_mi = None
    mi_meta = None
    df_used = None
    if missing_id == 'O1_COMPLETE_CASE':
        before = len(df_base)
        if 'Education_tri' in needed_original:
            df_model = df_base.dropna(subset=needed_original).copy()
            n_education_dropped = int(before - len(df_model))
        else:
            df_model = df_base.copy()
        if len(df_model) == 0:
            raise ValueError('No rows left after complete-case filtering')
        result = _fit_single(df_model, first_level, second_level, wave_levels, covariates, model_id)
        n_used = int(len(df_model))
        n_id = int(df_model['ID'].nunique())
        effect_size = result['est']
        p_value = result['pval']
        ci_lower = result['ci_lower']
        ci_upper = result['ci_upper']
        df_used = result['df']
        estimator = result['method']
    elif missing_id == 'O2_MULTIPLE_IMPUTATION':
        if 'Education_tri' not in needed_original:
            raise ValueError('K1: MI requires Education_tri in model')
        df_mi = df_base.copy()
        m_imp = 20
        maxit_imp = 20
        seed_imp = 20261029
        datasets, mi_meta = _mice_impute_education(df_mi, m=m_imp, maxit=maxit_imp, seed=seed_imp)
        estimates = []
        variances = []
        mi_dfs = []
        failures = []
        for idx, d_imp in enumerate(datasets):
            try:
                r = _fit_single(d_imp, first_level, second_level, wave_levels, covariates, model_id)
                if np.isfinite(r['est']):
                    estimates.append(r['est'])
                    if r['var'] is not None:
                        variances.append(r['var'])
                    mi_dfs.append(r['df'])
                else:
                    failures.append(f'dataset {idx}: non-finite estimate')
            except Exception as e:
                failures.append(f'dataset {idx}: {e}')
        if len(estimates) == 0:
            raise RuntimeError(f'All MI dataset fits failed: {failures[:3]}')
        if model_id == 'O1_LMM_RANDOM_INTERCEPT':
            pooled = _pool_mi_point(estimates, len(estimates))
            effect_size = pooled['est']
            p_value = None
            ci_lower = None
            ci_upper = None
            df_used = None
            estimator = pooled['method']
        else:
            if len(variances) != len(estimates):
                raise RuntimeError('MI variances missing for some successful fits')
            pooled = _pool_mi_ols(estimates, variances, mi_dfs, len(estimates))
            effect_size = pooled['est']
            p_value = pooled['pval']
            ci_lower = pooled['ci_lower']
            ci_upper = pooled['ci_upper']
            df_used = pooled['df']
            estimator = pooled['method']
        n_used = int(len(df_mi))
        n_id = int(df_mi['ID'].nunique())
        n_mi = len(estimates)
        mi_meta['successful_datasets'] = len(estimates)
        mi_meta['failed_datasets'] = failures
    else:
        raise ValueError(f'Unsupported D_MISSING: {missing_id}')
    if not np.isfinite(float(effect_size)):
        raise RuntimeError('Non-finite effect_size')
    cd = spec.get('comparison_definition', {})
    if not isinstance(cd, dict):
        cd = {}
    if 'effect_scale' not in cd:
        raise ValueError('comparison_definition.effect_scale missing')
    if 'estimand' not in cd:
        raise ValueError('comparison_definition.estimand missing')
    effect_scale = cd['effect_scale']
    estimand = cd['estimand']
    null_value = cd.get('null_value', 0)
    oc = spec.get('output_contract', {})
    inf = oc.get('inference', {}) if isinstance(oc, dict) else {}
    test_name = inf.get('test_name', 'Selected pairwise contrast t test')
    alternative = inf.get('alternative', 'two_sided')
    alpha = inf.get('alpha', 0.05)
    assumptions = inf.get('assumptions', [])
    limitations = inf.get('limitations', [])
    if model_id == 'O1_LMM_RANDOM_INTERCEPT':
        inference_status = 'unavailable'
        reason = ('Kenward-Roger denominator df formal t test is not implemented in this module; '
                  'the REML random-intercept model converged and the point estimate was computed, '
                  'but p_value and CI are unavailable. This is an implementation limitation, '
                  'not statistical non-identifiability and not non-significance.')
        point_estimate_computed = True
        frozen_test_implemented = False
        frozen_test_missing = 'Kenward-Roger denominator df t test'
    else:
        if p_value is None:
            inference_status = 'unavailable'
            reason = 'Point estimate computed but formal robust t test p-value unavailable.'
            point_estimate_computed = True
            frozen_test_implemented = False
            frozen_test_missing = 'robust t test'
        else:
            inference_status = 'conditional_formal_test'
            reason = ('Formal robust t test executed for the selected pairwise contrast under '
                      'the frozen covariance specification.')
            point_estimate_computed = True
            frozen_test_implemented = True
            frozen_test_missing = None
    status_counts = {str(int(k)): int(v) for k, v in df['status'].value_counts().sort_index().items()}
    wave_counts = {str(int(k)): int(v) for k, v in df['wave'].value_counts().sort_index().items()}
    diagnostics = {
        'rows_input': rows_input,
        'rows_after_base_filter': rows_base,
        'rows_after_wave_filter': rows_wave,
        'rows_used_in_model': int(n_used),
        'n_unique_id': int(n_id),
        'status_counts': status_counts,
        'wave_counts': wave_counts,
        'waves': [int(w) for w in waves],
        'contrast': {'first_level': int(first_level), 'second_level': int(second_level)},
        'D_CONTRAST': _opt_id(contrast_opt),
        'D_WAVE': _opt_id(wave_opt),
        'D_ADJUST': adjust_id,
        'D_MISSING': missing_id,
        'D_MODEL': model_id,
        'estimator': estimator,
        'df': df_used,
        'convergence': True,
        'failure': None,
        'n_education_dropped': int(n_education_dropped),
        'point_estimate_computed': point_estimate_computed,
        'frozen_test_implemented': frozen_test_implemented,
        'frozen_test_missing': frozen_test_missing,
        'mi_datasets_requested': 20 if missing_id == 'O2_MULTIPLE_IMPUTATION' else None,
        'mi_datasets_successful': n_mi,
        'mi_maxit': 20 if missing_id == 'O2_MULTIPLE_IMPUTATION' else None,
        'mi_seed': 20261029 if missing_id == 'O2_MULTIPLE_IMPUTATION' else None,
        'mi_failures': mi_meta.get('failed_datasets', []) if mi_meta is not None else None,
        'warnings': []
    }
    out = {
        'effect_size': effect_size,
        'p_value': p_value,
        'ci_lower': ci_lower,
        'ci_upper': ci_upper,
        'n': int(n_used),
        'effect_scale': effect_scale,
        'estimand': estimand,
        'diagnostics': diagnostics,
        'inference': {
            'status': inference_status,
            'test_name': test_name,
            'alternative': alternative,
            'alpha': alpha,
            'null_value': null_value,
            'assumptions': assumptions,
            'limitations': limitations,
            'reason': reason
        }
    }
    return _jsonify(out)
