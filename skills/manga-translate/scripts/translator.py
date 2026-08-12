"""
skills/manga-translate/scripts/translator.py
============================================
ComicTranslator — "Đôi mắt + Cái mồm" dịch truyện, chạy LOCAL hoàn toàn (Level 4).

Ngữ cảnh ở ../SKILL.md; file này chỉ chứa code thực thi, registry nạp TRỄ qua importlib.
  - easyocr        : bóc text ngoại ngữ + toạ độ box, chạy local (CPU được).
  - deep-translator: dịch sang Tiếng Việt qua Google Translate free (không cần key).
  - Pillow         : vẽ hộp trắng + chữ Việt đã word-wrap & auto-fit lên ảnh gốc.

Thư viện nặng được import TRỄ trong hàm — script vẫn nạp được khi chưa cài, và báo
lỗi rõ khi thực sự gọi.

LIÊN KẾT NỘI BỘ: khi chapter chưa tải, gọi `manga.download` qua
`tools.registry.call_skill(...)` — KHÔNG import chéo script sibling — để giữ đúng
cơ chế lazy-load của registry.

Tool công khai `tool_translate_manga(...)` luôn trả ToolResult.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Cho phép `from core...`/`from tools...` hoạt động dù nạp qua importlib hay chạy độc lập.
# skills/manga-translate/scripts/translator.py -> parents[3] = gốc dự án.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import logging
import textwrap

from core.config import settings
from core.schemas import MangaTarget, ToolResult

logger = logging.getLogger("aura.skills.manga_translate")

# Đuôi ảnh sẽ xử lý trong một chapter.
_IMAGE_EXTS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp"})


class ComicTranslator:
    """Pipeline OCR → dịch → in lại text Việt cho một trang / một chapter."""

    def __init__(
        self,
        ocr_languages: tuple[str, ...] = ("ja", "en"),
        confidence_threshold: float = 0.3,
        target_language: str = "vi",
        font_path: str | None = None,
    ) -> None:
        self.ocr_languages = list(ocr_languages)
        self.confidence_threshold = confidence_threshold
        self.target_language = target_language
        self.font_path = font_path
        # Khởi tạo trễ: chỉ nạp model OCR ở lần dùng đầu (rất nặng).
        self._reader = None
        self._translator = None

    # ------------------------------------------------------------------ #
    # Khởi tạo trễ các thành phần nặng
    # ------------------------------------------------------------------ #
    def _get_reader(self):
        """Nạp easyocr.Reader một lần (tốn vài giây + RAM)."""
        if self._reader is None:
            try:
                import easyocr
            except ModuleNotFoundError as exc:
                raise ModuleNotFoundError(
                    "Thiếu 'easyocr'. Cài: pip install easyocr"
                ) from exc
            logger.info("Đang nạp easyocr cho %s...", self.ocr_languages)
            # gpu=False để chạy được trên máy không NPU/GPU.
            self._reader = easyocr.Reader(self.ocr_languages, gpu=False)
        return self._reader

    def _get_translator(self):
        """Khởi tạo deep-translator (GoogleTranslator) một lần."""
        if self._translator is None:
            try:
                from deep_translator import GoogleTranslator
            except ModuleNotFoundError as exc:
                raise ModuleNotFoundError(
                    "Thiếu 'deep-translator'. Cài: pip install deep-translator"
                ) from exc
            self._translator = GoogleTranslator(source="auto", target=self.target_language)
        return self._translator

    # ------------------------------------------------------------------ #
    # Trích xuất + dịch
    # ------------------------------------------------------------------ #
    def extract_and_translate(self, image_path: str) -> list[dict]:
        """
        OCR một ảnh, lọc nhiễu theo confidence, dịch từng cụm sang Tiếng Việt.

        Returns:
            list[{bbox, text_original, text_translated, confidence}].
            bbox = (x_min, y_min, x_max, y_max) pixel.
        """
        reader = self._get_reader()
        translator = self._get_translator()

        raw_results = reader.readtext(image_path)  # [(box4pts, text, conf), ...]
        out: list[dict] = []
        for box, text, conf in raw_results:
            if conf < self.confidence_threshold:
                continue
            cleaned = text.strip()
            if len(cleaned) < 2:  # bỏ mảnh quá ngắn (thường là nhiễu)
                continue

            xs = [int(p[0]) for p in box]
            ys = [int(p[1]) for p in box]
            bbox = (min(xs), min(ys), max(xs), max(ys))

            try:
                translated = translator.translate(cleaned)
            except Exception as exc:  # noqa: BLE001 — dịch lỗi 1 cụm không nên giết cả trang
                logger.warning("Dịch lỗi cụm %r: %s", cleaned, exc)
                translated = cleaned  # giữ nguyên gốc nếu dịch hỏng

            out.append(
                {
                    "bbox": bbox,
                    "text_original": cleaned,
                    "text_translated": translated or cleaned,
                    "confidence": float(conf),
                }
            )
        return out

    # ------------------------------------------------------------------ #
    # Vẽ text Việt lên ảnh
    # ------------------------------------------------------------------ #
    def _load_font(self, size: int):
        """Nạp font theo size; fallback font mặc định nếu không có font Việt."""
        from PIL import ImageFont

        if self.font_path:
            try:
                return ImageFont.truetype(self.font_path, size)
            except OSError:
                pass
        for candidate in ("arial.ttf", "DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
        return ImageFont.load_default()

    def _draw_text_wrapped(self, draw, text, bbox, max_font_size=30) -> None:
        """Vẽ text có word-wrap, tự thu nhỏ font cho vừa hộp; nền trắng phía sau."""
        x_min, y_min, x_max, y_max = bbox
        box_w = max(1, x_max - x_min)
        box_h = max(1, y_max - y_min)

        font_size = max_font_size
        while font_size >= 8:
            font = self._load_font(font_size)
            char_w = max(1, int(font_size * 0.6))
            max_chars = max(1, box_w // char_w)
            wrapped = textwrap.fill(text, width=max_chars)

            try:
                bb = draw.multiline_textbbox((0, 0), wrapped, font=font)
                text_w, text_h = bb[2] - bb[0], bb[3] - bb[1]
            except AttributeError:  # Pillow rất cũ
                text_w, text_h = draw.multiline_textsize(wrapped, font=font)

            if text_w <= box_w and text_h <= box_h:
                break
            font_size -= 2
        else:
            font = self._load_font(8)
            wrapped = textwrap.fill(text, width=max(1, box_w // 5))

        # Nền trắng để chữ dễ đọc, rồi vẽ chữ đen viền trắng.
        draw.rectangle([x_min, y_min, x_max, y_max], fill="white")
        tx = x_min + 2
        ty = y_min + 2
        draw.multiline_text(
            (tx, ty), wrapped, font=font, fill="black", align="center",
            stroke_width=1, stroke_fill="white",
        )

    def draw_translated_text(
        self, image_path: str, text_data: list[dict], output_path: str
    ) -> bool:
        """Vẽ toàn bộ cụm dịch lên ảnh và lưu ra output_path. True nếu thành công."""
        from PIL import Image, ImageDraw

        img = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        for item in text_data:
            self._draw_text_wrapped(draw, item["text_translated"], item["bbox"])
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path)
        return True

    # ------------------------------------------------------------------ #
    # Xử lý cả chapter
    # ------------------------------------------------------------------ #
    def process_chapter(
        self, chapter_folder: Path, output_folder: Path
    ) -> tuple[int, int]:
        """
        Dịch mọi ảnh trong một chapter. Trả (số trang thành công, số trang lỗi).
        """
        output_folder.mkdir(parents=True, exist_ok=True)
        images = sorted(
            p for p in chapter_folder.iterdir()
            if p.suffix.lower() in _IMAGE_EXTS
        )

        success, fail = 0, 0
        for img_path in images:
            out_path = output_folder / img_path.name
            try:
                data = self.extract_and_translate(str(img_path))
                self.draw_translated_text(str(img_path), data, str(out_path))
                success += 1
            except ModuleNotFoundError:
                raise  # thiếu thư viện -> ném lên để tool báo cài đặt
            except Exception as exc:  # noqa: BLE001 — 1 trang lỗi không giết cả chapter
                logger.warning("Trang %s lỗi: %s", img_path.name, exc)
                fail += 1
        return success, fail


# ---------------------------------------------------------------------------
# Liên kết nội bộ: tự tải chapter nếu thiếu — qua registry (KHÔNG import sibling)
# ---------------------------------------------------------------------------
def _ensure_downloaded(target: MangaTarget, src: Path, source_url: str | None) -> str | None:
    """
    Bảo đảm chapter đã có ảnh ở `src`. Nếu thiếu và có source_url, gọi manga.download
    qua call_skill (lazy-load). Trả None nếu OK, hoặc chuỗi lỗi nếu vẫn không có ảnh.
    """
    if src.exists() and any(p.suffix.lower() in _IMAGE_EXTS for p in src.iterdir()):
        return None
    if not source_url:
        return (f"Chưa thấy chapter đã tải tại {src}. Sếp cung cấp 'source_url' để em "
                "tự tải trước, hoặc chạy manga.download giúp em.")

    # Gọi chéo skill ĐÚNG chuẩn lazy-load: code manga.download chỉ nạp tại đây.
    from tools.registry import call_skill

    logger.info("Chapter chưa có ảnh — tự gọi manga.download qua registry.")
    dl = call_skill("manga.download", {
        "title": target.title, "chapter": target.chapter, "source_url": source_url,
    })
    if not dl.ok:
        return f"Tự tải chapter thất bại: {dl.error}"
    if not (src.exists() and any(p.suffix.lower() in _IMAGE_EXTS for p in src.iterdir())):
        return f"Đã gọi tải nhưng vẫn không thấy ảnh ở {src}."
    return None


# ---------------------------------------------------------------------------
# Tool công khai cho Registry  (entrypoint khai báo trong SKILL.md)
# ---------------------------------------------------------------------------
def tool_translate_manga(
    title: str,
    chapter: float,
    source_url: str | None = None,
    auto_download: bool = True,
) -> ToolResult:
    """
    Tool 'manga.translate': dịch chapter đã tải, trả ToolResult (không ném exception).

    Đường dẫn theo quy ước:
      nguồn : downloads/<title>/<chapter_label>
      đích  : downloads/<title>_Translated/<chapter_label>

    Nếu nguồn chưa có và auto_download=True + có source_url, tự gọi manga.download trước.
    """
    try:
        target = MangaTarget(title=title, chapter=chapter)
    except ValueError as exc:
        return ToolResult.failure("manga.translate", f"Tham số truyện không hợp lệ: {exc}")

    src = settings.downloads_dir / target.title / target.chapter_label
    dst = settings.downloads_dir / f"{target.title}_Translated" / target.chapter_label

    # Liên kết nội bộ: bảo đảm có ảnh nguồn (tự tải qua registry nếu cần).
    missing = _ensure_downloaded(target, src, source_url if auto_download else None)
    if missing is not None:
        return ToolResult.failure("manga.translate", missing)

    try:
        translator = ComicTranslator()
        success, fail = translator.process_chapter(src, dst)
    except ModuleNotFoundError as exc:
        return ToolResult.failure("manga.translate", str(exc))
    except Exception as exc:  # noqa: BLE001 — vành đai cuối
        return ToolResult.failure("manga.translate", f"Lỗi không xác định: {exc}")

    if success == 0:
        return ToolResult.failure(
            "manga.translate",
            f"Không dịch được trang nào (lỗi {fail} trang). Kiểm tra ảnh nguồn.",
        )

    artifacts = [str(p) for p in sorted(dst.iterdir()) if p.suffix.lower() in _IMAGE_EXTS]
    return ToolResult.success(
        tool_name="manga.translate",
        output=f"Đã dịch {success} trang (lỗi {fail}) → {dst}",
        artifacts=artifacts,
    )


# ---------------------------------------------------------------------------
# CLI độc lập (Level 4)
# ---------------------------------------------------------------------------
def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="AURA skill manga.translate — dịch 1 chapter.")
    ap.add_argument("--title", required=True)
    ap.add_argument("--chapter", required=True, type=float)
    ap.add_argument("--source-url", default=None, help="Tự tải trước nếu chapter chưa có.")
    ap.add_argument("--no-auto-download", action="store_true")
    args = ap.parse_args(argv)

    result = tool_translate_manga(
        title=args.title, chapter=args.chapter,
        source_url=args.source_url, auto_download=not args.no_auto_download,
    )
    print(result.model_dump_json(indent=2))
    return 0 if result.ok else 1


__all__ = ["ComicTranslator", "tool_translate_manga"]


if __name__ == "__main__":
    raise SystemExit(_main())
