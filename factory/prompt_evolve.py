"""
factory/prompt_evolve.py
========================
RÈN PROMPT VIẾT TRUYỆN — cách AURA viết hay lên mà **KHÔNG đụng trọng số model**
(nguyên lý SkillOpt, nhưng làm gọn bằng đúng đồ AURA đã có: QC + sổ bài học).

Vòng lặp mỗi lượt rèn:
  1. Lấy prompt ĐANG DÙNG làm mốc (baseline).
  2. Nhờ cloud đề xuất BẢN CẢI TIẾN — có nhồi `reflexion.lessons_prompt('story')`
     (những lỗi AURA đã từng bị QC bắt) để sửa đúng chỗ yếu thật.
  3. Cho MỖI bản viết THỬ một đoạn mở chương từ CÙNG một đề bài.
  4. Chấm bằng GIÁM KHẢO LLM theo thang điểm rõ ràng (hook/show-don't-tell/nhịp/
     tự nhiên/không sáo rỗng), 0-10.
  5. **CỔNG KIỂM ĐỊNH**: chỉ khi bản mới hơn mốc ≥ `margin` mới được ghi vào
     hàng chờ (staged). KHÔNG tự áp — Sếp gật thì mới `adopt()`.

Chi phí: ~4-6 lượt gọi cloud mỗi lần rèn (rẻ hơn nhiều so với giàn skillopt-train).

Dùng:
    venv/Scripts/python.exe -m factory.prompt_evolve --evolve
    venv/Scripts/python.exe -m factory.prompt_evolve --status
    venv/Scripts/python.exe -m factory.prompt_evolve --adopt
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

from core.config import settings

logger = logging.getLogger(__name__)

_DIR = settings.factory_dir / "prompts"
ACTIVE = _DIR / "story_chapter.txt"          # bản đang dùng (Sếp đã duyệt)
STAGED = _DIR / "story_chapter.staged.txt"   # bản chờ duyệt
LOG = _DIR / "evolve_log.jsonl"

# Đề bài thử — CỐ ĐỊNH để so sánh công bằng giữa các bản prompt.
_TEST_BRIEF = (
    "Bối cảnh: đô thị tương lai mục nát, nhân vật chính vừa tỉnh dậy trong thân xác "
    "một kẻ dưới đáy xã hội, bị hai tên côn đồ dồn vào ngõ cụt. "
    "Viết ĐOẠN MỞ CHƯƠNG khoảng 320 từ."
)

_RUBRIC = (
    "Chấm đoạn văn theo thang 0-10 cho từng tiêu chí:\n"
    "1. HOOK: 30 giây đầu có giữ chân độc giả không (mở giữa hành động, không thuyết minh dài).\n"
    "2. SHOW-DON'T-TELL: tả bằng giác quan, chi tiết ĐẮT, không tường thuật suông, "
    "không chồng 3-5 lớp tả gây bội thực.\n"
    "3. NHỊP: có khoảng lặng xen hành động, câu có lực, không lê thê.\n"
    "4. TỰ NHIÊN: tiếng Việt mượt, không dịch máy, không lạm dụng 'như một/giống như'.\n"
    "5. KHÔNG SÁO RỖNG: tránh cụm AI mòn ('mang theo bí ẩn', 'áp lực vô hình', "
    "'thay đổi số phận'...).\n"
    'CHỈ trả JSON: {"hook":x,"show":x,"nhip":x,"tunhien":x,"saorong":x,"tong":x,"nhanxet":"..."} '
    "với tong = trung bình 5 tiêu chí."
)


def _cloud():
    from core.llm import build_engines
    return build_engines()[1]


def _ask(system: str, user: str, max_tokens: int = 1400) -> str:
    eng = _cloud()
    if eng is None:
        raise RuntimeError("Chưa cấu hình cloud brain.")
    r = eng.complete([{"role": "user", "content": user}],
                     system_prompt=system, max_tokens=max_tokens)
    if not r.get("ok"):
        raise RuntimeError(f"Cloud lỗi: {r.get('error')}")
    return (r.get("text") or "").strip()


def current_prompt() -> str:
    """Prompt đang dùng: bản đã duyệt, không có thì lấy bản mặc định trong code."""
    if ACTIVE.is_file():
        return ACTIVE.read_text(encoding="utf-8").strip()
    from factory.tools import story_factory as sf
    import inspect
    src = inspect.getsource(sf._write_chapter)
    m = re.search(r'system = \(\s*(.*?)\n    \)', src, re.S)
    if not m:
        return ""
    # Nguồn là chuỗi Python nối nhiều mảnh -> gom nội dung trong dấu nháy lại
    # thành VĂN BẢN THẬT (bỏ f-string marker, giải escape) cho LLM đọc đúng.
    raw = m.group(1)
    parts = re.findall(r'(?:f?)"((?:[^"\\]|\\.)*)"', raw)
    text = "".join(parts)
    text = (text.replace("\\n", "\n").replace('\\"', '"')
                .replace("\\'", "'").replace("\\\\", "\\"))
    # Giữ chỗ cho tham số động để lúc dùng thay lại được.
    text = re.sub(r"\{int\(words \* [\d.]+\)\}", "{words_target}", text)
    text = text.replace("{words}", "{words}").replace("{chap_num}", "{chap_num}")
    return text.strip()


def _propose(base: str) -> str:
    """Nhờ cloud viết BẢN CẢI TIẾN của prompt, dựa trên lỗi QC đã từng mắc."""
    from factory import reflexion
    lessons = reflexion.lessons_prompt("story") or "(chưa có bài học nào)"
    system = (
        "Bạn là chuyên gia PROMPT ENGINEERING cho viết truyện mạng tiếng Việt. "
        "Nhiệm vụ: viết lại BẢN HƯỚNG DẪN (system prompt) cho AI viết chương truyện "
        "sao cho chương viết ra HAY HƠN. Giữ mọi ràng buộc kỹ thuật quan trọng "
        "(độ dài tối thiểu, định dạng trả về, bám bible/canon). Được phép cô đọng, "
        "sắp xếp lại, bỏ luật trùng lặp, thêm luật khắc phục lỗi hay mắc. "
        "CHỈ trả về nội dung prompt mới, KHÔNG giải thích."
    )
    user = (
        f"=== PROMPT HIỆN TẠI ===\n{base}\n\n"
        f"=== LỖI AURA HAY BỊ QC BẮT ===\n{lessons}\n\n"
        "Viết BẢN PROMPT MỚI tốt hơn."
    )
    return _ask(system, user, max_tokens=2200)


_MIN_SAMPLE = 600   # dưới ngần này ký tự coi như lượt viết HỎNG, không đem chấm


def _sample(prompt: str) -> str:
    """Viết thử đoạn mở chương bằng prompt đang xét.
    PHẢI thay hết chỗ trống ({words}/{chap_num}) — để nguyên thì model đọc được
    chữ '{words}' và viết hỏng (đã mắc: mẫu chỉ ra 83 ký tự)."""
    p = (prompt.replace("{words}", "320").replace("{words_target}", "420")
               .replace("{chap_num}", "1"))
    return _ask(p, _TEST_BRIEF, max_tokens=8000)


def _judge(text: str) -> dict:
    """Giám khảo LLM chấm đoạn văn theo rubric -> dict điểm."""
    if len(text.strip()) < _MIN_SAMPLE:
        return {"tong": None, "nhanxet": f"mẫu quá ngắn ({len(text)} ký tự) — bỏ lượt"}
    out = _ask("Bạn là biên tập viên truyện mạng khó tính, chấm điểm khách quan.",
               f"{_RUBRIC}\n\n=== ĐOẠN VĂN ===\n{text}", max_tokens=4000)
    out = re.sub(r"^```(?:json)?|```$", "", out.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return {"tong": None, "nhanxet": "không đọc được điểm"}
    try:
        d = json.loads(m.group(0))
        d["tong"] = float(d.get("tong") or 0)
        return d
    except Exception:  # noqa: BLE001
        return {"tong": None, "nhanxet": "JSON hỏng"}


def evolve(margin: float = 0.3) -> str:
    """Một lượt rèn. Chỉ ghi vào hàng chờ nếu bản mới HƠN mốc >= margin."""
    _DIR.mkdir(parents=True, exist_ok=True)
    base = current_prompt()
    if not base:
        return "⚠️ Không lấy được prompt hiện tại."
    try:
        base_txt = _sample(base)
        base_sc = _judge(base_txt)
        cand = _propose(base)
        cand_txt = _sample(cand)
        cand_sc = _judge(cand_txt)
    except Exception as exc:  # noqa: BLE001
        return f"⚠️ Rèn prompt lỗi: {exc}"

    # CHẤM HỎNG (None) thì BỎ LƯỢT — tuyệt đối không so với số rác rồi tưởng thắng.
    if base_sc.get("tong") is None or cand_sc.get("tong") is None:
        return ("⚠️ Lượt rèn KHÔNG hợp lệ (chấm hỏng: "
                f"mốc={base_sc.get('nhanxet','?')[:60]} | "
                f"mới={cand_sc.get('nhanxet','?')[:60]}). Bỏ lượt, không đổi gì.")
    b, c = float(base_sc["tong"]), float(cand_sc["tong"])
    rec = {"ts": time.time(), "base": b, "cand": c, "margin": margin,
           "nhan_xet_moi": cand_sc.get("nhanxet", "")[:300]}
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass

    if c >= b + margin:
        STAGED.write_text(cand, encoding="utf-8")
        return (f"🧠 RÈN ĐƯỢC BẢN TỐT HƠN: {b:.1f} → {c:.1f} (+{c-b:.1f}).\n"
                f"Nhận xét: {cand_sc.get('nhanxet','')[:200]}\n"
                "Đã để vào hàng chờ — Sếp gật thì em áp (lệnh /apdungvan).")
    return (f"➖ Chưa hơn được bản cũ ({b:.1f} → {c:.1f}, cần +{margin}). "
            "Giữ nguyên prompt cũ — không đổi gì.")


def adopt() -> str:
    """Áp bản đang chờ thành bản đang dùng (Sếp đã duyệt)."""
    if not STAGED.is_file():
        return "📭 Không có bản nào đang chờ duyệt."
    _DIR.mkdir(parents=True, exist_ok=True)
    if ACTIVE.is_file():
        bak = _DIR / f"story_chapter.bak.{int(time.time())}.txt"
        bak.write_text(ACTIVE.read_text(encoding="utf-8"), encoding="utf-8")
    ACTIVE.write_text(STAGED.read_text(encoding="utf-8"), encoding="utf-8")
    STAGED.unlink(missing_ok=True)
    return ("✅ Đã áp bản prompt mới — từ chương sau AURA viết theo bản này. "
            "(Bản cũ đã lưu dự phòng, muốn quay lại thì bảo em.)")


def status() -> str:
    lines = [f"Prompt đang dùng: {'bản đã duyệt' if ACTIVE.is_file() else 'bản mặc định trong code'}"]
    lines.append(f"Đang chờ duyệt: {'CÓ' if STAGED.is_file() else 'không'}")
    if LOG.is_file():
        try:
            rows = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
            lines.append(f"Số lượt đã rèn: {len(rows)}")
            if rows:
                r = rows[-1]
                lines.append(f"Lần gần nhất: {r.get('base'):.1f} → {r.get('cand'):.1f}")
        except Exception:  # noqa: BLE001
            pass
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Rèn prompt viết truyện của AURA")
    ap.add_argument("--evolve", action="store_true", help="Chạy 1 lượt rèn")
    ap.add_argument("--adopt", action="store_true", help="Áp bản đang chờ")
    ap.add_argument("--status", action="store_true", help="Xem trạng thái")
    ap.add_argument("--margin", type=float, default=0.3, help="Mức hơn tối thiểu")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if args.evolve:
        print(evolve(args.margin)); return 0
    if args.adopt:
        print(adopt()); return 0
    print(status()); return 0


if __name__ == "__main__":
    sys.exit(main())
