"""
skills/web-scrape/scripts/scraper.py
====================================
WebScraper — "Đôi mắt đọc web" của AURA: cào nội dung TEXT + ẢNH cơ bản từ 1 URL.

Đây là LỚP LOGIC (Level 4 — Procedural) của skill `web.scrape`. Ngữ cảnh "khi nào
dùng / hướng dẫn" nằm ở ../SKILL.md; file này chỉ chứa code thực thi, được registry
nạp TRỄ (lazy) đúng lúc gọi — nên import nặng không làm phình System Prompt.

  - Xoay User-Agent, hỗ trợ proxy (settings.manga_proxy), timeout + retry backoff.
  - requests + BeautifulSoup (bs4 import TRỄ kèm hướng dẫn cài).
  - Bóc tiêu đề, text sạch (bỏ script/style/nav/footer), danh sách URL ảnh tuyệt đối.

Tool công khai `tool_web_scrape(url, ...)` LUÔN trả ToolResult (không ném exception).
Hợp đồng tool: fn(**parameters) -> ToolResult.

Có thể chạy độc lập để kiểm thử:
    python skills/web-scrape/scripts/scraper.py --url "https://example.com"
"""

from __future__ import annotations

import sys
from pathlib import Path

# Cho phép `from core...` hoạt động dù file được nạp qua importlib HAY chạy độc lập.
# skills/web-scrape/scripts/scraper.py  ->  parents[3] = gốc dự án.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import hashlib
import json
import logging
import re
import time
from urllib.parse import urljoin, urlparse

import requests

from core.config import settings
from core.schemas import ToolResult

logger = logging.getLogger("aura.skills.web_scrape")

# Vài User-Agent thật để xoay vòng, giảm khả năng bị chặn.
_USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
)

# Thẻ không mang nội dung đọc — gỡ bỏ trước khi lấy text.
_NOISE_TAGS: tuple[str, ...] = (
    "script", "style", "noscript", "template", "svg",
    "nav", "header", "footer", "aside", "form",
)
# Từ khoá trong URL gợi ý ảnh rác (logo, banner...).
_SKIP_HINTS: tuple[str, ...] = ("logo", "banner", "avatar", "icon", "ads", "sprite")
# Giới hạn an toàn để không nuốt cả trang khổng lồ vào context LLM.
_DEFAULT_MAX_CHARS: int = 20_000

# Mặt nạ trình duyệt người thật để vượt anti-bot 403 cơ bản (full headers).
def _browser_headers(user_agent: str | None = None) -> dict[str, str]:
    return {
        "User-Agent": user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate",  # KHÔNG br: tránh raw bytes/mojibake khi thiếu brotli
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }


class WebScraper:
    """Cào TEXT + URL ảnh từ một trang HTML tĩnh (không chạy JS)."""

    def __init__(
        self,
        proxy: str | None = None,
        timeout_s: float = 20.0,
        max_retries: int = 4,
    ) -> None:
        self.proxy = proxy if proxy is not None else settings.manga_proxy
        self.timeout_s = timeout_s
        self.max_retries = max(1, max_retries)
        self._ua_index = 0

    # ------------------------------------------------------------------ #
    def _next_user_agent(self) -> str:
        ua = _USER_AGENTS[self._ua_index % len(_USER_AGENTS)]
        self._ua_index += 1
        return ua

    def _request(self, url: str) -> requests.Response:
        """GET có xoay UA, proxy, timeout và retry backoff. Ném RequestException nếu hết lượt."""
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            headers = _browser_headers(self._next_user_agent())
            try:
                resp = requests.get(
                    url, headers=headers, proxies=proxies, timeout=self.timeout_s
                )
                resp.raise_for_status()
                # Chống mojibake: server không khai charset -> requests đoán ISO-8859-1.
                if "charset" not in resp.headers.get("Content-Type", "").lower():
                    resp.encoding = resp.apparent_encoding
                return resp
            except requests.RequestException as exc:
                last_exc = exc
                wait = min(2 ** attempt, 10)  # backoff 2,4,8,10...
                logger.warning(
                    "Request lỗi (%d/%d) %s — chờ %ds: %s",
                    attempt, self.max_retries, url, wait, exc,
                )
                time.sleep(wait if attempt < self.max_retries else 0)

        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------ #
    def scrape(
        self,
        url: str,
        *,
        max_chars: int = _DEFAULT_MAX_CHARS,
        include_images: bool = True,
    ) -> dict:
        """
        Cào một trang.

        Returns:
            Dict JSON-ready: url, final_url, title, text, char_count, truncated,
            images (list URL tuyệt đối), image_count.

        Raises:
            requests.RequestException, ModuleNotFoundError — caller gói vào ToolResult.
        """
        try:
            from bs4 import BeautifulSoup
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Thiếu 'beautifulsoup4'. Cài: pip install beautifulsoup4"
            ) from exc

        resp = self._request(url)
        final_url = str(resp.url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Gỡ thẻ nhiễu để text sạch.
        for tag in soup(list(_NOISE_TAGS)):
            tag.decompose()

        title = (soup.title.string or "").strip() if soup.title else ""

        # Lấy text, gom khoảng trắng, cắt theo max_chars.
        raw_text = soup.get_text(separator="\n")
        lines = (line.strip() for line in raw_text.splitlines())
        text = "\n".join(line for line in lines if line)
        text = re.sub(r"\n{3,}", "\n\n", text)
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars].rstrip() + "\n…[đã cắt bớt]"

        images: list[str] = []
        if include_images:
            images = self._extract_image_urls(final_url, soup)

        return {
            "url": url,
            "final_url": final_url,
            "title": title,
            "text": text,
            "char_count": len(text),
            "truncated": truncated,
            "images": images,
            "image_count": len(images),
        }

    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_image_urls(page_url: str, soup) -> list[str]:
        """Bóc URL ảnh (gồm lazy-load), tuyệt đối hoá, bỏ ảnh rác và trùng lặp."""
        urls: list[str] = []
        seen: set[str] = set()
        for img in soup.find_all("img"):
            raw = (
                img.get("data-src")
                or img.get("data-original")
                or img.get("data-lazy-src")
                or img.get("src")
            )
            if not raw or raw.startswith("data:"):
                continue
            absolute = urljoin(page_url, raw.strip())
            low = absolute.lower()
            if not low.startswith(("http://", "https://")):
                continue
            if any(hint in low for hint in _SKIP_HINTS):
                continue
            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append(absolute)
        return urls


# ---------------------------------------------------------------------------
# Tool công khai cho Registry  (entrypoint khai báo trong SKILL.md)
# ---------------------------------------------------------------------------
def tool_web_scrape(
    url: str,
    max_chars: int = _DEFAULT_MAX_CHARS,
    include_images: bool = True,
    save: bool = False,
) -> ToolResult:
    """
    Tool 'web.scrape': cào text + ảnh cơ bản từ một URL. Luôn trả ToolResult.

    Args:
        url: URL trang cần cào (bắt buộc, http/https).
        max_chars: giới hạn độ dài text trả về (mặc định 20k ký tự).
        include_images: có bóc danh sách URL ảnh không (mặc định True).
        save: nếu True, ghi text ra settings.outputs_dir và đính vào artifacts.
    """
    if not url or not isinstance(url, str):
        return ToolResult.failure("web.scrape", "Thiếu 'url' hoặc url không hợp lệ.")

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ToolResult.failure(
            "web.scrape", f"URL phải bắt đầu bằng http/https và có domain hợp lệ: {url!r}"
        )

    try:
        scraper = WebScraper()
        info = scraper.scrape(
            url.strip(), max_chars=max_chars, include_images=include_images
        )
    except ModuleNotFoundError as exc:
        return ToolResult.failure("web.scrape", str(exc))
    except requests.RequestException as exc:
        return ToolResult.failure("web.scrape", f"Lỗi mạng khi cào: {exc}")
    except Exception as exc:  # noqa: BLE001 — vành đai cuối, không để lọt exception
        return ToolResult.failure("web.scrape", f"Lỗi không xác định: {exc}")

    if not info["text"] and info["image_count"] == 0:
        return ToolResult.failure(
            "web.scrape",
            f"Không bóc được nội dung từ {info['final_url']}. Có thể trang render bằng "
            "JS — cần web_agent (browser) ở phase sau.",
        )

    artifacts: list[str] = []
    if save:
        try:
            settings.outputs_dir.mkdir(parents=True, exist_ok=True)
            slug = hashlib.sha1(info["final_url"].encode()).hexdigest()[:10]
            dest = Path(settings.outputs_dir) / f"scrape_{slug}.txt"
            dest.write_text(
                f"# {info['title']}\n# {info['final_url']}\n\n{info['text']}",
                encoding="utf-8",
            )
            artifacts.append(str(dest))
        except Exception as exc:  # noqa: BLE001 — ghi file là phụ, không nên làm fail cả tool
            logger.warning("Không ghi được file scrape: %s", exc)

    return ToolResult.success(
        tool_name="web.scrape",
        output=json.dumps(info, ensure_ascii=False),
        artifacts=artifacts,
    )


# ---------------------------------------------------------------------------
# CLI độc lập (Level 4): cho phép "gọi script" thay vì để LLM tự đoán logic.
# ---------------------------------------------------------------------------
def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="AURA skill web.scrape — cào text + ảnh.")
    ap.add_argument("--url", required=True, help="URL http/https cần cào.")
    ap.add_argument("--max-chars", type=int, default=_DEFAULT_MAX_CHARS)
    ap.add_argument("--no-images", action="store_true", help="Bỏ qua việc bóc ảnh.")
    ap.add_argument("--save", action="store_true", help="Ghi text ra data/outputs/.")
    args = ap.parse_args(argv)

    result = tool_web_scrape(
        url=args.url,
        max_chars=args.max_chars,
        include_images=not args.no_images,
        save=args.save,
    )
    print(result.model_dump_json(indent=2))
    return 0 if result.ok else 1


__all__ = ["WebScraper", "tool_web_scrape"]


if __name__ == "__main__":
    raise SystemExit(_main())
