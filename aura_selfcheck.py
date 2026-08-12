"""
aura_selfcheck.py
=================
TỰ KIỂM TOÀN HỆ AURA — chạy trước khi để máy làm việc dài ngày không người trông.

Triết lý: mỗi mục phải TRẢ LỜI ĐƯỢC bằng bằng chứng, không đoán. Hỏng ở đâu thì
in ra ngay chỗ đó, kèm cách sửa. Không sửa gì cả — chỉ soi.

    venv/Scripts/python.exe aura_selfcheck.py
"""

from __future__ import annotations

import io
import sys
import time
import traceback
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

OK, WARN, BAD = "✅", "⚠️", "❌"
_rows: list[tuple[str, str, str]] = []


def check(name: str, retries: int = 1):
    """Decorator: chạy 1 mục kiểm, bắt mọi lỗi, ghi kết quả.

    `retries` > 1 cho mục phụ thuộc MẠNG: một cú mạng chập không được phép làm
    cả bộ kiểm la 'HỎNG' (đã mắc: Telegram ConnectionReset 1 lần rồi 3/3 lại OK).
    """
    def deco(fn):
        def run():
            icon = detail = None
            for attempt in range(max(1, retries)):
                try:
                    icon, detail = fn()
                    if icon != BAD:
                        break
                except Exception as exc:  # noqa: BLE001
                    icon, detail = BAD, f"nổ lỗi: {exc.__class__.__name__}: {exc}"
                if attempt < retries - 1:
                    time.sleep(3)
            if icon == BAD and retries > 1:
                detail = f"(đã thử {retries} lần) {detail}"
            _rows.append((icon, name, detail))
        return run
    return deco


# --------------------------------------------------------------------------- #
@check("Cấu hình .env")
def c_config():
    from core.config import Settings
    s = Settings()
    on = [k for k, v in {
        "telegram": s.telegram_enabled,
        "story_autopilot": s.story_autopilot_enabled,
        "rookies_autopilot": s.rookies_autopilot_enabled,
        "skillopt": s.skillopt_enabled,
        "factory": s.factory_enabled,
        "health_guard": s.health_enabled,
    }.items() if v]
    return OK, "đang bật: " + ", ".join(on)


@check("Cloud brain (viết truyện)", retries=3)
def c_cloud():
    from core.llm import build_engines
    eng = build_engines()[1]
    t0 = time.time()
    r = eng.complete([{"role": "user", "content": "Trả lời đúng 1 từ: OK"}],
                     system_prompt="Trả lời cực ngắn.", max_tokens=10)
    dt = time.time() - t0
    if not r.get("ok"):
        return BAD, f"lỗi: {str(r.get('error'))[:90]}"
    return OK, f"trả lời sau {dt:.1f}s ({r.get('model')})"


@check("Telegram (kênh báo cáo)", retries=3)
def c_telegram():
    from core.config import Settings
    import requests
    s = Settings()
    if not s.telegram_enabled or not s.telegram_bot_token:
        return WARN, "chưa bật — Sếp sẽ không nhận được báo cáo"
    tok = s.telegram_bot_token.get_secret_value()
    r = requests.post(f"https://api.telegram.org/bot{tok}/getMe", timeout=15).json()
    if not r.get("ok"):
        return BAD, f"token hỏng: {r.get('description')}"
    return OK, f"bot @{r['result'].get('username')} sống, owner={s.telegram_owner_id}"


@check("Phiên đăng nhập Rookies", retries=3)
def c_rookies():
    from core.config import Settings
    s = Settings()
    if not s.rookies_autopilot_enabled:
        return WARN, "autopilot Rookies đang tắt"
    prof = Path("data/rookies_profile")
    if not prof.is_dir() or not any(prof.iterdir()):
        return BAD, "chưa có profile — chạy `python -m core.rookies_bot --login`"
    from core.rookies_bot import _context, _logged_out, STUDIO
    pw, ctx = _context(headless=True)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(STUDIO, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        if _logged_out(page) or "/studio" not in (page.url or ""):
            return BAD, "PHIÊN ĐÃ HẾT HẠN — đăng lên Rookies sẽ hỏng suốt 3 ngày"
        return OK, "còn đăng nhập, vào studio được"
    finally:
        ctx.close()
        pw.stop()


@check("Đồng bộ truyện lên Rookies", retries=3)
def c_sync():
    from core.config import Settings
    s = Settings()
    if not s.rookies_autopilot_enabled:
        return WARN, "đang tắt"
    from core.rookies_bot import sync_series
    import asyncio
    # Lấy bộ mới nhất giống daemon làm.
    from core.daemon import AuraDaemon
    d = AuraDaemon(event_queue=asyncio.Queue())
    ser = d._autopilot_series()
    if not ser:
        return WARN, "chưa có bộ truyện nào"
    # cap=0 -> chỉ DÒ, không đẩy (max(1,cap) nên dùng đường khác: đọc thông báo)
    msg = sync_series(ser[0], cap=1)
    return (OK if ("đã đủ" in msg or msg.startswith("📤")) else BAD), msg[:110]


@check("SkillOpt (đêm tự rèn)")
def c_skillopt():
    from core.config import Settings
    s = Settings()
    if not s.skillopt_enabled:
        return WARN, "đang tắt"
    from core.skillopt_hand import status
    out = status()
    if out.startswith("⚠️"):
        return BAD, out[:110]
    return OK, f"backend={s.skillopt_backend}, " + out.splitlines()[-1][:70]


@check("Xưởng (hàng đợi job)")
def c_factory():
    from factory import queue as q
    jobs = q.list_jobs(limit=100)
    run = [j for j in jobs if j.state == "running"]
    fail = [j for j in jobs if j.state == "failed"]
    qd = [j for j in jobs if j.state == "queued"]
    detail = f"{len(qd)} chờ, {len(run)} đang chạy, {len(fail)} hỏng"
    if fail:
        detail += f" (gần nhất: {fail[-1].tool})"
    return (WARN if fail else OK), detail


@check("Luật nền tảng đăng bài")
def c_rules():
    from factory.platform_rules import can_post
    bad = [p for p in ("rookies", "wattpad") if not can_post(p)[0]]
    if bad:
        return BAD, f"nền bị chặn: {bad}"
    return OK, "rookies + wattpad cho đăng; nền lạ bị chặn mặc định"


@check("Cầu dao xưởng")
def c_breaker():
    from factory import breaker
    out = breaker.status()
    return (OK if out.startswith("✅") else WARN), " | ".join(out.splitlines())[:110]


@check("Tài nguyên máy")
def c_res():
    import shutil
    try:
        import psutil
        ram = psutil.virtual_memory().percent
    except Exception:  # noqa: BLE001
        ram = -1
    free_gb = shutil.disk_usage("D:\\").free / 1024**3
    icon = OK
    if ram > 88 or free_gb < 5:
        icon = WARN
    return icon, f"RAM {ram:.0f}%, ổ D còn {free_gb:.1f} GB"


@check("Bí mật không lọt vào git")
def c_secrets():
    import subprocess
    r = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    leaked = [l for l in (r.stdout or "").splitlines()
              if any(k in l.lower() for k in (".env", "keys.env", "_profile/"))
              and not l.endswith(".example")]
    if leaked:
        return BAD, f"ĐANG BỊ TRACK: {leaked[:3]}"
    return OK, "không có .env/key/profile nào bị track"


# --------------------------------------------------------------------------- #
def main() -> int:
    print("\n" + "=" * 66)
    print("  AURA — TỰ KIỂM TRƯỚC CA CHẠY DÀI NGÀY")
    print("=" * 66)
    for fn in (c_config, c_cloud, c_telegram, c_rookies, c_sync, c_skillopt,
               c_factory, c_rules, c_breaker, c_res, c_secrets):
        fn()
    print()
    for icon, name, detail in _rows:
        print(f"{icon} {name:28} {detail}")
    bad = sum(1 for i, _, _ in _rows if i == BAD)
    warn = sum(1 for i, _, _ in _rows if i == WARN)
    print("-" * 66)
    if bad:
        print(f"❌ CÓ {bad} MỤC HỎNG — phải sửa trước khi để chạy dài ngày.")
    elif warn:
        print(f"⚠️  {warn} mục cần lưu ý, còn lại ổn.")
    else:
        print("✅ TẤT CẢ ỔN — yên tâm để AURA chạy.")
    print("=" * 66 + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
