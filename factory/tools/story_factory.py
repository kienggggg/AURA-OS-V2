"""
factory/tools/story_factory.py
===============================
story.factory — AURA TỰ VIẾT truyện dài kỳ (tool kiếm tiền nội dung gốc/đồng nhân).

Giải bài toán "viết dài không lạc mạch": mỗi bộ giữ một BIBLE bền (thế giới +
nhân vật + hệ thống sức mạnh + tuyến truyện tổng) — dựng 1 lần, mọi chương bám
theo. Mỗi chương viết kèm TÓM TẮT chương trước (trí nhớ cuốn chiếu, như
novel.translate) nên nhân vật/diễn biến nhất quán xuyên hàng trăm chương.

AURA viết 100%: dựng bible → viết từng chương → tự tóm tắt để nhớ → đóng
PDF/EPUB + chèn donate. Sập máy/hết quota chỉ tạm dừng, chạy lại viết tiếp
chương dở (checkpoint từng chương).

Đăng bài: Wattpad/Webtoon KHÔNG có API đăng → AURA xuất bản chữ sẵn (kèm dòng
donate), user dán tay cho an toàn tài khoản. Ảnh QR nằm trong bản PDF.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from core.config import settings
from factory import pdfkit
from factory import queue as job_queue
from factory.models import FormField, JobCancelled, JobRecord, ToolSpec
from factory.qc import QCReport, register_checker

from factory.tools.epub_style_extractor import get_epub_samples

_SUMMARY_MARK = "===TÓM TẮT==="

_FEW_SHOT_EXAMPLES = """
=== VÍ DỤ ĐỂ HỌC TẬP (FEW-SHOT LEARNING) ===

Ví dụ 1: Xử lý tình huống Xuyên Không (Tâm lý Isekai)
❌ VIẾT DỞ (Ngây ngô, hoảng loạn): "Lâm Hạo ôm đầu gào thét: 'Trời ơi, tôi đang ở đâu thế này? Tại sao tôi lại bị đánh?' Cậu sợ hãi co rúm người lại."
✅ VIẾT HAY (Sắc bén, thực dụng): "Lâm Hạo lùi lại, nuốt cục máu tanh trong cổ họng. Khung cảnh xa lạ, nhưng bản năng sinh tồn của một gã sống bằng nghề phân tích rủi ro nói cho cậu biết: Kẻ thù trước mặt không đàm phán được. Phải tìm khe hở để lật kèo."

Ví dụ 2: Lỗi lạm dụng so sánh & Nhịp độ chiến đấu
❌ VIẾT DỞ (Văn AI lề mề, sáo rỗng): "Hắn lao đến như một cơn gió, đôi mắt đỏ ngầu như máu. Không khí nặng nề như một tảng đá đè xuống."
✅ VIẾT HAY (Show-don't-tell, dứt khoát): "Hắn lao tới. Mũi kiếm xé gió rít lên chói tai. Không khí đặc quánh lại, bức bối đến nghẹt thở. Lâm Hạo nín thở, gạt mạnh thanh gỉ sét cản đòn, cổ tay truyền đến một trận tê dại."

Ví dụ 3: Xây dựng nhịp cầu tâm lý (Phản diện/Nhân vật phụ)
❌ VIẾT DỞ (Thay đổi thái độ vô lý): "Ngụy Dịch Phong vung kiếm định chém, nhưng đột nhiên thấy Lâm Hạo quá đáng thương. Hắn thu kiếm lại: 'Ta sẽ nhận ngươi làm đệ tử'."
✅ VIẾT HAY (Thỏa hiệp vì lợi ích): "Mũi kiếm của Ngụy Dịch Phong dừng lại cách cổ Lâm Hạo đúng một thốn. Ánh mắt hắn lóe lên sự toan tính. Kẻ mang dị hỏa này nếu chết ở đây thì phí quá, chi bằng giữ lại làm mồi nhử. Hắn hạ kiếm: 'Muốn sống không, nhóc?'."

Ví dụ 4: Bệnh "Info-dumping" (Thuyết minh bối cảnh như đọc từ điển)
❌ VIẾT DỞ (Kể lể lê thê): "Thế giới này gọi là Thiên Đỉnh Đại Lục, nơi mọi người đều tu luyện linh khí. Lâm Hạo là một thiếu niên mười lăm tuổi, gia cảnh nghèo khó, hôm nay cậu vào rừng tìm thảo dược."
✅ VIẾT HAY (Cài cắm bối cảnh qua hành động): "Lâm Hạo cắn răng bấu chặt tay vào mỏm đá, từng luồng linh khí loãng tuếch của vùng ngoại ô cứa vào phổi cậu. Mười lăm năm sống kiếp bần hàn ở Thiên Đỉnh Đại Lục dạy cho cậu một đạo lý: Không có thực lực, mạng người rẻ hơn cỏ rác."

Ví dụ 5: Lỗi thoại "Robot" (Nhân vật giải thích chiêu thức như sách giáo khoa)
❌ VIẾT DỞ (Thoại vô hồn, dư thừa): "Lâm Hạo hét lên: 'Ngươi dùng Hỏa Long Quyền cấp 3, chiêu này có thể thiêu rụi mọi thứ nhưng lại tiêu hao rất nhiều linh lực. Ta không sợ ngươi đâu!'"
✅ VIẾT HAY (Thoại gãy gọn, hợp hoàn cảnh sinh tử): "Lâm Hạo nhếch mép, gạt vệt máu trên cằm: 'Hỏa Long Quyền? Khè lửa được vài cái rồi cạn linh lực, để xem ngươi trụ được bao lâu!'."

Ví dụ 6: Xử lý khoảnh khắc nhận Kim Thủ Chỉ / Năng Lực Mới
❌ VIẾT DỞ (Reo hò sáo rỗng): "Lâm Hạo mỉm cười sung sướng: 'Ha ha ha, có hệ thống này rồi, ta sẽ vô địch thiên hạ, không ai làm gì được ta nữa!'"
✅ VIẾT HAY (Đầy nghi ngại & thực tế): "Dòng chữ đỏ quạnh hiện lên giữa khoảng không, nhưng Lâm Hạo không mừng. Trên đời không có miếng bánh kẹp nào rơi từ trên trời xuống mà không gắn mồi câu. Cậu nín thở quan sát: Cái giá của thứ năng lực này... là gì?"

Ví dụ 7: Thương lượng trong thế yếu / Kỹ năng sinh tồn
❌ VIẾT DỞ (Van xin khóc lóc): "Lâm Hạo thề thốt: 'Xin đại ca tha mạng! Tôi có thể làm trâu làm ngựa, dâng hết của cải cho các người!'"
✅ VIẾT HAY (Đưa ra đòn bẩy lợi ích): "Lâm Hạo hai tay giơ cao, lùi nửa bước: 'Giết tôi, các người có được một cái xác khô. Giữ tôi sống 10 phút, tôi mở cho các người cánh cửa ngầm phế tích. Ngã giá đi.'"

Ví dụ 8: Tả cảnh & Khí quyển (Thay cụm từ AI mòn bằng giác quan tả thực)
❌ VIẾT DỞ (Lạm dụng cụm AI mòn): "Không khí ở đây cực kỳ nặng nề, một áp lực vô hình bao trùm lấy không gian làm cây cối rung chuyển."
✅ VIẾT HAY (Giác quan sinh động, súc tích): "Mùi bùn nhão lẫn mùi lưu huỳnh sặc lên nồng nặc. Gió đêm thốc qua khe núi rít lên từng hồi như tiếng rên rỉ của kim loại cũ."

Ví dụ 9: Nhịp gài Hook mở đầu & chuyển đoạn (In-Media-Res)
❌ VIẾT DỞ (Dẫn dắt dài dòng): "Buổi sáng hôm đó trời rất đẹp. Lâm Hạo thức dậy, ăn vội củ khoai rồi sửa soạn hành trang đi tới trường đấu."
✅ VIẾT HAY (Bật thẳng vào nút thắt): "Tiếng nổ xé rách không gian ngay trên đỉnh đầu. Lâm Hạo lao mình vào bụi gai, cát bụi dội xuống lưng rần rật. Trận phục kích bắt đầu sớm hơn cậu tính toán hai tiếng."

Ví dụ 10: Kiểm soát Suy nghĩ Nội tâm vs Thoại thành tiếng (Dấu ngoặc kép)
❌ VIẾT DỞ (Đưa nội tâm vào ngoặc kép làm nhiễu thoại): "Lâm Hạo rơi xuống vực, hắn vội nhắm mắt: 'Trời ơi, phải bám lấy gờ đá ngay!'."
✅ VIẾT HAY (Tách biệt rõ ràng thoại & phản xạ): "Thân thể hẫng đi. Gió rít bên tai bạt mạng. Lâm Hạo siết chặt cơ bụng, gập người vung tay móc vào gờ đá nổi — tiếng móng tay miết vào vách đá vang lên ken két."

Ví dụ 11: Văn phong Bi tráng / Tinh thần hi sinh (Âm hưởng lịch sử)
❌ VIẾT DỞ (Ủy mị, sến súa): "Người mẹ khóc nức nở ôm lấy thi thể con trai: 'Trời ơi, con tôi chết rồi, đất nước này làm sao đây!' Bà gục xuống trong nỗi đau khổ tột cùng."
✅ VIẾT HAY (Hùng hồn, nén đau thương thành sức mạnh): "Con nằm xuống để đất nước đứng lên, mẹ đứng lên chỉ để đi tìm nơi con nằm xuống. Bà không khóc. Giọt nước mắt đã cạn từ trận càn năm ngoái, giờ chỉ còn ánh nhìn kiên định, thắp lên ngọn lửa không thể dập tắt cho những người ở lại."

Ví dụ 12: Tôn vinh nhân vật lỗi lạc / Khí chất lãnh đạo
❌ VIẾT DỞ (Kể lể liệt kê): "Ông ấy là một người rất giỏi ngoại giao và yêu nước. Ông đã giúp đất nước vượt qua nhiều khó khăn và không màng danh lợi, từ chối cả giải thưởng lớn."
✅ VIẾT HAY (Dùng định danh súc tích, uy lực): "Giữa bàn đàm phán quốc tế chông gai, khí chất của một 'Kiến trúc sư ngoại giao' hiện rõ qua từng lời sắc sảo. Lợi ích quốc gia là tối thượng, mọi thứ danh vọng hào nhoáng hay những tờ giấy khen ngợi của phương Tây đối với ông chỉ là củi vụn."

Ví dụ 13: Khoảng lặng trầm ngâm — nỗi mỏi mệt lâu ngày (nhịp chậm, không đánh nhau)
❌ VIẾT DỞ (Gọi thẳng tên cảm xúc rồi kết luận hộ độc giả): "Sau bao năm tháng, Lâm Hạo cảm thấy vô cùng đau khổ và tuyệt vọng. Cậu đã mất hết niềm tin vào cuộc sống, trở nên chán nản và không còn hy vọng gì nữa."
✅ VIẾT HAY (Lật vế, thu hẹp điều mong muốn, đóng bằng một chi tiết nhìn thấy được): "Thứ làm Lâm Hạo già đi không phải mười năm ở Huyền Thiên Tông, mà là những lần cậu tin rồi hụt, tin rồi lại hụt, đến khi chẳng buồn tin nữa. Ngày trước cậu muốn đứng trên đỉnh đại lục. Giờ cậu chỉ mong qua hết hôm nay mà không ai gõ cửa. Nỗi mỏi ấy không gào, không nước mắt — chỉ là một sáng soi mặt xuống chậu nước, cậu thấy cái nhếch mép của mình đã không còn giống hồi mười lăm tuổi."
"""

def _slug(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE).strip("_")
    return s[:max_len] or "bo_truyen"


def _cloud(user: str, system: str, max_tokens: int = 8000, temperature: float = 0.8,
           tier: str = "smart", **kwargs) -> str:
    from core.llm import CloudEngine
    res = CloudEngine().complete(
        [{"role": "user", "content": user}], system_prompt=system,
        temperature=temperature, max_tokens=max_tokens, tier=tier, **kwargs
    )
    if not res.get("ok") or not str(res.get("text", "")).strip():
        raise RuntimeError(f"Cloud viết lỗi: {res.get('error') or 'trả rỗng'}")
    return str(res["text"]).strip()


# --------------------------------------------------------------------------- #
# TRUTH FILES (kiểu InkOS): canon SỐNG cập nhật sau mỗi chương — chống lạc mạch
# truyện dài. Khác "chỉ nhớ chương trước": giữ (1) tóm tắt TOÀN BỘ cốt cuốn chiếu,
# (2) TRẠNG THÁI HIỆN TẠI từng nhân vật (cấp độ/quan hệ/vật phẩm/vị trí — đổi theo
# truyện, không đứng yên như bible), (3) chương ngay trước.
# --------------------------------------------------------------------------- #
def _story_memory_ctx(state: dict, chap_num: int = 1, bible: dict | None = None) -> str:
    parts: list[str] = []
    if state.get("arc_progress"):
        parts.append("CỐT ĐÃ DIỄN RA (bám để KHÔNG mâu thuẫn):\n" + str(state["arc_progress"]))
    cs = state.get("characters_state") or {}
    if cs:
        lines = "\n".join(f"- {k}: {v}" for k, v in cs.items())
        parts.append("TRẠNG THÁI NHÂN VẬT HIỆN TẠI (dùng đúng, đừng để tụt cấp/quên "
                     "vật phẩm):\n" + lines)
    if bible and isinstance(bible.get("arc_roadmap"), list) and bible["arc_roadmap"]:
        roadmap = "\n".join(f"- {step}" for step in bible["arc_roadmap"][:8])
        parts.append(f"DÀN Ý TOÀN BỘ CÁC CHẶNG (ROADMAP):\n{roadmap}")
        # Tìm chặng mục tiêu cụ thể cho chương hiện tại để không đi chệch
        current_step_info = ""
        for step in bible["arc_roadmap"]:
            m = re.search(r"Chương\s+(\d+)(?:-(\d+))?", step, re.IGNORECASE)
            if m:
                s_start = int(m.group(1))
                s_end = int(m.group(2)) if m.group(2) else s_start
                if s_start <= chap_num <= s_end:
                    current_step_info = step
                    break
        if current_step_info:
            parts.append(f"👉 MỤC TIÊU CỐT LÕI CỦA CHƯƠNG {chap_num} HIỆN TẠI (BẤT DI BẤT DỊCH):\n{current_step_info}\n(🔴 LỆNH THÉP: Nếu chương này thuộc chặng '{current_step_info}', CẤM tự ý đưa thêm quái vật, phụ bản, cửa ải hay boss ngoại lai không có trong chặng này!)")
    recent_summaries: list[str] = []
    for prev in range(max(1, chap_num - 3), chap_num):
        sum_text = state.get(f"summary_{prev}") or (state.get("last_summary") if prev == chap_num - 1 else "")
        if sum_text:
            recent_summaries.append(f"Chương {prev}: {sum_text}")
    if recent_summaries:
        parts.append("TÓM TẮT CÁC CHƯƠNG GẦN NHẤT:\n" + "\n\n".join(recent_summaries))
    elif state.get("last_summary"):
        parts.append("CHƯƠNG NGAY TRƯỚC: " + str(state["last_summary"]))
    
    # MỎ NEO DIỄN BIẾN CUỐI CHƯƠNG TRƯỚC (Tail-hook)
    tail = state.get(f"tail_{chap_num - 1}") or (state.get("last_body_tail") if chap_num > 1 else "")
    if tail and chap_num > 1:
        parts.append(f"=== ĐOẠN CUỐI CHƯƠNG {chap_num - 1} (BẮT BUỘC NỐI TIẾP NGAY TỪ ĐÂY) ===\n{tail}\n\n(🔴 LỆNH THÉP: Chương {chap_num} BẮT BUỘC phải mở đầu nối tiếp ngay mạch hành động/hội thoại của đoạn cuối trên. CẤM nhảy cóc thời gian, CẤM lờ đi nhân vật vừa xuất hiện ở câu cuối cùng!)")
    return "\n\n".join(parts)


def _update_truth(bible_ctx: str, state: dict, chap_title: str, body: str) -> dict:
    """Cập nhật canon sau 1 chương (LLM fast — rẻ, nhanh). Lỗi -> giữ state cũ."""
    system = (
        "Bạn quản lý CANON (Truth Files) cho truyện dài, chống mâu thuẫn. Đọc chương "
        "mới + trạng thái cũ, trả JSON THUẦN (không markdown):\n"
        "{\"arc_progress\": \"tóm tắt TOÀN BỘ cốt đã diễn ra tới giờ — GỘP cái cũ + "
        "chương mới, <=250 từ, giữ mọi mốc/bí mật quan trọng theo dòng thời gian\",\n"
        " \"characters_state\": {\"tên\": \"cấp độ tu luyện + quan hệ + vật phẩm + vị "
        "trí HIỆN TẠI\"}}\n"
        "Chỉ ghi nhân vật đã xuất hiện; cập nhật theo diễn biến MỚI NHẤT."
    )
    body_sample = body[:1500] + ("\n...\n[DIỄN BIẾN CUỐI CHƯƠNG]:\n" + body[-5000:] if len(body) > 6500 else "\n" + body[1500:])
    user = (f"BIBLE:\n{bible_ctx}\n\nARC CŨ: {state.get('arc_progress', '(chưa có)')}\n"
            f"NHÂN VẬT CŨ: {json.dumps(state.get('characters_state', {}), ensure_ascii=False)}\n\n"
            f"CHƯƠNG MỚI ({chap_title}):\n{body_sample}")
    try:
        raw = _cloud(user, system, max_tokens=8000, temperature=0.3, tier="fast")
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            upd = json.loads(m.group(0))
            if upd.get("arc_progress"):
                state["arc_progress"] = str(upd["arc_progress"])[:2500]
            if isinstance(upd.get("characters_state"), dict):
                state["characters_state"] = {
                    str(k): str(v) for k, v in upd["characters_state"].items()
                }
    except Exception:  # noqa: BLE001 — canon lỗi không được chặn dây chuyền viết
        pass
    return state


# --------------------------------------------------------------------------- #
# 1) BIBLE — dựng 1 lần, user sửa được, mọi chương bám theo
# --------------------------------------------------------------------------- #
def _build_bible(world: str, premise: str) -> dict:
    system = (
        "Bạn là biên kịch kiêm biên tập viên truyện mạng vàng (tu tiên/đồng nhân). Từ yêu cầu "
        "của user, dựng BIBLE chuẩn chỉ cho một bộ truyện dài kỳ có độ cuốn hút cao ngay từ chương 1. "
        "Trả JSON THUẦN (không markdown):\n"
        "{\"title\": \"tên truyện tiếng Việt hấp dẫn\",\n"
        " \"logline\": \"1 câu tóm gọn sức hút (xung đột + rủi ro)\",\n"
        " \"world\": \"bối cảnh thế giới (bám nguyên tác nếu là đồng nhân)\",\n"
        " \"power_system\": \"hệ thống sức mạnh + các cấp bậc\",\n"
        " \"main\": {\"name\": \"tên nhân vật chính\", \"look\": \"ngoại hình\", "
        "\"personality\": \"tính cách (🔴 QUAN TRỌNG: Nếu là XUYÊN KHÔNG/ISEKAI, BẮT BUỘC phải có tư duy thực dụng, tính toán rủi ro của người hiện đại, KHÔNG ĐƯỢC khóc lóc ngây ngô như trẻ con bản địa)\", \"immediate_goal\": \"mục tiêu trước mắt thực tế sinh tử (SỐNG SÓT/thoát truy sát/cứu người - CẤM dùng 'trở thành người mạnh nhất')\", "
        "\"long_term_goal\": \"mục tiêu dài hạn sâu xa\", \"cheat_manifestation\": \"lợi thế/kim thủ chỉ tả thực bằng 5 giác quan: màu sắc, áp lực, âm thanh, cảm giác cơ thể (CẤM dùng từ 'bí ẩn' chung chung)\"},\n"
        " \"cast\": [{\"name\": \"...\", \"role\": \"vai trò\", \"note\": \"quan hệ với main (🔴 YÊU CẦU: Nếu có sự chuyển biến thái độ, BẮT BUỘC phải xây dựng 'nhịp cầu tâm lý' hợp logic lợi ích, CẤM quay ngoắt 180 độ vô lý)\"}],\n"
        " \"arc_roadmap\": [\"Chương 1-3: Mở đầu In-Media-Res sinh tử, giấu bí mật thân thế, hé lộ năng lực...\", \"Chương 4-7: Khám phá địa điểm mới, xung đột quan niệm, gặp đồng minh...\", \"Chương 8-10: Cao trào Arc 1, trả giá cho sức mạnh...\", \"Chương 11-15: Mở rộng thế giới, thử thách nâng cấp...\"],\n"
        " \"secrets_to_hide\": [\"Danh sách 2-3 bí mật KHÔNG ĐƯỢC spoil/tiết lộ trong 5 chương đầu (vd: xuyên không, thân thế nguyên chủ...)\"],\n"
        " \"tone\": \"giọng văn bão táp, tả thực 5 giác quan, chống nhịp văn AI sáo rỗng\"}\n"
        "Nếu là ĐỒNG NHÂN: tôn trọng thiết định gốc, nhưng nhân vật chính và tuyến "
        "truyện phải MỚI để tạo sức hút riêng."
    )
    user = f"Thế giới: {world}"
    if premise.strip():
        user += f"\nÝ tưởng/nhân vật user muốn: {premise}"
    raw = _cloud(
        user, system, max_tokens=8000, temperature=0.85, 
        response_format={"type": "json_object"}
    )
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        print(f"[DEBUG _build_bible raw output]:\n{raw}")
        raise RuntimeError("Bible trả về không có JSON.")
    return json.loads(m.group(0), strict=False)


def _bible_context(bible: dict) -> str:
    """Rút gọn bible thành khối nhắc cho prompt viết chương."""
    main = bible.get("main", {})
    cast = "; ".join(f"{c.get('name')}({c.get('role')})" for c in bible.get("cast", [])[:8])
    # Bible CŨ (trước 2026-07-13) chỉ có 'arc' chuỗi, không có 'arc_roadmap' —
    # fallback để bộ đang chạy không MẤT định hướng tuyến truyện.
    roadmap = "\n".join(f"  + {step}" for step in bible.get("arc_roadmap", [])[:6]) \
        or f"  + {bible.get('arc', '')}"
    secrets = "; ".join(bible.get("secrets_to_hide", []))
    imm_goal = main.get("immediate_goal") or main.get("goal") or "sống sót thoát hiểm"
    cheat_desc = main.get("cheat_manifestation") or main.get("cheat") or "năng lực đặc biệt"
    return (
        f"TÊN BỘ: {bible.get('title')}\nLOGLINE: {bible.get('logline')}\n"
        f"THẾ GIỚI: {bible.get('world')}\nHỆ THỐNG SỨC MẠNH: {bible.get('power_system')}\n"
        f"NHÂN VẬT CHÍNH: {main.get('name')} — {main.get('look')}; tính: "
        f"{main.get('personality')}\n"
        f"  - Mục tiêu trước mắt (sinh tồn/thực tế): {imm_goal}\n"
        f"  - Mục tiêu dài hạn: {main.get('long_term_goal', '')}\n"
        f"  - Tả thực năng lực/kim thủ chỉ (5 giác quan): {cheat_desc}\n"
        f"TUYẾN NHÂN VẬT: {cast}\n"
        f"DÀN Ý CHẶNG (ROADMAP):\n{roadmap}\n"
        f"BÍ MẬT CẦN GIẤU (CẤM SPOIL Ở CÁC CHƯƠNG ĐẦU): {secrets}\n"
        f"GIỌNG VĂN: {bible.get('tone')}"
    )


def _polish_chapter(title: str, body: str, bible_ctx: str = "", memory_ctx: str = "") -> str:
    """TỰ BIÊN TẬP: LLM tầng SMART đóng vai biên tập viên lão luyện, viết lại chương —
    TRỌNG TÂM kiểm soát nhịp: cắt tả thừa, xen câu ngắn/khoảng lặng, sửa lỗi logic/ảo giác.
    Đây chính là bước 'hỏi AI lớn nhận xét & sửa' — dùng chính model xịn của router."""
    system = (
        "Bạn là BIÊN TẬP VIÊN truyện mạng LÃO LUYỆN (đã viết vài triệu chữ). Viết lại "
        "chương cho HAY hơn, chuẩn nhịp độ, VÀ BẮT BUỘC SỬA LỖI LOGIC / ẢO GIÁC NẾU CÓ:\n"
        "- ĐƯỢC PHÉP VÀ BẮT BUỘC CẮT BỎ hoặc VIẾT LẠI các tình tiết ảo giác phi logic (ví dụ: quái vật lạ, cửa đá hay nhân vật bí ẩn đột ngột nhảy ra không có trong Dàn ý Roadmap hoặc trái với diễn biến nối tiếp từ chương trước; hoặc những mô tả ngô nghê sai sinh lý cơ thể như 'bứt ra khỏi lỗ mũi').\n"
        "- SỬA LỖI TÂM LÝ NHÂN VẬT: Nếu nhân vật phụ/phản diện thay đổi thái độ (từ thù thành bạn/phản bội) mà không có 'nhịp cầu tâm lý' dựa trên lợi ích rõ ràng, BẮT BUỘC viết lại để thêm toan tính/ép buộc. Nếu nhân vật chính (Xuyên không) mà hành xử ngây ngô, BẮT BUỘC sửa thành tư duy lạnh lùng, tính toán sắc bén.\n"
        "- CẮT ~20-30% miêu tả THỪA. Mỗi khoảnh khắc chỉ giữ 1-2 chi tiết giác quan ĐẮT "
        "nhất; CẤM chồng 3-5 lớp tả liên tiếp (máu→mùi→đau→đất→xương→tim...) làm độc giả "
        "bội thực. Xóa bớt 30% cấu trúc so sánh ('như một', 'giống như'). Viết trực tiếp thay vì lạm dụng so sánh (vd: thay 'cành lá buông rũ như cánh tay ma quái' bằng 'cành lá buông rũ, ma quái vươn ra').\n"
        "- BỚT TÍNH TỪ & TÁCH CÂU GỌN TRONG COMBAT: Khi đánh nhau hoặc truy đuổi, câu văn phải dứt khoát có lực. TUYỆT ĐỐI CẤM dùng các từ cộc lốc vô nghĩa 1 từ như 'Cắt!', 'Đánh!', 'Chém!' kiểu lệnh game ra lệnh.\n"
        "- KHOẢNG LẶNG TRẦM NGÂM (đoạn chậm, nhân vật ngồi một mình, hồi tưởng): CẤM gọi "
        "thẳng tên cảm xúc ('đau khổ', 'tuyệt vọng', 'chán nản') rồi kết luận hộ độc giả. "
        "Dùng bốn đòn: (1) LẬT VẾ — 'thứ làm hắn gục không phải X, mà là Y', phủ nhận "
        "nguyên nhân ai cũng đoán rồi mới chỉ ra nguyên nhân thật; (2) THU HẸP ĐIỀU MONG "
        "MUỐN theo thời gian — trước kia mong cả thiên hạ, giờ chỉ mong qua hết hôm nay; "
        "(3) ĐỊNH NGHĨA BẰNG PHỦ ĐỊNH — 'không gào, không nước mắt' thay vì tả nỗi buồn; "
        "(4) ĐÓNG BẰNG MỘT CHI TIẾT NHÌN THẤY ĐƯỢC — mặt nước, vết chai tay, cái nhếch "
        "mép trong gương. Trừu tượng ở đầu đoạn, cụ thể ở nhịp cuối, KHÔNG ngược lại.\n"
        "- TỪ VỰNG CHUẨN KHÔNG KHÍ (IMMERSION): Cấm dùng từ lóng hiện đại, báo chí, văn phòng "
        "(vd: 'biểu tình', 'tối ưu', 'khảo cứu', 'quản lý'...) làm mất không khí tu tiên/huyền huyễn. LƯU Ý TỪ ĐIỂN THẾ GIỚI: Nếu là truyện Tu Tiên/Kiếm Hiệp/Ma Đạo, CẤM TUYỆT ĐỐI dùng khái niệm 'hồn thú', 'hồn sư', 'hồn hoàn', 'ma pháp' (chỉ dùng khi truyện thuộc Đấu La Đại Lục hay Tây Phương).\n"
        "- BẢN SẮC HÌNH ẢNH KIM THỦ CHỈ/VÕ HỒN THỐNG NHẤT: Thống nhất cách gọi và tả cảm giác "
        "kim thủ chỉ/võ hồn (vd: áp lực nặng như núi đè, khí tức tro tàn), CẤM gọi lộn xộn lúc "
        "thì hắc khí, lúc thì ánh sáng làm độc giả khó hình dung.\n"
        "- LOGIC HÀNH VĂN & KIỂM DUYỆT DẤU NGOẶC KÉP: Khi nhân vật ở một mình hoặc rơi xuống vực, "
        "TUYỆT ĐỐI CẤM để phản xạ cơ thể hay suy nghĩ nội tâm vào dấu ngoặc kép (vd cấm viết: "
        "'\"Gập người lại!\"') vì sẽ làm độc giả ngơ ngác tưởng có ai hô hoán từ hư không. "
        "Dấu ngoặc kép '\"...\"' CHỈ DÀNH cho đối thoại thành tiếng giữa các nhân vật. Suy nghĩ "
        "nội tâm để trong dấu *in nghiêng* hoặc tả bằng hành động cơ thể.\n"
        "- NHỊP LÊN XUỐNG & SÓNG CẢM XÚC: xen câu NGẮN + khoảng LẶNG. Đối thoại tự nhiên. "
        "Đặc biệt từ Chương 2 trở đi, CẤM đánh nhau dồn dập 100% từ đầu đến cuối; phải có "
        "khoảng lặng cho độc giả tìm hiểu chiều sâu nhân vật, lý do xuyên không, cái giá của "
        "sức mạnh, và tránh các lối mòn sáo rỗng.\n"
        "- GÀI NHÂN VẬT: chèn 1-2 câu hé lộ MỤC TIÊU/nội tâm nhân vật (vd 'chưa tìm được "
        "đường về', 'không thể chết ở đây') + thông tin định hướng TỐI THIỂU để độc giả ĐỒNG CẢM và KHÔNG lạc hướng.\n"
        "- CẮT cụm khí quyển sáo rỗng LẶP LẠI ('không khí nặng nề', 'không gian méo mó', "
        "'áp lực vô hình', 'cây cối rung chuyển') — thay bằng hình ảnh cụ thể hoặc bỏ.\n"
        "- GIỮ show-don't-tell + các HOOK đắt.\n"
        "- Độ dài chênh không quá 15% (cắt tả thừa thì bù bằng GÀI nhân vật/thông tin, "
        "không để chương ngắn đi).\n"
        "- CHỈ trả về NGUYÊN VĂN chương đã viết lại (không lời dẫn/giải thích/markdown/tựa đề)."
    )
    system += _FEW_SHOT_EXAMPLES + get_epub_samples()
    try:
        ctx = f"TỰA CHƯƠNG: '{title}'\n\n"
        if bible_ctx:
            ctx += f"=== BIBLE THAM KHẢO ===\n{bible_ctx}\n\n"
        if memory_ctx:
            ctx += f"=== TRÍ NHỚ & MỎ NEO NỐI TIẾP ===\n{memory_ctx}\n\n"
        ctx += f"=== BẢN NHÁP CẦN BIÊN TẬP & NÂNG CẤP ===\n{body}"
        raw = _cloud(ctx, system, max_tokens=max(8000, len(body) * 2), temperature=0.3)
        out = re.sub(r"^\s*#.*\n", "", raw.strip()).strip()   # bỏ dòng tựa nếu có
        out = re.sub(r"(\*\s*)+$", "", out).strip()
        # Chỉ nhận nếu GIỮ ĐỦ độ dài (polish quá ngắn = mất tình tiết -> bỏ, dùng gốc).
        if len(out) >= len(body) * 0.75:
            return out
    except Exception:  # noqa: BLE001 — biên tập lỗi thì dùng bản gốc, KHÔNG sập
        pass
    return body


# Cụm khí quyển sáo rỗng hay lọt qua biên tập -> soát riêng.
_TIC_MARKERS = ("không khí nặng nề", "không khí nén lại", "không khí đặc quánh",
                "không gian méo mó", "không gian bị bóp méo", "áp lực vô hình",
                "cây cối rung chuyển", "cây cối rùng mình")


def _sweep_tics(body: str) -> str:
    """LƯỢT SOÁT TIC. Dọn **in đậm** bằng REGEX (an toàn tuyệt đối, không nhờ LLM
    viết lại kẻo model yếu làm hỏng văn). CHỈ khi còn cụm sáo rỗng mới nhờ LLM
    tầng BULK (Gemini — giỏi tiếng Việt) sửa; kết quả nghi hỏng thì giữ bản regex."""
    # 1) Bỏ in đậm bằng regex: **...** -> ...  (không đụng *in nghiêng* 1 dấu sao).
    swept = re.sub(r"\*\*(.+?)\*\*", r"\1", body, flags=re.DOTALL)
    low = swept.lower()
    if not any(m in low for m in _TIC_MARKERS):
        return swept       # hết sáo rỗng -> xong, khỏi gọi LLM
    system = (
        "Bạn là NGƯỜI SOÁT LỖI VĂN. CHỈ thay các cụm khí quyển sáo rỗng LẶP ('không "
        "khí nặng nề/nén lại/đặc quánh', 'không gian méo mó', 'áp lực vô hình', 'cây "
        "cối rung chuyển') bằng hình ảnh CỤ THỂ hoặc bỏ; gộp câu chồng tính từ. TUYỆT "
        "ĐỐI KHÔNG đổi cốt/sự kiện/thoại, KHÔNG rút ngắn, KHÔNG viết lại phần đã ổn. "
        "Trả về NGUYÊN VĂN (không lời dẫn/tựa đề)."
    )
    try:
        raw = _cloud(swept, system, max_tokens=max(6000, len(swept)),
                     temperature=0.2, tier="bulk")
        out = re.sub(r"^\s*#.*\n", "", raw.strip()).strip()
        out = re.sub(r"\*\*(.+?)\*\*", r"\1", out, flags=re.DOTALL)
        # Chỉ nhận nếu độ dài sát (né model thêm/bớt bậy) -> không thì giữ bản regex.
        if 0.9 * len(swept) <= len(out) <= 1.15 * len(swept):
            return out
    except Exception:  # noqa: BLE001
        pass
    return swept


def _word_count(text: str) -> int:
    return len(text.split())


def _expand_chapter(title: str, body: str, target_words: int) -> str:
    """LƯỢT NỚI CHƯƠNG: bản cuối hụt sàn từ -> nhờ LLM MỞ RỘNG bằng cách đào sâu
    cảnh/nội tâm/đối thoại SẴN CÓ (cấm thêm cốt mới, cấm đổi diễn biến). Nhận khi
    dài lên thật và không phình quá đà; lỗi -> giữ nguyên."""
    system = (
        "Bạn là tác giả truyện mạng. Chương dưới đây HAY nhưng NGẮN quá chuẩn đăng. "
        f"Hãy MỞ RỘNG lên khoảng {target_words} từ bằng cách ĐÀO SÂU những gì đã có: "
        "kéo dài các nhịp hành động sẵn có, thêm nội tâm/hồi ức ngắn, thêm lời thoại "
        "tự nhiên, tả kỹ hơn các khoảnh khắc ĐẮT — TUYỆT ĐỐI KHÔNG thêm sự kiện/nhân "
        "vật/địa điểm mới, KHÔNG đổi thứ tự diễn biến, KHÔNG đổi kết chương. Giữ đúng "
        "giọng văn hiện tại (show-don't-tell, nhịp lên xuống, nội tâm *in nghiêng*). "
        "Trả về NGUYÊN VĂN chương đã mở rộng (không lời dẫn/tựa đề)."
    )
    try:
        raw = _cloud(f"CHƯƠNG '{title}':\n\n{body}", system,
                     max_tokens=max(8000, target_words * 4), temperature=0.7)
        out = re.sub(r"^\s*#.*\n", "", raw.strip()).strip()
        out = re.sub(r"\*\*(.+?)\*\*", r"\1", out, flags=re.DOTALL)
        wc_old, wc_new = _word_count(body), _word_count(out)
        # Nhận khi: dài lên thật (>=1.15x) và không phình điên (<=2.2x).
        if wc_new >= wc_old * 1.15 and wc_new <= max(target_words * 1.6, wc_old * 2.2):
            return out
    except Exception:  # noqa: BLE001
        pass
    return body


# --------------------------------------------------------------------------- #
# 2) VIẾT CHƯƠNG — bám bible + tóm tắt chương trước
# --------------------------------------------------------------------------- #
def _prompt_override() -> str:
    """Bản prompt viết chương ĐÃ ĐƯỢC SẾP DUYỆT (do prompt_evolve rèn ra).
    Không có file = dùng bản mặc định trong code."""
    p = settings.factory_dir / "prompts" / "story_chapter.txt"
    try:
        return p.read_text(encoding="utf-8").strip() if p.is_file() else ""
    except Exception:  # noqa: BLE001 — hỏng file không được chặn viết truyện
        return ""


def _write_chapter(bible_ctx: str, memory_ctx: str, chap_num: int,
                   words: int) -> tuple[str, str, str]:
    system = (
        "Bạn là tác giả truyện mạng ăn khách, văn phong cuốn hút, hợp độc giả Việt "
        "(tu tiên/đồng nhân). Viết TRỌN một chương truyện chữ tiếng Việt, "
        # LLM vốn viết HỤT mục tiêu ~30-40%, biên tập lại cắt thêm -> đặt mục tiêu DƯ
        # (words*1.3) + sàn cứng để bản cuối vẫn đủ dài chuẩn Wattpad.
        f"TỐI THIỂU {words} từ (hướng tới {int(words * 1.3)} từ — chương NGẮN hơn "
        f"{words} từ bị coi là KHÔNG ĐẠT; muốn đủ dài hãy đào sâu cảnh, nội tâm, đối "
        "thoại thay vì thêm cốt mới), có đối thoại, hành động, cảm xúc; KẾT chương gài "
        "móc (cliffhanger) để độc giả muốn đọc tiếp. Bám sát BIBLE + CANON — TUYỆT ĐỐI "
        "không để nhân vật tụt cấp, quên vật phẩm, hay mâu thuẫn diễn biến.\n\n"
        "QUY TẮC BẤT BIẾN 'SHOW-DON'T-TELL, KIỂM SOÁT NHỊP & CHỐNG VĂN AI':\n"
        "- TÂM LÝ NHÂN VẬT THỰC TẾ (PSYCHOLOGICAL REALISM): Sự thay đổi thái độ của nhân vật (thù thành bạn, phản bội) BẮT BUỘC phải có 'nhịp cầu tâm lý' hợp lý dựa trên lợi ích hoặc hoàn cảnh ép buộc, CẤM quay ngoắt 180 độ vô lý. Nếu Main là người Xuyên Không (Isekai), phải giữ tư duy logic, tính toán sắc bén của người hiện đại (biết đánh đổi, tận dụng cơ hội), tuyệt đối không hoảng loạn khóc lóc ngây ngô.\n"
        "- BẮT BUỘC KHỞI ĐẦU NỐI TIẾP (TAIL-HOOK CONTINUITY): Nếu trong Trí Nhớ có 'ĐOẠN CUỐI CHƯƠNG TRƯỚC', chương mới PHẢI bắt đầu khớp nối 100% với khung cảnh, thời gian và nhân vật ở đoạn đó. CẤM tự động nhảy cóc thời gian hoặc lờ đi nhân vật vừa xuất hiện ở cuối chương trước.\n"
        "- Show-don't-tell CHỌN LỌC: cấm tường thuật suông ('hồn thú tấn công'), tả bằng "
        "giác quan — NHƯNG mỗi khoảnh khắc chỉ 1-2 chi tiết ĐẮT, CẤM chồng 3-5 lớp tả "
        "(máu→mùi→đau→đất→xương→tim) gây bội thực; tiết chế tính từ.\n"
        "- KIỂM SOÁT NHỊP (PACING) & TÁCH CÂU: Khi đánh nhau, viết câu gọn gàng có lực. TUYỆT ĐỐI BẮT BUỘC chèn những KHOẢNG LẶNG (Breathing Room) sau chuỗi hành động dồn dập (vd: đêm tĩnh mịch bên đống lửa, nhân vật tự chữa thương, suy nghĩ nội tâm) để độc giả 'thở' và đồng cảm. Đừng ép độc giả chạy marathon liên tục.\n"
        "- HẠN CHẾ SO SÁNH ('như một', 'giống như'): Thay vì lạm dụng phép so sánh, hãy dùng miêu tả trực tiếp để câu văn mạnh và sắc bén hơn.\n"
        "- TỪ VỰNG CHUẨN KHÔNG KHÍ & TỪ ĐIỂN THẾ GIỚI: Cấm dùng từ ngữ hiện đại ('biểu tình', 'tối ưu', 'khảo cứu', 'quản lý'). Đặc biệt: nếu thế giới truyện là Tu Tiên / Kiếm Hiệp / Ma Đạo, TUYỆT ĐỐI CẤM xuất hiện các từ 'hồn thú', 'hồn sư', 'hồn hoàn', 'ma pháp' (chỉ dùng khi truyện thuộc Đấu La Đại Lục hay Tây Phương).\n"
        "- THỐNG NHẤT BẢN SẮC HÌNH ẢNH KIM THỦ CHỈ/VÕ HỒN: Giữ nguyên 1-2 đặc trưng giác quan "
        "cốt lõi xuyên suốt từ đầu, CẤM gọi lộn xộn mỗi "
        "đoạn một dạng khác nhau làm độc giả mất phương hướng.\n"
        "- LOGIC HÀNH VĂN & CHUẨN DẤU NGOẶC KÉP: Khi nhân vật ở một mình hoặc đang rơi, CẤM để suy "
        "nghĩ nội tâm hoặc phản xạ vào dấu ngoặc kép '\"...\"' vì sẽ làm độc giả tưởng có người "
        "khác hô hoán thành tiếng. Dấu ngoặc kép CHỈ dùng cho đối thoại nói thành tiếng giữa các nhân vật.\n"
        "- GÀI NHÂN VẬT sớm: hé lộ MỤC TIÊU/nội tâm nhân vật + thông tin định hướng tối "
        "thiểu để độc giả đồng cảm và không lạc hướng (đừng chỉ có đánh nhau suốt chương).\n"
        "- Cấm cụm AI sáo rỗng ('mang theo bí ẩn', 'khác biệt hoàn toàn', 'thay đổi số "
        "phận', 'không khí nặng nề', 'không gian méo mó', 'áp lực vô hình' lặp lại).\n"
        "- Cấm tự ý đẻ thêm Boss/kẻ thù bí ẩn mới ở cuối chương nếu không có trong Dàn ý (Roadmap).\n"
        f"ĐỊNH DẠNG TRẢ VỀ: dòng đầu 'Chương {chap_num}: <tựa chương>', "
        "xuống dòng rồi nội dung. CUỐI CÙNG thêm dòng '" + _SUMMARY_MARK + "' rồi "
        "2-3 câu tóm tắt diễn biến chương này."
    )
    # RÈN PROMPT (factory/prompt_evolve.py): nếu có bản Sếp ĐÃ DUYỆT thì dùng thay
    # bản mặc định. Đây là cách AURA khôn thêm mà KHÔNG đụng trọng số model.
    _ov = _prompt_override()
    if _ov:
        system = _ov.replace("{chap_num}", str(chap_num)).replace("{words}", str(words))
    system += _FEW_SHOT_EXAMPLES + get_epub_samples()
    if chap_num == 1:
        system += (
            "\n\n🔴 QUY TẮC ĐẶC BIỆT CHO CHƯƠNG 1 (HOOK ĐỘC GIẢ TRONG 30 GIÂY & GÀI MỎ NEO NHÂN VẬT):\n"
            "- CẤM VIẾT ĐOẠN GIỚI THIỆU BỐI CẢNH HAY LÝ LỊCH NHÂN VẬT DÀI DÒNG ở đầu chương.\n"
            "- BẮT BUỘC mở đầu In-Media-Res (giữa hành động/nguy hiểm): Mở mắt ra là một vết thương đau nhói, một con quái vật lao đến, hoặc một cuộc truy sát căng thẳng.\n"
            "- TIẾT LỘ NHỎ GIỌT NHƯNG PHẢI CÓ MỎ NEO (Progressive Disclosure with Anchoring): Cấm thuyết minh bối cảnh như từ điển, NHƯNG BẮT BUỘC phải xen kẽ 2-3 câu suy nghĩ/tiết lộ ngắn gọn trong khoảng lặng để độc giả BIẾT CHUYỆN GÌ ĐANG XẢY RA: (1) Nhân vật vừa xuyên không tới/tỉnh lại bao lâu, (2) Tại sao đang bị săn lùng (vd: vì võ hồn dị biến bị nhòm ngó), (3) Động cơ/mục tiêu cốt lõi để sống sót (vd: 'Không thể chết ở thế giới quỷ quái này, mình phải tìm đường quay về...'). Nếu không có mỏ neo này, độc giả sẽ không đồng cảm với nhân vật!\n"
        )
    elif chap_num >= 2:
        system += (
            "\n\n🟢 QUY TẮC ĐẶC BIỆT CHO CHƯƠNG 2 TRỞ ĐI (SÓNG NHỊP ĐỘ & KHOẢNG LẶNG CHIỀU SÂU):\n"
            "- CẤM đánh nhau/combat liên tục 100% tiếp nối ngay từ chương 1 làm độc giả bị mệt mỏi bội thực hành động.\n"
            "- BẮT BUỘC phải tạo KHOẢNG LẶNG (Breathing Room): Sau tình huống thoát hiểm hoặc bơi lên bờ, cho nhân vật và độc giả thời gian thở, kiểm tra kinh mạch/vết thương, và khám phá chiều sâu cốt truyện:\n"
            "  + (1) Lý do sâu xa hoặc hoàn cảnh xuyên không/tỉnh lại (tại sao cỗ thân thể nguyên chủ lại ở đây, bị ai hãm hại).\n"
            "  + (2) Bản chất Kim Thủ Chỉ/Võ Hồn là gì và VÌ SAO nó lại ăn mòn sinh mệnh/kinh mạch.\n"
            "  + (3) Vì sao thế lực đối địch lại thèm khát nó đến mức truy sát gắt gao.\n"
            "- TRÁNH tuyệt đối các lối mòn sáo rỗng mỳ ăn liền (nhặt tiên thảo tình cờ, gặp lão gia gia rập khuôn). Nếu gặp nhân vật mới, phải là sự kiện hợp logic bối cảnh hoặc có xung đột quan niệm."
        )
    from factory import reflexion
    # Bài học từ cả 2 dòng: 'novel' (cũ, trước khi tách product_line) + 'story' (mới).
    system += reflexion.lessons_prompt("novel") + reflexion.lessons_prompt("story")
    user = bible_ctx
    if memory_ctx:
        user += f"\n\n=== TRÍ NHỚ TRUYỆN (CANON) ===\n{memory_ctx}"
    user += f"\n\nHãy viết Chương {chap_num}."
    raw = _cloud(user, system, max_tokens=max(8000, words * 4), temperature=0.85)
    summary = ""
    if _SUMMARY_MARK in raw:
        raw, summary = raw.rsplit(_SUMMARY_MARK, 1)
        summary = re.sub(r"^(\*\s*)+", "", summary.strip()).strip()[:600]
    raw = re.sub(r"(\*\s*)+$", "", raw.strip()).strip()
    lines = raw.split("\n", 1)
    title_raw = lines[0].strip().lstrip("#").strip()
    title = re.sub(r"^(\*\s*)+|(\*\s*)+$", "", title_raw).strip() or f"Chương {chap_num}"
    body = lines[1].strip() if len(lines) > 1 else ""
    if len(body) < 200:
        raise RuntimeError(f"Chương {chap_num}: nội dung quá ngắn, nghi lỗi.")
    # TỰ BIÊN TẬP: 1 lượt biên tập viên khó tính viết lại cho hay hơn (giữ nguyên cốt),
    # rồi 1 lượt SOÁT TIC dọn nốt sáo rỗng/in đậm còn sót.
    if getattr(settings, "story_self_edit", True):
        body = _polish_chapter(title, body, bible_ctx, memory_ctx)
        body = _sweep_tics(body)
    # SÀN ĐỘ DÀI: nháp dư + biên tập cắt vẫn có thể hụt (~800 từ trong khi chuẩn
    # Wattpad cần >=1500) -> 1 lượt NỚI đào sâu cảnh sẵn có cho đủ sàn.
    if _word_count(body) < int(words * 0.85):
        body = _expand_chapter(title, body, words)
    if not summary:
        try:
            summary_raw = _cloud(
                f"Tóm tắt ngắn 2-3 câu (<=100 từ) các sự kiện chính trong chương truyện sau:\n{body[-4000:]}",
                "Trả về text tóm tắt ngắn gọn thuần túy.", max_tokens=300, temperature=0.3, tier="fast"
            )
            summary = re.sub(r"^(\*\s*)+", "", summary_raw.strip()).strip()[:600]
        except Exception:
            pass
    return title, body, summary


# --------------------------------------------------------------------------- #
# 3) Donate: dòng chữ (cho Wattpad dán) + ảnh QR (cho PDF)
# --------------------------------------------------------------------------- #
def _donate_text() -> str:
    if not settings.donate_bank_account:
        return ""
    return (f"\n\n─────────────\n💛 Nếu thấy hay, ủng hộ tác giả viết tiếp nhé:\n"
            f"{settings.donate_bank_name} — {settings.donate_bank_account} "
            f"(MB Bank)\nCảm ơn đã đọc! Theo dõi để không lỡ chương mới.")


def _donate_qr(dest: Path) -> Path | None:
    """Tải ảnh VietQR (không cần key) về cache để chèn vào PDF."""
    if not settings.donate_bank_account or not settings.donate_bank_bin:
        return None
    if dest.exists():
        return dest
    url = (f"https://img.vietqr.io/image/{settings.donate_bank_bin}-"
           f"{settings.donate_bank_account}-compact2.png?accountName="
           + urllib.parse.quote(settings.donate_bank_name or ""))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        if len(data) > 3000:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return dest
    except Exception:  # noqa: BLE001 — không có QR vẫn xuất được truyện
        pass
    return None


# --------------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------------- #
def run(job: JobRecord, progress) -> None:
    params = job.params
    series = str(params.get("series") or "").strip()
    world = str(params.get("world") or "").strip()
    if not series or not world:
        raise ValueError("Cần 'series' (tên bộ) và 'world' (thế giới).")
    n_new = max(1, min(20, int(params.get("chapters") or 1)))
    words = max(800, min(4000, int(params.get("words") or 1800)))

    art_dir = settings.outputs_dir / "story" / _slug(series)
    ch_dir = art_dir / "chapters"
    ch_dir.mkdir(parents=True, exist_ok=True)
    job.artifacts_dir = str(art_dir)

    # 1) Bible: dựng 1 lần, bền theo bộ (user sửa được giữa các lần chạy).
    bible_path = art_dir / "bible.json"
    if bible_path.exists():
        bible = json.loads(bible_path.read_text(encoding="utf-8"))
        progress(5, f"Dùng bible sẵn có: {bible.get('title')}")
    else:
        progress(3, "Dựng bible (thế giới + nhân vật + tuyến truyện)")
        premise = str(params.get("premise") or "")
        # VIẾT THEO GU TỪNG NỀN: nếu job chỉ định nền đích, nhét gợi ý thể loại +
        # gu độc giả của nền đó vào premise -> AURA chọn bối cảnh/giọng văn hợp
        # nơi sẽ đăng, thay vì viết một kiểu rồi rải khắp nơi.
        plat = str(params.get("platform") or "").strip()
        if plat:
            try:
                from factory.platform_rules import genre_hint
                hint = genre_hint(plat)
                if hint:
                    premise = f"{premise}\n\n{hint}".strip()
                    progress(4, f"Bám gu nền: {plat}")
            except Exception:  # noqa: BLE001 — thiếu luật nền không được chặn viết
                pass
        bible = _build_bible(world, premise)
        bible_path.write_text(json.dumps(bible, ensure_ascii=False, indent=2), encoding="utf-8")
    bible_ctx = _bible_context(bible)
    title = str(bible.get("title") or series)

    # Trạng thái bền (Truth Files): arc_progress + characters_state + tóm tắt cuối.
    state_path = art_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    existing = sorted(ch_dir.glob("ch_*.md"))
    start_num = len(existing) + 1
    if start_num > 1 and not state.get(f"tail_{start_num - 1}"):
        last_ch = ch_dir / f"ch_{start_num - 1:04d}.md"
        if last_ch.exists():
            content_ch = last_ch.read_text(encoding="utf-8")
            state[f"tail_{start_num - 1}"] = content_ch[-2500:].strip() if len(content_ch) > 2500 else content_ch.strip()
            state["last_body_tail"] = state[f"tail_{start_num - 1}"]

    # 2) Viết n_new chương mới, checkpoint từng chương + cập nhật canon.
    donate = _donate_text()
    for i in range(n_new):
        chap_num = start_num + i
        if job_queue.is_cancelled(job.id):
            raise JobCancelled()
        pct = 8 + int(78 * i / n_new)
        progress(pct, f"Viết chương {chap_num} (bộ {title})")
        mem_ctx = _story_memory_ctx(state, chap_num, bible)          # canon SỐNG, không chỉ chương trước
        ch_title, body, summary = _write_chapter(bible_ctx, mem_ctx, chap_num, words)
        (ch_dir / f"ch_{chap_num:04d}.md").write_text(
            f"# {ch_title}\n\n{body}{donate}\n", encoding="utf-8")
        state["last_summary"] = summary
        state[f"summary_{chap_num}"] = summary
        state[f"tail_{chap_num}"] = body[-2500:].strip() if len(body) > 2500 else body.strip()
        state["last_body_tail"] = state[f"tail_{chap_num}"]
        # Cập nhật Truth Files (arc + trạng thái nhân vật) để chương sau không lạc mạch.
        progress(pct + 2, f"Cập nhật canon sau chương {chap_num}")
        state = _update_truth(bible_ctx, state, ch_title, body)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3) Đóng PDF + EPUB toàn bộ (chèn QR donate cuối sách).
    progress(90, "Đóng gói PDF + EPUB")
    packaged: list[tuple[str, str]] = []
    for f in sorted(ch_dir.glob("ch_*.md")):
        content = f.read_text(encoding="utf-8")
        first, _, rest = content.partition("\n")
        packaged.append((first.lstrip("# ").strip(), rest.strip()))
    slug = _slug(series)
    qr = _donate_qr(art_dir / "donate_qr.png")
    if qr:   # thêm "trang cảm ơn" có QR vào cuối sách
        packaged.append(("Ủng hộ tác giả", f"Quét mã QR để ủng hộ (ảnh: {qr.name}).\n"
                         f"{settings.donate_bank_name} — {settings.donate_bank_account} (MB Bank)"))
    author = str(getattr(settings, "author_pen_name", "") or "")
    pdfkit.chapters_to_pdf(packaged, art_dir / f"{slug}.pdf", title, author=author)
    pdfkit.chapters_to_epub(packaged, art_dir / f"{slug}.epub", title, author=author)

    (art_dir / "package_info.json").write_text(json.dumps({
        "title": title, "total_chapters": len(list(ch_dir.glob("ch_*.md"))),
        "new_this_run": n_new,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_posting_guide(art_dir, title)   # file grab-and-go cho Sếp đăng tay
    progress(100, f"Xong — bộ '{title}' giờ có {start_num + n_new - 1} chương")


# --------------------------------------------------------------------------- #
# QC riêng cho truyện TỰ VIẾT. Trước dùng chung qc_novel của tool DỊCH truyện
# (đếm 'chương dịch vào sách' từ package_info kiểu khác) -> "0/0 chương" ->
# MỌI job viết chương đều treo needs_review oan dù chương ổn. Cùng họ bug với
# qc story.video ngày trước. Bộ này kiểm đúng thứ story.factory tạo ra.
# --------------------------------------------------------------------------- #
def qc_story(job: JobRecord) -> QCReport:
    art = Path(job.artifacts_dir or "")
    pkg = art / "package_info.json"
    if not pkg.is_file():
        return QCReport(passed=False, checks=[
            {"name": "package", "ok": False, "note": "Chưa có package_info.json."}])
    try:
        info = json.loads(pkg.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return QCReport(passed=False, checks=[
            {"name": "package", "ok": False, "note": f"package_info hỏng: {exc}"}])
    checks: list[dict] = []
    ok = True

    total = int(info.get("total_chapters") or 0)
    new = int(info.get("new_this_run") or 0)
    grew = total >= 1 and new >= 1
    checks.append({"name": "có chương mới", "ok": grew,
                   "note": f"bộ {total} chương, lượt này +{new}"})
    ok &= grew

    # Chương mới nhất phải đủ dày (sàn từ ~70% mục tiêu autopilot).
    chs = sorted((art / "chapters").glob("ch_*.md"))
    if chs:
        body = chs[-1].read_text(encoding="utf-8").split("─────")[0]
        wc = len(body.split())
        floor = int(int(getattr(settings, "story_autopilot_words", 1800)) * 0.7)
        deep = wc >= floor
        checks.append({"name": "chương đủ dày", "ok": deep,
                       "note": f"{chs[-1].name}: {wc} từ (sàn {floor})"})
        ok &= deep
    else:
        checks.append({"name": "chương đủ dày", "ok": False, "note": "không thấy file chương"})
        ok = False

    pdfs = list(art.glob("*.pdf"))
    if pdfs:
        try:
            from pypdf import PdfReader
            n = len(PdfReader(str(pdfs[0])).pages)
            checks.append({"name": "pdf mở được", "ok": n >= 1, "note": f"{n} trang"})
            ok &= n >= 1
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": "pdf mở được", "ok": False, "note": str(exc)})
            ok = False
    else:
        checks.append({"name": "pdf mở được", "ok": False, "note": "thiếu PDF"})
        ok = False
    return QCReport(passed=bool(ok), checks=checks)


register_checker("story", qc_story)


_DARK_MARKERS = ("máu", "hiến tế", "bạo lực", "giết", "tà", "ma đạo", "ma đầu",
                 "địa ngục", "diệt", "thảm sát", "báo thù", "hắc ám")


def _write_posting_guide(art_dir: Path, title: str) -> None:
    """Ghi HƯỚNG DẪN ĐĂNG theo ĐÚNG mẫu form 'Chi Tiết Truyện' của Wattpad —
    Sếp điền từng ô 1-1. Tự nhận Fanfic (đồng nhân) vs Hư cấu (nguyên bản) +
    gợi ý xếp loại trưởng thành theo tông truyện. Tự làm lại mỗi lần viết thêm."""
    import time as _t
    kit = art_dir / "publish_kit"
    van_an = tags = genre = ""
    cover = "(chưa có — story.kit sẽ vẽ; xem publish_kit/cover.png)"
    ki = kit / "kit_info.json"
    if ki.exists():
        try:
            d = json.loads(ki.read_text(encoding="utf-8"))
            genre = str(d.get("genre") or "")
            if d.get("cover_ok"):
                cover = str((kit / "cover.png"))
        except Exception:  # noqa: BLE001
            pass
    if (kit / "van_an.md").exists():
        van_an = (kit / "van_an.md").read_text(encoding="utf-8")
    if (kit / "tags.txt").exists():
        tags = (kit / "tags.txt").read_text(encoding="utf-8")

    # Đọc bible: nhân vật chính + tông + nhận diện đồng nhân.
    bible = {}
    bp = art_dir / "bible.json"
    if bp.exists():
        try:
            bible = json.loads(bp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            bible = {}
    main = bible.get("main", {})
    cast = bible.get("cast", []) or []
    chars = [str(main.get("name") or "").strip()] + \
            [str(c.get("name") or "").strip() for c in cast[:4]]
    chars = [c for c in chars if c]

    blob = (art_dir.name + " " + json.dumps(bible, ensure_ascii=False)).lower().replace("_", " ")
    is_fanfic = "đồng nhân" in blob or "fanfic" in blob or "dong nhan" in blob
    loai = "Fanfic" if is_fanfic else "Hư cấu"
    tone_blob = (str(bible.get("tone", "")) + str(bible.get("world", "")) +
                 str(bible.get("logline", "")) + van_an).lower()
    mature = any(m in tone_blob for m in _DARK_MARKERS)
    xep_loai = ("Trưởng Thành (bật — truyện có yếu tố tối/bạo lực)" if mature
                else "Mọi đối tượng (không bật Trưởng Thành)")

    rows = []
    for f in sorted((art_dir / "chapters").glob("ch_*.md")):
        first = f.read_text(encoding="utf-8").split("\n", 1)[0].lstrip("#* ").rstrip("* ").strip()
        rows.append(f"- [ ] {first}  →  `{f}`")

    fanfic_note = ("\n> ⚠️ Đây là ĐỒNG NHÂN (fanfic) — ở ô 'Loại hình văn bản' CHỌN "
                   "**Fanfic**, KHÔNG chọn Hư cấu. Bản quyền để 'Bảo Lưu Mọi Quyền' cho "
                   "phần sáng tạo của mình, nhưng nhớ đây là tác phẩm phái sinh.\n"
                   if is_fanfic else
                   "\n> ✅ Đây là truyện NGUYÊN BẢN — ô 'Loại hình văn bản' chọn **Hư cấu**, "
                   "bản quyền 'Bảo Lưu Mọi Quyền' (All Rights Reserved).\n")

    pen = getattr(settings, 'author_pen_name', '') or ''
    guide = f"""# 📤 HƯỚNG DẪN ĐĂNG WATTPAD: {title}
*Tác giả: {pen} — cập nhật {_t.strftime('%d/%m/%Y %H:%M')}*

Điền form **"Chi Tiết Truyện"** trên Wattpad theo từng ô dưới đây (làm 1 lần khi tạo truyện):
{fanfic_note}
| Ô trên Wattpad | Điền |
|---|---|
| **Tiêu đề** | {title} |
| **Ảnh bìa** (512×800) | `{cover}` |
| **Ngôn ngữ** | Tiếng Việt |
| **Loại hình văn bản** | **{loai}**{' → rồi chọn thể loại: ' + genre if genre else ''} |
| **Bản quyền** | Bảo Lưu Mọi Quyền (All Rights Reserved) |
| **Xếp loại** | {xep_loai} |
| **Các nhân vật chính** | {', '.join(chars) if chars else '(xem bible)'} |
| **Độc giả Mục tiêu** | Độc giả truyện {genre or 'tu tiên/huyền huyễn'}, thích {loai.lower()} |

## Mô tả — copy dán vào ô "Mô tả":
{van_an or '(chưa có — story.kit sẽ viết)'}

## Tags — copy dán vào ô "Tags" (cách nhau bằng dấu cách):
{tags or '(chưa có — story.kit sẽ tạo)'}

## Đăng từng chương (tick [x] khi đã đăng):
{chr(10).join(rows) if rows else '(chưa có chương)'}

> Mẹo: mở file .md của chương, copy toàn bộ (đã có sẵn dòng donate cuối chương), dán vào Wattpad.
"""
    (art_dir / "HƯỚNG_DẪN_ĐĂNG.md").write_text(guide, encoding="utf-8")


SPEC = ToolSpec(
    name="story.factory",
    label_vi="Viết truyện (AURA tự sáng tác)",
    description="AURA tự viết truyện dài kỳ (tu tiên gốc / đồng nhân): dựng bible "
                 "thế giới+nhân vật, viết từng chương có trí nhớ mạch truyện, đóng "
                 "PDF/EPUB + chèn donate. Chạy lại nhiều lần để viết tiếp chương mới. "
                 "Lần đầu nên viết 1 chương để chấm giọng văn trước.",
    product_line="story",
    form_fields=(
        FormField(key="series", label="Tên bộ (thư mục lưu, vd Dau-La-Dong-Nhan)",
                  placeholder="Đấu La Đồng Nhân"),
        FormField(key="world", label="Thế giới / bối cảnh",
                  placeholder="Đồng nhân Đấu La Đại Lục"),
        FormField(key="premise", label="Ý tưởng / nhân vật chính (bỏ trống = AURA tự nghĩ)",
                  type="textarea", required=False),
        FormField(key="chapters", label="Số chương viết lần này", type="number",
                  default=1, required=False),
        FormField(key="words", label="Độ dài mỗi chương (từ)", type="number",
                  default=1800, required=False),
    ),
    handler=run,
    experimental=True,
)

__all__ = ["SPEC", "run"]
