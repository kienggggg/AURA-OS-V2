"""
factory/breaker.py
==================
CẦU DAO TỰ NGẮT cho xưởng — chặn "vòng lặp tự hại im lặng".

Bài học thật (2026-07-23): token YouTube hết hạn, nhưng autopilot vẫn đều đặn
đẩy job `youtube.upload`. Kết quả: **25 job hỏng cùng một lỗi**, 14 job nữa xếp
hàng, worker (chạy 1 job/lúc) bị nghẽn nên việc thật không bao giờ tới lượt.
Không ai biết vì hỏng im lặng.

Nguyên tắc: một tool hỏng LIÊN TIẾP `ngưỡng` lần thì **NGẮT** — worker bỏ qua
mọi job của tool đó và báo Sếp một lần. Thành công một lần là **đóng lại** ngay.
Sếp cũng có thể đóng tay bằng `reset()`.

Cố ý làm ĐƠN GIẢN: một file JSON, không DB, không phụ thuộc.
"""

from __future__ import annotations

import json
import logging
import time

from core.config import settings

logger = logging.getLogger(__name__)

_PATH = settings.factory_dir / "breaker.json"
_THRESHOLD = 5          # hỏng liên tiếp bao nhiêu lần thì ngắt
_COOLDOWN_H = 6.0       # sau ngần này giờ thì cho thử LẠI một lần (nửa mở)


def _load() -> dict:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8")) if _PATH.is_file() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(d: dict) -> None:
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ghi breaker.json lỗi: %s", exc)


def note_success(tool: str) -> None:
    """Job chạy được -> đóng cầu dao, xoá đếm."""
    d = _load()
    if tool in d:
        d.pop(tool, None)
        _save(d)


def note_failure(tool: str, error: str = "") -> bool:
    """Job hỏng -> đếm lên. Trả True nếu VỪA ngắt (để phía gọi báo Sếp)."""
    d = _load()
    rec = d.get(tool) or {"fails": 0, "tripped_at": 0, "last_error": ""}
    rec["fails"] = int(rec.get("fails", 0)) + 1
    rec["last_error"] = (error or "")[:200]
    rec["last_at"] = time.time()
    just_tripped = False
    if rec["fails"] >= _THRESHOLD and not rec.get("tripped_at"):
        rec["tripped_at"] = time.time()
        just_tripped = True
        logger.warning("CẦU DAO NGẮT tool '%s' sau %d lần hỏng liên tiếp.",
                       tool, rec["fails"])
    d[tool] = rec
    _save(d)
    return just_tripped


def is_open(tool: str) -> tuple[bool, str]:
    """(đang bị ngắt?, lý do). Quá `_COOLDOWN_H` thì cho thử lại 1 lần."""
    rec = _load().get(tool)
    if not rec or not rec.get("tripped_at"):
        return False, ""
    age_h = (time.time() - float(rec["tripped_at"])) / 3600.0
    if age_h >= _COOLDOWN_H:
        return False, ""      # nửa mở: cho 1 lượt thử, hỏng nữa thì ngắt tiếp
    return True, (f"'{tool}' đã hỏng {rec.get('fails')} lần liên tiếp "
                  f"(lỗi: {rec.get('last_error','')[:90]})")


def reset(tool: str | None = None) -> str:
    """Đóng cầu dao bằng tay (Sếp đã sửa nguyên nhân)."""
    d = _load()
    if tool:
        d.pop(tool, None)
        _save(d)
        return f"✅ Đã đóng lại cầu dao cho '{tool}'."
    _save({})
    return "✅ Đã đóng lại TẤT CẢ cầu dao."


def status() -> str:
    d = _load()
    if not d:
        return "✅ Không có tool nào bị ngắt."
    lines = []
    for tool, rec in d.items():
        mark = "🔴 ĐANG NGẮT" if rec.get("tripped_at") else "⚠️ đang đếm"
        lines.append(f"{mark} {tool}: {rec.get('fails')} lần hỏng — "
                     f"{rec.get('last_error','')[:80]}")
    return "\n".join(lines)


__all__ = ["note_success", "note_failure", "is_open", "reset", "status"]
