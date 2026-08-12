from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from core.coding_arena_evidence import (
    EvidenceValidationError,
    compute_task_manifest_sha,
    exact_binomial_one_sided,
    sign_record,
    validate_evidence_bundle,
    validate_record,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs" / "aura_coding_arena_contract.schema.json"
SECRET = b"arena-test-secret-not-stored-by-coder-0001"
ZERO_SHA = "0" * 64
ONE_SHA = "1" * 64
TWO_SHA = "2" * 64


def _task(batch_id: str, number: int) -> dict:
    return {
        "record_type": "task",
        "id": f"{batch_id}-task-{number}",
        "batch_id": batch_id,
        "repo_hash": ZERO_SHA,
        "task_manifest_sha": ZERO_SHA,
        "failing_test": f"tests/test_{batch_id}_{number}.py::test_red",
        "files_allowed": [f"core/unit_{number}.py"],
        "forbidden_paths": ["tests", ".env", ".git"],
        "budget_s": 300,
        "requested_max_output_tokens": 10_000,
        "budget_prompt_chars": 50_000,
        "budget_reply_chars": 100_000,
        "network": False,
    }


def _episode(task_id: str, actor: str, run_kind: str = "arena") -> dict:
    run_id = f"run-{task_id}-{actor}-{run_kind}"
    return sign_record({
        "record_type": "episode",
        "task_id": task_id,
        "run_id": run_id,
        "run_kind": run_kind,
        "actor": actor,
        "declared_model_id": f"model-{actor}",
        "model_calls": [{
            "prompt_sha": ZERO_SHA,
            "reply_sha": ZERO_SHA,
            "declared_history_free": True,
            "declared_tools_enabled": False,
            "declared_recall_enabled": False,
        }],
        "prompt_sha": ZERO_SHA,
        "patch_sha": ONE_SHA if actor == "aura" else TWO_SHA,
        "stdout_sha": ZERO_SHA,
        "stderr_sha": ZERO_SHA,
        "tests_before": {"red": 1},
        "tests_after": {"green": actor == "aura"},
        "elapsed_s_measured_by_evaluator": 1.0,
        "tokens_reported_by_participant": 10,
        "prompt_chars_measured_by_evaluator": 100,
        "reply_chars_measured_by_evaluator": 100,
        "reply_char_limit": 100_000,
        "attempts": 1,
        "human_touches": 0,
        "exit_reason": "completed",
    }, SECRET)


def _result(episode: dict, passed: bool) -> dict:
    return sign_record({
        "record_type": "result",
        "task_id": episode["task_id"],
        "run_id": episode["run_id"],
        "evaluator_version": "arena-v1",
        "environment_fingerprint": ZERO_SHA,
        "hidden_pass": 1 if passed else 0,
        "hidden_total": 1,
        "red_test_pass": True,
        "regression_pass": True,
        "safety_flags": [],
    }, SECRET)


def _valid_bundle() -> list[dict]:
    records: list[dict] = []
    paired_results: list[dict] = []
    repro_task_ids: list[str] = []
    for batch_id in ("batch-a", "batch-b"):
        tasks = [_task(batch_id, number) for number in range(8)]
        manifest = compute_task_manifest_sha(tasks)
        for task in tasks:
            task["task_manifest_sha"] = manifest
        prereg = sign_record({
            "record_type": "pre_registration",
            "batch_id": batch_id,
            "n_tasks": len(tasks),
            "threshold_p": 0.05,
            "hypothesis_direction": "aura_better",
            "registered_at": "2026-08-08T08:00:00+07:00",
            "manifest_sha": manifest,
        }, SECRET)
        records.extend([prereg, *tasks])
        for task in tasks:
            aura_episode = _episode(task["id"], "aura")
            baseline_episode = _episode(task["id"], "baseline")
            records.extend([
                aura_episode,
                baseline_episode,
                _result(aura_episode, True),
                _result(baseline_episode, False),
            ])
        repro_task_ids.append(tasks[0]["id"])
        paired_results.append({
            "batch_id": batch_id,
            "paired_counts": {
                "both_pass": 0,
                "aura_only_pass": 8,
                "model_only_pass": 0,
                "both_fail": 0,
            },
        })

    repro_run_ids: list[str] = []
    for task_id in repro_task_ids:
        episode = _episode(task_id, "aura", "reproduction")
        records.extend([episode, _result(episode, True)])
        repro_run_ids.append(episode["run_id"])

    approval = {
        "record_type": "approval",
        "id": "approval-1",
        "champion_before": "aura-v1",
        "candidate": "aura-v2",
        "vibe_diff_sha": TWO_SHA,
        "decision": "approve",
        "approved_by": "Sếp",
        "approved_at": "2026-08-08T09:00:00+07:00",
        "channel": "telegram",
        "telegram_message_id": 101,
        "telegram_chat_id": -100123456,
        "from_user_id": 777,
        "reply_to_message_id": 100,
    }
    promotion = sign_record({
        "record_type": "promotion",
        "champion_before": "aura-v1",
        "candidate": "aura-v2",
        "arena_batches": ["batch-a", "batch-b"],
        "paired_results": paired_results,
        "exact_p": exact_binomial_one_sided(16, 0),
        "repro_runs": repro_run_ids,
        "approval_id": approval["id"],
        "approved_by": "Sếp",
        "rollback_ref": "refs/aura/champion-v1",
    }, SECRET)
    records.extend([approval, promotion])
    return records


def test_json_schema_is_valid_draft_2020_12():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validators.validator_for(schema).check_schema(schema)


def test_valid_signed_bundle_passes_semantic_validation():
    validate_evidence_bundle(
        _valid_bundle(), SECRET,
        lambda approval: approval["from_user_id"] == 777,
        lambda _episode: True,
    )


def test_forged_losing_promotion_with_fake_p_is_rejected():
    promotion = {
        "record_type": "promotion",
        "champion_before": "v1",
        "candidate": "v2",
        "arena_batches": ["a", "b"],
        "paired_results": [
            {"batch_id": "a", "paired_counts": {"both_pass": 0, "aura_only_pass": 3, "model_only_pass": 5, "both_fail": 0}},
            {"batch_id": "b", "paired_counts": {"both_pass": 0, "aura_only_pass": 3, "model_only_pass": 5, "both_fail": 0}},
        ],
        "exact_p": 0.001,
        "repro_runs": ["run-1", "run-2"],
        "approval_id": "approval-1",
        "approved_by": "Sếp",
        "rollback_ref": "v1",
    }
    with pytest.raises(EvidenceValidationError, match="must beat"):
        validate_record(sign_record(promotion, SECRET), SECRET)


@pytest.mark.parametrize("aura_only,model_only", [(8, 0), (9, 1), (15, 2)])
def test_stored_p_must_equal_recomputed_exact_test(aura_only: int, model_only: int):
    promotion = {
        "record_type": "promotion",
        "champion_before": "v1",
        "candidate": "v2",
        "arena_batches": ["a", "b"],
        "paired_results": [
            {"batch_id": "a", "paired_counts": {"both_pass": 0, "aura_only_pass": aura_only, "model_only_pass": model_only, "both_fail": 0}},
            {"batch_id": "b", "paired_counts": {"both_pass": 0, "aura_only_pass": aura_only, "model_only_pass": model_only, "both_fail": 0}},
        ],
        "exact_p": min(1.0, exact_binomial_one_sided(aura_only * 2, model_only * 2) + 0.01),
        "repro_runs": ["run-1", "run-2"],
        "approval_id": "approval-1",
        "approved_by": "Sếp",
        "rollback_ref": "v1",
    }
    with pytest.raises(EvidenceValidationError, match="exact_p mismatch"):
        validate_record(sign_record(promotion, SECRET), SECRET)


@pytest.mark.parametrize("record_type", ["episode", "result"])
def test_evaluator_records_reject_wrong_hmac(record_type: str):
    episode = _episode("task-1", "aura")
    record = episode if record_type == "episode" else _result(episode, True)
    field = "episode_signature" if record_type == "episode" else "result_signature"
    record[field] = "f" * 64
    with pytest.raises(EvidenceValidationError, match=f"invalid {field}"):
        validate_record(record, SECRET)


def test_v2_rejects_misleading_v1_token_label():
    episode = _episode("task-1", "aura")
    forged = deepcopy(episode)
    forged["tokens_metered_by_evaluator"] = forged.pop("tokens_reported_by_participant")
    with pytest.raises(EvidenceValidationError, match="missing=.*tokens_reported_by_participant"):
        validate_record(sign_record(forged, SECRET), SECRET)


def test_model_call_rejects_old_fact_labels_and_extra_fields():
    episode = _episode("task-1", "aura")
    forged = deepcopy(episode)
    call = forged["model_calls"][0]
    call["history_free"] = call.pop("declared_history_free")
    with pytest.raises(EvidenceValidationError, match="misleading or incomplete"):
        validate_record(sign_record(forged, SECRET), SECRET)


def test_episode_attempt_count_must_match_model_calls():
    episode = _episode("task-1", "aura")
    forged = deepcopy(episode)
    forged["attempts"] = 2
    with pytest.raises(EvidenceValidationError, match="attempts must equal"):
        validate_record(sign_record(forged, SECRET), SECRET)


def test_lesson_evidence_and_held_out_sets_cannot_overlap():
    lesson = {
        "record_type": "lesson",
        "id": "lesson-1",
        "failure_signature": ZERO_SHA,
        "content": "Verify through hidden tests.",
        "evidence_run_ids": ["run-1"],
        "evidence_patch_sha": [ONE_SHA],
        "held_out_run_ids": ["run-1"],
        "status": "candidate",
    }
    with pytest.raises(EvidenceValidationError, match="disjoint"):
        validate_record(lesson)


def test_signed_self_declared_counts_are_rejected_against_results():
    records = _valid_bundle()
    promotion = next(record for record in records if record["record_type"] == "promotion")
    forged = deepcopy(promotion)
    forged["paired_results"][0]["paired_counts"]["both_pass"] = 1
    forged["paired_results"][0]["paired_counts"]["aura_only_pass"] = 7
    forged["exact_p"] = exact_binomial_one_sided(15, 0)
    forged = sign_record(forged, SECRET)
    records[records.index(promotion)] = forged
    with pytest.raises(EvidenceValidationError, match="do not match signed results"):
        validate_evidence_bundle(records, SECRET, lambda _approval: True, lambda _episode: True)


def test_promotion_without_human_approval_is_rejected():
    records = [record for record in _valid_bundle() if record["record_type"] != "approval"]
    with pytest.raises(EvidenceValidationError, match="lacks human approval"):
        validate_evidence_bundle(records, SECRET, lambda _approval: True, lambda _episode: True)


def test_task_manifest_change_after_preregistration_is_rejected():
    records = _valid_bundle()
    task = next(record for record in records if record["record_type"] == "task")
    task["budget_s"] += 1
    with pytest.raises(EvidenceValidationError, match="manifest mismatch"):
        validate_evidence_bundle(records, SECRET, lambda _approval: True, lambda _episode: True)


def test_machine_hmac_cannot_sign_a_human_approval():
    approval = next(record for record in _valid_bundle() if record["record_type"] == "approval")
    with pytest.raises(EvidenceValidationError, match="is not signed"):
        sign_record(approval, SECRET)


def test_promotion_requires_independent_human_verifier():
    with pytest.raises(EvidenceValidationError, match="independent human approval verifier"):
        validate_evidence_bundle(_valid_bundle(), SECRET)


def test_unverified_or_wrong_user_telegram_approval_is_rejected():
    with pytest.raises(EvidenceValidationError, match="real message from Sếp"):
        validate_evidence_bundle(
            _valid_bundle(), SECRET, lambda _approval: False, lambda _episode: True,
        )


def test_arena_run_cannot_be_reused_as_reproduction():
    records = _valid_bundle()
    promotion = next(record for record in records if record["record_type"] == "promotion")
    arena_runs = [
        record["run_id"] for record in records
        if record["record_type"] == "episode" and record["run_kind"] == "arena" and record["actor"] == "aura"
    ]
    forged = deepcopy(promotion)
    forged["repro_runs"] = arena_runs[:2]
    records[records.index(promotion)] = sign_record(forged, SECRET)
    with pytest.raises(EvidenceValidationError, match="disjoint from arena runs"):
        validate_evidence_bundle(records, SECRET, lambda _approval: True, lambda _episode: True)


def test_baseline_run_cannot_be_claimed_as_aura_reproduction():
    records = _valid_bundle()
    promotion = next(record for record in records if record["record_type"] == "promotion")
    reproduction_episodes = [
        record for record in records
        if record["record_type"] == "episode" and record["run_kind"] == "reproduction"
    ]
    forged_episode = deepcopy(reproduction_episodes[0])
    forged_episode["actor"] = "baseline"
    forged_episode = sign_record(forged_episode, SECRET)
    records[records.index(reproduction_episodes[0])] = forged_episode
    with pytest.raises(EvidenceValidationError, match="fresh AURA run"):
        validate_evidence_bundle(records, SECRET, lambda _approval: True, lambda _episode: True)


def test_promotion_requires_independent_participant_isolation_verifier():
    with pytest.raises(EvidenceValidationError, match="participant isolation verifier"):
        validate_evidence_bundle(_valid_bundle(), SECRET, lambda _approval: True)


def test_unverified_participant_isolation_is_rejected():
    with pytest.raises(EvidenceValidationError, match="isolation was not independently verified"):
        validate_evidence_bundle(
            _valid_bundle(), SECRET, lambda _approval: True, lambda _episode: False,
        )


def test_episode_over_signed_task_character_budget_is_rejected():
    records = _valid_bundle()
    episode = next(record for record in records if record["record_type"] == "episode")
    forged = deepcopy(episode)
    forged["reply_chars_measured_by_evaluator"] = 100_001
    records[records.index(episode)] = sign_record(forged, SECRET)
    with pytest.raises(EvidenceValidationError, match="reply character budget"):
        validate_evidence_bundle(
            records, SECRET, lambda _approval: True, lambda _episode: True,
        )


def test_regression_not_run_cannot_count_as_a_promotion_pass():
    records = _valid_bundle()
    result = next(
        record for record in records
        if record["record_type"] == "result"
        and record["run_id"].endswith("-aura-arena")
    )
    forged = deepcopy(result)
    forged["regression_pass"] = None
    records[records.index(result)] = sign_record(forged, SECRET)
    with pytest.raises(EvidenceValidationError, match="paired counts do not match"):
        validate_evidence_bundle(
            records, SECRET, lambda _approval: True, lambda _episode: True,
        )
