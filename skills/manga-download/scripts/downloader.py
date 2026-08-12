"""
skills/manga-download/scripts/downloader.py
===========================================
MangaDownloader — "Đôi chân" tải ảnh truyện về máy (LỚP LOGIC, Level 4).

Ngữ cảnh "khi nào dùng / hướng dẫn" ở ../SKILL.md; file này chỉ chứa code thực thi,
được registry nạp TRỄ (lazy) qua importlib đúng lúc gọi.

  - Xoay User-Agent, hỗ trợ proxy (settings.manga_proxy), timeout + retry backoff.
  - Trích URL ảnh từ HTML (kể cả lazy-load qua data-src/data-original).
  - Tải về downloads/<title>/<chapter_label>/ và tự đánh số 01,02,...

Tool công khai `tool_download_manga(title, chapter, source_url)` LUÔN trả ToolResult.
Hợp đồng tool: fn(**parameters) -> ToolResult.

Chạy độc lập để kiểm thử:
    python skills/manga-download/scripts/downloader.py --title T --chapter 1 --source-url URL
"""

from __future__ import annotations

import sys
from pathlib import Path

# Cho phép `from core...` hoạt động dù file được nạp qua importlib HAY chạy độc lập.
# skills/manga-download/scripts/downloader.py -> parents[3] = gốc dự án.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json
import logging
import os
import time
from urllib.parse import urljoin, urlparse

import requests

from core.config import settings
from core.schemas import MangaTarget, ToolResult

logger = logging.getLogger("aura.skills.manga_download")

# Vài User-Agent thật để xoay vòng, giảm khả năng bị chặn.
_USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
)

# Phần mở rộng ảnh hợp lệ + map từ content-type.
_VALID_EXT: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})
_CT_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
# Từ khoá trong URL gợi ý ảnh KHÔNG phải trang truyện (logo, banner...).
_SKIP_HINTS: tuple[str, ...] = ("logo", "banner", "avatar", "icon", "ads", "sprite")


def _guess_extension(url: str, content_type: str | None) -> str:
    """Đoán đuôi file ảnh: ưu tiên theo URL, rồi tới content-type, mặc định .jpg."""
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    if ext in _VALID_EXT:
        return ".jpg" if ext == ".jpeg" else ext
    ct = (content_type or "").split(";")[0].strip().lower()
    return _CT_TO_EXT.get(ct, ".jpg")


class MangaDownloader:
    """Tải một chapter từ một URL trang đọc truyện (HTML có thẻ <img>)."""

    def __init__(
        self,
        output_root: Path | None = None,
        proxy: str | None = None,
        timeout_s: float = 20.0,
        max_retries: int = 4,
    ) -> None:
        self.output_root = output_root or settings.downloads_dir
        self.proxy = proxy if proxy is not None else settings.manga_proxy
        self.timeout_s = timeout_s
        self.max_retries = max(1, max_retries)
        self._ua_index = 0

    # ------------------------------------------------------------------ #
    def _next_user_agent(self) -> str:
        ua = _USER_AGENTS[self._ua_index % len(_USER_AGENTS)]
        self._ua_index += 1
        return ua

    def _request(
        self, url: str, *, stream: bool = False, referer: str | None = None
    ) -> requests.Response:
        """GET có xoay UA, proxy, timeout và retry backoff. Ném RequestException nếu hết lượt."""
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None
        last_exc: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            headers = {"User-Agent": self._next_user_agent()}
            if referer:
                headers["Referer"] = referer
            try:
                resp = requests.get(
                    url, headers=headers, proxies=proxies,
                    timeout=self.timeout_s, stream=stream,
                )
                resp.raise_for_status()
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
    def _extract_image_urls(self, page_url: str, html: str) -> list[str]:
        """Bóc URL ảnh trang truyện từ HTML (gồm cả lazy-load), lọc ảnh rác."""
        try:
            from bs4 import BeautifulSoup
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Thiếu 'beautifulsoup4'. Cài: pip install beautifulsoup4"
            ) from exc

        soup = BeautifulSoup(html, "html.parser")
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
            if any(hint in low for hint in _SKIP_HINTS):
                continue
            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append(absolute)

        return urls

    # ------------------------------------------------------------------ #
    def download_chapter(self, source_url: str, output_folder: Path) -> dict:
        """
        Tải toàn bộ ảnh của một chapter.

        Returns:
            Dict JSON-ready: source_url, output_folder, image_count, saved_files.

        Raises:
            requests.RequestException, ModuleNotFoundError — caller gói vào ToolResult.
        """
        output_folder.mkdir(parents=True, exist_ok=True)

        page = self._request(source_url)
        image_urls = self._extract_image_urls(source_url, page.text)

        saved_files: list[str] = []
        for idx, img_url in enumerate(image_urls, start=1):
            try:
                resp = self._request(img_url, stream=True, referer=source_url)
            except requests.RequestException as exc:
                logger.warning("Bỏ qua ảnh %d (tải lỗi): %s", idx, exc)
                continue

            ext = _guess_extension(img_url, resp.headers.get("Content-Type"))
            dest = output_folder / f"{idx:02d}{ext}"
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            saved_files.append(str(dest))

        return {
            "source_url": source_url,
            "output_folder": str(output_folder),
            "image_count": len(saved_files),
            "saved_files": saved_files,
        }


# ---------------------------------------------------------------------------
# Tool công khai cho Registry  (entrypoint khai báo trong SKILL.md)
# ---------------------------------------------------------------------------
def tool_download_manga(
    title: str, chapter: float, source_url: str | None = None
) -> ToolResult:
    """
    Tool 'manga.download': tải 1 chapter, trả ToolResult (không ném exception).

    Args:
        title: tên truyện (đặt tên thư mục).
        chapter: số chương (float — hỗ trợ 10.5).
        source_url: URL trang chapter. BẮT BUỘC để cào được (chưa có resolver tên→URL).
    """
    if not source_url:
        return ToolResult.failure(
            "manga.download",
            "Thiếu source_url. Phiên này chưa có bộ tra tên→link; "
            "sếp cung cấp link trang chapter giúp em.",
        )

    try:
        target = MangaTarget(title=title, chapter=chapter)
    except ValueError as exc:
        return ToolResult.failure("manga.download", f"Tham số truyện không hợp lệ: {exc}")

    folder = settings.downloads_dir / target.title / target.chapter_label

    try:
        downloader = MangaDownloader()
        info = downloader.download_chapter(source_url, folder)
    except ModuleNotFoundError as exc:
        return ToolResult.failure("manga.download", str(exc))
    except requests.RequestException as exc:
        return ToolResult.failure("manga.download", f"Lỗi mạng khi tải: {exc}")
    except Exception as exc:  # noqa: BLE001 — vành đai cuối, không để lọt exception
        return ToolResult.failure("manga.download", f"Lỗi không xác định: {exc}")

    if info["image_count"] == 0:
        return ToolResult.failure(
            "manga.download",
            f"Không tìm thấy ảnh nào tại {source_url}. Có thể trang dùng JS render — "
            "cần web_agent (browser-use) ở phase sau.",
        )

    return ToolResult.success(
        tool_name="manga.download",
        output=json.dumps(
            {
                "title": target.title,
                "chapter": target.chapter,
                "chapter_label": target.chapter_label,
                **info,
            },
            ensure_ascii=False,
        ),
        artifacts=info["saved_files"],
    )


# ---------------------------------------------------------------------------
# CLI độc lập (Level 4)
# ---------------------------------------------------------------------------
def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="AURA skill manga.download — tải 1 chapter.")
    ap.add_argument("--title", required=True)
    ap.add_argument("--chapter", required=True, type=float)
    ap.add_argument("--source-url", required=True)
    args = ap.parse_args(argv)

    result = tool_download_manga(
        title=args.title, chapter=args.chapter, source_url=args.source_url
    )
    print(result.model_dump_json(indent=2))
    return 0 if result.ok else 1


__all__ = ["MangaDownloader", "tool_download_manga", "_guess_extension"]


if __name__ == "__main__":
    raise SystemExit(_main())
