# Data access and preparation

The repository contains derived specification results, not original observations or the historical graph. Obtain the following source snapshots separately. The five expected analysis-table hashes, shapes, and study titles are in `cases/inventory.json`.

| Case | Recorded source | Preparation |
|---|---|---|
| P01 | [GEOWEALTH-US code/data](https://github.com/jhsuss/wealth-inequality/tree/c9bfe94), snapshot `c9bfe94` | Read object `ineq_cz` from `data/wealth_inequality.Rdata`; reproduce the original candidate-CSV export and selected-table CSV import/export. |
| P02 | [Monaghan study materials](https://github.com/C-Monaghan/crisp-clam/tree/dd04529), snapshot `dd04529` | Copy `analysis/data/data_long.csv`. This is an author-prepared analysis table, not raw HRS data. |
| P03 | [Card-Krueger data](https://davidcard.berkeley.edu/data_sets/njmin.zip) | Import all rows of `public.dat` using the recorded codebook field positions. |
| P04 | [Card college-proximity data](https://davidcard.berkeley.edu/data_sets/proximity.zip) | Import all rows of `nls.dat` using the recorded codebook field positions. |
| P05 | [Sims et al. materials](https://github.com/R-Computing-Lab/Sims-et-al-2024/tree/7bc7590), snapshot `7bc7590`, plus [NlsyLinks family identifiers](https://raw.githubusercontent.com/nlsy-links/NlsyLinks/master/data/SubjectDetails79.rda) | Import `data/dsSingle_unpaired.xlsx`; append `ExtendedID` by a validated many-to-one `SubjectTag` join. Keep all 8,012 rows. |

Source repositories and access conditions remain controlled by their providers. Use the recorded revisions rather than assuming the current default branches contain identical files. The expected family-map SHA-256 is `07a7213a25bc00594f930c855ad3da531cf6440818bc2a1a2c39dbce3d2d2833`. The complete author-supplied tables can contain variables already constructed upstream; the data are not independent of those upstream choices.

## Prepare tables

Install the data-conversion packages:

```sh
python -m pip install -r requirements-data.txt
```

Save the downloaded files locally, then run:

```sh
python prepare_inputs.py --geowealth wealth-inequality.zip --hrs crisp-clam.zip --minimum-wage njmin.zip --college proximity.zip --nlsy Sims-et-al-2024.zip --family-map SubjectDetails79.rda --output external_data
```

For the original collected archive, `--bundle papers_code_and_available_data.zip` replaces `--geowealth`, `--hrs`, and `--nlsy`. Supply the two Card source ZIPs and family map separately as above. Individual extracted source files or directories are also accepted.

The converter reads data files only. Fixed-width field positions are in `cases/input_recipes.json`; no author analysis script is executed. It verifies the prepared CSV against the original analysis-table hash before writing it. If a source revision or serialization differs, it stops instead of accepting a changed input. A preparation receipt lists the verified inputs.

Data preparation and analysis outputs belong in ignored local directories. Do not add participant-level data, author replication packages, family-linkage files, API credentials, or Neo4j connection secrets to Git.
