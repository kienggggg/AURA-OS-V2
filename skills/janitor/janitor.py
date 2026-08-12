"""
skills/janitor/janitor.py
=========================
CÔNG NHÂN DỌN RÁC (trash.janitor) — CÔNG NHÂN THỨ BA theo mô hình
"quản gia giao tool cho thợ" (sau job_scout và news.scout).

Phân quyền CỨNG (đã chốt trong thiết kế worker):
  1. CHỈ LUẬT CỨNG mới được dọn file — và dọn = đưa vào RECYCLE BIN (send2trash,
     hoàn tác được), KHÔNG BAO GIỜ xoá vĩnh viễn.
  2. Model nhỏ (công nhân embedding core/embedder.py) CHỈ ĐỀ XUẤT: phân loại file
     cũ trong Downloads theo tên ("bộ cài", "file nén", "tài liệu"...) để Sếp tự
     quyết — không có quyền đụng vào file.
  3. Báo cáo MỘT CHIỀU: ghi data/feedback/janitor_last.json; quản gia/daemon đọc
     khi rảnh.

Luật cứng nhận RÁC (tất cả đều phải CŨ hơn janitor_min_age_days, mặc định 30 ngày):
  - Đuôi rác:  .tmp .temp .dmp .crdownload .partial .part .download .bak .swp/.swo/.swn
  - Tên rác cố định (BleachBit deepscan):  Thumbs.db  .DS_Store  ehthumbs.db
  - File khoá Office bỏ quên:  ~$xxx.docx
  - Backup của editor:  foo.txt~
  - File 0 byte
Vành đai an toàn: không đụng file trong project AURA, bỏ qua symlink/junction,
bỏ file thuộc tính SYSTEM, trần janitor_max_recycle file/lượt, file >2GB chỉ đề xuất.

Mặc định DRY-RUN (apply=False): chỉ báo cáo, không dọn. Daemon truyền apply=True.
"""

from __future__ import annotations

import sys
from pathlib import Path

# skills/janitor/janitor.py -> parents[2] = gốc dự án.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json
import logging
import os
import re
import time

from core.schemas import ToolResult

logger = logging.getLogger("aura.skills.janitor")

# Đuôi rác cứng. Bổ sung từ luật BleachBit deepscan (an toàn, phổ quát): .bak (backup),
# .swp/.swo/.swn (VIM swap). CỐ TÌNH KHÔNG lấy node_modules/venv/__pycache__/.angular
# của BleachBit — đó là artefact dev; janitor chạy NGẦM, đụng vào = phá project đang làm.
_RULE_EXTS = {".tmp", ".temp", ".dmp", ".crdownload", ".partial", ".part", ".download",
              ".bak", ".swp", ".swo", ".swn"}
# Tên file rác CHÍNH XÁC (BleachBit deepscan: Thumbs.db, .DS_Store...). So khớp lowercase.
_JUNK_NAMES = {"thumbs.db", "thumbs.db:encryptable", "ehthumbs.db", ".ds_store"}
_MAX_SCAN_DEPTH = 3            # quét đệ quy tối đa 3 tầng trong thư mục temp
_MAX_SUGGESTIONS = 25          # trần số đề xuất mỗi lượt (đừng ngập báo cáo)
_BIG_FILE_BYTES = 2 * 1024**3  # >2GB: không tự dọn, chỉ đề xuất
_FILE_ATTRIBUTE_SYSTEM = 0x4
_REPORT_PATH = _PROJECT_ROOT / "data" / "feedback" / "janitor_last.json"

# Nhóm phân loại cho MODEL ĐỀ XUẤT (embedding so tên file với mô tả nhóm).
_CATEGORIES: dict[str, str] = {
    "installer": "bộ cài đặt phần mềm setup installer",
    "archive": "file nén lưu trữ zip rar archive compressed",
    "document": "tài liệu văn bản báo cáo document report giáo án bài giảng",
    "media": "ảnh video nhạc hình chụp màn hình photo screenshot",
    "code": "mã nguồn source code script chương trình",
}
_CATEGORY_HINT: dict[str, str] = {
    "installer": "cài xong rồi thì xoá được",
    "archive": "đã giải nén thì xoá được",
    "document": "nên xếp vào thư mục tài liệu",
    "media": "nên xếp vào thư mục ảnh/video",
    "code": "nên xếp vào thư mục dự án",
    "unknown": "Sếp tự xem giúp em",
}
_EMBED_MIN_COS = 0.25          # cosine thấp hơn -> chịu, xếp 'unknown'


# --------------------------------------------------------------------------- #
# Thư mục quét (đọc lười từ config, có mặc định an toàn)
# --------------------------------------------------------------------------- #
def _settings():
    try:
        from core.config import settings
        return settings
    except Exception:  # noqa: BLE001
        return None


def _csv_dirs(val) -> list[Path]:
    return [Path(p.strip()).expanduser() for p in str(val or "").split(",") if p.strip()]


def _rule_dirs() -> list[Path]:
    st = _settings()
    dirs = _csv_dirs(getattr(st, "janitor_rule_dirs", None)) if st else []
    if not dirs:
        import tempfile
        dirs = [Path(tempfile.gettempdir())]
    return dirs


def _suggest_dirs() -> list[Path]:
    st = _settings()
    dirs = _csv_dirs(getattr(st, "janitor_suggest_dirs", None)) if st else []
    if not dirs:
        dirs = [Path.home() / "Downloads"]
    return dirs


# --------------------------------------------------------------------------- #
# Vành đai an toàn
# --------------------------------------------------------------------------- #
def _is_protected(p: Path) -> bool:
    """File KHÔNG được đụng: nằm trong project AURA, symlink/junction, file SYSTEM."""
    try:
        if p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()):
            return True
        if _PROJECT_ROOT in p.resolve().parents:
            return True
        attrs = getattr(p.stat(follow_symlinks=False), "st_file_attributes", 0)
        if attrs & _FILE_ATTRIBUTE_SYSTEM:
            return True
    except OSError:
        return True     # đọc không nổi metadata -> coi như cấm, an toàn trước
    return False


def _age_days(p: Path) -> float:
    try:
        return (time.time() - p.stat(follow_symlinks=False).st_mtime) / 86400.0
    except OSError:
        return -1.0     # không đọc được -> coi như mới, không đụng


def _is_rule_junk(p: Path, min_age_days: float) -> bool:
    """Luật cứng (mở rộng từ BleachBit deepscan): đuôi rác / tên rác cố định /
    file khoá Office / backup editor '~' / 0 byte — và phải ĐỦ CŨ."""
    age = _age_days(p)
    if age < min_age_days:
        return False
    if p.suffix.lower() in _RULE_EXTS:
        return True
    if p.name.lower() in _JUNK_NAMES:              # Thumbs.db, .DS_Store...
        return True
    if p.name.startswith("~$"):                    # file khoá Office (~$baocao.docx)
        return True
    if len(p.name) > 1 and p.name.endswith("~"):   # backup editor (foo.txt~, gedit/emacs)
        return True
    try:
        if p.stat(follow_symlinks=False).st_size == 0:
            return True
    except OSError:
        return False
    return False


# --------------------------------------------------------------------------- #
# Quét (tool do CODE cầm — model không điều khiển gì ở đây)
# --------------------------------------------------------------------------- #
def _walk_files(root: Path, max_depth: int) -> list[Path]:
    """Duyệt file trong root tới max_depth tầng, bỏ symlink/junction. Lỗi -> bỏ qua."""
    out: list[Path] = []
    base_depth = len(root.parts)
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            d = Path(dirpath)
            if len(d.parts) - base_depth >= max_depth:
                dirnames.clear()        # đủ sâu -> không xuống nữa
            dirnames[:] = [n for n in dirnames if not (d / n).is_symlink()]
            for name in filenames:
                out.append(d / name)
    except OSError as exc:
        logger.warning("Duyệt %s lỗi (bỏ qua phần còn lại): %s", root, exc)
    return out


def _scan_rule_junk(min_age_days: float) -> list[Path]:
    junk: list[Path] = []
    for root in _rule_dirs():
        if not root.is_dir():
            continue
        for p in _walk_files(root, _MAX_SCAN_DEPTH):
            if not _is_protected(p) and _is_rule_junk(p, min_age_days):
                junk.append(p)
    return junk


# --------------------------------------------------------------------------- #
# Model ĐỀ XUẤT (không có quyền dọn): phân loại file cũ trong Downloads theo tên
# --------------------------------------------------------------------------- #
def _name_tokens(p: Path) -> str:
    """Tên file -> chuỗi từ cho model: tách [-_.], bỏ token toàn số/hex dài vô nghĩa."""
    toks = [t for t in re.split(r"[-_.\s]+", p.stem)
            if t and not re.fullmatch(r"[0-9a-fA-F]{6,}|\d+", t)]
    ext = p.suffix.lstrip(".").lower()
    return " ".join(toks + ([ext] if ext else [])) or p.name


def _classify_suggestions(files: list[Path]) -> list[dict]:
    """Công nhân embedding phân loại tên file -> nhóm + gợi ý. Hỏng -> unknown hết."""
    if not files:
        return []
    cats = list(_CATEGORIES.keys())
    labels = [None] * len(files)
    confs = [0.0] * len(files)
    try:
        from core.embedder import get_worker
        worker = get_worker()
        f_emb = worker.embed([_name_tokens(p) for p in files])
        c_emb = worker.embed(list(_CATEGORIES.values()))
        sims = c_emb @ f_emb.T                      # (nhóm, file)
        best = sims.argmax(axis=0)
        for i in range(len(files)):
            cos = float(sims[best[i], i])
            if cos >= _EMBED_MIN_COS:
                labels[i] = cats[int(best[i])]
                confs[i] = round(cos, 3)
    except Exception as exc:  # noqa: BLE001 — model hỏng thì mọi file thành 'unknown'
        logger.warning("Công nhân embedding phân loại lỗi (unknown hết): %s", exc)
    out = []
    for p, lab, conf in zip(files, labels, confs):
        cat = lab or "unknown"
        out.append({
            "name": p.name, "dir": str(p.parent), "category": cat, "conf": conf,
            "age_days": round(_age_days(p), 1),
            "size_mb": round(p.stat(follow_symlinks=False).st_size / 1024**2, 2),
            "hint": _CATEGORY_HINT[cat],
        })
    return out


def _scan_suggestions(min_age_days: float, already_junk: set[Path]) -> list[dict]:
    cands: list[Path] = []
    for root in _suggest_dirs():
        if not root.is_dir():
            continue
        try:
            for p in sorted(root.iterdir()):
                if (p.is_file() and p not in already_junk and not _is_protected(p)
                        and _age_days(p) >= min_age_days):
                    cands.append(p)
        except OSError as exc:
            logger.warning("Quét đề xuất %s lỗi (bỏ qua): %s", root, exc)
    # File to/cũ nhất lên đầu — đáng dọn nhất; cắt trần cho gọn báo cáo.
    cands.sort(key=lambda p: -(p.stat(follow_symlinks=False).st_size if p.exists() else 0))
    return _classify_suggestions(cands[:_MAX_SUGGESTIONS])


# --------------------------------------------------------------------------- #
# Dọn (chỉ luật cứng, chỉ Recycle Bin, chỉ khi apply=True)
# --------------------------------------------------------------------------- #
def _recycle(files: list[Path], cap: int) -> tuple[int, int, list[str]]:
    """Đưa file vào Recycle Bin. Trả (số dọn được, số lỗi, mẫu tên đã dọn)."""
    from send2trash import send2trash
    done = failed = 0
    samples: list[str] = []
    for p in files[:cap]:
        try:
            if p.stat(follow_symlinks=False).st_size > _BIG_FILE_BYTES:
                continue                      # file khổng lồ: không tự dọn
            send2trash(str(p))
            done += 1
            if len(samples) < 8:
                samples.append(p.name)
        except Exception as exc:  # noqa: BLE001 — file khoá/đang dùng: bỏ qua, đi tiếp
            failed += 1
            logger.info("Không dọn được %s (bỏ qua): %s", p, exc)
    return done, failed, samples


# --------------------------------------------------------------------------- #
# Tool công khai cho Registry
# --------------------------------------------------------------------------- #
def tool_janitor(
    apply: bool = False,
    min_age_days: float | None = None,
    as_json: bool = False,
) -> ToolResult:
    """Tool 'trash.janitor': quét rác theo luật + đề xuất phân loại. Luôn trả ToolResult."""
    st = _settings()
    age = float(min_age_days if min_age_days is not None
                else (getattr(st, "janitor_min_age_days", 30.0) if st else 30.0))
    cap = int(getattr(st, "janitor_max_recycle", 200)) if st else 200

    try:
        junk = _scan_rule_junk(age)
        junk_size_mb = 0.0
        for p in junk:
            try:
                junk_size_mb += p.stat(follow_symlinks=False).st_size / 1024**2
            except OSError:
                pass

        recycled = failed = 0
        samples: list[str] = []
        if apply and junk:
            recycled, failed, samples = _recycle(junk, cap)

        suggestions = _scan_suggestions(age, set(junk))

        data = {
            "ts": int(time.time()),
            "apply": bool(apply),
            "min_age_days": age,
            "rule_junk_found": len(junk),
            "rule_junk_size_mb": round(junk_size_mb, 1),
            "recycled": recycled,
            "recycle_failed": failed,
            "recycled_samples": samples,
            "suggestions": suggestions,
        }
        try:
            _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            _REPORT_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError as exc:
            logger.warning("Ghi báo cáo janitor lỗi (bỏ qua): %s", exc)

        output = json.dumps(data, ensure_ascii=False, indent=2) if as_json else _render(data)
        return ToolResult.success("trash.janitor", output=output)
    except Exception as exc:  # noqa: BLE001 — vành đai cuối
        return ToolResult.failure("trash.janitor", f"Lỗi dọn rác: {exc}")
    finally:
        # Công nhân xong ca thì nhả RAM.
        try:
            from core.embedder import get_worker
            get_worker().unload()
        except Exception:  # noqa: BLE001
            pass


def _render(data: dict) -> str:
    mode = "ĐÃ DỌN" if data["apply"] else "DRY-RUN (chỉ báo cáo)"
    lines = [
        "# 🧹 Janitor — công nhân dọn rác",
        f"Rác theo luật: **{data['rule_junk_found']}** file "
        f"(~{data['rule_junk_size_mb']}MB, cũ hơn {data['min_age_days']:.0f} ngày) · {mode}.",
    ]
    if data["apply"]:
        lines.append(f"Đã đưa vào Recycle Bin: **{data['recycled']}** file"
                     + (f" (lỗi/đang dùng: {data['recycle_failed']})" if data["recycle_failed"] else "")
                     + ".")
        if data["recycled_samples"]:
            lines.append("Ví dụ: " + ", ".join(data["recycled_samples"]))
    if data["suggestions"]:
        lines.append(f"\nĐỀ XUẤT của model (KHÔNG tự dọn, {len(data['suggestions'])} file cũ trong Downloads):")
        for s in data["suggestions"][:10]:
            lines.append(f"- [{s['category']}] {s['name']} ({s['size_mb']}MB, {s['age_days']:.0f} ngày)"
                         f" — {s['hint']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI độc lập (Level 4)
# --------------------------------------------------------------------------- #
def _main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="AURA skill trash.janitor — công nhân dọn rác.")
    ap.add_argument("--apply", action="store_true",
                    help="THẬT SỰ dọn (vào Recycle Bin). Mặc định dry-run.")
    ap.add_argument("--min-age-days", type=float, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    result = tool_janitor(apply=args.apply, min_age_days=args.min_age_days, as_json=args.json)
    print(result.output if result.ok else f"[LỖI] {result.error}")
    return 0 if result.ok else 1


__all__ = ["tool_janitor"]


if __name__ == "__main__":
    raise SystemExit(_main())
