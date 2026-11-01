# Changes in the prototype release

This revision replaces the figure-only repository introduction with a concise project README and restores the broader v16 research prototype.

- Restored the original retrieval, model-design, Boba execution, evaluation, graph-construction, and supporting Python source.
- Restored the five frozen protocols, specification lists, and original Boba templates. Accepted analysis files and trusted workers are byte-identical to v16.
- Added `rerun_frozen.py` to stage separate runtimes, run official Boba on external data, evaluate new results, compare them after execution, and generate figures from the new estimates.
- The portable Boba runner batches 16 frozen paths per script by default to reduce startup overhead; `--batch-size 1` preserves one script per path. Each original worker call, frozen choice, and execution receipt remains separate.
- Added `prepare_inputs.py` and recorded input recipes. They perform data-format conversion and the original public-identifier join, with strict table-hash checks.
- Added `run_pipeline.py`, credential-free model settings, an example study manifest, and an external-resource checklist. Fresh generation retains external historical workspace requirements; it is not represented as a newly validated self-contained workflow.
- Moved detailed reproduction, data access, prototype setup, and verification information out of the main README.
- Retained the earlier figure-reproduction command and all frozen result tables and reference images.
- Serialized historical non-English model/configuration strings with Unicode escapes while preserving their parsed values. Scientific prompts and parameters were not translated or redesigned.

No new specifications or scientific methods were introduced. The existing v16 results, graph, and original ZIP archives remain unchanged. Recomputed validation outputs are separate from the frozen reference results. Author matching was not regenerated.

The current computational validation is the 126-specification HRS case. After that study completed, the remaining broader run was stopped at the author's request. The release does not claim a new full five-study rerun.
