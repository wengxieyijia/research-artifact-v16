# Changes from Research_Artifact_v16.zip

Prepared 1 November 2026. This derivative is limited to frozen-result figure reproduction.

| Change | Files / extent | Scientific effect |
|---|---|---|
| Added one offline entry point | `reproduce_figures.py`, `src/curve_reproduction.py`, `src/__init__.py` | None: reads existing results; does not estimate models. |
| Added necessary derived inputs | `data/specification_results.csv`, `question_results.csv`, `cases.json`, `figure_inventory.json` | None: source bytes preserved. |
| Extracted English display metadata | `data/plot_schema.json`, `data/option_catalog.json` | Existing labels/IDs and ordering retained; no new scientific judgment. |
| Added integrity metadata | `data/integrity.json`, `MANIFEST.sha256`, provenance records | No numerical changes. |
| Recorded plotting dependencies | `requirements.txt` | Observed versions installed successfully in the new validation environment. |
| Replaced old documentation | One root English `README.md` plus focused English documents under `docs/` | Scope and limitations made explicit. |
| Removed Chinese and upstream material from this copy | See every original member in `SOURCE_INVENTORY.csv` | No deletion from the original archive; no translated historical prompt is passed off as the original. |
| Relocated five analysis implementations | `cases/Pxx/analysis.py` to `analysis_reference/Pxx.py` | Byte-identical, not executed. |
| Relocated original figures | `figures/` to `reference_figures/` | All 16 original image files byte-identical. |
| Made new SVG export identifiers deterministic | Stable SVG hash salt; date metadata suppressed by the new renderer | Presentation metadata only; original images unchanged. |
| Added explicit font control | Arial preference and DejaVu Sans fallback; `--font` override | Typography can vary; effects and Option choices do not. |
| Added credential/file exclusions | `.gitignore` and staged-content inspection | No API key or `.env` file is required or included. |

The initial preparation copy was retained outside this release as a documentation snapshot. The subsequent validation/release work below does not alter the source experiments.


## Validated reproduction release: 1 November 2026

- Installed the 11 pinned plotting packages in a new Windows/Python 3.12.7 environment; dependency consistency checking passed.
- Executed the input check and all eight figure redraws. All 480 saved point records, sorting, inference flags, intervals, and Option-matrix memberships matched.
- Added `verify_reproduction.py`, which independently reads the frozen CSV and compares point records, matrix membership, image files, and SVG structure. Its identifier normalization was corrected during validation to number ID-bearing nodes independently of metadata-node counts. No plotting input or reference figure was changed to obtain a passing check.
- Confirmed byte-identical PNG outputs for all eight references and equivalent normalized SVG geometry, styles, and text. SVG export timestamps and generated identifiers are deliberately excluded from that comparison.
- Exercised the documented P03 case-selection and DejaVu Sans options; both employment curves preserved their 120 numerical points and matrix memberships. Typography differences from Arial remain expected.
- Added reproducible validation commands and recorded the regenerated figures, exact comparison results, and environment under `validation/`.
- Replaced preparation-only review status documents with `docs/VALIDATION.md` and final file-level release checks. The former documents were copied to the local preparation archive, outside the published artifact.
- Updated the English README with the public repository URL and measured validation results. The original v16 ZIPs, saved scientific results, original references, and five accepted analysis implementations remain unchanged.
- Added `.gitattributes` to prevent Git from changing line endings on checkout. This preserves the frozen input hashes on Windows as well as Unix-like systems.
