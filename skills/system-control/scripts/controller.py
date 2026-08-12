"""
skills/system-control/scripts/controller.py
===========================================
System Control — "Tay chân" điều khiển laptop của AURA (LỚP LOGIC, Level 4).

Hành động TƯỜNG MINH (không shell tự do) + rào cản an toàn:
  - Confine thao tác file trong thư mục cho phép (HOME/CWD/TEMP/data AURA).
  - CHẶN thư mục hệ thống + path traversal ('..').
  - delete -> Thùng rác (send2trash) thay vì xoá cứng; xoá cứng phải `force=True` + an toàn.
  - open_app theo allowlist; KHÔNG `shell=True`, KHÔNG eval/exec.

Đây là skill TIN CẬY (hand-written), cố ý được phép chạm OS — khác với code TỰ SINH
(bị ASTValidator/CONTEXT §5 cấm subprocess). Lá chắn: allowlist + path-safety + cổng
VIBE DIFF duyệt từng hành động ở tầng Orchestrator.

Tool công khai `tool_system_control(...)` luôn trả ToolResult (không ném exception).
"""

from __future__ import annotations

import sys
from pathlib import Path

# skills/system-control/scripts/controller.py -> parents[3] = gốc dự án.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json
import logging
import os
import re
import shutil
import tempfile
import webbrowser

from core.schemas import ToolResult

logger = logging.getLogger("aura.skills.system_control")

# Thư mục hệ thống nhạy cảm — CHẶN mọi thao tác mutating bên trong.
_BLOCKED_PREFIXES: tuple[str, ...] = (
    "/etc", "/usr", "/bin", "/sbin", "/boot", "/sys", "/proc", "/var", "/dev", "/root",
    "c:\\windows", "c:\\program files", "c:\\program files (x86)", "%systemroot%",
)

# App được phép mở (tên thân thiện -> lệnh theo nền tảng).
_APP_ALLOWLIST: dict[str, dict[str, list[str]]] = {
    "notepad":     {"win": ["notepad.exe"], "posix": ["xdg-open"]},
    "calculator":  {"win": ["calc.exe"], "posix": ["gnome-calculator"]},
    "calc":        {"win": ["calc.exe"], "posix": ["gnome-calculator"]},
    "explorer":    {"win": ["explorer.exe"], "posix": ["xdg-open"]},
    "chrome":      {"win": ["chrome"], "posix": ["google-chrome"]},
    "edge":        {"win": ["msedge"], "posix": ["microsoft-edge"]},
    "firefox":     {"win": ["firefox"], "posix": ["firefox"]},
    "code":        {"win": ["code"], "posix": ["code"]},
}

_VALID_ACTIONS = (
    "sysinfo", "list_dir", "mkdir", "move", "rename", "copy",
    "delete", "open_app", "open_path", "open_url",
)
_MUTATING = frozenset({"mkdir", "move", "rename", "copy", "delete"})


# ---------------------------------------------------------------------------
# An toàn đường dẫn
# ---------------------------------------------------------------------------
def _allowed_roots() -> list[Path]:
    roots = [Path.home(), Path.cwd(), Path(tempfile.gettempdir()), _PROJECT_ROOT / "data"]
    out: list[Path] = []
    for r in roots:
        try:
            out.append(r.resolve())
        except OSError:
            pass
    return out


def _is_blocked(path: Path) -> bool:
    low = str(path).lower().replace("\\", "\\")  # giữ nguyên để so prefix windows
    low_norm = str(path).lower()
    return any(low_norm.startswith(pref) for pref in _BLOCKED_PREFIXES)


def _safe_path(raw: str, *, must_exist: bool = False, for_write: bool = False) -> Path:
    """
    Chuẩn hoá + kiểm an toàn một đường dẫn. Ném ValueError nếu vi phạm.

    - Bung '~'; resolve tuyệt đối (chống '..').
    - CHẶN thư mục hệ thống.
    - Với thao tác GHI/SỬA (for_write): bắt buộc nằm trong allowed_roots.
    """
    if not raw or not isinstance(raw, str):
        raise ValueError("Thiếu đường dẫn.")
    if ".." in raw.replace("\\", "/").split("/"):
        raise ValueError(f"Từ chối path traversal ('..'): {raw!r}")
    p = Path(os.path.expanduser(raw)).resolve()
    if _is_blocked(p):
        raise ValueError(f"CHẶN: đường dẫn hệ thống nhạy cảm: {p}")
    if for_write:
        roots = _allowed_roots()
        if not any(_within(p, r) for r in roots):
            raise ValueError(
                f"CHẶN: '{p}' nằm ngoài thư mục cho phép (HOME/CWD/TEMP/data)."
            )
    if must_exist and not p.exists():
        raise ValueError(f"Không tồn tại: {p}")
    return p


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Câu lệnh tự nhiên -> (action, target, dst)  (best-effort, an toàn)
# ---------------------------------------------------------------------------
def _parse_command(text: str) -> dict:
    """Suy ra hành động từ câu lệnh tiếng Việt. Không chắc -> action='unknown'."""
    t = (text or "").strip()
    low = t.lower()

    url = re.search(r"https?://\S+", t)
    if url:
        return {"action": "open_url", "target": url.group(0)}

    if any(k in low for k in ("dung lượng", "còn bao nhiêu", "thông tin hệ thống",
                              "ổ đĩa", "ram", "bộ nhớ", "sysinfo")):
        return {"action": "sysinfo"}

    m = re.search(r"(?:mở|chạy|khởi động)\s+(?:app|ứng dụng|chương trình)?\s*([a-zA-Z0-9_\-\.]+)", low)
    if m and m.group(1) in _APP_ALLOWLIST:
        return {"action": "open_app", "target": m.group(1)}

    if any(k in low for k in ("liệt kê", "xem thư mục", "có gì trong", "list")):
        m2 = re.search(r"(?:trong|thư mục|list)\s+(.+)$", t, re.IGNORECASE)
        return {"action": "list_dir", "target": (m2.group(1).strip() if m2 else "~")}

    if any(k in low for k in ("tạo thư mục", "mkdir", "tạo folder")):
        m3 = re.search(r"(?:tạo thư mục|mkdir|tạo folder)\s+(.+)$", t, re.IGNORECASE)
        if m3:
            return {"action": "mkdir", "target": m3.group(1).strip()}

    m4 = re.search(r"(?:đổi tên)\s+(.+?)\s+(?:thành|->)\s+(.+)$", t, re.IGNORECASE)
    if m4:
        return {"action": "rename", "target": m4.group(1).strip(), "dst": m4.group(2).strip()}

    m5 = re.search(r"(?:di chuyển|chuyển|move)\s+(.+?)\s+(?:sang|vào|->|to)\s+(.+)$", t, re.IGNORECASE)
    if m5:
        return {"action": "move", "target": m5.group(1).strip(), "dst": m5.group(2).strip()}

    m6 = re.search(r"(?:sao chép|copy)\s+(.+?)\s+(?:sang|vào|->|to)\s+(.+)$", t, re.IGNORECASE)
    if m6:
        return {"action": "copy", "target": m6.group(1).strip(), "dst": m6.group(2).strip()}

    m7 = re.search(r"(?:xoá|xóa|delete)\s+(.+)$", t, re.IGNORECASE)
    if m7:
        return {"action": "delete", "target": m7.group(1).strip()}

    return {"action": "unknown", "raw": t}


# ---------------------------------------------------------------------------
# Các hành động
# ---------------------------------------------------------------------------
def _act_sysinfo() -> dict:
    info: dict = {"platform": sys.platform}
    try:
        root = "C:\\" if os.name == "nt" else "/"
        du = shutil.disk_usage(root)
        info["disk"] = {"root": root, "total_gb": round(du.total / 1e9, 1),
                        "used_gb": round(du.used / 1e9, 1), "free_gb": round(du.free / 1e9, 1)}
    except Exception as exc:  # noqa: BLE001
        info["disk_error"] = str(exc)
    try:
        import psutil  # type: ignore
        vm = psutil.virtual_memory()
        info["ram"] = {"total_gb": round(vm.total / 1e9, 1), "available_gb": round(vm.available / 1e9, 1),
                       "percent": vm.percent}
    except Exception:  # noqa: BLE001 — psutil tuỳ chọn
        info["ram"] = "không rõ (cài psutil để xem RAM)"
    return info


def _act_list_dir(target: str) -> dict:
    p = _safe_path(target, must_exist=True)
    if not p.is_dir():
        raise ValueError(f"Không phải thư mục: {p}")
    entries = []
    for child in sorted(p.iterdir())[:200]:
        try:
            size = child.stat().st_size if child.is_file() else None
        except OSError:
            size = None
        entries.append({"name": child.name, "type": "dir" if child.is_dir() else "file", "size": size})
    return {"dir": str(p), "count": len(entries), "entries": entries}


def _act_mkdir(target: str) -> dict:
    p = _safe_path(target, for_write=True)
    p.mkdir(parents=True, exist_ok=True)
    return {"created": str(p)}


def _act_move(target: str, dst: str) -> dict:
    src = _safe_path(target, must_exist=True, for_write=True)
    dest = _safe_path(dst, for_write=True)
    shutil.move(str(src), str(dest))
    return {"moved": str(src), "to": str(dest)}


def _act_rename(target: str, dst: str) -> dict:
    src = _safe_path(target, must_exist=True, for_write=True)
    # dst có thể là tên mới (cùng thư mục) hoặc đường dẫn đầy đủ.
    dest_raw = dst if ("/" in dst or "\\" in dst) else str(src.parent / dst)
    dest = _safe_path(dest_raw, for_write=True)
    src.rename(dest)
    return {"renamed": str(src), "to": str(dest)}


def _act_copy(target: str, dst: str) -> dict:
    src = _safe_path(target, must_exist=True, for_write=True)
    dest = _safe_path(dst, for_write=True)
    if src.is_dir():
        shutil.copytree(str(src), str(dest))
    else:
        shutil.copy2(str(src), str(dest))
    return {"copied": str(src), "to": str(dest)}


def _act_delete(target: str, force: bool) -> dict:
    p = _safe_path(target, must_exist=True, for_write=True)
    # Ưu tiên Thùng rác.
    try:
        import send2trash  # type: ignore
        send2trash.send2trash(str(p))
        return {"trashed": str(p), "method": "recycle_bin"}
    except ModuleNotFoundError:
        pass
    if not force:
        raise ValueError(
            f"Không có 'send2trash' để đưa vào Thùng rác. Từ chối xoá CỨNG '{p}'. "
            "Cài `pip install send2trash`, hoặc truyền force=true nếu chắc chắn."
        )
    # Xoá cứng (đã an toàn path + force).
    if p.is_dir():
        shutil.rmtree(str(p))
    else:
        p.unlink()
    return {"deleted": str(p), "method": "hard_delete"}


def _act_open_app(target: str) -> dict:
    name = (target or "").strip().lower()
    spec = _APP_ALLOWLIST.get(name)
    if not spec:
        raise ValueError(
            f"App '{target}' không có trong allowlist. Cho phép: {', '.join(sorted(_APP_ALLOWLIST))}."
        )
    argv = spec["win"] if os.name == "nt" else spec["posix"]
    import subprocess  # import trễ; KHÔNG shell=True; argv là LIST (chống injection)
    subprocess.Popen(argv)  # noqa: S603 — argv allowlist, không shell
    return {"opened_app": name, "argv": argv}


def _act_open_path(target: str) -> dict:
    p = _safe_path(target, must_exist=True)
    if os.name == "nt":
        os.startfile(str(p))  # type: ignore[attr-defined]  # Windows mở bằng app mặc định
    elif sys.platform == "darwin":
        import subprocess
        subprocess.Popen(["open", str(p)])
    else:
        import subprocess
        subprocess.Popen(["xdg-open", str(p)])
    return {"opened_path": str(p)}


def _act_open_url(target: str) -> dict:
    if not re.match(r"^https?://", target or ""):
        raise ValueError(f"URL phải http/https: {target!r}")
    webbrowser.open(target)
    return {"opened_url": target}


# ---------------------------------------------------------------------------
# Tool công khai cho Registry
# ---------------------------------------------------------------------------
def tool_system_control(
    command: str = "",
    action: str = "",
    target: str = "",
    dst: str = "",
    force: bool = False,
    as_json: bool = False,
) -> ToolResult:
    """
    Tool 'system.control': điều khiển laptop qua hành động an toàn. Luôn trả ToolResult.

    Ưu tiên `action` tường minh; nếu rỗng thì suy ra từ `command` (best-effort).
    """
    act, tgt, d = action.strip(), target.strip(), dst.strip()
    if not act and command.strip():
        parsed = _parse_command(command)
        act = parsed.get("action", "")
        tgt = tgt or parsed.get("target", "")
        d = d or parsed.get("dst", "")

    if act == "unknown" or not act:
        return ToolResult.failure(
            "system.control",
            "Chưa rõ thao tác. Hãy nêu rõ, vd: action=open_app target=notepad, "
            "hoặc câu lệnh kiểu 'mở Notepad' / 'liệt kê ~/Downloads' / 'xoá <đường dẫn>'.",
        )
    if act not in _VALID_ACTIONS:
        return ToolResult.failure(
            "system.control", f"Hành động không hợp lệ: {act!r}. Cho phép: {', '.join(_VALID_ACTIONS)}."
        )

    try:
        if act == "sysinfo":
            result = _act_sysinfo()
        elif act == "list_dir":
            result = _act_list_dir(tgt or "~")
        elif act == "mkdir":
            result = _act_mkdir(tgt)
        elif act == "move":
            result = _act_move(tgt, d)
        elif act == "rename":
            result = _act_rename(tgt, d)
        elif act == "copy":
            result = _act_copy(tgt, d)
        elif act == "delete":
            result = _act_delete(tgt, force)
        elif act == "open_app":
            result = _act_open_app(tgt)
        elif act == "open_path":
            result = _act_open_path(tgt)
        elif act == "open_url":
            result = _act_open_url(tgt)
        else:  # không tới được
            return ToolResult.failure("system.control", f"Chưa hỗ trợ: {act}")
    except ValueError as exc:  # vi phạm an toàn / input sai
        return ToolResult.failure("system.control", str(exc))
    except FileNotFoundError as exc:
        return ToolResult.failure("system.control", f"Không tìm thấy: {exc}")
    except PermissionError as exc:
        return ToolResult.failure("system.control", f"Không đủ quyền: {exc}")
    except Exception as exc:  # noqa: BLE001 — vành đai cuối
        return ToolResult.failure("system.control", f"Lỗi thao tác hệ thống: {exc}")

    payload = {"action": act, **result}
    artifacts = [v for k, v in result.items()
                 if k in ("created", "to", "moved", "renamed", "copied") and isinstance(v, str)]
    output = json.dumps(payload, ensure_ascii=False, indent=2) if as_json else _render(act, result)
    return ToolResult.success("system.control", output=output, artifacts=artifacts)


def _render(act: str, result: dict) -> str:
    if act == "sysinfo":
        d = result.get("disk", {})
        return (f"🖥️ Hệ thống ({result.get('platform')}): ổ {d.get('root','?')} "
                f"còn {d.get('free_gb','?')}GB / {d.get('total_gb','?')}GB. RAM: {result.get('ram')}")
    if act == "list_dir":
        lines = [f"📂 {result['dir']} ({result['count']} mục):"]
        for e in result["entries"][:50]:
            tag = "📁" if e["type"] == "dir" else "📄"
            lines.append(f"  {tag} {e['name']}")
        return "\n".join(lines)
    return "✅ " + json.dumps(result, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI độc lập (Level 4)
# ---------------------------------------------------------------------------
def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="AURA skill system.control — tay chân điều khiển laptop.")
    ap.add_argument("--action", default="")
    ap.add_argument("--target", default="")
    ap.add_argument("--dst", default="")
    ap.add_argument("--command", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    result = tool_system_control(
        command=args.command, action=args.action, target=args.target,
        dst=args.dst, force=args.force, as_json=args.json,
    )
    print(result.output if result.ok else f"[LỖI] {result.error}")
    return 0 if result.ok else 1


__all__ = ["tool_system_control"]


if __name__ == "__main__":
    raise SystemExit(_main())
