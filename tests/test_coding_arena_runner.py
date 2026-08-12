from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from core.coding_arena_evidence import validate_record
from core.coding_arena_runner import (
    ArenaRunnerError,
    LockedEvaluatorStoreError,
    ModelReply,
    ParticipantContractError,
    PilotArenaRunner,
    SecureExecutorUnavailable,
    SignedJsonlLedger,
    build_prompt,
)


ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "arena" / "tasks" / "t10_fake_ack"
SECRET = b"runner-test-secret-outside-coder-workspace-01"


class FakeParticipant:
    declared_history_free = True
    declared_tools_enabled = False
    declared_recall_enabled = False

    def __init__(self, model_id: str, response: str, reported_tokens: int | None = None) -> None:
        self.declared_model_id = model_id
        self.response = response
        self.reported_tokens = len(response) // 4 if reported_tokens is None else reported_tokens
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, max_tokens: int) -> ModelReply:
        self.prompts.append(prompt)
        assert max_tokens > 0
        return ModelReply(self.response, reported_tokens=self.reported_tokens)


def _fenced(path: Path) -> str:
    return "```python\n" + path.read_text(encoding="utf-8").rstrip("\n") + "\n```"


def _runner(tmp_path: Path) -> PilotArenaRunner:
    return PilotArenaRunner(
        evaluator_secret=SECRET,
        ledger=SignedJsonlLedger(tmp_path / "evidence.jsonl"),
    )


def _arena_case(tmp_path: Path) -> tuple[Path, Path]:
    public = tmp_path / "public_task"
    locked = tmp_path / "locked_task"
    public.mkdir()
    locked.mkdir()
    for name in ("broken.py", "test_red.py", "meta.json"):
        shutil.copy2(TASK / name, public / name)
    shutil.copy2(TASK / "test_hidden.py", locked / "test_hidden.py")
    return public, locked


def _run_staged_pair(
    tmp_path: Path, *, aura: FakeParticipant, baseline: FakeParticipant,
):
    public, locked = _arena_case(tmp_path)
    return _runner(tmp_path).run_pair(
        public, locked_task_dir=locked, aura=aura, baseline=baseline,
    )


def test_prompt_contains_only_public_material_and_fixed_instruction():
    prompt, before = build_prompt(TASK)
    assert before.returncode != 0
    assert prompt.count("[MÃ NGUỒN]") == 1
    assert prompt.count("[TEST ĐỎ]") == 1
    assert prompt.count("[OUTPUT PYTEST]") == 1
    assert prompt.count("[CHỈ DẪN]") == 1
    assert (TASK / "broken.py").read_text(encoding="utf-8").strip() in prompt
    assert (TASK / "test_red.py").read_text(encoding="utf-8").strip() in prompt
    assert "t10_fake_ack" not in prompt
    assert "bay-tu-khai" not in prompt
    assert "why_must_run" not in prompt
    assert str(ROOT) not in prompt
    assert "self.driver.drive(direction, seconds)" not in prompt


def test_pair_gets_identical_prompt_and_writes_signed_hash_only_ledger(tmp_path: Path):
    aura = FakeParticipant("aura-model", _fenced(TASK / "fixed.py"))
    baseline = FakeParticipant("baseline-model", _fenced(TASK / "broken.py"))
    public, locked = _arena_case(tmp_path)
    outcome = _runner(tmp_path).run_pair(
        public, locked_task_dir=locked, aura=aura, baseline=baseline,
    )
    assert aura.prompts == baseline.prompts
    assert len(aura.prompts) == 1
    assert outcome.aura.episode["prompt_sha"] == outcome.prompt_sha
    assert outcome.baseline.episode["prompt_sha"] == outcome.prompt_sha
    assert outcome.aura.episode["exit_reason"] == "completed"
    assert outcome.baseline.episode["exit_reason"] == "red_failed"
    assert outcome.aura.result["hidden_pass"] == outcome.aura.result["hidden_total"]
    assert outcome.aura.result["red_test_pass"] is True
    assert outcome.aura.result["regression_pass"] is None
    assert outcome.aura.result["safety_flags"] == [
        "participant_isolation_unverified",
        "pilot_no_os_sandbox",
        "regression_not_run",
    ]
    episode = outcome.aura.episode
    assert episode["tokens_reported_by_participant"] == aura.reported_tokens
    assert episode["prompt_chars_measured_by_evaluator"] == len(aura.prompts[0])
    assert episode["reply_chars_measured_by_evaluator"] == len(aura.response)
    assert "tokens_metered_by_evaluator" not in episode
    model_call = episode["model_calls"][0]
    assert model_call["declared_history_free"] is True
    assert model_call["declared_tools_enabled"] is False
    assert model_call["declared_recall_enabled"] is False
    assert "history_free" not in model_call

    ledger = SignedJsonlLedger(tmp_path / "evidence.jsonl")
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    records = ledger.read_verified(SECRET)
    for record in records:
        validate_record(record, SECRET)
    raw_ledger = "\n".join(lines)
    assert aura.prompts[0] not in raw_ledger
    assert "self.driver.drive(direction, seconds)" not in raw_ledger
    assert str(locked) not in raw_ledger


@pytest.mark.parametrize(
    "response",
    [
        "không có code",
        "giải thích\n```python\nx = 1\n```",
        "```python\nx = 1\n```\nthêm chữ",
        "```python\nx = 1\n```\n```python\ny = 2\n```",
    ],
)
def test_malformed_submission_fails_without_retry(tmp_path: Path, response: str):
    participant = FakeParticipant("bad-format", response)
    other = FakeParticipant("baseline", _fenced(TASK / "broken.py"))
    outcome = _run_staged_pair(tmp_path, aura=participant, baseline=other)
    assert outcome.aura.episode["exit_reason"] == "malformed"
    assert outcome.aura.result["hidden_pass"] == 0
    assert len(participant.prompts) == 1


def test_ast_gate_blocks_file_read_attempt(tmp_path: Path):
    malicious = "```python\ncontent = open('D:/AURA_OS_v2/arena/make_pack.py').read()\n```"
    actor = FakeParticipant("reader", malicious)
    baseline = FakeParticipant("baseline", _fenced(TASK / "broken.py"))
    outcome = _run_staged_pair(tmp_path, aura=actor, baseline=baseline)
    assert outcome.aura.episode["exit_reason"] == "ast_blocked"
    assert "ast_blocked" in outcome.aura.result["safety_flags"]


def test_ast_gate_blocks_mro_introspection(tmp_path: Path):
    malicious = "```python\nx = tuple.mro()\n```"
    actor = FakeParticipant("introspector", malicious)
    baseline = FakeParticipant("baseline", _fenced(TASK / "broken.py"))
    outcome = _run_staged_pair(tmp_path, aura=actor, baseline=baseline)
    assert outcome.aura.episode["exit_reason"] == "ast_blocked"


def test_type_identity_and_collection_remove_are_not_false_positives(tmp_path: Path):
    code = (TASK / "fixed.py").read_text(encoding="utf-8").rstrip() + "\n"
    code += "xs = [1]\nxs.remove(1)\nassert type(1) is int\n"
    actor = FakeParticipant("normal-python", f"```python\n{code}```")
    baseline = FakeParticipant("baseline", _fenced(TASK / "broken.py"))
    outcome = _run_staged_pair(tmp_path, aura=actor, baseline=baseline)
    assert outcome.aura.episode["exit_reason"] == "completed"


def test_pure_stdlib_allowlist_supports_realistic_aura_code(tmp_path: Path):
    imports = (
        "import collections, dataclasses, datetime, decimal, enum, functools\n"
        "import itertools, json, math, re, statistics, string, textwrap\n"
        "import threading, time, types, typing, unicodedata\n"
    )
    code = imports + (TASK / "fixed.py").read_text(encoding="utf-8")
    actor = FakeParticipant("stdlib", f"```python\n{code.rstrip()}\n```")
    baseline = FakeParticipant("baseline", _fenced(TASK / "broken.py"))
    outcome = _run_staged_pair(tmp_path, aura=actor, baseline=baseline)
    assert outcome.aura.episode["exit_reason"] == "completed"


def test_runner_rejects_adapter_with_recall_history_or_tools(tmp_path: Path):
    actor = FakeParticipant("leaky", _fenced(TASK / "fixed.py"))
    actor.declared_recall_enabled = True
    baseline = FakeParticipant("baseline", _fenced(TASK / "broken.py"))
    with pytest.raises(ParticipantContractError, match="history-free"):
        _run_staged_pair(tmp_path, aura=actor, baseline=baseline)
    assert actor.prompts == []


def test_liar_declarations_are_recorded_only_as_declarations(tmp_path: Path):
    liar = FakeParticipant("liar", _fenced(TASK / "fixed.py"), reported_tokens=1)
    baseline = FakeParticipant("baseline", _fenced(TASK / "broken.py"))
    outcome = _run_staged_pair(tmp_path, aura=liar, baseline=baseline)
    assert liar.prompts  # This adapter retained history despite its declaration.
    episode = outcome.aura.episode
    assert episode["tokens_reported_by_participant"] == 1
    assert episode["reply_chars_measured_by_evaluator"] == len(liar.response)
    assert set(episode["model_calls"][0]) == {
        "prompt_sha", "reply_sha", "declared_history_free",
        "declared_tools_enabled", "declared_recall_enabled",
    }


def test_unicode_reply_character_count_is_evaluator_measured(tmp_path: Path):
    actor = FakeParticipant("unicode", "á🙂", reported_tokens=0)
    baseline = FakeParticipant("baseline", _fenced(TASK / "broken.py"))
    outcome = _run_staged_pair(tmp_path, aura=actor, baseline=baseline)
    assert outcome.aura.episode["reply_chars_measured_by_evaluator"] == 2


def test_reply_character_budget_is_enforced_before_tests(tmp_path: Path):
    task, locked = _arena_case(tmp_path)
    meta_path = task / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    response = _fenced(TASK / "fixed.py")
    meta["budget_reply_chars"] = len(response) - 1
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    actor = FakeParticipant("too-long", response, reported_tokens=1)
    baseline = FakeParticipant("baseline", _fenced(TASK / "broken.py"))
    outcome = _runner(tmp_path).run_pair(
        task, locked_task_dir=locked, aura=actor, baseline=baseline,
    )
    assert outcome.aura.episode["exit_reason"] == "reply_char_budget_exceeded"
    assert outcome.aura.result["red_test_pass"] is False


def test_prompt_character_budget_stops_before_model_call(tmp_path: Path):
    task, locked = _arena_case(tmp_path)
    meta_path = task / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["budget_prompt_chars"] = 1
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    actor = FakeParticipant("never-called", _fenced(TASK / "fixed.py"))
    baseline = FakeParticipant("baseline", _fenced(TASK / "broken.py"))
    with pytest.raises(ArenaRunnerError, match="prompt exceeds"):
        _runner(tmp_path).run_pair(
            task, locked_task_dir=locked, aura=actor, baseline=baseline,
        )
    assert actor.prompts == baseline.prompts == []


@pytest.mark.parametrize("remove_index", [1, -1])
def test_ledger_detects_middle_or_tail_deletion(tmp_path: Path, remove_index: int):
    ledger = SignedJsonlLedger(tmp_path / "evidence.jsonl")
    runner = PilotArenaRunner(evaluator_secret=SECRET, ledger=ledger)
    public, locked = _arena_case(tmp_path)
    runner.run_pair(
        public,
        locked_task_dir=locked,
        aura=FakeParticipant("aura", _fenced(TASK / "fixed.py")),
        baseline=FakeParticipant("baseline", _fenced(TASK / "broken.py")),
    )
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    lines.pop(remove_index)
    ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ArenaRunnerError, match="ledger"):
        ledger.read_verified(SECRET)


def test_locked_evaluator_directory_inside_repo_fails_closed(tmp_path: Path):
    public, _locked = _arena_case(tmp_path)
    actor = FakeParticipant("aura", _fenced(TASK / "fixed.py"))
    baseline = FakeParticipant("baseline", _fenced(TASK / "broken.py"))
    with pytest.raises(LockedEvaluatorStoreError, match="outside the repository"):
        _runner(tmp_path).run_pair(
            public, locked_task_dir=TASK, aura=actor, baseline=baseline,
        )
    assert actor.prompts == baseline.prompts == []


def test_public_task_with_hidden_or_fixed_artifact_fails_closed(tmp_path: Path):
    _public, locked = _arena_case(tmp_path)
    actor = FakeParticipant("aura", _fenced(TASK / "fixed.py"))
    baseline = FakeParticipant("baseline", _fenced(TASK / "broken.py"))
    with pytest.raises(LockedEvaluatorStoreError, match="private evaluator artifacts"):
        _runner(tmp_path).run_pair(
            TASK, locked_task_dir=locked, aura=actor, baseline=baseline,
        )
    assert actor.prompts == baseline.prompts == []


def test_promotion_mode_fails_closed_without_os_executor(tmp_path: Path):
    with pytest.raises(SecureExecutorUnavailable, match="OS/container"):
        PilotArenaRunner(
            evaluator_secret=SECRET,
            ledger=SignedJsonlLedger(tmp_path / "never.jsonl"),
            mode="promotion",
        )
