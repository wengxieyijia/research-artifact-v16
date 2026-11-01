# Validation

Checked on Windows with Python 3.12.7 on 1 November 2026.

## Frozen-design computational reproduction

The analysis, data-conversion, and prototype Python requirements were installed in the independently created virtual environment used for the earlier figure checks, with system site packages disabled. Dependency consistency checking passed. No packages, virtual environment, raw input tables, or credentials are bundled in the release.

The five data-preparation recipes were executed against the recorded source archives and public family map. Every generated CSV matched its frozen analysis-table SHA-256. The GEOWEALTH-US conversion follows the original RData-to-candidate-CSV and selected-table CSV import/export; direct RData serialization alone initially produced different bytes and was not accepted. The converter now explicitly preserves each recorded CSV line ending. NlsyLinks emitted a date-casting warning while reading columns outside the two join fields; the joined input still matched its recorded hash exactly.

The selected computational check is the HRS procrastination/cognitive-status study (P02), a study other than GEOWEALTH-US as requested by the author. Its frozen implementation ran with official Boba 1.1.2: **126 successful paths, no failed paths, one curve, 90 valid P values, and 36 unavailable P values**. Of the 90 valid tests, 26 were significant. Batched scheduling compiled 8 scripts; all eight script exit codes were zero, and their expanded bindings cover the 126 frozen IDs exactly once.

The wider batch was stopped at the author's request once a study other than GEOWEALTH-US had completed. Other completed or partial receipts remain in the private work directory; this release does not claim a new complete five-study reanalysis. The original v16 tables and eight curves, including the 24 recorded NLSY failures, remain unchanged. No parameters or scientific implementations were repaired to make this validation pass.

All 126 HRS statuses and choices, estimates, available intervals and P values, and significance flags matched the frozen reference within rtol=1e-9 and atol=1e-12. Exact equality of every compared numeric field: **true**. Maximum absolute differences by field: `{"alpha": 0, "ci_lower": 0, "ci_upper": 0, "effect_size": 0, "p_value": 0}`. The reference result table was opened for comparison only after HRS had finished. The new curve was drawn from the newly calculated estimates.

See `../validation/reanalysis/reanalysis_report.json`, `recomputed_results.csv`, `input_preparation.json`, and `figures/` for the recorded results. The newly computed HRS PNG is byte-identical to its original figure: **true**. Numerical reproduction is distinct from a check of statistical validity or scientific applicability.

## Original saved-result figure route

The earlier `reproduce_figures.py` checks remain recorded under `validation/`. They matched all 480 saved points and Option memberships; all eight PNGs were byte-identical in the recorded Arial environment, and normalized SVG geometry/styles/text matched. This route reads saved results rather than recomputing analyses. Cross-platform font/raster identity is not promised.

## Design prototype

The released v12 orchestrator imported successfully with network and subprocess access blocked. The initialization and preflight checks were exercised in a new workspace. Missing historical resources or an absent model credential stop the run before a provider request. See `../validation/prototype_preflight.json`.

No new DeepSeek design, author-matching call, graph extraction/import, or author analysis was executed for this revision. A fresh model-generation run and a graph rebuild from only the public Python files remain unvalidated and require the external materials documented in `PROTOTYPE.md`.

## Preservation and file checks

All 85 original Python files are included and their parsed source matches the old archive. The five accepted analyses and trusted workers retain their original bytes. Frozen result tables, reference images, source ZIPs, and the original 20-paper graph were not changed. Known credentials were compared only in memory against the public files; values and secret fingerprints were not logged. A file-level manifest and source inventory accompany the release.
