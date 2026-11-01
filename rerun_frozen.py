"""Recompute the five v16 studies using their frozen designs and official Boba."""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text("utf-8"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n", "utf-8")


def frozen_assignments(path):
    result = {}
    for node in ast.parse(Path(path).read_text("utf-8-sig")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            result[node.targets[0].id] = ast.literal_eval(node.value)
    return result


def protected_output(path):
    path = path.resolve()
    for name in ("cases", "data", "prototype", "src", "reference_figures", "analysis_reference", "docs", "validation"):
        protected = (ROOT / name).resolve()
        if path == protected or path.is_relative_to(protected) or protected.is_relative_to(path):
            raise ValueError("Choose an output directory separate from the supplied artifact files")
    if path == ROOT:
        raise ValueError("Choose a dedicated output directory")
    return path


def inputs(args, inventory):
    if args.inputs:
        manifest = Path(args.inputs).resolve()
        found = read(manifest)
        return {case: (manifest.parent / found[case]).resolve() for case in inventory}
    root = Path(args.data_root).resolve()
    return {case: root / inventory[case]["data_file"] for case in inventory}


def check_sources(inventory, selected, paths):
    for case in selected:
        entry = inventory[case]
        data = paths[case]
        if not data.is_file():
            raise FileNotFoundError(f"{case}: supply {entry['data_file']}; see docs/DATA_ACCESS.md")
        if sha(data) != entry["data_sha256"]:
            raise ValueError(f"{case}: input bytes differ from the frozen analysis table; use prepare_inputs.py or the recorded table")
        if sha(ROOT / "cases" / case / "analysis.py") != entry["analysis_sha256"]:
            raise ValueError(f"{case}: the accepted analysis implementation has changed")


def stage(case, source, destination, batch_size):
    folder = destination / case
    if folder.exists():
        raise FileExistsError(f"{case}: output already exists; choose a new --output directory")
    runtime = folder / "runtime"
    runtime.mkdir(parents=True)
    case_root = ROOT / "cases" / case
    protocol = frozen_assignments(case_root / "frozen_protocol.py")
    specifications = frozen_assignments(case_root / "frozen_specifications.py")["SPECIFICATIONS"]
    shutil.copyfile(source, runtime / "data.csv")
    shutil.copyfile(case_root / "analysis.py", runtime / "analysis_round_0.py")
    shutil.copyfile(ROOT / "src/execution/blind_five_worker_v7.py", runtime / "blind_five_worker_base_v7.py")
    shutil.copyfile(ROOT / "src/execution/auto_worker_v8.py", runtime / "blind_five_worker_v7.py")
    save(runtime / "specifications.json", {"specifications": specifications})
    save(runtime / "specification_plan.json", protocol["PLAN"])
    save(runtime / "specification_lock.json", {
        "data_sha256": sha(runtime / "data.csv"),
        "specifications_sha256": sha(runtime / "specifications.json"),
        "plan_sha256": sha(runtime / "specification_plan.json"),
    })
    (runtime / "temp").mkdir()
    work = runtime / "execution_round_0"
    work.mkdir()
    ids = [s["spec_id"] for s in specifications]
    batches = [ids[i:i + batch_size] for i in range(0, len(ids), batch_size)]
    config = {"graph": ["Run"], "decisions": [{"var": "SPEC_IDS", "options": [repr(batch) for batch in batches]}]}
    template = "# --- (BOBA_CONFIG)\n" + json.dumps(config, indent=2) + "\n\n# --- (Run)\n"
    template += "import sys\nsys.dont_write_bytecode = True\nsys.path.insert(0," + repr(str(runtime)) + ")\n"
    template += "from blind_five_worker_v7 import run_one\nSPEC_IDS = {{SPEC_IDS}}\n"
    template += "for SPEC_ID in SPEC_IDS:\n    run_one(" + repr(str(runtime)) + ", SPEC_ID, execution_round=0)\n"
    (work / "boba_template.py").write_text(template, "utf-8")
    return folder, runtime, work, specifications


def run_boba(case, runtime, work, specifications, jobs):
    environment = {key: value for key, value in os.environ.items()
                   if key.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT"}}
    environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1",
                       OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                       TEMP=str(runtime / "temp"), TMP=str(runtime / "temp"))
    compile_command = [sys.executable, "-X", "utf8", "-m", "boba.cli", "compile", "--script", str(work / "boba_template.py"), "--out", str(work)]
    with (work / "compile.log").open("w", encoding="utf-8") as log:
        subprocess.run(compile_command, cwd=runtime, env=environment, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    multiverse = work / "multiverse"
    expected = {s["spec_id"] for s in specifications}
    bindings = []
    for script in multiverse.rglob("universe_*.py"):
        tree = ast.parse(script.read_text("utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "SPEC_IDS" for t in n.targets))
        bindings.extend(ast.literal_eval(node.value))
    if len(bindings) != len(expected) or set(bindings) != expected:
        raise ValueError("Official Boba compilation did not enumerate every frozen path exactly once")
    save(multiverse / "lang.json", {"python": {"ext": ["py"], "run": [sys.executable, "-X", "utf8", "{{script_name}}"]}})
    command = [sys.executable, "-X", "utf8", "-m", "boba.cli", "run", "--all", "--jobs", str(jobs), "--dir", str(multiverse)]
    started, complete_since, reported = time.monotonic(), None, -1
    completion = "normal_cli_exit"
    with (work / "run.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=runtime, env=environment, stdout=log, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                count = len(list((work / "results").glob("S*.json")))
                if count // 20 != reported:
                    print(f"{case}: {count}/{len(expected)} execution receipts", flush=True)
                    reported = count // 20
                if count == len(expected):
                    if complete_since is None:
                        complete_since = time.monotonic()
                    if time.monotonic() - complete_since > 30:
                        # The original Windows executor uses the same completed-receipt policy.
                        if os.name == "nt":
                            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=30)
                        else:
                            process.terminate()
                        completion = "controller_terminated_after_all_final_receipts"
                        break
                if time.monotonic() - started > 7200:
                    raise TimeoutError("Boba exceeded the two-hour per-study execution limit")
                time.sleep(1)
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=30)
                else:
                    process.terminate()
            returncode = process.wait(timeout=30)
    records = [read(p) for p in sorted((work / "results").glob("S*.json"))]
    if len(records) != len(expected) or {r["spec_id"] for r in records} != expected:
        raise RuntimeError(f"{case}: incomplete execution; inspect {work / 'run.log'}")
    if any(r["status"] == "success" and not r.get("inference_contract_checked") for r in records):
        raise ValueError("A successful receipt lacks the original inference-contract check")
    return records, {"official_boba_compile": True, "official_boba_run": True,
                     "compiled_paths": len(bindings), "compiled_scripts": len(list(multiverse.rglob("universe_*.py"))),
                     "cli_returncode": returncode,
                     "completion": completion, "seconds": round(time.monotonic() - started, 3)}


def load_evaluator():
    path = ROOT / "src/execution/auto_evaluate_v8.py"
    spec = importlib.util.spec_from_file_location("frozen_evaluator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compare(rows, selected):
    # Reference results are opened only after every selected study has finished.
    with (ROOT / "data/specification_results.csv").open(encoding="utf-8-sig", newline="") as handle:
        original = {(r["case"], r["spec_id"]): r for r in csv.DictReader(handle) if r["case"] in selected}
    received = {(r["case"], r["spec_id"]): r for r in rows}
    if set(original) != set(received):
        raise ValueError("Recomputed path identities differ from the frozen release")
    mismatches, maximum, exact = [], {}, True
    for identity, row in received.items():
        old = original[identity]
        for key in ("status", "p_status"):
            if row[key] != old[key]:
                mismatches.append({"case": identity[0], "spec_id": identity[1], "field": key})
        if row["choices"] != json.loads(old["selected_option_ids"]):
            mismatches.append({"case": identity[0], "spec_id": identity[1], "field": "choices"})
        old_flag = {"True": True, "False": False, "": None}[old["significant"]]
        if row["significant"] is not old_flag:
            mismatches.append({"case": identity[0], "spec_id": identity[1], "field": "significant"})
        for key in ("effect_size", "ci_lower", "ci_upper", "p_value", "alpha"):
            previous = None if old[key] == "" else float(old[key])
            current = row.get(key)
            if current is None or previous is None:
                if current is not previous:
                    mismatches.append({"case": identity[0], "spec_id": identity[1], "field": key})
                continue
            difference = abs(current - previous)
            maximum[key] = max(maximum.get(key, 0), difference)
            exact = exact and current == previous
            if not math.isclose(current, previous, rel_tol=1e-9, abs_tol=1e-12):
                mismatches.append({"case": identity[0], "spec_id": identity[1], "field": key,
                                   "recomputed": current, "reference": previous})
    return {"status": "passed" if not mismatches else "differences_found", "paths_compared": len(rows),
            "all_numeric_fields_exact": exact, "relative_tolerance": 1e-9, "absolute_tolerance": 1e-12,
            "maximum_absolute_difference": maximum, "mismatches": mismatches}


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--data-root", help="Directory containing P01/data.csv through P05/data.csv")
    source.add_argument("--inputs", help="Local JSON mapping case IDs to external CSV paths")
    parser.add_argument("--case", nargs="+", choices=["P01", "P02", "P03", "P04", "P05"])
    parser.add_argument("--output", default="rerun_outputs")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=16, help="Frozen paths per official Boba script; use 1 for one script per path")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--font", default="auto")
    args = parser.parse_args(arguments)
    inventory = {entry["case"]: entry for entry in read(ROOT / "cases/inventory.json")}
    selected = args.case or list(inventory)
    if not 1 <= args.jobs <= 32:
        parser.error("--jobs must be between 1 and 32")
    if not 1 <= args.batch_size <= 64:
        parser.error("--batch-size must be between 1 and 64")
    paths = inputs(args, {case: inventory[case] for case in selected})
    check_sources(inventory, selected, paths)
    if args.check_only:
        print(json.dumps({"status": "passed", "studies": selected,
                          "frozen_paths": sum(inventory[c]["paths"] for c in selected)}, indent=2))
        return 0
    from importlib.metadata import version
    output = protected_output(Path(args.output))
    if (output / "reanalysis_report.json").exists():
        raise FileExistsError("Choose a new output directory; an earlier reanalysis is already present")
    output.mkdir(parents=True, exist_ok=True)
    evaluator = load_evaluator()
    rows, executions = [], []
    for case in selected:
        folder, runtime, work, specs = stage(case, paths[case], output, args.batch_size)
        receipts, execution = run_boba(case, runtime, work, specs, args.jobs)
        save(folder / "execution_results.json", {"results": receipts})
        evaluation, evaluated = evaluator.evaluate(specs, receipts, [])
        save(folder / "evaluation.json", evaluation)
        for row in evaluated:
            row["case"] = case
        rows.extend(evaluated)
        executions.append({"case": case, "input_sha256": sha(paths[case]),
                           "analysis_sha256": sha(ROOT / "cases" / case / "analysis.py"),
                           "batch_size": args.batch_size, **execution})
        print(f"{case}: {sum(r['status'] == 'success' for r in receipts)} successful, "
              f"{sum(r['status'] != 'success' for r in receipts)} failed", flush=True)
    comparison = compare(rows, selected)
    save(output / "recomputed_paths.json", rows)
    fields = ["case", "spec_id", "family_id", "plot_group", "status", "effect_size", "ci_lower", "ci_upper",
              "p_value", "p_status", "significant", "alpha", "selected_option_ids"]
    with (output / "recomputed_results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            values = {key: row.get(key) for key in fields}
            values["selected_option_ids"] = json.dumps(row["choices"], sort_keys=True)
            writer.writerow(values)
    from src.curve_reproduction import render_curves
    curves = [curve for curve in read(ROOT / "data/plot_schema.json")["curves"] if curve["case"] in selected]
    figures_folder = output / "figures"
    figures_folder.mkdir()
    figures, graphics = render_curves(curves, rows, figures_folder, args.font)
    save(figures_folder / "reproduction_record.json", {"scope": "figures from newly recomputed effects",
          "recomputed_effects": True, "figures": figures, "environment": graphics})
    counts = {"paths": len(rows), "success": sum(r["status"] == "success" for r in rows),
              "failed": sum(r["status"] != "success" for r in rows), "curves": len(figures),
              "valid_p": sum(r["p_status"] == "valid" for r in rows),
              "p_unavailable": sum(r["status"] == "success" and r["p_status"] != "valid" for r in rows)}
    report = {"status": comparison["status"], "scope": "frozen-design computational reproduction",
              "recomputed_effects": True, "original_data_read": True, "llm_calls": False,
              "author_material_in_execution_runtime": False, "reference_opened_after_all_executions": True,
              "counts": counts, "executions": executions, "comparison": comparison,
              "environment": {"python": sys.version.split()[0], **{name: version(name) for name in
                    ["boba", "numpy", "pandas", "scipy", "statsmodels", "scikit-learn", "matplotlib"]}}}
    save(output / "reanalysis_report.json", report)
    print(json.dumps({"status": report["status"], **counts, "output": str(output)}, indent=2))
    return 0 if comparison["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
