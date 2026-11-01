# Data Dictionary

All files use UTF-8. The tables contain saved analysis outputs or presentation metadata, not original observations. The scientific release is v16; the English reproduction copy does not define a new experiment.

## specification_results.csv

There are 504 records. The compound primary key is `(case, spec_id)`; specification IDs alone repeat across studies. `family_id` and `plot_group` are also interpreted within a case.

| Field | Meaning and handling |
|---|---|
| `case` | Study ID P01-P05. |
| `spec_id` | Frozen path ID within a study. |
| `family_id` | Frozen analytical family ID. |
| `plot_group` | The existing effect-specific curve group; no regrouping is performed. |
| `status` | Saved execution status. Only `success` records with finite estimates are drawn. |
| `effect_size` | Saved raw numerical effect. The unit is supplied by the curve schema. |
| `ci_lower`, `ci_upper` | Saved interval bounds. Drawn only as an available pair; never recalculated. |
| `p_value` | Saved P value. Empty fields remain missing. |
| `p_status` | Saved inference availability/validity; `valid` permits the significance color classification. |
| `significant` | Saved `True`/`False`, or empty for unavailable inference. Runtime consistency checking compares valid flags to the saved `p_value < alpha` contract. |
| `alpha` | Saved threshold (0.05 in this snapshot). |
| `direction` | Saved direction classification, retained for provenance. The plotted y-value remains `effect_size`. |
| `selected_option_ids` | A JSON object mapping Decision keys to their selected Option IDs. Parsed as JSON, not evaluated as code. |

An empty numeric field is read as `None`. A failed path is not converted to a zero effect. Missing P values are not converted to 1 or classified as nonsignificant. All 24 failures remain in the CSV.

## plot_schema.json

Eight ordered curve definitions record `case`, `plot_group`, `stem`, `title`, `unit`, `null_value`, `direction_multiplier`, `expected_points`, `expected_spec_order`, and `dimensions`. Each dimension has a stable `family_id`, Decision `key`, existing English `question`, and ordered list of Option `id`/`label` pairs.

Dimension order and Option order follow first encounter in the original effect-sorted successful paths. They are not reconstructed by alphabetically sorting the CSV's JSON keys. This distinction preserves the original lower-panel row order. No new semantic translation or analytical choice was made during extraction.

## option_catalog.json

This contains existing English display labels for all frozen families and Options, including an Option that may have no successful plotted estimate. It is an explanatory catalog, not a substitute for a complete executable scientific protocol.

## Other inputs

- `question_results.csv`: the eight unchanged effect-group summaries, including original author-comparison scopes and denominators. Read the column names rather than pooling across groups.
- `cases.json`: five unchanged case summaries, English H1 renderings, input-table fingerprints, and effect-group summaries. Row/column counts describe excluded input datasets; they are not raw records.
- `figure_inventory.json`: original filenames, titles, units, point counts, and original PNG/SVG hashes.
- `integrity.json`: hashes of frozen input/reference assets and expected snapshot totals. It does not contain a secret or an API configuration.

## Units

P01 uses Gini coefficient change per decade; P02 uses Total_p scale points; P03 uses total or nonmanagerial employees per store; P04 uses years of schooling; P05 uses the corresponding total, within-family, or between-family Pearson correlation. Curves with different meanings remain separate.
