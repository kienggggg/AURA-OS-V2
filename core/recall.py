"""TRÍ NHỚ BIẾT CHỌN — cổng [Retrieve] + HyDE + cổng [IsREL].

Rút từ đợt sàng 06/08/2026, nơi **4 video độc lập** cùng chỉ vào một chỗ:
HyDE · LLM Wiki (Karpathy) · ZeroMem · Self-RAG (paper ICLR 2024).

Ba bệnh của cách lục trí nhớ cũ trong AURA:

1. **Lúc nào cũng lục.** Sếp chào "hi" cũng đi tra ChromaDB rồi nhồi ngữ cảnh vào
   prompt. Tốn token cho việc vô ích.
2. **Hỏi sao lục vậy.** Câu hỏi ngắn ("wifi?") khác xa văn phong của ký ức đã lưu
   nên embedding khớp kém. → **HyDE**: bảo LLM viết một câu trả lời GIẢ, rồi đem
   chính nó đi tìm — câu trả lời giả trông giống tài liệu thật nên khớp tốt hơn.
3. **Lấy về là tin.** `search_memory` vứt bỏ `distances` nên ký ức lạc đề vẫn được
   nhồi vào prompt. → **cổng [IsREL]**: có điểm rồi thì loại thứ quá xa.

Triết lý giữ nguyên như các lần áp công nghệ trước: **lấy tư tưởng, tự viết glue
nhẹ, không ôm cả framework**. Không thêm phụ thuộc nào.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Iterable

logger = logging.getLogger(__name__)

# Câu KHÔNG cần lục trí nhớ — chào hỏi, xác nhận, cảm thán.
_NO_RECALL = {
    "hi", "hello", "chào", "chao", "ok", "oke", "okay", "ừ", "u", "uh", "vâng",
    "vang", "y", "yes", "no", "không", "khong", "cảm ơn", "cam on", "thanks",
    "tks", "được", "duoc", "rồi", "roi", "xong", "tốt", "tot", "ngon", "đúng",
    "dung", "sai", "tiếp", "tiep", "next", "dừng", "dung lai", "stop",
}
# Lệnh điều khiển — trả lời bằng hành động, không cần ký ức cũ.
_COMMAND_HINTS = (
    "tạm ngừng", "tam ngung", "bật lại", "bat lai", "mở ", "mo ", "chạy ", "chay ",
    "tắt ", "tat ", "khởi động", "khoi dong", "restart", "ngủ đông", "ngu dong",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def should_retrieve(text: str) -> bool:
    """Cổng [Retrieve] — có đáng lục trí nhớ không? Thuần heuristic, TỐN 0 TOKEN.

    Thà lục thừa còn hơn quên mất ngữ cảnh, nên mặc định là CÓ; chỉ chặn các
    trường hợp rõ ràng vô ích.
    """
    t = _norm(text)
    if not t:
        return False
    if t.strip("!?. ") in _NO_RECALL:
        return False
    # Quá ngắn mà không có dấu hỏi -> nhiều khả năng là xác nhận, không phải câu hỏi.
    if len(t) <= 3 and "?" not in t:
        return False
    if any(t.startswith(h) for h in _COMMAND_HINTS):
        return False
    return True


def should_remember(text: str) -> bool:
    """Có đáng LƯU mẩu này vào trí nhớ không?

    ĐO THẬT 06/08/2026 trên kho ký ức của AURA: 226 mẩu hội thoại, trong đó đầy
    thứ rỗng nghĩa như "xin chào" / "Vâng, sếp cần em hỗ trợ gì ạ?". Mấy mẩu này
    **khớp với mọi câu hỏi** (kể cả "công thức nấu phở") vì chúng không mang thông
    tin gì — làm hỏng mọi phép lọc theo điểm ở khâu đọc.

    Kết luận: bệnh nằm ở lúc GHI, không phải lúc ĐỌC. Chặn rác ngay từ đầu vào.
    """
    t = _norm(text)
    if len(t) < 12:                     # quá ngắn -> không có nội dung để nhớ
        return False
    if t.strip("!?. ") in _NO_RECALL:
        return False
    # Câu xã giao mở đầu, không mang thông tin.
    if re.match(r"^(xin chào|chào |vâng[,. ]|dạ[,. ]|ok[,. ])", t) and len(t) < 40:
        return False
    return True


def hyde_expand(text: str, complete: Callable[[str, str], str] | None) -> str:
    """HyDE — bảo LLM viết câu trả lời GIẢ để đem đi tìm thay cho câu hỏi trần.

    `complete(prompt, system) -> str`. Không có LLM / LLM hỏng / trả rỗng thì
    **lùi về câu gốc** — không bao giờ để HyDE làm hỏng việc tìm kiếm.
    """
    q = (text or "").strip()
    if not q or complete is None:
        return q
    system = (
        "Bạn viết một đoạn NGẮN (1-2 câu) trông như trích từ ghi chú/tài liệu, "
        "trả lời giả định cho câu hỏi. Không rào đón, không nói 'tôi không biết', "
        "chỉ viết nội dung. Được phép đoán — đoạn này chỉ dùng để TÌM KIẾM."
    )
    try:
        draft = (complete(q, system) or "").strip()
    except Exception as exc:  # noqa: BLE001 — HyDE hỏng KHÔNG được làm hỏng recall
        logger.warning("HyDE lỗi, dùng câu gốc: %s", exc)
        return q
    if not draft:
        return q
    # Ghép cả câu hỏi gốc: giữ được từ khoá riêng (tên người, tên file) mà bản
    # giả có thể làm rơi mất.
    return f"{q}\n{draft[:600]}"


def filter_relevant(
    scored: Iterable[tuple[object, float]], max_distance: float
) -> list[object]:
    """Cổng [IsREL] — bỏ ký ức quá xa câu hỏi.

    ChromaDB: khoảng cách càng NHỎ càng giống. Ngưỡng để RỘNG (mặc định nới) vì
    lọc quá gắt sẽ làm AURA "quên sạch" — hỏng còn tệ hơn nhồi thừa.
    """
    out = []
    for rec, dist in scored:
        if dist is None or dist <= max_distance:
            out.append(rec)
    return out


def smart_recall(
    store,
    query: str,
    collection=None,
    k: int | None = None,
    complete: Callable[[str, str], str] | None = None,
    max_distance: float | None = None,
    use_hyde: bool | None = None,
) -> list:
    """Lục trí nhớ có chọn lọc: [Retrieve] -> HyDE -> tìm -> [IsREL].

    Hỏng ở bất kỳ khâu nào cũng **lùi về cách cũ**, không ném lỗi ra ngoài.
    """
    try:
        from core.config import settings
    except Exception:  # noqa: BLE001
        settings = None

    def _s(name, default):
        return getattr(settings, name, default) if settings is not None else default

    if not _s("recall_smart_enabled", True):
        return _plain(store, query, collection, k)
    if not should_retrieve(query):
        return []

    if use_hyde is None:
        use_hyde = bool(_s("recall_hyde_enabled", False))
    if max_distance is None:
        max_distance = float(_s("recall_max_distance", 1.20))

    search_query = hyde_expand(query, complete) if use_hyde else query

    try:
        scored = store.search_scored(search_query, collection, k) if collection is not None \
            else store.search_scored(search_query, k=k)
    except Exception as exc:  # noqa: BLE001 — không có search_scored -> cách cũ
        logger.warning("search_scored lỗi (%s) — lùi về search thường.", exc)
        return _plain(store, search_query, collection, k)

    kept = filter_relevant(scored, max_distance)
    if scored and not kept:
        # Lọc sạch trơn thì giữ lại cái GẦN NHẤT — thà thừa một mẩu còn hơn mù.
        kept = [min(scored, key=lambda p: p[1])[0]]
    return kept


def _plain(store, query, collection, k):
    try:
        if collection is not None:
            return store.search_memory(query, collection, k)
        return store.search_memory(query, k=k)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Recall thường cũng lỗi (bỏ ngữ cảnh): %s", exc)
        return []
