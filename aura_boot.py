"""
aura_boot.py — Trình tự ĐÁNH THỨC hệ điều hành AURA.

Chạy MỘT lệnh để kiểm tra "ngôi nhà thông minh" đã sẵn sàng thức dậy chưa:
    python aura_boot.py

Kiểm: Python, thư viện (bắt buộc + tuỳ chọn), file .env, Ollama + model local,
registry khám phá skills, và import các module lõi. Cuối cùng báo SẴN SÀNG hay
liệt kê đúng việc cần sửa (kèm lệnh). Bản thân doctor CHỈ dùng stdlib nên luôn
chạy được kể cả khi chưa cài gì.

Không khởi động server thật — đây là bước kiểm trước `python main.py`.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

# Console Windows mặc định cp1252 không in được emoji/tiếng Việt → ép UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).resolve().parent
OK, WARN, BAD = "[ OK ]", "[ -- ]", "[ XX ]"
_blockers: list[str] = []
_notes: list[str] = []


def _p(tag: str, msg: str) -> None:
    print(f"{tag} {msg}")


def _has(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
def check_python() -> None:
    v = sys.version_info
    if (v.major, v.minor) >= (3, 10):
        _p(OK, f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        _p(BAD, f"Python {v.major}.{v.minor} — cần >= 3.10")
        _blockers.append("Nâng Python lên >= 3.10")


def check_deps() -> None:
    print("\n— Thư viện BẮT BUỘC —")
    required = [
        ("requests", "pip install requests"),
        ("bs4", "pip install beautifulsoup4"),
        ("pydantic", "pip install pydantic"),
        ("pydantic_settings", "pip install pydantic-settings"),
        ("chromadb", "pip install chromadb"),
        ("websockets", "pip install websockets"),
        ("PyQt5", "pip install PyQt5"),        # Mascot Miku (ui.mascot) — mặt autostart duy nhất
        ("psutil", "pip install psutil"),     # cảm biến nhường đường RAM (core/daemon.py)
    ]
    for mod, fix in required:
        if _has(mod):
            _p(OK, mod)
        else:
            _p(BAD, f"{mod} — THIẾU → {fix}")
            _blockers.append(fix)

    print("\n— Thư viện TUỲ CHỌN (skill nâng cao) —")
    optional = [
        ("playwright", "pip install playwright && python -m playwright install chromium", "web.agent render JS"),
        ("playwright_stealth", "pip install playwright-stealth", "vượt Cloudflare"),
        ("send2trash", "pip install send2trash", "system.control xoá an toàn (Thùng rác)"),
        ("pyautogui", "pip install pyautogui", "rpa.browser lướt web vật lý"),
        ("pypdf", "pip install pypdf", "knowledge.ingest đọc PDF"),
        ("easyocr", "pip install easyocr", "manga.translate OCR"),
        ("deep_translator", "pip install deep-translator", "manga.translate dịch"),
    ]
    for mod, fix, why in optional:
        if _has(mod):
            _p(OK, f"{mod}")
        else:
            _p(WARN, f"{mod} — thiếu ({why}) → {fix}")
            _notes.append(f"(tuỳ chọn) {fix} — {why}")


def _parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def check_env() -> dict[str, str]:
    print("\n— Cấu hình .env —")
    env_path = ROOT / ".env"
    if not env_path.is_file():
        _p(WARN, ".env CHƯA có → copy .env.example thành .env rồi điền giá trị")
        _notes.append("copy .env.example .env  (rồi điền OLLAMA_MODEL, ANTHROPIC_API_KEY nếu dùng Cloud)")
        return {}
    env = _parse_env(env_path)
    model = env.get("OLLAMA_MODEL", "(mặc định gemma4:e4b)")
    _p(OK, f".env có sẵn — OLLAMA_MODEL={model}")
    if env.get("ANTHROPIC_API_KEY"):
        _p(OK, "ANTHROPIC_API_KEY đã đặt (Cloud escalation khả dụng)")
    else:
        _p(WARN, "ANTHROPIC_API_KEY trống — AURA chạy thuần local (không mượn được 'thầy')")
    return env


def check_ollama(env: dict[str, str]) -> None:
    print("\n— Bộ não local (Ollama) —")
    host = (env.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    want = env.get("OLLAMA_MODEL") or "gemma4:e4b"
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [m.get("model", "") for m in data.get("models", [])]
        _p(OK, f"Ollama đang chạy tại {host}")
        if any(want.split(":")[0] in m for m in models):
            _p(OK, f"Model '{want}' đã sẵn sàng")
        else:
            _p(BAD, f"Model '{want}' CHƯA pull → ollama pull {want}")
            _blockers.append(f"ollama pull {want}")
            if models:
                _p(WARN, f"   (đang có: {', '.join(models[:5])})")
    except Exception as exc:  # noqa: BLE001
        _p(BAD, f"Không kết nối Ollama tại {host} ({exc}) → cài & chạy 'ollama serve'")
        _blockers.append("Cài Ollama (ollama.com) và chạy nền; rồi `ollama pull <model>`")


def check_skills_and_core() -> None:
    print("\n— Registry & lõi —")
    if not _has("pydantic"):
        _p(WARN, "Bỏ qua (cần cài thư viện bắt buộc trước rồi chạy lại doctor)")
        return
    sys.path.insert(0, str(ROOT))
    try:
        from tools.registry import build_default_registry
        skills = dict(build_default_registry().catalog())
        _p(OK, f"Khám phá {len(skills)} skills: {', '.join(sorted(skills))}")
    except Exception as exc:  # noqa: BLE001
        _p(BAD, f"Registry lỗi: {exc}")
        _blockers.append(f"Sửa registry: {exc}")
    core_mods = ["core.orchestrator", "core.vibe_diff", "core.reflection",
                 "core.self_improve", "core.metrics", "core.deliberate",
                 "core.llm", "core.daemon", "core.brain_router"]
    failed = []
    for m in core_mods:
        try:
            importlib.import_module(m)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{m} ({exc})")
    if not failed:
        _p(OK, f"Import sạch {len(core_mods)} module lõi")
    else:
        for f in failed:
            _p(BAD, f"Import lỗi: {f}")
        _blockers.append("Sửa import module lõi (xem trên)")


def main() -> int:
    print("=" * 60)
    print("   🏠 AURA — TRÌNH TỰ ĐÁNH THỨC HỆ ĐIỀU HÀNH")
    print("=" * 60)
    check_python()
    check_deps()
    env = check_env()
    check_ollama(env)
    check_skills_and_core()

    print("\n" + "=" * 60)
    if not _blockers:
        print("✅ SẴN SÀNG. Đánh thức AURA:")
        print("     python main.py            (server + daemon + skills)")
        print("     python -m ui.mascot       (Mascot Miku — cửa sổ 2, chat + hoạt hình)")
        print("     python aura_autostart.py --install   (cho AURA thường trú)")
        if _notes:
            print("\n   Gợi ý nâng cấp (không bắt buộc):")
            for n in _notes:
                print(f"     • {n}")
        print("=" * 60)
        return 0
    print("⛔ CHƯA THỨC ĐƯỢC — cần xử lý:")
    for b in _blockers:
        print(f"     • {b}")
    if _notes:
        print("\n   Tuỳ chọn thêm:")
        for n in _notes:
            print(f"     • {n}")
    print("=" * 60)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
