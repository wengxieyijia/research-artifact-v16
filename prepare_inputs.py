"""Prepare the five frozen analysis tables from separately obtained source files."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def member_bytes(source, suffix, paper_id=None):
    source = Path(source)
    if source.is_dir():
        candidates = [p for p in source.rglob("*") if p.is_file() and p.as_posix().endswith(suffix)]
        if len(candidates) != 1:
            raise ValueError(f"Expected one source member ending in {suffix}")
        return candidates[0].read_bytes()
    if not zipfile.is_zipfile(source):
        return source.read_bytes()
    with zipfile.ZipFile(source) as archive:
        matches = [n for n in archive.namelist() if n.endswith(suffix) and "__MACOSX" not in n]
        if matches:
            contents = {archive.read(n) for n in matches}
            if len(contents) == 1:
                return next(iter(contents))
        if paper_id:
            nested = [n for n in archive.namelist() if paper_id in n and n.endswith(".zip")]
            if len(nested) == 1:
                with zipfile.ZipFile(io.BytesIO(archive.read(nested[0]))) as inner:
                    matches = [n for n in inner.namelist() if n.endswith(suffix) and "__MACOSX" not in n]
                    if matches:
                        contents = {inner.read(n) for n in matches}
                        if len(contents) == 1:
                            return next(iter(contents))
    raise ValueError(f"Expected one source member ending in {suffix}")


def r_frame(raw, key):
    import pyreadr
    with tempfile.TemporaryDirectory(prefix="v16_data_") as temporary:
        path = Path(temporary) / "source.rda"
        path.write_bytes(raw)
        return pyreadr.read_r(str(path))[key]


def convert(case, source, recipes, family_map=None):
    import pandas as pd
    recipe = recipes[case]
    csv_options = {"index": False, "lineterminator": recipe["csv_lineterminator"]}
    raw = member_bytes(source, recipe["member_suffix"], recipe.get("paper_id"))
    if case == "P01":
        frame = r_frame(raw, "ineq_cz")
        # The original ingestion exported a candidate CSV, then read/wrote the selected table.
        frame = pd.read_csv(io.StringIO(frame.to_csv(**csv_options)))
    elif case == "P02":
        return raw
    elif case in {"P03", "P04"}:
        fields = recipe["fields"]
        frame = pd.read_fwf(io.StringIO(raw.decode("ascii")),
                            colspecs=[(f["start"] - 1, f["end"]) for f in fields],
                            names=[f["name"] for f in fields], na_values=["."])
    else:
        if not family_map:
            raise ValueError("P05 also requires --family-map SubjectDetails79.rda")
        frame = pd.read_excel(io.BytesIO(raw))
        # Reproduce the original intermediate CSV import before the identifier join.
        frame = pd.read_csv(io.StringIO(frame.to_csv(**csv_options)))
        linkage_raw = Path(family_map).read_bytes()
        if digest(linkage_raw) != recipe["family_map_sha256"]:
            raise ValueError("The NlsyLinks family map differs from the recorded source")
        linkage = r_frame(linkage_raw, "SubjectDetails79")[["SubjectTag", "ExtendedID"]]
        if linkage.SubjectTag.duplicated().any():
            raise ValueError("Family identifiers must be unique by SubjectTag")
        joined = frame.merge(linkage, on="SubjectTag", how="left", validate="many_to_one", sort=False)
        pd.testing.assert_frame_equal(frame.reset_index(drop=True), joined[list(frame)].reset_index(drop=True))
        frame = joined
    return frame.to_csv(**csv_options).encode("utf-8")


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", help="Original papers_code_and_available_data.zip, for P01/P02/P05")
    parser.add_argument("--geowealth", help="GEOWEALTH-US source ZIP, directory, or Rdata")
    parser.add_argument("--hrs", help="HRS study source ZIP, directory, or data_long.csv")
    parser.add_argument("--minimum-wage", help="Card-Krueger njmin.zip or public.dat")
    parser.add_argument("--college", help="Card proximity.zip or nls.dat")
    parser.add_argument("--nlsy", help="Sims et al. source ZIP, directory, or dsSingle_unpaired.xlsx")
    parser.add_argument("--family-map", help="Recorded NlsyLinks SubjectDetails79.rda")
    parser.add_argument("--output", default="external_data")
    args = parser.parse_args(arguments)
    sources = {"P01": args.geowealth or args.bundle, "P02": args.hrs or args.bundle,
               "P03": args.minimum_wage, "P04": args.college, "P05": args.nlsy or args.bundle}
    selected = {case: path for case, path in sources.items() if path}
    if not selected:
        parser.error("Supply at least one study source; see docs/DATA_ACCESS.md")
    output = Path(args.output).resolve()
    for name in ["cases", "data", "src", "prototype", "reference_figures", "validation", "docs"]:
        protected = (ROOT / name).resolve()
        if output == protected or output.is_relative_to(protected) or protected.is_relative_to(output):
            parser.error("Use an external-data directory separate from the artifact files")
    recipes = json.loads((ROOT / "cases/input_recipes.json").read_text("utf-8"))
    inventory = {v["case"]: v for v in json.loads((ROOT / "cases/inventory.json").read_text("utf-8"))}
    receipts = []
    for case, source in selected.items():
        destination = output / case / "data.csv"
        if destination.exists():
            raise FileExistsError(f"{case}: destination exists; choose a new --output")
        raw = convert(case, source, recipes, args.family_map)
        actual = digest(raw)
        if actual != inventory[case]["data_sha256"]:
            raise ValueError(f"{case}: conversion hash differs from the frozen table ({actual}); no analysis input was written")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        receipts.append({"case": case, "data_sha256": actual, "source": Path(source).name,
                         "rows": inventory[case]["rows"], "columns": inventory[case]["columns"]})
        print(f"{case}: prepared and verified {destination}", flush=True)
    (output / "preparation_receipt.json").write_text(json.dumps(receipts, indent=2) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
