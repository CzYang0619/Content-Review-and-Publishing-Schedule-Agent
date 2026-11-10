"""Reproduce fixtures, run cases, assert business outcomes, write real evidence."""
import argparse
import copy
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.agent import run
from src.model import LiveModel, MockModel


def fixtures():
    req = {"request_id": "req-normal", "material_id": "M01", "requested_at": "2026-11-10T18:00:00+08:00", "channel": "short-video", "hard_requirement": True}
    world = {"materials": json.loads((ROOT / "data/materials.json").read_text(encoding="utf-8")), "rules": json.loads((ROOT / "data/rules.json").read_text(encoding="utf-8")), "schedule": [], "supplements": {}}
    values = {}
    for name in ("normal", "missing_metadata", "rule_risk", "slot_conflict", "duplicate", "save_failure", "supplement_recovery", "changed_occupancy", "confirmed_alternative", "read_failure", "all_slots_occupied"):
        values[name] = {"request": {**req, "request_id": "req-" + name}, "world": copy.deepcopy(world)}
    values["missing_metadata"]["world"]["materials"]["M01"].pop("owner")
    values["rule_risk"]["world"]["materials"]["M01"]["copyright"] = "unknown"
    occupied = {"at": req["requested_at"], "channel": req["channel"]}
    values["slot_conflict"]["world"]["schedule"] = [occupied]
    values["save_failure"]["world"]["failures"] = {"save_draft": "always"}
    values["supplement_recovery"]["world"]["materials"]["M01"].pop("owner")
    values["supplement_recovery"]["world"]["supplements"] = {"M01": {"owner": "补充记录中的作者"}}
    values["changed_occupancy"]["world"]["schedule"] = [occupied, {**occupied, "at": "2026-11-10T19:00:00+08:00"}]
    values["confirmed_alternative"]["world"]["schedule"] = [occupied]
    values["confirmed_alternative"]["request"]["confirmed_at"] = "2026-11-10T19:00:00+08:00"
    values["read_failure"]["world"]["failures"] = {"read_material": "once"}
    values["all_slots_occupied"]["world"]["schedule"] = [{**occupied, "at": f"2026-11-10T{hour}:00:00+08:00"} for hour in range(18, 24)]
    return values


def check(name, output):
    expected = {"normal": "completed", "missing_metadata": "needs_info", "rule_risk": "blocked", "slot_conflict": "needs_confirmation", "duplicate": "completed", "save_failure": "failed", "supplement_recovery": "completed", "changed_occupancy": "needs_confirmation", "confirmed_alternative": "completed", "read_failure": "completed"}
    errors = []
    evidence = output.get("first_execution", output)
    trace = evidence.get("trace", [])
    if any(item.get("event") == "model_error" for item in trace):
        errors.append("model unavailable; scenario was not exercised")
    actions = [item.get("decision", {}).get("action") for item in trace]
    if "read_material" not in actions or "check_rules" not in actions:
        errors.append("review path was not exercised")
    if name == "save_failure" and not any(item.get("result", {}).get("error") == "INJECTED_SAVE_DRAFT_FAILURE" for item in trace):
        errors.append("save failure injection was not reached")
    if name in expected and output["status"] != expected[name]:
        errors.append("status expected " + expected[name] + ", got " + output["status"])
    if output["published"] is not False:
        errors.append("published must be false")
    saved = name in ("normal", "slot_conflict", "duplicate", "supplement_recovery", "changed_occupancy", "confirmed_alternative", "read_failure")
    if name != "all_slots_occupied" and output["draft"]["saved"] != saved:
        errors.append("unexpected save state")
    if name == "slot_conflict" and output["suggested_at"] != "2026-11-10T19:00:00+08:00":
        errors.append("expected 19:00 proposal")
    if name == "changed_occupancy" and output["suggested_at"] != "2026-11-10T20:00:00+08:00":
        errors.append("expected 20:00 proposal")
    if name == "duplicate" and (output["draft_count"] != 1 or not output["draft"].get("duplicate")):
        errors.append("duplicate request must produce exactly one draft")
    if name in ("slot_conflict", "changed_occupancy") and (not output["pending_items"] or output["draft"].get("reserved")):
        errors.append("unapproved proposal cannot reserve slot")
    return errors


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["mock", "live"], default="mock")
    p.add_argument("--cases", nargs="*")
    p.add_argument("--generate-only", action="store_true")
    p.add_argument("--fail-fast", action="store_true", help="Stop on provider failure instead of sending the remaining cases")
    p.add_argument("--output-dir", help="Separate evidence directory for a model experiment")
    args = p.parse_args()
    output_root = Path(args.output_dir).resolve() if args.output_dir else ROOT / "examples" / args.mode
    cases = fixtures()
    for name, data in cases.items():
        path = ROOT / "examples" / "inputs" / (name + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.generate_only:
        return 0
    model = LiveModel() if args.mode == "live" else MockModel()
    planned = args.cases or list(cases)
    summary = {"mode": args.mode, "model": model.name, "executed_at": datetime.now(timezone.utc).isoformat(), "planned_cases": planned, "cases": []}
    for name in planned:
        data = cases[name]
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "drafts.db"
            first = run(data["request"], data["world"], db, model)
            output = run(data["request"], data["world"], db, model) if name == "duplicate" and first["draft"]["saved"] else first
            if name == "duplicate":
                output["first_execution"] = copy.deepcopy(first)
            errors = check(name, output)
            path = output_root / (name + ".json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            evidence_path = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
            summary["cases"].append({"name": name, "status": output["status"], "passed": not errors, "errors": errors, "file": str(evidence_path).replace("\\", "/")})
            print(name, output["status"], "PASS" if not errors else errors, flush=True)
            summary["unrun_cases"] = [item for item in planned if item not in [c["name"] for c in summary["cases"]]]
            (path.parent / "evaluation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if args.fail_fast and any(t.get("event") == "model_error" for t in output.get("first_execution", output)["trace"]):
                break
    path = output_root / "evaluation.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return int(any(not item["passed"] for item in summary["cases"]))


if __name__ == "__main__":
    raise SystemExit(main())
