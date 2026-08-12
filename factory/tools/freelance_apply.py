"""
factory/tools/freelance_apply.py
=================================
freelance.apply — BỘ HỒ SƠ ỨNG TUYỂN cho 1 tin việc (ý từ ai-job-search):
chấm độ hợp kiểu ATS + kỹ năng khớp/thiếu + pitch may đo + mock phỏng vấn.

Máy lo phần nhàm (phân tích + soạn nháp); Sếp lo phần quyết (sửa + TỰ gửi).
KHÔNG tự gửi đơn. Chống bịa NGHIÊM: chỉ dùng dữ kiện trong freelance_profile —
bài học cũ: cloud từng gán kỹ năng AURA không có.

Ra 1 file markdown data/outputs/freelance/<job>/ung_tuyen.md + ghi sổ
applications.jsonl. product_line 'freelance' (QC pass-through).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from core.config import settings
from core.work_for_hire import create_draft, is_listing_url
from factory.models import FormField, JobRecord, ToolSpec

_LEDGER = settings.ledger_dir / "applications.jsonl"


def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE).strip("_")
    return s[:max_len] or "job"


def _fetch_detail(url: str) -> str:
    """Kéo mô tả tin qua Jina reader (best-effort)."""
    try:
        from skills.scouts.job_scout import _fetch_jina
        md = _fetch_jina(url)
        if md and "403" not in md[:200]:
            return re.sub(r"\s+", " ", md)[:2500]
    except Exception:  # noqa: BLE001
        pass
    return ""


def _analyze(job: str, profile: str, lang: str) -> dict:
    """LLM 1 call: chấm hợp + khớp/thiếu kỹ năng + pitch + advice + mock phỏng vấn."""
    from core.llm import CloudEngine
    if lang == "en":
        system = (
            "You are an ATS-savvy job coach. Applicant profile is the ONLY source of "
            "truth about the applicant: " + profile + ". STRICT: never invent skills or "
            "experience the profile doesn't state. Analyze the job vs the profile. "
            "Return PURE JSON:\n"
            "{\"fit_score\": <0-100 int>, \"matched\": [\"skills in BOTH job and "
            "profile\"], \"missing\": [\"skills the job wants but profile lacks\"], "
            "\"pitch\": \"110-150 word tailored application, [brackets] for name/rate/"
            "portfolio, no empty adjectives\", \"advice\": \"2-3 sentences: how to "
            "position, honest note if fit is weak\", \"interview\": [{\"q\": \"likely "
            "interview question\", \"a\": \"suggested answer grounded ONLY in profile\"}]}"
            " Give 5 interview items."
        )
    else:
        system = (
            "Bạn là cố vấn tuyển dụng rành ATS. Hồ sơ ứng viên là NGUỒN SỰ THẬT DUY "
            "NHẤT: " + profile + ". NGHIÊM: không bịa kỹ năng/kinh nghiệm ngoài hồ sơ. "
            "Phân tích tin việc so với hồ sơ. Trả JSON THUẦN:\n"
            "{\"fit_score\": <số nguyên 0-100>, \"matched\": [\"kỹ năng CÓ ở CẢ tin "
            "lẫn hồ sơ\"], \"missing\": [\"kỹ năng tin đòi mà hồ sơ chưa có\"], "
            "\"pitch\": \"thư ứng tuyển may đo 120-170 từ, chừa [chỗ điền] tên/giá/"
            "portfolio, không sáo rỗng\", \"advice\": \"2-3 câu: nên định vị thế nào, "
            "nói thẳng nếu độ hợp thấp\", \"interview\": [{\"q\": \"câu phỏng vấn dễ "
            "gặp\", \"a\": \"gợi ý trả lời CHỈ dựa trên hồ sơ\"}]} Cho 5 câu phỏng vấn."
        )
    res = CloudEngine().complete(
        [{"role": "user", "content": f"Tin việc:\n{job[:3000]}"}],
        system_prompt=system, temperature=0.5, max_tokens=2500, tier="smart",
    )
    if not res.get("ok"):
        raise RuntimeError(f"Phân tích lỗi: {res.get('error')}")
    m = re.search(r"\{.*\}", str(res["text"]), re.DOTALL)
    if not m:
        raise RuntimeError("Phân tích không trả JSON.")
    return json.loads(m.group(0))


def _render_md(title: str, url: str, data: dict, lang: str, demo_info: dict | None = None) -> str:
    fit = int(data.get("fit_score") or 0)
    bar = "🟢 hợp tốt" if fit >= 70 else "🟡 cân nhắc" if fit >= 45 else "🔴 hợp thấp"
    matched = data.get("matched") or []
    missing = data.get("missing") or []
    iv = data.get("interview") or []
    L = (lang == "en")
    parts = [
        f"# {'Application kit' if L else 'Bộ hồ sơ ứng tuyển'}: {title}",
        (f"*Nguồn: {url}*" if url else ""),
        f"\n## {'Fit' if L else 'Độ hợp'}: **{fit}/100** — {bar}",
        f"\n**{'Matched skills' if L else 'Kỹ năng KHỚP'}:** "
        + (", ".join(map(str, matched)) or "—"),
        f"\n**{'Missing/needs work' if L else 'Kỹ năng THIẾU'}:** "
        + (", ".join(map(str, missing)) or "—"),
        f"\n## {'Tailored pitch' if L else 'Thư ứng tuyển (may đo)'}\n"
        + str(data.get("pitch") or ""),
    ]

    if demo_info and demo_info.get("filename"):
        fn = demo_info["filename"]
        pv = demo_info.get("preview_text", "")
        parts.append(
            f"\n## ⚡ {'Working Demo Output (AURA Generated)' if L else 'Sản phẩm mẫu tự động (AURA Demo)'}\n"
            f"- **File:** `{fn}`\n"
            f"```\n{pv}\n```\n"
            f"*(AURA generated this sample proof of work to attach directly into client proposal)*"
        )

    parts.extend([
        f"\n## {'Positioning advice' if L else 'Lời khuyên định vị'}\n"
        + str(data.get("advice") or ""),
        f"\n## {'Mock interview' if L else 'Luyện phỏng vấn'}",
    ])
    for i, qa in enumerate(iv, 1):
        parts.append(f"\n**{i}. {qa.get('q', '')}**\n> {qa.get('a', '')}")
    parts.append(f"\n---\n*{'AURA drafted + generated demo — review then confirm via Telegram.' if L else 'AURA đã tạo bộ hồ sơ + Demo thật — Sếp duyệt qua Telegram để nộp.'}*")
    return "\n".join(p for p in parts if p)


def run(job: JobRecord, progress) -> None:
    params = job.params
    text = str(params.get("job") or "").strip()
    url = str(params.get("url") or "").strip()
    title = (str(params.get("title") or "").strip()
             or (text.split("\n")[0][:80] if text else "") or "Tin việc")
    # Tin do scout tự tìm phải có URL thật. Không dựng portfolio/deliverable từ
    # tiêu đề rỗng hoặc bài báo tổng hợp rồi khiến Sếp tưởng là cơ hội có thể nộp.
    if params.get("_auto") and not is_listing_url(url):
        raise ValueError("Bỏ qua tin tự động không có URL ứng tuyển HTTP(S) thật.")

    source_verified = False
    if url:
        progress(15, "Kéo mô tả tin việc")
        fetched = _fetch_detail(url)
        if len(fetched) >= 200:
            text = fetched
            source_verified = True
        elif params.get("_auto"):
            raise RuntimeError("Không xác minh được nội dung tin tự động; không soạn hồ sơ từ snippet.")
    if not text:
        raise ValueError("Cần dán mô tả tin việc ('job') hoặc URL kéo được nội dung.")

    profile = str(getattr(settings, "freelance_profile", "") or "").strip()
    if not profile:
        raise ValueError("Chưa có freelance_profile trong config để soạn hồ sơ.")

    lang = str(params.get("lang") or "auto")
    if lang == "auto":
        from skills.scouts.job_scout import _detect_pitch_lang
        lang = _detect_pitch_lang(title, url, text)

    progress(45, "Chấm độ hợp + may đo pitch + soạn phỏng vấn (tầng smart)")
    data = _analyze(text, profile, lang)

    art_dir = settings.outputs_dir / "freelance" / _slug(title)
    art_dir.mkdir(parents=True, exist_ok=True)
    job.artifacts_dir = str(art_dir)

    fit_score = int(data.get("fit_score") or 0)
    min_fit = int(getattr(settings, "work_for_hire_min_fit", 75))

    # Chỉ làm demo cho một tin thật, đủ hợp. Demo cho tin mơ hồ/hợp thấp chỉ
    # tạo thêm rác và làm Sếp phân tán khỏi cơ hội có khả năng ký được việc.
    demo_info = None
    if (
        fit_score >= min_fit
        and source_verified
        and getattr(settings, "freelance_auto_demo_enabled", True)
    ):
        try:
            progress(75, "Tự động tạo sản phẩm mẫu (Auto-Demo)")
            from core.auto_demo import generate_sample_demo
            demo_info = generate_sample_demo(title, text, art_dir)
        except Exception as exc:  # noqa: BLE001
            pass

    md = art_dir / "ung_tuyen.md"
    md.write_text(_render_md(title, url, data, lang, demo_info), encoding="utf-8")
    (art_dir / "package_info.json").write_text(json.dumps({
        "title": title, "url": url, "fit_score": fit_score,
        "lang": lang, "output": str(md), "demo_info": demo_info,
        "source_verified": source_verified,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # Một nguồn sự thật cho toàn bộ phễu kiếm tiền. Cơ hội chỉ đi tới hàng
    # ‘Sếp duyệt’ khi URL đã xác minh và điểm hợp đủ cao.
    deal = create_draft(
        title=title,
        url=url,
        fit_score=fit_score,
        artifact=str(md),
        source_verified=source_verified,
        origin="scout" if params.get("_auto") else "manual",
        notes="AURA soạn pitch; người thật tự nộp hồ sơ.",
    )

    # Ghi sổ ứng tuyển (audit — chưa gửi, trạng thái 'drafted').
    _LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with _LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({

            "ts": int(time.time()), "title": title, "url": url,
            "fit_score": fit_score, "status": deal["status"],
            "file": str(md), "deal_id": deal["id"],
        }, ensure_ascii=False) + "\n")
    # Gom chỉ mục VIỆC_HÔM_NAY.md — 1 file duy nhất Sếp mở là thấy mọi hồ sơ đã
    # soạn sẵn (xếp theo độ hợp), diệt ma sát "phải nhấn từng link".
    try:
        _write_today_index()
        # Job do scout TỰ soạn -> BẬT file lên màn hình luôn (Sếp tự nhận là hay
        # lười + không để ý; cửa sổ Notepad giữa desktop thì không thể không thấy).
        if params.get("_auto"):
            import os
            os.startfile(str(settings.outputs_dir / "freelance" / "VIỆC_HÔM_NAY.md"))  # noqa: S606
    except Exception:  # noqa: BLE001 — chỉ mục/bật file hỏng không hỏng job
        pass
    progress(100, f"Xong — độ hợp {fit_score}/100, pipeline: {deal['status']}")


def _write_today_index(days: int = 14) -> None:
    import time as _t
    rows = []
    cutoff = _t.time() - days * 86400
    if _LEDGER.exists():
        for ln in _LEDGER.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if d.get("status") == "drafted" and float(d.get("ts") or 0) >= cutoff:
                rows.append(d)
    # mới ghi đè cũ theo url; xếp độ hợp giảm dần
    dedup: dict = {}
    for d in rows:
        dedup[d.get("url") or d.get("title")] = d
    rows = sorted(dedup.values(), key=lambda d: int(d.get("fit_score") or 0), reverse=True)
    out = settings.outputs_dir / "freelance" / "VIỆC_HÔM_NAY.md"
    lines = [
        "# 🎯 VIỆC HÔM NAY — hồ sơ AURA ĐÃ SOẠN SẴN",
        "*Mỗi dòng: mở file → sửa [chỗ trống] (tên/giá/link) → copy pitch → GỬI. "
        "Không phải đọc tin gốc, không phải tự viết gì.*\n",
    ]
    for d in rows:
        fit = int(d.get("fit_score") or 0)
        dot = "🟢" if fit >= 70 else "🟡" if fit >= 45 else "🔴"
        lines.append(f"- [ ] {dot} **{fit}/100** — {d.get('title','?')}\n"
                     f"      Hồ sơ: `{d.get('file','')}`\n"
                     f"      Tin gốc: {d.get('url','')}")
    if not rows:
        lines.append("(chưa có hồ sơ nào trong 14 ngày — scout sẽ tự soạn khi thấy việc hợp)")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


SPEC = ToolSpec(
    name="freelance.apply",
    label_vi="Bộ hồ sơ ứng tuyển (chấm hợp + pitch + phỏng vấn)",
    description="Dán mô tả tin việc (hoặc URL) — AURA chấm độ hợp kiểu ATS (kỹ năng "
                 "khớp/thiếu), may đo thư ứng tuyển theo hồ sơ của Sếp, và soạn 5 câu "
                 "luyện phỏng vấn kèm gợi ý trả lời. KHÔNG tự gửi — Sếp sửa rồi tự nộp. "
                 "Chỉ dùng dữ kiện trong freelance_profile (không bịa).",
    product_line="freelance",
    form_fields=(
        FormField(key="job", label="Mô tả tin việc (dán vào)", type="textarea",
                  required=False),
        FormField(key="url", label="… hoặc URL tin việc", required=False),
        FormField(key="title", label="Tên vị trí (tuỳ chọn)", required=False),
        FormField(key="lang", label="Ngôn ngữ", type="select", default="auto",
                  choices=("auto", "vi", "en"), required=False),
    ),
    handler=run,
    experimental=True,
)

__all__ = ["SPEC", "run"]
