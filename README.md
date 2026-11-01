# Frozen v16 Specification Curves: Reproduction Artifact

This research artifact provides an offline entry point for redrawing the eight final Specification Curves from the v16 multiverse demonstration. The figures summarize five studies and 504 saved specification-level records: 480 successful point estimates and 24 failed paths.

**Reproduction scope:** saved experimental outputs to figures. The entry point reads frozen estimates, confidence intervals, significance fields, and Decision-Option choices. It does not estimate models, generate specifications, query a knowledge graph, or contact a language-model provider. No API key is required.

**Validated reproduction, 1 November 2026:** the documented requirements were installed into a new Windows virtual environment with Python 3.12.7 and system site packages disabled. All eight curves were rendered successfully. All 480 plotted records and their Option matrices matched the frozen inputs; the eight PNG files were byte-identical to the reference images, and normalized SVG geometry, styles, and text also matched. See [validation details](docs/VALIDATION.md) and the machine-readable records under `validation/`. This validates figure reproduction from saved outputs, not scientific reanalysis.

## Contents

```text
README.md                     Scope, setup, commands, and expected outputs
requirements.txt              Observed plotting-environment package versions
reproduce_figures.py           Single offline command-line entry point
verify_reproduction.py         Independent numerical/matrix/image comparisons
src/                          Input checks and the adapted final plotting routine
data/                         Frozen derived results and ordered English plot metadata
reference_figures/            Original v16 PNG/SVG figures, preserved byte-for-byte
analysis_reference/           Five accepted scientific implementations, unchanged
validation/                   Regenerated figures, audit records, and tested environment
docs/                         Data dictionary, provenance, changes, and validation details
MANIFEST.sha256               Checksums for the prepared files
```

The repository contains derived analysis outputs, not participant-level or other original observations. Historical graph stores, embeddings, target papers, author replication archives, model-response caches, credentials, and local environments are excluded. The archived analytical implementations are provided for inspection; they are not imported by the plotting entry point. Full scientific reanalysis remains outside this artifact's reproduction scope.

## Requirements

- Python **3.12** is the documented target; the source environment recorded Python 3.12.14.
- Install the plotting dependencies listed in `requirements.txt`.
- Arial was used for the original figures. The default `--font auto` selects Arial if installed and otherwise uses Matplotlib's DejaVu Sans. Arial is not redistributed in this artifact.
- No DeepSeek account, token, Neo4j server, Boba installation, network service, raw dataset, or TeX installation is needed for redrawing. Package installation normally requires access to a package index; the subsequent plotting command is offline.

The pinned versions were read from the existing plotting environment rather than inferred from an unrelated environment. They were successfully resolved and installed in the clean validation environment. Validation was performed on Windows; no clean macOS/Linux installation is claimed, and cross-platform raster identity is not promised.

## Setup

Download the repository ZIP, or clone the [public repository](https://github.com/wengxieyijia/research-artifact-v16):

```sh
git clone https://github.com/wengxieyijia/research-artifact-v16.git
cd research-artifact-v16
```

Open a terminal **inside the directory containing this README and `reproduce_figures.py`**.

### Windows PowerShell

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe reproduce_figures.py
.\.venv\Scripts\python.exe verify_reproduction.py
```

Use a Python 3.12 interpreter for the first two commands. If several versions are installed, `py -3.12 -m venv .venv` can be used instead of `python -m venv .venv`. Activating the environment is not required when using its interpreter explicitly.

### macOS or Linux

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python reproduce_figures.py
.venv/bin/python verify_reproduction.py
```

## Run options

All commands below use `python` to denote the interpreter in the environment created above. On Windows the explicit executable is `.\.venv\Scripts\python.exe`; on macOS/Linux it is `.venv/bin/python`.

```sh
# Redraw all eight curves (default output directory: outputs/).
python reproduce_figures.py

# Redraw one study; P03 has two curves and P05 has three.
python reproduce_figures.py --case P03 --output outputs_P03

# Compare the generated data, Option matrix, PNGs, and normalized SVGs.
python verify_reproduction.py

# Require exact reference typography/pixels as in the validated Arial environment.
python verify_reproduction.py --require-reference-images

# Check saved files, path counts, and point order without importing Matplotlib.
python reproduce_figures.py --check-only

# Select the portable bundled font explicitly.
python reproduce_figures.py --font "DejaVu Sans" --output outputs_dejavu

# Replace only the named generated files in an existing output directory.
python reproduce_figures.py --output outputs --overwrite
```

The default command validates input checksums and frozen counts before drawing. It refuses to overwrite existing outputs unless `--overwrite` is supplied. The output directory must not overlap the artifact's protected input/source directories. It never edits the saved estimates or reference images.

## Expected outputs

The default run is intended to create **16 figure files** and **one JSON audit record**; the verification command adds `validation_report.json` in `outputs/`:

| Files, each as `.png` and `.svg` | Study and effect | Plotted points | Valid P | P unavailable | Significant / valid P |
|---|---|---:|---:|---:|---:|
| `P01_curve_1` | Regional wealth inequality trend | 108 | 36 | 72 | 28 / 36 |
| `P02_curve_1` | Procrastination by cognitive status | 126 | 90 | 36 | 26 / 90 |
| `P03_curve_1` | Minimum wages: total employment | 60 | 60 | 0 | 0 / 60 |
| `P03_curve_2` | Minimum wages: nonmanagerial employment | 60 | 60 | 0 | 0 / 60 |
| `P04_curve_1` | College proximity and schooling | 90 | 90 | 0 | 82 / 90 |
| `P05_curve_1` | Total depression-delinquency correlation | 12 | 12 | 0 | 12 / 12 |
| `P05_curve_2` | Within-family correlation | 12 | 12 | 0 | 4 / 12 |
| `P05_curve_3` | Between-family correlation | 12 | 12 | 0 | 12 / 12 |

These frozen v16 counts were reproduced by the validated plotting run. The 24 failed paths remain in `data/specification_results.csv`; they belong to the within-family and between-family NLSY groups and are not drawn as point estimates.

`reproduction_record.json` records the input fingerprints, runtime package and font information, figure fingerprints, sorted specification identities, saved point values, and every Option-matrix membership. It permits a later check of what was actually plotted without needing the original analysis environment.

## Figure conventions and fidelity

- Points are sorted by saved effect size, then specification ID. Option-matrix columns use exactly the same order.
- The y-axis shows the saved raw effect in its recorded unit. No cross-study standardization, pooling, or new statistical test is applied.
- Black points indicate a valid saved test with `P < alpha`; blue points indicate a valid test with `P >= alpha`; gray points indicate unavailable or invalid inference. Missing P is not treated as nonsignificance.
- Black points are **not original-author effect markers**. Author-reference values are not fitted or optimized against by this entry point.
- Confidence intervals are drawn only when both saved bounds are present. Missing intervals are not filled in.
- The lower matrix includes the Options represented by successful plotted paths, as in the original renderer. An Option occurring only in failed paths is retained in the catalog/results but is not added to the matrix as a fabricated estimate.
- English labels, dimension order, Option order, units, nulls, and plot grouping were extracted from the final saved presentation state. The rendering layout follows `proposal_report_layout_v14.py`, which also underlies the unchanged v16 curves.

The numerical records and original images are preserved exactly. New SVG metadata/element identifiers and font rendering can differ; selecting DejaVu Sans rather than Arial also changes text layout. Consequently, byte-identical or pixel-identical regenerated files are not promised across platforms. Scientific-content agreement and successful rendering were checked for all eight curves in the documented validation environment. The same checks can be rerun with `verify_reproduction.py`; strict image comparison is optional when using another font or platform. Reference-image SHA-256 values identify the supplied originals, not the expected hashes of a newly rendered SVG. Matplotlib documents these [font and backend differences](https://matplotlib.org/stable/users/explain/text/fonts.html).

## Files and provenance

- [Data dictionary](docs/DATA_DICTIONARY.md): field types, keys, units, and missing-value handling.
- [Decision-Option display catalog](docs/DECISION_OPTIONS.md): the recorded English labels and their stable identifiers.
- [Provenance](docs/PROVENANCE.md): archive fingerprints, extraction rules, retained analyses, and exclusions.
- [Change log](docs/CHANGES.md): packaging and rendering changes relative to the original review archive.
- [Source inventory](docs/SOURCE_INVENTORY.csv): the disposition and checksum of every original archive member.
- [Validation details](docs/VALIDATION.md): executed commands, comparison results, environment, and limits.
- [Validation record](validation/validation_report.json): all eight numerical/matrix/image comparisons.
- [Regenerated figures](validation/figures/): the PNG/SVG files produced by the validated run.

The original `Research_Artifact_v16.zip` is retained unchanged outside this focused reproduction copy. Its broader generation/retrieval utilities, full recorded prompts, and repetitive frozen-protocol dictionaries are not silently presented as a runnable complete pipeline here. They are outside this figure-only export and are listed in the inventory. The five accepted analytical implementations remain byte-identical in `analysis_reference/` for methodological traceability.

## Interpretation limits

These curves describe the frozen choices of a five-case prototype. They do not establish an exhaustive scientifically valid specification universe, an independent-observation sample of analyses, or a field-wide rediscovery rate. GEOWEALTH-US inference uses only five or six periods; 72 GEOWEALTH-US and 36 HRS estimates lack usable P values. The NLSY record preserves 24 failed imputation paths. No joint across-specification null test is supplied.

Author-direction/significance comparisons in the copied summary tables retain their original scopes and exclusions. Agreement of conclusions is not evidence that estimands, adjustments, or statistical tests are equivalent. Redrawing these figures does not revalidate the scientific analyses.

## Troubleshooting

- **`python` is not found:** install/select Python 3.12, reopen the terminal, and retry the setup commands.
- **A plotting package is missing:** install `requirements.txt` using the same environment interpreter that runs the script.
- **A requested font is unavailable:** use `--font "DejaVu Sans"`. This is an explicit typography change, not a numerical change.
- **A frozen file/checksum differs:** restore the supplied `data/` and `reference_figures/` files; do not change expected counts or results to make a check pass.
- **Output files already exist:** use a new `--output` directory or explicitly pass `--overwrite`.
- **SVG appearance differs in another viewer:** SVG text uses the selected font family; the receiving machine/viewer may substitute fonts. Inspect the PNG for the rasterized output.

## Credentials, licensing, and citation

No API credential is required or included. The entry point has no provider/HTTP/database integration and does not read `.env` files. `.gitignore` excludes local credential files and environments. Original observations and full target-paper or knowledge-graph content are not embedded in the plotting data.

The repository is https://github.com/wengxieyijia/research-artifact-v16. Publication bibliographic details remain to be finalized. No OSF identifier or DOI is claimed. No additional software/data license has been selected by the rights holder, and this artifact does not relicense the underlying papers or external datasets.

For a scholarly citation, use the accompanying paper once its bibliographic details are finalized. The original Specification Curve and multiverse methods include Simonsohn, Simmons, and Nelson (2020), *Specification curve analysis*, https://doi.org/10.1038/s41562-020-0912-z; and Liu et al. (2021), *Boba: Authoring and Visualizing Multiverse Analyses*, https://doi.org/10.1109/TVCG.2020.3028985.
