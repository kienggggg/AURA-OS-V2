"""
core/skillopt_hand.py
=====================
Cầu nối AURA <-> **SkillOpt-Sleep** (microsoft/SkillOpt) — cơ chế cho agent
TỰ TIẾN HOÁ KỸ NĂNG **mà KHÔNG đụng trọng số model**.

Cách nó chạy (mỗi "đêm"): thu hoạch transcript phiên làm việc -> đào ra tác vụ
lặp lại -> phát lại -> đề xuất bản skill mới -> **CỔNG KIỂM ĐỊNH held-out**:
chỉ nhận nếu điểm THỰC SỰ tăng, không thì từ chối. Đây là điểm khiến nó khác
mấy trò "AI tự sửa mình" vô kiểm soát.

Nguyên tắc an toàn của AURA:
- MẶC ĐỊNH **CHỈ ĐỀ XUẤT** (staged), KHÔNG tự áp (`auto_adopt=False`). Sếp xem
  rồi duyệt — vì bản skill mới sẽ ảnh hưởng mọi phiên sau.
- Có TRẦN số phiên/tác vụ mỗi đêm (đỡ tốn quota LLM).
- Backend `mock` = chạy khô, không tốn quota; `claude` = dùng Claude Code thật.

Dùng tay:
    venv/Scripts/python.exe -m core.skillopt_hand --dry      # chạy khô, báo cáo
    venv/Scripts/python.exe -m core.skillopt_hand --run      # 1 đêm thật (staged)
    venv/Scripts/python.exe -m core.skillopt_hand --status
    venv/Scripts/python.exe -m core.skillopt_hand --adopt    # áp đề xuất mới nhất
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys

from core.config import settings, PROJECT_ROOT

logger = logging.getLogger(__name__)

_EXE = PROJECT_ROOT / "venv" / "Scripts" / "skillopt-sleep.exe"


def _bin() -> str:
    return str(_EXE) if _EXE.is_file() else "skillopt-sleep"


def _run(args: list[str], timeout: int = 1800) -> tuple[int, str]:
    cmd = [_bin(), *args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except FileNotFoundError:
        return 127, "Chưa cài SkillOpt. Cài: pip install skillopt"
    except subprocess.TimeoutExpired:
        return 124, f"SkillOpt chạy quá {timeout}s — bỏ lượt."
    except Exception as exc:  # noqa: BLE001
        return 1, f"Lỗi gọi SkillOpt: {exc}"


def _common() -> list[str]:
    return [
        "--project", str(PROJECT_ROOT),
        "--source", str(getattr(settings, "skillopt_source", "claude")),
        "--backend", str(getattr(settings, "skillopt_backend", "mock")),
        "--lookback-hours", str(int(getattr(settings, "skillopt_lookback_hours", 24))),
        "--max-sessions", str(int(getattr(settings, "skillopt_max_sessions", 5))),
        "--max-tasks", str(int(getattr(settings, "skillopt_max_tasks", 8))),
    ]


def dry_run() -> str:
    """Chạy khô: thu hoạch + đào + phát lại, CHỈ báo cáo, không đổi gì."""
    code, out = _run(["dry-run", *_common()])
    return _fmt("Chạy khô SkillOpt", code, out)


def run_night(auto_adopt: bool | None = None) -> str:
    """Chạy MỘT đêm tiến hoá. Mặc định chỉ staged (không tự áp)."""
    aa = bool(getattr(settings, "skillopt_auto_adopt", False)) if auto_adopt is None else auto_adopt
    args = ["run", *_common()]
    if aa:
        args.append("--auto-adopt")
    code, out = _run(args)
    return _fmt("Đêm tiến hoá SkillOpt" + (" (TỰ ÁP)" if aa else " (chỉ đề xuất)"), code, out)


def status() -> str:
    code, out = _run(["status", "--project", str(PROJECT_ROOT)], timeout=120)
    return _fmt("Trạng thái SkillOpt", code, out)


def adopt() -> str:
    """Áp bản skill mới nhất đã qua cổng kiểm định (Sếp duyệt)."""
    code, out = _run(["adopt", "--project", str(PROJECT_ROOT)], timeout=300)
    return _fmt("Áp đề xuất SkillOpt", code, out)


def _fmt(title: str, code: int, out: str) -> str:
    tail = "\n".join(out.splitlines()[-12:]) if out else "(không có output)"
    icon = "✅" if code == 0 else ("ℹ️" if code == 2 else "⚠️")
    return f"{icon} {title} (mã {code}):\n{tail}"


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AURA <-> SkillOpt-Sleep")
    ap.add_argument("--dry", action="store_true", help="Chạy khô, chỉ báo cáo")
    ap.add_argument("--run", action="store_true", help="Chạy 1 đêm tiến hoá")
    ap.add_argument("--status", action="store_true", help="Xem trạng thái + đề xuất")
    ap.add_argument("--adopt", action="store_true", help="Áp đề xuất mới nhất")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if args.dry:
        print(dry_run()); return 0
    if args.run:
        print(run_night()); return 0
    if args.adopt:
        print(adopt()); return 0
    print(status()); return 0


if __name__ == "__main__":
    sys.exit(main())
