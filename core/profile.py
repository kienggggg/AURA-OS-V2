"""
core/profile.py
===============
CHÂN DUNG SẾP (User Profile) — cái RỄ chung cho cả "gánh việc" lẫn "huấn luyện Sếp".

Lưu trữ KÉP (chống xung đột với ChromaDB hiện có):
  - NGUỒN SỰ THẬT  : file JSON `data/user_profile.json` (đọc/sửa/version chính xác).
  - BẢN SAO NGỮ NGHĨA: collection ChromaDB `CollectionName.PROFILE`, upsert theo ID ỔN
    ĐỊNH (vd 'weakness:overuse') -> id trùng thì GHI ĐÈ, không nhân bản.

Bước này CHỈ dựng nền: mô hình dữ liệu + đọc/ghi JSON + seed + sync_to_memory + summary.
KHÔNG nối vào orchestrator/daemon ở đây nên KHÔNG đụng Vibe Diff / Health Guard đang chạy.

Test nhanh trên máy Sếp:
    python -m core.profile     # seed (nếu chưa có) -> đồng bộ ChromaDB -> in chân dung
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from core.config import PROJECT_ROOT

logger = logging.getLogger("aura.profile")

_PROFILE_PATH = PROJECT_ROOT / "data" / "user_profile.json"


# ---------------------------------------------------------------------------
# Mô hình dữ liệu — mỗi mục có `key` để dựng ID ỔN ĐỊNH cho ChromaDB.
# ---------------------------------------------------------------------------
class Goal(BaseModel):
    key: str
    text: str
    why: str = ""
    target_date: str | None = None
    status: Literal["active", "done", "paused"] = "active"


class Habit(BaseModel):
    key: str
    text: str
    kind: Literal["good", "bad"] = "good"     # tốt = củng cố ; xấu = cần bỏ
    cadence: str = ""                          # vd "hằng ngày", "mỗi sáng"


class Weakness(BaseModel):
    key: str
    text: str
    severity: Literal["low", "medium", "high"] = "medium"


class Routine(BaseModel):
    key: str
    text: str
    at: str = ""                               # mốc giờ "HH:MM" nếu có


class RecurringTask(BaseModel):
    key: str
    text: str
    cadence: str = ""


class UserProfile(BaseModel):
    """Toàn bộ chân dung Sếp — nguồn sự thật, round-trip JSON."""

    # Tên thật nằm trong data/user_profile.json (không theo dõi bởi git), không
    # phải ở đây. Mặc định để trung tính vì tệp này lên GitHub.
    owner: str = "Sếp"
    goals: list[Goal] = Field(default_factory=list)
    habits: list[Habit] = Field(default_factory=list)
    weaknesses: list[Weakness] = Field(default_factory=list)
    routines: list[Routine] = Field(default_factory=list)
    recurring_tasks: list[RecurringTask] = Field(default_factory=list)
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


# ---------------------------------------------------------------------------
# Dữ liệu MỒI (seed) — điểm yếu mặc định để test.
# ---------------------------------------------------------------------------
def _seed_default() -> UserProfile:
    return UserProfile(
        weaknesses=[
            Weakness(
                key="overuse",
                text=("Dễ lười biếng, có xu hướng sử dụng laptop/điện thoại liên tục "
                      "hơn 8 tiếng/ngày."),
                severity="high",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# ProfileStore — đọc/ghi JSON + đồng bộ ChromaDB.
# ---------------------------------------------------------------------------
class ProfileStore:
    """Quản lý chân dung Sếp: JSON là nguồn sự thật, ChromaDB là bản sao ngữ nghĩa."""

    def __init__(self, path: Path | str | None = None, memory=None) -> None:
        self.path = Path(path) if path else _PROFILE_PATH
        self._memory = memory                  # MemoryStore (nạp lười nếu None)
        self.profile: UserProfile = self.load()

    # ---- JSON I/O ----
    def load(self) -> UserProfile:
        """Đọc JSON; chưa có file -> tạo bằng dữ liệu MỒI rồi ghi xuống đĩa."""
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return UserProfile(**data)
            except Exception as exc:  # noqa: BLE001 — JSON hỏng không được làm sập
                logger.warning("Đọc profile lỗi (%s) -> dùng seed mặc định.", exc)
        prof = _seed_default()
        self._write(prof)
        logger.info("Khởi tạo %s với dữ liệu mồi.", self.path.name)
        return prof

    def _write(self, profile: UserProfile) -> None:
        profile.updated_at = datetime.now().isoformat(timespec="seconds")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")

    def save(self) -> None:
        """Ghi chân dung hiện tại xuống JSON (nguồn sự thật)."""
        self._write(self.profile)

    # ---- ánh xạ fact -> (id ổn định, text, category) ----
    def _iter_facts(self):
        p = self.profile
        for g in p.goals:
            why = f" (vì: {g.why})" if g.why else ""
            yield f"goal:{g.key}", f"[MỤC TIÊU] {g.text}{why}", "goal"
        for h in p.habits:
            tag = "THÓI QUEN TỐT" if h.kind == "good" else "THÓI QUEN XẤU"
            yield f"habit:{h.key}", f"[{tag}] {h.text}", "habit"
        for w in p.weaknesses:
            yield f"weakness:{w.key}", f"[ĐIỂM YẾU] {w.text}", "weakness"
        for r in p.routines:
            at = f" lúc {r.at}" if r.at else ""
            yield f"routine:{r.key}", f"[NHỊP SỐNG] {r.text}{at}", "routine"
        for t in p.recurring_tasks:
            yield f"task:{t.key}", f"[VIỆC LẶP] {t.text}", "task"

    def sync_to_memory(self, memory=None) -> int:
        """
        UPSERT mọi fact vào ChromaDB collection PROFILE theo id ổn định (ghi đè, chống
        trùng). Trả về số fact đã đồng bộ. Thiếu chromadb/MemoryStore -> bỏ qua êm (0).
        """
        mem = memory or self._memory
        if mem is None:
            try:
                from core.memory import MemoryStore
                mem = MemoryStore()
                self._memory = mem
            except Exception as exc:  # noqa: BLE001 — không có ChromaDB cũng không sập
                logger.warning("Không mở được MemoryStore (%s) -> bỏ sync.", exc)
                return 0

        from core.memory import CollectionName
        from core.schemas import MemoryRecord

        n = 0
        for fid, text, cat in self._iter_facts():
            try:
                mem.upsert_memory(
                    MemoryRecord(id=fid, role="system", text=text, tags=["profile", cat]),
                    CollectionName.PROFILE,
                )
                n += 1
            except Exception as exc:  # noqa: BLE001 — một fact lỗi không chặn các fact khác
                logger.warning("Upsert fact %s lỗi (bỏ qua): %s", fid, exc)
        logger.info("Đã đồng bộ %d mẩu Chân dung Sếp vào ChromaDB.", n)
        return n

    def get_summary(self) -> str:
        """Khối text GỌN nhồi vào system prompt (Bước 2 sẽ dùng)."""
        p = self.profile
        lines = [f"[CHÂN DUNG {p.owner.upper()}]"]
        active_goals = [g.text for g in p.goals if g.status == "active"]
        if active_goals:
            lines.append("Mục tiêu: " + "; ".join(active_goals))
        good = [h.text for h in p.habits if h.kind == "good"]
        bad = [h.text for h in p.habits if h.kind == "bad"]
        if good:
            lines.append("Thói quen tốt cần củng cố: " + "; ".join(good))
        if bad:
            lines.append("Thói quen xấu cần bỏ: " + "; ".join(bad))
        if p.weaknesses:
            lines.append("Điểm yếu cần lưu ý: " + "; ".join(w.text for w in p.weaknesses))
        if p.routines:
            lines.append("Nhịp sống: " + "; ".join(
                (r.text + (f" ({r.at})" if r.at else "")) for r in p.routines))
        if p.recurring_tasks:
            lines.append("Việc lặp: " + "; ".join(t.text for t in p.recurring_tasks))
        return "\n".join(lines)

    # ---- mutators (nền cho Bước 2; chưa nối Vibe Diff ở bước này) ----
    @staticmethod
    def _upsert_list(items: list, new) -> None:
        for i, it in enumerate(items):
            if getattr(it, "key", None) == new.key:
                items[i] = new
                return
        items.append(new)

    def add_goal(self, key: str, text: str, why: str = "", target_date: str | None = None) -> None:
        self._upsert_list(self.profile.goals, Goal(key=key, text=text, why=why, target_date=target_date))
        self.save()

    def add_habit(self, key: str, text: str, kind: str = "good", cadence: str = "") -> None:
        self._upsert_list(self.profile.habits, Habit(key=key, text=text, kind=kind, cadence=cadence))
        self.save()

    def note_weakness(self, key: str, text: str, severity: str = "medium") -> None:
        self._upsert_list(self.profile.weaknesses, Weakness(key=key, text=text, severity=severity))
        self.save()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    store = ProfileStore()
    print(store.get_summary())
    try:
        n = store.sync_to_memory()
        print(f"\nĐã đồng bộ {n} mẩu Chân dung Sếp vào ChromaDB (collection 'profile').")
    except Exception as exc:  # noqa: BLE001
        print("Bỏ qua sync ChromaDB:", exc)


if __name__ == "__main__":
    main()


__all__ = [
    "UserProfile", "Goal", "Habit", "Weakness", "Routine", "RecurringTask",
    "ProfileStore",
]
