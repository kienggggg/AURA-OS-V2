"""
skills/scouts/job_scout.py
==========================
TÌNH BÁO TĨNH LẶNG (read-only) — gom cơ hội từ Freelance đến Ổn định, lọc rác bằng
CÔNG NHÂN embedding (model nhỏ local), dâng top vào Briefing sáng.

Luồng: URL (RSS hoặc HTML) -> bóc tin (xml stdlib / BeautifulSoup) -> chấm độ phù hợp
0.0–1.0 bằng công nhân embedding MiniLM ~118M (core/embedder.py; fallback: LLM nếu có
engine, rồi heuristic từ khoá) -> cộng/trừ điểm theo phản hồi Sếp đã ghi (record_feedback)
-> bỏ tin < ngưỡng (mặc định 0.6) -> xếp hạng -> format 2 dòng "Cơ hội kiếm tiền"
+ "Cập nhật sự nghiệp". Xong lượt quét thì công nhân nhả RAM.

Đây là CÔNG NHÂN ĐẦU TIÊN theo mô hình "quản gia giao tool cho thợ": pipeline code
cầm tool (fetch/parse), model nhỏ chỉ trả lời câu hỏi đóng (tin này giống mối quan
tâm của Sếp cỡ nào), không cần gọi cloud.

Chỉ ĐỌC (GET), bọc try/except, KHÔNG ghi/sửa gì ngoài file feedback do Sếp chủ động
chấm. PII được redact trước khi rời máy. URL & từ khoá đọc từ .env: FREELANCE_URLS,
PEDAGOGY_URLS, SCOUT_KEYWORDS, SCOUT_THRESHOLD, SCOUT_EMBED_LOW/HIGH, SCOUT_FEEDBACK_WEIGHT.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit

# skills/scouts/job_scout.py -> parents[2] = gốc dự án (cho `from core...`).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger("aura.scouts.job")

# 12/08/2026: bộ mặc định từng ghi sẵn chứng chỉ và tỉnh đang ở của Sếp. Gỡ khi
# soi bản đã đẩy lên GitHub — ghép lại là một hồ sơ cá nhân đọc được.
# Đặt SCOUT_KEYWORDS trong .env cho đúng nghề của mình.
_DEFAULT_KEYWORDS = "Python, automation, crawl data, video editor"
_DEFAULT_THRESHOLD = 0.6
_MAX_ITEMS_PER_SOURCE = 20


# --------------------------------------------------------------------------- #
# Cấu hình (đọc lười, thiếu config không sập)
# --------------------------------------------------------------------------- #
def _settings():
    try:
        from core.config import settings
        return settings
    except Exception:  # noqa: BLE001
        return None


def _csv(val) -> list[str]:
    return [u.strip() for u in str(val or "").split(",") if u.strip()]


# --------------------------------------------------------------------------- #
# Thu thập (read-only)
# --------------------------------------------------------------------------- #
def _fetch(url: str, timeout: float = 12.0, session=None) -> str:
    if not url.lower().startswith(("http://", "https://")):
        return ""
    import requests
    headers = {"User-Agent": "Mozilla/5.0 (AURA read-only scout)"}
    # Dùng Session chung khi có (tái dùng kết nối TCP/TLS -> đỡ bắt tay lại mỗi nguồn,
    # đặc biệt lợi khi nhiều nguồn cùng qua r.jina.ai). Không có session -> gọi rời như cũ.
    getter = session.get if session is not None else requests.get
    r = getter(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


def _strip_html(s: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", s or "").split())


def _parse_feed(text: str) -> list[dict]:
    """Parse RSS/Atom bằng xml stdlib (không cần feedparser). Lỗi -> []."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(text)
    except Exception:  # noqa: BLE001
        return []

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1].lower()

    out: list[dict] = []
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        title = desc = link = ""
        for c in el:
            lt = local(c.tag)
            if lt == "title":
                title = (c.text or "").strip()
            elif lt in ("description", "summary", "content"):
                desc = (c.text or "").strip()
            elif lt == "link":
                link = (c.get("href") or c.text or "").strip()
        if title:
            out.append({"title": title, "summary": _strip_html(desc)[:300], "url": link})
    return out


def _parse_html(text: str, base_url: str) -> list[dict]:
    """Cào HTML cơ bản: hốt các <a> có text giống tiêu đề việc. Lỗi/thiếu bs4 -> []."""
    try:
        from bs4 import BeautifulSoup
    except Exception:  # noqa: BLE001
        return []
    soup = BeautifulSoup(text, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a"):
        txt = " ".join(a.get_text(" ").split())
        href = a.get("href") or ""
        key = txt.lower()
        if 12 <= len(txt) <= 140 and href and key not in seen:
            seen.add(key)
            url = href if href.startswith("http") else urljoin(base_url, href)
            out.append({"title": txt, "summary": "", "url": url})
        if len(out) >= _MAX_ITEMS_PER_SOURCE * 2:
            break
    return out


def _fetch_jina(url: str, timeout: float = 15.0, session=None) -> str:
    """Đọc trang qua Jina Reader -> markdown sạch (đọc được cả trang JS, KHÔNG cookie)."""
    return _fetch("https://r.jina.ai/" + url, timeout, session=session)


def _parse_markdown(md: str) -> list[dict]:
    """Bóc các link [tiêu đề](url) trong markdown Jina trả về làm item ứng viên."""
    out: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(r"\[([^\]]{8,140})\]\((https?://[^\)\s]+)\)", md or ""):
        title = " ".join(m.group(1).split())
        key = title.lower()
        if key not in seen:
            seen.add(key)
            out.append({"title": title, "summary": "", "url": m.group(2)})
        if len(out) >= _MAX_ITEMS_PER_SOURCE * 2:
            break
    return out


def _collect_source(url: str, use_jina: bool = True, session=None) -> list[dict]:
    text = ""
    try:
        text = _fetch(url, session=session)
    except Exception as exc:  # noqa: BLE001 — cào thẳng lỗi -> còn cửa Jina
        logger.info("Cào thẳng %s lỗi (%s) -> thử Jina.", url, exc)

    items: list[dict] = []
    if text:
        head = text[:600].lower()
        if "<rss" in head or "<feed" in head or "<?xml" in head:
            items = _parse_feed(text)
        if not items:
            items = _parse_html(text, url)

    # TẦNG 2 — Jina Reader: khi cào thẳng rỗng (trang JS / chặn requests).
    if not items and use_jina:
        try:
            md = _fetch_jina(url, session=session)
            if md and "403: Forbidden" not in md and "Attention Required" not in md:
                items = _parse_markdown(md)
            else:
                logger.info("Jina cũng bị chặn (Cloudflare?) ở %s — cần RSS hoặc web.agent.", url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Jina lỗi ở %s (bỏ qua): %s", url, exc)

    for it in items:
        it["source"] = url
    return items[:_MAX_ITEMS_PER_SOURCE]


# --------------------------------------------------------------------------- #
# Chấm điểm: công nhân embedding trước, LLM rồi heuristic fallback
# --------------------------------------------------------------------------- #
def _kw_list(kw_str: str) -> list[str]:
    return [k.strip().lower() for k in re.split(r"[,\n]", kw_str or "") if k.strip()]


_FEEDBACK_PATH = _PROJECT_ROOT / "data" / "feedback" / "job_scout.jsonl"
_LAST_SCAN_PATH = _PROJECT_ROOT / "data" / "feedback" / "job_scout_last.json"
_APPLICATIONS_PATH = _PROJECT_ROOT / "data" / "feedback" / "applications.jsonl"


# --------------------------------------------------------------------------- #
# TRỢ LÝ CHỐT KÈO (kiếm tiền): cloud soạn nháp pitch + sổ theo dõi ứng tuyển.
# Máy lo phần nhàm (soạn nháp, ghi sổ); Sếp lo phần quyết (sửa + tự gửi). KHÔNG tự gửi.
# --------------------------------------------------------------------------- #
# Nguồn tin việc QUỐC TẾ (thị trường tiếng Anh) -> pitch nên viết tiếng Anh.
_INTL_JOB_HOSTS = ("remoteok", "python.org/jobs", "weworkremotely", "upwork",
                   "linkedin.com/jobs", "indeed.", "wellfound", "ycombinator",
                   "stackoverflow.com/jobs", "remote.co", "flexjobs")
_VN_DIACRITICS = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]")


def _detect_pitch_lang(title: str, url: str, detail: str) -> str:
    """Đoán ngôn ngữ pitch: nguồn quốc tế -> 'en'; tin có dấu tiếng Việt -> 'vi'; else 'en'."""
    if any(h in (url or "").lower() for h in _INTL_JOB_HOSTS):
        return "en"
    if _VN_DIACRITICS.search(((title or "") + " " + (detail or "")[:400]).lower()):
        return "vi"
    return "en"


def _pitch_template(title: str, profile: str, lang: str = "vi") -> str:
    """Khung pitch offline khi cloud không dùng được (Sếp tự điền chỗ [...])."""
    if lang == "en":
        return (
            f"Hi [name/team],\n\nI'm interested in the \"{title}\" role. "
            f"{profile.split('.')[0]}. I'd be a strong fit because [list 2-3 concrete strengths]. "
            "I work remotely, communicate clearly, and deliver on time.\n\n"
            "I'd love to hear more about the scope. You can see my work at [portfolio link], "
            "and I'm happy to share a quote. Thanks!\n[Your full name]"
        )
    return (
        f"Chào anh/chị,\n\nEm quan tâm tới công việc \"{title}\". "
        f"{profile.split('.')[0]}. Em tin mình phù hợp vì [nêu 2-3 điểm mạnh cụ thể]. "
        "Em có thể bắt đầu ngay và giao đúng hạn.\n\n"
        "Anh/chị cho em xin thêm chi tiết yêu cầu để trao đổi cụ thể hơn ạ. Cảm ơn anh/chị!\n"
        "[Tên + link portfolio/liên hệ]"
    )


def draft_pitch(title: str, url: str = "", summary: str = "", lang: str = "auto") -> str:
    """Soạn nháp thư/pitch ứng tuyển bằng não cloud (fallback khung mẫu). KHÔNG gửi.

    lang: 'vi' | 'en' | 'auto' (tự nhận theo nguồn/ngôn ngữ tin — quốc tế -> Anh).
    Best-effort kéo chi tiết tin (Jina) để pitch bám yêu cầu thật; cloud viết ~150 từ,
    KHÔNG bịa ngoài freelance_profile của Sếp.
    """
    st = _settings()
    profile = (getattr(st, "freelance_profile", "") if st else "") or "Freelancer Python & dựng video."
    detail = summary or ""
    if url and not detail:
        try:
            md = _fetch_jina(url)
            if md and "403" not in md[:200]:
                detail = re.sub(r"\s+", " ", md)[:1500]
        except Exception:  # noqa: BLE001 — không lấy được chi tiết vẫn soạn từ tiêu đề
            pass
    if lang == "auto":
        lang = _detect_pitch_lang(title, url, detail)
    try:
        from core.llm import CloudEngine
        # Chống bịa MẠNH (bài học: cloud từng gán "video content" cho AURA — sai).
        if lang == "en":
            system = (
                "Write a SHORT freelance job application (110-150 words) in natural, "
                "professional English. Applicant profile (the ONLY source of truth): " + profile +
                ". STRICT RULES: use ONLY facts stated in the profile. Do NOT invent skills, "
                "experience, or project details. Do NOT re-attribute a project to a field it "
                "isn't about. Avoid empty adjectives ('passionate', 'talented', 'expert'). "
                "Structure: hook, 2-3 concrete matches to the role, a closing CTA. "
                "Leave [brackets] for details the applicant must fill (full name, rate, portfolio link)."
            )
            user = f"Job posting: {title}"
            if detail:
                user += f"\nJob details: {detail}"
        else:
            system = (
                "Bạn viết thư ứng tuyển/pitch freelance NGẮN (120-170 từ) bằng tiếng Việt, "
                "giọng tự tin, chuyên nghiệp, KHÔNG sáo rỗng. Hồ sơ ứng viên (NGUỒN SỰ THẬT DUY "
                "NHẤT): " + profile + ". LUẬT NGHIÊM: chỉ dùng dữ kiện có trong hồ sơ — TUYỆT ĐỐI "
                "KHÔNG bịa kỹ năng/kinh nghiệm, KHÔNG gán dự án sang lĩnh vực nó không thuộc về, "
                "tránh tính từ rỗng ('tài năng', 'chuyên gia'). Gồm: câu mở hook, 2-3 điểm phù hợp "
                "cụ thể, câu kết mời trao đổi (CTA). Chừa [chỗ điền] cho thông tin cần tự thêm "
                "(tên, giá, portfolio)."
            )
            user = f"Tin việc: {title}"
            if detail:
                user += f"\nChi tiết tin: {detail}"
        res = CloudEngine().complete(
            [{"role": "user", "content": user}],
            system_prompt=system, temperature=0.5, max_tokens=500,
        )
        if res.get("ok") and res.get("text", "").strip():
            return res["text"].strip()
        logger.info("Cloud soạn pitch không thành (%s) -> khung mẫu.", res.get("error"))
    except Exception as exc:  # noqa: BLE001 — cloud hỏng -> khung mẫu
        logger.info("Soạn pitch cloud lỗi (%s) -> khung mẫu.", exc)
    return _pitch_template(title, profile, lang)


def record_application(title: str, url: str = "", status: str = "applied") -> None:
    """Ghi sổ theo dõi ứng tuyển (append jsonl): drafted | applied | replied | closed."""
    import json
    import time
    try:
        _APPLICATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": int(time.time()), "title": str(title), "url": str(url), "status": str(status)}
        with _APPLICATIONS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Ghi sổ ứng tuyển lỗi (bỏ qua): %s", exc)


def application_ledger(max_rows: int = 100) -> list[dict]:
    """Đọc sổ ứng tuyển gần nhất (cho review tuần/dashboard). Thiếu file -> []."""
    import json
    try:
        lines = _APPLICATIONS_PATH.read_text(encoding="utf-8").splitlines()[-max_rows:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def _save_last_scan(results: list[dict]) -> None:
    """Lưu top tin việc thật cho UI; không để bài báo lọt lại từ caller khác."""
    import json
    import time
    try:
        actionable = [r for r in results if _is_real_listing(r)]
        _LAST_SCAN_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": int(time.time()),
            "items": [
                {
                    **{k: r.get(k, "") for k in ("title", "url", "score", "category")},
                    "actionable": True,
                }
                for r in actionable[:10]
            ],
        }
        _LAST_SCAN_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001 — lưu cho UI lỗi không được làm hỏng lượt quét
        logger.warning("Lưu last-scan cho UI lỗi (bỏ qua): %s", exc)


def record_feedback(title: str, liked: bool, url: str = "") -> None:
    """Sếp chấm 'tin này hay/rác' — nguyên liệu cho công nhân tự tiến hoá cách chấm.

    Ghi append 1 dòng JSON; các lượt quét sau sẽ cộng điểm tin GIỐNG tin đã khen,
    trừ điểm tin giống tin đã chê (tiến hoá cấu hình, không đụng trọng số model).
    """
    import json
    import time
    _FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": int(time.time()), "title": str(title), "url": str(url), "liked": bool(liked)}
    with _FEEDBACK_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_feedback(max_rows: int = 200) -> tuple[list[str], list[str]]:
    """Đọc feedback gần nhất -> (tiêu đề đã khen, tiêu đề đã chê). Thiếu file -> rỗng."""
    import json
    liked: list[str] = []
    disliked: list[str] = []
    try:
        lines = _FEEDBACK_PATH.read_text(encoding="utf-8").splitlines()[-max_rows:]
    except OSError:
        return liked, disliked
    for ln in lines:
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        title = str(row.get("title", "")).strip()
        if title:
            (liked if row.get("liked") else disliked).append(title)
    return liked, disliked


def _embed_scores(items: list[dict], kw_str: str) -> list[float] | None:
    """Chấm bằng công nhân embedding local. None nếu công nhân hỏng (caller fallback).

    Điểm gốc = cosine cao nhất giữa tin và từng từ khoá, calib tuyến tính
    [scout_embed_low, scout_embed_high] -> [0, 1]. Sau đó cộng/trừ theo độ giống
    các tin Sếp đã khen/chê (scout_feedback_weight).
    """
    try:
        import numpy as np
        from core.embedder import get_worker
        kws = _kw_list(kw_str)
        if not kws or not items:
            return None
        st = _settings()
        low = float(getattr(st, "scout_embed_low", 0.20)) if st else 0.20
        high = float(getattr(st, "scout_embed_high", 0.55)) if st else 0.55
        fb_w = float(getattr(st, "scout_feedback_weight", 0.15)) if st else 0.15

        worker = get_worker()
        docs = [f"{it.get('title', '')} — {it.get('summary', '')[:160]}" for it in items]
        doc_emb = worker.embed(docs)                      # (n, 384)
        kw_emb = worker.embed(kws)                        # (k, 384)
        base = (kw_emb @ doc_emb.T).max(axis=0)           # từ khoá khớp nhất quyết định
        span = max(high - low, 1e-6)
        scores = np.clip((base - low) / span, 0.0, 1.0)

        liked, disliked = _load_feedback()
        if liked:
            scores = scores + fb_w * (worker.embed(liked).mean(axis=0) @ doc_emb.T)
        if disliked:
            scores = scores - fb_w * (worker.embed(disliked).mean(axis=0) @ doc_emb.T)
        return [round(float(s), 2) for s in np.clip(scores, 0.0, 1.0)]
    except Exception as exc:  # noqa: BLE001 — công nhân hỏng -> còn LLM/heuristic
        logger.warning("Công nhân embedding lỗi (fallback LLM/heuristic): %s", exc)
        return None


def _heuristic_score(item: dict, kws: list[str]) -> float:
    hay = (item.get("title", "") + " " + item.get("summary", "")).lower()
    matched = sum(1 for k in kws if k and k in hay)
    return round(min(1.0, matched / 3.0), 2)   # khớp >=3 từ khoá -> 1.0


# Dấu hiệu việc CHỈ tuyển người CƯ TRÚ ở nước ngoài — ngõ cụt, lọc bỏ sớm.
_FOREIGN_RESTRICT = (
    "based only", "us based", "u.s. based", "usa based", "us-based", "eu based",
    "eu-based", "europe based", "uk based", "canada based", "us only", "usa only",
    "u.s. only", "eu only", "uk only", "europe only", "must be based",
    "must be located", "must reside", "based in the united states",
    "located in the united states", "authorized to work in the united states",
    "work authorization", "green card", "us citizen", "eu citizen",
    "us, canada", "u.s., canada", "canada, europe",
)
# Nếu có mấy chữ này thì việc mở toàn cầu / trong nước -> GIỮ, kệ dấu hiệu trên.
_LOCAL_OK = ("vietnam", "việt nam", "viet nam", "worldwide", "anywhere", "global remote",
             "remote anywhere", "asia", "châu á")


def _is_foreign_restricted(item: dict) -> bool:
    """Việc chỉ nhận người ở nước ngoài? (giữ remote-toàn-cầu và việc trong nước)."""
    hay = (item.get("title", "") + " " + item.get("summary", "")).lower()
    if any(ok in hay for ok in _LOCAL_OK):
        return False
    return any(sig in hay for sig in _FOREIGN_RESTRICT)


def _llm_scores(items: list[dict], kw_str: str, engine) -> list[float | None] | None:
    """Chấm điểm hàng loạt bằng Local LLM. Trả list điểm (None nếu không parse được)."""
    sys_p = (
        "Bạn là bộ lọc cơ hội việc làm. Chấm ĐỘ PHÙ HỢP 0.0-1.0 của MỖI tin với mối "
        f"quan tâm của Sếp: {kw_str}. CHỈ in mỗi dòng dạng 'STT: điểm' (vd '1: 0.8'), "
        "KHÔNG giải thích, KHÔNG thêm chữ."
    )
    body = "\n".join(
        f"{i + 1}. {it.get('title', '')} — {it.get('summary', '')[:160]}"
        for i, it in enumerate(items)
    )
    try:
        res = engine.complete(
            [{"role": "user", "content": body}],
            system_prompt=sys_p, temperature=0.0, max_tokens=300,
        )
        if not res.get("ok"):
            return None
        scores: list[float | None] = [None] * len(items)
        for m in re.finditer(r"(\d+)\s*[:.\)]\s*([01](?:\.\d+)?)", res.get("text", "")):
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(items):
                try:
                    scores[idx] = max(0.0, min(1.0, float(m.group(2))))
                except ValueError:
                    pass
        return scores
    except Exception as exc:  # noqa: BLE001 — LLM lỗi -> để caller fallback heuristic
        logger.warning("LLM chấm điểm lỗi (fallback heuristic): %s", exc)
        return None


def _priority_terms() -> list[str]:
    st = _settings()
    # Rỗng = TẮT hẳn ưu tiên địa phương. Trước 12/08/2026 chỗ này rơi về tỉnh
    # đang ở của Sếp, nên gỡ ở config vẫn còn dấu vết ở đây.
    raw = (getattr(st, "scout_priority_terms", None) if st else None) or ""
    return [t.strip().lower() for t in raw.split(",") if t.strip()]


def _is_priority(item: dict) -> bool:
    hay = (item.get("title", "") + " " + item.get("summary", "")).lower()
    return any(t in hay for t in _priority_terms())


def _apply_priority_boost(items: list[dict], scores: list[float]) -> list[float]:
    """Cộng điểm cho tin chứa từ ĐỊA PHƯƠNG ưu tiên -> nổi lên top.

    Giải quyết: nguồn tin trả nhiều tin cùng nghề ở tỉnh khác với điểm ngang nhau;
    boost giúp tin đúng địa phương đã đặt vượt lên (kể cả kéo tin dưới ngưỡng lọt
    vào). Không đặt `scout_priority_terms` thì phần này tắt."""
    st = _settings()
    boost = float(getattr(st, "scout_priority_boost", 0.25)) if st else 0.25
    min_base = float(getattr(st, "scout_priority_min_base", 0.6)) if st else 0.6
    if boost <= 0 or not _priority_terms():
        return scores
    # Chỉ boost khi điểm NỀN đủ cao (>=min_base) -> không kéo tin địa phương lệch chủ đề lên.
    return [round(min(1.0, sc + boost), 2) if (_is_priority(it) and sc >= min_base) else sc
            for it, sc in zip(items, scores)]


def score_items(items: list[dict], kw_str: str | None = None, engine=None) -> list[float]:
    """Điểm 0.0-1.0 cho từng tin. Thứ tự: công nhân embedding -> LLM -> heuristic,
    rồi CỘNG điểm ưu tiên địa phương (scout_priority_terms).

    Điểm cuối lấy max(embedding, heuristic): khớp từ khoá nguyên văn là tín hiệu
    mạnh, không để điểm ngữ nghĩa dìm mất.
    """
    kw_str = kw_str or _DEFAULT_KEYWORDS
    kws = _kw_list(kw_str)
    heur = [_heuristic_score(it, kws) for it in items]
    if not items:
        return heur
    emb = _embed_scores(items, kw_str)
    if emb is not None:
        base = [round(max(e, h), 2) for e, h in zip(emb, heur)]
    elif engine is not None and (llm := _llm_scores(items, kw_str, engine)):
        base = [llm[i] if llm[i] is not None else heur[i] for i in range(len(items))]
    else:
        base = heur
    return _apply_priority_boost(items, base)


# --------------------------------------------------------------------------- #
# Gom + lọc + báo cáo
# --------------------------------------------------------------------------- #
def collect(engine=None, threshold: float | None = None) -> list[dict]:
    """Gom tin có thể ứng tuyển, loại bài báo rồi mới chấm độ phù hợp."""
    st = _settings()
    kw = (getattr(st, "scout_keywords", None) or _DEFAULT_KEYWORDS) if st else _DEFAULT_KEYWORDS
    thr = threshold if threshold is not None else (
        getattr(st, "scout_threshold", _DEFAULT_THRESHOLD) if st else _DEFAULT_THRESHOLD
    )
    free = _csv(getattr(st, "freelance_urls", None)) if st else []
    peda = _csv(getattr(st, "pedagogy_urls", None)) if st else []

    results: list[dict] = []
    import requests
    # MỘT Session dùng chung cho cả lượt quét (tái dùng kết nối TCP/TLS thay vì bắt tay
    # lại mỗi nguồn — lợi nhất khi nhiều nguồn qua CÙNG host r.jina.ai qua tầng 2).
    try:
        with requests.Session() as session:
            for category, urls in (("money", free), ("career", peda)):
                use_jina = bool(getattr(st, "scout_use_jina", True)) if st else True
                items: list[dict] = []
                for u in urls:
                    items += _collect_source(u, use_jina=use_jina, session=session)
                # Cap theo THỂ LOẠI nới gấp đôi cap nguồn: công nhân embedding chấm rẻ,
                # đừng để nguồn đứng sau bị rớt nguyên cụm như thời chấm bằng LLM.
                items = items[:_MAX_ITEMS_PER_SOURCE * 2]
                # Lọc việc chỉ tuyển ở nước ngoài TRƯỚC khi chấm (đỡ tốn cả công embed).
                if (getattr(st, "scout_local_only", True) if st else True):
                    items = [it for it in items if not _is_foreign_restricted(it)]
                # NGƯỠNG CỨNG trước embedding: từ khóa "tuyển dụng" trong một bài báo
                # không biến bài đó thành tin việc. Chỉ chấm những URL có thể ứng tuyển.
                items = [
                    it for it in items
                    if _is_real_listing({**it, "category": category})
                ]
                for it, sc in zip(items, score_items(items, kw, engine)):
                    if sc >= thr:
                        results.append({**it, "score": sc, "category": category})
    finally:
        # Công nhân xong ca thì nhả RAM (scout chỉ chạy 1-2 lần/ngày, không cần giữ model).
        try:
            from core.embedder import get_worker
            get_worker().unload()
        except Exception:  # noqa: BLE001
            pass
    # Tin đúng địa phương ưu tiên xếp TRƯỚC khi cùng điểm -> lên đầu brief kể cả
    # khi tin cả nước cũng chạm trần 1.0. Chỉ ưu-tiên-sort tin đã đủ điểm nền (>=min_base:
    # tin đã được boost -> score cao); tin đúng địa phương mà lệch chủ đề (điểm thấp)
    # không chen lên.
    min_base = float(getattr(st, "scout_priority_min_base", 0.6)) if st else 0.6
    results.sort(key=lambda r: (_is_priority(r) and r["score"] >= min_base, r["score"]),
                 reverse=True)
    _save_last_scan(results)
    # TỰ SOẠN HỒ SƠ cho tin việc THẬT đủ điểm (diệt ma sát: Sếp không phải nhấn
    # link đọc rồi tự viết pitch — mở VIỆC_HÔM_NAY.md là có sẵn mọi thứ).
    global _LAST_AUTO_DRAFTED
    try:
        _LAST_AUTO_DRAFTED = _auto_apply(results)
    except Exception as exc:  # noqa: BLE001 — hỏng khâu phụ không hỏng lượt quét
        logger.warning("Tự soạn hồ sơ lỗi (bỏ qua): %s", exc)
        _LAST_AUTO_DRAFTED = 0
    return results


_LAST_AUTO_DRAFTED = 0


_JOB_LISTING_HOSTS = (
    "remotive.com",
    "weworkremotely.com",
    "remoteok.com",
    "upwork.com",
    "freelancer.com",
    "fiverr.com",
    "vlance.vn",
    "itviec.com",
    "topcv.vn",
    "vietnamworks.com",
    "careerbuilder.vn",
    "glints.com",
    "indeed.com",
    "linkedin.com",
    "wellfound.com",
    "ycombinator.com",
    "python.org",
    "tuyencongchuc.vn",
)
_NEWS_HOSTS = (
    "news.google.",
    "laodong.vn",
    "tuoitre.vn",
    "vnanet.vn",
    "phapluatplus.vn",
    "baohungyen.vn",
    "congan.hungyen.gov.vn",
    "thuonghieucongluan.com.vn",
)
_LISTING_PATH_MARKERS = (
    "/job/",
    "/jobs/",
    "/remote-jobs/",
    "/viec-lam/",
    "/tuyen-dung/",
    "/thong-bao-tuyen",
    "/careers/",
    "/vacancies/",
)
_STRONG_LISTING_TITLE_MARKERS = (
    "thông báo tuyển dụng",
    "thông báo tuyển",
    "cần tuyển",
    "tuyển nhân viên",
    "tuyển giáo viên hợp đồng",
    "tuyển dụng giáo viên hợp đồng",
    "hiring",
    "vacancy",
    "open position",
)
_NEWS_ONLY_TITLE_MARKERS = (
    "kế hoạch tuyển dụng",
    "kỳ tuyển dụng",
    "quy trình tuyển dụng",
    "đề xuất tuyển dụng",
    "bảo đảm",
    "nguy cơ mất việc",
    "tâm thư",
    "thiếu giáo viên",
    "an ninh, trật tự",
)


# Trang tìm kiếm RỖNG (0 kết quả) hay bị scrape thành 1 "tin việc" ma.
# (?<!\d) để KHÔNG dính '10 việc làm' / '100 việc làm' (số 0 đứng sau chữ số khác).
_ZERO_RESULT = re.compile(
    r"(?<!\d)0\s*(việc làm|viec lam|công việc|cong viec|job|kết quả|ket qua)", re.I)
_NO_RESULT_MARKERS = (
    "không có việc", "khong co viec", "không tìm thấy", "khong tim thay",
    "chưa có việc", "chua co viec", "no jobs found", "no matching",
)


def _is_real_listing(item: dict) -> bool:
    """Tin ĐĂNG VIỆC thật có đích ứng tuyển, không chỉ nhắc chữ “tuyển dụng”."""
    raw_url = str(item.get("url") or "").strip()
    if not raw_url:
        return False
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = parsed.netloc.casefold().removeprefix("www.")
    path = parsed.path.casefold()
    title = str(item.get("title") or "").casefold()
    # Trang search RỖNG ("tuyển dụng 0 việc làm...") KHÔNG phải tin việc thật.
    if _ZERO_RESULT.search(title) or any(m in title for m in _NO_RESULT_MARKERS):
        return False
    if "/rss/articles/" in path or any(marker in host for marker in _NEWS_HOSTS):
        return False
    if any(marker in title for marker in _NEWS_ONLY_TITLE_MARKERS):
        return False
    if any(marker in host for marker in _JOB_LISTING_HOSTS):
        # LinkedIn/Python/YC là host rộng; bắt buộc URL nằm đúng khu vực việc làm.
        if any(wide in host for wide in ("linkedin.com", "python.org", "ycombinator.com")):
            return any(marker in path for marker in _LISTING_PATH_MARKERS)
        return True
    has_listing_path = any(marker in path for marker in _LISTING_PATH_MARKERS)
    has_listing_title = any(marker in title for marker in _STRONG_LISTING_TITLE_MARKERS)
    return has_listing_path and has_listing_title


def _auto_apply(results: list[dict]) -> int:
    """Đẩy job freelance.apply cho top tin việc thật chưa từng soạn. Trả số bộ đã đẩy."""
    st = _settings()
    if st and not bool(getattr(st, "job_auto_apply", True)):
        return 0
    thr = float(getattr(st, "job_auto_apply_threshold", 0.72)) if st else 0.72
    cap = int(getattr(st, "job_auto_apply_per_scan", 2)) if st else 2
    try:
        from core.work_for_hire import auto_draft_slots
        cap = min(cap, auto_draft_slots())
    except Exception:  # noqa: BLE001 — quota lỗi không được làm hỏng cả lượt scout
        pass
    if cap <= 0:
        return 0

    from factory import queue as fq
    from factory.models import JobRecord
    seen = {str(r.get("url") or "") for r in application_ledger(500)}
    for j in fq.list_jobs(limit=120):
        if j.tool == "freelance.apply" and j.state in ("queued", "running"):
            seen.add(str(j.params.get("url") or ""))

    n = 0
    for r in results:
        if n >= cap:
            break
        u = str(r.get("url") or "")
        if not u or u in seen or not _is_real_listing(r):
            continue
        if float(r.get("score") or 0) < thr:
            continue
        fq.enqueue(JobRecord(tool="freelance.apply", params={
            "url": u, "title": str(r.get("title") or ""), "lang": "auto",
            "_auto": True}))   # đánh dấu auto -> xong sẽ TỰ BẬT file lên màn hình
        seen.add(u)
        n += 1
    if n:
        logger.info("Job scout: tự soạn %d bộ hồ sơ ứng tuyển (freelance.apply).", n)
    return n


def morning_brief(engine=None, max_items: int = 3, threshold: float | None = None) -> str:
    """Format top cơ hội cho Briefing sáng. PII redact trước khi rời máy. '' nếu không có."""
    from core.redact import redact
    res = collect(engine=engine, threshold=threshold)
    if not res:
        return ""
    top = res[:max_items]
    money = [r for r in top if r["category"] == "money"]
    career = [r for r in top if r["category"] == "career"]
    lines: list[str] = []
    if money:
        lines.append("Cơ hội kiếm tiền hôm nay: " + "; ".join(
            redact(f"[{r['title']}]") for r in money))
    if career:
        lines.append("Cập nhật sự nghiệp: " + "; ".join(
            redact(f"[{r['title']}]") for r in career))
    return "\n".join(lines)


__all__ = ["collect", "morning_brief", "score_items", "record_feedback",
           "draft_pitch", "record_application", "application_ledger"]
