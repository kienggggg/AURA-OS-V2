"""Local screen observation and owner-scoped desktop automation for AURA.

The module deliberately separates observation from side effects:

* Window metadata is sampled cheaply.
* Screenshots stay in RAM and OCR is loaded only for an explicit task.
* A one-time owner switch permits low-risk actions in allow-listed windows.
* Banking, credentials, OTP/CAPTCHA, payments and irreversible external
  submissions are always blocked by the default policy.
* PyAutoGUI's corner fail-safe remains enabled as a physical kill switch.
"""

from __future__ import annotations

import ctypes
import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unicodedata
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Protocol

from core.config import PROJECT_ROOT, settings
from core.redact import redact

logger = logging.getLogger("aura.desktop_autopilot")

_STATE_PATH = PROJECT_ROOT / "data" / "ledger" / "desktop_autopilot.json"
_TASKS_PATH = PROJECT_ROOT / "data" / "ledger" / "desktop_autopilot_tasks.json"
_AUDIT_PATH = PROJECT_ROOT / "data" / "ledger" / "desktop_autopilot_audit.jsonl"
_LOCK = threading.RLock()
_RUNTIME_AUTOPILOT: "DesktopAutopilot | None" = None

_SAFE_PROJECT_SUFFIXES = frozenset({".py", ".md", ".json", ".js", ".html", ".css", ".txt"})
_SAFE_PROJECT_ROOTS = frozenset(
    {"core", "interface", "factory", "skills", "tools", "tests", "brains", "agents"}
)
_DEFAULT_SELF_FILES = (
    # Sổ mổ ĐỨNG ĐẦU: AURA phải biết ai đã làm gì với chính nó trước đã.
    "docs/SO_MO_AURA.md",
    "AURA_COMMAND.md",
    "AURA_STATE.md",
    "CONTEXT.md",
    "ARCHITECTURE_v2.md",
)
_ALLOWED_ACTIONS = frozenset(
    {"observe", "click", "click_text", "type_text", "press", "hotkey", "scroll", "wait"}
)
_NAVIGATION_KEYS = frozenset(
    {
        "tab",
        "shift",
        "esc",
        "escape",
        "up",
        "down",
        "left",
        "right",
        "pageup",
        "pagedown",
        "home",
        "end",
        "space",
        "enter",
        "return",
        "backspace",
        "delete",
    }
)
_SAFE_HOTKEYS = frozenset(
    {
        ("ctrl", "a"),
        ("ctrl", "c"),
        ("ctrl", "l"),
        ("ctrl", "v"),
        ("ctrl", "f"),
        ("ctrl", "tab"),
        ("ctrl", "shift", "tab"),
        ("shift", "tab"),
    }
)
_SENSITIVE_PATTERN = re.compile(
    r"(?i)(?:sk-[a-z0-9_-]{8,}|AIza[a-z0-9_-]{12,}|ghp_[a-z0-9]{12,}|"
    r"hf_[a-z0-9]{12,}|\b\d{4,8}\b)"
)


def _csv_tokens(value: str) -> tuple[str, ...]:
    return tuple(token.strip().casefold() for token in str(value or "").split(",") if token.strip())


def _normalize_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", str(value or "").casefold())
    return " ".join("".join(ch for ch in folded if not unicodedata.combining(ch)).split())


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        dir=path.parent,
        delete=False,
        encoding="utf-8",
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        temp_name = handle.name
    os.replace(temp_name, path)


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _append_audit(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


class DesktopDriver(Protocol):
    def active_window_title(self) -> str: ...
    def screen_size(self) -> tuple[int, int]: ...
    def screenshot(self): ...
    def click(self, x: int, y: int) -> None: ...
    def type_text(self, text: str) -> None: ...
    def press(self, key: str) -> None: ...
    def hotkey(self, *keys: str) -> None: ...
    def scroll(self, amount: int) -> None: ...


class LocalPyAutoGuiDriver:
    """Thin, lazy wrapper so importing AURA does not seize the desktop."""

    def __init__(self) -> None:
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.35
        self._gui = pyautogui

    @staticmethod
    def active_window_title() -> str:
        if os.name != "nt":
            return ""
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return ""
            length = user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            return str(buffer.value or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    def screen_size(self) -> tuple[int, int]:
        size = self._gui.size()
        return int(size.width), int(size.height)

    def screenshot(self):
        return self._gui.screenshot()

    def click(self, x: int, y: int) -> None:
        self._gui.click(int(x), int(y))

    def type_text(self, text: str) -> None:
        value = str(text)
        try:
            import pyperclip

            previous = pyperclip.paste()
            pyperclip.copy(value)
            self._gui.hotkey("ctrl", "v")
            pyperclip.copy(previous)
        except Exception:  # noqa: BLE001
            self._gui.write(value, interval=0.02)

    def press(self, key: str) -> None:
        self._gui.press(str(key))

    def hotkey(self, *keys: str) -> None:
        self._gui.hotkey(*keys)

    def scroll(self, amount: int) -> None:
        self._gui.scroll(int(amount))


class LazyEasyOCR:
    """OCR remains unloaded until a task actually needs visible text."""

    def __init__(self, languages: tuple[str, ...] | None = None) -> None:
        self.languages = languages or _csv_tokens(
            getattr(settings, "desktop_autopilot_ocr_languages", "vi,en")
        )
        self._reader = None

    def _get_reader(self):
        if self._reader is None:
            import easyocr

            self._reader = easyocr.Reader(
                list(self.languages or ("en",)),
                gpu=False,
                verbose=False,
                download_enabled=False,
            )
        return self._reader

    def read(self, image) -> list[dict[str, Any]]:
        import numpy as np

        results = self._get_reader().readtext(np.asarray(image), detail=1, paragraph=False)
        boxes: list[dict[str, Any]] = []
        for box, text, confidence in results:
            points = [[int(float(p[0])), int(float(p[1]))] for p in box]
            boxes.append(
                {
                    "text": str(text or "").strip(),
                    "confidence": float(confidence or 0.0),
                    "box": points,
                }
            )
        return boxes


class LocalTesseractOCR:
    """Lightweight OCR through stdin/stdout; screenshots never touch disk."""

    def __init__(self, executable: str | None = None) -> None:
        candidates = (
            executable,
            shutil.which("tesseract"),
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        )
        self.executable = next(
            (str(path) for path in candidates if path and Path(path).is_file()),
            "",
        )

    @property
    def available(self) -> bool:
        return bool(self.executable)

    @staticmethod
    def _parse_tsv(tsv: str) -> list[dict[str, Any]]:
        lines: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for raw in str(tsv or "").splitlines()[1:]:
            fields = raw.split("\t", 11)
            if len(fields) != 12:
                continue
            text = fields[11].strip()
            if not text:
                continue
            try:
                left, top, width, height = map(int, fields[6:10])
                confidence = max(0.0, float(fields[10])) / 100.0
            except ValueError:
                continue
            key = (fields[2], fields[3], fields[4])
            lines.setdefault(key, []).append(
                {
                    "text": text,
                    "confidence": confidence,
                    "left": left,
                    "top": top,
                    "right": left + width,
                    "bottom": top + height,
                }
            )

        boxes: list[dict[str, Any]] = []
        for words in lines.values():
            left = min(word["left"] for word in words)
            top = min(word["top"] for word in words)
            right = max(word["right"] for word in words)
            bottom = max(word["bottom"] for word in words)
            boxes.append(
                {
                    "text": " ".join(word["text"] for word in words),
                    "confidence": sum(word["confidence"] for word in words) / len(words),
                    "box": [[left, top], [right, top], [right, bottom], [left, bottom]],
                }
            )
        return boxes

    def read(self, image) -> list[dict[str, Any]]:
        if not self.available:
            raise FileNotFoundError("Không tìm thấy Tesseract OCR cục bộ.")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        completed = subprocess.run(
            [
                self.executable,
                "stdin",
                "stdout",
                "-l",
                "eng",
                "--psm",
                "11",
                "tsv",
            ],
            input=buffer.getvalue(),
            capture_output=True,
            timeout=20,
            check=False,
            creationflags=creationflags,
        )
        if completed.returncode != 0:
            error = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Tesseract OCR lỗi: {error[:240]}")
        return self._parse_tsv(completed.stdout.decode("utf-8", errors="replace"))


class DesktopSafetyPolicy:
    """Fail-closed policy for a pre-authorized desktop session."""

    def __init__(
        self,
        allowed_windows: tuple[str, ...] | None = None,
        blocked_terms: tuple[str, ...] | None = None,
    ) -> None:
        self.allowed_windows = allowed_windows or _csv_tokens(
            getattr(
                settings,
                "desktop_autopilot_allowed_windows",
                "aura,codex,chatgpt,chrome,edge,facebook,tiktok,payhip,upwork,"
                "file explorer,explorer,notepad,visual studio code,vscode",
            )
        )
        self.blocked_terms = blocked_terms or _csv_tokens(
            getattr(
                settings,
                "desktop_autopilot_blocked_terms",
                "mb bank,mbbank,banking,ngân hàng,password,mật khẩu,passcode,"
                "otp,captcha,2fa,authenticator,thanh toán,payment,chuyển tiền,transfer",
            )
        )
        self.external_terms = _csv_tokens(
            "đăng,publish,post,gửi,send,nộp,submit,mua,buy,đặt hàng,order,"
            "xóa,delete,gỡ,uninstall,cài đặt,install,xác nhận thanh toán,confirm payment"
        )

    def classify_window(self, title: str) -> str:
        normalized = _normalize_text(title)
        if not normalized:
            return "unknown"
        if any(_normalize_text(term) in normalized for term in self.blocked_terms):
            return "blocked"
        if any(_normalize_text(term) in normalized for term in self.allowed_windows):
            return "allowed"
        return "unknown"

    def validate_window(self, title: str, expected: tuple[str, ...] = ()) -> tuple[bool, str]:
        category = self.classify_window(title)
        if category != "allowed":
            return False, f"cửa sổ {category}; không được tự thao tác"
        normalized = _normalize_text(title)
        if expected and not any(_normalize_text(term) in normalized for term in expected):
            return False, "cửa sổ hiện tại không khớp task"
        return True, ""

    def validate_action(
        self,
        action: dict[str, Any],
        *,
        title: str,
        approved_scopes: set[str],
        task_scope: str,
    ) -> tuple[bool, str]:
        kind = str(action.get("kind") or "").strip().lower()
        if kind not in _ALLOWED_ACTIONS:
            return False, f"action không hỗ trợ: {kind}"
        if kind == "observe":
            return True, ""
        ok, reason = self.validate_window(
            title,
            tuple(str(v) for v in action.get("expected_window_keywords") or ()),
        )
        if not ok:
            return False, reason

        visible_label = " ".join(
            str(action.get(key) or "") for key in ("label", "target", "key")
        )
        normalized_label = _normalize_text(visible_label)
        if any(_normalize_text(term) in normalized_label for term in self.blocked_terms):
            return False, "action chạm vùng nhạy cảm"
        if any(_normalize_text(term) in normalized_label for term in self.external_terms):
            if task_scope != "external_submit" or "external_submit" not in approved_scopes:
                return False, "gửi/đăng/xóa/thanh toán chưa nằm trong phạm vi được cấp một lần"

        if kind == "type_text":
            text = str(action.get("text") or "")
            if not text:
                return False, "không có nội dung để gõ"
            if _SENSITIVE_PATTERN.search(text):
                return False, "không tự gõ chuỗi có dạng secret/OTP"
        if kind == "press":
            key = str(action.get("key") or "").strip().lower()
            if key in {"enter", "return"} and task_scope not in {"local_ui", "external_submit"}:
                return False, "phím Enter có thể gửi dữ liệu"
            if key in {"enter", "return"} and task_scope == "external_submit":
                if "external_submit" not in approved_scopes:
                    return False, "phím Enter có thể gửi dữ liệu"
            elif key not in _NAVIGATION_KEYS:
                return False, f"phím chưa được allowlist: {key}"
        if kind == "hotkey":
            keys = tuple(str(v).strip().lower() for v in action.get("keys") or ())
            if keys not in _SAFE_HOTKEYS:
                return False, f"phím tắt chưa được allowlist: {'+'.join(keys)}"
        return True, ""


class DesktopAutopilot:
    """Persistent low-risk task queue executed by the daemon."""

    def __init__(
        self,
        *,
        driver: DesktopDriver | None = None,
        ocr: Any | None = None,
        memory: Any | None = None,
        state_path: Path | None = None,
        tasks_path: Path | None = None,
        audit_path: Path | None = None,
        project_root: Path | None = None,
        policy: DesktopSafetyPolicy | None = None,
    ) -> None:
        self.driver = driver
        self.ocr = ocr
        self.memory = memory
        self.state_path = state_path or _STATE_PATH
        self.tasks_path = tasks_path or _TASKS_PATH
        self.audit_path = audit_path or _AUDIT_PATH
        self.project_root = (project_root or PROJECT_ROOT).resolve()
        self.policy = policy or DesktopSafetyPolicy()

    def _driver(self) -> DesktopDriver:
        if self.driver is None:
            self.driver = LocalPyAutoGuiDriver()
        return self.driver

    def _ocr(self):
        if self.ocr is None:
            lightweight = LocalTesseractOCR()
            self.ocr = lightweight if lightweight.available else LazyEasyOCR()
        return self.ocr

    def _default_state(self) -> dict[str, Any]:
        return {
            "owner_enabled": False,
            "paused": False,
            "emergency_stop": False,
            "approved_scopes": ["local_ui", "research", "drafting"],
            "last_observed_at": 0,
            "last_window": "",
            "last_window_category": "unknown",
            "last_action_at": 0,
            "last_error": "",
            "updated_at": int(time.time()),
        }

    def _state(self) -> dict[str, Any]:
        state = _read_json(self.state_path, self._default_state())
        if not isinstance(state, dict):
            return self._default_state()
        return {**self._default_state(), **state}

    def _write_state(self, state: dict[str, Any]) -> dict[str, Any]:
        state["updated_at"] = int(time.time())
        _atomic_write_json(self.state_path, state)
        return state

    def _tasks(self) -> list[dict[str, Any]]:
        tasks = _read_json(self.tasks_path, [])
        return tasks if isinstance(tasks, list) else []

    def status(self) -> dict[str, Any]:
        state = self._state()
        tasks = self._tasks()
        counts: dict[str, int] = {}
        for task in tasks:
            task_status = str(task.get("status") or "unknown")
            counts[task_status] = counts.get(task_status, 0) + 1
        return {
            **state,
            "capability_version": "desktop-autopilot-telegram-v2",
            "runtime_enabled": bool(
                getattr(settings, "desktop_autopilot_enabled", True)
                and state.get("owner_enabled")
                and not state.get("paused")
                and not state.get("emergency_stop")
            ),
            "task_counts": counts,
            "memory_connected": self.memory is not None,
            "screenshot_retention": False,
            "physical_kill_switch": "move_mouse_to_any_corner",
        }

    def set_control(self, action: str, *, confirmed_by_owner: bool) -> dict[str, Any]:
        if not confirmed_by_owner:
            raise PermissionError("Chỉ Chủ AURA mới được đổi trạng thái Desktop Autopilot.")
        action = str(action or "").strip().lower()
        with _LOCK:
            state = self._state()
            if action == "enable":
                state["owner_enabled"] = True
                state["paused"] = False
                state["emergency_stop"] = False
            elif action == "disable":
                state["owner_enabled"] = False
                state["paused"] = True
            elif action == "pause":
                state["paused"] = True
            elif action == "resume":
                state["paused"] = False
            elif action == "emergency_stop":
                state["emergency_stop"] = True
                state["paused"] = True
            elif action == "clear_emergency":
                state["emergency_stop"] = False
                state["paused"] = False
            else:
                raise ValueError(f"Điều khiển không hợp lệ: {action}")
            self._write_state(state)
            self._audit("control", {"control": action, "ok": True})
            return self.status()

    def observe(self, *, include_ocr: bool = False) -> dict[str, Any]:
        driver = self._driver()
        title = driver.active_window_title()
        category = self.policy.classify_window(title)
        width, height = driver.screen_size()
        safe_title = "[SENSITIVE_WINDOW]" if category == "blocked" else redact(title)[:200]
        observation: dict[str, Any] = {
            "observed_at": int(time.time()),
            "window_title": safe_title,
            "window_category": category,
            "screen_size": [width, height],
            "ocr_performed": False,
            "ocr_text": "",
        }
        if include_ocr and category == "allowed":
            boxes = self._read_ocr_boxes()
            observation["ocr_performed"] = True
            observation["ocr_text"] = redact(" ".join(box["text"] for box in boxes))[:4000]

        with _LOCK:
            state = self._state()
            state["last_observed_at"] = observation["observed_at"]
            state["last_window"] = safe_title
            state["last_window_category"] = category
            self._write_state(state)
        return observation

    def _read_ocr_boxes(self) -> list[dict[str, Any]]:
        image = self._driver().screenshot()
        return list(self._ocr().read(image))

    def _find_text(self, target: str) -> tuple[int, int] | None:
        target_norm = _normalize_text(target)
        best: tuple[float, dict[str, Any]] | None = None
        for item in self._read_ocr_boxes():
            text_norm = _normalize_text(item.get("text", ""))
            if not text_norm:
                continue
            if target_norm in text_norm or text_norm in target_norm:
                score = 1.0
            else:
                score = SequenceMatcher(None, target_norm, text_norm).ratio()
            score *= max(0.2, float(item.get("confidence") or 0.0))
            if best is None or score > best[0]:
                best = (score, item)
        if best is None or best[0] < 0.48:
            return None
        points = best[1].get("box") or []
        if len(points) < 2:
            return None
        xs = [int(point[0]) for point in points]
        ys = [int(point[1]) for point in points]
        return sum(xs) // len(xs), sum(ys) // len(ys)

    def enqueue_task(
        self,
        *,
        title: str,
        actions: list[dict[str, Any]],
        scope: str = "local_ui",
        expected_window_keywords: list[str] | None = None,
    ) -> dict[str, Any]:
        if not title.strip() or not actions:
            raise ValueError("Desktop task cần title và ít nhất một action.")
        max_actions = int(getattr(settings, "desktop_autopilot_max_actions_per_task", 25))
        if len(actions) > max_actions:
            raise ValueError(f"Task vượt trần {max_actions} action.")
        state = self._state()
        approved_scopes = set(str(v) for v in state.get("approved_scopes") or [])
        if scope not in approved_scopes:
            raise PermissionError(f"Scope '{scope}' chưa được Chủ cấp một lần.")
        cleaned_actions: list[dict[str, Any]] = []
        for action in actions:
            if not isinstance(action, dict):
                raise TypeError("Mỗi desktop action phải là object.")
            kind = str(action.get("kind") or "").strip().lower()
            if kind not in _ALLOWED_ACTIONS:
                raise ValueError(f"Action không hỗ trợ: {kind}")
            cleaned = dict(action)
            cleaned["kind"] = kind
            if expected_window_keywords and "expected_window_keywords" not in cleaned:
                cleaned["expected_window_keywords"] = list(expected_window_keywords)
            if kind == "type_text" and _SENSITIVE_PATTERN.search(str(cleaned.get("text") or "")):
                raise PermissionError("Không lưu task chứa chuỗi có dạng secret/OTP.")
            cleaned_actions.append(cleaned)
        task = {
            "id": f"DT-{uuid.uuid4().hex[:12]}",
            "title": " ".join(title.split())[:200],
            "scope": scope,
            "actions": cleaned_actions,
            "status": "queued",
            "created_at": int(time.time()),
            "started_at": 0,
            "finished_at": 0,
            "error": "",
        }
        with _LOCK:
            tasks = self._tasks()
            tasks.append(task)
            _atomic_write_json(self.tasks_path, tasks)
        self._audit("task_queued", {"task_id": task["id"], "scope": scope, "ok": True})
        return {key: value for key, value in task.items() if key != "actions"} | {
            "action_count": len(cleaned_actions)
        }

    def run_next(self) -> dict[str, Any]:
        with _LOCK:
            state = self._state()
            if not getattr(settings, "desktop_autopilot_enabled", True):
                return {"status": "blocked", "reason": "disabled_by_config"}
            if not state.get("owner_enabled"):
                return {"status": "blocked", "reason": "owner_not_enabled"}
            if state.get("paused") or state.get("emergency_stop"):
                return {"status": "blocked", "reason": "paused_or_emergency_stop"}
            tasks = self._tasks()
            index = next(
                (i for i, task in enumerate(tasks) if task.get("status") == "queued"),
                None,
            )
            if index is None:
                return {"status": "idle"}
            task = tasks[index]
            task["status"] = "running"
            task["started_at"] = int(time.time())
            _atomic_write_json(self.tasks_path, tasks)

        try:
            self._execute_task(task, state)
            final_status = "completed"
            error = ""
        except Exception as exc:  # noqa: BLE001
            final_status = "failed"
            error = str(exc)
            logger.warning("Desktop task %s thất bại: %s", task.get("id"), exc)

        with _LOCK:
            tasks = self._tasks()
            for row in tasks:
                if row.get("id") == task.get("id"):
                    row["status"] = final_status
                    row["finished_at"] = int(time.time())
                    row["error"] = error[:500]
                    break
            _atomic_write_json(self.tasks_path, tasks)
            state = self._state()
            state["last_action_at"] = int(time.time())
            state["last_error"] = error[:500]
            self._write_state(state)
        self._audit(
            "task_finished",
            {
                "task_id": task.get("id"),
                "scope": task.get("scope"),
                "ok": final_status == "completed",
                "error": error[:300],
            },
        )
        return {
            "status": final_status,
            "task_id": task.get("id"),
            "title": task.get("title"),
            "error": error,
        }

    def _execute_task(self, task: dict[str, Any], state: dict[str, Any]) -> None:
        driver = self._driver()
        approved_scopes = set(str(v) for v in state.get("approved_scopes") or [])
        width, height = driver.screen_size()
        for index, action in enumerate(task.get("actions") or []):
            current_state = self._state()
            if current_state.get("paused") or current_state.get("emergency_stop"):
                raise RuntimeError("Desktop Autopilot đã bị dừng trong lúc chạy.")
            title = driver.active_window_title()
            ok, reason = self.policy.validate_action(
                action,
                title=title,
                approved_scopes=approved_scopes,
                task_scope=str(task.get("scope") or ""),
            )
            if not ok:
                raise PermissionError(reason)

            kind = str(action["kind"])
            self._dispatch_action(action, driver, width, height)

            self._audit(
                "action",
                {
                    "task_id": task.get("id"),
                    "index": index,
                    "kind": kind,
                    "label": redact(str(action.get("label") or action.get("target") or ""))[:120],
                    "window_hash": hashlib.sha256(title.encode("utf-8")).hexdigest()[:12],
                    "ok": True,
                },
            )

    def _dispatch_action(self, action: dict[str, Any], driver, width: int, height: int) -> None:
        """Thực thi ĐÚNG MỘT action đã qua validate. Tách ra để vòng lặp thao tác
        (desktop_operator) dùng chung, không viết lại tay/chân."""
        kind = str(action["kind"])
        if kind == "observe":
            self.observe(include_ocr=bool(action.get("include_ocr")))
        elif kind == "click_text":
            point = self._find_text(str(action.get("target") or ""))
            if point is None:
                raise LookupError(f"Không tìm thấy chữ: {action.get('target')}")
            driver.click(*point)
        elif kind == "click":
            x, y = int(action.get("x") or -1), int(action.get("y") or -1)
            if not (0 <= x < width and 0 <= y < height):
                raise ValueError("Tọa độ click nằm ngoài màn hình.")
            if not str(action.get("label") or "").strip():
                raise ValueError("Click theo tọa độ bắt buộc có label kiểm toán.")
            driver.click(x, y)
        elif kind == "type_text":
            driver.type_text(str(action.get("text") or ""))
        elif kind == "press":
            driver.press(str(action.get("key") or ""))
        elif kind == "hotkey":
            driver.hotkey(*(str(v) for v in action.get("keys") or ()))
        elif kind == "scroll":
            driver.scroll(int(action.get("amount") or 0))
        elif kind == "wait":
            time.sleep(min(5.0, max(0.0, float(action.get("seconds") or 0.5))))

    def run_single_action(self, action: dict[str, Any], *, scope: str = "local_ui") -> None:
        """Chạy MỘT action lẻ, có validate an toàn đầy đủ (cửa sổ nhạy cảm,
        external_submit, secret). Dùng cho vòng lặp thao tác từng-bước-một."""
        state = self._state()
        if not state.get("owner_enabled"):
            raise PermissionError("Chủ chưa bật tự thao tác.")
        if state.get("paused") or state.get("emergency_stop"):
            raise RuntimeError("Desktop Autopilot đang bị dừng.")
        approved_scopes = set(str(v) for v in state.get("approved_scopes") or [])
        driver = self._driver()
        title = driver.active_window_title()
        ok, reason = self.policy.validate_action(
            action, title=title, approved_scopes=approved_scopes, task_scope=scope,
        )
        if not ok:
            raise PermissionError(reason)
        width, height = driver.screen_size()
        self._dispatch_action(action, driver, width, height)
        self._audit("single_action", {
            "kind": str(action.get("kind")),
            "label": redact(str(action.get("label") or action.get("target") or ""))[:120],
            "window_hash": hashlib.sha256(title.encode("utf-8")).hexdigest()[:12],
            "ok": True,
        })

    def read_self_context(
        self,
        *,
        paths: list[str] | None = None,
        max_chars: int = 12_000,
    ) -> dict[str, Any]:
        selected = paths or list(_DEFAULT_SELF_FILES)
        snippets: list[dict[str, str]] = []
        remaining = max(1000, min(int(max_chars), 40_000))
        for relative in selected[:8]:
            path = (self.project_root / str(relative)).resolve()
            try:
                rel = path.relative_to(self.project_root)
            except ValueError:
                continue
            if not path.is_file() or path.suffix.casefold() not in _SAFE_PROJECT_SUFFIXES:
                continue
            if rel.parts and rel.parts[0] not in _SAFE_PROJECT_ROOTS and len(rel.parts) > 1:
                continue
            if any(part.casefold() in {".git", ".env", "api_keys", "chroma", "ledger"} for part in rel.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            excerpt = text[-remaining:] if path.name in {"AURA_COMMAND.md", "AURA_STATE.md"} else text[:remaining]
            excerpt = redact(excerpt)
            snippets.append({"path": str(rel), "text": excerpt})
            remaining -= len(excerpt)
            if remaining <= 0:
                break

        source_files = [
            path
            for root_name in ("core", "interface", "factory", "skills")
            for path in (self.project_root / root_name).rglob("*")
            if path.is_file() and path.suffix.casefold() in _SAFE_PROJECT_SUFFIXES
        ]
        latest = sorted(source_files, key=lambda p: p.stat().st_mtime, reverse=True)[:12]
        return {
            "files": snippets,
            "source_file_count": len(source_files),
            "recently_changed": [str(path.relative_to(self.project_root)) for path in latest],
        }

    def recall_local_memory(self, query: str, *, k: int = 3) -> dict[str, Any]:
        if self.memory is None:
            return {"available": False, "records": []}
        query = str(query or "AURA current task and owner preferences").strip()
        records: list[dict[str, str]] = []
        methods = (
            ("conversation", "recall_context"),
            ("preferences", "recall_preferences"),
            ("rules", "recall_rules"),
            ("knowledge", "recall_knowledge"),
            ("profile", "recall_profile"),
        )
        for collection, method_name in methods:
            method = getattr(self.memory, method_name, None)
            if method is None:
                continue
            try:
                for record in method(query, k=max(1, min(int(k), 5))):
                    records.append(
                        {
                            "collection": collection,
                            "role": str(getattr(record, "role", "")),
                            "text": redact(str(getattr(record, "text", "")))[:1200],
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Không recall được %s: %s", collection, exc)
        return {"available": True, "records": records[:20]}

    def build_local_context(
        self,
        query: str,
        *,
        paths: list[str] | None = None,
    ) -> dict[str, Any]:
        observation = self.observe(include_ocr=False)
        return {
            "screen": observation,
            "self": self.read_self_context(paths=paths),
            "memory": self.recall_local_memory(query),
            "local_only": True,
        }

    def _audit(self, event: str, payload: dict[str, Any]) -> None:
        with _LOCK:
            _append_audit(
                self.audit_path,
                {"ts": int(time.time()), "event": event, **payload},
            )


def _normalize_intent(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text or "").casefold()).replace("đ", "d")
    return " ".join(
        "".join(ch for ch in folded if not unicodedata.combining(ch)).split()
    )


def is_screen_observation_request(text: str) -> bool:
    """True khi Chủ HỎI 'màn hình đang hiện gì' — để route vào MẮT THẬT thay vì
    để LLM đoán. Không bắt câu ra lệnh tắt/khoá màn hình."""
    normalized = _normalize_intent(text)
    screen_terms = ("man hinh", "screen", "desktop", "cua so laptop", "cua so may tinh")
    observe_terms = (
        "dang co gi", "dang co nhung gi", "dang hien", "hien thi gi", "nhin",
        "xem", "doc", "quan sat", "thay gi", "tren laptop", "tren may tinh",
    )
    control_terms = ("tat man hinh", "khoa man hinh", "ngu man hinh", "shutdown")
    return (
        any(t in normalized for t in screen_terms)
        and any(t in normalized for t in observe_terms)
        and not any(t in normalized for t in control_terms)
    )


def describe_current_screen() -> str:
    """Đọc màn hình THẬT (OCR) và mô tả trung thực. Dùng chung cho Telegram VÀ
    bong bóng mascot. TUYỆT ĐỐI không đoán khi chưa OCR — mù thì nói mù.

    Đây là hàm ĐỒNG BỘ (OCR chặn); phía async phải gọi qua asyncio.to_thread.
    """
    try:
        autopilot = get_runtime_autopilot()
        status = autopilot.status()
        if not status.get("owner_enabled"):
            return (
                "👁️ Mắt màn hình chưa được Chủ bật. Mở tab 'Tự thao tác' trên "
                "dashboard và bấm 'Bật tự thao tác' một lần."
            )
        observation = autopilot.observe(include_ocr=True)
    except Exception as exc:  # noqa: BLE001 — báo thật, KHÔNG fallback đoán
        logger.warning("Đọc màn hình lỗi: %s", exc)
        return f"⚠️ AURA chưa đọc được màn hình thật: {exc}"

    category = str(observation.get("window_category") or "unknown")
    title = str(observation.get("window_title") or "không xác định")
    if category == "blocked":
        return (
            "🔒 Cửa sổ hiện tại thuộc vùng nhạy cảm "
            "(ngân hàng/mật khẩu/OTP/thanh toán). AURA đã không chụp và không OCR."
        )
    if category != "allowed":
        return (
            f"⚠️ AURA thấy cửa sổ '{title}' nhưng cửa sổ này chưa nằm trong "
            "danh sách được phép, nên không đọc nội dung."
        )
    if not observation.get("ocr_performed"):
        return (
            f"⚠️ AURA nhận ra cửa sổ '{title}' nhưng OCR chưa thực sự chạy; "
            "không có dữ liệu để mô tả màn hình."
        )
    ocr_text = " ".join(str(observation.get("ocr_text") or "").split())
    if not ocr_text:
        return (
            f"👁️ Cửa sổ hiện tại: {title}\n"
            "OCR đã chạy nhưng không đọc thấy chữ rõ ràng trên màn hình."
        )
    width, height = (observation.get("screen_size") or ["?", "?"])[:2]
    return (
        "👁️ MÀN HÌNH LAPTOP HIỆN TẠI\n"
        f"Cửa sổ: {title}\n"
        f"Kích thước: {width} × {height}\n\n"
        f"Chữ AURA đọc được:\n{ocr_text[:3000]}"
    )


def set_runtime_autopilot(autopilot: DesktopAutopilot | None) -> None:
    global _RUNTIME_AUTOPILOT
    _RUNTIME_AUTOPILOT = autopilot


def get_runtime_autopilot() -> DesktopAutopilot:
    global _RUNTIME_AUTOPILOT
    if _RUNTIME_AUTOPILOT is None:
        _RUNTIME_AUTOPILOT = DesktopAutopilot()
    return _RUNTIME_AUTOPILOT


__all__ = [
    "DesktopAutopilot",
    "DesktopSafetyPolicy",
    "LazyEasyOCR",
    "LocalTesseractOCR",
    "LocalPyAutoGuiDriver",
    "get_runtime_autopilot",
    "set_runtime_autopilot",
    "is_screen_observation_request",
    "describe_current_screen",
]
