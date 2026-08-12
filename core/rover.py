"""TAY LÁI CỦA AURA — điều khiển xe rover ESP32 qua Bluetooth (BLE).

Xe lắp xong và nghiệm thu chạy thẳng 06/08/2026 (ESP32 + TB6612 + US-100 +
2 motor TT). Firmware `robot/esp32_aura_rover` CHỈ nhận lệnh qua BLE, không nhận
qua cáp USB — đó là thiết kế "xương sống an toàn" của nó.

⚠️ ĐÂY LÀ VẬT LÝ. Xe chạy thật, đâm được vào đồ đạc, rơi được khỏi bàn.
Nên mọi lệnh ở đây đều có TRẦN THỜI GIAN và TỰ DỪNG sau khi chạy xong.

Bốn lớp an toàn nằm sẵn trong firmware (đã nghiệm thu thật):
  1. lệnh DỪNG
  2. quá 1,1 giây không có tín hiệu sống -> tự dừng
  3. vật cản ≤ 150mm -> tự dừng (chỉ chặn lệnh TIẾN)
  4. mất BLE -> tự dừng

AURA thêm lớp thứ 5 ở phía này: **trần thời gian mỗi lệnh** + **luôn gửi STOP**.
Không dựa hết vào firmware — nó ở xa, dây có thể đứt, pin có thể yếu.
"""

from __future__ import annotations

import asyncio
import logging
import re

logger = logging.getLogger("aura.rover")

DEVICE_NAME = "AURA-ROVER"
_CMD_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
_TEL_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

# Trần cứng: KHÔNG lệnh nào được chạy lâu hơn ngần này, dù Sếp gõ số to hơn.
MAX_RUN_S = 3.0
DEFAULT_RUN_S = 1.5
_HEARTBEAT_S = 0.4          # firmware dừng nếu quá 1,1s không nhận tín hiệu

# Tốc độ (0-255). Đo thật 06/08: ở 255 xe đi 1,13m trong 3 giây — quá nhanh
# trong nhà, chưa kịp nhìn đã đâm. Hạ xuống cho dễ quan sát và can thiệp.
# Xe còn hơi lệch ở tốc này, nhưng KHÔNG chỉnh hệ số bù thêm: chạy chậm thì lệch
# ít, và sau này camera tự lái sẽ bù bằng vòng kín — chỉnh mù bây giờ là công cốc.
SPEED_SLOW = 95
SPEED_NORMAL = 110
SPEED_FAST = 150

_MOVES: dict[str, tuple[str, str]] = {
    # từ khoá -> (lệnh firmware, tên tiếng Việt)
    "tiến":   ("F", "tiến"),
    "tien":   ("F", "tiến"),
    "đi":     ("F", "tiến"),
    "lùi":    ("B", "lùi"),
    "lui":    ("B", "lùi"),
    "trái":   ("L", "xoay trái"),
    "trai":   ("L", "xoay trái"),
    "phải":   ("R", "xoay phải"),
    "phai":   ("R", "xoay phải"),
}
_STOP_WORDS = ("dừng", "dung lai", "dừng lại", "stop", "đứng", "phanh")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def is_rover_command(text: str) -> bool:
    """Câu này có phải lệnh điều khiển xe không?

    Phải có TỪ CHỈ XE (xe/robot/rover) để không cướp mất câu chat thường —
    "đi ngủ đi" hay "lùi lại chút" không được làm xe chạy.
    """
    t = _norm(text)
    if not re.search(r"\b(xe|robot|rover)\b", t):
        return False
    if any(w in t for w in _STOP_WORDS):
        return True
    if re.search(r"khoảng cách|khoang cach|phía trước|phia truoc|thấy gì|thay gi", t):
        return True
    return any(k in t for k in _MOVES)


def _speed_of(t: str) -> int:
    """Chọn mức tốc theo lời Sếp; mặc định CHẬM cho an toàn trong nhà."""
    if re.search(r"nhanh|gấp|gap|tối đa|toi da", t):
        return SPEED_FAST
    if re.search(r"chậm|cham|từ từ|tu tu|nhẹ|nhe", t):
        return SPEED_SLOW
    return SPEED_NORMAL


def _parse(text: str) -> tuple[str, float, str]:
    """-> (lệnh firmware kèm tốc, số giây, mô tả). 'S' = dừng, '?' = hỏi khoảng cách."""
    t = _norm(text)
    if any(w in t for w in _STOP_WORDS):
        return "S", 0.0, "dừng"
    if re.search(r"khoảng cách|khoang cach|phía trước|phia truoc|thấy gì|thay gi", t):
        return "?", 0.0, "đo khoảng cách"

    cmd, name = "F", "tiến"
    for key, (c, n) in _MOVES.items():
        if key in t:
            cmd, name = c, n
            break

    secs = DEFAULT_RUN_S
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(giây|giay|s\b)", t)
    if m:
        secs = float(m.group(1).replace(",", "."))

    # Gửi kèm tốc độ -> hạ tốc mà KHÔNG phải nạp lại firmware.
    return f"{cmd}:{_speed_of(t)}", max(0.2, min(secs, MAX_RUN_S)), name


async def _drive(cmd: str, secs: float) -> dict:
    """Nối BLE, chạy đúng `secs` giây, LUÔN gửi STOP, rồi ngắt."""
    from bleak import BleakClient, BleakScanner

    dev = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10.0)
    if dev is None:
        return {"ok": False, "error": "không thấy xe — xe đã bật nguồn chưa?"}

    dist: dict[str, int | None] = {"mm": None}
    notes: list[str] = []

    def _on_tel(_h, data: bytearray) -> None:
        s = data.decode(errors="ignore").strip()
        m = re.search(r"DIST:(\d+)", s)
        if m:
            dist["mm"] = int(m.group(1))
        if "STOP:" in s:
            notes.append(s.split("STOP:")[1].split(";")[0].strip())

    client = BleakClient(dev, timeout=20.0)
    await client.connect()
    try:
        await client.start_notify(_TEL_UUID, _on_tel)
        await asyncio.sleep(1.0)              # chờ nhịp telemetry đầu

        if cmd == "?":
            return {"ok": True, "dist_mm": dist["mm"], "moved": False}
        if cmd == "S":
            await client.write_gatt_char(_CMD_UUID, b"S", response=False)
            return {"ok": True, "dist_mm": dist["mm"], "moved": False}

        stop = asyncio.Event()

        async def _hb() -> None:
            while not stop.is_set():
                try:
                    await client.write_gatt_char(_CMD_UUID, b"PING", response=False)
                except Exception:  # noqa: BLE001 — mất kết nối: firmware tự dừng
                    return
                await asyncio.sleep(_HEARTBEAT_S)

        beat = asyncio.create_task(_hb())
        try:
            await client.write_gatt_char(_CMD_UUID, cmd.encode(), response=False)
            await asyncio.sleep(min(secs, MAX_RUN_S))
        finally:
            # LUÔN dừng, kể cả khi trên có lỗi.
            try:
                await client.write_gatt_char(_CMD_UUID, b"S", response=False)
            except Exception:  # noqa: BLE001
                pass
            stop.set()
            await beat
        await asyncio.sleep(0.5)
        return {"ok": True, "dist_mm": dist["mm"], "moved": True, "notes": notes}
    finally:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass


def handle_rover_command(text: str) -> str:
    """Thực thi lệnh xe và trả lời bằng tiếng Việt. Không bao giờ ném lỗi ra ngoài."""
    cmd, secs, name = _parse(text)
    try:
        res = asyncio.run(_drive(cmd, secs))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Điều khiển xe lỗi: %s", exc)
        return f"⚠️ Không điều khiển được xe: {exc}"

    if not res.get("ok"):
        return f"⚠️ {res.get('error', 'không rõ lỗi')}"

    d = res.get("dist_mm")
    khoang = f"{d} mm ({d/10:.0f} cm)" if isinstance(d, int) else "chưa đọc được"

    if cmd == "?":
        return f"📏 Phía trước xe: {khoang}."
    if cmd == "S":
        return f"🛑 Đã dừng xe. Phía trước: {khoang}."

    msg = f"🚗 Xe đã {name} {secs:g} giây rồi tự dừng. Phía trước: {khoang}."
    for n in res.get("notes") or []:
        if n and n != "COMMAND":
            msg += f"\n⚠️ Firmware tự cắt giữa chừng, lý do: {n}"
    return msg
