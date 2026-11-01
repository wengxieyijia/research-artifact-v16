"""Prepare, check, and start the original restricted-input design prototype."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text("utf-8"))


def unchanged_copy(source, target):
    if target.exists():
        if target.read_bytes() != source.read_bytes():
            raise FileExistsError(f"Refusing to replace an existing workspace source: {target.name}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def initialize(workspace):
    for name in ["cases", "data", "src", "prototype", "reference_figures", "validation", "docs", "config"]:
        protected = ROOT / name
        if workspace == ROOT or workspace == protected or workspace.is_relative_to(protected) or protected.is_relative_to(workspace):
            raise ValueError("Use a separate external workspace")
    modules = workspace / "outputs/decision_option_lab"
    for source in (ROOT / "prototype/src/decision_option_lab").glob("*.py"):
        unchanged_copy(source, modules / source.name)
    unchanged_copy(ROOT / "prototype/src/reported_pipeline/pipeline.py",
                   workspace / "outputs/DAG_reported_20261023/pipeline.py")
    unchanged_copy(ROOT / "config/model_settings.json", modules / "config_high.json")
    # This compact checkpoint view is presentation-only; recorded scientific code is unchanged.
    unchanged_copy(ROOT / "prototype/checkpoint_report.html", modules / "auto_report_v8.html")
    print(f"Prepared the released prototype sources in {workspace}")


def preflight(workspace, manifest):
    required = read(ROOT / "config/prototype_resources.json")
    missing = [entry for entry in required if not (workspace / entry["path"]).exists()]
    cfg = read(manifest)
    fields = [cfg.get("data", {}).get("path"), cfg.get("paper", {}).get("pdf") or cfg.get("paper", {}).get("archive")]
    fields.extend(cfg.get("code", []))
    missing_inputs = [str(path) for path in fields if path and not Path(path).is_file()]
    if not cfg.get("data", {}).get("path"):
        missing_inputs.append("manifest.data.path")
    if not (cfg.get("paper", {}).get("pdf") or cfg.get("paper", {}).get("archive")):
        missing_inputs.append("manifest.paper.pdf or manifest.paper.archive")
    public = [Path(cfg[key]).resolve() for key in ["output", "quarantine", "report"]]
    disjoint = all(a != b and not a.is_relative_to(b) and not b.is_relative_to(a)
                   for i, a in enumerate(public) for b in public[i + 1:])
    if not disjoint:
        raise ValueError("Design output, author quarantine, and report directories must be disjoint")
    key_present = bool(os.environ.get("DEEPSEEK_API_KEY"))
    graph = workspace / "outputs/DAG_20papers_20261023/\u5c55\u793a\u6570\u636e\u5feb\u7167.json"
    graph_matches = None
    if graph.is_file():
        graph_matches = hashlib.sha256(graph.read_bytes()).hexdigest() == "4064f0fe3dbf4bd6ae539d9033963f196b7c8e448d8edc92ff6b25b6e2197b0d"
    # Report only presence; never return a credential or its fingerprint.
    result = {"status": "ready" if not missing and not missing_inputs and key_present and graph_matches else "resources_required",
              "missing_workspace_resources": missing, "missing_input_files": missing_inputs,
              "api_key_present_in_environment": key_present, "provider_called": False,
              "historical_graph_hash_matches": graph_matches,
              "fresh_design_generation_validated_on_new_machine": False}
    print(json.dumps(result, indent=2))
    return result


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "check", "run"])
    parser.add_argument("--workspace", required=True, help="Separate workspace with the historical resources")
    parser.add_argument("--manifest", help="Study manifest; paths must be absolute")
    args = parser.parse_args(arguments)
    workspace = Path(args.workspace).expanduser().resolve()
    if args.action == "init":
        initialize(workspace)
        return 0
    if not args.manifest:
        parser.error("--manifest is required for check and run")
    manifest = Path(args.manifest).expanduser().resolve()
    result = preflight(workspace, manifest)
    if result["status"] != "ready":
        return 2
    if args.action == "check":
        return 0
    command = [sys.executable, "-X", "utf8", str(workspace / "outputs/decision_option_lab/proposal_trial_v12.py"),
               "run", "--manifest", str(manifest)]
    return subprocess.run(command, cwd=workspace).returncode


if __name__ == "__main__":
    raise SystemExit(main())
