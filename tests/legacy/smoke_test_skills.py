"""
smoke_test_skills.py
====================
Smoke-test cho kiến trúc Agent Skills (Progressive Disclosure) của AURA OS v2.

Chạy trên máy thật (có pydantic/bs4/...):
    python smoke_test_skills.py            # cấu trúc + lazy-load (offline)
    python smoke_test_skills.py --live     # thêm 1 lần cào web thật (cần mạng)

LƯU Ý thứ tự: nhóm "ranh giới lazy-load" PHẢI chạy TRƯỚC các test gọi manga.* khác,
vì execute_tool() nạp module skill (kể cả khi tham số sai). Nên nhóm lazy-load đứng
ngay sau discovery, lúc chưa skill nào được nạp.
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.schemas import Task, ToolResult
from tools.registry import build_default_registry, get_default_registry

_fails = 0


def check(label: str, ok: bool) -> None:
    global _fails
    if not ok:
        _fails += 1
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")


def _skill_mods() -> list[str]:
    return [m for m in sys.modules if m.startswith("aura_skill_")]


def main(live: bool = False) -> int:
    reg = build_default_registry()
    # Các skill LÕI bắt buộc phải khám phá được; registry còn nạp thêm nhiều skill
    # khác nên kiểm "tập con" thay vì "bằng đúng" để test không vỡ khi thêm skill mới.
    expected = {"web.scrape", "manga.download", "manga.translate", "tech.scout"}

    print("===== A. DISCOVERY / LEVEL 1 =====")
    print(reg.system_prompt_block())
    discovered = set(dict(reg.catalog()))
    check(f"discovered core skills ({len(discovered)} total)", expected <= discovered)
    check("Level-1 block: names/desc only (no code paths)",
          "scripts/" not in reg.system_prompt_block())
    check("no skill code imported during discovery", not _skill_mods())

    print("\n===== B. LAZY-LOAD BOUNDARY (clean state) =====")
    check("nothing loaded before any execute", not _skill_mods())
    reg.execute_tool("manga.translate", {"title": "T", "chapter": 1})  # no source_url
    check("translate ran WITHOUT importing easyocr", "easyocr" not in sys.modules)
    check("translate script loaded", any("manga_translate" in m for m in sys.modules))
    check("manga.download NOT loaded yet (no cross-call)",
          not any("manga_download" in m for m in sys.modules))

    print("\n===== C. CROSS-SKILL LAZY LINKAGE (call_skill) =====")
    reg.execute_tool("manga.translate",
                     {"title": "T", "chapter": 1, "source_url": "https://example.com/c1"})
    check("manga.download loaded ONLY after cross-skill call",
          any("manga_download" in m for m in sys.modules))
    check("call_skill shares the default registry", get_default_registry() is reg)

    print("\n===== D. SAFETY BELTS =====")
    check("web.scrape bad url -> failure",
          not reg.execute_tool("web.scrape", {"url": "not-a-url"}).ok)
    check("manga.download missing source_url -> failure",
          not reg.execute_tool("manga.download", {"title": "X", "chapter": 1}).ok)
    check("unknown skill -> failure", not reg.execute_tool("nope.nope").ok)
    r = reg.execute_tool("web.scrape", {})
    check("missing required arg -> TypeError wrapped",
          (not r.ok) and "Tham" in (r.error or ""))

    print("\n===== E. ORCHESTRATOR PATH (dispatch via Task) =====")
    check("dispatch(Task) returns ToolResult",
          isinstance(reg.dispatch(Task(tool_name="web.scrape",
                                       arguments={"url": "not-a-url"})), ToolResult))

    print("\n===== F. EVOLUTION COMPAT (register runtime tool) =====")
    reg.register("demo.echo",
                 lambda **k: ToolResult.success("demo.echo", output=repr(k)), "demo")
    check("register() + run runtime tool",
          reg.execute_tool("demo.echo", {"x": 9}).output == "{'x': 9}")

    print("\n===== G. LEVEL 3 (instructions on demand) =====")
    check("get_instructions returns SKILL.md body",
          reg.get_instructions("web.scrape").startswith("# Web Scrape"))

    if live:
        print("\n===== H. LIVE web.scrape (can mang) =====")
        res = reg.execute_tool("web.scrape", {"url": "https://example.com", "max_chars": 400})
        check("live scrape ok", res.ok)
        if res.ok:
            import json
            d = json.loads(res.output)
            print(f"      title={d['title']!r} chars={d['char_count']} imgs={d['image_count']}")

    print("\n" + ("[OK] TAT CA PASS" if _fails == 0 else f"[X] {_fails} KIEM TRA FAIL"))
    return 1 if _fails else 0


if __name__ == "__main__":
    raise SystemExit(main(live="--live" in sys.argv))
