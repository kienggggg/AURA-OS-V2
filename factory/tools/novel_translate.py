"""
factory/tools/novel_translate.py
=================================
novel.translate — dịch truyện chữ DÀI (web novel/tiểu thuyết) sang tiếng Việt
rồi đóng gói PDF + EPUB bán được (tool kiếm tiền #2).

Ba vấn đề cốt lõi của dịch truyện dài và cách giải:
1. NHẤT QUÁN tên riêng      -> glossary.json bền theo bộ truyện: LLM tầng smart
   trích tên nhân vật/địa danh từ chương đầu MỘT LẦN, bơm vào mọi prompt sau;
   user sửa được file này giữa các lần chạy (dashboard chỉ đường dẫn).
2. NGỮ CẢNH giữa các chương -> mỗi call dịch kèm tóm tắt 2 câu của chương trước
   (chính LLM tự viết tóm tắt trong cùng response, lưu vào checkpoint).
3. QUOTA pool free          -> tầng bulk (6 key Gemini), throttle
   novel_rate_limit_rpm; checkpoint TỪNG CHƯƠNG — hết quota/sập máy chỉ TẠM
   DỪNG, chạy lại là tiếp tục đúng chương dở, không mất công.

Nguồn vào: dán text thẳng, đường dẫn .txt, hoặc URL (mượn skill web.scrape).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from core.config import settings
from factory import pdfkit
from factory import queue as job_queue
from factory.models import FormField, JobCancelled, JobRecord, ToolSpec
from factory.qc import QCReport, register_checker

# Nhận diện đầu chương: Trung (第N章/回/节), Việt (Chương N), Anh (Chapter N).
_CHAPTER_RE = re.compile(
    r"^\s*(第\s*[0-9〇零一二三四五六七八九十百千两]+\s*[章回节話话]|"
    r"Chương\s+\d+|Chapter\s+\d+|CHƯƠNG\s+\d+)[^\n]*$",
    re.MULTILINE,
)
_FALLBACK_CHUNK = 6000   # không dò được chương -> cắt khúc ~6k ký tự theo đoạn văn

_SUMMARY_MARK = "===TÓM TẮT==="


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE).strip("_")
    return s[:max_len] or "truyen"


def _load_source(params: dict) -> str:
    """Lấy văn bản nguồn: text dán thẳng > file .txt > URL (web.scrape)."""
    text = str(params.get("text") or "").strip()
    if text:
        return text
    src = str(params.get("source") or "").strip()
    if not src:
        raise ValueError("Chưa có nguồn truyện (dán text, đường dẫn .txt, hoặc URL).")
    p = Path(src)
    if p.exists():
        for enc in ("utf-8", "utf-16", "gb18030", "big5"):
            try:
                return p.read_text(encoding=enc)
            except (UnicodeDecodeError, UnicodeError):
                continue
        raise ValueError(f"Không đọc được file {src} (thử utf-8/utf-16/gb18030/big5).")
    if src.startswith(("http://", "https://")):
        from tools.registry import call_skill
        res = call_skill("web.scrape", {"url": src})
        if not res.ok or not res.output:
            raise ValueError(f"Cào URL thất bại: {res.error}")
        return str(res.output)
    raise ValueError(f"Nguồn không hợp lệ (không phải file/URL): {src[:80]}")


def _split_chapters(text: str) -> list[tuple[str, str]]:
    """Tách (tiêu đề chương, nội dung). Không dò được -> cắt khúc đều theo đoạn."""
    marks = list(_CHAPTER_RE.finditer(text))
    if len(marks) >= 2:
        out: list[tuple[str, str]] = []
        for i, m in enumerate(marks):
            start = m.end()
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            body = text[start:end].strip()
            if body:
                out.append((m.group(0).strip(), body))
        return out
    # Fallback: cắt ~6k ký tự, ưu tiên ranh giới đoạn văn.
    paras = [p for p in text.split("\n") if p.strip()]
    out, buf, size = [], [], 0
    for p in paras:
        buf.append(p)
        size += len(p)
        if size >= _FALLBACK_CHUNK:
            out.append((f"Phần {len(out) + 1}", "\n".join(buf)))
            buf, size = [], 0
    if buf:
        out.append((f"Phần {len(out) + 1}", "\n".join(buf)))
    return out


def _cloud(messages: list[dict], system: str, tier: str,
           temperature: float = 0.4, max_tokens: int = 8000) -> str:
    from core.llm import CloudEngine
    res = CloudEngine().complete(
        messages, system_prompt=system,
        temperature=temperature, max_tokens=max_tokens, tier=tier,
    )
    if not res.get("ok") or not str(res.get("text", "")).strip():
        raise RuntimeError(f"Cloud dịch lỗi: {res.get('error') or 'trả rỗng'}")
    return str(res["text"]).strip()


def _build_glossary(first_chapters: str, target: str) -> dict[str, str]:
    """LLM smart trích tên riêng 1 LẦN -> {tên gốc: tên dịch chốt}."""
    system = (
        "Bạn là biên tập viên dịch thuật. Từ đoạn truyện sau, trích RA JSON THUẦN "
        "(không markdown) dạng {\"tên gốc\": \"tên dịch\"} gồm tên NHÂN VẬT, ĐỊA DANH, "
        "MÔN PHÁI/TỔ CHỨC, và THUẬT NGỮ đặc thù lặp lại. Chọn cách dịch sang "
        f"{'tiếng Việt (ưu tiên Hán-Việt cho truyện Trung)' if target == 'vi' else target} "
        "hay nhất và CHỐT LUÔN — glossary này sẽ ép mọi chương dịch giống nhau. "
        "Tối đa 40 mục, chỉ lấy tên THẬT SỰ xuất hiện."
    )
    raw = _cloud([{"role": "user", "content": first_chapters[:8000]}],
                 system, tier="smart", temperature=0.2, max_tokens=2000)
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {}
    try:
        d = json.loads(m.group(0))
        return {str(k): str(v) for k, v in d.items()}
    except json.JSONDecodeError:
        return {}


def _translate_chapter(title: str, body: str, target: str, glossary: dict[str, str],
                       prev_summary: str, tier: str) -> tuple[str, str, str]:
    """Dịch 1 chương. Trả (tiêu đề dịch, nội dung dịch, tóm tắt 2 câu cho chương sau)."""
    lang = "tiếng Việt" if target == "vi" else target
    gloss_txt = "\n".join(f"- {k} => {v}" for k, v in list(glossary.items())[:40])
    system = (
        f"Bạn là dịch giả tiểu thuyết chuyên nghiệp. Dịch CHƯƠNG TRUYỆN sau sang {lang}, "
        "văn phong mượt tự nhiên như truyện xuất bản, giữ giọng kể và không khí gốc, "
        "KHÔNG tóm lược, KHÔNG bỏ đoạn.\n"
        "GLOSSARY BẮT BUỘC (dùng đúng các cách dịch đã chốt này):\n" + gloss_txt + "\n"
        + (f"BỐI CẢNH chương trước: {prev_summary}\n" if prev_summary else "")
        + "ĐỊNH DẠNG TRẢ VỀ: dòng đầu là tiêu đề chương đã dịch, xuống dòng, toàn bộ "
          f"nội dung dịch. CUỐI CÙNG là dòng '{_SUMMARY_MARK}' rồi 2 câu tóm tắt chương "
          "này (để làm bối cảnh dịch chương kế)."
    )
    raw = _cloud([{"role": "user", "content": f"{title}\n\n{body}"}],
                 system, tier=tier, max_tokens=10000)
    summary = ""
    if _SUMMARY_MARK in raw:
        raw, summary = raw.rsplit(_SUMMARY_MARK, 1)
        summary = summary.strip()[:500]
    lines = raw.strip().split("\n", 1)
    # LLM hay tự thêm '#'/'##' markdown vào tiêu đề -> lột sạch trước khi mình thêm.
    vi_title = lines[0].strip().lstrip("#").strip() or title
    vi_body = lines[1].strip() if len(lines) > 1 else ""
    if not vi_body:
        raise RuntimeError(f"Chương '{title}': cloud trả về rỗng phần nội dung.")
    return vi_title, vi_body, summary


def run(job: JobRecord, progress) -> None:
    params = job.params
    target = str(params.get("target") or "vi")
    title = str(params.get("title") or "").strip() or "Truyện chưa đặt tên"
    slug = _slug(title)

    art_dir = settings.outputs_dir / "novel" / slug
    art_dir.mkdir(parents=True, exist_ok=True)
    job.artifacts_dir = str(art_dir)
    ch_dir = art_dir / "chapters"
    ch_dir.mkdir(exist_ok=True)

    progress(2, "Đọc nguồn truyện")
    text = _load_source(params)
    chapters = _split_chapters(text)
    if not chapters:
        raise ValueError("Không tách được chương/phần nào từ nguồn.")
    n = len(chapters)

    # Trạng thái bền theo BỘ TRUYỆN (không theo job) — chạy lại/chạy thêm đều nối tiếp.
    state_path = art_dir / "state.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            state = {}

    # 1) Glossary: dựng 1 lần, user sửa được giữa các lần chạy.
    gloss_path = art_dir / "glossary.json"
    if gloss_path.exists():
        glossary = json.loads(gloss_path.read_text(encoding="utf-8"))
    else:
        progress(5, "Trích glossary tên riêng (1 lần, tầng smart)")
        glossary = _build_glossary(
            "\n\n".join(f"{t}\n{b}" for t, b in chapters[:2]), target
        )
        gloss_path.write_text(
            json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 2) Dịch từng chương — checkpoint + throttle.
    min_gap_s = 60.0 / max(1, settings.novel_rate_limit_rpm)
    tier = settings.novel_llm_tier
    prev_summary = str(state.get("last_summary") or "")
    last_call = 0.0
    done_titles: list[tuple[str, str]] = []

    for i, (ch_title, ch_body) in enumerate(chapters):
        ch_file = ch_dir / f"ch_{i + 1:04d}.md"
        pct = 8 + int(82 * i / n)
        if ch_file.exists():
            done_titles.append((ch_title, str(ch_file)))
            progress(pct, f"Chương {i + 1}/{n}: đã dịch từ trước (checkpoint)")
            # nạp lại tóm tắt đã lưu để chương sau vẫn có bối cảnh
            prev_summary = str(state.get(f"summary_{i + 1}") or prev_summary)
            continue
        if job_queue.is_cancelled(job.id):
            raise JobCancelled()

        wait = min_gap_s - (time.monotonic() - last_call)
        if wait > 0:
            time.sleep(wait)
        progress(pct, f"Chương {i + 1}/{n}: đang dịch ({ch_title[:40]})")
        last_call = time.monotonic()

        vi_title, vi_body, prev_summary = _translate_chapter(
            ch_title, ch_body, target, glossary, prev_summary, tier
        )
        ch_file.write_text(f"# {vi_title}\n\n{vi_body}\n", encoding="utf-8")
        state[f"summary_{i + 1}"] = prev_summary
        state["last_summary"] = prev_summary
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        done_titles.append((ch_title, str(ch_file)))

    # 3) Đóng gói PDF + EPUB từ toàn bộ chương đã dịch.
    progress(92, "Đóng gói PDF + EPUB")
    packaged: list[tuple[str, str]] = []
    for f in sorted(ch_dir.glob("ch_*.md")):
        content = f.read_text(encoding="utf-8")
        first, _, rest = content.partition("\n")
        packaged.append((first.lstrip("# ").strip(), rest.strip()))
    pdfkit.chapters_to_pdf(packaged, art_dir / f"{slug}.pdf", title)
    pdfkit.chapters_to_epub(packaged, art_dir / f"{slug}.epub", title, lang=target)

    # Ghi lại số liệu cho QC.
    (art_dir / "package_info.json").write_text(json.dumps({
        "title": title, "expected_chapters": n,
        "packaged_chapters": len(packaged), "target": target,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(100, f"Xong {len(packaged)}/{n} chương -> {slug}.pdf + .epub")


# ------------------------------------------------------------------------- #
# QC truyện chữ
# ------------------------------------------------------------------------- #
def qc_novel(job: JobRecord) -> QCReport:
    art_dir = Path(job.artifacts_dir)
    checks: list[dict] = []
    ok_all = True

    info = {}
    info_path = art_dir / "package_info.json"
    if info_path.exists():
        info = json.loads(info_path.read_text(encoding="utf-8"))
    expected = int(info.get("expected_chapters") or 0)
    packaged = int(info.get("packaged_chapters") or 0)
    complete = expected > 0 and packaged >= expected
    checks.append({"name": "đủ chương", "ok": complete,
                   "note": f"{packaged}/{expected} chương vào sách"})
    ok_all &= complete

    slug = art_dir.name
    for ext in ("pdf", "epub"):
        f = art_dir / f"{slug}.{ext}"
        good = f.exists() and f.stat().st_size > 10_000
        checks.append({"name": f"file {ext}", "ok": good,
                       "note": f"{f.stat().st_size} bytes" if f.exists() else "thiếu file"})
        ok_all &= good
    if (art_dir / f"{slug}.pdf").exists():
        try:
            from pypdf import PdfReader
            pages = len(PdfReader(str(art_dir / f"{slug}.pdf")).pages)
            checks.append({"name": "pdf mở được", "ok": pages > 0, "note": f"{pages} trang"})
            ok_all &= pages > 0
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": "pdf mở được", "ok": False, "note": str(exc)})
            ok_all = False

    # Glossary: tên NGUỒN không được sót lại chưa dịch trong bản dịch.
    gloss_path = art_dir / "glossary.json"
    if gloss_path.exists():
        glossary = json.loads(gloss_path.read_text(encoding="utf-8"))
        all_vi = " ".join(
            f.read_text(encoding="utf-8") for f in sorted((art_dir / "chapters").glob("ch_*.md"))
        )
        leaked = [src for src in list(glossary)[:40]
                  if len(src) >= 2 and not src.isascii() and src in all_vi]
        gl_ok = len(leaked) <= max(1, len(glossary) // 10)   # cho sót lẻ tẻ <10%
        checks.append({"name": "glossary sạch", "ok": gl_ok,
                       "note": ("sót tên gốc: " + ", ".join(leaked[:5])) if leaked else "không sót tên gốc"})
        ok_all &= gl_ok

    return QCReport(passed=bool(ok_all), checks=checks)


register_checker("novel", qc_novel)


SPEC = ToolSpec(
    name="novel.translate",
    label_vi="Dịch truyện chữ → PDF + EPUB",
    description="Dán truyện (hoặc đường dẫn .txt / URL) — AURA tách chương, chốt "
                 "glossary tên riêng để dịch NHẤT QUÁN cả bộ, dịch từng chương có "
                 "ngữ cảnh, rồi đóng gói PDF + EPUB sẵn bán. Sập máy/hết lượt cloud "
                 "chỉ tạm dừng — chạy lại là dịch tiếp chương dở.",
    product_line="novel",
    form_fields=(
        FormField(key="title", label="Tên truyện (bản dịch)",
                  placeholder="vd: Lý Cẩu Tu Tiên"),
        FormField(key="text", label="Dán nội dung truyện (bỏ trống nếu dùng nguồn dưới)",
                  type="textarea", required=False),
        FormField(key="source", label="Hoặc: đường dẫn file .txt / URL chương truyện",
                  required=False, placeholder=r"D:\truyen\bo1.txt hoặc https://..."),
        FormField(key="target", label="Ngôn ngữ đích", type="select",
                  default="vi", choices=("vi", "en"), required=False),
    ),
    handler=run,
)

__all__ = ["SPEC", "run", "qc_novel"]
