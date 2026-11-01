# Provenance and Export Scope

## Frozen source archives

| Archive | SHA-256 |
|---|---|
| Research_Artifact_v16.zip | `ddf9f24bbf1ae20b514f2fbfdfe9987da6ee283248fbeabb5eabb8ce989809c5` |
| Technical_Supplement_v16.zip | `1648f1975d25b5c2bcf94cb6d92917fcbbd3d195387b7308ad508c8a49cd5e86` |

The original archives remain unchanged. This focused copy is a figure-reproduction derivative, not a replacement scientific release or a fresh model run.

## Existing records, not inferred values

`specification_results.csv`, `question_results.csv`, `cases.json`, and the renamed `figure_inventory.json` were copied byte-for-byte from the technical supplement. Every exported effect, interval, P value, significance flag, status, family, plot group, and selected-Option identity was also compared as a saved value with the corresponding final report record during preparation. These are structural/content checks on existing outputs, not empirical execution.

The ordered display schema was extracted from `Proposal_Five_Papers_20261030`: its frozen specifications, plans, evaluated paths, evaluation groups, and existing English display overlays. P05 already had English display strings and required no overlay. The source renderer's traversal/ordering rules were retained. The complete source JSON files and their unrelated model prompts, data previews, or private paths were not copied. File fingerprints are recorded in `PROVENANCE.json`.

## Rendering adaptation

`src/curve_reproduction.py` adapts the presentation behavior of `proposal_report_layout_v14.py`, used for the unchanged v16 plots. The adaptation replaces original-workspace JSON/report dependencies with the packaged CSV and minimal ordered schema. Axis units, effect order, point/interval semantics, significance colors, Option-matrix rows, layout dimensions, and export resolution are retained.

New SVG IDs use a fixed salt, and new SVG date metadata is suppressed. The default font preference follows Arial then DejaVu Sans. These choices are documented presentation/export changes; no original curve file is overwritten, and regenerated file hashes are not assumed to equal original hashes.

## Scientific implementation references

The five `analysis_reference/P01.py` through `P05.py` files are byte-identical to the accepted implementations in the source artifact. They are for inspection and are not imported or executed by the reproduction command. Dependencies and source data needed to rerun those analyses are outside the supported plotting entry point.

## Excluded source material

The former root English README is replaced, and the Chinese README and other old submission notes are not carried into this copy. Historical generation/retrieval/report utilities, full Chinese model prompts, Boba templates, and repetitive full protocol/specification dictionaries are omitted from this figure-focused export rather than translated into altered historical scientific inputs. Their original files remain in the untouched source archive, and each disposition is listed in `SOURCE_INVENTORY.csv`.

No original observation dataset, Neo4j content, embedding model, author-paper archive, dependency environment, credential, or repository history is included. The clean entry point neither needs nor reads provider credentials. All included human-readable descriptions are English.

## Validation boundary

On 1 November 2026, the requirements were installed in a new Windows Python 3.12.7 virtual environment with system site packages disabled. The input-only check, eight-curve rendering command, and independent strict numerical/matrix/image comparison completed successfully. All eight regenerated PNG files were byte-identical to their v16 references. SVG comparison preserved geometry, styles, and text while excluding export metadata, generated identifiers, and non-rendering XML indentation. A P03 subset run with DejaVu Sans also preserved all 120 plotted records and Option-matrix memberships.

The figure-reproduction command reads saved numerical outputs; it does not rerun Boba, an estimator, or a language model. These checks establish software rendering fidelity in the documented environment, not independent authentication or statistical validity of the underlying experiments. See `VALIDATION.md` and `validation/` for the recorded evidence.
