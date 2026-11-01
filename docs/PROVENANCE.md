# Provenance

The release combines the original v16 source archive with the unchanged final result tables and figures from its companion technical supplement. Both original ZIP files remain unchanged.

- `Research_Artifact_v16.zip`: SHA-256 `ddf9f24bbf1ae20b514f2fbfdfe9987da6ee283248fbeabb5eabb8ce989809c5`.
- `Technical_Supplement_v16.zip`: SHA-256 `1648f1975d25b5c2bcf94cb6d92917fcbbd3d195387b7308ad508c8a49cd5e86`.

All 85 original Python sources are included. `SOURCE_PROVENANCE.json` records original/exported file hashes and parsed-source equivalence; `SOURCE_INVENTORY.csv` accounts for all original archive members. The five accepted case analyses and the trusted scientific/inference workers are byte-identical. Historical configuration and prompt strings retain their recorded values, serialized using Unicode escapes where needed. Formatting/comment removal does not change their Python syntax trees.

The specification result tables, case summaries, and 16 reference images retain their original bytes. English display schemas and Option labels were extracted from the existing final presentation state. Original observations, graph content, model weights, environments, target papers, author replication packages, credentials, and machine-specific connection files are not distributed.

New root commands provide data preparation, frozen-design computational reproduction, and external-workspace initialization/checking. They are listed in `CHANGES.md`. A new computational run uses the frozen scientific designs on external input tables; the supplied results are opened only for comparison after execution. Newly generated outputs remain separate from the v16 references. The code does not repair failed scientific paths or change a parameter to make a reference comparison pass.

See `VALIDATION.md` for the executed checks and their scope. Fresh model-generation and historical graph rebuilding remain dependent on the external resources described in `PROTOTYPE.md`.
