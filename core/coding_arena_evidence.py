"""Fail-closed semantic validation for AURA Coding Arena evidence.

JSON Schema validates record shape.  This module validates relationships and
authenticity: evaluator-owned records are HMAC signed, paired statistics are
recomputed, manifests are derived from tasks, and promotion references must
resolve to signed evidence.

The signing secret is deliberately an explicit argument.  It must be supplied
by the trusted evaluator from outside the coder workspace; this module never
reads it from the environment, a file, or ``.env``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
from collections import defaultdict
from copy import deepcopy
from typing import Any, Callable, Iterable, Mapping


class EvidenceValidationError(ValueError):
    """Raised when arena evidence is malformed, forged, or inconsistent."""


SIGNATURE_FIELDS = {
    "pre_registration": "registration_signature",
    "episode": "episode_signature",
    "result": "result_signature",
    "promotion": "promotion_signature",
}

REQUIRED_FIELDS = {
    "pre_registration": {
        "record_type", "batch_id", "n_tasks", "threshold_p",
        "hypothesis_direction", "registered_at", "manifest_sha",
        "registration_signature",
    },
    "task": {
        "record_type", "id", "batch_id", "repo_hash", "task_manifest_sha",
        "failing_test", "files_allowed", "forbidden_paths", "budget_s",
        "requested_max_output_tokens", "budget_prompt_chars",
        "budget_reply_chars", "network",
    },
    "episode": {
        "record_type", "task_id", "run_id", "run_kind", "actor",
        "declared_model_id",
        "model_calls", "prompt_sha", "patch_sha", "stdout_sha", "stderr_sha",
        "tests_before", "tests_after", "elapsed_s_measured_by_evaluator",
        "tokens_reported_by_participant", "prompt_chars_measured_by_evaluator",
        "reply_chars_measured_by_evaluator", "reply_char_limit",
        "attempts", "human_touches",
        "exit_reason", "episode_signature",
    },
    "result": {
        "record_type", "task_id", "run_id", "evaluator_version",
        "environment_fingerprint", "hidden_pass", "hidden_total",
        "red_test_pass", "regression_pass", "safety_flags", "result_signature",
    },
    "lesson": {
        "record_type", "id", "failure_signature", "content",
        "evidence_run_ids", "evidence_patch_sha", "held_out_run_ids", "status",
    },
    "approval": {
        "record_type", "id", "champion_before", "candidate", "vibe_diff_sha",
        "decision", "approved_by", "approved_at", "channel",
        "telegram_message_id", "telegram_chat_id", "from_user_id",
        "reply_to_message_id",
    },
    "promotion": {
        "record_type", "champion_before", "candidate", "arena_batches",
        "paired_results", "exact_p", "repro_runs", "approval_id",
        "approved_by", "rollback_ref", "promotion_signature",
    },
}

MODEL_CALL_FIELDS = {
    "prompt_sha", "reply_sha", "declared_history_free",
    "declared_tools_enabled", "declared_recall_enabled",
}

SHA_FIELDS = {
    "manifest_sha", "repo_hash", "task_manifest_sha", "patch_sha",
    "stdout_sha", "stderr_sha", "environment_fingerprint",
    "failure_signature", "vibe_diff_sha",
    *SIGNATURE_FIELDS.values(),
}


def _fail(message: str) -> None:
    raise EvidenceValidationError(message)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _secret_bytes(secret: bytes | bytearray) -> bytes:
    if not isinstance(secret, (bytes, bytearray)) or len(secret) < 32:
        _fail("evaluator HMAC secret must be at least 32 bytes")
    return bytes(secret)


def _unsigned_record(record: Mapping[str, Any]) -> dict[str, Any]:
    record_type = record.get("record_type")
    signature_field = SIGNATURE_FIELDS.get(record_type)
    if signature_field is None:
        _fail(f"record type {record_type!r} is not signed")
    unsigned = deepcopy(dict(record))
    unsigned.pop(signature_field, None)
    return unsigned


def sign_record(record: Mapping[str, Any], secret: bytes | bytearray) -> dict[str, Any]:
    """Return a signed copy of an evaluator-owned evidence record."""
    secret_bytes = _secret_bytes(secret)
    signed = deepcopy(dict(record))
    record_type = signed.get("record_type")
    signature_field = SIGNATURE_FIELDS.get(record_type)
    if signature_field is None:
        _fail(f"record type {record_type!r} is not signed")
    signed.pop(signature_field, None)
    signed[signature_field] = hmac.new(
        secret_bytes, _canonical_bytes(signed), hashlib.sha256,
    ).hexdigest()
    return signed


def verify_record_signature(
    record: Mapping[str, Any], secret: bytes | bytearray,
) -> None:
    """Raise if a signed record was not produced by the trusted evaluator."""
    secret_bytes = _secret_bytes(secret)
    record_type = record.get("record_type")
    signature_field = SIGNATURE_FIELDS.get(record_type)
    if signature_field is None:
        _fail(f"record type {record_type!r} is not signed")
    actual = record.get(signature_field)
    if not isinstance(actual, str):
        _fail(f"missing {signature_field}")
    expected = hmac.new(
        secret_bytes, _canonical_bytes(_unsigned_record(record)), hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(actual, expected):
        _fail(f"invalid {signature_field}")


def exact_binomial_one_sided(aura_only: int, model_only: int) -> float:
    """Exact one-sided paired-test p-value under p=0.5 (AURA is better)."""
    if not isinstance(aura_only, int) or not isinstance(model_only, int):
        _fail("paired counts must be integers")
    if aura_only < 0 or model_only < 0:
        _fail("paired counts cannot be negative")
    discordant = aura_only + model_only
    if discordant == 0:
        return 1.0
    return sum(
        math.comb(discordant, wins)
        for wins in range(aura_only, discordant + 1)
    ) / (2 ** discordant)


def compute_task_manifest_sha(tasks: Iterable[Mapping[str, Any]]) -> str:
    """Hash task definitions without their circular manifest field."""
    normalized: list[dict[str, Any]] = []
    for task in tasks:
        item = deepcopy(dict(task))
        item.pop("task_manifest_sha", None)
        normalized.append(item)
    normalized.sort(key=lambda item: str(item.get("id", "")))
    return hashlib.sha256(_canonical_bytes(normalized)).hexdigest()


def _require_string(record: Mapping[str, Any], field: str) -> None:
    if not isinstance(record.get(field), str) or not record[field]:
        _fail(f"{record.get('record_type')}.{field} must be a non-empty string")


def _require_int(record: Mapping[str, Any], field: str, minimum: int = 0) -> None:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{record.get('record_type')}.{field} must be an integer >= {minimum}")


def _require_unique_strings(
    record: Mapping[str, Any], field: str, minimum: int = 0,
) -> None:
    value = record.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        _fail(f"{record.get('record_type')}.{field} must be a list of non-empty strings")
    if len(value) < minimum:
        _fail(f"{record.get('record_type')}.{field} must contain at least {minimum} items")
    if len(value) != len(set(value)):
        _fail(f"{record.get('record_type')}.{field} must not contain duplicates")


def _validate_paired_counts(counts: Any) -> None:
    fields = {"both_pass", "aura_only_pass", "model_only_pass", "both_fail"}
    if not isinstance(counts, dict) or set(counts) != fields:
        _fail("paired_counts has missing or extra fields")
    for field in fields:
        if isinstance(counts[field], bool) or not isinstance(counts[field], int) or counts[field] < 0:
            _fail(f"paired_counts.{field} must be a non-negative integer")


def validate_record(
    record: Mapping[str, Any], secret: bytes | bytearray | None = None,
) -> None:
    """Validate one record's exact shape, semantics, and signature."""
    if not isinstance(record, Mapping):
        _fail("record must be an object")
    record_type = record.get("record_type")
    required = REQUIRED_FIELDS.get(record_type)
    if required is None:
        _fail(f"unknown record_type {record_type!r}")
    if set(record) != required:
        missing = sorted(required - set(record))
        extra = sorted(set(record) - required)
        _fail(f"{record_type} has missing={missing} extra={extra}")

    for field in required & SHA_FIELDS:
        value = record[field]
        if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            _fail(f"{record_type}.{field} must be lowercase SHA-256 hex")

    if record_type in SIGNATURE_FIELDS:
        if secret is None:
            _fail(f"trusted secret required for {record_type}")
        verify_record_signature(record, secret)

    if record_type == "pre_registration":
        for field in ("batch_id", "registered_at"):
            _require_string(record, field)
        _require_int(record, "n_tasks", 1)
        threshold = record["threshold_p"]
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 < threshold <= 0.05:
            _fail("pre_registration.threshold_p must be in (0, 0.05]")
        if record["hypothesis_direction"] != "aura_better":
            _fail("only the preregistered aura_better hypothesis is accepted")

    elif record_type == "task":
        for field in ("id", "batch_id", "failing_test"):
            _require_string(record, field)
        for field in ("files_allowed", "forbidden_paths"):
            _require_unique_strings(record, field, 1)
        _require_int(record, "budget_s", 1)
        _require_int(record, "requested_max_output_tokens", 1)
        _require_int(record, "budget_prompt_chars", 1)
        _require_int(record, "budget_reply_chars", 1)
        if record["network"] is not False:
            _fail("task.network must be false")

    elif record_type == "episode":
        for field in ("task_id", "run_id", "declared_model_id", "exit_reason"):
            _require_string(record, field)
        if record["actor"] not in {"aura", "baseline"}:
            _fail("episode.actor must be 'aura' or 'baseline'")
        if record["run_kind"] not in {"arena", "reproduction"}:
            _fail("episode.run_kind must be 'arena' or 'reproduction'")
        if (
            not isinstance(record["model_calls"], list)
            or not record["model_calls"]
            or any(not isinstance(x, dict) for x in record["model_calls"])
        ):
            _fail("episode.model_calls must be a non-empty list of objects")
        for index, model_call in enumerate(record["model_calls"]):
            if set(model_call) != MODEL_CALL_FIELDS:
                _fail(f"episode.model_calls[{index}] has misleading or incomplete fields")
            for field in ("prompt_sha", "reply_sha"):
                value = model_call[field]
                if (
                    not isinstance(value, str)
                    or len(value) != 64
                    or any(ch not in "0123456789abcdef" for ch in value)
                ):
                    _fail(f"episode.model_calls[{index}].{field} must be SHA-256 hex")
            for field in (
                "declared_history_free", "declared_tools_enabled",
                "declared_recall_enabled",
            ):
                if not isinstance(model_call[field], bool):
                    _fail(f"episode.model_calls[{index}].{field} must be boolean")
        if not isinstance(record["tests_before"], dict) or not isinstance(record["tests_after"], dict):
            _fail("episode test measurements must be objects")
        elapsed = record["elapsed_s_measured_by_evaluator"]
        if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or elapsed < 0:
            _fail("episode.elapsed_s_measured_by_evaluator must be non-negative")
        for field, minimum in (
            ("tokens_reported_by_participant", 0),
            ("prompt_chars_measured_by_evaluator", 0),
            ("reply_chars_measured_by_evaluator", 0),
            ("reply_char_limit", 1),
            ("attempts", 1),
            ("human_touches", 0),
        ):
            _require_int(record, field, minimum)
        if record["attempts"] != len(record["model_calls"]):
            _fail("episode.attempts must equal len(model_calls)")
        if any(call["prompt_sha"] != record["prompt_sha"] for call in record["model_calls"]):
            _fail("episode model call prompt SHA must match episode.prompt_sha")

    elif record_type == "result":
        for field in ("task_id", "run_id", "evaluator_version"):
            _require_string(record, field)
        _require_int(record, "hidden_pass", 0)
        _require_int(record, "hidden_total", 1)
        if record["hidden_pass"] > record["hidden_total"]:
            _fail("result.hidden_pass cannot exceed hidden_total")
        if not isinstance(record["red_test_pass"], bool):
            _fail("result.red_test_pass must be boolean")
        if record["regression_pass"] is not None and not isinstance(record["regression_pass"], bool):
            _fail("result.regression_pass must be boolean or null")
        _require_unique_strings(record, "safety_flags", 0)

    elif record_type == "lesson":
        for field in ("id", "content"):
            _require_string(record, field)
        for field in ("evidence_run_ids", "evidence_patch_sha", "held_out_run_ids"):
            _require_unique_strings(record, field, 1)
        if set(record["evidence_run_ids"]) & set(record["held_out_run_ids"]):
            _fail("lesson evidence and held-out run IDs must be disjoint")
        if record["status"] not in {"candidate", "rejected", "promoted"}:
            _fail("invalid lesson.status")

    elif record_type == "approval":
        for field in ("id", "champion_before", "candidate", "approved_at"):
            _require_string(record, field)
        if record["decision"] != "approve" or record["approved_by"] != "Sếp":
            _fail("approval must be an explicit decision by Sếp")
        if record["channel"] != "telegram":
            _fail("approval must come from the Telegram human channel")
        for field in ("telegram_message_id", "from_user_id", "reply_to_message_id"):
            _require_int(record, field, 1)
        chat_id = record["telegram_chat_id"]
        if isinstance(chat_id, bool) or not isinstance(chat_id, int) or chat_id == 0:
            _fail("approval.telegram_chat_id must be a non-zero integer")

    elif record_type == "promotion":
        for field in ("champion_before", "candidate", "approval_id", "rollback_ref"):
            _require_string(record, field)
        _require_unique_strings(record, "arena_batches", 2)
        _require_unique_strings(record, "repro_runs", 2)
        if record["approved_by"] != "Sếp":
            _fail("promotion requires Sếp approval")
        paired_results = record["paired_results"]
        if not isinstance(paired_results, list) or len(paired_results) < 2:
            _fail("promotion requires at least two paired results")
        paired_ids: list[str] = []
        aura_only = model_only = 0
        for paired in paired_results:
            if not isinstance(paired, dict) or set(paired) != {"batch_id", "paired_counts"}:
                _fail("invalid paired_result")
            if not isinstance(paired["batch_id"], str) or not paired["batch_id"]:
                _fail("paired_result.batch_id must be non-empty")
            _validate_paired_counts(paired["paired_counts"])
            counts = paired["paired_counts"]
            if counts["aura_only_pass"] <= counts["model_only_pass"]:
                _fail("AURA must beat the baseline in every promoted batch")
            paired_ids.append(paired["batch_id"])
            aura_only += counts["aura_only_pass"]
            model_only += counts["model_only_pass"]
        if len(paired_ids) != len(set(paired_ids)) or set(paired_ids) != set(record["arena_batches"]):
            _fail("paired_results must map one-to-one to arena_batches")
        exact_p = record["exact_p"]
        if isinstance(exact_p, bool) or not isinstance(exact_p, (int, float)):
            _fail("promotion.exact_p must be numeric")
        recomputed = exact_binomial_one_sided(aura_only, model_only)
        if not math.isclose(float(exact_p), recomputed, rel_tol=0.0, abs_tol=1e-12):
            _fail(f"promotion.exact_p mismatch: stored={exact_p}, recomputed={recomputed}")


def _result_passes(result: Mapping[str, Any]) -> bool:
    return (
        result["hidden_pass"] == result["hidden_total"]
        and result["red_test_pass"] is True
        and result["regression_pass"] is True
        and not result["safety_flags"]
    )


def _derived_paired_counts(
    tasks: list[Mapping[str, Any]],
    episodes_by_run: Mapping[str, Mapping[str, Any]],
    results_by_run: Mapping[str, Mapping[str, Any]],
) -> dict[str, int]:
    counts = {"both_pass": 0, "aura_only_pass": 0, "model_only_pass": 0, "both_fail": 0}
    runs_by_task_actor: dict[tuple[str, str], list[str]] = defaultdict(list)
    for run_id, episode in episodes_by_run.items():
        if run_id in results_by_run and episode["run_kind"] == "arena":
            runs_by_task_actor[(episode["task_id"], episode["actor"])].append(run_id)
    for task in tasks:
        outcomes: dict[str, bool] = {}
        for actor in ("aura", "baseline"):
            run_ids = runs_by_task_actor.get((task["id"], actor), [])
            if len(run_ids) != 1:
                _fail(f"task {task['id']} requires exactly one signed result for actor {actor}")
            outcomes[actor] = _result_passes(results_by_run[run_ids[0]])
        if outcomes["aura"] and outcomes["baseline"]:
            counts["both_pass"] += 1
        elif outcomes["aura"]:
            counts["aura_only_pass"] += 1
        elif outcomes["baseline"]:
            counts["model_only_pass"] += 1
        else:
            counts["both_fail"] += 1
    return counts


def validate_evidence_bundle(
    records: Iterable[Mapping[str, Any]], secret: bytes | bytearray,
    human_approval_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
    participant_isolation_verifier: Callable[[Mapping[str, Any]], bool] | None = None,
) -> None:
    """Validate cross-record provenance and promotion eligibility."""
    records_list = [dict(record) for record in records]
    for record in records_list:
        validate_record(record, secret if record.get("record_type") in SIGNATURE_FIELDS else None)

    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records_list:
        by_type[record["record_type"]].append(record)

    def unique_index(record_type: str, key: str) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for record in by_type[record_type]:
            value = record[key]
            if value in index:
                _fail(f"duplicate {record_type}.{key}: {value}")
            index[value] = record
        return index

    prereg_by_batch = unique_index("pre_registration", "batch_id")
    task_by_id = unique_index("task", "id")
    episode_by_run = unique_index("episode", "run_id")
    result_by_run = unique_index("result", "run_id")
    approval_by_id = unique_index("approval", "id")

    tasks_by_batch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in by_type["task"]:
        tasks_by_batch[task["batch_id"]].append(task)
    for batch_id, prereg in prereg_by_batch.items():
        tasks = tasks_by_batch.get(batch_id, [])
        if len(tasks) != prereg["n_tasks"]:
            _fail(f"batch {batch_id} task count does not match preregistration")
        manifest = compute_task_manifest_sha(tasks)
        if prereg["manifest_sha"] != manifest:
            _fail(f"batch {batch_id} preregistered manifest mismatch")
        if any(task["task_manifest_sha"] != manifest for task in tasks):
            _fail(f"batch {batch_id} task manifest mismatch")
    if set(tasks_by_batch) - set(prereg_by_batch):
        _fail("every task batch must have a signed preregistration")

    for run_id, episode in episode_by_run.items():
        if episode["task_id"] not in task_by_id:
            _fail(f"episode {run_id} refers to unknown task")
        task = task_by_id[episode["task_id"]]
        if episode["prompt_chars_measured_by_evaluator"] > task["budget_prompt_chars"]:
            _fail(f"episode {run_id} exceeds prompt character budget")
        if episode["reply_chars_measured_by_evaluator"] > task["budget_reply_chars"]:
            _fail(f"episode {run_id} exceeds reply character budget")
    arena_prompt_shas: dict[str, set[str]] = defaultdict(set)
    for episode in episode_by_run.values():
        if episode["run_kind"] == "arena":
            arena_prompt_shas[episode["task_id"]].add(episode["prompt_sha"])
    if any(len(prompt_shas) != 1 for prompt_shas in arena_prompt_shas.values()):
        _fail("paired arena actors must receive the same prompt SHA")
    for run_id, result in result_by_run.items():
        episode = episode_by_run.get(run_id)
        if episode is None or result["task_id"] != episode["task_id"]:
            _fail(f"result {run_id} does not match a signed episode")

    for lesson in by_type["lesson"]:
        all_runs = lesson["evidence_run_ids"] + lesson["held_out_run_ids"]
        if any(run_id not in result_by_run for run_id in all_runs):
            _fail(f"lesson {lesson['id']} refers to an unknown result")
        evidence_patches = {episode_by_run[run_id]["patch_sha"] for run_id in lesson["evidence_run_ids"]}
        if set(lesson["evidence_patch_sha"]) != evidence_patches:
            _fail(f"lesson {lesson['id']} patch provenance mismatch")

    for promotion in by_type["promotion"]:
        approval = approval_by_id.get(promotion["approval_id"])
        if approval is None:
            _fail("promotion lacks human approval")
        if human_approval_verifier is None:
            _fail("promotion requires an independent human approval verifier")
        try:
            human_verified = human_approval_verifier(approval)
        except Exception as exc:
            raise EvidenceValidationError("human approval verification failed") from exc
        if human_verified is not True:
            _fail("Telegram approval was not verified as a real message from Sếp")
        if participant_isolation_verifier is None:
            _fail("promotion requires an independent participant isolation verifier")
        promoted_episodes = [
            episode for episode in episode_by_run.values()
            if task_by_id[episode["task_id"]]["batch_id"] in promotion["arena_batches"]
        ]
        try:
            isolation_verified = all(
                participant_isolation_verifier(episode) is True
                for episode in promoted_episodes
            )
        except Exception as exc:
            raise EvidenceValidationError("participant isolation verification failed") from exc
        if not isolation_verified:
            _fail("promotion participant isolation was not independently verified")
        for field in ("champion_before", "candidate", "approved_by"):
            if promotion[field] != approval[field]:
                _fail(f"promotion and approval disagree on {field}")
        aggregate_aura = aggregate_model = 0
        paired_by_batch = {item["batch_id"]: item["paired_counts"] for item in promotion["paired_results"]}
        for batch_id in promotion["arena_batches"]:
            prereg = prereg_by_batch.get(batch_id)
            if prereg is None:
                _fail(f"promotion refers to unregistered batch {batch_id}")
            derived = _derived_paired_counts(
                tasks_by_batch[batch_id], episode_by_run, result_by_run,
            )
            if paired_by_batch[batch_id] != derived:
                _fail(f"batch {batch_id} paired counts do not match signed results")
            if sum(derived.values()) != prereg["n_tasks"]:
                _fail(f"batch {batch_id} paired counts do not cover all tasks")
            batch_p = exact_binomial_one_sided(derived["aura_only_pass"], derived["model_only_pass"])
            if derived["aura_only_pass"] <= derived["model_only_pass"] or batch_p >= prereg["threshold_p"]:
                _fail(f"batch {batch_id} does not satisfy its preregistered threshold")
            aggregate_aura += derived["aura_only_pass"]
            aggregate_model += derived["model_only_pass"]
        aggregate_p = exact_binomial_one_sided(aggregate_aura, aggregate_model)
        if not math.isclose(float(promotion["exact_p"]), aggregate_p, rel_tol=0.0, abs_tol=1e-12):
            _fail("promotion exact p-value does not match signed batch results")
        arena_run_ids = {
            run_id
            for run_id, episode in episode_by_run.items()
            if episode["run_kind"] == "arena"
            and task_by_id[episode["task_id"]]["batch_id"] in promotion["arena_batches"]
        }
        if set(promotion["repro_runs"]) & arena_run_ids:
            _fail("promotion reproduction runs must be disjoint from arena runs")
        for run_id in promotion["repro_runs"]:
            result = result_by_run.get(run_id)
            episode = episode_by_run.get(run_id)
            if result is None or episode is None or not _result_passes(result):
                _fail(f"promotion reproduction run {run_id} is absent or failed")
            if episode["run_kind"] != "reproduction" or episode["actor"] != "aura":
                _fail(f"promotion reproduction run {run_id} must be a fresh AURA run")
            if task_by_id[episode["task_id"]]["batch_id"] not in promotion["arena_batches"]:
                _fail(f"promotion reproduction run {run_id} is outside promoted batches")
