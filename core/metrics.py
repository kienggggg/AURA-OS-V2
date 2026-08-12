"""
core/metrics.py
===============
Thước đo tự đánh giá — để AURA "biết mình đang khá lên hay tệ đi".

Ghi lại từng lần chạy kỹ năng: thành công/thất bại + thời gian (ms), gom theo NGÀY
và theo TOOL, lưu bền vào data/metrics.json. Cung cấp:
  - record()    : ghi một lần chạy (gọi từ Orchestrator, an toàn, rất nhẹ).
  - scorecard() : bảng điểm hôm nay (tỉ lệ thành công, độ trễ trung bình).
  - trend()     : so hôm nay với hôm qua -> "khá lên / tệ đi" cho từng tool.

Đây là nền cho Self-Reflection (#5) & Self-Evolve (#2): có số liệu thì bài học và
đề xuất tự-viết-tool mới có căn cứ, không cảm tính.

Thuần stdlib (json), file nhỏ, ghi load-modify-save bọc try/except — không bao giờ
làm sập luồng chính dù I/O lỗi.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import date, timedelta
from pathlib import Path

from core.config import PROJECT_ROOT

logger = logging.getLogger("aura.metrics")

_METRICS_PATH = PROJECT_ROOT / "data" / "metrics.json"
_LOCK = threading.Lock()  # nhiều worker thread có thể ghi -> khoá nhẹ tránh đua


# ---------------------------------------------------------------------------
# I/O nền
# ---------------------------------------------------------------------------
def _load() -> dict:
    try:
        if _METRICS_PATH.is_file():
            return json.loads(_METRICS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Đọc metrics lỗi (dùng rỗng): %s", exc)
    return {"days": {}}


def _save(data: dict) -> None:
    try:
        _METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _METRICS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 — ghi metrics hỏng KHÔNG được làm sập
        logger.warning("Ghi metrics lỗi: %s", exc)


def _today() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Ghi nhận
# ---------------------------------------------------------------------------
def record(tool_name: str, ok: bool, elapsed_ms: int = 0, *, day: str | None = None) -> None:
    """
    Ghi một lần chạy kỹ năng. An toàn tuyệt đối (mọi lỗi bị nuốt). Rất nhẹ.

    Cấu trúc: days[ngày][tool] = {runs, ok, fail, total_ms}.
    """
    try:
        d = day or _today()
        with _LOCK:
            data = _load()
            day_bucket = data.setdefault("days", {}).setdefault(d, {})
            rec = day_bucket.setdefault(tool_name, {"runs": 0, "ok": 0, "fail": 0, "total_ms": 0})
            rec["runs"] += 1
            rec["ok" if ok else "fail"] += 1
            rec["total_ms"] += int(elapsed_ms or 0)
            _save(data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics.record lỗi (bỏ qua): %s", exc)


# ---------------------------------------------------------------------------
# Báo cáo
# ---------------------------------------------------------------------------
def _aggregate(day_bucket: dict) -> dict:
    runs = sum(r["runs"] for r in day_bucket.values())
    ok = sum(r["ok"] for r in day_bucket.values())
    ms = sum(r["total_ms"] for r in day_bucket.values())
    return {
        "runs": runs, "ok": ok, "fail": runs - ok,
        "success_rate": round(ok / runs, 3) if runs else 0.0,
        "avg_ms": round(ms / runs) if runs else 0,
    }


def scorecard(day: str | None = None) -> dict:
    """Bảng điểm một ngày (mặc định hôm nay): tổng + chi tiết theo tool."""
    d = day or _today()
    data = _load()
    bucket = data.get("days", {}).get(d, {})
    per_tool = {
        t: {
            "runs": r["runs"], "ok": r["ok"], "fail": r["fail"],
            "success_rate": round(r["ok"] / r["runs"], 3) if r["runs"] else 0.0,
            "avg_ms": round(r["total_ms"] / r["runs"]) if r["runs"] else 0,
        }
        for t, r in bucket.items()
    }
    return {"day": d, "overall": _aggregate(bucket), "tools": per_tool}


def trend(day: str | None = None) -> dict:
    """
    So hôm nay với hôm qua: tỉ lệ thành công tăng/giảm cho từng tool + tổng thể.
    Trả {overall_delta, tools: {tool: {today, yesterday, delta, verdict}}}.
    """
    d = date.fromisoformat(day) if day else date.today()
    today_sc = scorecard(d.isoformat())
    yday_sc = scorecard((d - timedelta(days=1)).isoformat())

    tools: dict[str, dict] = {}
    names = set(today_sc["tools"]) | set(yday_sc["tools"])
    for t in names:
        tr = today_sc["tools"].get(t, {}).get("success_rate", 0.0)
        yr = yday_sc["tools"].get(t, {}).get("success_rate", 0.0)
        delta = round(tr - yr, 3)
        verdict = "khá lên" if delta > 0.01 else ("tệ đi" if delta < -0.01 else "giữ nguyên")
        tools[t] = {"today": tr, "yesterday": yr, "delta": delta, "verdict": verdict}

    overall_delta = round(today_sc["overall"]["success_rate"] - yday_sc["overall"]["success_rate"], 3)
    return {"day": today_sc["day"], "overall_delta": overall_delta, "tools": tools}


def render_scorecard(day: str | None = None) -> str:
    """Bảng điểm người-đọc-được (cho UI / báo cáo nhịp tim)."""
    sc = scorecard(day)
    o = sc["overall"]
    if o["runs"] == 0:
        return f"📊 {sc['day']}: chưa có lượt chạy kỹ năng nào."
    tr = trend(day)
    arrow = "↗" if tr["overall_delta"] > 0 else ("↘" if tr["overall_delta"] < 0 else "→")
    lines = [
        f"📊 Bảng điểm {sc['day']}: {o['ok']}/{o['runs']} thành công "
        f"({int(o['success_rate']*100)}%, {arrow} so hôm qua {tr['overall_delta']:+.0%}), "
        f"trễ TB {o['avg_ms']}ms.",
    ]
    for t, r in sorted(sc["tools"].items(), key=lambda kv: kv[1]["runs"], reverse=True):
        v = tr["tools"].get(t, {}).get("verdict", "")
        lines.append(f"  • {t}: {r['ok']}/{r['runs']} ({int(r['success_rate']*100)}%) {('— '+v) if v else ''}")
    return "\n".join(lines)


def system_thermal_check(max_cpu_percent: float = 85.0) -> dict:
    """
    Cảm biến nhiệt độ & tải phần cứng (chống nóng máy khi chạy 24/7 liên tục).
    Nếu CPU vượt max_cpu_percent (mặc định 85%), đề xuất worker nghỉ nhẹ (cool_down_s).
    """
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage("D:\\" if Path("D:\\").exists() else "C:\\").percent
        overheated = cpu > max_cpu_percent
        return {
            "ok": True,
            "cpu_percent": cpu,
            "memory_percent": mem,
            "disk_percent": disk,
            "overheated": overheated,
            "cool_down_s": 1.0 if overheated else 0.0,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "cpu_percent": 0.0, "memory_percent": 0.0, "disk_percent": 0.0, "overheated": False, "cool_down_s": 0.0, "error": str(exc)}


__all__ = ["record", "scorecard", "trend", "render_scorecard", "system_thermal_check"]
