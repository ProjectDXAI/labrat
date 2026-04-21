#!/usr/bin/env python3
"""Shared helpers for the labrat vNext runtime."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


PLACEHOLDER_TOKEN = "LABRAT_PLACEHOLDER"
PHASE0_FILES = [
    "branches.yaml",
    "dead_ends.md",
    "research_brief.md",
    "research_sources.md",
    "evaluation.yaml",
    "runtime.yaml",
]
STATE_FILES = [
    "runtime.json",
    "jobs.json",
    "workers.json",
    "frontier.json",
]
MIN_PYTHON = (3, 10)
IMPORT_NAME_OVERRIDES = {
    "pyyaml": "yaml",
    "scikit-learn": "sklearn",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    with open(path) as f:
        return json.load(f)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_text(path: Path, content: str) -> None:
    _atomic_write_bytes(path, content.encode("utf-8"))


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, indent=2, sort_keys=False) + "\n")


def write_yaml(path: Path, payload: Any) -> None:
    write_text(path, yaml.safe_dump(payload, sort_keys=False))


def ensure_file(path: Path, content: str = "") -> None:
    if not path.exists():
        write_text(path, content)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(payload, sort_keys=False))
        f.write("\n")


def latest_records(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = row.get(key)
        if value:
            latest[value] = row
    return latest


def load_yaml(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    with open(path) as f:
        return yaml.safe_load(f) or ({} if default is None else default)


def read_text(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def find_readiness_issues(lab_root: Path) -> list[str]:
    issues: list[str] = []

    for name in PHASE0_FILES:
        path = lab_root / name
        if not path.exists():
            issues.append(f"Missing {name}.")
            continue
        if path.suffix in {".md", ".yaml", ".yml"} and PLACEHOLDER_TOKEN in path.read_text():
            issues.append(f"{name} still contains `{PLACEHOLDER_TOKEN}` placeholders.")

    branches = load_yaml(lab_root / "branches.yaml", {})
    if not branches.get("families"):
        issues.append("branches.yaml must define at least one family in `families:`.")

    runtime_cfg = load_yaml(lab_root / "runtime.yaml", {})
    if not runtime_cfg.get("workers", {}).get("pools"):
        issues.append("runtime.yaml must define at least one worker pool.")

    eval_cfg = load_yaml(lab_root / "evaluation.yaml", {})
    if not eval_cfg.get("search_eval") or not eval_cfg.get("selection_eval"):
        issues.append("evaluation.yaml must define both `search_eval` and `selection_eval`.")
    if not eval_cfg.get("prediction_tests"):
        issues.append("evaluation.yaml must define at least one held-out `prediction_tests` challenge.")

    return issues


def runtime_initialized(lab_root: Path) -> bool:
    state_dir = lab_root / "state"
    return state_dir.exists() and all((state_dir / name).exists() for name in STATE_FILES)


def load_lab_state(lab_root: Path) -> dict[str, Any]:
    state_dir = lab_root / "state"
    candidate_rows = load_jsonl(state_dir / "candidates.jsonl")
    evaluation_rows = load_jsonl(state_dir / "evaluations.jsonl")
    checkpoint_rows = load_jsonl(state_dir / "checkpoints.jsonl")
    jobs = load_json(state_dir / "jobs.json", {"queued": [], "leased": [], "finished": []})
    workers = load_json(state_dir / "workers.json", {"workers": {}})
    runtime = load_json(state_dir / "runtime.json", {})
    frontier = load_json(
        state_dir / "frontier.json",
        {
            "global_champion": None,
            "family_champions": {},
            "elite_archive": {"global": [], "families": {}},
            "family_funding": {},
            "decisive_challenges": {},
            "audit_queue": [],
            "invalid_fast_candidates": [],
            "unstable_candidates": [],
            "pending_expansion": None,
            "frame_break_required": False,
        },
    )
    return {
        "runtime_config": load_yaml(lab_root / "runtime.yaml", {}),
        "evaluation_config": load_yaml(lab_root / "evaluation.yaml", {}),
        "branches_config": load_yaml(lab_root / "branches.yaml", {}),
        "runtime": runtime,
        "jobs": jobs,
        "workers": workers,
        "frontier": frontier,
        "candidate_rows": candidate_rows,
        "evaluation_rows": evaluation_rows,
        "checkpoint_rows": checkpoint_rows,
        "candidates": latest_records(candidate_rows, "candidate_id"),
    }


def checkpoint_interval(lab_root: Path, state: dict[str, Any] | None = None) -> int:
    state = state or load_lab_state(lab_root)
    return int(state.get("runtime_config", {}).get("checkpoint_interval", 12))


def invalid_fast_candidates(state: dict[str, Any]) -> list[str]:
    frontier = state.get("frontier", {})
    if frontier.get("invalid_fast_candidates"):
        return list(frontier["invalid_fast_candidates"])
    return [
        candidate_id
        for candidate_id, candidate in state.get("candidates", {}).items()
        if candidate.get("status") == "invalidated" and candidate.get("suspicion") == "invalid_fast"
    ]


def audit_candidates(state: dict[str, Any]) -> list[str]:
    frontier = state.get("frontier", {})
    queue = frontier.get("audit_queue", [])
    if queue:
        return list(queue)
    return invalid_fast_candidates(state)


def frontier_plateaued(state: dict[str, Any]) -> bool:
    runtime = state.get("runtime", {})
    if runtime.get("active_phase") == "frame_break_needed":
        return True
    frontier = state.get("frontier", {})
    if frontier.get("frame_break_required"):
        return True
    stagnation = int(runtime.get("stagnation_counter", 0) or 0)
    threshold = int(state.get("runtime_config", {}).get("plateau", {}).get("window", 6))
    return stagnation >= threshold


def remaining_cheap_probes(state: dict[str, Any]) -> int:
    frontier = state.get("frontier", {})
    total = 0
    for family_state in frontier.get("family_funding", {}).values():
        total += int(family_state.get("remaining_cheap_probes", 0) or 0)
    return total


def active_worker_count(state: dict[str, Any]) -> int:
    workers = state.get("workers", {}).get("workers", {})
    return sum(1 for worker in workers.values() if worker.get("status") == "leased")


def queued_job_count(state: dict[str, Any]) -> int:
    return len(state.get("jobs", {}).get("queued", []))


def leased_job_count(state: dict[str, Any]) -> int:
    return len(state.get("jobs", {}).get("leased", []))


def pending_candidate_count(state: dict[str, Any]) -> int:
    pending_statuses = {"queued", "running", "evaluating"}
    return sum(
        1
        for candidate in state.get("candidates", {}).values()
        if candidate.get("status") in pending_statuses
    )


def has_pending_runtime_work(state: dict[str, Any]) -> bool:
    return queued_job_count(state) > 0 or leased_job_count(state) > 0 or pending_candidate_count(state) > 0


def total_candidates(state: dict[str, Any]) -> int:
    return len(state.get("candidates", {}))


def determine_next_phase(lab_root: Path, state: dict[str, Any] | None = None) -> str:
    issues = find_readiness_issues(lab_root)
    if issues:
        return "design"
    if not runtime_initialized(lab_root):
        return "supervisor"

    state = state or load_lab_state(lab_root)
    runtime = state.get("runtime", {})
    step_count = int(runtime.get("step_count", 0) or 0)
    interval = checkpoint_interval(lab_root, state)
    if step_count > 0 and interval > 0 and step_count % interval == 0:
        return "checkpoint"
    if state.get("frontier", {}).get("pending_expansion"):
        return "expansion"
    if audit_candidates(state):
        return "audit"
    if has_pending_runtime_work(state):
        return "supervisor"
    if frontier_plateaued(state) and remaining_cheap_probes(state) <= 0:
        return "frame_break"
    return "supervisor"


def summarize_lab(lab_root: Path) -> dict[str, Any]:
    readiness = find_readiness_issues(lab_root)
    summary: dict[str, Any] = {
        "lab_root": str(lab_root),
        "ready": not readiness,
        "readiness_issues": readiness,
        "runtime_initialized": runtime_initialized(lab_root),
        "next_phase": "design" if readiness else "supervisor",
    }
    if not summary["runtime_initialized"]:
        return summary

    state = load_lab_state(lab_root)
    frontier = state.get("frontier", {})
    runtime = state.get("runtime", {})
    global_champion = frontier.get("global_champion") or {}
    summary.update(
        {
            "next_phase": determine_next_phase(lab_root, state),
            "step_count": int(runtime.get("step_count", 0) or 0),
            "active_phase": runtime.get("active_phase", "idle"),
            "queued_jobs": queued_job_count(state),
            "leased_jobs": leased_job_count(state),
            "finished_jobs": len(state.get("jobs", {}).get("finished", [])),
            "worker_leases": active_worker_count(state),
            "total_workers": len(state.get("workers", {}).get("workers", {})),
            "total_candidates": total_candidates(state),
            "pending_candidates": pending_candidate_count(state),
            "audit_queue": audit_candidates(state),
            "invalid_fast_candidates": invalid_fast_candidates(state),
            "pending_expansion": frontier.get("pending_expansion"),
            "global_champion": global_champion,
            "family_credits": {
                name: family_state.get("credits", 0)
                for name, family_state in frontier.get("family_funding", {}).items()
            },
            "families": sorted((state.get("branches_config", {}).get("families") or {}).keys()),
            "remaining_cheap_probes": remaining_cheap_probes(state),
        }
    )
    return summary


def _parse_requirement_name(line: str) -> str | None:
    raw = line.split("#", 1)[0].strip()
    if not raw or raw.startswith(("-", ".")) or raw.startswith("git+"):
        return None
    if "@" in raw and "://" in raw:
        return None
    raw = raw.split(";", 1)[0].strip()
    for marker in ("==", ">=", "<=", "~=", "!=", ">", "<"):
        if marker in raw:
            raw = raw.split(marker, 1)[0].strip()
            break
    raw = raw.split("[", 1)[0].strip().lower()
    return raw or None


def _import_name_for_requirement(name: str) -> str:
    return IMPORT_NAME_OVERRIDES.get(name, name.replace("-", "_"))


def _check_requirements(path: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    checked: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    skipped: list[str] = []
    seen: set[str] = set()

    if not path.exists():
        return checked, missing, skipped

    for line in path.read_text().splitlines():
        name = _parse_requirement_name(line)
        if not name:
            raw = line.split("#", 1)[0].strip()
            if raw:
                skipped.append(raw)
            continue
        if name in seen:
            continue
        seen.add(name)
        import_name = _import_name_for_requirement(name)
        record = {"requirement": name, "import_name": import_name}
        checked.append(record)
        if importlib.util.find_spec(import_name) is None:
            missing.append(record)

    return checked, missing, skipped


def _bootstrap_state(lab_root: Path) -> str:
    state_dir = lab_root / "state"
    if not state_dir.exists():
        return "missing"
    present = [name for name in STATE_FILES if (state_dir / name).exists()]
    if len(present) == len(STATE_FILES):
        return "ready"
    if present:
        return "partial"
    return "missing"


def diagnose_lab(lab_root: Path) -> dict[str, Any]:
    summary = summarize_lab(lab_root)
    bootstrap_state = _bootstrap_state(lab_root)
    requirements_path = lab_root / "requirements.txt"
    checked_requirements, missing_requirements, skipped_requirements = _check_requirements(requirements_path)
    script_dir = lab_root / "scripts"
    expected_scripts = [
        "bootstrap.py",
        "operator_helper.py",
        "runtime.py",
        "evaluator.py",
        "research_scout.py",
        "run_experiment.py",
    ]
    missing_scripts = [name for name in expected_scripts if not (script_dir / name).exists()]
    python_ok = sys.version_info >= MIN_PYTHON

    runtime_health: dict[str, Any] = {
        "initialized": bool(summary.get("runtime_initialized")),
        "bootstrap_state": bootstrap_state,
        "stale_leases": [],
    }

    runtime_error: str | None = None
    if summary.get("runtime_initialized"):
        try:
            state = load_lab_state(lab_root)
            workers = state.get("workers", {}).get("workers", {})
            now = datetime.now(timezone.utc).timestamp()
            stale_leases = []
            for job in state.get("jobs", {}).get("leased", []):
                worker_id = job.get("worker_id")
                worker = workers.get(worker_id, {})
                timeout_seconds = int(worker.get("lease_timeout_seconds", 1800) or 1800)
                leased_at = parse_iso_datetime(job.get("leased_at"))
                if leased_at is None:
                    continue
                age_seconds = int(max(0.0, now - leased_at.timestamp()))
                if age_seconds > timeout_seconds:
                    stale_leases.append(
                        {
                            "job_id": job.get("job_id"),
                            "candidate_id": job.get("candidate_id"),
                            "worker_id": worker_id,
                            "age_seconds": age_seconds,
                            "timeout_seconds": timeout_seconds,
                        }
                    )
            runtime_health.update(
                {
                    "queued_jobs": queued_job_count(state),
                    "leased_jobs": leased_job_count(state),
                    "worker_leases": active_worker_count(state),
                    "total_workers": len(workers),
                    "total_candidates": total_candidates(state),
                    "stale_leases": stale_leases,
                }
            )
        except Exception as exc:
            runtime_error = str(exc)

    status = "ready"
    next_action = "Lab looks healthy."

    if not python_ok:
        status = "degraded"
        next_action = "Use Python 3.10+ before running labrat."
    elif missing_scripts:
        status = "degraded"
        next_action = "Restore the missing lab scripts before continuing."
    elif bootstrap_state == "partial":
        status = "degraded"
        next_action = "Repair the partial `state/` directory before bootstrapping or resuming the lab."
    elif runtime_error:
        status = "degraded"
        next_action = "Inspect the malformed state files; labrat could not read the runtime state cleanly."
    elif missing_requirements:
        status = "needs_setup"
        next_action = "Install the lab requirements from `requirements.txt` in your active environment."
    elif summary["readiness_issues"]:
        status = "needs_setup"
        next_action = "Complete Phase 0 files, then rerun `check-readiness`."
    elif bootstrap_state == "missing":
        status = "needs_setup"
        next_action = "Run `python scripts/bootstrap.py` to initialize runtime state."
    elif runtime_health["stale_leases"]:
        status = "degraded"
        next_action = "Run `python scripts/runtime.py reap` to reclaim stale leases."

    return {
        "status": status,
        "next_action": next_action,
        "lab_root": str(lab_root),
        "python": {
            "version": ".".join(str(part) for part in sys.version_info[:3]),
            "ok": python_ok,
            "minimum": ".".join(str(part) for part in MIN_PYTHON),
        },
        "phase0": {
            "ready": bool(summary["ready"]),
            "issues": summary["readiness_issues"],
        },
        "files": {
            "dashboard_present": (lab_root / "dashboard.html").exists(),
            "requirements_present": requirements_path.exists(),
            "missing_scripts": missing_scripts,
        },
        "dependencies": {
            "requirements_file": str(requirements_path) if requirements_path.exists() else None,
            "checked": checked_requirements,
            "missing": missing_requirements,
            "skipped": skipped_requirements,
        },
        "runtime": runtime_health,
        "runtime_error": runtime_error,
        "summary": summary,
    }
