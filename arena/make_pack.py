# -*- coding: utf-8 -*-
"""Sinh và TỰ NGHIỆM THU pack 10 đề pilot cho Coding Arena (Giai đoạn B).

Mỗi đề gồm:
  broken.py      — mã có lỗi, thí sinh được sửa
  fixed.py       — lời giải tham chiếu, KHÔNG giao cho thí sinh
  test_red.py    — test đỏ GIAO cho thí sinh (tái hiện lỗi)
  test_hidden.py — test ẨN, chỉ trọng tài chạy
  meta.json      — loại lỗi + lý do "phải chạy mới biết"

Nguyên tắc chọn đề (chốt ở lượt 004/008 của phòng thảo luận):
  1. Chỉ nhận lỗi NHÌN KHÔNG ĐOÁN RA, phải chạy mới lộ.
  2. Loại thẳng lỗi cú pháp / sai tên biến / lỗi thấy ngay trong một hàm.
  3. Đề phải có lời giải tham chiếu chạy được — không giao đề chưa tự giải nổi.

Chạy trực tiếp để sinh pack rồi nghiệm thu:
    venv/Scripts/python.exe arena/make_pack.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASKS = ROOT / "tasks"

# --------------------------------------------------------------------------
# 10 đề. Mỗi đề: (thư mục, loại, vì sao phải chạy, broken, fixed, red, hidden)
# --------------------------------------------------------------------------

PACK: list[dict] = []


def task(slug, category, why_run, broken, fixed, red, hidden):
    PACK.append({
        "slug": slug, "category": category, "why_must_run": why_run,
        "broken": broken, "fixed": fixed, "red": red, "hidden": hidden,
    })


# --- 1. Trạng thái tích luỹ: backoff giảm dần thay vì reset sau thành công -
task(
    "t01_backoff_reset", "trang-thai-tich-luy",
    "Một chu kỳ hỏng-rồi-thành-công vẫn ra số hợp lý. Chỉ lệch sau NHIỀU lần hỏng liên tiếp.",
    broken='''
class Backoff:
    """Giãn cách thử lại.

    Hợp đồng: sau MỘT lần thành công, giãn cách quay về mức đầu (`base`).
    """

    def __init__(self, base: float = 1.0, cap: float = 60.0) -> None:
        self.base = base
        self.cap = cap
        self.failures = 0

    def record_failure(self) -> None:
        self.failures += 1

    def record_success(self) -> None:
        self.failures = max(self.failures - 1, 0)

    def delay(self) -> float:
        return min(self.cap, self.base * (2 ** self.failures))
''',
    fixed='''
class Backoff:
    """Giãn cách thử lại.

    Hợp đồng: sau MỘT lần thành công, giãn cách quay về mức đầu (`base`).
    """

    def __init__(self, base: float = 1.0, cap: float = 60.0) -> None:
        self.base = base
        self.cap = cap
        self.failures = 0

    def record_failure(self) -> None:
        self.failures += 1

    def record_success(self) -> None:
        self.failures = 0

    def delay(self) -> float:
        return min(self.cap, self.base * (2 ** self.failures))
''',
    red='''
from module import Backoff


def test_one_success_returns_to_base_delay():
    b = Backoff(base=1.0, cap=60.0)
    for _ in range(5):
        b.record_failure()
    b.record_success()
    assert b.delay() == 1.0, f"sau 1 lan thanh cong van cho {b.delay()}s"
''',
    hidden='''
from module import Backoff


def test_fresh_backoff_is_base():
    assert Backoff(base=2.0).delay() == 2.0


def test_single_failure_doubles():
    b = Backoff(base=1.0)
    b.record_failure()
    assert b.delay() == 2.0


def test_cap_is_respected():
    b = Backoff(base=1.0, cap=8.0)
    for _ in range(20):
        b.record_failure()
    assert b.delay() == 8.0


def test_success_after_long_outage_resets_fully():
    b = Backoff(base=0.5, cap=100.0)
    for _ in range(10):
        b.record_failure()
    b.record_success()
    assert b.delay() == 0.5
    assert b.failures == 0


def test_alternating_failure_success_does_not_creep():
    b = Backoff(base=1.0, cap=60.0)
    for _ in range(30):
        b.record_failure()
        b.record_failure()
        b.record_success()
    assert b.delay() == 1.0


def test_success_on_healthy_backoff_is_harmless():
    b = Backoff(base=1.0)
    b.record_success()
    assert b.delay() == 1.0
''',
)

# --- 2. LRU thoái hoá thành FIFO vì get không đánh dấu vừa dùng ------------
task(
    "t02_lru_cache", "trang-thai-tich-luy",
    "Chỉ sai khi vượt sức chứa VÀ có get xen giữa. Chưa đầy thì không lộ.",
    broken='''
from collections import OrderedDict


class LRUCache:
    """Bộ nhớ đệm loại bỏ mục LÂU NHẤT KHÔNG ĐƯỢC DÙNG."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._data: OrderedDict[str, object] = OrderedDict()

    def get(self, key: str, default=None):
        if key not in self._data:
            return default
        return self._data[key]

    def put(self, key: str, value) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        while len(self._data) > self.capacity:
            self._data.popitem(last=False)
''',
    fixed='''
from collections import OrderedDict


class LRUCache:
    """Bộ nhớ đệm loại bỏ mục LÂU NHẤT KHÔNG ĐƯỢC DÙNG."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._data: OrderedDict[str, object] = OrderedDict()

    def get(self, key: str, default=None):
        if key not in self._data:
            return default
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key: str, value) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        while len(self._data) > self.capacity:
            self._data.popitem(last=False)
''',
    red='''
from module import LRUCache


def test_recently_read_key_survives_eviction():
    c = LRUCache(capacity=2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1        # "a" vừa được dùng
    c.put("c", 3)                 # phải loại "b", không phải "a"
    assert c.get("a") == 1
    assert c.get("b") is None
''',
    hidden='''
from module import LRUCache


def test_basic_put_get():
    c = LRUCache(2)
    c.put("x", 10)
    assert c.get("x") == 10


def test_missing_key_returns_default():
    assert LRUCache(2).get("nope", "d") == "d"


def test_capacity_never_exceeded():
    c = LRUCache(3)
    for i in range(50):
        c.put(f"k{i}", i)
    assert len(c._data) == 3


def test_repeated_reads_keep_key_alive():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    for _ in range(5):
        c.get("a")
    c.put("c", 3)
    assert c.get("a") == 1


def test_overwrite_refreshes_recency():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("a", 9)
    c.put("c", 3)
    assert c.get("a") == 9
    assert c.get("b") is None
''',
)

# --- 3. Hai module chuẩn hoá khoá khác nhau --------------------------------
task(
    "t03_key_normalize", "tuong-tac-hai-module",
    "Đọc riêng từng hàm đều hợp lý. Chỉ sai khi ghi và đọc gặp nhau.",
    broken='''
def normalize_key(raw: str) -> str:
    """Chuẩn hoá khoá trước khi LƯU."""
    return raw.strip().lower()


class Store:
    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    def save(self, raw_key: str, value) -> None:
        self._data[normalize_key(raw_key)] = value

    def load(self, raw_key: str, default=None):
        # đọc: cắt khoảng trắng cho gọn
        return self._data.get(raw_key.strip(), default)
''',
    fixed='''
def normalize_key(raw: str) -> str:
    """Chuẩn hoá khoá trước khi LƯU."""
    return raw.strip().lower()


class Store:
    def __init__(self) -> None:
        self._data: dict[str, object] = {}

    def save(self, raw_key: str, value) -> None:
        self._data[normalize_key(raw_key)] = value

    def load(self, raw_key: str, default=None):
        return self._data.get(normalize_key(raw_key), default)
''',
    red='''
from module import Store


def test_uppercase_key_round_trips():
    s = Store()
    s.save("  Job.Scout  ", 42)
    assert s.load("Job.Scout") == 42
''',
    hidden='''
from module import Store, normalize_key


def test_lowercase_still_works():
    s = Store()
    s.save("abc", 1)
    assert s.load("abc") == 1


def test_whitespace_ignored_both_sides():
    s = Store()
    s.save("  k  ", 5)
    assert s.load("k") == 5
    assert s.load("   k ") == 5


def test_mixed_case_lookup():
    s = Store()
    s.save("AURA", "x")
    assert s.load("aura") == "x"
    assert s.load("AuRa") == "x"


def test_missing_returns_default():
    assert Store().load("zzz", "def") == "def"


def test_normalize_key_contract_unchanged():
    assert normalize_key("  Ab ") == "ab"
''',
)

# --- 4. Retry đặt lại hạn chót -> tổng thời gian không có trần -------------
task(
    "t04_retry_deadline", "tuong-tac-hai-module",
    "Đọc thấy có timeout nên tưởng an toàn. Phải bấm giờ mới thấy tổng vượt trần.",
    broken='''
import time


class Timeout(Exception):
    pass


def call_with_retry(fn, timeout: float, attempts: int = 5, sleep: float = 0.0):
    """Gọi fn, thử lại tối đa `attempts` lần, TỔNG thời gian không quá `timeout`."""
    last_error = None
    for _ in range(attempts):
        deadline = time.monotonic() + timeout
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if time.monotonic() >= deadline:
                raise Timeout("het han") from exc
            if sleep:
                time.sleep(sleep)
    raise Timeout("het so lan thu") from last_error
''',
    fixed='''
import time


class Timeout(Exception):
    pass


def call_with_retry(fn, timeout: float, attempts: int = 5, sleep: float = 0.0):
    """Gọi fn, thử lại tối đa `attempts` lần, TỔNG thời gian không quá `timeout`."""
    deadline = time.monotonic() + timeout
    last_error = None
    for _ in range(attempts):
        if time.monotonic() >= deadline:
            raise Timeout("het han") from last_error
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if time.monotonic() >= deadline:
                raise Timeout("het han") from exc
            if sleep:
                time.sleep(sleep)
    raise Timeout("het so lan thu") from last_error
''',
    red='''
import time
import pytest
from module import call_with_retry, Timeout


def test_total_time_respects_timeout():
    def slow_failure():
        time.sleep(0.05)
        raise ValueError("hong")

    start = time.monotonic()
    with pytest.raises(Timeout):
        call_with_retry(slow_failure, timeout=0.08, attempts=5)
    elapsed = time.monotonic() - start
    assert elapsed < 0.25, f"tong thoi gian {elapsed:.3f}s vuot tran"
''',
    hidden='''
import time
import pytest
from module import call_with_retry, Timeout


def test_success_returns_immediately():
    assert call_with_retry(lambda: 7, timeout=1.0) == 7


def test_recovers_on_second_attempt():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ValueError("chua on")
        return "ok"

    assert call_with_retry(flaky, timeout=1.0, attempts=3) == "ok"
    assert calls["n"] == 2


def test_attempts_exhausted_raises_timeout():
    with pytest.raises(Timeout):
        call_with_retry(lambda: (_ for _ in ()).throw(ValueError("x")),
                        timeout=5.0, attempts=2)


def test_deadline_is_total_not_per_attempt():
    def slow_failure():
        time.sleep(0.04)
        raise ValueError("hong")

    start = time.monotonic()
    with pytest.raises(Timeout):
        call_with_retry(slow_failure, timeout=0.06, attempts=10)
    assert time.monotonic() - start < 0.30


def test_no_call_after_deadline_passed():
    calls = {"n": 0}

    def counter():
        calls["n"] += 1
        time.sleep(0.03)
        raise ValueError("x")

    with pytest.raises(Timeout):
        call_with_retry(counter, timeout=0.05, attempts=20)
    assert calls["n"] <= 3
''',
)

# --- 5. Phân vị: chỉ số làm tròn vượt biên ở p cao -------------------------
task(
    "t05_percentile_edge", "bien-du-lieu-that",
    "Đúng với p=50 và n chẵn. Chỉ vỡ ở p sát 100 hoặc n=1 — phải chạy đủ biên.",
    broken='''
def percentile(values: list[float], p: float) -> float:
    """Phân vị thứ p (0..100) theo phép nội suy tuyến tính."""
    if not values:
        raise ValueError("danh sach rong")
    ordered = sorted(values)
    pos = (len(ordered) - 1) * (p / 100.0)
    lower = int(pos)
    frac = pos - lower
    return ordered[lower] + (ordered[lower + 1] - ordered[lower]) * frac
''',
    fixed='''
def percentile(values: list[float], p: float) -> float:
    """Phân vị thứ p (0..100) theo phép nội suy tuyến tính."""
    if not values:
        raise ValueError("danh sach rong")
    ordered = sorted(values)
    pos = (len(ordered) - 1) * (p / 100.0)
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    frac = pos - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * frac
''',
    red='''
from module import percentile


def test_p100_does_not_crash():
    assert percentile([1.0, 2.0, 3.0], 100) == 3.0
''',
    hidden='''
import pytest
from module import percentile


def test_median_odd():
    assert percentile([3.0, 1.0, 2.0], 50) == 2.0


def test_median_even():
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5


def test_p0_is_min():
    assert percentile([5.0, 1.0, 9.0], 0) == 1.0


def test_single_element_any_percentile():
    for p in (0, 25, 50, 99, 100):
        assert percentile([7.0], p) == 7.0


def test_p99_interpolates():
    got = percentile([0.0, 100.0], 99)
    assert abs(got - 99.0) < 1e-9


def test_empty_raises():
    with pytest.raises(ValueError):
        percentile([], 50)
''',
)

# --- 6. Cắt chuỗi theo BYTE làm hỏng dấu tiếng Việt ------------------------
task(
    "t06_vietnamese_truncate", "bien-du-lieu-that",
    "Tiếng Anh luôn đúng. Chỉ hỏng với ký tự nhiều byte — phải chạy dữ liệu thật.",
    broken='''
def truncate(text: str, max_chars: int, suffix: str = "...") -> str:
    """Cắt còn tối đa `max_chars` KÝ TỰ, thêm hậu tố nếu bị cắt."""
    if len(text) <= max_chars:
        return text
    raw = text.encode("utf-8")[: max_chars - len(suffix)]
    return raw.decode("utf-8", errors="ignore") + suffix
''',
    fixed='''
def truncate(text: str, max_chars: int, suffix: str = "...") -> str:
    """Cắt còn tối đa `max_chars` KÝ TỰ, thêm hậu tố nếu bị cắt.

    Kết quả KHÔNG BAO GIỜ dài quá `max_chars`, kể cả khi hậu tố dài hơn
    giới hạn — lúc đó chính hậu tố bị cắt.
    """
    if len(text) <= max_chars:
        return text
    if max_chars <= 0:
        return ""
    if len(suffix) >= max_chars:
        return suffix[:max_chars]
    return text[: max_chars - len(suffix)] + suffix
''',
    red='''
from module import truncate


def test_vietnamese_keeps_characters_not_bytes():
    text = "Đấu La Đại Lục hồi thứ nhất"
    got = truncate(text, 15)
    assert len(got) == 15, f"dai {len(got)} thay vi 15: {got!r}"
    assert got.endswith("...")
''',
    hidden='''
from module import truncate


def test_short_text_untouched():
    assert truncate("abc", 10) == "abc"


def test_ascii_truncation_length():
    got = truncate("abcdefghij", 6)
    assert len(got) == 6
    assert got.endswith("...")


def test_no_replacement_or_mojibake():
    text = "Sếp ơi, xe đã chạy thẳng rồi ạ"
    got = truncate(text, 12)
    assert "\\ufffd" not in got
    assert len(got) == 12


def test_exact_boundary_not_truncated():
    assert truncate("Đấu La", 6) == "Đấu La"


def test_all_multibyte():
    got = truncate("ăâêôơư" * 5, 8)
    assert len(got) == 8


def test_never_exceeds_limit_at_any_size():
    text = "Đấu La Đại Lục hồi thứ nhất"
    for limit in (0, 1, 2, 3, 4, 7, 15, 26):
        got = truncate(text, limit)
        assert len(got) <= limit, f"limit={limit} nhung tra ve {len(got)} ky tu: {got!r}"


def test_zero_limit_returns_empty():
    assert truncate("Đấu La", 0) == ""


def test_long_custom_suffix_is_itself_trimmed():
    got = truncate("Đấu La Đại Lục", 4, suffix="[da cat]")
    assert len(got) <= 4


def test_suffix_shorter_than_limit_keeps_content():
    got = truncate("Đấu La Đại Lục", 6)
    assert len(got) == 6
    assert got.endswith("...")
    assert got[0] == "Đ"
''',
)

# --- 7. Nuốt ngoại lệ: test đỏ hiện ở chỗ khác nơi gây lỗi -----------------
task(
    "t07_swallowed_error", "nuot-ngoai-le",
    "Triệu chứng hiện ở hàm đếm, còn nguyên nhân nằm ở hàm nạp. Đọc chỗ đỏ không ra.",
    broken='''
def parse_record(line: str) -> dict:
    name, _, score = line.partition("=")
    return {"name": name.strip(), "score": int(score)}


def load_records(lines: list[str]) -> list[dict]:
    out = []
    for line in lines:
        try:
            out.append(parse_record(line))
        except Exception:
            pass
    return out


def total_score(lines: list[str]) -> int:
    return sum(r["score"] for r in load_records(lines))
''',
    fixed='''
class BadRecord(ValueError):
    pass


def parse_record(line: str) -> dict:
    name, sep, score = line.partition("=")
    if not sep or not score.strip():
        raise BadRecord(f"dong khong hop le: {line!r}")
    try:
        value = int(score.strip())
    except ValueError as exc:
        raise BadRecord(f"diem khong phai so: {line!r}") from exc
    return {"name": name.strip(), "score": value}


def load_records(lines: list[str]) -> list[dict]:
    return [parse_record(line) for line in lines]


def total_score(lines: list[str]) -> int:
    return sum(r["score"] for r in load_records(lines))
''',
    red='''
import pytest
from module import total_score


def test_bad_line_is_not_silently_dropped():
    lines = ["a=1", "b=xx", "c=3"]
    with pytest.raises(Exception):
        total_score(lines)
''',
    hidden='''
import pytest
from module import total_score, load_records, parse_record


def test_all_valid_sums():
    assert total_score(["a=1", "b=2"]) == 3


def test_parse_single():
    assert parse_record("x = 5") == {"name": "x", "score": 5}


def test_missing_separator_raises():
    with pytest.raises(Exception):
        parse_record("khong co dau bang")


def test_empty_score_raises():
    with pytest.raises(Exception):
        parse_record("a=")


def test_load_records_keeps_every_valid_row():
    assert len(load_records(["a=1", "b=2", "c=3"])) == 3


def test_error_message_names_the_bad_line():
    try:
        parse_record("b=xx")
    except Exception as exc:
        assert "b=xx" in str(exc)
    else:
        raise AssertionError("phai nem loi")
''',
)

# --- 8. Sai thứ tự: kiểm hạn TRƯỚC khi cập nhật nhịp tim -------------------
task(
    "t08_heartbeat_order", "sai-thu-tu-nhip",
    "Đọc tuần tự thấy hợp lý. Chỉ sai đúng ở mốc bằng hạn — phải chạy mới lộ.",
    broken='''
class Watchdog:
    """Ngắt nếu quá `timeout` giây không có nhịp tim."""

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        self.last_seen: float | None = None
        self.stopped = False

    def ping(self, now: float) -> None:
        if self.last_seen is not None and now - self.last_seen > self.timeout:
            self.stopped = True
        if not self.stopped:
            self.last_seen = now

    def tick(self, now: float) -> bool:
        if self.last_seen is not None and now - self.last_seen > self.timeout:
            self.stopped = True
        return not self.stopped
''',
    fixed='''
class Watchdog:
    """Ngắt nếu quá `timeout` giây không có nhịp tim."""

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        self.last_seen: float | None = None
        self.stopped = False

    def ping(self, now: float) -> None:
        if self.stopped:
            return
        self.last_seen = now

    def tick(self, now: float) -> bool:
        if self.last_seen is not None and now - self.last_seen > self.timeout:
            self.stopped = True
        return not self.stopped
''',
    red='''
from module import Watchdog


def test_late_ping_revives_before_tick_declares_death():
    w = Watchdog(timeout=1.0)
    w.ping(0.0)
    w.ping(1.5)          # trễ, nhưng ĐÃ tới nơi trước khi ai kiểm tra
    assert w.tick(1.6) is True
    assert w.stopped is False
''',
    hidden='''
from module import Watchdog


def test_regular_pings_stay_alive():
    w = Watchdog(timeout=1.0)
    for t in (0.0, 0.5, 1.0, 1.5):
        w.ping(t)
        assert w.tick(t) is True


def test_silence_stops_it():
    w = Watchdog(timeout=1.0)
    w.ping(0.0)
    assert w.tick(2.0) is False
    assert w.stopped is True


def test_exactly_at_timeout_is_still_alive():
    w = Watchdog(timeout=1.0)
    w.ping(0.0)
    assert w.tick(1.0) is True


def test_stopped_is_terminal():
    w = Watchdog(timeout=1.0)
    w.ping(0.0)
    w.tick(5.0)
    w.ping(5.1)
    assert w.tick(5.2) is False


def test_no_ping_yet_is_alive():
    assert Watchdog(timeout=1.0).tick(99.0) is True


def test_delayed_ping_is_still_a_heartbeat():
    w = Watchdog(timeout=2.0)
    w.ping(0.0)
    w.ping(5.0)          # trễ, nhưng nhịp tim ĐÃ tới
    assert w.stopped is False
    assert w.tick(5.5) is True


def test_recovery_after_gap_repeats():
    w = Watchdog(timeout=1.0)
    for t in (0.0, 3.0, 6.0, 9.0):
        w.ping(t)
        assert w.tick(t + 0.1) is True, f"chet oan tai t={t}"


def test_ping_updates_last_seen_even_when_late():
    w = Watchdog(timeout=1.0)
    w.ping(0.0)
    w.ping(10.0)
    assert w.last_seen == 10.0
''',
)

# --- 9. Rò tài nguyên: luồng sinh ra không bao giờ thu hồi -----------------
task(
    "t09_thread_leak", "ro-tai-nguyen",
    "Một lần gọi hoàn toàn bình thường. Chỉ lộ khi chạy lặp và đếm luồng sống.",
    broken='''
import threading


class Worker:
    """Chạy việc nền, mỗi lệnh một luồng."""

    def __init__(self) -> None:
        self.done: list[int] = []
        self._threads: list[threading.Thread] = []

    def submit(self, value: int) -> None:
        t = threading.Thread(target=self.done.append, args=(value,), daemon=True)
        t.start()
        self._threads.append(t)

    def wait(self) -> None:
        for t in self._threads:
            t.join()
''',
    fixed='''
import threading


class Worker:
    """Chạy việc nền, mỗi lệnh một luồng."""

    def __init__(self) -> None:
        self.done: list[int] = []
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    def _run(self, value: int) -> None:
        with self._lock:
            self.done.append(value)

    def submit(self, value: int) -> None:
        self._threads = [t for t in self._threads if t.is_alive()]
        t = threading.Thread(target=self._run, args=(value,), daemon=True)
        t.start()
        self._threads.append(t)

    def wait(self) -> None:
        for t in self._threads:
            t.join()
        self._threads = [t for t in self._threads if t.is_alive()]
''',
    red='''
from module import Worker


def test_finished_threads_are_not_retained():
    w = Worker()
    for i in range(300):
        w.submit(i)
    w.wait()
    assert len(w._threads) < 50, f"con giu {len(w._threads)} luong da xong"
''',
    hidden='''
from module import Worker


def test_single_submit_completes():
    w = Worker()
    w.submit(1)
    w.wait()
    assert w.done == [1]


def test_all_values_recorded():
    w = Worker()
    for i in range(100):
        w.submit(i)
    w.wait()
    assert sorted(w.done) == list(range(100))


def test_repeated_batches_do_not_accumulate():
    w = Worker()
    for _ in range(5):
        for i in range(60):
            w.submit(i)
        w.wait()
    assert len(w._threads) < 50


def test_wait_is_idempotent():
    w = Worker()
    w.submit(1)
    w.wait()
    w.wait()
    assert w.done == [1]
''',
)

# --- 10. BẪY TỰ KHAI: báo ACK mà không hề tác động ------------------------
task(
    "t10_fake_ack", "bay-tu-khai",
    "Giá trị trả về LUÔN đúng. Chỉ sai ở HỆ QUẢ — phải kiểm trạng thái phần cứng.",
    broken='''
class MotorDriver:
    """Phần cứng giả lập: chỉ nó mới biết bánh có quay hay không."""

    def __init__(self) -> None:
        self.position = 0.0
        self.online = True

    def drive(self, direction: str, seconds: float) -> None:
        if not self.online:
            raise RuntimeError("driver offline")
        step = {"forward": 1.0, "backward": -1.0}[direction]
        self.position += step * seconds


class Rover:
    def __init__(self, driver: MotorDriver) -> None:
        self.driver = driver
        self.log: list[str] = []

    def move(self, direction: str, seconds: float) -> str:
        self.log.append(f"{direction}:{seconds}")
        return f"ACK:{direction.upper()}"
''',
    fixed='''
class MotorDriver:
    """Phần cứng giả lập: chỉ nó mới biết bánh có quay hay không."""

    def __init__(self) -> None:
        self.position = 0.0
        self.online = True

    def drive(self, direction: str, seconds: float) -> None:
        if not self.online:
            raise RuntimeError("driver offline")
        step = {"forward": 1.0, "backward": -1.0}[direction]
        self.position += step * seconds


class Rover:
    def __init__(self, driver: MotorDriver) -> None:
        self.driver = driver
        self.log: list[str] = []

    def move(self, direction: str, seconds: float) -> str:
        self.driver.drive(direction, seconds)
        self.log.append(f"{direction}:{seconds}")
        return f"ACK:{direction.upper()}"
''',
    red='''
from module import Rover, MotorDriver


def test_ack_means_the_wheels_actually_turned():
    d = MotorDriver()
    rover = Rover(d)
    assert rover.move("forward", 3.0) == "ACK:FORWARD"
    assert d.position == 3.0, "bao ACK nhung banh khong quay"
''',
    hidden='''
import pytest
from module import Rover, MotorDriver


def test_backward_moves_the_other_way():
    d = MotorDriver()
    Rover(d).move("backward", 2.0)
    assert d.position == -2.0


def test_duration_is_respected():
    d = MotorDriver()
    Rover(d).move("forward", 0.5)
    assert d.position == 0.5


def test_offline_driver_must_not_return_ack():
    d = MotorDriver()
    d.online = False
    with pytest.raises(RuntimeError):
        Rover(d).move("forward", 1.0)


def test_failed_move_is_not_logged_as_done():
    d = MotorDriver()
    d.online = False
    rover = Rover(d)
    with pytest.raises(RuntimeError):
        rover.move("forward", 1.0)
    assert rover.log == []


def test_sequence_accumulates():
    d = MotorDriver()
    r = Rover(d)
    r.move("forward", 2.0)
    r.move("backward", 0.5)
    assert d.position == 1.5
''',
)


# --------------------------------------------------------------------------
# Sinh pack
# --------------------------------------------------------------------------

def write_pack() -> None:
    if TASKS.exists():
        shutil.rmtree(TASKS)
    TASKS.mkdir(parents=True)
    for index, item in enumerate(PACK, start=1):
        folder = TASKS / item["slug"]
        folder.mkdir()
        (folder / "broken.py").write_text(item["broken"].lstrip("\n"), encoding="utf-8")
        (folder / "fixed.py").write_text(item["fixed"].lstrip("\n"), encoding="utf-8")
        (folder / "test_red.py").write_text(item["red"].lstrip("\n"), encoding="utf-8")
        (folder / "test_hidden.py").write_text(item["hidden"].lstrip("\n"), encoding="utf-8")
        meta = {
            "id": f"pilot-{index:02d}-{item['slug']}",
            "batch_id": "pilot-b1",
            "category": item["category"],
            "why_must_run": item["why_must_run"],
            "failing_test": "test_red.py",
            "files_allowed": ["module.py"],
            "forbidden_paths": ["test_red.py", "test_hidden.py", "fixed.py"],
            "budget_s": 600,
            "requested_max_output_tokens": 60000,
            "budget_prompt_chars": 50000,
            "budget_reply_chars": 240000,
            "network": False,
        }
        (folder / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


# --------------------------------------------------------------------------
# Nghiệm thu: đề chỉ hợp lệ khi ĐỎ trước và XANH sau
# --------------------------------------------------------------------------

def _run_pytest(workdir: Path, test_file: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", test_file, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=workdir, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def _stage(folder: Path, source: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="arena_"))
    shutil.copy(folder / source, tmp / "module.py")
    shutil.copy(folder / "test_red.py", tmp / "test_red.py")
    shutil.copy(folder / "test_hidden.py", tmp / "test_hidden.py")
    return tmp


def verify() -> int:
    print("NGHIEM THU PACK — moi de phai DO truoc, XANH sau\n")
    header = f"{'de':<26}{'red/broken':<13}{'hid/broken':<13}{'red/fixed':<12}{'hid/fixed':<12}{'ket luan'}"
    print(header)
    print("-" * len(header))
    bad = 0
    for item in PACK:
        folder = TASKS / item["slug"]
        broken_dir = _stage(folder, "broken.py")
        fixed_dir = _stage(folder, "fixed.py")
        try:
            red_broken, _ = _run_pytest(broken_dir, "test_red.py")
            hid_broken, _ = _run_pytest(broken_dir, "test_hidden.py")
            red_fixed, out_rf = _run_pytest(fixed_dir, "test_red.py")
            hid_fixed, out_hf = _run_pytest(fixed_dir, "test_hidden.py")
        finally:
            shutil.rmtree(broken_dir, ignore_errors=True)
            shutil.rmtree(fixed_dir, ignore_errors=True)

        ok = (not red_broken) and (not hid_broken) and red_fixed and hid_fixed
        if not ok:
            bad += 1
        mark = lambda v: "DO" if not v else "XANH"
        print(
            f"{item['slug']:<26}{mark(red_broken):<13}{mark(hid_broken):<13}"
            f"{mark(red_fixed):<12}{mark(hid_fixed):<12}{'OK' if ok else '*** HONG ***'}"
        )
        if not ok:
            if not red_fixed:
                print("    test_red van do tren ban vá:\n" + out_rf[-700:])
            if not hid_fixed:
                print("    test_hidden van do tren ban vá:\n" + out_hf[-700:])
    print()
    if bad:
        print(f"KHONG DAT: {bad}/{len(PACK)} de hong — chua duoc dung lam de thi.")
    else:
        print(f"DAT: ca {len(PACK)} de deu do-truoc/xanh-sau. Pack dung duoc.")
    return 1 if bad else 0


if __name__ == "__main__":
    write_pack()
    raise SystemExit(verify())
