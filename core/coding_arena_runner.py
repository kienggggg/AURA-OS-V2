"""Fail-closed pilot runner for paired AURA coding experiments.

This runner deliberately supports only ``pilot`` mode on the current machine.
The local subprocess used for tests is defense-in-depth, not an OS security
boundary, so every result carries ``pilot_no_os_sandbox`` and is therefore
ineligible for promotion under :mod:`core.coding_arena_evidence`.

Contestants receive one text prompt and return one text response.  The runner
never supplies paths, history, recall, tools, hidden tests, reference fixes, or
the task slug.  A future promotion runner must use a separately reviewed
OS/container executor; asking this module for promotion mode fails closed.
"""
from __future__ import annotations

import ast
import hashlib
import hmac
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from core.coding_arena_evidence import sign_record, validate_record
from evolution.validator import ASTValidator


class ArenaRunnerError(RuntimeError):
    """Base class for runner failures."""


class SecureExecutorUnavailable(ArenaRunnerError):
    """Raised rather than pretending local subprocesses are secure."""


class ParticipantContractError(ArenaRunnerError):
    """Raised when an adapter could carry history, tools, or recall."""


class LockedEvaluatorStoreError(ArenaRunnerError):
    """Raised when private evaluator artifacts are not physically separated."""


@dataclass(frozen=True)
class ModelReply:
    content: str
    reported_tokens: int


class TextOnlyParticipant(Protocol):
    """Clean one-shot model adapter.  Implementations are evaluator-owned."""

    declared_model_id: str
    declared_history_free: bool
    declared_tools_enabled: bool
    declared_recall_enabled: bool

    def complete(self, prompt: str, *, max_tokens: int) -> ModelReply: ...


@dataclass(frozen=True)
class TestMeasurement:
    returncode: int
    passed: int
    total: int
    timed_out: bool
    elapsed_s: float
    stdout: str
    stderr: str

    def evidence(self) -> dict:
        return {
            "returncode": self.returncode,
            "passed": self.passed,
            "total": self.total,
            "timed_out": self.timed_out,
            "elapsed_s": round(self.elapsed_s, 6),
            "stdout_sha": _sha_text(self.stdout),
            "stderr_sha": _sha_text(self.stderr),
        }


@dataclass(frozen=True)
class ContestantOutcome:
    episode: dict
    result: dict


@dataclass(frozen=True)
class PairOutcome:
    prompt_sha: str
    aura: ContestantOutcome
    baseline: ContestantOutcome


_SUBMISSION_RE = re.compile(r"\A```python\r?\n(.+?)\r?\n```\Z", re.DOTALL)
_ALLOWED_IMPORTS = frozenset({
    "collections", "dataclasses", "datetime", "decimal", "enum", "functools",
    "itertools", "json", "math", "re", "statistics", "string", "textwrap",
    "threading", "time", "types", "typing", "unicodedata",
})
_BLOCKED_CALLS = frozenset({
    "open", "eval", "exec", "compile", "__import__", "input",
    "getattr", "setattr", "delattr", "globals", "locals", "vars",
    "breakpoint", "help", "mro",
})
_SAFE_ENV = (
    "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC",
    "NUMBER_OF_PROCESSORS", "LANG", "LC_ALL", "TZ",
)
_LEDGER_LOCK = threading.Lock()
_REPO_ROOT = Path(__file__).resolve().parents[1]
_ZERO_SHA = "0" * 64
_LEDGER_ENTRY_FIELDS = frozenset({"ledger_seq", "prev_sha", "record", "ledger_signature"})
_LEDGER_HEAD_FIELDS = frozenset({"record_count", "last_entry_sha", "ledger_signature"})


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_text(value: str) -> str:
    return _sha_bytes(value.encode("utf-8"))


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _ledger_hmac(value: dict, secret: bytes) -> str:
    unsigned = dict(value)
    unsigned.pop("ledger_signature", None)
    return hmac.new(secret, _canonical_bytes(unsigned), hashlib.sha256).hexdigest()


def _minimal_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in _SAFE_ENV if key in os.environ}
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "AURA_ARENA_MODE": "pilot",
    })
    return env


def _resolved_directory(path: Path, label: str) -> Path:
    candidate = Path(path)
    if candidate.is_symlink():
        raise LockedEvaluatorStoreError(f"{label} cannot be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise LockedEvaluatorStoreError(f"{label} does not exist") from exc
    if not resolved.is_dir():
        raise LockedEvaluatorStoreError(f"{label} must be a directory")
    return resolved


def _is_within(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _read_locked_hidden_source(task_dir: Path, locked_task_dir: Path) -> str:
    public_dir = _resolved_directory(task_dir, "public task directory")
    locked_input = Path(locked_task_dir)
    locked_dir = _resolved_directory(locked_input, "locked evaluator directory")
    repo_root = _REPO_ROOT.resolve()
    if _is_within(locked_dir, repo_root):
        raise LockedEvaluatorStoreError(
            "locked evaluator directory must be outside the repository"
        )
    if _is_within(locked_dir, public_dir) or _is_within(public_dir, locked_dir):
        raise LockedEvaluatorStoreError(
            "public task and locked evaluator directories must be disjoint"
        )
    leaked = [name for name in ("test_hidden.py", "fixed.py") if (public_dir / name).exists()]
    if leaked:
        raise LockedEvaluatorStoreError(
            "public task contains private evaluator artifacts: " + ", ".join(leaked)
        )
    hidden_input = locked_dir / "test_hidden.py"
    if hidden_input.is_symlink():
        raise LockedEvaluatorStoreError("locked hidden test cannot be a symlink")
    try:
        hidden_path = hidden_input.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise LockedEvaluatorStoreError("locked hidden test is missing") from exc
    if not hidden_path.is_file() or not _is_within(hidden_path, locked_dir):
        raise LockedEvaluatorStoreError("locked hidden test escapes its directory")
    return hidden_path.read_text(encoding="utf-8")


def _pytest_counts(output: str, returncode: int) -> tuple[int, int]:
    counts = {name: 0 for name in ("passed", "failed", "error", "errors", "skipped", "xfailed", "xpassed")}
    for number, name in re.findall(
        r"(?<![\w.])(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed)\b",
        output,
    ):
        counts[name] += int(number)
    errors = counts["error"] + counts["errors"]
    total = counts["passed"] + counts["failed"] + errors + counts["skipped"] + counts["xfailed"] + counts["xpassed"]
    if total == 0:
        total = 1
    passed = counts["passed"] if returncode == 0 else min(counts["passed"], total)
    return passed, total


def _run_test(module_source: str, test_source: str, timeout_s: float) -> TestMeasurement:
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="aura_arena_eval_") as temp_name:
        workspace = Path(temp_name)
        (workspace / "module.py").write_text(module_source, encoding="utf-8", newline="\n")
        (workspace / "test_case.py").write_text(test_source, encoding="utf-8", newline="\n")
        command = [
            sys.executable, "-I", "-m", "pytest", "test_case.py", "-q",
            "--no-header", "-p", "no:cacheprovider",
        ]
        kwargs: dict = {
            "cwd": workspace,
            "env": _minimal_env(),
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": timeout_s,
            "check": False,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            completed = subprocess.run(command, **kwargs)
            timed_out = False
            returncode = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            returncode = -1
            stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            stderr += "\nTIMEOUT"
    elapsed = time.monotonic() - start
    passed, total = _pytest_counts(stdout + "\n" + stderr, returncode)
    return TestMeasurement(returncode, passed, total, timed_out, elapsed, stdout, stderr)


def _submission_code(response: str) -> str | None:
    if response.count("```") != 2 or response.count("```python") != 1:
        return None
    match = _SUBMISSION_RE.fullmatch(response)
    if match is None:
        return None
    code = match.group(1)
    return code if code.strip() else None


def _strict_ast_gate(code: str) -> list[str]:
    """Return fail reasons; an empty list means the pilot AST gate passed."""
    report = ASTValidator().validate(code)
    reasons = [f"{finding.rule}:{finding.lineno}" for finding in report.blocks]
    if not report.syntax_ok:
        return reasons or ["syntax"]
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = (
                [alias.name.split(".")[0] for alias in node.names]
                if isinstance(node, ast.Import)
                else [(node.module or "").split(".")[0]]
            )
            for module in modules:
                if module not in _ALLOWED_IMPORTS:
                    reasons.append(f"import:{module}:{getattr(node, 'lineno', 0)}")
        elif isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in _BLOCKED_CALLS:
                reasons.append(f"call:{name}:{node.lineno}")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            reasons.append(f"dunder:{node.attr}:{getattr(node, 'lineno', 0)}")
        elif isinstance(node, ast.Name) and node.id.startswith("__"):
            reasons.append(f"dunder-name:{node.id}:{getattr(node, 'lineno', 0)}")
    return sorted(set(reasons))


def build_prompt(task_dir: Path, *, timeout_s: float = 15.0) -> tuple[str, TestMeasurement]:
    """Build the only prompt contestants see; no task metadata is included."""
    module_source = (task_dir / "broken.py").read_text(encoding="utf-8")
    red_source = (task_dir / "test_red.py").read_text(encoding="utf-8")
    before = _run_test(module_source, red_source, timeout_s)
    if before.returncode == 0 or before.timed_out:
        raise ArenaRunnerError("pilot task must have a deterministic red public test")
    raw_output = before.stdout + before.stderr
    instruction = (
        "Sửa module.py cho test đỏ xanh. Chỉ trả về TOÀN BỘ nội dung mới "
        "của module.py trong đúng một khối ```python. Không giải thích."
    )
    prompt = (
        "[MÃ NGUỒN]\n```python\n" + module_source.rstrip("\n") + "\n```\n\n"
        "[TEST ĐỎ]\n```python\n" + red_source.rstrip("\n") + "\n```\n\n"
        "[OUTPUT PYTEST]\n```text\n" + raw_output.rstrip("\n") + "\n```\n\n"
        "[CHỈ DẪN]\n" + instruction
    )
    return prompt, before


class SignedJsonlLedger:
    """Evaluator-owned, HMAC-chained ledger storing hashes/metrics, never prompts.

    Evidence records keep their own evaluator HMAC.  Each JSONL line is a
    separately HMAC-authenticated envelope whose ``prev_sha`` points at the
    previous complete envelope.  A signed head sidecar detects ordinary tail
    deletion.  A trusted external anchor is still required to detect rollback
    of both the ledger and its head to an older, jointly valid snapshot.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.head_path = self.path.with_name(self.path.name + ".head.json")

    @staticmethod
    def _check_secret(secret: bytes) -> None:
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ArenaRunnerError("ledger HMAC secret must be at least 32 bytes")

    def _read_verified_unlocked(self, secret: bytes) -> tuple[list[dict], int, str]:
        records: list[dict] = []
        expected_seq = 1
        expected_prev = _ZERO_SHA
        if self.path.exists():
            for line_number, raw in enumerate(
                self.path.read_text(encoding="utf-8").splitlines(), start=1,
            ):
                if not raw.strip():
                    raise ArenaRunnerError(f"blank ledger line {line_number}")
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ArenaRunnerError(f"invalid ledger JSON at line {line_number}") from exc
                if not isinstance(entry, dict) or set(entry) != _LEDGER_ENTRY_FIELDS:
                    raise ArenaRunnerError(f"invalid ledger envelope at line {line_number}")
                if entry["ledger_seq"] != expected_seq:
                    raise ArenaRunnerError(f"ledger sequence break at line {line_number}")
                if entry["prev_sha"] != expected_prev:
                    raise ArenaRunnerError(f"ledger hash-chain break at line {line_number}")
                actual_signature = entry.get("ledger_signature")
                expected_signature = _ledger_hmac(entry, secret)
                if not isinstance(actual_signature, str) or not hmac.compare_digest(
                    actual_signature, expected_signature,
                ):
                    raise ArenaRunnerError(f"invalid ledger HMAC at line {line_number}")
                record = entry["record"]
                if not isinstance(record, dict):
                    raise ArenaRunnerError(f"invalid evidence record at line {line_number}")
                validate_record(record, secret)
                records.append(record)
                expected_prev = _sha_bytes(_canonical_bytes(entry))
                expected_seq += 1

        if records:
            if not self.head_path.exists():
                raise ArenaRunnerError("ledger head is missing")
            try:
                head = json.loads(self.head_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ArenaRunnerError("invalid ledger head JSON") from exc
            if not isinstance(head, dict) or set(head) != _LEDGER_HEAD_FIELDS:
                raise ArenaRunnerError("invalid ledger head")
            if not hmac.compare_digest(
                str(head.get("ledger_signature", "")), _ledger_hmac(head, secret),
            ):
                raise ArenaRunnerError("invalid ledger head HMAC")
            if head["record_count"] != len(records) or head["last_entry_sha"] != expected_prev:
                raise ArenaRunnerError("ledger head does not match JSONL chain")
        elif self.head_path.exists():
            raise ArenaRunnerError("ledger head exists without records")
        return records, expected_seq, expected_prev

    def read_verified(self, secret: bytes) -> list[dict]:
        """Return evidence records only after verifying every envelope and head."""
        self._check_secret(secret)
        with _LEDGER_LOCK:
            records, _, _ = self._read_verified_unlocked(secret)
        return records

    def append(self, secret: bytes, *records: dict) -> None:
        self._check_secret(secret)
        if not records:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _LEDGER_LOCK:
            _, next_seq, prev_sha = self._read_verified_unlocked(secret)
            entries: list[dict] = []
            for record in records:
                validate_record(record, secret)
                entry = {
                    "ledger_seq": next_seq,
                    "prev_sha": prev_sha,
                    "record": record,
                }
                entry["ledger_signature"] = _ledger_hmac(entry, secret)
                entries.append(entry)
                prev_sha = _sha_bytes(_canonical_bytes(entry))
                next_seq += 1
            payload = "".join(
                _canonical_bytes(entry).decode("utf-8") + "\n" for entry in entries
            )
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())

            head = {"record_count": next_seq - 1, "last_entry_sha": prev_sha}
            head["ledger_signature"] = _ledger_hmac(head, secret)
            temp_head = self.head_path.with_name(self.head_path.name + ".tmp")
            temp_head.write_bytes(_canonical_bytes(head) + b"\n")
            os.replace(temp_head, self.head_path)


class PilotArenaRunner:
    """Paired, history-free text runner.  It can never emit promotion evidence."""

    def __init__(
        self,
        *,
        evaluator_secret: bytes,
        ledger: SignedJsonlLedger,
        mode: str = "pilot",
        test_timeout_s: float = 15.0,
    ) -> None:
        if mode != "pilot":
            raise SecureExecutorUnavailable(
                "promotion mode requires a reviewed OS/container executor; none is installed"
            )
        self.secret = evaluator_secret
        self.ledger = ledger
        self.test_timeout_s = test_timeout_s

    @staticmethod
    def _check_participant(participant: TextOnlyParticipant) -> dict[str, bool]:
        declarations = {
            "declared_history_free": getattr(participant, "declared_history_free", False),
            "declared_tools_enabled": getattr(participant, "declared_tools_enabled", True),
            "declared_recall_enabled": getattr(participant, "declared_recall_enabled", True),
        }
        if any(not isinstance(value, bool) for value in declarations.values()):
            raise ParticipantContractError("participant declarations must be booleans")
        if (
            not declarations["declared_history_free"]
            or declarations["declared_tools_enabled"]
            or declarations["declared_recall_enabled"]
        ):
            raise ParticipantContractError(
                "arena participant must declare history-free, tool-free, and recall-free operation"
            )
        declared_model_id = getattr(participant, "declared_model_id", None)
        if not isinstance(declared_model_id, str) or not declared_model_id:
            raise ParticipantContractError("participant declared_model_id is required")
        return declarations

    def _environment_fingerprint(self) -> str:
        facts = {
            "python": sys.version,
            "platform": platform.platform(),
            "runner": "pilot-arena-v2",
            "os_sandbox": False,
        }
        return _sha_text(json.dumps(facts, sort_keys=True, separators=(",", ":")))

    def _run_one(
        self,
        *,
        actor: str,
        participant: TextOnlyParticipant,
        task_id: str,
        prompt: str,
        prompt_sha: str,
        before: TestMeasurement,
        red_source: str,
        hidden_source: str,
        max_tokens: int,
        reply_char_limit: int,
    ) -> ContestantOutcome:
        declarations = self._check_participant(participant)
        started = time.monotonic()
        reply = participant.complete(prompt, max_tokens=max_tokens)
        elapsed = time.monotonic() - started
        if (
            not isinstance(reply, ModelReply)
            or not isinstance(reply.content, str)
            or isinstance(reply.reported_tokens, bool)
            or not isinstance(reply.reported_tokens, int)
            or reply.reported_tokens < 0
        ):
            raise ParticipantContractError("participant must return ModelReply with reported token usage")

        prompt_chars = len(prompt)
        reply_chars = len(reply.content)
        code = None if reply_chars > reply_char_limit else _submission_code(reply.content)
        exit_reason = "completed"
        ast_reasons: list[str] = []
        if reply_chars > reply_char_limit:
            exit_reason = "reply_char_budget_exceeded"
            code_for_hash = reply.content
            after = TestMeasurement(-2, 0, 1, False, 0.0, "", "reply character budget exceeded")
            hidden = TestMeasurement(-2, 0, 1, False, 0.0, "", "not evaluated")
        elif code is None:
            exit_reason = "malformed"
            code_for_hash = reply.content
            after = TestMeasurement(-2, 0, 1, False, 0.0, "", "malformed submission")
            hidden = TestMeasurement(-2, 0, 1, False, 0.0, "", "not evaluated")
        else:
            code_for_hash = code
            ast_reasons = _strict_ast_gate(code)
            if ast_reasons:
                exit_reason = "ast_blocked"
                after = TestMeasurement(-2, 0, 1, False, 0.0, "", ";".join(ast_reasons))
                hidden = TestMeasurement(-2, 0, 1, False, 0.0, "", "not evaluated")
            else:
                after = _run_test(code, red_source, self.test_timeout_s)
                if after.returncode != 0:
                    exit_reason = "red_failed"
                    hidden = TestMeasurement(-2, 0, 1, False, 0.0, "", "not evaluated")
                else:
                    hidden = _run_test(code, hidden_source, self.test_timeout_s)
                    if hidden.returncode != 0:
                        exit_reason = "hidden_failed"

        run_id = f"pilot-{uuid.uuid4().hex}"
        patch_sha = _sha_text(code_for_hash)
        episode = sign_record({
            "record_type": "episode",
            "task_id": task_id,
            "run_id": run_id,
            "run_kind": "arena",
            "actor": actor,
            "declared_model_id": participant.declared_model_id,
            "model_calls": [{
                "prompt_sha": prompt_sha,
                "reply_sha": _sha_text(reply.content),
                **declarations,
            }],
            "prompt_sha": prompt_sha,
            "patch_sha": patch_sha,
            "stdout_sha": after.evidence()["stdout_sha"],
            "stderr_sha": after.evidence()["stderr_sha"],
            "tests_before": before.evidence(),
            "tests_after": after.evidence(),
            "elapsed_s_measured_by_evaluator": elapsed,
            "tokens_reported_by_participant": reply.reported_tokens,
            "prompt_chars_measured_by_evaluator": prompt_chars,
            "reply_chars_measured_by_evaluator": reply_chars,
            "reply_char_limit": reply_char_limit,
            "attempts": 1,
            "human_touches": 0,
            "exit_reason": exit_reason,
        }, self.secret)
        safety_flags = [
            "participant_isolation_unverified",
            "pilot_no_os_sandbox",
            "regression_not_run",
        ]
        if ast_reasons:
            safety_flags.append("ast_blocked")
        result = sign_record({
            "record_type": "result",
            "task_id": task_id,
            "run_id": run_id,
            "evaluator_version": "pilot-arena-v2",
            "environment_fingerprint": self._environment_fingerprint(),
            "hidden_pass": hidden.passed,
            "hidden_total": hidden.total,
            "red_test_pass": after.returncode == 0 and not after.timed_out,
            "regression_pass": None,
            "safety_flags": safety_flags,
        }, self.secret)
        self.ledger.append(self.secret, episode, result)
        return ContestantOutcome(episode, result)

    def run_pair(
        self,
        task_dir: Path,
        *,
        locked_task_dir: Path,
        aura: TextOnlyParticipant,
        baseline: TextOnlyParticipant,
    ) -> PairOutcome:
        """Give both contestants the exact same prompt bytes, then score privately."""
        task_dir = _resolved_directory(task_dir, "public task directory")
        hidden_source = _read_locked_hidden_source(task_dir, locked_task_dir)
        meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
        prompt, before = build_prompt(task_dir, timeout_s=self.test_timeout_s)
        prompt_sha = _sha_text(prompt)
        red_source = (task_dir / "test_red.py").read_text(encoding="utf-8")
        max_tokens = int(meta["requested_max_output_tokens"])
        prompt_char_limit = int(meta["budget_prompt_chars"])
        reply_char_limit = int(meta["budget_reply_chars"])
        if len(prompt) > prompt_char_limit:
            raise ArenaRunnerError("prompt exceeds evaluator-owned character budget")
        aura_outcome = self._run_one(
            actor="aura", participant=aura, task_id=meta["id"], prompt=prompt,
            prompt_sha=prompt_sha, before=before, red_source=red_source,
            hidden_source=hidden_source, max_tokens=max_tokens,
            reply_char_limit=reply_char_limit,
        )
        baseline_outcome = self._run_one(
            actor="baseline", participant=baseline, task_id=meta["id"], prompt=prompt,
            prompt_sha=prompt_sha, before=before, red_source=red_source,
            hidden_source=hidden_source, max_tokens=max_tokens,
            reply_char_limit=reply_char_limit,
        )
        if aura_outcome.episode["prompt_sha"] != baseline_outcome.episode["prompt_sha"]:
            raise ArenaRunnerError("paired contestants received different prompt bytes")
        return PairOutcome(prompt_sha, aura_outcome, baseline_outcome)


__all__ = [
    "ArenaRunnerError", "ContestantOutcome", "ModelReply", "PairOutcome",
    "LockedEvaluatorStoreError", "ParticipantContractError", "PilotArenaRunner",
    "SecureExecutorUnavailable",
    "SignedJsonlLedger", "TextOnlyParticipant", "build_prompt",
]
