"""
skills/trend-radar/radar.py
===========================
CÔNG NHÂN RADAR TREND — công nhân thứ tư theo mô hình "quản gia giao tool cho thợ".

Nhiệm vụ: quét vài nguồn TREND miễn phí (Google Trends RSS, Hacker News...) -> công
nhân embedding chấm chủ đề nào đang lên MÀ hợp GÓC RIÊNG của Sếp (giáo dục/Python/
video...) -> dựng BRIEF cho top chủ đề để Sếp quay video ăn theo NHANH nhưng có góc
riêng. KHÔNG sinh video, KHÔNG tự đăng — chỉ đưa Sếp tấm bản đồ + tờ brief.

Phân vai đúng kiến trúc:
  - Việc lọc/xếp hạng (câu hỏi đóng "chủ đề này hợp góc của Sếp cỡ nào") -> CÔNG NHÂN
    embedding local core/embedder.py (rẻ, ~0.3s, offline).
  - Việc VIẾT brief (sinh văn bản) -> NÃO CLOUD (CloudEngine) nếu bật; không thì rơi
    về brief-khung mẫu (vẫn dùng được, Sếp tự điền).

Read-only mạng, bọc try/except, trả ToolResult (không ném). PII không rời máy.
Cấu hình .env: TREND_SOURCES, TREND_ANGLE, TREND_GEO, TREND_TOP, TREND_USE_CLOUD.
"""

from __future__ import annotations

import sys
from pathlib import Path

# skills/trend-radar/radar.py -> parents[2] = gốc dự án.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote, urlparse

import requests

from core.schemas import ToolResult

logger = logging.getLogger("aura.skills.trend_radar")

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "application/rss+xml,application/xml,text/html;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}

# Góc riêng mặc định của Sếp (lợi thế thật: giáo viên tương lai + Python + dựng video).
_DEFAULT_ANGLE = ("Giáo dục, dạy học, sư phạm, học sinh, Python, lập trình, "
                  "tự động hóa, trí tuệ nhân tạo, công nghệ giáo dục, dựng video, CapCut")
# Từ khóa GÓC song ngữ — tín hiệu CHÍNH XÁC (feed trend tổng hợp nhiều rác giải trí/
# thể thao, embedding thuần không lọc nổi; có từ khóa mới coi là thật sự hợp góc).
_ANGLE_KEYWORDS = (
    "giáo dục", "giáo viên", "dạy học", "dạy", "sư phạm", "học sinh", "sinh viên",
    "trường học", "bài giảng", "giáo án", "python", "lập trình", "code", "coding",
    "phần mềm", "tự động", "automation", "ai", "trí tuệ nhân tạo", "machine learning",
    "chatbot", "llm", "công nghệ", "tech", "software", "developer", "video", "capcut",
    "edit", "youtube", "tiktok", "khóa học", "education", "teacher", "teaching",
    "student", "learning", "programming",
)
_MAX_PER_SOURCE = 25
_REPORT_PATH = _PROJECT_ROOT / "data" / "feedback" / "trend_radar_last.json"


def _settings():
    try:
        from core.config import settings
        return settings
    except Exception:  # noqa: BLE001
        return None


def _default_sources(geo: str) -> list[str]:
    # Nguồn TREND miễn phí, không cần API key, đều RSS:
    #  - Google Trends: chủ đề đang hot theo quốc gia (có cả lượng traffic).
    #  - Hacker News frontpage: trend công nghệ/lập trình đang nổi.
    return [
        f"https://trends.google.com/trending/rss?geo={geo}",
        "https://hnrss.org/frontpage",
    ]


# --------------------------------------------------------------------------- #
# Thu thập trend (read-only)
# --------------------------------------------------------------------------- #
def _http_get(url: str, timeout_s: float = 15.0) -> requests.Response:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout_s)
    resp.raise_for_status()
    if "charset" not in resp.headers.get("Content-Type", "").lower():
        resp.encoding = resp.apparent_encoding
    return resp


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _parse_trends(xml_text: str, source: str, limit: int) -> list[dict]:
    """Parse RSS trend (chuẩn + namespace Google Trends ht:). Trả [{title, signal, why, link}]."""
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    import html
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        title = link = signal = why = ""
        for c in node.iter():
            lt = _local(c.tag)
            txt = (c.text or "").strip()
            if lt == "title" and not title and txt:
                title = html.unescape(txt)
            elif lt == "link" and not link:
                link = (c.get("href") or txt).strip()
            elif "approx_traffic" in lt and txt:
                signal = txt                       # Google Trends: lượng tìm kiếm
            elif lt in ("news_item_title", "description") and not why and txt:
                why = html.unescape(re.sub(r"<[^>]+>", " ", txt))[:160]
        if title:
            if not link:
                link = "https://trends.google.com/trends/explore?q=" + quote(title)
            items.append({"title": title, "signal": signal, "why": why,
                          "link": link, "source": urlparse(source).netloc})
        if len(items) >= limit:
            break
    return items


def _collect(sources: list[str]) -> list[dict]:
    out: list[dict] = []
    for s in sources:
        p = urlparse((s or "").strip())
        if p.scheme not in ("http", "https"):
            continue
        try:
            resp = _http_get(s.strip())
            out += _parse_trends(resp.text, s, _MAX_PER_SOURCE)
        except Exception as exc:  # noqa: BLE001 — 1 nguồn lỗi không giết cả radar
            logger.info("Nguồn trend lỗi %s (bỏ qua): %s", s, exc)
    return out


# --------------------------------------------------------------------------- #
# Lọc/xếp hạng bằng công nhân embedding (câu hỏi đóng: hợp góc của Sếp cỡ nào)
# --------------------------------------------------------------------------- #
# Khớp theo RANH GIỚI TỪ (\b), KHÔNG phải chuỗi con: "ai" chỉ khớp từ "ai"/"AI"
# đứng riêng, không dính vào "tại/mai/hai..." (tiếng Việt đầy 'ai' làm chuỗi con).
_KW_PATTERNS = tuple(
    (kw, re.compile(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", re.IGNORECASE))
    for kw in _ANGLE_KEYWORDS
)


def _keyword_hit(text: str) -> tuple[float, str]:
    """Từ khóa góc có đứng RIÊNG trong text? Trả (điểm 0..1, từ khóa khớp dài nhất)."""
    hits = [kw for kw, pat in _KW_PATTERNS if pat.search(text)]
    if not hits:
        return 0.0, ""
    # 1 từ khóa đã là tín hiệu topical mạnh với tiêu đề trend ngắn; 2+ -> chắc chắn.
    hits.sort(key=len, reverse=True)              # ưu tiên khớp cụm dài ("trí tuệ nhân tạo")
    return (1.0 if len(hits) >= 2 else 0.85), hits[0]


def _rank(items: list[dict], angle: str) -> list[dict]:
    """Xếp hạng độ hợp góc = TỪ KHÓA (chính xác) kết hợp EMBEDDING (độ phủ).

    Feed trend tổng hợp đầy rác giải trí/thể thao mà embedding nhỏ không lọc nổi
    (chữ 'sư phạm' hút cả 'nam em'). Nên: có từ khóa góc -> tin (fit cao); KHÔNG có
    từ khóa -> dìm mạnh điểm embedding (chỉ giữ khi embedding cực cao, bắt được
    paraphrase như 'chatbot' ~ AI mà tiêu đề không chứa từ khóa thẳng)."""
    if not items:
        return []
    phrases = [p.strip() for p in re.split(r"[,/]", angle or "") if p.strip()]
    st = _settings()
    low = float(getattr(st, "trend_embed_low", 0.30)) if st else 0.30
    high = float(getattr(st, "trend_embed_high", 0.68)) if st else 0.68
    try:
        import numpy as np
        from core.embedder import get_worker
        worker = get_worker()
        docs = [f"{it['title']} {it.get('why', '')}" for it in items]
        d_emb = worker.embed(docs)
        p_emb = worker.embed(phrases) if phrases else None
        for i, it in enumerate(items):
            emb = 0.0
            hit_phrase = ""
            if p_emb is not None:
                sims = p_emb @ d_emb[i]
                j = int(sims.argmax())
                emb = float(np.clip((sims[j] - low) / max(high - low, 1e-6), 0, 1))
                hit_phrase = phrases[j]
            kw, kw_word = _keyword_hit(f"{it['title']} {it.get('why', '')}")
            if kw > 0:
                it["fit"] = round(max(kw, emb), 3)          # topical theo từ khóa -> tin
                it["angle_hit"] = kw_word
            else:
                it["fit"] = round(emb * 0.35, 3)            # không từ khóa -> dìm nhiễu embedding
                it["angle_hit"] = hit_phrase
    except Exception as exc:  # noqa: BLE001 — embedder hỏng -> lọc thô bằng từ khóa
        logger.warning("Radar embedding lỗi (%s) -> chỉ dùng từ khóa.", exc)
        for it in items:
            kw, kw_word = _keyword_hit(f"{it['title']} {it.get('why', '')}")
            it["fit"] = kw
            it["angle_hit"] = kw_word
    items.sort(key=lambda it: it["fit"], reverse=True)
    return items


# --------------------------------------------------------------------------- #
# Dựng brief: cloud viết (nếu bật) hoặc khung mẫu (offline)
# --------------------------------------------------------------------------- #
def _brief_template(it: dict, angle: str) -> str:
    hit = it.get("angle_hit") or "góc của Sếp"
    why = it.get("why") or (f"đang có ~{it['signal']} lượt tìm" if it.get("signal") else "đang nổi trên nguồn trend")
    return (
        f"Góc riêng gợi ý: nhìn '{it['title']}' dưới lăng kính {hit}.\n"
        f"    Cấu trúc 3 phần: (1) Hook 5s: nêu '{it['title']}' đang nóng; "
        f"(2) Thân: giải thích/áp dụng theo góc {hit}; (3) Chốt: bài học + CTA.\n"
        f"    Hook thử: \"Ai cũng nói về {it['title']}, nhưng dưới góc {hit} thì sao?\""
    )


def _brief_cloud(top: list[dict], angle: str) -> str | None:
    """Một lần gọi cloud viết brief cho cả top chủ đề. None nếu cloud lỗi/không cấu hình."""
    try:
        from core.llm import CloudEngine
        listing = "\n".join(
            f"{i+1}. {it['title']} (góc khớp: {it.get('angle_hit','')}; "
            f"vì sao nóng: {it.get('why') or it.get('signal') or '?'})"
            for i, it in enumerate(top)
        )
        system = (
            "Bạn là nhà chiến lược nội dung cho một creator có góc riêng: " + angle +
            ". Với MỖI chủ đề đang trend dưới đây, viết brief NGẮN gọn tiếng Việt gồm 3 ý: "
            "(a) GÓC RIÊNG creator nên khai thác (khác đám đông), (b) cấu trúc 3 phần "
            "(hook / thân / chốt), (c) một câu HOOK mở đầu. Đánh số theo đúng thứ tự, "
            "không lan man, không sáo rỗng."
        )
        res = CloudEngine().complete(
            [{"role": "user", "content": listing}],
            system_prompt=system, temperature=0.6, max_tokens=900,
        )
        if res.get("ok") and res.get("text", "").strip():
            return res["text"].strip()
        logger.info("Cloud viết brief không thành (%s) -> khung mẫu.", res.get("error"))
    except Exception as exc:  # noqa: BLE001 — cloud hỏng -> khung mẫu
        logger.info("Cloud brief lỗi (%s) -> khung mẫu.", exc)
    return None


# --------------------------------------------------------------------------- #
# Tool công khai cho Registry
# --------------------------------------------------------------------------- #
def tool_trend_radar(
    sources: list[str] | str | None = None,
    angle: str = "",
    geo: str = "",
    top: int = 5,
    use_cloud: bool | None = None,
    as_json: bool = False,
) -> ToolResult:
    """Tool 'trend.radar': quét trend -> lọc theo góc của Sếp -> brief top chủ đề."""
    st = _settings()
    angle = (angle or (getattr(st, "trend_angle", None) if st else None) or _DEFAULT_ANGLE).strip()
    geo = (geo or (getattr(st, "trend_geo", None) if st else None) or "VN").strip()
    top = max(1, min(int(top), 10))
    if use_cloud is None:
        use_cloud = bool(getattr(st, "trend_use_cloud", False)) if st else False
    if sources:
        src_list = [sources] if isinstance(sources, str) else list(sources)
    else:
        cfg = (getattr(st, "trend_sources", None) if st else None) or ""
        src_list = [u.strip() for u in cfg.split(",") if u.strip()] or _default_sources(geo)

    try:
        items = _collect(src_list)
        if not items:
            return ToolResult.failure("trend.radar", "Không kéo được trend nào từ các nguồn.")
        ranked = _rank(items, angle)
        min_fit = float(getattr(st, "trend_min_fit", 0.5)) if st else 0.5
        top_items = [it for it in ranked if it.get("fit", 0) >= min_fit][:top]
        weak = not top_items
        if weak:                               # hôm nay không có gì hợp góc -> đưa top thô + cờ
            top_items = ranked[:min(top, 3)]

        cloud_briefs = _brief_cloud(top_items, angle) if (use_cloud and top_items) else None
        for it in top_items:
            it["brief"] = _brief_template(it, angle)

        data = {
            "ts": int(time.time()),
            "angle": angle,
            "total_seen": len(items),
            "weak": weak,
            "top": [
                {"title": it["title"], "fit": it.get("fit", 0), "angle_hit": it.get("angle_hit", ""),
                 "signal": it.get("signal", ""), "why": it.get("why", ""),
                 "link": it.get("link", ""), "source": it.get("source", ""),
                 "brief": it.get("brief", "")}
                for it in top_items
            ],
            "cloud_briefs": cloud_briefs or "",
        }
        try:
            _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            _REPORT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as exc:
            logger.warning("Ghi báo cáo radar lỗi (bỏ qua): %s", exc)

        output = json.dumps(data, ensure_ascii=False, indent=2) if as_json else _render(data)
        return ToolResult.success("trend.radar", output=output)
    except Exception as exc:  # noqa: BLE001 — vành đai cuối
        return ToolResult.failure("trend.radar", f"Lỗi radar trend: {exc}")
    finally:
        try:
            from core.embedder import get_worker
            get_worker().unload()
        except Exception:  # noqa: BLE001
            pass


def _render(data: dict) -> str:
    lines = [
        "# 📡 Radar Trend — chủ đề đang lên hợp góc của Sếp",
        f"Quét {data['total_seen']} chủ đề · góc: {data['angle']}\n",
    ]
    if data.get("weak"):
        lines.append("⚠️ Hôm nay chưa có trend nào hợp góc rõ rệt — đây là mấy chủ đề gần nhất:\n")
    for i, it in enumerate(data["top"], start=1):
        pct = int(round(it["fit"] * 100))
        sig = f" · 🔥 {it['signal']}" if it["signal"] else ""
        lines.append(f"{i}. [{pct}% hợp góc “{it['angle_hit']}”]{sig} {it['title']}")
        if it["link"]:
            lines.append(f"   {it['source']} · {it['link']}")
        if not data["cloud_briefs"] and it["brief"]:
            lines.append("   " + it["brief"].replace("\n", "\n   "))
    if data["cloud_briefs"]:
        lines.append("\n## ✍️ Brief (AURA soạn):\n" + data["cloud_briefs"])
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI độc lập (Level 4)
# --------------------------------------------------------------------------- #
def _main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="AURA skill trend.radar — radar chủ đề đang lên.")
    ap.add_argument("--source", action="append", default=[], help="URL RSS trend (lặp lại được).")
    ap.add_argument("--angle", default="", help="Góc riêng của Sếp (rỗng = mặc định).")
    ap.add_argument("--geo", default="", help="Mã quốc gia Google Trends (mặc định VN).")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--cloud", action="store_true", help="Nhờ cloud viết brief (tốn 1 lượt gọi).")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    res = tool_trend_radar(
        sources=args.source or None, angle=args.angle, geo=args.geo,
        top=args.top, use_cloud=args.cloud or None, as_json=args.json,
    )
    print(res.output if res.ok else f"[LỖI] {res.error}")
    return 0 if res.ok else 1


__all__ = ["tool_trend_radar"]


if __name__ == "__main__":
    raise SystemExit(_main())
