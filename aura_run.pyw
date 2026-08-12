"""
aura_run.pyw — Bật CẢ "não" lẫn "khuôn mặt" của AURA bằng MỘT cú, chạy NỀN ẨN.

10/08/2026: khuôn mặt của AURA đổi từ mascot Miku sang ỨNG DỤNG CHAT v3.
Mascot và health guard đã gỡ khỏi dây khởi động — xem ghi chú trong `main()`.

Phần mở rộng .pyw -> Windows chạy bằng pythonw.exe => KHÔNG cửa sổ console đen.
Đây là thứ aura_autostart.py đăng ký vào Task Scheduler: đăng nhập Windows xong là
AURA tự thức — cả bộ não (server + daemon + skills) lẫn AURA-chan (interface.avatar).

Trình tự:
  1) chạy main.py  -> server WebSocket + daemon nhịp tim (nền)
  2) chờ vài giây cho server mở cổng
  3) chạy interface.avatar -> AURA-chan (Chat Window) hiện trên màn hình, tự nối vào server

Chỉ dùng stdlib. Cả hai tiến trình con dùng pythonw -> không nháy console.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW (Windows) — tránh mọi nháy cửa sổ


def _pythonw() -> str:
    exe = Path(sys.executable)
    cand = exe.with_name("pythonw.exe")
    return str(cand if cand.exists() else exe)


def _spawn(args: list[str]) -> None:
    kwargs = {"cwd": str(ROOT)}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = _NO_WINDOW
    subprocess.Popen(args, **kwargs)  # noqa: S603 — script vận hành tin cậy, args dạng list


def main() -> int:
    pw = _pythonw()
    # 1) Não nền v2 — tổ công nhân (job scout, trend radar, janitor) vẫn ghi sổ
    #    mỗi ngày, nên GIỮ. Đây không phải phần Sếp nhìn thấy.
    _spawn([pw, str(ROOT / "main.py")])

    # 2) Khuôn mặt của AURA giờ là ỨNG DỤNG CHAT v3, không phải mascot.
    #    `aura_app.pyw` tự chờ server sẵn sàng rồi mới mở cửa sổ, nên ở đây
    #    không cần `time.sleep` đoán mò như bản cũ.
    _spawn([pw, str(ROOT / "aura_app.pyw")])

    # ĐÃ GỠ, cố ý:
    #   ui.mascot       — Sếp tắt hẳn 10/08/2026. Khuôn mặt là cửa sổ chat.
    #   ui.health_guard — Sếp tắt hẳn 05/08/2026 sau khi nó phủ khiên đen giữa
    #                     buổi phỏng vấn TEKY. `HEALTH_ENABLED=false` đã chặn
    #                     phần việc, nhưng tiến trình vẫn được đẻ ra mỗi lần
    #                     đăng nhập — giờ thì không.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
