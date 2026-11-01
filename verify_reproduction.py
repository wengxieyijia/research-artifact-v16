"""Independently compare regenerated v16 figures and their saved plotting record."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from PIL import Image


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_svg(path: Path):
    """Ignore export metadata, generated IDs, and non-rendering XML indentation."""
    root = ET.parse(path).getroot()
    ids = [node.attrib["id"] for node in root.iter() if "id" in node.attrib]
    identifiers = {identifier: f"id_{index}" for index, identifier in enumerate(ids)}

    def replacement(value: str) -> str:
        if value.startswith("#") and value[1:] in identifiers:
            return "#" + identifiers[value[1:]]
        return re.sub(r"url\(#([^)]+)\)", lambda match: "url(#" + identifiers.get(match[1], match[1]) + ")", value)

    def normalize(node, inside_text=False):
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "metadata":
            return None
        is_text = inside_text or tag in ("text", "tspan", "textPath")
        attributes = []
        for name, value in node.attrib.items():
            attributes.append((name, identifiers[value] if name == "id" else replacement(value)))
        return (
            node.tag, tuple(sorted(attributes)),
            (node.text or "") if is_text or tag == "style" else (node.text or "").strip(),
            (node.tail or "") if inside_text else "",
            tuple(value for child in node if (value := normalize(child, is_text)) is not None),
        )

    return normalize(root)


def main(arguments=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="outputs", help="The directory produced by reproduce_figures.py.")
    parser.add_argument("--require-reference-images", action="store_true", help="Also require pixel-identical PNGs and equivalent normalized SVGs (reference typography required).")
    args = parser.parse_args(arguments)
    root = Path(__file__).resolve().parent
    output = Path(args.output).resolve()
    schema = load_json(root / "data/plot_schema.json")
    record = load_json(output / "reproduction_record.json")
    integrity = load_json(root / "data/integrity.json")
    checks, errors = [], []
    for relative, expected in integrity["files"].items():
        path = root / relative
        if not path.is_file() or digest(path) != expected:
            errors.append("A frozen input/reference asset is missing or modified: " + relative)
    if record["source_csv_sha256"] != digest(root / "data/specification_results.csv"):
        errors.append("The recorded input CSV fingerprint differs from the frozen table.")
    if record["schema_sha256"] != digest(root / "data/plot_schema.json"):
        errors.append("The recorded display schema fingerprint differs from the frozen schema.")
    if record["complete_snapshot_counts"] != integrity["expected_counts"]:
        errors.append("The recorded full-snapshot counts differ.")
    if any(record.get(key) is not False for key in ("recomputed_effects", "llm_calls", "original_data_read")):
        errors.append("The recorded execution scope is not frozen-result plotting only.")

    with (root / "data/specification_results.csv").open(encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    by_group = {}
    for row in source_rows:
        if row["status"] == "success":
            by_group.setdefault((row["case"], row["plot_group"]), []).append(row)
    curves = {(item["case"], item["plot_group"]): item for item in schema["curves"]}
    identities = [(item["case"], item["plot_group"]) for item in record["figures"]]
    if len(identities) != len(set(identities)):
        errors.append("A curve was recorded more than once.")
    if args.require_reference_images and set(identities) != set(curves):
        errors.append("The strict full-reproduction check requires all eight curves.")

    for figure in record["figures"]:
        identity = (figure["case"], figure["plot_group"])
        curve = curves[identity]
        expected = sorted(by_group[identity], key=lambda row: (float(row["effect_size"]), row["spec_id"]))
        expected_order = [row["spec_id"] for row in expected]
        data_equal = figure["spec_order"] == expected_order == curve["expected_spec_order"]
        data_equal = data_equal and len(figure["points"]) == figure["point_count"] == curve["expected_points"]
        statuses = Counter()
        for saved, actual in zip(expected, figure["points"]):
            data_equal = data_equal and all(actual[key] == saved[key] for key in ("spec_id", "family_id", "p_status"))
            for key in ("effect_size", "ci_lower", "ci_upper", "p_value", "alpha"):
                value = None if saved[key] == "" else float(saved[key])
                data_equal = data_equal and actual[key] == value
            flag = {"True": True, "False": False, "": None}[saved["significant"]]
            data_equal = data_equal and actual["significant"] is flag
            data_equal = data_equal and actual["choices"] == json.loads(saved["selected_option_ids"])
            statuses["unavailable" if saved["p_status"] != "valid" else "significant" if flag else "not_significant"] += 1
        data_equal = data_equal and figure["point_status_counts"] == {key: statuses[key] for key in ("significant", "not_significant", "unavailable")}

        expected_matrix = []
        for dimension in curve["dimensions"]:
            for option in dimension["options"]:
                ranks = [index for index, row in enumerate(expected, 1) if row["family_id"] == dimension["family_id"] and json.loads(row["selected_option_ids"])[dimension["key"]] == option["id"]]
                expected_matrix.append({"family_id": dimension["family_id"], "decision_key": dimension["key"], "option_id": option["id"], "ranks": ranks})
        matrix_equal = figure["option_matrix"] == expected_matrix

        png, svg = output / (curve["stem"] + ".png"), output / (curve["stem"] + ".svg")
        reference_png, reference_svg = root / "reference_figures" / png.name, root / "reference_figures" / svg.name
        for path in (png, svg):
            if digest(path) != figure["output_sha256"][path.name]:
                errors.append("A generated figure differs from its recorded hash: " + path.name)
        with Image.open(png) as rendered, Image.open(reference_png) as reference:
            a, b = rendered.convert("RGBA"), reference.convert("RGBA")
            png_equal = a.size == b.size and a.tobytes() == b.tobytes()
            dimensions = list(a.size)
        svg_equal = canonical_svg(svg) == canonical_svg(reference_svg)
        checks.append({
            "stem": curve["stem"], "case": curve["case"], "points": len(expected),
            "point_values_flags_and_order_match": data_equal,
            "option_matrix_matches": matrix_equal,
            "png_size": dimensions, "png_bytes_equal_reference": digest(png) == digest(reference_png),
            "png_pixels_equal_reference": png_equal,
            "svg_geometry_styles_and_text_equal_reference": svg_equal,
            "svg_bytes_equal_reference": digest(svg) == digest(reference_svg),
            "png_sha256": digest(png), "svg_sha256": digest(svg),
        })
        if not data_equal or not matrix_equal:
            errors.append("Frozen plotting content differs: " + curve["stem"])
        if args.require_reference_images and not (png_equal and svg_equal):
            errors.append("Reference-image comparison differs: " + curve["stem"])

    report = {
        "status": "passed" if not errors else "failed", "source_release": "v16",
        "validation_scope": "Frozen-result rendering, not scientific reanalysis or independent execution attestation.",
        "strict_reference_images_required": args.require_reference_images,
        "runtime_environment": record["environment"], "curve_count": len(checks),
        "point_count": sum(item["points"] for item in checks), "curves": checks, "errors": errors,
        "svg_comparison_ignores_export_metadata_generated_identifiers_and_nonrendering_xml_indentation": True,
    }
    destination = output / "validation_report.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "curve_count", "point_count", "errors")}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
