# -*- coding: utf-8 -*-
"""
test_video_routing.py — smoke test routing "tải video" (vá 2026-07-02).
Chạy:  venv\\Scripts\\python.exe test_video_routing.py   (cần PYTHONUTF8=1)

Bối cảnh: Sếp gõ 'tải video "ta mô phỏng Con đường trường sinh" về' → rơi vào
local gemma nói nhảm. Vá: IntentLabel.VIDEO_DOWNLOAD + Iron Rule + bóc URL.
"""
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.orchestrator import _iron_rule_label, _TOOL_FOR_LABEL, AURA_Orchestrator
from core.schemas import IntentLabel

FAILED = []


def check(name: str, cond: bool, detail: str = ""):
    print(("PASS " if cond else "FAIL ") + name + (f" ({detail})" if detail else ""))
    if not cond:
        FAILED.append(name)


# 1) Iron Rule: câu tải video -> ép VIDEO_DOWNLOAD (không để LLM quyết)
check("iron: tải video + tên", _iron_rule_label('tải video "Con đường trường sinh" về') == IntentLabel.VIDEO_DOWNLOAD)
check("iron: download video + url", _iron_rule_label("download video https://x.com/a.mp4") == IntentLabel.VIDEO_DOWNLOAD)
check("iron: tải clip", _iron_rule_label("tải clip này về máy") == IntentLabel.VIDEO_DOWNLOAD)

# 2) KHÔNG nuốt nhầm domain khác
check("iron: tải truyện vẫn là manga", _iron_rule_label("tải truyện One Piece chương 5") == IntentLabel.MANGA_DOWNLOAD)
check("iron: việc làm vẫn là job", _iron_rule_label("tìm việc làm dựng video") == IntentLabel.JOB_SCOUT)

# 3) Map nhãn -> tool trong registry
check("map: VIDEO_DOWNLOAD -> video.download", _TOOL_FOR_LABEL.get(IntentLabel.VIDEO_DOWNLOAD) == "video.download")

# 4) Bóc tham số: có URL -> {'url':...}; không URL -> {} (hỏi lại, không đoán bừa)
build = AURA_Orchestrator._build_tool_arguments
args1 = build(None, IntentLabel.VIDEO_DOWNLOAD, "tải video https://example.com/v.mp4 về nhé")
check("args: bóc URL sạch", args1 == {"url": "https://example.com/v.mp4"}, str(args1))
args2 = build(None, IntentLabel.VIDEO_DOWNLOAD, 'tải video "Con đường trường sinh" về')
check("args: không URL -> {} để hỏi lại", args2 == {}, str(args2))

# 5) Registry thấy skill video.download (cần thư mục skills/video-download/)
try:
    from tools.registry import SkillRegistry
    reg = SkillRegistry()
    check("registry: có video.download", reg.has("video.download"))
except Exception as exc:  # noqa: BLE001
    check("registry: có video.download", False, f"lỗi nạp registry: {exc}")

print()
if FAILED:
    print(f"KẾT QUẢ: {len(FAILED)} FAIL -> {FAILED}")
    sys.exit(1)
print("KẾT QUẢ: TẤT CẢ PASS — restart AURA để nạp routing + skill mới.")
