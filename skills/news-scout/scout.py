"""
skills/news-scout/scout.py
==========================
News Scout — "Nhịp tim đọc tin" (LỚP LOGIC, Level 4).

Kéo tiêu đề (RSS/trang tin) -> chấm điểm hữu ích theo mục tiêu của Sếp (CÔNG NHÂN
embedding local core/embedder.py; fallback: LLM local rồi heuristic) -> CHỈ kéo chi
tiết bài điểm cao -> đếm bài hữu ích theo domain -> tự whitelist nguồn tốt vào
data/whitelist_sources.json.

CÔNG NHÂN THỨ HAI theo mô hình "quản gia giao tool cho thợ" (sau job_scout):
pipeline cầm tool (RSS/HTTP), model nhỏ ~118M chỉ trả lời câu hỏi đóng "tiêu đề này
giống mục tiêu của Sếp cỡ nào" — không cần dựng LLM 7.2GB mỗi nhịp tin nữa.

Thiết kế NHẸ CPU:
  - Parse RSS bằng stdlib `xml.etree` (không phụ thuộc), giới hạn số bài/nguồn.
  - Chấm điểm gom 1 LẦN gọi LLM cho cả cụm tiêu đề (batched), không gọi từng bài.
  - Chỉ tải nội dung chi tiết cho `max_detail` bài điểm cao nhất.

Tuân thủ CONTEXT.md: bọc try/except (§2), trả ToolResult (không ném), validate URL
(§7), read-only + timeout (§6), không secret (§1).
"""

from __future__ import annotations

import sys
from pathlib import Path

# skills/news-scout/scout.py -> parents[2] = gốc dự án (KHÁC các skill trong scripts/).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests

from core.schemas import ToolResult

logger = logging.getLogger("aura.skills.news_scout")

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "application/rss+xml,application/xml,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",  # KHÔNG br (tránh mojibake khi thiếu brotli)
}
_NOISE_TAGS = ("script", "style", "noscript", "template", "svg", "nav", "header", "footer")

# Mục tiêu cốt lõi (dùng cho cả LLM prompt lẫn heuristic).
#
# 12/08/2026: bản cũ ghi thẳng tỉnh đang ở và ngành Sếp đang theo, cả trong
# _GOAL lẫn trọng số. Gỡ khi soi bản đã đẩy lên GitHub — ghép lại là một hồ sơ
# cá nhân. Muốn chấm theo mục tiêu riêng thì sửa hai hằng số này ở bản của mình.
_GOAL = ("Python/AI/trí tuệ nhân tạo, dựng video, công nghệ và việc làm.")
_GOAL_WEIGHTS: dict[str, int] = {
    "python": 2, "ai": 2, "trí tuệ nhân tạo": 2, "machine learning": 2,
    "video": 1, "công nghệ": 1, "việc làm": 2, "tuyển dụng": 2,
}

# Nguồn RSS mặc định (nhẹ, XML nhỏ). Có thể bổ sung qua whitelist đã học.
_DEFAULT_SOURCES: tuple[str, ...] = (
    "https://vnexpress.net/rss/giao-duc.rss",
    "https://vnexpress.net/rss/so-hoa.rss",
    "https://thanhnien.vn/rss/giao-duc.rss",
)

_MAX_TITLES_PER_SOURCE = 15      # trần tiêu đề mỗi nguồn — giữ nhẹ
_DETAIL_MAX_CHARS = 4000
_WHITELIST_PATH = _PROJECT_ROOT / "data" / "whitelist_sources.json"
_WHITELIST_USEFUL_THRESHOLD = 5  # cộng dồn đủ bài hữu ích -> whitelist domain


# ---------------------------------------------------------------------------
# Chấm điểm (pluggable: LLM batched, fallback heuristic)
# ---------------------------------------------------------------------------
def _heuristic_scores(titles: list[str], goal: str = "") -> list[float]:
    """Chấm điểm 0..1 theo từ khoá mục tiêu (rẻ, tất định, offline)."""
    total = sum(_GOAL_WEIGHTS.values()) or 1
    out: list[float] = []
    for t in titles:
        low = (t or "").lower()
        got = sum(w for kw, w in _GOAL_WEIGHTS.items() if kw in low)
        # Chuẩn hoá mềm: 1 từ khoá mạnh đã đủ "hữu ích".
        out.append(round(min(1.0, got / max(3, total / 4)), 3))
    return out


def _llm_scores(titles: list[str], goal: str) -> list[float] | None:
    """
    Gom toàn bộ tiêu đề -> 1 LẦN gọi LLM local chấm điểm 0..1. Trả None nếu lỗi/offline
    (caller sẽ fallback heuristic). Giữ NHẸ: một call duy nhất cho cả cụm.
    """
    try:
        from core.llm import LocalCPUEngine
    except Exception as exc:  # noqa: BLE001
        logger.info("Không nạp được LocalCPUEngine (%s) -> heuristic.", exc)
        return None

    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    system = (
        "Bạn là bộ lọc tin của AURA. Chấm mức HỮU ÍCH của từng tiêu đề theo MỤC TIÊU "
        f"của Sếp: {goal}. Chỉ trả về MỘT mảng JSON các số thực 0..1 theo đúng thứ tự, "
        "không giải thích. Ví dụ: [0.9, 0.1, 0.5]"
    )
    try:
        eng = LocalCPUEngine()
        res = eng.complete(
            [{"role": "user", "content": numbered}],
            system_prompt=system, temperature=0.0, max_tokens=256,
        )
        if not res.get("ok"):
            logger.info("LLM chấm điểm lỗi (%s) -> heuristic.", res.get("error"))
            return None
        m = re.search(r"\[.*\]", res["text"], re.DOTALL)
        scores = json.loads(m.group(0)) if m else json.loads(res["text"])
        scores = [float(x) for x in scores][: len(titles)]
        # Thiếu thì bù 0.0 cho đủ độ dài.
        scores += [0.0] * (len(titles) - len(scores))
        return [max(0.0, min(1.0, s)) for s in scores]
    except Exception as exc:  # noqa: BLE001 — LLM hỏng không được làm sập nhịp tim
        logger.info("LLM chấm điểm hỏng (%s) -> heuristic.", exc)
        return None


def _embed_scores(titles: list[str], goal: str) -> list[float] | None:
    """CÔNG NHÂN embedding chấm điểm local. None nếu công nhân hỏng (caller fallback).

    Tách goal thành cụm từ khoá (theo dấu phẩy và '/'), điểm gốc = cosine cao nhất
    giữa tiêu đề và từng cụm, calib [news_embed_low, news_embed_high] -> [0,1]
    ("gen cấu hình" RIÊNG, gắt hơn job_scout vì feed tin toàn bài gần chủ đề).
    Điểm cuối = max(embedding, heuristic): khớp từ khoá nguyên văn vẫn là tín hiệu mạnh.
    """
    try:
        import numpy as np
        from core.embedder import get_worker
        phrases = [p.strip() for p in re.split(r"[,/]", goal or "") if p.strip()]
        if not phrases or not titles:
            return None
        try:
            from core.config import settings
            low = float(getattr(settings, "news_embed_low", 0.35))
            high = float(getattr(settings, "news_embed_high", 0.85))
        except Exception:  # noqa: BLE001 — thiếu config vẫn chấm được
            low, high = 0.35, 0.85
        worker = get_worker()
        doc_emb = worker.embed([t or " " for t in titles])
        ph_emb = worker.embed(phrases)
        base = (ph_emb @ doc_emb.T).max(axis=0)
        emb = np.clip((base - low) / max(high - low, 1e-6), 0.0, 1.0)
        heur = _heuristic_scores(titles, goal)
        return [round(float(max(e, h)), 3) for e, h in zip(emb, heur)]
    except Exception as exc:  # noqa: BLE001 — công nhân hỏng -> còn LLM/heuristic
        logger.info("Công nhân embedding lỗi (%s) -> LLM/heuristic.", exc)
        return None


_SCORER = None  # cho phép tiêm scorer khác để test: fn(titles, goal)->list[float]


def set_scorer(fn) -> None:
    """Tiêm bộ chấm điểm (test/định tuyến) — fn(titles: list[str], goal: str)->list[float]."""
    global _SCORER
    _SCORER = fn


def _score_titles(titles: list[str], goal: str, use_llm: bool) -> list[float]:
    """Thứ tự: scorer tiêm -> công nhân embedding -> LLM local -> heuristic."""
    if _SCORER is not None:
        try:
            return list(_SCORER(titles, goal))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Scorer tiêm lỗi -> heuristic: %s", exc)
    emb = _embed_scores(titles, goal)
    if emb is not None:
        return emb
    if use_llm:
        s = _llm_scores(titles, goal)
        if s is not None:
            return s
    return _heuristic_scores(titles, goal)


# ---------------------------------------------------------------------------
# Kéo tiêu đề (RSS stdlib) + chi tiết (có chọn lọc)
# ---------------------------------------------------------------------------
def _http_get(url: str, timeout_s: float = 15.0) -> requests.Response:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout_s)
    resp.raise_for_status()
    if "charset" not in resp.headers.get("Content-Type", "").lower():
        resp.encoding = resp.apparent_encoding
    return resp


def _parse_rss(xml_text: str, limit: int) -> list[dict]:
    """Parse RSS/Atom bằng stdlib. Trả [{title, link}]. Không phải XML -> []."""
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for node in root.iter():
        tag = node.tag.lower().rsplit("}", 1)[-1]
        if tag not in ("item", "entry"):
            continue
        title, link = None, ""
        for child in node:
            ctag = child.tag.lower().rsplit("}", 1)[-1]
            if ctag == "title" and child.text:
                title = child.text.strip()
            elif ctag == "link":
                link = (child.get("href") or (child.text or "")).strip()
        if title:
            # Feed (vd thanhnien.vn) hay để entity HTML trong title ('T&ocirc;n') ->
            # unescape cho sạch cả hiển thị lẫn embedding.
            import html
            items.append({"title": html.unescape(title), "link": link})
        if len(items) >= limit:
            break
    return items


def _fetch_titles(source_url: str) -> list[dict]:
    """Kéo danh sách {title, link, domain} từ một nguồn RSS. Lỗi -> [] (caller log)."""
    resp = _http_get(source_url)
    items = _parse_rss(resp.text, _MAX_TITLES_PER_SOURCE)
    domain = urlparse(source_url).netloc
    for it in items:
        it["domain"] = urlparse(it["link"]).netloc or domain
        it["source"] = source_url
    return items


def _fetch_detail(url: str) -> str:
    """Kéo nội dung chi tiết 1 bài (chỉ gọi cho bài điểm cao). Lỗi -> ''."""
    try:
        resp = _http_get(url, timeout_s=15.0)
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(list(_NOISE_TAGS)):
                tag.decompose()
            raw = soup.get_text(separator="\n")
        except ModuleNotFoundError:
            raw = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(s.strip() for s in raw.splitlines() if s.strip()))
        return text[:_DETAIL_MAX_CHARS]
    except Exception as exc:  # noqa: BLE001 — 1 bài lỗi không giết cả nhịp
        logger.warning("Kéo chi tiết lỗi %s: %s", url, exc)
        return ""


# ---------------------------------------------------------------------------
# Auto-Subscribe (whitelist_sources.json)
# ---------------------------------------------------------------------------
def _load_whitelist() -> dict:
    try:
        if _WHITELIST_PATH.is_file():
            return json.loads(_WHITELIST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Đọc whitelist lỗi (dùng rỗng): %s", exc)
    return {"domains": {}}


def _save_whitelist(data: dict) -> None:
    try:
        _WHITELIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        _WHITELIST_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 — ghi whitelist hỏng không được làm sập nhịp
        logger.warning("Ghi whitelist lỗi: %s", exc)


def _update_whitelist(useful_by_domain: dict[str, int], seen_by_domain: dict[str, int]) -> list[str]:
    """Cộng dồn số bài hữu ích/đã thấy theo domain. Trả list domain VỪA được whitelist."""
    data = _load_whitelist()
    domains = data.setdefault("domains", {})
    newly: list[str] = []
    all_domains = set(useful_by_domain) | set(seen_by_domain)
    for dom in all_domains:
        rec = domains.setdefault(dom, {"useful": 0, "seen": 0, "whitelisted": False})
        rec["useful"] += useful_by_domain.get(dom, 0)
        rec["seen"] += seen_by_domain.get(dom, 0)
        if not rec["whitelisted"] and rec["useful"] >= _WHITELIST_USEFUL_THRESHOLD:
            rec["whitelisted"] = True
            rec["since"] = time.strftime("%Y-%m-%d")
            newly.append(dom)
    _save_whitelist(data)
    return newly


def whitelisted_feeds() -> list[str]:
    """Trả các nguồn RSS đã whitelist (nếu lưu kèm). Hiện whitelist theo domain bài viết;
    để mở rộng tần suất, daemon có thể ưu tiên các domain này."""
    data = _load_whitelist()
    return [d for d, r in data.get("domains", {}).items() if r.get("whitelisted")]


# ---------------------------------------------------------------------------
# Tool công khai cho Registry
# ---------------------------------------------------------------------------
def tool_news_scout(
    sources: list[str] | str | None = None,
    goal: str = "",
    threshold: float = 0.4,
    max_detail: int = 3,
    use_llm: bool = True,
    persist: bool = True,
    as_json: bool = False,
) -> ToolResult:
    """
    Tool 'news.scout': đọc tin, chấm điểm, kéo chi tiết bài tốt, tự whitelist nguồn.
    Luôn trả ToolResult (không ném exception).
    """
    goal = goal.strip() or _GOAL
    src_list = ([sources] if isinstance(sources, str) else (list(sources) if sources else list(_DEFAULT_SOURCES)))

    articles: list[dict] = []
    errors: list[str] = []
    seen_by_domain: dict[str, int] = {}

    try:
        for s in src_list:
            parsed = urlparse((s or "").strip())
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                errors.append(f"Bỏ nguồn không hợp lệ: {s!r}")
                continue
            try:
                items = _fetch_titles(s.strip())
            except requests.RequestException as exc:
                errors.append(f"Nguồn lỗi {s}: {exc}")
                continue
            for it in items:
                seen_by_domain[it["domain"]] = seen_by_domain.get(it["domain"], 0) + 1
            articles.extend(items)

        if not articles:
            reason = "Không kéo được tiêu đề nào."
            if errors:
                reason += " Chi tiết: " + " | ".join(errors[:5])
            return ToolResult.failure("news.scout", reason)

        # --- AI JUDGMENT: chấm điểm gom 1 lần ---
        titles = [a["title"] for a in articles]
        scores = _score_titles(titles, goal, use_llm)
        for a, sc in zip(articles, scores):
            a["score"] = round(float(sc), 3)

        articles.sort(key=lambda a: a["score"], reverse=True)
        useful = [a for a in articles if a["score"] >= threshold]

        # --- Kéo chi tiết CHỌN LỌC: chỉ top max_detail bài hữu ích ---
        for a in useful[: max(0, max_detail)]:
            if a.get("link"):
                a["detail"] = _fetch_detail(a["link"])

        # --- AUTO-SUBSCRIBE ---
        newly_whitelisted: list[str] = []
        if persist:
            useful_by_domain: dict[str, int] = {}
            for a in useful:
                useful_by_domain[a["domain"]] = useful_by_domain.get(a["domain"], 0) + 1
            newly_whitelisted = _update_whitelist(useful_by_domain, seen_by_domain)
    except Exception as exc:  # noqa: BLE001 — vành đai cuối
        return ToolResult.failure("news.scout", f"Lỗi đọc tin: {exc}")
    finally:
        # Công nhân xong ca thì nhả RAM (nhịp tin chỉ chạy vài lần/ngày).
        try:
            from core.embedder import get_worker
            get_worker().unload()
        except Exception:  # noqa: BLE001
            pass

    data = {
        "goal": goal,
        "total_seen": len(articles),
        "useful_count": len(useful),
        "threshold": threshold,
        "top": [
            {"title": a["title"], "score": a["score"], "domain": a["domain"],
             "link": a.get("link", ""), "has_detail": bool(a.get("detail"))}
            for a in useful[: max(max_detail, 5)]
        ],
        "newly_whitelisted": newly_whitelisted,
        "errors": errors,
    }
    output = json.dumps(data, ensure_ascii=False, indent=2) if as_json else _render(data)
    return ToolResult.success("news.scout", output=output)


def _render(data: dict) -> str:
    lines = [
        "# 📰 News Scout — Nhịp tim đọc tin",
        f"Quét {data['total_seen']} tin · hữu ích **{data['useful_count']}** "
        f"(ngưỡng {data['threshold']}). Mục tiêu: {data['goal']}\n",
    ]
    for i, a in enumerate(data["top"], start=1):
        pct = int(round(a["score"] * 100))
        flag = " 📄" if a["has_detail"] else ""
        lines.append(f"{i}. [{pct}%] {a['title']}{flag}")
        lines.append(f"   {a['domain']} · {a['link']}")
    if data["newly_whitelisted"]:
        lines.append("\n✅ Tự THEO DÕI nguồn tốt (whitelist): " + ", ".join(data["newly_whitelisted"]))
    if data["errors"]:
        lines.append("\n⚠️ Nguồn lỗi: " + " | ".join(data["errors"][:5]))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI độc lập (Level 4)
# ---------------------------------------------------------------------------
def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="AURA skill news.scout — nhịp tim đọc tin.")
    ap.add_argument("--source", action="append", default=[], help="URL RSS (lặp lại được).")
    ap.add_argument("--threshold", type=float, default=0.4)
    ap.add_argument("--max-detail", type=int, default=3)
    ap.add_argument("--no-llm", action="store_true", help="Tắt LLM, dùng heuristic.")
    ap.add_argument("--no-persist", action="store_true", help="Không ghi whitelist.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    result = tool_news_scout(
        sources=args.source or None, threshold=args.threshold, max_detail=args.max_detail,
        use_llm=not args.no_llm, persist=not args.no_persist, as_json=args.json,
    )
    print(result.output if result.ok else f"[LỖI] {result.error}")
    return 0 if result.ok else 1


__all__ = ["tool_news_scout", "set_scorer", "whitelisted_feeds"]


if __name__ == "__main__":
    raise SystemExit(_main())
