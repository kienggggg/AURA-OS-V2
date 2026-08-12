"""
core/memory.py
==============
MemoryStore — "Cuốn vở ghi chép" của AURA, lưu trên ChromaDB (persistent).

Vai trò: nguồn sự thật DUY NHẤT cho ký ức của AURA (đã bỏ hẳn mem0). Lưu vật lý
ra đĩa nên restart máy không mất trí nhớ.

Ba collection tách bạch theo mục đích:
  - "conversation"     : lịch sử hội thoại user/assistant (RAG ngữ cảnh ngắn hạn).
  - "user_preferences" : hồ sơ của Sếp (thích Gunpla, code Vibe Coding...).
  - "system_rules"     : bài học lỗi→giải pháp (vd bug regex float) để RAG lại
                         cho Coder Agent, tránh lặp sai lầm cũ.

Mọi thao tác vào/ra đều đi qua schema `MemoryRecord` (xem core/schemas.py),
không truyền dict trần — để dữ liệu luôn được validate tại biên.

Embedding: mặc định dùng DefaultEmbeddingFunction của ChromaDB (all-MiniLM-L6-v2
chạy local qua ONNX, không cần GPU/torch). Có thể đổi sang Ollama embedding
(nomic-embed-text) bằng tham số `embedding_backend="ollama"`.

Cài đặt phụ thuộc:
    pip install chromadb
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from core.config import settings
from core.schemas import MemoryRecord

if TYPE_CHECKING:  # chỉ để type-hint, không bắt buộc import lúc runtime
    import chromadb
    from chromadb.api.models.Collection import Collection

logger = logging.getLogger("aura.memory")


class CollectionName(str, Enum):
    """Tên 3 collection — dùng Enum để tránh gõ sai chuỗi rải rác trong code."""

    CONVERSATION = "conversation"
    USER_PREFERENCES = "user_preferences"
    SYSTEM_RULES = "system_rules"
    KNOWLEDGE = "knowledge"
    PROFILE = "profile"        # Chân dung Sếp (upsert theo id ổn định)


class MemoryStore:
    """
    Bọc ChromaDB PersistentClient và 3 collection của AURA.

    Cách dùng:
        store = MemoryStore()                      # embedding local mặc định
        store.remember_preference("Thích Gunpla Real Grade", tags=["gunpla"])
        prefs = store.recall_preferences("sở thích mô hình")
    """

    def __init__(self, embedding_backend: str = "default") -> None:
        """
        Khởi tạo client + 3 collection.

        Args:
            embedding_backend: "default" (all-MiniLM-L6-v2 local qua ONNX) hoặc
                "ollama" (gọi Ollama embedding theo settings.ollama_host).
        """
        try:
            import chromadb
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Thiếu thư viện 'chromadb'. Cài bằng: pip install chromadb"
            ) from exc

        # Đảm bảo thư mục lưu trữ tồn tại trước khi mở client.
        settings.chroma_path.mkdir(parents=True, exist_ok=True)

        # PersistentClient: lưu vật lý ra đĩa → bền vững qua các lần restart.
        self._client = chromadb.PersistentClient(path=str(settings.chroma_path))
        self._embedding_fn = self._build_embedding_function(embedding_backend)

        # Tạo (hoặc lấy lại) cả 3 collection. metadata hnsw:space=cosine cho
        # độ tương đồng văn bản tốt hơn khoảng cách L2 mặc định.
        self._collections: dict[CollectionName, "Collection"] = {
            name: self._client.get_or_create_collection(
                name=name.value,
                embedding_function=self._embedding_fn,
                metadata={"hnsw:space": "cosine"},
            )
            for name in CollectionName
        }
        logger.info(
            "MemoryStore sẵn sàng tại %s (embedding=%s)",
            settings.chroma_path,
            embedding_backend,
        )

    # ------------------------------------------------------------------ #
    # Khởi tạo embedding function
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_embedding_function(backend: str) -> Any:
        """
        Tạo embedding function theo backend yêu cầu.

        - "default": DefaultEmbeddingFunction — model all-MiniLM-L6-v2 tải về một
          lần rồi chạy local hoàn toàn qua onnxruntime. Không cần GPU.
        - "ollama" : OllamaEmbeddingFunction — đẩy việc nhúng sang Ollama server
          cục bộ (cần `ollama pull nomic-embed-text` trước).
        """
        from chromadb.utils import embedding_functions

        normalized = backend.lower().strip()
        if normalized == "ollama":
            return embedding_functions.OllamaEmbeddingFunction(
                url=f"{settings.ollama_host}/api/embeddings",
                model_name="nomic-embed-text",
            )
        if normalized == "default":
            return embedding_functions.DefaultEmbeddingFunction()
        raise ValueError(
            f"embedding_backend không hợp lệ: {backend!r}. Chọn 'default' hoặc 'ollama'."
        )

    # ------------------------------------------------------------------ #
    # Tiện ích nội bộ
    # ------------------------------------------------------------------ #
    def _get(self, collection: CollectionName) -> "Collection":
        """Lấy đối tượng collection theo Enum (đã tạo sẵn ở __init__)."""
        return self._collections[collection]

    @staticmethod
    def _record_from_chroma(
        record_id: str, document: str, metadata: dict[str, Any]
    ) -> MemoryRecord:
        """
        Dựng lại MemoryRecord từ dữ liệu thô ChromaDB trả về.

        Đảo ngược đúng những gì MemoryRecord.to_chroma_metadata() đã làm:
        ISO string → datetime, chuỗi tags nối bằng dấu phẩy → list[str].
        """
        tags_raw = metadata.get("tags", "") or ""
        tags = [t for t in tags_raw.split(",") if t]

        ts_raw = metadata.get("timestamp")
        timestamp = (
            datetime.fromisoformat(ts_raw)
            if isinstance(ts_raw, str)
            else datetime.now()
        )

        return MemoryRecord(
            id=record_id,
            role=metadata.get("role", "system"),
            text=document,
            timestamp=timestamp,
            tags=tags,
        )

    # ------------------------------------------------------------------ #
    # API cốt lõi
    # ------------------------------------------------------------------ #
    def add_memory(
        self,
        record: MemoryRecord,
        collection: CollectionName = CollectionName.CONVERSATION,
    ) -> str:
        """
        Ghi một MemoryRecord vào collection chỉ định.

        Returns:
            id của bản ghi (để truy vết / xoá sau này).
        """
        col = self._get(collection)
        col.add(
            ids=[record.id],
            documents=[record.text],
            metadatas=[record.to_chroma_metadata()],
        )
        logger.debug("Đã lưu memory %s vào '%s'", record.id, collection.value)
        return record.id

    def search_memory(
        self,
        query: str,
        collection: CollectionName = CollectionName.CONVERSATION,
        k: int | None = None,
        role: str | None = None,
    ) -> list[MemoryRecord]:
        """
        Truy vấn ngữ nghĩa các ký ức gần nhất với `query`.

        Args:
            query: câu truy vấn (thường là input mới nhất của người dùng).
            collection: collection cần tìm.
            k: số kết quả; mặc định lấy settings.memory_recall_k.
            role: nếu set, chỉ lọc bản ghi có role tương ứng (vd "feedback").

        Returns:
            Danh sách MemoryRecord, gần nhất xếp trước. Rỗng nếu không có gì.
        """
        col = self._get(collection)
        n_results = k if k is not None else settings.memory_recall_k
        where = {"role": role} if role else None

        result = col.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
        )

        # ChromaDB trả về dạng list-of-lists (một list con cho mỗi query_text).
        # Ta chỉ gửi 1 query nên lấy phần tử [0]. Có thể rỗng nếu collection trống.
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]

        records: list[MemoryRecord] = []
        for rid, doc, meta in zip(ids, documents, metadatas):
            records.append(self._record_from_chroma(rid, doc, meta or {}))
        return records

    def search_scored(
        self,
        query: str,
        collection: CollectionName = CollectionName.CONVERSATION,
        k: int | None = None,
        role: str | None = None,
    ) -> list[tuple[MemoryRecord, float]]:
        """Như search_memory nhưng TRẢ KÈM khoảng cách (càng NHỎ càng giống).

        search_memory vứt bỏ `distances` nên AURA không biết ký ức lấy ra có liên
        quan không — cứ đủ số lượng là nhồi vào prompt, kể cả thứ lạc đề. Hàm này
        giữ lại điểm để bên gọi tự lọc (cổng [IsREL] của Self-RAG).

        Không đổi search_memory cũ để khỏi gãy chỗ đang dùng.
        """
        col = self._get(collection)
        n_results = k if k is not None else settings.memory_recall_k
        where = {"role": role} if role else None

        result = col.query(query_texts=[query], n_results=n_results, where=where)
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        out: list[tuple[MemoryRecord, float]] = []
        for i, (rid, doc, meta) in enumerate(zip(ids, documents, metadatas)):
            dist = float(distances[i]) if i < len(distances) else 0.0
            out.append((self._record_from_chroma(rid, doc, meta or {}), dist))
        return out

    def _recall_filtered(
        self, query: str, collection: CollectionName, k: int | None = None
    ) -> list[MemoryRecord]:
        """Lục trí nhớ RỒI LỌC bỏ mẩu lạc đề (cổng [IsREL] của Self-RAG).

        Trước đây mọi recall_* đều nhồi đủ `k` mẩu vào prompt bất kể có liên quan
        hay không. Nay dùng điểm giống nhau để loại thứ quá xa.
        Tắt bằng `RECALL_SMART_ENABLED=false` -> quay về hành vi cũ y hệt.
        """
        if not getattr(settings, "recall_smart_enabled", True):
            return self.search_memory(query, collection, k=k)
        try:
            from core.recall import filter_relevant

            scored = self.search_scored(query, collection, k=k)
            max_dist = float(getattr(settings, "recall_max_distance", 1.20))
            kept = filter_relevant(scored, max_dist)
            if scored and not kept:
                # Lọc sạch trơn -> giữ mẩu gần nhất, thà thừa còn hơn mù.
                kept = [min(scored, key=lambda p: p[1])[0]]
            return kept
        except Exception as exc:  # noqa: BLE001 — lọc hỏng thì cứ trả như cũ
            logger.warning("Lọc ký ức lỗi (%s) — dùng recall thường.", exc)
            return self.search_memory(query, collection, k=k)

    # ------------------------------------------------------------------ #
    # Tiện ích cấp cao cho từng collection
    # ------------------------------------------------------------------ #
    def remember_turn(self, role: str, text: str) -> str:
        """Lưu một lượt hội thoại vào collection conversation — TRỪ rác xã giao.

        Đo thật 06/08/2026: 226 mẩu trong kho, đầy thứ rỗng nghĩa ("xin chào",
        "Vâng, sếp cần em hỗ trợ gì ạ?"). Chúng khớp với MỌI câu hỏi nên phá hỏng
        việc lọc theo điểm ở khâu đọc. Chặn từ đầu vào là cách chữa đúng gốc.

        Trả "" khi bỏ qua (không lưu). Tắt bằng RECALL_SMART_ENABLED=false.
        """
        if getattr(settings, "recall_smart_enabled", True):
            try:
                from core.recall import should_remember

                if not should_remember(text):
                    logger.debug("Bỏ qua lưu trí nhớ (xã giao/rỗng nghĩa): %.40s", text)
                    return ""
            except Exception:  # noqa: BLE001 — thiếu module thì cứ lưu như cũ
                pass
        record = MemoryRecord(role=role, text=text, tags=["turn"])
        return self.add_memory(record, CollectionName.CONVERSATION)

    def recall_context(self, query: str, k: int | None = None) -> list[MemoryRecord]:
        """Lấy ngữ cảnh hội thoại liên quan để chèn vào system prompt."""
        return self._recall_filtered(query, CollectionName.CONVERSATION, k)

    def remember_preference(self, text: str, tags: list[str] | None = None) -> str:
        """Lưu một sở thích/hồ sơ của người dùng vào user_preferences."""
        record = MemoryRecord(role="user", text=text, tags=tags or ["preference"])
        return self.add_memory(record, CollectionName.USER_PREFERENCES)

    def recall_preferences(self, query: str, k: int | None = None) -> list[MemoryRecord]:
        """Truy vấn hồ sơ người dùng (để tái cấu trúc system prompt theo sở thích)."""
        return self._recall_filtered(query, CollectionName.USER_PREFERENCES, k)

    def remember_rule(self, context: str, error: str, solution: str) -> str:
        """
        Lưu một bài học lỗi→giải pháp vào system_rules (cơ chế RL từ feedback).

        Ví dụ: context='bóc tách chapter manga', error='int() chết với 10.5',
        solution='dùng float()'. Coder Agent sẽ RAG lại trước khi sinh code.
        """
        text = (
            f"BỐI CẢNH: {context}\n"
            f"LỖI: {error}\n"
            f"GIẢI PHÁP: {solution}"
        )
        record = MemoryRecord(role="feedback", text=text, tags=["rule"])
        return self.add_memory(record, CollectionName.SYSTEM_RULES)

    def recall_rules(self, query: str, k: int | None = None) -> list[MemoryRecord]:
        """Truy vấn các bài học liên quan để tránh lặp lại lỗi cũ khi sinh code."""
        return self._recall_filtered(query, CollectionName.SYSTEM_RULES, k)

    def remember_knowledge(self, text: str, tags: list[str] | None = None) -> str:
        """Lưu một mảnh tri thức (AURA tự đọc sách) vào collection knowledge."""
        record = MemoryRecord(role="system", text=text, tags=tags or ["knowledge"])
        return self.add_memory(record, CollectionName.KNOWLEDGE)

    def recall_knowledge(self, query: str, k: int | None = None) -> list[MemoryRecord]:
        """Tra kho tri thức đã đọc để bồi đắp câu trả lời/hành động (RAG)."""
        return self._recall_filtered(query, CollectionName.KNOWLEDGE, k)

    def upsert_memory(
        self,
        record: MemoryRecord,
        collection: CollectionName = CollectionName.PROFILE,
    ) -> str:
        """
        GHI ĐÈ (upsert) một MemoryRecord theo id ỔN ĐỊNH: id trùng -> cập nhật tại chỗ,
        KHÔNG sinh bản trùng. Dùng cho Chân dung Sếp (mỗi fact một id cố định, vd
        'weakness:overuse'). Khác add_memory (luôn thêm mới với id ngẫu nhiên).
        """
        col = self._get(collection)
        col.upsert(
            ids=[record.id],
            documents=[record.text],
            metadatas=[record.to_chroma_metadata()],
        )
        logger.debug("Đã upsert memory %s vào '%s'", record.id, collection.value)
        return record.id

    def recall_profile(self, query: str, k: int | None = None) -> list[MemoryRecord]:
        """Truy vấn ngữ nghĩa các mẩu Chân dung Sếp liên quan (để nhồi vào prompt)."""
        return self._recall_filtered(query, CollectionName.PROFILE, k)

    # ------------------------------------------------------------------ #
    # Bảo trì
    # ------------------------------------------------------------------ #
    def count(self, collection: CollectionName) -> int:
        """Đếm số bản ghi trong một collection (tiện cho test/giám sát)."""
        return self._get(collection).count()

    def reset_collection(self, collection: CollectionName) -> None:
        """
        Xoá sạch một collection rồi tạo lại rỗng. Dùng cho test hoặc khi cần
        làm mới hoàn toàn một loại ký ức. CẨN THẬN: không thể hoàn tác.
        """
        self._client.delete_collection(collection.value)
        self._collections[collection] = self._client.get_or_create_collection(
            name=collection.value,
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        logger.warning("Đã reset collection '%s'", collection.value)


__all__ = ["MemoryStore", "CollectionName"]