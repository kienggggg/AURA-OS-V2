"""Điều khiển công nhân (crew) bằng lời: NGỪNG / BẬT LẠI việc săn job, tin tức...

Sếp gõ "tạm ngừng săn job" -> AURA phải HIỂU đây là LỆNH (tạm dừng công nhân
'job'), KHÔNG được đổ báo cáo Job Scout ra (bệnh "trả lời một nẻo"). Trạng thái
nhớ qua data/feedback/crew_paused.json để sống qua khởi động lại; nhịp crew nền
sẽ BỎ QUA công nhân đang tạm dừng.

Nguyên tắc chống nhầm: động từ/đối tượng khớp theo CỤM TÁCH KHOẢNG TRẮNG (không
substring thô) — để 'tắt' không dính 'tất cả', 'dừng' không dính 'sử dụng'...
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "data" / "feedback" / "crew_paused.json"

# Công nhân chuẩn + bí danh trong lời nói (dấu và không dấu).
_ALIASES: dict[str, tuple[str, ...]] = {
    "job": ("săn job", "san job", "tìm việc", "tim viec", "việc làm", "viec lam",
            "job scout", "tuyển dụng", "tuyen dung", "job", "cv"),
    "news": ("tin tức", "tin tuc", "săn tin", "san tin", "news", "bản tin", "ban tin"),
    "janitor": ("dọn rác", "don rac", "janitor", "dọn dẹp", "don dep"),
    "radar": ("trend", "xu hướng", "xu huong", "trend radar", "radar"),
}
# CHỈ nhận cụm rõ là "cả tổ" — KHÔNG lấy bare "tất cả" (dễ nuốt "tắt tất cả thông báo").
_ALL = ("cả tổ", "ca to", "công nhân", "cong nhan", "crew", "tổ trưởng", "to truong")

_PAUSE_VERBS = ("tạm ngừng", "tam ngung", "tạm dừng", "tam dung", "ngừng", "ngung",
                "dừng lại", "dung lai", "dừng", "dung", "tắt", "tat", "ngưng",
                "stop", "pause")
_RESUME_VERBS = ("bật lại", "bat lai", "mở lại", "mo lai", "bật", "bat",
                 "tiếp tục", "tiep tuc", "chạy lại", "chay lai", "kích hoạt",
                 "kich hoat", "resume", "start")

_LABELS = {"job": "săn job", "news": "săn tin tức",
           "janitor": "dọn rác", "radar": "radar xu hướng"}


def _norm(text: str) -> str:
    """Bỏ dấu câu -> khoảng trắng, thêm đệm 2 đầu để khớp cụm theo biên từ."""
    low = re.sub(r"[^\w\s]", " ", (text or "").lower(), flags=re.UNICODE)
    return " " + re.sub(r"\s+", " ", low).strip() + " "


def _first_idx(norm: str, phrases: tuple[str, ...]) -> int:
    """Vị trí sớm nhất một cụm (có biên khoảng trắng) xuất hiện; -1 nếu không có."""
    best = -1
    for p in phrases:
        i = norm.find(" " + p + " ")
        if i != -1 and (best == -1 or i < best):
            best = i
    return best


def _has(norm: str, phrases: tuple[str, ...]) -> bool:
    return _first_idx(norm, phrases) != -1


def _targets(norm: str) -> set[str]:
    if _has(norm, _ALL):
        return set(_ALIASES)
    return {name for name, al in _ALIASES.items() if _has(norm, al)}


# --------------------------------------------------------------------------- #
# Trạng thái tạm dừng (bền qua khởi động lại)
# --------------------------------------------------------------------------- #
def _load() -> set[str]:
    try:
        return set(json.loads(_PATH.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 — chưa có file -> không ai bị dừng
        return set()


def _save(s: set[str]) -> None:
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(sorted(s), ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def is_paused(worker: str) -> bool:
    return worker in _load()


def list_paused() -> list[str]:
    return sorted(_load())


# --------------------------------------------------------------------------- #
# Lớp hiểu lệnh
# --------------------------------------------------------------------------- #
def is_worker_control(text: str) -> bool:
    """Câu có ĐỘNG TỪ điều khiển (ngừng/bật) VÀ nhắm tới một công nhân?"""
    norm = _norm(text)
    has_verb = _has(norm, _PAUSE_VERBS) or _has(norm, _RESUME_VERBS)
    return has_verb and bool(_targets(norm))


def handle_worker_control(text: str) -> str:
    """Thực thi lệnh ngừng/bật và trả câu xác nhận (KHÔNG đổ báo cáo)."""
    norm = _norm(text)
    targets = _targets(norm)
    if not targets:
        return "Sếp muốn ngừng/bật công nhân nào? (săn job · tin tức · dọn rác · trend)"

    pi = _first_idx(norm, _PAUSE_VERBS)
    ri = _first_idx(norm, _RESUME_VERBS)
    # Cả hai cùng xuất hiện (vd 'bật lại' vs 'ngừng') -> động từ ĐỨNG TRƯỚC thắng.
    if pi != -1 and ri != -1:
        resume = ri < pi
    else:
        resume = ri != -1

    cur = _load()
    names = ", ".join(_LABELS[t] for t in sorted(targets))
    if resume:
        cur -= targets
        _save(cur)
        return f"✅ Đã BẬT LẠI: {names}. Công nhân sẽ chạy lại theo nhịp."
    cur |= targets
    _save(cur)
    return (f"⏸️ Đã TẠM NGỪNG: {names}. Em sẽ không săn/không báo cáo tới khi "
            f"Sếp bảo 'bật lại {_LABELS[sorted(targets)[0]]}'.")
