# Figure Reproduction Validation

Validation date: 1 November 2026. Repository: https://github.com/wengxieyijia/research-artifact-v16.

## Environment and commands

A new Windows AMD64 virtual environment used Python 3.12.7 with `include-system-site-packages = false`. All 11 pinned dependencies installed successfully; `python -m pip check` reported no broken requirements. The exact versions and font/backend information are recorded in `validation/environment.json` and `validation/reproduction_record.json`.

The documented entry points were run with that environment's interpreter:

```sh
python reproduce_figures.py --check-only
python reproduce_figures.py
python verify_reproduction.py --require-reference-images
```

An additional documented branch was exercised using a separate output directory:

```sh
python reproduce_figures.py --case P03 --font "DejaVu Sans" --output outputs_dejavu
python verify_reproduction.py --output outputs_dejavu
```

## Results

| Check | Result |
|---|---|
| Frozen input/reference fingerprints and counts | Passed: 504 paths, 480 successful estimates, 24 failures, eight curves. |
| Saved inference availability | Preserved: 372 valid P values and 108 unavailable P values among successful estimates. |
| Point values, intervals, flags, and sorting | All 480 plotted records matched exactly. |
| Decision-Option matrix memberships | All eight curves matched. |
| PNG files with Arial in the recorded environment | Eight of eight byte-identical and pixel-identical to the original references. |
| Normalized SVG geometry, styles, and text | Eight of eight matched. |
| DejaVu Sans / P03 subset | Both curves and all 120 plotted records/matrix memberships matched; typography differs as expected. |
| Original reference images, source ZIPs, and accepted analyses | Unchanged. |

`validation/figures/` contains the actual regenerated PNG/SVG files. `validation/reproduction_record.json` records the actual plotted points, sorted IDs, matrix memberships, environment, and file hashes. `validation/validation_report.json` records every curve comparison. `validation/dejavu_P03_validation.json` records the fallback-font subset check.

SVG equivalence excludes the metadata subtree, generated element IDs/ID references, and non-rendering XML indentation. Rendered text and style content are retained. SVG byte identity is not asserted. The checker initially numbered identifiers using positions that included metadata elements, causing false mismatches when export dates were omitted. That checker-only normalization was corrected; the scientific data and generated/reference figures were not changed.

## Limits

These are checks of rendering from saved outputs. No statistical model, imputation procedure, Boba path, retrieval stage, hypothesis extraction, or LLM generation was rerun. Matching PNGs does not independently authenticate or validate the original experimental analyses. Cross-platform rendering and another font can differ even when the plotted scientific content is identical. Clean macOS/Linux installations were not executed in this validation.

The current public reproduction scope remains the eight frozen curves, not a complete data-to-scientific-result rerun. Original observations, the historical graph, model credentials, and provider requests are not distributed by this figure artifact.
