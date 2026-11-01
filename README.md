# Machines Can Be Blinded: Would Social Science Find It Again?

Code and experimental materials for the accompanying research proposal. The prototype uses a knowledge graph of historical analyses to design and run multiverse analyses of new studies. The system retrieves relevant data-processing decisions and modeling methods. A language model proposes analysis choices and records their sources. Boba executes the frozen specifications; a separate evaluation compares effect direction and significance with published conclusions.

The v16 experiments cover five studies and eight research questions: 504 specifications, 480 successful estimates, and 24 failed executions.

## Repository

| Directory | Contents |
|---|---|
| `prototype/` | Original retrieval, design, execution, and evaluation source |
| `cases/` | Five accepted analysis implementations, frozen plans, specifications, and Boba templates |
| `data/` | Saved specification-level results and figure metadata |
| `src/` | Portable execution and plotting support |
| `reference_figures/` | Eight final curves in PNG and SVG |
| `config/` | Model settings, example study manifest, and external-resource checklist |
| `docs/` | Data access, experimental reproduction, and prototype setup |
| `validation/` | Recorded execution and figure checks |

## Installation

Use Python 3.12. From the repository directory:

```sh
python -m venv .venv
```

Activate it with `.venv\Scripts\Activate.ps1` on Windows PowerShell or `source .venv/bin/activate` on macOS/Linux, then install:

```sh
python -m pip install -r requirements-analysis.txt
```

## Reproduce the experiments

Obtain the study inputs and prepare the five analysis tables following [Data access](docs/DATA_ACCESS.md). Original observations are not distributed in this repository. For the validated HRS example, prepare `external_data/P02/data.csv`, then run:

```sh
python rerun_frozen.py --data-root external_data --case P02 --output rerun_hrs
```

This command executes the 126 frozen HRS specifications with Boba, calculates direction and significance summaries, compares the new estimates with v16, and draws the curve from the newly calculated results. It uses the recorded model-generated plans and code; it does not ask the language model to design them again. The HRS estimates, available intervals and P values matched v16 exactly. See [Experimental reproduction](docs/REPRODUCING_EXPERIMENTS.md) to run the other studies or the full batch.

## Inspect the saved results

To draw the figures directly from the supplied result tables:

```sh
python reproduce_figures.py
```

The figures are written to `outputs/`. This shorter route needs only `requirements.txt` and does not recompute the analyses.

## Run a new study

The generation prototype and its original prompts are included under `prototype/`. It requires a DeepSeek account, the historical graph and embedding resources, and a configured external workspace. [Prototype setup](docs/PROTOTYPE.md) explains the resource checks, study manifest, and run command. This route has not been validated as a self-contained installation on a new machine. New model calls may produce different designs.

Target papers and author code are restricted to extraction and evaluation. The designer receives the released H1, data metadata, two historical retrieval outputs, and effect type/unit. Author conclusions are opened after the independent results are frozen. API credentials are supplied locally and are not included here.

## Study outputs

| Study | Curve files | Specifications |
|---|---|---:|
| GEOWEALTH-US | `P01_curve_1` | 108 |
| Procrastination and cognitive status | `P02_curve_1` | 126 |
| Minimum wages and employment | `P03_curve_1`, `P03_curve_2` | 120 |
| College proximity and schooling | `P04_curve_1` | 90 |
| Depression and delinquency | `P05_curve_1` to `P05_curve_3` | 60 |

Each curve has PNG and SVG versions. The 24 failed paths belong to the depression-delinquency study; missing P values are retained as unavailable. See [Validation](docs/VALIDATION.md) and [Changes](docs/CHANGES.md).

## Citation

Please cite the accompanying proposal, *Machines Can Be Blinded: Would Social Science Find It Again?* Bibliographic details will be added when available. The multiverse execution framework is [Boba](https://doi.org/10.1109/TVCG.2020.3028985); the curve presentation follows [Specification Curve Analysis](https://doi.org/10.1038/s41562-020-0912-z). A distribution license has not yet been assigned by the authors.
