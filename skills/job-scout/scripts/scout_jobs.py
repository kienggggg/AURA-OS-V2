"""
skills/job-scout/scripts/scout_jobs.py
======================================
Job Scout — "Đặc vụ săn việc" (LỚP LOGIC, Level 4).

Cào tin tuyển dụng (requests + BeautifulSoup, cùng họ web.scrape), chấm Match Score
theo từ khoá ưu tiên của Sếp, tóm tắt mô tả (tuỳ chọn LLM), rồi xếp hạng + báo cáo.

Tuân thủ CONTEXT.md:
  - §1 không hardcode secret; §2 bọc try/except, luôn trả ToolResult;
  - §5 không os.system/eval/subprocess...; §6 chỉ đọc (read-only), có timeout/retry;
  - §7 validate input (URL http/https). Vẫn đi qua cổng VIBE DIFF ở tầng Orchestrator.

Tool công khai `tool_scout_jobs(...)` luôn trả ToolResult (không ném exception).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Cho phép `from core...` dù nạp qua importlib hay chạy độc lập.
# skills/job-scout/scripts/scout_jobs.py -> parents[3] = gốc dự án.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json
import logging
import re
import time
from urllib.parse import urlparse

import requests

from core.schemas import ToolResult

logger = logging.getLogger("aura.skills.job_scout")

# Xoay User-Agent (giống web.scrape) giảm khả năng bị chặn.
_USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
)
_NOISE_TAGS = ("script", "style", "noscript", "template", "svg", "nav", "header", "footer")

# Bộ từ khoá ưu tiên + trọng số (CAO = quan trọng hơn).
#
# 12/08/2026: bản cũ ghi sẵn tỉnh đang ở và ngành Sếp theo, viết thường nên đợt
# soát đầu (phân biệt hoa thường) TRƯỢT mất chỗ này. Đặt lại bộ trung tính; sửa
# ở bản của mình cho đúng nghề mình cần.
_DEFAULT_KEYWORDS: dict[str, int] = {
    "python": 2,
    "automation": 2,
    "video editor": 2,
    "ai": 1,
}

# URL tuyển dụng mẫu (giáo dục / IT / freelance). Cần mạng; lỗi -> báo cáo nhẹ nhàng.
_SAMPLE_URLS: tuple[str, ...] = (
    "https://www.topcv.vn/tim-viec-lam-giao-vien-tai-thai-binh",
    "https://itviec.com/it-jobs/python",
    "https://www.vlance.vn/cong-viec/video-editor",
)


# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Tóm tắt (mặc định extractive; có thể cắm LLM thật qua set_summarizer)
# ---------------------------------------------------------------------------
def _default_summary(text: str, max_len: int = 180) -> str:
    """Tóm tắt trích đoạn đơn giản, offline (gom khoảng trắng + cắt độ dài)."""
    clean = " ".join((text or "").split())
    return clean[:max_len] + ("…" if len(clean) > max_len else "")


_SUMMARIZER = _default_summary


def set_summarizer(fn) -> None:
    """
    Cắm bộ tóm tắt khác (vd LLM đàn anh cloud như tech.scout) — fn(text)->str.
    Không bắt buộc; nếu fn lỗi, hệ tự fallback về extractive (xem _summarize).
    """
    global _SUMMARIZER
    _SUMMARIZER = fn


def _summarize(text: str) -> str:
    try:
        return _SUMMARIZER(text)
    except Exception as exc:  # noqa: BLE001 — tóm tắt lỗi không được làm hỏng báo cáo
        logger.warning("Summarizer lỗi, fallback extractive: %s", exc)
        return _default_summary(text)


# ---------------------------------------------------------------------------
# Fallback trình duyệt thật (web.agent) cho trang JS/Cloudflare
# ---------------------------------------------------------------------------
# Nội dung ngắn hơn ngưỡng này -> coi như trang JS chưa render -> cần web.agent.
_THIN_TEXT = 400


def _default_browser_fetch(url: str, wait_selector: str = "") -> dict | None:
    """Gọi web.agent (trình duyệt thật) qua registry — đúng chuẩn lazy-load chéo skill."""
    try:
        from tools.registry import call_skill
        res = call_skill("web.agent", {"url": url, "wait_selector": wait_selector})
        if not getattr(res, "ok", False):
            logger.warning("web.agent fallback lỗi %s: %s", url, getattr(res, "error", "?"))
            return None
        d = json.loads(res.output)
        return {"url": url, "final_url": d.get("final_url", url),
                "title": d.get("title", url), "text": d.get("text", "")}
    except Exception as exc:  # noqa: BLE001 — fallback lỗi không được làm sập job.scout
        logger.warning("Không gọi được web.agent cho %s: %s", url, exc)
        return None


_BROWSER_FETCH = _default_browser_fetch


def set_browser_fetcher(fn) -> None:
    """Cắm bộ render trình duyệt khác (test/định tuyến) — fn(url, wait_selector)->dict|None."""
    global _BROWSER_FETCH
    _BROWSER_FETCH = fn


# ---------------------------------------------------------------------------
# Chấm điểm
# ---------------------------------------------------------------------------
def _parse_keywords(keywords: str) -> dict[str, int]:
    """Parse 'kw:trọng_số, kw' -> dict. Rỗng -> bộ mặc định của Sếp."""
    if not keywords or not keywords.strip():
        return dict(_DEFAULT_KEYWORDS)
    out: dict[str, int] = {}
    for chunk in keywords.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            kw, _, w = chunk.partition(":")
            try:
                out[kw.strip().lower()] = max(1, int(w.strip()))
            except ValueError:
                out[kw.strip().lower()] = 1
        else:
            out[chunk.lower()] = 1
    return out or dict(_DEFAULT_KEYWORDS)


def _score_job(title: str, text: str, kw_weights: dict[str, int]) -> tuple[float, list[str]]:
    """Match Score 0..1 = tổng trọng số khớp / tổng trọng số. Trả (điểm, từ khoá khớp)."""
    hay = f"{title} {text}".lower()
    total = sum(kw_weights.values()) or 1
    matched = [kw for kw in kw_weights if kw in hay]
    got = sum(kw_weights[kw] for kw in matched)
    return round(got / total, 3), matched


def _level(score: float) -> str:
    if score >= 0.6:
        return "CAO"
    if score >= 0.3:
        return "TRUNG BÌNH"
    if score > 0:
        return "THẤP"
    return "KHÔNG KHỚP"


# ---------------------------------------------------------------------------
# Cào một trang tuyển dụng
# ---------------------------------------------------------------------------
def _fetch_job(url: str, timeout_s: float = 20.0, max_retries: int = 3) -> dict:
    """
    Cào 1 URL: trả {url, final_url, title, text}. Ném RequestException nếu hết lượt
    hoặc ModuleNotFoundError nếu thiếu bs4 (caller gói vào báo cáo).
    """
    try:
        from bs4 import BeautifulSoup
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("Thiếu 'beautifulsoup4'. Cài: pip install beautifulsoup4") from exc

    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        headers = _browser_headers(_USER_AGENTS[(attempt - 1) % len(_USER_AGENTS)])
        try:
            resp = requests.get(url, headers=headers, timeout=timeout_s)
            resp.raise_for_status()
            break
        except requests.exceptions.HTTPError as exc:
            # 4xx (vd 403 Cloudflare) sẽ không đổi khi thử lại -> ném NGAY để fallback browser.
            code = exc.response.status_code if exc.response is not None else None
            if code is not None and 400 <= code < 500:
                raise
            last_exc = exc
            time.sleep(min(2 ** attempt, 8) if attempt < max_retries else 0)
        except requests.RequestException as exc:
            last_exc = exc
            wait = min(2 ** attempt, 8)
            logger.warning("job.scout fetch lỗi (%d/%d) %s — chờ %ds: %s",
                           attempt, max_retries, url, wait, exc)
            time.sleep(wait if attempt < max_retries else 0)
    else:
        assert last_exc is not None
        raise last_exc

    # Chống mojibake: server không khai charset -> requests đoán ISO-8859-1.
    if "charset" not in resp.headers.get("Content-Type", "").lower():
        resp.encoding = resp.apparent_encoding
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(list(_NOISE_TAGS)):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title else url
    raw = soup.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(s.strip() for s in raw.splitlines() if s.strip()))
    return {"url": url, "final_url": str(resp.url), "title": title, "text": text[:8000]}


# ---------------------------------------------------------------------------
# Tool công khai cho Registry
# ---------------------------------------------------------------------------
def tool_scout_jobs(
    urls: list[str] | str | None = None,
    keywords: str = "",
    top_k: int = 5,
    jobs: list[dict] | None = None,
    as_json: bool = False,
    use_browser: bool = False,
    auto_browser: bool = True,
    wait_selector: str = "",
) -> ToolResult:
    """
    Tool 'job.scout': cào tin tuyển dụng + chấm Match Score + báo cáo. Luôn trả ToolResult.

    Args:
        urls: URL (hoặc list URL) trang tuyển dụng. Mặc định dùng URL mẫu.
        keywords: từ khoá chấm điểm 'kw:trọng_số, kw'. Mặc định bộ ưu tiên của Sếp.
        top_k: số cơ hội tốt nhất đưa vào báo cáo.
        jobs: dữ liệu việc có sẵn [{title, description, url}] -> bỏ qua bước cào.
        as_json: True -> JSON có cấu trúc; False -> báo cáo markdown.
    """
    kw_weights = _parse_keywords(keywords)
    scored: list[dict] = []
    errors: list[str] = []

    try:
        # --- Nguồn 1: dữ liệu việc có sẵn (offline / caller tự cào) ---
        if jobs:
            for j in jobs:
                if not isinstance(j, dict):
                    continue
                title = str(j.get("title", "(không tên)"))
                desc = str(j.get("description", ""))
                score, matched = _score_job(title, desc, kw_weights)
                scored.append({
                    "title": title, "url": j.get("url", ""),
                    "score": score, "level": _level(score),
                    "matched": matched, "summary": _summarize(desc),
                })
        else:
            # --- Nguồn 2: cào từ URL ---
            url_list = [urls] if isinstance(urls, str) else (list(urls) if urls else list(_SAMPLE_URLS))
            valid: list[str] = []
            for u in url_list:
                parsed = urlparse((u or "").strip())
                if parsed.scheme in ("http", "https") and parsed.netloc:
                    valid.append(u.strip())
                else:
                    errors.append(f"Bỏ URL không hợp lệ: {u!r}")
            for u in valid:
                info = None
                blocked = False  # bị tường lửa chặn (403/401/429/503) -> ép web.agent
                if not use_browser:  # thử requests tĩnh trước (nhẹ, nhanh)
                    try:
                        info = _fetch_job(u)
                    except ModuleNotFoundError as exc:
                        return ToolResult.failure("job.scout", str(exc))
                    except requests.exceptions.HTTPError as exc:
                        code = exc.response.status_code if exc.response is not None else None
                        if code in (401, 403, 429, 503):
                            blocked = True
                            logger.info("HTTP %s ở %s -> KÍCH HOẠT web.agent vượt tường lửa.", code, u)
                        else:
                            errors.append(f"HTTP {code} {u}")
                    except requests.RequestException as exc:
                        errors.append(f"Cào tĩnh lỗi {u}: {exc}")
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"Lỗi không xác định {u}: {exc}")
                # Mỏng/rỗng (trang JS) HOẶC bị chặn 4xx/5xx -> mở trình duyệt thật.
                thin = info is None or len((info or {}).get("text", "")) < _THIN_TEXT
                if (thin or blocked) and (use_browser or auto_browser):
                    binfo = _BROWSER_FETCH(u, wait_selector)
                    if binfo and binfo.get("text"):
                        info = binfo
                    elif info is None:
                        errors.append(f"web.agent không vượt được {u}")
                if info is None:
                    continue
                score, matched = _score_job(info["title"], info["text"], kw_weights)
                scored.append({
                    "title": info["title"], "url": info.get("final_url", u),
                    "score": score, "level": _level(score),
                    "matched": matched, "summary": _summarize(info["text"]),
                })
    except Exception as exc:  # noqa: BLE001 — vành đai cuối, không để lọt exception
        return ToolResult.failure("job.scout", f"Lỗi săn việc: {exc}")

    if not scored:
        reason = "Không thu được tin tuyển dụng nào."
        if errors:
            reason += " Chi tiết: " + " | ".join(errors[:5])
        return ToolResult.failure("job.scout", reason)

    scored.sort(key=lambda r: r["score"], reverse=True)
    top = scored[: max(1, top_k)]

    data = {
        "keywords": kw_weights,
        "total_found": len(scored),
        "top": top,
        "errors": errors,
    }
    output = json.dumps(data, ensure_ascii=False, indent=2) if as_json else _render(data)
    return ToolResult.success("job.scout", output=output)


def _render(data: dict) -> str:
    """Báo cáo markdown người-đọc-được."""
    lines = [
        "# 🧭 Job Scout — Báo cáo cơ hội việc làm",
        f"Tìm thấy **{data['total_found']}** tin; xếp hạng theo Match Score "
        f"(từ khoá: {', '.join(data['keywords'])}).\n",
    ]
    for i, r in enumerate(data["top"], start=1):
        pct = int(round(r["score"] * 100))
        kw = ", ".join(r["matched"]) if r["matched"] else "—"
        lines.append(f"## {i}. {r['title']}  ·  Match {pct}% ({r['level']})")
        lines.append(f"- 🔗 {r['url']}")
        lines.append(f"- 🔑 Khớp: {kw}")
        lines.append(f"- 📝 {r['summary']}")
        lines.append("")
    if data["errors"]:
        lines.append("---")
        lines.append("**URL cào lỗi:**")
        for e in data["errors"][:5]:
            lines.append(f"- {e}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI độc lập (Level 4)
# ---------------------------------------------------------------------------
def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="AURA skill job.scout — săn việc + Match Score.")
    ap.add_argument("--url", action="append", default=[], help="URL tuyển dụng (lặp lại được).")
    ap.add_argument("--keywords", default="", help="kw:trọng_số, kw (mặc định bộ của Sếp).")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    result = tool_scout_jobs(
        urls=args.url or None, keywords=args.keywords, top_k=args.top_k, as_json=args.json
    )
    print(result.output if result.ok else f"[LỖI] {result.error}")
    return 0 if result.ok else 1


__all__ = ["tool_scout_jobs", "set_summarizer", "set_browser_fetcher"]


if __name__ == "__main__":
    raise SystemExit(_main())
