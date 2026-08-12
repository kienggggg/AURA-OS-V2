"""
skills/connectors/calendar_sync.py
==================================
Calendar Connector (CHỈ ĐỌC) — đọc lịch định dạng .ics (iCalendar) từ một URL
(vd Google Calendar "Secret address in iCal format") và trả về SỰ KIỆN HÔM NAY.

Chỉ dùng stdlib (urllib) — GET read-only, KHÔNG ghi/sửa lịch. Lỗi mạng/parse đều
nuốt gọn -> trả rỗng, không làm sập briefing. Parser tối giản: bóc VEVENT, lấy
SUMMARY/DTSTART/DTEND/RRULE; lọc sự kiện rơi vào hôm nay (kể cả lặp DAILY/WEEKLY cơ bản).
"""

from __future__ import annotations

import logging
import sys
import urllib.request
from datetime import date
from pathlib import Path

# skills/connectors/calendar_sync.py -> parents[2] = gốc dự án (cho `from core...`).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger("aura.connectors.calendar")

_WD = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _fetch_ics(url: str, timeout: float = 10.0) -> str:
    """GET nội dung .ics (read-only). URL phải http/https. Lỗi -> ''."""
    if not url or not str(url).lower().startswith(("http://", "https://")):
        return ""
    req = urllib.request.Request(url, headers={"User-Agent": "AURA/1.0 (+read-only)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — đã validate scheme
        return resp.read().decode("utf-8", errors="replace")


def _unfold(text: str) -> list[str]:
    """Nối dòng gấp theo RFC5545 (dòng bắt đầu bằng space/tab là phần tiếp nối)."""
    out: list[str] = []
    for line in text.splitlines():
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _date_of(val: str) -> date | None:
    v = val.strip()
    d = v.split("T")[0] if "T" in v else v
    try:
        return date(int(d[0:4]), int(d[4:6]), int(d[6:8]))
    except Exception:  # noqa: BLE001
        return None


def _time_label(val: str) -> str:
    v = val.strip()
    if "T" in v:
        t = v.split("T")[1].rstrip("Z")
        try:
            return f"{t[0:2]}:{t[2:4]}"
        except Exception:  # noqa: BLE001
            return ""
    return "cả ngày"


def _weekly_today(rrule: str, dtstart: date, wd: int) -> bool:
    up = rrule.upper()
    if "BYDAY=" in up:
        part = up.split("BYDAY=")[1].split(";")[0]
        days = {_WD[x[-2:]] for x in part.split(",") if x[-2:] in _WD}
        return wd in days
    return dtstart.weekday() == wd


def _occurs_today(ev: dict, today: date, wd: int) -> bool:
    d = _date_of(ev.get("DTSTART", ""))
    if d is None:
        return False
    if d == today:
        return True
    rrule = ev.get("RRULE", "")
    if rrule and d <= today:
        up = rrule.upper()
        if "FREQ=DAILY" in up:
            return True
        if "FREQ=WEEKLY" in up:
            return _weekly_today(rrule, d, wd)
    return False


def fetch_today_events(ics_url: str | None = None) -> list[dict]:
    """Trả danh sách sự kiện hôm nay [{time, summary}], sắp theo giờ. Lỗi -> []."""
    url = ics_url
    if url is None:
        try:
            from core.config import settings
            url = settings.calendar_ics_url
        except Exception:  # noqa: BLE001
            url = None
    if not url:
        return []
    try:
        text = _fetch_ics(url)
    except Exception as exc:  # noqa: BLE001 — mạng/timeout không được làm sập
        logger.warning("Đọc .ics lỗi (bỏ qua): %s", exc)
        return []
    if not text:
        return []

    today = date.today()
    wd = today.weekday()
    events: list[dict] = []
    cur: dict | None = None
    for line in _unfold(text):
        if line.startswith("BEGIN:VEVENT"):
            cur = {}
        elif line.startswith("END:VEVENT"):
            if cur is not None and _occurs_today(cur, today, wd):
                events.append({
                    "time": _time_label(cur.get("DTSTART", "")),
                    "summary": (cur.get("SUMMARY") or "(không tên)").strip(),
                })
            cur = None
        elif cur is not None and ":" in line:
            key = line.partition(":")[0].split(";")[0].upper()
            if key in ("SUMMARY", "DTSTART", "DTEND", "RRULE"):
                cur[key] = line.partition(":")[2]
    events.sort(key=lambda e: e["time"])
    return events


def today_brief(ics_url: str | None = None) -> str:
    """Tóm tắt 1 dòng các sự kiện hôm nay cho briefing; '' nếu không có/không cấu hình."""
    evs = fetch_today_events(ics_url)
    if not evs:
        return ""
    return "; ".join(f"{e['time']} {e['summary']}" for e in evs[:12])


__all__ = ["fetch_today_events", "today_brief"]
