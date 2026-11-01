import json
import math
import warnings
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm


def _option_id(opt):
    return str(opt.get('id', ''))


def _option_params(opt):
    p = opt.get('parameters', {})
    if p is None:
        return {}
    return p


def _resolve_option(spec, dim):
    sel = spec.get('selected_options', {})
    if isinstance(sel, dict) and dim in sel:
        opt = sel[dim]
        if isinstance(opt, dict):
            return opt
    choices = spec.get('choices', {})
    oid = None
    if isinstance(choices, dict):
        oid = choices.get(dim)
    if oid is None:
        raise ValueError('Cannot resolve selected option for ' + dim)
    oid = str(oid)
    p = {}
    if dim == 'D_TIME_WINDOW':
        if oid == 'Y1':
            p = {'included_years': [1970, 1980, 1990, 2000, 2010, 2020]}
        elif oid == 'Y2':
            p = {'included_years': [1970, 1980, 1990, 2000, 2010]}
        elif oid == 'Y3':
            p = {'included_years': [1980, 1990, 2000, 2010, 2020]}
    elif dim == 'D_TRIM':
        if oid == 'T2':
            p = {'lower_percentile': 0.01, 'upper_percentile': 0.99}
    elif dim == 'D_TREND_ESTIMATOR':
        p = {'alpha': 0.05, 'alternative': 'two_sided', 'null_hypothesis': 'trend = 0'}
    return {'id': oid, 'parameters': p, 'data_binding': {}, 'label': oid}


def _included_years(opt):
    p = _option_params(opt)
    if 'included_years' in p:
        return [float(x) for x in p['included_years']]
    oid = _option_id(opt)
    maps = {
        'Y1': [1970, 1980, 1990, 2000, 2010, 2020],
        'Y2': [1970, 1980, 1990, 2000, 2010],
        'Y3': [1980, 1990, 2000, 2010, 2020],
    }
    if oid in maps:
        return [float(x) for x in maps[oid]]
    raise ValueError('Unknown D_TIME_WINDOW option: ' + oid)


def _weighted_gini(x, w):
    x = np.asarray(x, dtype=float)
    w = np.asarray(w, dtype=float)
    mask = np.isfinite(x) & np.isfinite(w) & (w > 0.0)
    x = x[mask]
    w = w[mask]
    if x.size < 2:
        raise ValueError('Fewer than 2 valid regions for Gini')
    W = float(w.sum())
    if not np.isfinite(W) or W <= 0.0:
        raise ValueError('Invalid total weight')
    mu = float((w * x).sum() / W)
    if not np.isfinite(mu) or mu <= 0.0:
        raise ValueError('Non-positive weighted mean for Gini')
    diff = np.abs(x[:, None] - x[None, :])
    num = float((w[:, None] * w[None, :] * diff).sum())
    den = 2.0 * W * W * mu
    return num / den


def _ols_trend_slope(years, y):
    x = np.asarray(years, dtype=float) - 1970.0
    y = np.asarray(y, dtype=float)
    xm = x.mean()
    ym = y.mean()
    den = float(((x - xm) ** 2).sum())
    if den <= 0.0:
        raise ValueError('No variation in year for OLS trend')
    slope = float(((x - xm) * (y - ym)).sum() / den)
    return slope


def _trend_r1(gdf, alpha):
    y = gdf['between_region_gini'].to_numpy(dtype=float)
    years = gdf['year'].to_numpy(dtype=float)
    n_years = int(y.size)
    if n_years < 2:
        raise ValueError('Need at least 2 years for trend')
    if n_years >= 3:
        X = np.column_stack([np.ones(n_years), years - 1970.0])
        model = sm.OLS(y, X)
        res = model.fit(cov_type='HAC', cov_kwds={'maxlags': 1, 'kernel': 'bartlett', 'use_correction': True})
        slope = float(res.params[1])
        se = float(res.bse[1])
        df_resid = float(res.df_resid)
        effect = 10.0 * slope
        if (df_resid > 0.0) and np.isfinite(se) and (se > 0.0) and np.isfinite(slope):
            tcrit = float(stats.t.ppf(1.0 - alpha / 2.0, df_resid))
            ci_low = effect - tcrit * 10.0 * se
            ci_high = effect + tcrit * 10.0 * se
            tstat = slope / se
            pval = float(2.0 * (1.0 - stats.t.cdf(abs(tstat), df_resid)))
            if pval < 0.0:
                pval = 0.0
            if pval > 1.0:
                pval = 1.0
            return effect, pval, ci_low, ci_high, True, 'conditional_formal_test'
        return effect, None, None, None, False, 'not_identifiable'
    slope = _ols_trend_slope(years, y)
    return 10.0 * slope, None, None, None, False, 'not_identifiable'


def _trend_r2(gdf):
    years = gdf['year'].to_numpy(dtype=float)
    y = gdf['between_region_gini'].to_numpy(dtype=float)
    n = int(years.size)
    if n < 2:
        raise ValueError('Need at least 2 years for Theil-Sen')
    slopes = []
    for i in range(n):
        for j in range(i + 1, n):
            dy = years[j] - years[i]
            if dy != 0.0 and np.isfinite(y[i]) and np.isfinite(y[j]):
                slopes.append((y[j] - y[i]) / dy)
    if len(slopes) == 0:
        raise ValueError('No valid pairwise slopes')
    med = float(np.median(np.asarray(slopes, dtype=float)))
    return 10.0 * med, None, None, None, False, 'not_identifiable', int(len(slopes))


def _trend_r3(gdf):
    g = gdf.dropna(subset=['between_region_gini']).sort_values('year')
    if len(g) < 2:
        raise ValueError('Need at least 2 valid years for endpoint difference')
    years = g['year'].to_numpy(dtype=float)
    y = g['between_region_gini'].to_numpy(dtype=float)
    start_year = float(years[0])
    end_year = float(years[-1])
    if end_year <= start_year:
        raise ValueError('Endpoint years not increasing')
    effect = (y[-1] - y[0]) * 10.0 / (end_year - start_year)
    return float(effect), None, None, None, False, 'not_identifiable'


def analyze(data, spec):
    if not isinstance(data, pd.DataFrame):
        raise TypeError('data must be a pandas DataFrame')
    required = ['year', 'czone', 'hhlds']
    for c in required:
        if c not in data.columns:
            raise ValueError('Missing required column: ' + c)
    opt_time = _resolve_option(spec, 'D_TIME_WINDOW')
    opt_wealth = _resolve_option(spec, 'D_WEALTH_LEVEL')
    opt_trim = _resolve_option(spec, 'D_TRIM')
    opt_weight = _resolve_option(spec, 'D_WEIGHT')
    opt_trend = _resolve_option(spec, 'D_TREND_ESTIMATOR')
    years = _included_years(opt_time)
    df = data.loc[data['year'].isin(years)].copy()
    if len(df) == 0:
        raise ValueError('No rows in selected time window')
    year_float = pd.to_numeric(df['year'], errors='coerce').astype(float)
    czone_float = pd.to_numeric(df['czone'], errors='coerce').astype(float)
    hhlds_float = pd.to_numeric(df['hhlds'], errors='coerce').astype(float)
    valid_base = year_float.notna() & czone_float.notna() & np.isfinite(hhlds_float) & (hhlds_float > 0.0)
    df = df.loc[valid_base].copy()
    if len(df) == 0:
        raise ValueError('No valid rows after base validation')
    df['year'] = pd.to_numeric(df['year'], errors='coerce').astype(float)
    df['czone'] = pd.to_numeric(df['czone'], errors='coerce').astype(float)
    df['hhlds'] = pd.to_numeric(df['hhlds'], errors='coerce').astype(float)
    dup = df.duplicated(subset=['year', 'czone']).any()
    if bool(dup):
        raise ValueError('Duplicate czone-year rows after filtering')
    wid = _option_id(opt_wealth)
    if wid == 'W1':
        if 'wealth_total' not in df.columns:
            raise ValueError('W1 requires wealth_total')
        df['region_wealth'] = pd.to_numeric(df['wealth_total'], errors='coerce').astype(float) / df['hhlds']
    elif wid == 'W2':
        if 'mean' not in df.columns:
            raise ValueError('W2 requires mean')
        df['region_wealth'] = pd.to_numeric(df['mean'], errors='coerce').astype(float)
    elif wid == 'W3':
        if 'median' not in df.columns:
            raise ValueError('W3 requires median')
        df['region_wealth'] = pd.to_numeric(df['median'], errors='coerce').astype(float)
    else:
        raise ValueError('Unknown D_WEALTH_LEVEL option: ' + wid)
    tid = _option_id(opt_trim)
    trim_diag = {'option': tid, 'applied': False}
    if tid == 'T2':
        p = _option_params(opt_trim)
        lower = float(p.get('lower_percentile', 0.01))
        upper = float(p.get('upper_percentile', 0.99))
        qs = [lower * 100.0, upper * 100.0]
        trim_diag = {'option': tid, 'applied': True, 'lower_percentile': lower, 'upper_percentile': upper, 'by': 'year', 'boundary_rule': 'strict replacement below lower and above upper'}
        for yr, idx in df.groupby('year').groups.items():
            vals = df.loc[idx, 'region_wealth'].to_numpy(dtype=float)
            finite = np.isfinite(vals)
            if finite.sum() >= 1:
                p_lo, p_hi = np.percentile(vals[finite], qs)
                v = vals.copy()
                v[finite & (v < p_lo)] = p_lo
                v[finite & (v > p_hi)] = p_hi
                df.loc[idx, 'region_wealth'] = v
    elif tid != 'T1':
        raise ValueError('Unknown D_TRIM option: ' + tid)
    gid = _option_id(opt_weight)
    if gid == 'G1':
        df['w'] = df['hhlds'].astype(float)
    elif gid == 'G2':
        df['w'] = 1.0
    else:
        raise ValueError('Unknown D_WEIGHT option: ' + gid)
    records = []
    for yr, g in df.groupby('year', sort=True):
        x = g['region_wealth'].to_numpy(dtype=float)
        w = g['w'].to_numpy(dtype=float)
        mask = np.isfinite(x) & np.isfinite(w) & (w > 0.0)
        x2 = x[mask]
        w2 = w[mask]
        if x2.size < 2:
            raise ValueError('Year ' + str(yr) + ' has fewer than 2 valid regions')
        gini = _weighted_gini(x2, w2)
        records.append({
            'year': float(yr),
            'between_region_gini': float(gini),
            'n_regions': int(x2.size),
            'n_obs_year': int(len(g)),
            'weight_sum': float(w2.sum()),
        })
    gdf = pd.DataFrame(records).sort_values('year').reset_index(drop=True)
    rid = _option_id(opt_trend)
    p = _option_params(opt_trend)
    alpha = float(p.get('alpha', 0.05))
    if rid == 'R1':
        effect, pval, ci_low, ci_high, test_valid, status = _trend_r1(gdf, alpha)
        test_name = p.get('test_name', 'two-sided OLS linear-trend test with HAC(1) standard errors')
        missing_p_reason = None if test_valid else p.get('missing_p_reason', 'insufficient residual degrees of freedom for HAC t test')
        n_pairs = None
    elif rid == 'R2':
        effect, pval, ci_low, ci_high, test_valid, status, n_pairs = _trend_r2(gdf)
        test_name = p.get('test_name', 'Theil-Sen median pairwise slope (descriptive; no formal test)')
        missing_p_reason = p.get('missing_p_reason', 'Theil-Sen slope has no frozen sampling model for a valid p-value')
    elif rid == 'R3':
        effect, pval, ci_low, ci_high, test_valid, status = _trend_r3(gdf)
        test_name = p.get('test_name', 'endpoint per-decade difference (descriptive; no formal test)')
        missing_p_reason = p.get('missing_p_reason', 'Endpoint difference has no frozen sampling model for a valid p-value')
        n_pairs = None
    else:
        raise ValueError('Unknown D_TREND_ESTIMATOR option: ' + rid)
    cd = spec.get('comparison_definition', {})
    effect_scale = cd.get('effect_scale')
    estimand = cd.get('estimand')
    n_out = {
        'n_obs': int(len(df)),
        'czone_count': int(df['czone'].nunique()),
        'year_count': int(gdf.shape[0]),
        'n_years': int(gdf.shape[0]),
        'n_region_year': int(len(df)),
    }
    if n_pairs is not None:
        n_out['n_year_pairs'] = int(n_pairs)
    out_contract = spec.get('output_contract', {})
    inf_contract = out_contract.get('inference', {}) if isinstance(out_contract, dict) else {}
    assumptions = inf_contract.get('assumptions', [])
    if not isinstance(assumptions, list):
        assumptions = [str(assumptions)]
    null_hypothesis = p.get('null_hypothesis', inf_contract.get('null_hypothesis', 'trend = 0'))
    alternative = p.get('alternative', inf_contract.get('alternative', 'two_sided'))
    null_value = cd.get('null_value', 0)
    if missing_p_reason is not None:
        reason = missing_p_reason
    elif test_valid:
        reason = 'conditional formal test computed from selected OLS-HAC estimator'
    else:
        reason = 'no formal test available for selected estimator'
    inference = {
        'status': status,
        'test_name': test_name,
        'alternative': alternative,
        'alpha': alpha,
        'null_value': null_value,
        'assumptions': assumptions,
        'reason': reason,
        'p_value': pval,
    }
    diagnostics = {
        'group_id': spec.get('group_id'),
        'choices': spec.get('choices', {}),
        'selected_option_ids': {
            'D_TIME_WINDOW': _option_id(opt_time),
            'D_WEALTH_LEVEL': wid,
            'D_TRIM': tid,
            'D_WEIGHT': gid,
            'D_TREND_ESTIMATOR': rid,
        },
        'selected_option_parameters': {
            'D_TIME_WINDOW': _option_params(opt_time),
            'D_WEALTH_LEVEL': _option_params(opt_wealth),
            'D_TRIM': _option_params(opt_trim),
            'D_WEIGHT': _option_params(opt_weight),
            'D_TREND_ESTIMATOR': _option_params(opt_trend),
        },
        'time_window': years,
        'n_input_rows': int(len(data)),
        'n_analysis_rows': int(len(df)),
        'n_years_used': int(gdf.shape[0]),
        'n_unique_czone': int(df['czone'].nunique()),
        'annual_between_region_gini': records,
        'gini_formula': 'weighted Gini across region wealth values with frequency weights; each region contributes w pseudo-households',
        'trim': trim_diag,
        'estimator': {
            'id': rid,
            'description': test_name,
            'p_value_computed': pval is not None,
            'ci_computed': (ci_low is not None and ci_high is not None),
        },
        'random_seed': None,
        'resampling': {'used': False, 'details': 'No bootstrap, permutation, or random split used.'},
        'missing_p_reason': missing_p_reason,
        'effect_multiplier': 10.0,
        'estimand': estimand,
        'effect_scale': effect_scale,
    }
    return {
        'effect_size': float(effect),
        'p_value': None if pval is None else float(pval),
        'ci_lower': None if ci_low is None else float(ci_low),
        'ci_upper': None if ci_high is None else float(ci_high),
        'n': n_out,
        'effect_scale': effect_scale,
        'estimand': estimand,
        'diagnostics': diagnostics,
        'inference': inference,
    }
