"""
factory/platform_rules.py
=========================
LUẬT CHƠI TỪNG NỀN TẢNG đăng truyện — để AURA không bao giờ đăng sai luật và
làm Sếp bị khoá tài khoản.

Nguồn: khảo sát trực tiếp quy định của từng site (2026-07-22). Mỗi mục ghi rõ
căn cứ để sau này kiểm lại — luật nền tảng HAY ĐỔI, phải rà lại định kỳ.

Ba câu hỏi quyết định trước khi đăng bất kỳ đâu:
  1. Nền này có CHO nội dung AI không?          -> ai_allowed
  2. Có bắt KHAI BÁO là AI viết không?          -> ai_disclosure_required
  3. Có cho kêu gọi donate NGOÀI hệ thống không? -> external_donate_allowed
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlatformRule:
    key: str
    name: str
    ai_allowed: bool
    ai_disclosure_required: bool
    external_donate_allowed: bool
    fanfic_allowed: bool = True
    notes: str = ""
    source: str = ""
    checked: str = "2026-07-22"
    extra_bans: tuple[str, ...] = field(default_factory=tuple)
    # GU ĐỘC GIẢ của nền — để AURA viết ĐÚNG THỂ LOẠI ăn khách ở đó, thay vì
    # viết một kiểu rồi rải khắp nơi (Sếp đề xuất 2026-07-22).
    preferred_genres: tuple[str, ...] = field(default_factory=tuple)
    audience: str = ""


# Câu khai báo AI dùng chung (Wattpad ToS 5.3 yêu cầu đặt ở MÔ TẢ TRUYỆN và lặp
# lại ở ghi chú tác giả CHƯƠNG ĐẦU).
AI_DISCLOSURE_VI = (
    "⚠️ Lưu ý: Truyện này được sáng tác với sự hỗ trợ của công cụ trí tuệ nhân tạo (AI)."
)
AI_DISCLOSURE_EN = (
    "Disclosure: This story was created with the assistance of artificial "
    "intelligence (AI) tools."
)


RULES: dict[str, PlatformRule] = {
    "wattpad": PlatformRule(
        key="wattpad",
        name="Wattpad",
        ai_allowed=True,
        ai_disclosure_required=True,      # ToS 5.3
        external_donate_allowed=True,
        notes=(
            "CHO nội dung AI NHƯNG BẮT BUỘC khai báo rõ ràng: đặt ở phần MÔ TẢ "
            "truyện VÀ lặp lại trong ghi chú tác giả ở CHƯƠNG ĐẦU. Không khai báo "
            "= vi phạm nghiêm trọng -> gỡ truyện, khoá tài khoản, mất quyền kiếm "
            "tiền (Paid Stories/Wattpad Stars). Ngoài ra: Wattpad CHẶN BOT mạnh "
            "(bẫy debugger) -> chỉ đăng bằng tay/trợ giúp, KHÔNG automation."
        ),
        source="Wattpad ToS 5.3 (cập nhật 03/2024)",
        preferred_genres=("ngôn tình", "thanh xuân học đường", "teen fiction",
                          "huyền huyễn phương Tây", "sói/ma cà rồng"),
        audience="Độc giả trẻ (nữ chiếm đa số), đọc trên điện thoại, thích chương "
                 "ngắn + cảm xúc mạnh + kết chương treo. Bản tiếng Anh có cửa rộng hơn.",
    ),
    "rookies": PlatformRule(
        key="rookies",
        name="Rookies (rookies.vn)",
        ai_allowed=True,                  # không tìm thấy điều nào cấm AI
        ai_disclosure_required=False,
        external_donate_allowed=False,    # ĐIỀU 1 quy định nội dung
        notes=(
            "Quy định nội dung KHÔNG có điều nào cấm nội dung AI. NHƯNG điều 1 "
            "NGHIÊM CẤM mua bán/kêu gọi donate NGOÀI hệ thống Rookies -> PHẢI BỎ "
            "QR donate ngân hàng khi đăng ở đây; kiếm tiền qua khoá chương trả phí "
            "+ donate nội bộ của Rookies. Đăng tự do, không chờ kiểm duyệt."
        ),
        source="rookies.vn/trung-tam/quy-dinh-ve-noi-dung.html",
        preferred_genres=("ngôn tình", "thanh xuân học đường", "xuyên không",
                          "trọng sinh", "huyền huyễn", "hệ thống", "đam mỹ"),
        audience="Độc giả VIỆT, phần lớn nữ/trẻ. Quan sát trang chủ 2026-07-22: "
                 "truyện nổi bật nghiêng hẳn về NGÔN TÌNH/THANH XUÂN nhẹ nhàng "
                 "(vd 'Anh ấy dịu dàng hơn cả gió', 'Học bá của tôi là đồ đáng ghét') "
                 "— KHÔNG phải hành động/cyberpunk. Có khoá chương thu phí nên chương "
                 "đầu phải hút, cắt chương đúng chỗ cao trào.",
    ),
    "thiensonquan": PlatformRule(
        key="thiensonquan",
        name="Huyền Sơn Quán (huyensonquan.com)",
        ai_allowed=False,                 # CẤM THẲNG
        ai_disclosure_required=False,
        external_donate_allowed=False,
        fanfic_allowed=False,
        notes=(
            "❌ CẤM truyện viết bằng AI ('chat GPT, chat AI') — vi phạm lần 1 về "
            "chờ duyệt, lần 2 nhắc nhở, không sửa thì XOÁ. CẤM luôn truyện dịch/"
            "copy/đạo văn/fanfic/ĐỒNG NHÂN/phóng tác. Tài khoản mới KHÔNG up được "
            "truyện, phải xin duyệt lên tài khoản tác giả qua mail/Facebook. "
            "=> KHÔNG đăng truyện AURA lên đây."
        ),
        source="huyensonquan.com/quy-dinh-va-huong-dan/",
        extra_bans=("ai", "fanfic", "đồng nhân", "truyện dịch", "phóng tác"),
    ),
    "noveltoon": PlatformRule(
        key="noveltoon",
        name="NovelToon / Mangatoon",
        ai_allowed=False,                 # CHƯA rõ -> mặc định CHẶN cho an toàn
        ai_disclosure_required=True,
        external_donate_allowed=False,
        notes=(
            "CHƯA tra được quy định về nội dung AI (nền thương mại, ký hợp đồng/"
            "nhuận bút). Mặc định COI NHƯ CHẶN cho tới khi đọc kỹ điều khoản — "
            "nền có hợp đồng thì rủi ro pháp lý cao hơn nhiều."
        ),
        source="(chưa xác minh — cần đọc ToS trực tiếp)",
    ),
    "payhip": PlatformRule(
        key="payhip",
        name="Payhip (payhip.com)",
        ai_allowed=True,
        ai_disclosure_required=False,
        external_donate_allowed=False,   # Claude sửa: bán qua Payhip (Stripe/PayPal),
                                         # CẤM nhét QR ngân hàng lách cổng thanh toán.
        notes=(
            "Payhip cho phép bán các tệp kỹ thuật số (PDF, EPUB, hình ảnh) do AI tạo ra "
            "(Claude kiểm chứng 2026-07-24: danh sách cấm KHÔNG có nội dung AI). Thu tiền "
            "qua PayPal/Stripe của Payhip. ⚠️ CẤM 'PLR/MRR/content with resale rights' — "
            "bán sách tô màu dạng SẢN PHẨM GỐC dùng cá nhân, mô tả KHÔNG ghi 'resell/PLR/"
            "full resale rights'. KHÔNG nhét QR donate (lách thanh toán = khoá acc)."
        ),
        source="help.payhip.com/article/205 (Claude đọc trực tiếp 2026-07-24)",
        preferred_genres=("coloring book", "digital art", "ebook", "planner"),
        audience="Khách hàng quốc tế mua sản phẩm số.",
    ),
}


def get(platform: str) -> PlatformRule | None:
    return RULES.get((platform or "").strip().lower())


def can_post(platform: str) -> tuple[bool, str]:
    """(được đăng không, lý do). Nền lạ -> CHẶN (an toàn mặc định)."""
    r = get(platform)
    if r is None:
        return False, f"Chưa có luật cho nền '{platform}' — chưa rà quy định, không đăng."
    if not r.ai_allowed:
        return False, f"{r.name}: CẤM nội dung AI. {r.notes}"
    return True, f"{r.name}: được đăng."


def disclosure_for(platform: str) -> str:
    """Câu khai báo AI cần chèn (rỗng nếu nền không yêu cầu)."""
    r = get(platform)
    if r is None or not r.ai_disclosure_required:
        return ""
    return AI_DISCLOSURE_VI


def allows_donate_qr(platform: str) -> bool:
    r = get(platform)
    return bool(r and r.external_donate_allowed)


def genre_hint(platform: str) -> str:
    """Chuỗi GỢI Ý THỂ LOẠI + GU ĐỘC GIẢ, nhét thẳng vào prompt của story.factory
    để AURA viết ĐÚNG gu nền đó thay vì viết một kiểu rồi rải khắp nơi."""
    r = get(platform)
    if r is None or not r.preferred_genres:
        return ""
    return (
        f"NỀN TẢNG ĐÍCH: {r.name}. "
        f"THỂ LOẠI ĂN KHÁCH Ở ĐÂY: {', '.join(r.preferred_genres)}. "
        f"GU ĐỘC GIẢ: {r.audience} "
        "Hãy chọn bối cảnh/giọng văn bám đúng gu này."
    )


def preferred_genres(platform: str) -> tuple[str, ...]:
    r = get(platform)
    return r.preferred_genres if r else ()


__all__ = [
    "PlatformRule", "RULES", "get", "can_post", "disclosure_for",
    "allows_donate_qr", "genre_hint", "preferred_genres",
    "AI_DISCLOSURE_VI", "AI_DISCLOSURE_EN",
]
