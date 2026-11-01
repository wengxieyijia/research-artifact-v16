"""Replot frozen v16 results without executing any scientific analysis."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import re
import sys
import textwrap
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


CASE_IDS = ("P01", "P02", "P03", "P04", "P05")
OPTION_COLORS = (
    "#a04961", "#7e67a9", "#429383", "#d09235",
    "#637c40", "#386b89", "#7a6a57",
)
SIGNIFICANCE_COLORS = {
    "significant": "#151515",
    "not_significant": "#73b6d4",
    "unavailable": "#738590",
}


class ArtifactError(ValueError):
    """An input or output does not satisfy the frozen artifact contract."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def input_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ArtifactError("An integrity entry points outside the artifact.")
    return path


def optional_number(value: str, field: str) -> float | None:
    if value in ("", "NA"):
        return None
    try:
        number = float(value)
    except ValueError as error:
        raise ArtifactError(f"Invalid numeric field: {field}.") from error
    if not math.isfinite(number):
        raise ArtifactError(f"Nonfinite numeric field: {field}.")
    return number


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        records = list(csv.DictReader(handle))
    seen = set()
    for row in records:
        identity = (row["case"], row["spec_id"])
        if identity in seen:
            raise ArtifactError("Duplicate case/specification identity.")
        seen.add(identity)
        row["choices"] = json.loads(row["selected_option_ids"])
        if not isinstance(row["choices"], dict):
            raise ArtifactError("Selected options must be a dictionary.")
        for key in ("effect_size", "ci_lower", "ci_upper", "p_value", "alpha"):
            row[key] = optional_number(row[key], key)
        flag = row["significant"]
        if flag not in ("True", "False", ""):
            raise ArtifactError("An unknown significance flag was encountered.")
        row["significant"] = {"True": True, "False": False, "": None}[flag]
        if row["status"] == "success" and row["effect_size"] is None:
            raise ArtifactError("A successful path lacks its saved estimate.")
        if row["p_status"] == "valid":
            p, alpha = row["p_value"], row["alpha"]
            if p is None or alpha is None or not 0 <= p <= 1 or not 0 < alpha < 1:
                raise ArtifactError("A saved valid test has invalid P/alpha fields.")
            if row["significant"] is not (p < alpha):
                raise ArtifactError("A saved significance flag conflicts with P < alpha.")
    return records


def point_status(row: dict) -> str:
    if row["p_status"] != "valid":
        return "unavailable"
    return "significant" if row["significant"] else "not_significant"


def ordered_rows(rows: list[dict], curve: dict) -> list[dict]:
    return sorted(
        (row for row in rows
         if row["case"] == curve["case"]
         and row["plot_group"] == curve["plot_group"]
         and row["status"] == "success"),
        key=lambda row: (row["effect_size"], row["spec_id"]),
    )


def validate_inputs(root: Path) -> tuple[dict, list[dict], dict]:
    """Check files and saved values; never replace or estimate a missing result."""
    integrity = read_json(root / "data" / "integrity.json")
    for relative, expected in integrity["files"].items():
        path = input_path(root, relative)
        if not path.is_file() or sha256(path) != expected:
            raise ArtifactError(f"Missing or modified frozen asset: {relative}.")
    schema = read_json(root / "data" / "plot_schema.json")
    rows = load_rows(root / "data" / "specification_results.csv")
    expected = integrity["expected_counts"]
    counts = {
        "paths": len(rows),
        "successful_paths": sum(row["status"] == "success" for row in rows),
        "failed_paths": sum(row["status"] != "success" for row in rows),
        "curves": len(schema["curves"]),
        "valid_p": sum(row["status"] == "success" and row["p_status"] == "valid" for row in rows),
        "unavailable_p": sum(row["status"] == "success" and row["p_status"] != "valid" for row in rows),
    }
    if counts != expected:
        raise ArtifactError("Frozen path or figure counts do not match the artifact.")
    known = set()
    for curve in schema["curves"]:
        identity = (curve["case"], curve["plot_group"])
        if identity in known:
            raise ArtifactError("A curve identity occurs more than once.")
        known.add(identity)
        if not re.fullmatch(r"P0[1-5]_curve_[1-3]", curve["stem"]):
            raise ArtifactError("Invalid output figure identifier.")
        good = ordered_rows(rows, curve)
        if len(good) != curve["expected_points"]:
            raise ArtifactError(f"Unexpected point count for {curve['stem']}.")
        if [row["spec_id"] for row in good] != curve["expected_spec_order"]:
            raise ArtifactError(f"Saved point order differs for {curve['stem']}.")
        for row in good:
            matched = [dim for dim in curve["dimensions"] if dim["family_id"] == row["family_id"]]
            if {dim["key"] for dim in matched} != set(row["choices"]):
                raise ArtifactError("The Option matrix is incomplete for a plotted path.")
            for dim in matched:
                if row["choices"][dim["key"]] not in {opt["id"] for opt in dim["options"]}:
                    raise ArtifactError("A selected Option is missing from the display schema.")
    if any((row["case"], row["plot_group"]) not in known for row in rows):
        raise ArtifactError("A saved path belongs to an unknown curve.")
    return schema, rows, counts


def output_directory(root: Path, value: str, stems: list[str], overwrite: bool) -> Path:
    output = Path(value).expanduser().resolve()
    for protected in ("data", "reference_figures", "analysis_reference", "docs", "src"):
        area = (root / protected).resolve()
        if output == area or output.is_relative_to(area):
            raise ArtifactError("The output directory overlaps a protected artifact directory.")
    targets = [output / (stem + extension) for stem in stems for extension in (".png", ".svg")]
    targets.append(output / "reproduction_record.json")
    if not overwrite and any(path.exists() for path in targets):
        raise ArtifactError("An output already exists. Choose another --output directory or pass --overwrite.")
    output.mkdir(parents=True, exist_ok=True)
    return output


def render_curves(curves: list[dict], rows: list[dict], destination: Path, font: str) -> tuple[list[dict], dict]:
    """Adapt only the final v14/v16 presentation layer to packaged frozen inputs."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager, ft2font
    except ImportError as error:
        raise ArtifactError("Install the documented requirements before rendering.") from error

    names = {item.name for item in font_manager.fontManager.ttflist}
    if font == "auto":
        selected_font = next((name for name in ("Arial", "DejaVu Sans") if name in names), None)
    else:
        selected_font = font if font in names else None
    if selected_font is None:
        raise ArtifactError("The requested font is not installed. Try --font 'DejaVu Sans'.")
    rc = {
        "font.family": selected_font, "font.size": 9,
        "svg.fonttype": "none", "svg.hashsalt": "v16-frozen-figure-reproduction",
        "axes.unicode_minus": False,
    }
    records = []
    with plt.rc_context(rc):
        for curve in curves:
            good = ordered_rows(rows, curve)
            dimensions = curve["dimensions"]
            count = len(good)
            total_rows = sum(len(dim["options"]) + 1 for dim in dimensions)
            figure, (top, bottom) = plt.subplots(
                2, 1, figsize=(16, max(8, 4 + total_rows * .26)), sharex=True,
                gridspec_kw={"height_ratios": [1, max(1.5, total_rows * .12)], "hspace": .08},
            )
            for rank, row in enumerate(good, 1):
                color = SIGNIFICANCE_COLORS[point_status(row)]
                if row["ci_lower"] is not None and row["ci_upper"] is not None:
                    top.vlines(rank, row["ci_lower"], row["ci_upper"], color="#c0cdd3", lw=.6, alpha=.6)
                top.scatter(rank, row["effect_size"], s=14, color=color, zorder=3)
            top.axhline(curve["null_value"], color="#6c7e87", lw=.9)
            top.set_title(curve["title"] + f" | {count} specifications", loc="left", fontsize=15, pad=18)
            top.set_ylabel(curve["unit"])
            multiplier = curve["direction_multiplier"]
            top.text(
                .01, .98,
                "Black: valid P < alpha   Blue: valid P >= alpha   Gray: P unavailable/invalid\n"
                + f"Y axis: raw effect. Encoded direction = (effect - null) x {multiplier}.\n"
                + "Intervals follow each frozen inference contract; no author-value matching.",
                transform=top.transAxes, va="top", fontsize=8,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": .85},
            )
            matrix_row, positions, labels = 0, [], []
            matrix = []
            for index, dimension in enumerate(dimensions):
                matrix_row += 1
                bottom.text(
                    -.012, matrix_row, textwrap.fill(dimension["question"], width=65),
                    ha="right", va="center", transform=bottom.get_yaxis_transform(),
                    fontweight="bold", fontsize=8.5,
                )
                for option in dimension["options"]:
                    matrix_row += 1
                    positions.append(matrix_row)
                    labels.append(textwrap.fill(option["label"], width=67))
                    ranks = [
                        rank for rank, row in enumerate(good, 1)
                        if row["family_id"] == dimension["family_id"]
                        and row["choices"].get(dimension["key"]) == option["id"]
                    ]
                    bottom.scatter(ranks, [matrix_row] * len(ranks), s=10, color=OPTION_COLORS[index % len(OPTION_COLORS)])
                    matrix.append({
                        "family_id": dimension["family_id"], "decision_key": dimension["key"],
                        "option_id": option["id"], "ranks": ranks,
                    })
                bottom.axhline(matrix_row + .6, color="#edf1f3", lw=.7)
            bottom.set_yticks(positions, labels)
            bottom.tick_params(axis="y", length=0, labelsize=8.5)
            bottom.set_ylim(matrix_row + 1, 0)
            bottom.set_xlim(0, count + 2)
            ticks = sorted({1, count, *[x for x in range(25, count, 25) if count - x >= 8]}) if count > 25 else sorted({1, count})
            bottom.set_xticks(ticks)
            bottom.set_xlabel("Specification (sorted by effect; columns aligned across panels)")
            for axis in (top, bottom):
                axis.spines[["right", "top"]].set_visible(False)
            figure.patch.set_facecolor("#f3f7f8")
            figure.subplots_adjust(left=.34, right=.98, top=.93, bottom=.065)
            outputs = {}
            try:
                for extension in ("png", "svg"):
                    path = destination / f"{curve['stem']}.{extension}"
                    kwargs = {"metadata": {"Date": None}} if extension == "svg" else {}
                    figure.savefig(path, dpi=170, facecolor=figure.get_facecolor(), bbox_inches="tight", pad_inches=.18, **kwargs)
                    outputs[path.name] = sha256(path)
            finally:
                plt.close(figure)
            counts = Counter(point_status(row) for row in good)
            records.append({
                "case": curve["case"], "plot_group": curve["plot_group"], "stem": curve["stem"],
                "point_count": count, "point_status_counts": {key: counts[key] for key in SIGNIFICANCE_COLORS},
                "spec_order": [row["spec_id"] for row in good],
                "points": [{key: row[key] for key in (
                    "spec_id", "family_id", "effect_size", "ci_lower", "ci_upper",
                    "p_value", "p_status", "significant", "alpha", "choices",
                )} for row in good],
                "option_matrix": matrix, "output_sha256": outputs,
            })
    environment = {
        "python": sys.version.split()[0], "matplotlib": matplotlib.__version__,
        "numpy": importlib.metadata.version("numpy"),
        "pillow": importlib.metadata.version("Pillow"),
        "freetype": ft2font.__freetype_version__, "font_family": selected_font,
        "reference_font_family": "Arial",
        "reference_pixel_identity_expected": False,
    }
    return records, environment


def main(root: Path | None = None, arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="outputs", help="Directory for regenerated figures and their audit record.")
    parser.add_argument("--case", nargs="+", choices=CASE_IDS, help="Optional subset; the default includes all five cases.")
    parser.add_argument("--font", default="auto", help="auto prefers Arial, then DejaVu Sans; an installed font name is also accepted.")
    parser.add_argument("--overwrite", action="store_true", help="Replace only the named output files, never frozen inputs.")
    parser.add_argument("--check-only", action="store_true", help="Check frozen assets and counts without importing Matplotlib or drawing.")
    args = parser.parse_args(arguments)
    root = (root or Path(__file__).resolve().parents[1]).resolve()
    try:
        schema, rows, counts = validate_inputs(root)
        if args.check_only:
            print(json.dumps({"frozen_input_checks": "passed", **counts}, indent=2))
            return 0
        curves = [curve for curve in schema["curves"] if not args.case or curve["case"] in args.case]
        destination = output_directory(root, args.output, [curve["stem"] for curve in curves], args.overwrite)
        figures, environment = render_curves(curves, rows, destination, args.font)
        record = {
            "source_release": "v16", "scope": "frozen-result figure reproduction",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "recomputed_effects": False, "llm_calls": False, "original_data_read": False,
            "source_csv_sha256": sha256(root / "data" / "specification_results.csv"),
            "schema_sha256": sha256(root / "data" / "plot_schema.json"),
            "complete_snapshot_counts": counts, "environment": environment, "figures": figures,
        }
        (destination / "reproduction_record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(f"Wrote {len(figures)} curves as PNG and SVG to {destination}.")
        print("Saved path order, Option-matrix membership, and environment details in reproduction_record.json.")
        return 0
    except (ArtifactError, FileNotFoundError, KeyError, json.JSONDecodeError) as error:
        print(f"Reproduction stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
