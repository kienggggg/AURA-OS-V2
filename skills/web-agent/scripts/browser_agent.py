"""
skills/web-agent/scripts/browser_agent.py
=========================================
Web Agent — trình duyệt thật headless để render JS + vượt JS-challenge (LỚP LOGIC, Level 4).

Dùng Playwright (Chromium headless, sync API — an toàn khi gọi từ worker thread của
Orchestrator). Mở context EPHEMERAL ẩn danh, chạy trọn JavaScript, CHỜ THÔNG MINH đến
khi nội dung chính render xong rồi mới lấy HTML/text.

Tuân thủ CONTEXT.md:
  - §2 bọc try/except, luôn trả ToolResult; §6 read-only + timeout; §7 validate URL;
  - §1 không secret. Playwright import TRỄ -> thiếu thì báo lệnh cài, KHÔNG sập app.

Tool công khai `tool_web_agent(...)` luôn trả ToolResult (không ném exception).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Cho phép `from core...` dù nạp qua importlib hay chạy độc lập.
# skills/web-agent/scripts/browser_agent.py -> parents[3] = gốc dự án.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json
import logging
import random
import re
import time
from urllib.parse import urlparse

from core.schemas import ToolResult

logger = logging.getLogger("aura.skills.web_agent")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_ACCEPT_LANG = "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"
_NOISE_TAGS = ("script", "style", "noscript", "template", "svg", "nav", "header", "footer")
_DEFAULT_MAX_CHARS = 20_000
_VALID_WAIT_UNTIL = ("networkidle", "load", "domcontentloaded", "commit")


def _human_pause(lo_ms: int = 400, hi_ms: int = 1200) -> None:
    """Nghỉ ngẫu nhiên nhẹ để mô phỏng người dùng thao tác chậm (chống fingerprint hành vi)."""
    time.sleep(random.uniform(lo_ms, hi_ms) / 1000.0)


def _load_stealth():
    """
    Nạp playwright-stealth (lớp tàng hình chống phát hiện headless).
    Ưu tiên API cổ điển `stealth_sync` (theo yêu cầu); fallback API mới `Stealth`.
    Thiếu thư viện -> ném ModuleNotFoundError yêu cầu cài (caller -> ToolResult.failure).
    """
    try:
        from playwright_stealth import stealth_sync  # API 1.x
        return stealth_sync
    except ImportError:
        pass
    try:
        from playwright_stealth import Stealth  # API 2.x
        _engine = Stealth()
        return lambda page: _engine.apply_stealth_sync(page)
    except ImportError as exc:
        raise ModuleNotFoundError(
            "Thiếu 'playwright-stealth'. Cài: pip install playwright-stealth"
        ) from exc


def render_page(
    url: str,
    wait_selector: str | None = None,
    wait_until: str = "domcontentloaded",
    timeout_s: float = 30.0,
    extra_wait_ms: int = 600,
    headless: bool = False,
    human_like: bool = True,
) -> dict:
    """
    Mở Chromium headless ẩn danh, render JS, chờ thông minh, trả {url, final_url, title, html}.

    Ném ModuleNotFoundError nếu thiếu Playwright; RuntimeError nếu lỗi điều hướng —
    caller (tool_web_agent) gói vào ToolResult.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Thiếu 'playwright'. Cài: pip install playwright && python -m playwright install chromium"
        ) from exc

    stealth = _load_stealth()  # thiếu playwright-stealth -> ModuleNotFoundError (caller xử lý)

    if wait_until not in _VALID_WAIT_UNTIL:
        wait_until = "domcontentloaded"
    timeout_ms = int(max(1.0, timeout_s) * 1000)

    html, title, final_url = "", "", url
    with sync_playwright() as p:
        # HEADED (headless=False) để có GPU/Canvas thật -> vượt Cloudflare Turnstile.
        # Trên server không màn hình, cần Xvfb (xvfb-run) để có display ảo.
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
            # Tương đương excludeSwitches=enable-automation (gỡ cờ tự-động-hoá Playwright thêm mặc định).
            ignore_default_args=["--enable-automation"],
        )
        try:
            context = browser.new_context(  # context EPHEMERAL: không profile lưu
                user_agent=_UA,
                locale="vi-VN",
                viewport={"width": 1366, "height": 768},
                extra_http_headers={"Accept-Language": _ACCEPT_LANG},
            )
            page = context.new_page()
            page.set_default_timeout(timeout_ms)
            try:
                stealth(page)  # TIÊM TÀNG HÌNH trước khi điều hướng
            except Exception as exc:  # noqa: BLE001 — stealth lỗi runtime không được làm sập render
                logger.warning("Áp stealth lỗi (tiếp tục không tàng hình): %s", exc)

            if human_like:  # nghỉ ngẫu nhiên nhẹ như người thật trước khi tải trang
                _human_pause()

            # wait_until="domcontentloaded": KHÔNG chờ networkidle (trang có tracking
            # nền chạy mãi -> networkidle không bao giờ đạt -> timeout rác). Phần CHỜ
            # THÔNG MINH bên dưới (selector / innerText>200) mới đảm bảo nội dung đã render.
            page.goto(url, wait_until=wait_until, timeout=timeout_ms)

            # --- CHỜ THÔNG MINH ---
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, state="visible", timeout=timeout_ms)
                except Exception as exc:  # noqa: BLE001 — selector không hiện -> vẫn lấy nội dung hiện có
                    logger.warning("wait_selector %r không xuất hiện: %s", wait_selector, exc)
            else:
                try:  # chờ body có nội dung thực (JS đã render)
                    page.wait_for_function(
                        "document.body && document.body.innerText.trim().length > 200",
                        timeout=timeout_ms,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Body chưa đủ nội dung trong hạn chờ: %s", exc)

            if extra_wait_ms > 0:
                page.wait_for_timeout(extra_wait_ms)

            html = page.content()
            title = page.title()
            final_url = page.url
        finally:
            browser.close()  # đóng trình duyệt dù lỗi hay không (ephemeral)

    return {"url": url, "final_url": final_url, "title": title, "html": html}


def _html_to_text(html: str, max_chars: int) -> str:
    """Bóc text sạch từ HTML đã render (bs4 nếu có; fallback regex thô)."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(list(_NOISE_TAGS)):
            tag.decompose()
        raw = soup.get_text(separator="\n")
    except ModuleNotFoundError:
        raw = re.sub(r"<[^>]+>", " ", html)  # fallback: gỡ thẻ thô
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(s.strip() for s in raw.splitlines() if s.strip()))
    return text[:max_chars]


# ---------------------------------------------------------------------------
# Tool công khai cho Registry
# ---------------------------------------------------------------------------
def tool_web_agent(
    url: str,
    wait_selector: str = "",
    wait_until: str = "domcontentloaded",
    timeout_s: float = 30.0,
    max_chars: int = _DEFAULT_MAX_CHARS,
    headless: bool = False,
) -> ToolResult:
    """
    Tool 'web.agent': render trang bằng trình duyệt thật headless. Luôn trả ToolResult.

    Args:
        url: URL http/https cần render (bắt buộc).
        wait_selector: CSS selector nội dung chính để chờ (tuỳ chọn).
        wait_until: 'domcontentloaded' (mặc định, tránh treo vì tracking nền) /
                    'load' / 'networkidle'.
        timeout_s: hạn chờ tổng.
        max_chars: cắt độ dài text trả về.
    """
    if not url or not isinstance(url, str):
        return ToolResult.failure("web.agent", "Thiếu 'url' hoặc url không hợp lệ.")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ToolResult.failure(
            "web.agent", f"URL phải http/https và có domain hợp lệ: {url!r}"
        )

    try:
        info = render_page(
            url.strip(), wait_selector=wait_selector or None,
            wait_until=wait_until, timeout_s=timeout_s, headless=headless,
        )
    except ModuleNotFoundError as exc:
        return ToolResult.failure("web.agent", str(exc))
    except Exception as exc:  # noqa: BLE001 — vành đai cuối, không để lọt exception
        return ToolResult.failure("web.agent", f"Lỗi render trình duyệt: {exc}")

    text = _html_to_text(info["html"], max_chars)
    if not text:
        return ToolResult.failure(
            "web.agent", f"Render xong nhưng không bóc được text từ {info['final_url']}."
        )

    return ToolResult.success(
        "web.agent",
        output=json.dumps(
            {
                "url": info["url"],
                "final_url": info["final_url"],
                "title": info["title"],
                "text": text,
                "html_len": len(info["html"]),
            },
            ensure_ascii=False,
        ),
    )


# ---------------------------------------------------------------------------
# CLI độc lập (Level 4)
# ---------------------------------------------------------------------------
def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="AURA skill web.agent — render JS bằng trình duyệt thật.")
    ap.add_argument("--url", required=True)
    ap.add_argument("--wait-selector", default="")
    ap.add_argument("--wait-until", default="domcontentloaded")
    ap.add_argument("--timeout-s", type=float, default=30.0)
    ap.add_argument("--headless", action="store_true", help="Ép headless (mặc định HEADED để vượt Turnstile).")
    args = ap.parse_args(argv)

    result = tool_web_agent(
        url=args.url, wait_selector=args.wait_selector,
        wait_until=args.wait_until, timeout_s=args.timeout_s,
        headless=args.headless,
    )
    print(result.output if result.ok else f"[LỖI] {result.error}")
    return 0 if result.ok else 1


__all__ = ["tool_web_agent", "render_page"]


if __name__ == "__main__":
    raise SystemExit(_main())
