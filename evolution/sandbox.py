"""
evolution/sandbox.py
====================
Sandbox — chạy thử code tự sinh trong môi trường EPHEMERAL CÔ LẬP trước khi duyệt.

Chuẩn Ephemeral Sandboxing:
  1. Ephemeral workspace: mỗi lần chạy một `tempfile.TemporaryDirectory` riêng; kết
     thúc (thành công/lỗi/timeout) ĐỀU tự dọn sạch — không để rác tồn dư.
  2. Timeout "rút điện": chạy trong NHÓM tiến trình riêng; quá giờ -> giết CẢ NHÓM
     (con/cháu) bằng SIGKILL. Vòng lặp vô hạn / fork không thể sống sót.
  3. Env tối giản (allowlist): KHÔNG kế thừa toàn bộ môi trường; chỉ vài biến vô hại
     (PATH, locale, TEMP...). Mọi secret biến môi trường (API key...) bị cắt tuyệt đối.
  4. (POSIX) Giới hạn tài nguyên: RLIMIT_CPU + RLIMIT_AS làm lưới an toàn thứ hai.

ĐỘ TRUNG THỰC: vẫn chạy `-I` (isolated: bỏ qua PYTHONPATH/env/user-site), NHƯNG
harness tự CHÈN ĐÚNG MỘT đường dẫn có kiểm soát — gốc dự án — vào sys.path lúc chạy,
để code tự sinh tuân Hiến pháp (`from core.schemas import ToolResult`,
`import tools.registry`) import được. Cô lập vẫn còn (chỉ mở đúng 1 path), mà smoke
test thì sát thực tế.

THÀNH THẬT: đây là cô lập tiến trình + giới hạn tài nguyên, KHÔNG phải sandbox an ninh
đầy đủ (không seccomp/namespace/container). Lá chắn cuối vẫn là validator + người duyệt.

Chỉ dùng stdlib — test được offline.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("aura.evolution.sandbox")

# Gốc dự án = thư mục cha của evolution/. Đây là path DUY NHẤT được mở vào hộp cát.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Secret tuyệt đối KHÔNG truyền xuống (tài liệu hoá; allowlist bên dưới đã loại sẵn).
_SECRET_ENV_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
    "AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID", "HF_TOKEN", "GITHUB_TOKEN",
)

# CHỈ các biến vô hại này được phép vào hộp cát (allowlist — cắt giảm tối đa).
_ENV_ALLOW: tuple[str, ...] = (
    "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR",
    "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC",
    "NUMBER_OF_PROCESSORS",
)

# Lưới an toàn POSIX.
_CPU_HEADROOM_S = 2
_ADDR_SPACE_LIMIT = 1024 * 1024 * 1024  # 1 GB

# Harness: chèn gốc dự án vào sys.path (1 path có kiểm soát) RỒI import candidate,
# xác nhận có entrypoint tool_*, KHÔNG gọi nó (tránh tác dụng phụ thật).
_SMOKE_HARNESS = """\
import importlib.util, sys, inspect
sys.path.insert(0, r"{project_root}")
spec = importlib.util.spec_from_file_location("aura_candidate", r"{module_path}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
tools = [n for n, o in inspect.getmembers(mod, inspect.isfunction) if n.startswith("tool_")]
if not tools:
    print("SMOKE_FAIL: không tìm thấy hàm tool_*")
    sys.exit(2)
print("SMOKE_OK: " + ",".join(tools))
"""


@dataclass
class SandboxResult:
    """Kết quả chạy thử."""

    ok: bool
    timed_out: bool
    returncode: int
    stdout: str
    stderr: str
    tool_names: list[str]
    duration_s: float = 0.0

    def summary(self) -> str:
        if self.timed_out:
            return (f"⏱️ Sandbox: code chạy quá {self.duration_s:.1f}s "
                    "(treo/vòng lặp vô hạn?) — đã rút điện cả nhóm tiến trình.")
        if self.ok:
            return f"✅ Sandbox: import sạch, tìm thấy tool: {', '.join(self.tool_names)}"
        return f"❌ Sandbox: lỗi (rc={self.returncode}).\n{self.stderr[:500]}"


def _posix_preexec(cpu_seconds: int, mem_bytes: int):
    """Callable đặt RLIMIT trong tiến trình con (chỉ POSIX)."""
    def _apply() -> None:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
            if mem_bytes:
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        except Exception:  # noqa: BLE001
            pass
    return _apply


class Sandbox:
    """Chạy thử code trong subprocess EPHEMERAL: cô lập env + timeout cứng + 1 path mở."""

    def __init__(
        self,
        timeout_s: float = 10.0,
        mem_limit_bytes: int = _ADDR_SPACE_LIMIT,
        project_root: str | os.PathLike | None = None,
    ) -> None:
        self.timeout_s = timeout_s
        self.mem_limit_bytes = mem_limit_bytes
        # Path DUY NHẤT được mở vào hộp cát (để import core.schemas / tools.registry).
        self.project_root = str(Path(project_root).resolve()) if project_root else str(_PROJECT_ROOT)

    # ------------------------------------------------------------------ #
    def _minimal_env(self) -> dict[str, str]:
        """Env TỐI GIẢN theo allowlist (không kế thừa secret biến môi trường)."""
        env: dict[str, str] = {}
        for key in _ENV_ALLOW:
            val = os.environ.get(key)
            if val is not None:
                env[key] = val
        for key in _SECRET_ENV_KEYS:
            env.pop(key, None)
        env["AURA_SANDBOX"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    # ------------------------------------------------------------------ #
    @staticmethod
    def _kill_tree(proc: subprocess.Popen) -> None:
        """Giết CẢ NHÓM tiến trình (rút điện). POSIX: killpg; Windows: kill."""
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
        except (ProcessLookupError, OSError):
            pass
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ #
    def smoke_test(self, code: str) -> SandboxResult:
        """
        Ghi code ra workspace EPHEMERAL, chạy harness import trong subprocess cô lập.

        Bảo đảm: timeout cứng (giết cả nhóm), env tối giản, mở đúng 1 path (gốc dự án),
        dọn sạch sau khi chạy. Không bao giờ ném exception ra ngoài.
        """
        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="aura_sbx_") as tmp:
            module_path = Path(tmp) / "candidate.py"
            module_path.write_text(code, encoding="utf-8")
            harness_path = Path(tmp) / "harness.py"
            harness_path.write_text(
                _SMOKE_HARNESS.format(
                    module_path=str(module_path), project_root=self.project_root
                ),
                encoding="utf-8",
            )

            popen_kwargs: dict = dict(
                cwd=tmp,
                env=self._minimal_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if os.name == "posix":
                popen_kwargs["start_new_session"] = True
                cpu = int(self.timeout_s) + _CPU_HEADROOM_S
                popen_kwargs["preexec_fn"] = _posix_preexec(cpu, self.mem_limit_bytes)
            else:
                flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                if flags:
                    popen_kwargs["creationflags"] = flags

            try:
                py_exe = sys.executable
                if py_exe.lower().endswith("pythonw.exe"):
                    py_exe = py_exe[:-9] + "python.exe"
                elif py_exe.lower().endswith("pythonw"):
                    py_exe = py_exe[:-7] + "python"

                proc = subprocess.Popen(
                    [py_exe, "-I", str(harness_path)], **popen_kwargs
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Sandbox không khởi động được subprocess.")
                return SandboxResult(
                    ok=False, timed_out=False, returncode=-2,
                    stdout="", stderr=str(exc), tool_names=[],
                    duration_s=time.monotonic() - start,
                )

            try:
                stdout, stderr = proc.communicate(timeout=self.timeout_s)
            except subprocess.TimeoutExpired:
                self._kill_tree(proc)
                try:
                    stdout, stderr = proc.communicate(timeout=5)
                except Exception:  # noqa: BLE001
                    stdout, stderr = "", "Timeout"
                return SandboxResult(
                    ok=False, timed_out=True, returncode=-1,
                    stdout=stdout or "", stderr="Timeout: đã giết nhóm tiến trình.",
                    tool_names=[], duration_s=time.monotonic() - start,
                )
            except Exception as exc:  # noqa: BLE001
                self._kill_tree(proc)
                logger.exception("Sandbox lỗi bất ngờ.")
                return SandboxResult(
                    ok=False, timed_out=False, returncode=-2,
                    stdout="", stderr=str(exc), tool_names=[],
                    duration_s=time.monotonic() - start,
                )

            out = (stdout or "").strip()
            ok = proc.returncode == 0 and "SMOKE_OK" in out
            tool_names: list[str] = []
            if ok:
                line = [ln for ln in out.splitlines() if ln.startswith("SMOKE_OK")][-1]
                tool_names = [
                    s.strip() for s in line.replace("SMOKE_OK:", "").split(",") if s.strip()
                ]
            return SandboxResult(
                ok=ok, timed_out=False, returncode=proc.returncode,
                stdout=stdout or "", stderr=stderr or "", tool_names=tool_names,
                duration_s=time.monotonic() - start,
            )
        # `with` đã dọn TemporaryDirectory — workspace ephemeral biến mất hoàn toàn.


__all__ = ["Sandbox", "SandboxResult"]
