# Running the design prototype

The original v16 orchestration is included under `prototype/src/decision_option_lab/`. Its entry point is `proposal_trial_v12.py`, which extends the v8/v9 workflow. The stages are ingestion, release of one H1 and effect scope, clean data semantics, Route A/B retrieval, plan review and freeze, code generation and review, official Boba execution, isolated author extraction, evaluation, and checkpoint reporting. The v16 author matching/evaluation modules provide the later post-freeze comparison policy.

## External workspace

Fresh generation depends on historical assets that are deliberately not embedded in this code release. It is not a self-contained clean-machine installation. `config/prototype_resources.json` lists the required paths. The recorded full workflow used Windows and a dedicated portable Neo4j/Java installation; starting it can launch a local database. A Linux/macOS fresh-design run has not been validated.

Initialize a new workspace without replacing any existing files:

```sh
python -m pip install -r requirements-prototype.txt
python run_pipeline.py init --workspace external_workspace
```

This copies the released source into the original directory layout and supplies model settings and a compact English checkpoint view. The saved v16 plots are unaffected. Place the external historical assets at the paths listed in the resource checklist, including:

- The complete frozen 20-paper graph directory and its source records. The original display-snapshot SHA-256 is `4064f0fe3dbf4bd6ae539d9033963f196b7c8e448d8edc92ff6b25b6e2197b0d`.
- Historical ColumnBinding embeddings from the recorded v2 retrieval release.
- The multilingual MiniLM tokenizer and ONNX model at revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`.
- A separately configured Neo4j/Java runtime, its local connection settings, and an imported DAG20 graph. These files are not credentials to be committed.

The graph-construction code is included at `prototype/src/reported_pipeline/pipeline.py` and in `scale_trial.py`/`reported_extract.py`; the Neo4j importer is `neo4j_twenty.py`. Rebuilding the historical graph additionally requires its 20 source papers/packages, classification standards, extraction instructions, and configurations. The original source archive did not contain all of these non-Python resources. This release does not claim an independently runnable graph rebuild from the Python files alone.

## Study configuration

Copy `config/study.example.json` to a local manifest, replace all placeholder paths with absolute paths, and choose new, disjoint design, quarantine, and report directories. Supply original paper/code files only for the extraction/evaluation zones. Data-column documentation must describe the data rather than disclose the author's analysis recipe. The pipeline releases the H1 and effect type/unit, not the author effect magnitude, to the designer.

Set your own `DEEPSEEK_API_KEY` in the local process environment. The checked-in model settings contain no key. The recorded model identifier is an API alias; it does not pin the provider's hidden implementation.

```sh
python run_pipeline.py check --workspace external_workspace --manifest study.local.json
python run_pipeline.py run --workspace external_workspace --manifest study.local.json
```

The check lists missing resources and input files without making a provider request. Once supplied, `run` invokes the released original orchestrator. Resource presence alone is not a guarantee that a fresh generation run will complete; no new model-generation run was performed for this packaging revision. Do not use a new model run as a byte-for-byte reproduction of the published design. Use `rerun_frozen.py` for that purpose.

## Source preservation

The accepted case analysis files and trusted workers remain byte-identical. Other historical Python sources are serialized with an equivalent Python syntax tree: formatting/comments change, and recorded non-English string values use Unicode escapes. Model instructions, scientific parameters, IDs, and frozen choices retain their original values; they were not silently translated for a new experiment. Documentation, entry points, and figure labels are English.

`run_pipeline.py` is a portability wrapper. The checkpoint HTML supplied by `init` displays the recorded stage data in a compact view; it does not reproduce the older interactive dashboard. Both additions are separate from the scientific implementations.
