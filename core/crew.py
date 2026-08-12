"""
core/crew.py
============
TỔ TRƯỞNG công nhân (WorkerCrew) — "quản gia" điều phối cả 3 công nhân nhỏ vào MỘT
ca làm việc, thay vì 3 chỗ gọi rời rạc.

Vì sao gộp:
  - Model embedding (core/embedder.py) chỉ NẠP 1 LẦN cho cả ca (pin), 3 công nhân
    dùng chung, cuối ca nhả 1 lần — thay vì nạp/nhả 3 lần như trước.
  - Một BÁO CÁO ca làm việc duy nhất gửi Sếp, thay vì 3 lần ping rời.
  - Mỗi công nhân GIỮ nhịp riêng: tổ trưởng chỉ gọi công nhân "tới hạn" (due-gate
    theo data/feedback/crew_state.json) — news ~8h, job/janitor ~24h.

Danh sách công nhân (roster):
  - "job"     -> skills/scouts/job_scout.py  (nạp path-based, bản đã gắn embedder + feedback)
  - "news"    -> skill news.scout            (qua registry)
  - "janitor" -> skill trash.janitor         (qua registry)
  - "radar"   -> skill trend.radar           (qua registry) — trend hợp góc + brief video

Từng công nhân vẫn tự bọc try/except và tự gọi unload() (thành no-op khi bị pin).
Một công nhân lỗi KHÔNG làm hỏng cả ca.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger("aura.crew")

ROSTER = ("job", "news", "janitor", "radar")
_STATE_PATH = PROJECT_ROOT / "data" / "feedback" / "crew_state.json"

# Nhịp mặc định (giờ) mỗi công nhân "tới hạn" — có thể override qua settings.
_DEFAULT_INTERVAL_H: dict[str, float] = {
    "job": 24.0, "news": 8.0, "janitor": 24.0, "radar": 24.0,
}


def _settings():
    try:
        from core.config import settings
        return settings
    except Exception:  # noqa: BLE001
        return None


class WorkerCrew:
    """Tổ trưởng: giữ sổ 3 công nhân, chạy 1 ca chung 1 lần nạp model, 1 báo cáo."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._job_mod = None
        self._state = self._load_state()

    # ------------------------------------------------------------------ #
    # Trạng thái + due-gate
    # ------------------------------------------------------------------ #
    def _load_state(self) -> dict:
        try:
            return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — chưa có -> chạy lần đầu, ai cũng tới hạn
            return {"last": {}}

    def _save_state(self) -> None:
        try:
            _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _STATE_PATH.write_text(
                json.dumps(self._state, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as exc:
            logger.warning("Ghi crew_state lỗi (bỏ qua): %s", exc)

    def _interval_s(self, name: str) -> float:
        st = _settings()
        hours = _DEFAULT_INTERVAL_H.get(name, 24.0)
        if st is not None:
            hours = float(getattr(st, f"crew_{name}_interval_h", hours))
        return hours * 3600.0

    def _is_due(self, name: str) -> bool:
        last = float(self._state.get("last", {}).get(name, 0))
        return (time.time() - last) >= self._interval_s(name)

    def _mark_ran(self, name: str) -> None:
        self._state.setdefault("last", {})[name] = int(time.time())
        self._save_state()

    # ------------------------------------------------------------------ #
    # Ca làm việc
    # ------------------------------------------------------------------ #
    def run_shift(
        self,
        which: list[str] | tuple[str, ...] | None = None,
        only: set[str] | None = None,
        force: bool = False,
        apply_janitor: bool = True,
    ) -> dict:
        """Chạy một ca. `which`=None -> cả roster; `only`=lọc theo công nhân được bật;
        `force`=bỏ qua due-gate (chạy ngay). Trả dict báo cáo (kèm text đã render)."""
        cands = list(which) if which else list(ROSTER)
        cands = [w for w in cands if w in ROSTER]
        # Bỏ qua công nhân Sếp đã bảo "tạm ngừng" (nhịp nền không chạy/không báo cáo).
        from core.worker_control import is_paused
        cands = [w for w in cands if not is_paused(w)]
        if only is not None:
            cands = [w for w in cands if w in only]
        if not force:
            cands = [w for w in cands if self._is_due(w)]

        results: list[dict] = []
        if not cands:
            return self._report(results, ran=[])

        # Ghim model 1 lần cho CẢ ca (mọi unload() của công nhân thành no-op).
        from core.embedder import get_worker
        worker = get_worker()
        with self._lock:
            worker.pin()
            t0 = time.monotonic()
            try:
                for name in cands:
                    results.append(self._run_one(name, apply_janitor))
                    self._mark_ran(name)
            finally:
                worker.unpin()
                worker.unload(force=True)     # cuối ca: nhả thật, dù còn pin lồng nhau
            logger.info("Tổ công nhân xong ca [%s] trong %.1fs.",
                        ", ".join(cands), time.monotonic() - t0)
        return self._report(results, ran=cands)

    def _run_one(self, name: str, apply_janitor: bool) -> dict:
        try:
            if name == "job":
                return self._run_job()
            if name == "news":
                return self._run_news()
            if name == "janitor":
                return self._run_janitor(apply_janitor)
            if name == "radar":
                return self._run_radar()
        except Exception as exc:  # noqa: BLE001 — 1 công nhân ngã KHÔNG kéo đổ cả tổ
            logger.warning("Công nhân '%s' lỗi (bỏ qua): %s", name, exc)
            return {"worker": name, "ok": False, "summary": f"lỗi: {exc}"}
        return {"worker": name, "ok": False, "summary": "không rõ công nhân"}

    # --- adapters từng công nhân ---
    def _load_job(self):
        if self._job_mod is None:
            path = PROJECT_ROOT / "skills" / "scouts" / "job_scout.py"
            spec = importlib.util.spec_from_file_location("aura_crew_job", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self._job_mod = mod
        return self._job_mod

    def _run_job(self) -> dict:
        mod = self._load_job()
        jobs = mod.collect()                   # đã ghi job_scout_last.json cho menu vote
        top = [j.get("title", "") for j in jobs[:3]]
        summary = f"{len(jobs)} cơ hội việc làm mới" if jobs else "chưa có cơ hội mới"
        # Có hồ sơ TỰ SOẠN -> nói to cho Sếp (chỉ việc mở file, pitch đã viết sẵn).
        drafted = int(getattr(mod, "_LAST_AUTO_DRAFTED", 0) or 0)
        if drafted:
            summary += (f" — 🎯 ĐÃ SOẠN SẴN {drafted} bộ hồ sơ ứng tuyển, Sếp mở "
                        "data/outputs/freelance/VIỆC_HÔM_NAY.md là gửi được ngay")
        return {
            "worker": "job", "ok": True, "count": len(jobs), "top": top,
            "summary": summary, "notable": bool(drafted) or None,
        }

    def _run_news(self) -> dict:
        from tools.registry import call_skill
        res = call_skill("news.scout", {"use_llm": True, "max_detail": 3, "as_json": True})
        if not getattr(res, "ok", False):
            return {"worker": "news", "ok": False, "summary": f"lỗi: {getattr(res, 'error', '?')}"}
        data = json.loads(res.output or "{}")
        top = [t.get("title", "") for t in data.get("top", [])[:3]]
        return {
            "worker": "news", "ok": True, "count": data.get("useful_count", 0), "top": top,
            "summary": f"{data.get('useful_count', 0)} tin hữu ích / {data.get('total_seen', 0)} tin",
        }

    def _run_janitor(self, apply_janitor: bool) -> dict:
        from tools.registry import call_skill
        res = call_skill("trash.janitor", {"apply": apply_janitor, "as_json": True})
        if not getattr(res, "ok", False):
            return {"worker": "janitor", "ok": False, "summary": f"lỗi: {getattr(res, 'error', '?')}"}
        data = json.loads(res.output or "{}")
        n, mb = data.get("recycled", 0), data.get("rule_junk_size_mb", 0)
        sug = len(data.get("suggestions", []))
        return {
            "worker": "janitor", "ok": True, "recycled": n, "suggestions": sug,
            "summary": (f"dọn {n} file rác (~{mb}MB)" if n else "không có rác để dọn")
                       + (f", {sug} file Downloads chờ xem" if sug else ""),
        }

    def _run_radar(self) -> dict:
        from tools.registry import call_skill
        # Mặc định theo config trend_use_cloud (thường False -> brief khung mẫu, khỏi tốn
        # lượt cloud mỗi ngày). Muốn brief cloud trong tổ: đặt TREND_USE_CLOUD=true.
        res = call_skill("trend.radar", {"as_json": True})
        if not getattr(res, "ok", False):
            return {"worker": "radar", "ok": False, "summary": f"lỗi: {getattr(res, 'error', '?')}"}
        data = json.loads(res.output or "{}")
        tops = data.get("top", [])
        n = 0 if data.get("weak") else len(tops)
        top = [t.get("title", "") for t in tops[:2]]
        return {
            "worker": "radar", "ok": True, "count": n, "top": top,
            "summary": (f"{n} chủ đề trend hợp góc" + (f" (vd: {top[0]})" if top else ""))
                       if n else "chưa có trend hợp góc rõ",
        }

    # ------------------------------------------------------------------ #
    # Báo cáo ca (một chiều, gộp cả tổ)
    # ------------------------------------------------------------------ #
    def _report(self, results: list[dict], ran: list[str]) -> dict:
        icon = {"job": "💼 Việc làm", "news": "📰 Tin tức", "janitor": "🧹 Dọn rác",
                "radar": "📡 Trend"}
        lines = []
        for r in results:
            lines.append(f"• {icon.get(r['worker'], r['worker'])}: {r.get('summary', '')}")
        text = ""
        # "Đáng báo": có công nhân chạy thành công VÀ ra kết quả thực (job/news >0, janitor dọn/đề xuất).
        notable = any(
            r.get("ok") and (r.get("count") or r.get("recycled") or r.get("suggestions"))
            for r in results
        )
        if lines:
            text = "🧑‍🌾 Tổ công nhân vừa xong ca:\n" + "\n".join(lines)
        return {
            "ts": int(time.time()),
            "ran": ran,
            "results": results,
            "notable": notable,
            "text": text,
        }


_crew: WorkerCrew | None = None
_crew_lock = threading.Lock()


def get_crew() -> WorkerCrew:
    """Singleton tổ trưởng toàn tiến trình."""
    global _crew
    with _crew_lock:
        if _crew is None:
            _crew = WorkerCrew()
        return _crew


__all__ = ["WorkerCrew", "get_crew", "ROSTER"]
