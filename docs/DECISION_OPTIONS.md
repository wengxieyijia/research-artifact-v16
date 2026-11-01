# Recorded Decision-Option Display Catalog

These are the existing English display strings used by the saved final reports. IDs and scope are unchanged. Failed-only Options can appear here without appearing as points in a figure.

## P01 / F1

### D_TIME_WINDOW

Whether the analysis window covers all available years since 1970, or is shortened to test early/recent endpoint drivers.

- `Y1`: 1970–2020 all available years
- `Y2`: 1970–2010 excluding 2020 endpoint
- `Y3`: 1980–2020 excluding 1970 start point

### D_WEALTH_LEVEL

Which regional household wealth position represents the region's household wealth distribution level.

- `W1`: Total wealth per household: wealth_total / hhlds
- `W2`: Reported mean column: mean
- `W3`: Reported median column: median

### D_TRIM

Whether to robustify extreme values in regional wealth level.

- `T1`: No trimming
- `T2`: Winsorize regional wealth level at 1%/99% by year

### D_WEIGHT

How many households each region represents when calculating between-region Gini.

- `G1`: Weighted by hhlds household count
- `G2`: Equal weight by region

### D_TREND_ESTIMATOR

How to estimate and test the change per decade from the annual between-region Gini series.

- `R1`: OLS linear trend + HAC(1)
- `R2`: Theil–Sen median pairwise slope
- `R3`: Endpoint difference change per decade

## P02 / F1

### D_CONTRAST

Among H1's pairwise between-group differences, which scalar contrast is used as the effect size for the current path?

- `O1_STATUS2_MINUS_STATUS1`: Status 2 minus status 1
- `O2_STATUS3_MINUS_STATUS1`: Status 3 minus status 1
- `O3_STATUS3_MINUS_STATUS2`: Status 3 minus status 2

### D_WAVE

Which survey wave time windows does the analysis use?

- `O1_ALL_WAVES`: All three waves
- `O2_2018`: 2018 only
- `O3_2020`: 2020 only
- `O4_2022`: 2022 only
- `O5_EXCLUDE_2020`: 2018 plus 2022, excluding 2020

### D_ADJUST

Which covariates are adjusted for in the between-group comparison?

- `O1_UNADJUSTED`: Unadjusted
- `O2_AGE_GENDER`: Age and gender
- `O3_AGE_GENDER_EDU`: Age, gender, and education
- `O4_AGE_GENDER_EDU_AGE_SQ`: Age, gender, education, and age squared

### D_MISSING

How are the 21 missing rows of Education_tri handled?

- `O1_COMPLETE_CASE`: Complete case
- `O2_MULTIPLE_IMPUTATION`: Multiple imputation for education

### D_MODEL

How are the selected pairwise contrasts estimated and formally tested under repeated measures?

- `O1_LMM_RANDOM_INTERCEPT`: Random-intercept linear mixed model
- `O2_OLS_ROBUST`: OLS with robust standard errors

## P03 / F1_TOTAL_EMPLOYMENT_DID

### D_SAMPLE

Which stores enter the NJ-versus-PA comparison?

- `ALL_VALID`: All valid fast-food stores in NJ and PA after duplicate-SHEET exclusion
- `CHAIN_OVERLAP`: Restrict to chains observed in both NJ and PA
- `FRANCHISE_ONLY`: Exclude company-owned stores

### D_MISSING

How are missing employment component counts handled?

- `COMPLETE_CASE`: Complete-case for the selected employment measure
- `MICE_MI`: MICE multiple imputation of six employment component counts with frozen PMM rules

### D_OUTLIER

Should extreme employment counts be winsorized before outcome derivation?

- `RAW`: Use raw employment counts
- `WINSOR_1_99`: Winsorize component counts at pooled 1st and 99th percentiles

### D_ADJUST

How should the NJ-versus-PA employment change be adjusted for store composition?

- `UNADJUSTED_DID`: Unadjusted difference-in-differences
- `COVARIATE_DID`: Covariate-adjusted DiD with pre-store characteristics
- `STRATIFIED_DID`: Stratified DiD by chain and ownership
- `BASELINE_EMP_DID`: Covariate-adjusted DiD with baseline total employment

### D_INFERENCE

Which two-sided formal test and variance estimator is used for the zero DiD contrast?

- `HC2_OLS`: HC2 heteroskedasticity-robust OLS t-test
- `WELCH_T`: Welch two-sample t-test on store-level total employment changes

## P03 / F2_NONMANAGERIAL_EMPLOYMENT_DID

### D_SAMPLE

Which stores enter the NJ-versus-PA nonmanagerial comparison?

- `ALL_VALID`: All valid fast-food stores in NJ and PA after duplicate-SHEET exclusion
- `CHAIN_OVERLAP`: Restrict to chains observed in both NJ and PA
- `FRANCHISE_ONLY`: Exclude company-owned stores

### D_MISSING

How are missing nonmanagerial employment component counts handled?

- `COMPLETE_CASE`: Complete-case for the selected nonmanagerial employment measure
- `MICE_MI`: MICE multiple imputation of four nonmanagerial component counts with frozen PMM rules

### D_OUTLIER

Should extreme nonmanagerial employment counts be winsorized before outcome derivation?

- `RAW`: Use raw nonmanagerial employment counts
- `WINSOR_1_99`: Winsorize nonmanagerial component counts at pooled 1st and 99th percentiles

### D_ADJUST

How should the NJ-versus-PA nonmanagerial employment change be adjusted for store composition?

- `UNADJUSTED_DID`: Unadjusted difference-in-differences
- `COVARIATE_DID`: Covariate-adjusted DiD with pre-store characteristics
- `STRATIFIED_DID`: Stratified DiD by chain and ownership
- `BASELINE_EMP_DID`: Covariate-adjusted DiD with baseline nonmanagerial employment

### D_INFERENCE

Which two-sided formal test and variance estimator is used for the zero nonmanagerial DiD contrast?

- `HC2_OLS`: HC2 heteroskedasticity-robust OLS t-test
- `WELCH_T`: Welch two-sample t-test on store-level nonmanagerial employment changes

## P04 / F1

### D_SAMPLE

Within the 24–34 base sample, whether to further restrict age to approximate a population with higher educational completion?

- `ALL`: All aged 24–34
- `AGE25`: Aged 25–34
- `AGE30`: Aged 30–34

### D_WEIGHT

When estimating the sample mean difference, whether to use 1976 NLS cross-sectional weights, and whether to apply extreme-value sensitivity treatment to the weights?

- `UNWEIGHTED`: Unweighted
- `WEIGHTED`: 1976 NLS weights
- `WINSOR99`: 1976 NLS weights 99% winsorized

### D_ADJUST

Which observed covariates are included in the linear mean-difference model?

- `NONE`: Unadjusted
- `AGE_BLACK`: Age and race
- `FAMILY`: Family background (including parental education imputation indicator)
- `EXTENDED`: Extended family background and region (reference region reg661)
- `FAMILY_REGION`: Family background plus region (reference region reg661)

### D_INFERENCE

Which standard errors and two-sided test are used for the nearc4 coefficient?

- `HC1`: HC1 robust standard errors
- `CLASSICAL`: Classical homoskedastic standard errors

## P05 / F_TOTAL

### D_UNIT

How should repeated SubjectTag rows be handled for total correlation?

- `O1`: Subject-level averaging
- `O3`: Exact-duplicate removal then subject-level averaging

### D_DEPRESSION

Which CES-D depression score should be used?

- `O1`: CESD20_1992
- `O2`: CESD7_1992
- `O3`: CESD7_1994

### D_OUTLIER

How should extreme depression and delinquency values be handled?

- `O1`: No outlier treatment
- `O2`: Winsorize 1st and 99th percentiles

### D_MISSING

How should missing depression and delinquency be handled?

- `O1`: Complete-case deletion

## P05 / F_WITHIN

### D_UNIT

How should repeated SubjectTag rows be handled for within-family correlation?

- `O1`: Subject-level averaging with unique family assignment
- `O3`: Exact-duplicate removal then subject-level averaging with unique family assignment

### D_DEPRESSION

Which CES-D depression score should be used?

- `O1`: CESD20_1992
- `O2`: CESD7_1992
- `O3`: CESD7_1994

### D_OUTLIER

How should extreme depression and delinquency values be handled?

- `O1`: No outlier treatment
- `O2`: Winsorize 1st and 99th percentiles

### D_MISSING

How should missing depression and delinquency be handled?

- `O1`: Complete-case deletion
- `O2`: MICE multiple imputation

## P05 / F_BETWEEN

### D_UNIT

How should repeated SubjectTag rows be handled before family-mean aggregation?

- `O1`: Subject-level averaging with unique family assignment
- `O3`: Exact-duplicate removal then subject-level averaging with unique family assignment

### D_DEPRESSION

Which CES-D depression score should be used?

- `O1`: CESD20_1992
- `O2`: CESD7_1992
- `O3`: CESD7_1994

### D_OUTLIER

How should extreme depression and delinquency values be handled?

- `O1`: No outlier treatment
- `O2`: Winsorize 1st and 99th percentiles

### D_MISSING

How should missing depression and delinquency be handled before family-mean aggregation?

- `O1`: Complete-case deletion
- `O2`: MICE multiple imputation
