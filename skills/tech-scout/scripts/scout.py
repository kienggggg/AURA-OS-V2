"""
skills/tech-scout/scripts/scout.py
==================================
TechScout — "Đặc vụ trinh sát công nghệ" (LỚP LOGIC, Level 4).

Ngữ cảnh ở ../SKILL.md; file này chỉ chứa code thực thi, registry nạp TRỄ qua importlib.

Lang thang GitHub & Hugging Face QUA API CÔNG KHAI để tìm model/tool mới. Với mỗi
ứng viên: chấm điểm độ phù hợp, bóc mô tả ngắn, lưu ChromaDB (ngữ cảnh tĩnh dài hạn).

Luật sắt: chỉ TÌM + CHẤM + LƯU + ĐỀ XUẤT. Biến model thành "đàn anh" (register_senior)
cần endpoint + backend + Sếp duyệt — scout chuẩn bị ứng viên, không tự kích hoạt.

requests bắt buộc; ChromaDB qua MemoryStore. Token GitHub/HF (nếu có) đọc từ env.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Cho phép `from core...` hoạt động dù nạp qua importlib hay chạy độc lập.
# skills/tech-scout/scripts/scout.py -> parents[3] = gốc dự án.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests

from core.memory import CollectionName, MemoryStore
from core.schemas import MemoryRecord, ToolResult

logger = logging.getLogger("aura.skills.tech_scout")

_GITHUB_API = "https://api.github.com/search/repositories"
_HF_API = "https://huggingface.co/api/models"

# Bao lâu thì đánh giá lại một ứng viên (loại đồ out-date).
_REEVALUATE_AFTER_DAYS = 30
# Coi là "cũ" nếu repo/model không cập nhật trong khoảng này.
_STALE_AFTER_DAYS = 365


@dataclass
class TechCandidate:
    """Một ứng viên công nghệ tìm được."""

    source: str          # "github" | "huggingface"
    name: str            # full name, vd "owner/repo" hoặc "org/model"
    url: str
    description: str
    popularity: int      # sao (github) hoặc lượt tải (hf)
    last_update: str     # ISO date
    score: float = 0.0
    tags: list[str] = field(default_factory=list)

    def to_memory_record(self) -> MemoryRecord:
        """Đóng gói thành MemoryRecord để lưu ChromaDB (ngữ cảnh tĩnh)."""
        text = (
            f"[{self.source}] {self.name} (score={self.score:.2f})\n"
            f"URL: {self.url}\n"
            f"Mô tả: {self.description}\n"
            f"Phổ biến: {self.popularity} | Cập nhật: {self.last_update}"
        )
        reeval = (datetime.now(timezone.utc) + timedelta(days=_REEVALUATE_AFTER_DAYS))
        return MemoryRecord(
            role="system",
            text=text,
            tags=["tech_scout", self.source, f"reeval:{reeval.date().isoformat()}",
                  *self.tags],
        )


class TechScout:
    """Trinh sát công nghệ qua API công khai."""

    def __init__(self, memory: MemoryStore | None = None, timeout_s: float = 15.0) -> None:
        self.memory = memory if memory is not None else MemoryStore()
        self.timeout_s = timeout_s

    # ------------------------------------------------------------------ #
    # Nguồn 1: GitHub
    # ------------------------------------------------------------------ #
    def _search_github(self, query: str, limit: int) -> list[TechCandidate]:
        headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        params = {"q": query, "sort": "stars", "order": "desc", "per_page": limit}
        resp = requests.get(_GITHUB_API, headers=headers, params=params,
                            timeout=self.timeout_s)
        resp.raise_for_status()
        items = resp.json().get("items", [])

        out: list[TechCandidate] = []
        for it in items:
            out.append(TechCandidate(
                source="github",
                name=it.get("full_name", "?"),
                url=it.get("html_url", ""),
                description=(it.get("description") or "")[:300],
                popularity=int(it.get("stargazers_count", 0)),
                last_update=it.get("pushed_at", ""),
                tags=it.get("topics", [])[:5],
            ))
        return out

    # ------------------------------------------------------------------ #
    # Nguồn 2: Hugging Face
    # ------------------------------------------------------------------ #
    def _search_huggingface(self, query: str, limit: int) -> list[TechCandidate]:
        headers = {}
        token = os.environ.get("HF_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        params = {"search": query, "sort": "downloads", "direction": "-1",
                  "limit": limit}
        resp = requests.get(_HF_API, headers=headers, params=params,
                            timeout=self.timeout_s)
        resp.raise_for_status()
        models = resp.json()

        out: list[TechCandidate] = []
        for m in models:
            mid = m.get("modelId") or m.get("id", "?")
            out.append(TechCandidate(
                source="huggingface",
                name=mid,
                url=f"https://huggingface.co/{mid}",
                description=", ".join(m.get("tags", [])[:8])[:300],
                popularity=int(m.get("downloads", 0)),
                last_update=m.get("lastModified", ""),
                tags=m.get("tags", [])[:5],
            ))
        return out

    # ------------------------------------------------------------------ #
    # Chấm điểm độ phù hợp
    # ------------------------------------------------------------------ #
    @staticmethod
    def _score(candidate: TechCandidate, keywords: list[str]) -> float:
        """Điểm 0..1 kết hợp: độ phổ biến (log), độ mới, và khớp từ khoá."""
        import math

        # 1) Phổ biến: log để 100k sao không áp đảo tuyệt đối. Chuẩn hoá ~0..1.
        pop = math.log10(candidate.popularity + 1) / 6.0  # 10^6 -> ~1.0
        pop = min(pop, 1.0)

        # 2) Độ mới: cập nhật trong 1 năm = 1.0, càng cũ càng giảm về 0.
        freshness = 0.5
        try:
            last = datetime.fromisoformat(candidate.last_update.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - last).days
            freshness = max(0.0, 1.0 - age_days / _STALE_AFTER_DAYS)
        except (ValueError, AttributeError):
            pass

        # 3) Khớp từ khoá trong tên/mô tả/tags.
        haystack = f"{candidate.name} {candidate.description} {' '.join(candidate.tags)}".lower()
        hits = sum(1 for kw in keywords if kw.lower() in haystack)
        keyword_match = hits / len(keywords) if keywords else 0.0

        # Trọng số: phù hợp từ khoá quan trọng nhất, rồi tới mới, rồi phổ biến.
        return round(0.45 * keyword_match + 0.30 * freshness + 0.25 * pop, 3)

    # ------------------------------------------------------------------ #
    # Luồng chính
    # ------------------------------------------------------------------ #
    def scout(
        self, query: str, keywords: list[str] | None = None,
        sources: tuple[str, ...] = ("github", "huggingface"), limit: int = 5,
    ) -> list[TechCandidate]:
        """Tìm ứng viên, chấm điểm, sắp xếp giảm dần. Nguồn nào lỗi thì bỏ qua."""
        kw = keywords or query.split()
        candidates: list[TechCandidate] = []

        if "github" in sources:
            try:
                candidates += self._search_github(query, limit)
            except requests.RequestException as exc:
                logger.warning("GitHub search lỗi: %s", exc)
        if "huggingface" in sources:
            try:
                candidates += self._search_huggingface(query, limit)
            except requests.RequestException as exc:
                logger.warning("HuggingFace search lỗi: %s", exc)

        for c in candidates:
            c.score = self._score(c, kw)
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates

    def store(self, candidates: list[TechCandidate]) -> int:
        """Lưu ứng viên vào ChromaDB (collection system_rules — ngữ cảnh tĩnh dài hạn)."""
        saved = 0
        for c in candidates:
            try:
                self.memory.add_memory(c.to_memory_record(), CollectionName.SYSTEM_RULES)
                saved += 1
            except Exception as exc:  # noqa: BLE001 — lưu 1 cái lỗi không chặn cả mẻ
                logger.warning("Lưu ứng viên '%s' lỗi: %s", c.name, exc)
        return saved

    def recall_known(self, query: str, k: int = 5) -> list[MemoryRecord]:
        """Lấy lại các ứng viên đã từng trinh sát (để khỏi đề xuất trùng / xem lại)."""
        return self.memory.search_memory(query, CollectionName.SYSTEM_RULES, k=k)


# ---------------------------------------------------------------------------
# Tool công khai cho Registry  (entrypoint khai báo trong SKILL.md)
# ---------------------------------------------------------------------------
def tool_tech_scout(query: str, keywords: str = "", limit: int = 5) -> ToolResult:
    """
    Tool 'tech.scout': trinh sát công nghệ theo query, lưu kết quả, trả tóm tắt.

    Args:
        query: từ khoá tìm (vd "vietnamese translation model").
        keywords: từ khoá chấm điểm, phân tách bằng dấu phẩy (mặc định = tách query).
        limit: số kết quả mỗi nguồn.
    """
    start = time.monotonic()
    kw = [k.strip() for k in keywords.split(",") if k.strip()] or None
    try:
        scout = TechScout()
        candidates = scout.scout(query, keywords=kw, limit=limit)
    except Exception as exc:  # noqa: BLE001 — vành đai cuối
        return ToolResult.failure("tech.scout", f"Lỗi trinh sát: {exc}")

    if not candidates:
        return ToolResult.failure(
            "tech.scout",
            "Không tìm thấy ứng viên nào (nguồn lỗi hoặc query quá hẹp).",
        )

    saved = scout.store(candidates)
    elapsed = int((time.monotonic() - start) * 1000)

    top = candidates[:limit]
    lines = [
        f"{i+1}. [{c.source}] {c.name} (điểm {c.score:.2f}, {c.popularity} ⭐/↓)\n"
        f"   {c.url}"
        for i, c in enumerate(top)
    ]
    summary = (
        f"Tìm thấy {len(candidates)} ứng viên (đã lưu {saved} vào bộ nhớ dài hạn). "
        f"Top {len(top)}:\n" + "\n".join(lines) +
        "\n\nSếp muốn em đăng ký cái nào làm 'đàn anh' không? "
        "(cần endpoint + Sếp duyệt)"
    )
    return ToolResult.success("tech.scout", output=summary, elapsed_ms=elapsed)


# ---------------------------------------------------------------------------
# CLI độc lập (Level 4)
# ---------------------------------------------------------------------------
def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="AURA skill tech.scout — trinh sát công nghệ.")
    ap.add_argument("--query", required=True)
    ap.add_argument("--keywords", default="")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args(argv)

    result = tool_tech_scout(query=args.query, keywords=args.keywords, limit=args.limit)
    print(result.model_dump_json(indent=2))
    return 0 if result.ok else 1


__all__ = ["TechScout", "TechCandidate", "tool_tech_scout"]


if __name__ == "__main__":
    raise SystemExit(_main())
