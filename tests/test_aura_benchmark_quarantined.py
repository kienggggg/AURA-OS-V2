from __future__ import annotations

import ast
import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.aura_benchmark import AuraBenchmarkSuite, InvalidBenchmarkError


ROOT = Path(__file__).resolve().parents[1]
INCIDENT = ROOT / "docs" / "incidents" / "2026-08-08-fake-aura-benchmark"
ORIGINAL = INCIDENT / "aura_benchmark_original.py.txt"
SCHEMA = ROOT / "docs" / "aura_coding_arena_contract.schema.json"
EXPECTED_ORIGINAL_SHA256 = "f3bb303e2fb98efec7b140f63280a8d29108e8c509a544d5121afaa11b91e346"


@pytest.mark.parametrize(
    "method",
    [
        "evaluate_ifeval",
        "evaluate_swe_bench_coding",
        "evaluate_technical_performance",
        "run_full_benchmark",
    ],
)
def test_legacy_benchmark_api_fails_closed(method):
    suite = object.__new__(AuraBenchmarkSuite)
    with pytest.raises(InvalidBenchmarkError, match="not measured"):
        getattr(suite, method)()


def test_legacy_benchmark_fails_during_initialization_and_dynamic_import():
    with pytest.raises(InvalidBenchmarkError, match="not measured"):
        AuraBenchmarkSuite()
    module = importlib.import_module("core.aura_benchmark")
    with pytest.raises(InvalidBenchmarkError, match="not measured"):
        module.AuraBenchmarkSuite()


def test_running_quarantined_module_exits_nonzero_without_result_payload():
    run = subprocess.run(
        [sys.executable, str(ROOT / "core" / "aura_benchmark.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )
    assert run.returncode == 2
    assert run.stdout == ""
    assert "INVALID BENCHMARK" in run.stderr
    assert "elo_rating" not in run.stderr
    assert "win_rate" not in run.stderr


def test_archived_source_matches_pre_quarantine_hash():
    raw = ORIGINAL.read_bytes()
    first_line, payload = raw.splitlines(keepends=True)[0], raw[len(raw.splitlines(keepends=True)[0]):]
    assert first_line.rstrip(b"\r\n") == b"QUARANTINED_EVIDENCE_DO_NOT_EXECUTE ="
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_ORIGINAL_SHA256


def test_archived_source_is_not_executable_python():
    with pytest.raises(SyntaxError):
        compile(ORIGINAL.read_text(encoding="utf-8"), str(ORIGINAL), "exec")


def test_no_runtime_module_imports_quarantined_benchmark():
    roots = ["core", "ui", "factory", "skills", "brains", "scripts"]
    offenders: list[str] = []
    for directory in roots:
        for path in (ROOT / directory).rglob("*.py"):
            if path == ROOT / "core" / "aura_benchmark.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    if any(alias.name in {"aura_benchmark", "core.aura_benchmark"} for alias in node.names):
                        offenders.append(str(path.relative_to(ROOT)))
                elif isinstance(node, ast.ImportFrom):
                    if node.module in {"aura_benchmark", "core.aura_benchmark"}:
                        offenders.append(str(path.relative_to(ROOT)))
                elif isinstance(node, ast.Call):
                    literal_args = [
                        arg.value for arg in node.args
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                    ]
                    if "core.aura_benchmark" in literal_args or "aura_benchmark" in literal_args:
                        offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_arena_schema_closes_critical_trust_boundaries():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    definitions = schema["$defs"]
    assert set(definitions) >= {
        "pre_registration", "task", "episode", "result", "lesson",
        "approval", "promotion",
    }

    prereg = definitions["pre_registration"]
    assert {"threshold_p", "manifest_sha", "registration_signature"} <= set(prereg["required"])

    task = definitions["task"]
    assert task["additionalProperties"] is False
    assert task["properties"]["network"] == {"const": False}
    assert {"task_manifest_sha", "files_allowed", "forbidden_paths"} <= set(task["required"])

    episode = definitions["episode"]
    assert {
        "tokens_reported_by_participant", "prompt_chars_measured_by_evaluator",
        "reply_chars_measured_by_evaluator", "model_calls", "human_touches",
        "prompt_sha", "episode_signature",
    } <= set(episode["required"])
    assert "tokens_metered_by_evaluator" not in episode["required"]
    model_call = definitions["model_call"]
    assert model_call["additionalProperties"] is False
    assert {
        "declared_history_free", "declared_tools_enabled",
        "declared_recall_enabled", "prompt_sha", "reply_sha",
    } == set(model_call["required"])
    assert episode["properties"]["actor"] == {"enum": ["aura", "baseline"]}
    assert episode["properties"]["run_kind"] == {"enum": ["arena", "reproduction"]}

    result = definitions["result"]
    assert {"evaluator_version", "environment_fingerprint", "result_signature"} <= set(result["required"])

    lesson = definitions["lesson"]
    assert {"evidence_run_ids", "evidence_patch_sha", "held_out_run_ids"} <= set(lesson["required"])

    promotion = definitions["promotion"]
    assert promotion["properties"]["approved_by"] == {"const": "Sếp"}
    assert promotion["properties"]["arena_batches"]["minItems"] == 2
    assert promotion["properties"]["repro_runs"]["minItems"] == 2
    approval = definitions["approval"]
    assert approval["properties"]["approved_by"] == {"const": "Sếp"}
    assert approval["properties"]["channel"] == {"const": "telegram"}
    assert {
        "telegram_message_id", "telegram_chat_id", "from_user_id",
        "reply_to_message_id",
    } <= set(approval["required"])
    assert "approval_signature" not in approval["properties"]
