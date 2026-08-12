"""Fail-closed technology evidence registry for AURA.

The registry deliberately separates *hearing about* a technology from proving
that it works on this machine.  A technology can only move through the ladder

    DISCOVERED -> READ -> INSTALLED -> SMOKE_TESTED -> BENCHMARKED -> ADOPTED

when every step has a local, hash-locked artifact plus the command, exit code
and timestamps that produced it.  REJECTED is a terminal decision.  BLOCKED is
an evidenced pause: when the external condition changes it may reopen at READ
and must climb the ladder again rather than silently becoming "tested".

No function in this module installs packages or uses the network.  Probes are
executed without a shell and accept only the current Python interpreter or an
executable that lives inside the repository.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


SCHEMA_VERSION = 1
STATES = (
    "DISCOVERED",
    "READ",
    "INSTALLED",
    "SMOKE_TESTED",
    "BENCHMARKED",
    "ADOPTED",
    "REJECTED",
    "BLOCKED",
)
LADDER = (
    "DISCOVERED",
    "READ",
    "INSTALLED",
    "SMOKE_TESTED",
    "BENCHMARKED",
    "ADOPTED",
)
TERMINAL_STATES = {"ADOPTED", "REJECTED"}
EVIDENCE_KINDS = {
    "READ": "source_review",
    "INSTALLED": "install_check",
    "SMOKE_TESTED": "smoke_test",
    "BENCHMARKED": "benchmark",
    "ADOPTED": "decision",
    "REJECTED": "decision",
    "BLOCKED": "blocker",
}
PROBE_TARGETS = {
    "path_exists": {"READ", "INSTALLED"},
    "python_import": {"INSTALLED"},
    "local_command": {"READ", "INSTALLED", "SMOKE_TESTED", "BENCHMARKED"},
}


class TechEvidenceError(ValueError):
    """Raised when technology evidence is incomplete or inconsistent."""


@dataclass(frozen=True)
class ProbeResult:
    evidence: dict[str, Any]
    artifact_path: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )


def _require_non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TechEvidenceError(f"{label} must be a non-empty string")
    return value.strip()


def _require_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise TechEvidenceError(f"{label} must be a list of non-empty strings")
    if len(value) != len(set(value)):
        raise TechEvidenceError(f"{label} must not contain duplicates")
    return value


def _validate_timestamp(value: Any, label: str) -> datetime:
    text = _require_non_empty_string(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TechEvidenceError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise TechEvidenceError(f"{label} must include a timezone")
    return parsed


def _validate_url(value: str, label: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise TechEvidenceError(f"{label} must be an http(s) URL")


def _resolve_artifact(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute():
        raise TechEvidenceError("artifact_paths must be repository-relative")
    resolved_root = root.resolve()
    resolved = (resolved_root / rel).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise TechEvidenceError(f"artifact escapes repository: {relative}") from exc
    return resolved


def new_registry() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "technologies": []}


def new_technology(
    tech_id: str,
    name: str,
    category: str,
    *,
    discovered_at: str | None = None,
    claims: Sequence[Mapping[str, Any]] = (),
    probes: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    at = discovered_at or utc_now()
    return {
        "id": _require_non_empty_string(tech_id, "technology.id"),
        "name": _require_non_empty_string(name, "technology.name"),
        "category": _require_non_empty_string(category, "technology.category"),
        "state": "DISCOVERED",
        "claims": [deepcopy(dict(claim)) for claim in claims],
        "probes": [deepcopy(dict(probe)) for probe in probes],
        "evidence": [],
        "state_history": [{
            "state": "DISCOVERED",
            "at": at,
            "evidence_id": None,
        }],
    }


def load_registry(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise TechEvidenceError(f"registry not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TechEvidenceError(f"cannot read registry: {path}") from exc
    if not isinstance(value, dict):
        raise TechEvidenceError("registry must be a JSON object")
    return value


def save_registry(path: Path, registry: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _validate_claim(claim: Any, tech_id: str) -> None:
    if not isinstance(claim, Mapping):
        raise TechEvidenceError(f"{tech_id}.claim must be an object")
    expected = {"id", "text", "source_urls", "video_urls"}
    if set(claim) != expected:
        raise TechEvidenceError(
            f"{tech_id}.claim has missing/extra fields; expected {sorted(expected)}"
        )
    _require_non_empty_string(claim["id"], f"{tech_id}.claim.id")
    _require_non_empty_string(claim["text"], f"{tech_id}.claim.text")
    for field in ("source_urls", "video_urls"):
        urls = _require_string_list(claim[field], f"{tech_id}.claim.{field}")
        for index, url in enumerate(urls):
            _validate_url(url, f"{tech_id}.claim.{field}[{index}]")


def _validate_probe(probe: Any, tech_id: str) -> None:
    if not isinstance(probe, Mapping):
        raise TechEvidenceError(f"{tech_id}.probe must be an object")
    required = {"id", "kind", "proves_state", "summary"}
    if not required.issubset(probe):
        raise TechEvidenceError(f"{tech_id}.probe missing {sorted(required - set(probe))}")
    _require_non_empty_string(probe["id"], f"{tech_id}.probe.id")
    _require_non_empty_string(probe["summary"], f"{tech_id}.probe.summary")
    kind = probe["kind"]
    if kind not in {"path_exists", "python_import", "local_command"}:
        raise TechEvidenceError(f"{tech_id}.probe.kind is unsupported: {kind!r}")
    target = probe["proves_state"]
    if target not in EVIDENCE_KINDS:
        raise TechEvidenceError(f"{tech_id}.probe.proves_state is invalid")
    if target not in PROBE_TARGETS[kind]:
        raise TechEvidenceError(
            f"{tech_id}: {kind} cannot prove {target}; allowed={sorted(PROBE_TARGETS[kind])}"
        )
    if kind == "path_exists":
        _require_non_empty_string(probe.get("path"), f"{tech_id}.probe.path")
    elif kind == "python_import":
        _require_non_empty_string(probe.get("module"), f"{tech_id}.probe.module")
    else:
        argv = _require_string_list(probe.get("argv"), f"{tech_id}.probe.argv")
        if not argv:
            raise TechEvidenceError(f"{tech_id}.probe.argv cannot be empty")
        timeout_s = probe.get("timeout_s", 30)
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, int) or not 1 <= timeout_s <= 120:
            raise TechEvidenceError(f"{tech_id}.probe.timeout_s must be 1..120")


def _validate_evidence(evidence: Any, tech_id: str, root: Path) -> None:
    if not isinstance(evidence, Mapping):
        raise TechEvidenceError(f"{tech_id}.evidence must be an object")
    required = {
        "id", "kind", "proves_state", "summary", "command", "exit_code",
        "started_at", "finished_at", "duration_ms", "artifact_paths",
        "artifact_sha256", "stdout_sha256", "stderr_sha256",
    }
    if set(evidence) != required:
        missing = sorted(required - set(evidence))
        extra = sorted(set(evidence) - required)
        raise TechEvidenceError(
            f"{tech_id}.evidence has missing={missing} extra={extra}"
        )
    _require_non_empty_string(evidence["id"], f"{tech_id}.evidence.id")
    _require_non_empty_string(evidence["summary"], f"{tech_id}.evidence.summary")
    target = evidence["proves_state"]
    if target not in EVIDENCE_KINDS:
        raise TechEvidenceError(f"{tech_id}.evidence.proves_state is invalid")
    if evidence["kind"] != EVIDENCE_KINDS[target]:
        raise TechEvidenceError(
            f"{tech_id}.evidence.kind must be {EVIDENCE_KINDS[target]!r} for {target}"
        )
    command = _require_string_list(evidence["command"], f"{tech_id}.evidence.command")
    if not command:
        raise TechEvidenceError(f"{tech_id}.evidence.command cannot be empty")
    exit_code = evidence["exit_code"]
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise TechEvidenceError(f"{tech_id}.evidence.exit_code must be an integer")
    if target != "BLOCKED" and exit_code != 0:
        raise TechEvidenceError(
            f"{tech_id}: {target} requires a successful exit_code=0"
        )
    started = _validate_timestamp(evidence["started_at"], f"{tech_id}.evidence.started_at")
    finished = _validate_timestamp(evidence["finished_at"], f"{tech_id}.evidence.finished_at")
    if finished < started:
        raise TechEvidenceError(f"{tech_id}.evidence.finished_at precedes started_at")
    duration = evidence["duration_ms"]
    if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
        raise TechEvidenceError(f"{tech_id}.evidence.duration_ms must be >= 0")
    artifacts = _require_string_list(
        evidence["artifact_paths"], f"{tech_id}.evidence.artifact_paths"
    )
    if not artifacts:
        raise TechEvidenceError(f"{tech_id}.evidence.artifact_paths cannot be empty")
    hashes = evidence["artifact_sha256"]
    if not isinstance(hashes, Mapping) or set(hashes) != set(artifacts):
        raise TechEvidenceError(
            f"{tech_id}.evidence.artifact_sha256 must cover every artifact exactly"
        )
    for relative in artifacts:
        path = _resolve_artifact(root, relative)
        if not path.is_file():
            raise TechEvidenceError(f"{tech_id}.evidence artifact missing: {relative}")
        actual = sha256_file(path)
        if hashes[relative] != actual:
            raise TechEvidenceError(f"{tech_id}.evidence artifact hash mismatch: {relative}")
    for field in ("stdout_sha256", "stderr_sha256"):
        value = evidence[field]
        if not isinstance(value, str) or len(value) != 64 or any(
            char not in "0123456789abcdef" for char in value
        ):
            raise TechEvidenceError(f"{tech_id}.evidence.{field} must be SHA-256 hex")


def _allowed_next_states(current: str) -> set[str]:
    if current in TERMINAL_STATES:
        return set()
    if current == "BLOCKED":
        # A blocker can disappear (for example, the user later authorizes an
        # isolated install).  Re-enter at READ so fresh review, install and
        # smoke artifacts are all required; never jump straight to INSTALLED.
        return {"READ"}
    next_states: set[str] = {"REJECTED", "BLOCKED"} if current != "DISCOVERED" else set()
    next_states.add(LADDER[LADDER.index(current) + 1])
    return next_states


def validate_registry(registry: Mapping[str, Any], root: Path) -> None:
    if set(registry) != {"schema_version", "technologies"}:
        raise TechEvidenceError("registry must contain only schema_version and technologies")
    if registry["schema_version"] != SCHEMA_VERSION:
        raise TechEvidenceError(f"unsupported schema_version: {registry['schema_version']!r}")
    technologies = registry["technologies"]
    if not isinstance(technologies, list):
        raise TechEvidenceError("technologies must be a list")
    seen_ids: set[str] = set()
    for tech in technologies:
        if not isinstance(tech, Mapping):
            raise TechEvidenceError("technology must be an object")
        required = {
            "id", "name", "category", "state", "claims", "probes",
            "evidence", "state_history",
        }
        if set(tech) != required:
            raise TechEvidenceError(
                f"technology has missing={sorted(required - set(tech))} "
                f"extra={sorted(set(tech) - required)}"
            )
        tech_id = _require_non_empty_string(tech["id"], "technology.id")
        if tech_id in seen_ids:
            raise TechEvidenceError(f"duplicate technology id: {tech_id}")
        seen_ids.add(tech_id)
        _require_non_empty_string(tech["name"], f"{tech_id}.name")
        _require_non_empty_string(tech["category"], f"{tech_id}.category")
        if tech["state"] not in STATES:
            raise TechEvidenceError(f"{tech_id}.state is invalid: {tech['state']!r}")
        if not isinstance(tech["claims"], list):
            raise TechEvidenceError(f"{tech_id}.claims must be a list")
        for claim in tech["claims"]:
            _validate_claim(claim, tech_id)
        claim_ids = [claim["id"] for claim in tech["claims"]]
        if len(claim_ids) != len(set(claim_ids)):
            raise TechEvidenceError(f"{tech_id}.claim ids must be unique")
        if not isinstance(tech["probes"], list):
            raise TechEvidenceError(f"{tech_id}.probes must be a list")
        for probe in tech["probes"]:
            _validate_probe(probe, tech_id)
        probe_ids = [probe["id"] for probe in tech["probes"]]
        if len(probe_ids) != len(set(probe_ids)):
            raise TechEvidenceError(f"{tech_id}.probe ids must be unique")
        if not isinstance(tech["evidence"], list):
            raise TechEvidenceError(f"{tech_id}.evidence must be a list")
        evidence_by_id: dict[str, Mapping[str, Any]] = {}
        for item in tech["evidence"]:
            _validate_evidence(item, tech_id, root)
            if item["id"] in evidence_by_id:
                raise TechEvidenceError(f"{tech_id}.evidence ids must be unique")
            evidence_by_id[item["id"]] = item
        history = tech["state_history"]
        if not isinstance(history, list) or not history:
            raise TechEvidenceError(f"{tech_id}.state_history cannot be empty")
        expected_history_fields = {"state", "at", "evidence_id"}
        previous: str | None = None
        used_evidence: set[str] = set()
        for index, step in enumerate(history):
            if not isinstance(step, Mapping) or set(step) != expected_history_fields:
                raise TechEvidenceError(f"{tech_id}.state_history[{index}] is malformed")
            state = step["state"]
            if state not in STATES:
                raise TechEvidenceError(f"{tech_id}.state_history[{index}].state is invalid")
            _validate_timestamp(step["at"], f"{tech_id}.state_history[{index}].at")
            if index == 0:
                if state != "DISCOVERED" or step["evidence_id"] is not None:
                    raise TechEvidenceError(f"{tech_id} history must start at DISCOVERED")
            else:
                if state not in _allowed_next_states(previous or ""):
                    raise TechEvidenceError(
                        f"{tech_id} cannot transition from {previous} to {state}"
                    )
                evidence_id = _require_non_empty_string(
                    step["evidence_id"], f"{tech_id}.state_history[{index}].evidence_id"
                )
                if evidence_id in used_evidence:
                    raise TechEvidenceError(f"{tech_id} reuses evidence {evidence_id}")
                item = evidence_by_id.get(evidence_id)
                if item is None or item["proves_state"] != state:
                    raise TechEvidenceError(
                        f"{tech_id} transition to {state} lacks matching evidence"
                    )
                used_evidence.add(evidence_id)
            previous = state
        if history[-1]["state"] != tech["state"]:
            raise TechEvidenceError(f"{tech_id}.state does not match state_history")
        if set(evidence_by_id) != used_evidence:
            raise TechEvidenceError(f"{tech_id} has unattached evidence")


def find_technology(registry: Mapping[str, Any], tech_id: str) -> dict[str, Any]:
    for tech in registry.get("technologies", []):
        if tech.get("id") == tech_id:
            return tech
    raise TechEvidenceError(f"unknown technology: {tech_id}")


def promote_technology(
    registry: dict[str, Any],
    tech_id: str,
    target_state: str,
    evidence: Mapping[str, Any],
    root: Path,
) -> None:
    tech = find_technology(registry, tech_id)
    current = tech["state"]
    if target_state not in _allowed_next_states(current):
        raise TechEvidenceError(f"cannot transition {tech_id} from {current} to {target_state}")
    item = deepcopy(dict(evidence))
    if item.get("proves_state") != target_state:
        raise TechEvidenceError("evidence.proves_state does not match target state")
    _validate_evidence(item, tech_id, root)
    if any(old["id"] == item["id"] for old in tech["evidence"]):
        raise TechEvidenceError(f"duplicate evidence id: {item['id']}")
    tech["evidence"].append(item)
    tech["state"] = target_state
    tech["state_history"].append({
        "state": target_state,
        "at": item["finished_at"],
        "evidence_id": item["id"],
    })
    validate_registry(registry, root)


def _safe_executable(root: Path, executable: str) -> str:
    candidate = Path(executable)
    resolved_python = Path(sys.executable).resolve()
    if candidate.resolve() == resolved_python:
        return str(resolved_python)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise TechEvidenceError(
            "local_command executable must be sys.executable or live inside repository"
        ) from exc
    if not resolved.is_file():
        raise TechEvidenceError(f"probe executable not found: {resolved}")
    return str(resolved)


def _run_probe_command(root: Path, probe: Mapping[str, Any]) -> tuple[list[str], int, str, str]:
    kind = probe["kind"]
    if kind == "path_exists":
        relative = _require_non_empty_string(probe["path"], "probe.path")
        path = _resolve_artifact(root, relative)
        command = ["internal:path_exists", relative]
        return command, 0 if path.exists() else 1, str(path), ""
    if kind == "python_import":
        module = _require_non_empty_string(probe["module"], "probe.module")
        command = ["internal:python_import", module]
        spec = importlib.util.find_spec(module)
        return command, 0 if spec is not None else 1, str(spec.origin if spec else ""), ""
    argv = list(probe["argv"])
    argv[0] = _safe_executable(root, argv[0])
    if any("http://" in token.lower() or "https://" in token.lower() for token in argv):
        raise TechEvidenceError("network URLs are forbidden in local_command probes")
    lowered = [token.lower() for token in argv]
    if "pip" in lowered or "install" in lowered or "uninstall" in lowered:
        raise TechEvidenceError("package installation is forbidden in probes")
    cwd_text = probe.get("cwd", ".")
    cwd = _resolve_artifact(root, cwd_text)
    if not cwd.is_dir():
        raise TechEvidenceError(f"probe cwd is not a directory: {cwd_text}")
    # Keep the probe environment small, but do not remove Windows variables
    # required by Python's stdlib (notably ``asyncio._overlapped``) or by local
    # model caches.  Omitting SYSTEMROOT/WINDIR made an installed Docling fail
    # with WinError 10106, which was a broken probe rather than evidence that
    # Docling itself was broken.
    probe_env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
    }
    # 11/08/2026: OLLAMA_MODELS belongs to the "local model caches" case the
    # comment above already anticipates.  The models were moved to F: that
    # morning; without this variable the AirLLM disk-ceiling probe searched
    # only ~/.ollama, found nothing, and exited 1 — a broken probe reported as
    # a failed measurement, exactly the Docling/WinError mistake repeating.
    for name in (
        "SYSTEMROOT", "WINDIR", "USERPROFILE", "LOCALAPPDATA", "APPDATA",
        "TEMP", "TMP", "OLLAMA_MODELS", "OLLAMA_HOST",
    ):
        value = os.environ.get(name)
        if value:
            probe_env[name] = value
    completed = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=probe.get("timeout_s", 30),
        shell=False,
        env=probe_env,
    )
    return argv, completed.returncode, completed.stdout, completed.stderr


def run_probe(
    root: Path,
    tech: Mapping[str, Any],
    probe: Mapping[str, Any],
    *,
    artifacts_dir: Path | None = None,
) -> ProbeResult:
    """Run one offline probe and return hash-locked evidence.

    Failed probes still produce an artifact, but evidence for a progressive
    state will be rejected by :func:`promote_technology` because exit_code is
    non-zero.  This prevents "attempted" from becoming "tested".
    """
    _validate_probe(probe, str(tech.get("id", "technology")))
    started_at = utc_now()
    start = time.perf_counter()
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    try:
        command, exit_code, stdout, stderr = _run_probe_command(root, probe)
    except subprocess.TimeoutExpired as exc:
        command = list(probe.get("argv", [f"internal:{probe['kind']}"]))
        exit_code = 124
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = "probe timed out"
    finished_at = utc_now()
    duration_ms = max(0, round((time.perf_counter() - start) * 1000))
    safe_tech = "".join(char if char.isalnum() or char in "-_" else "_" for char in tech["id"])
    safe_probe = "".join(char if char.isalnum() or char in "-_" else "_" for char in probe["id"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = artifacts_dir or root / "data" / "tech_evidence" / "artifacts"
    artifact = base / safe_tech / f"{stamp}-{safe_probe}.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "technology_id": tech["id"],
        "probe_id": probe["id"],
        "probe_kind": probe["kind"],
        "network": False,
        "command": command,
        "exit_code": exit_code,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "stdout": stdout[:32768],
        "stderr": stderr[:32768],
    }
    artifact.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    relative = artifact.resolve().relative_to(root.resolve()).as_posix()
    evidence = {
        "id": f"{safe_tech}-{safe_probe}-{stamp}",
        "kind": EVIDENCE_KINDS[probe["proves_state"]],
        "proves_state": probe["proves_state"],
        "summary": probe["summary"],
        "command": command,
        "exit_code": exit_code,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "artifact_paths": [relative],
        "artifact_sha256": {relative: sha256_file(artifact)},
        "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
    }
    return ProbeResult(evidence=evidence, artifact_path=artifact)


def build_report(registry: Mapping[str, Any], root: Path) -> dict[str, Any]:
    issues: list[str] = []
    try:
        validate_registry(registry, root)
    except TechEvidenceError as exc:
        issues.append(str(exc))
    technologies = registry.get("technologies", [])
    if not isinstance(technologies, list):
        technologies = []
    counts = Counter(
        tech.get("state", "INVALID") for tech in technologies if isinstance(tech, Mapping)
    )
    items: list[dict[str, Any]] = []
    for tech in technologies:
        if not isinstance(tech, Mapping):
            continue
        source_urls = sorted({
            url
            for claim in tech.get("claims", []) if isinstance(claim, Mapping)
            for url in claim.get("source_urls", [])
        })
        video_urls = sorted({
            url
            for claim in tech.get("claims", []) if isinstance(claim, Mapping)
            for url in claim.get("video_urls", [])
        })
        history = tech.get("state_history", [])
        items.append({
            "id": tech.get("id"),
            "name": tech.get("name"),
            "category": tech.get("category"),
            "state": tech.get("state"),
            "claim_count": len(tech.get("claims", [])),
            "evidence_count": len(tech.get("evidence", [])),
            "source_urls": source_urls,
            "video_urls": video_urls,
            "last_verified_at": history[-1].get("at") if history else None,
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "valid": not issues,
        "issues": issues,
        "summary": {"total": len(items), "by_state": dict(sorted(counts.items()))},
        "technologies": items,
    }


def report_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# AURA Technology Evidence Report",
        "",
        f"Generated: `{report['generated_at']}`  ",
        f"Registry valid: **{'YES' if report['valid'] else 'NO'}**",
        "",
        "A technology is not considered tested until it reaches `SMOKE_TESTED`",
        "with a successful command and a hash-locked local artifact.",
        "",
    ]
    if report["issues"]:
        lines.extend(["## Validation issues", ""])
        lines.extend(f"- {issue}" for issue in report["issues"])
        lines.append("")
    lines.extend([
        "## Inventory",
        "",
        "| Technology | State | Claims | Evidence | Last verified | Sources |",
        "|---|---:|---:|---:|---|---:|",
    ])
    for item in report["technologies"]:
        source_count = len(item["source_urls"]) + len(item["video_urls"])
        lines.append(
            f"| {item['name']} (`{item['id']}`) | {item['state']} | "
            f"{item['claim_count']} | {item['evidence_count']} | "
            f"{item['last_verified_at'] or '-'} | {source_count} |"
        )
    if not report["technologies"]:
        lines.append("| _No technologies registered_ | - | 0 | 0 | - | 0 |")
    lines.extend(["", "## Counts by state", ""])
    for state in STATES:
        lines.append(f"- `{state}`: {report['summary']['by_state'].get(state, 0)}")
    return "\n".join(lines) + "\n"


def write_reports(
    registry: Mapping[str, Any],
    root: Path,
    json_path: Path,
    markdown_path: Path,
) -> dict[str, Any]:
    report = build_report(registry, root)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(report_markdown(report), encoding="utf-8")
    return report
