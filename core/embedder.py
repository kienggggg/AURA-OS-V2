"""
core/embedder.py
================
CÔNG NHÂN embedding — model nhỏ đa ngôn ngữ (~118M tham số, int8 ONNX, CPU-only).

Triết lý "quản gia giao tool cho công nhân": model nhỏ KHÔNG suy luận, KHÔNG sinh
văn bản — chỉ trả lời MỘT câu hỏi đóng: "hai đoạn văn giống nhau cỡ nào?"
(embedding + cosine). Pipeline (job_scout, tin tức, MemoryStore...) cầm tool,
gọi công nhân đúng ở bước cần phán đoán mờ, xong việc thì nhả RAM.

Model: paraphrase-multilingual-MiniLM-L12-v2 (bản ONNX của Xenova, hỗ trợ tiếng
Việt), tải 1 lần (~120MB) về data/models/embed/, chạy onnxruntime CPU.
RAM ~150-200MB CHỈ KHI load; load lười lần gọi đầu, unload()/maybe_unload(TTL)
để giữ footprint nền ~384MB của AURA.

Cách dùng:
    from core.embedder import get_worker
    w = get_worker()
    emb = w.embed(["Python automation job", "tuyển lập trình viên"])  # (2, 384)
    sim = emb[0] @ emb[1]        # cosine (embedding đã chuẩn hoá L2)
    w.unload()                   # trả RAM khi xong việc
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger("aura.workers.embed")

_DEFAULT_REPO = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"
_ONNX_FILE = "onnx/model_quantized.onnx"
_TOKENIZER_FILE = "tokenizer.json"
_MAX_TOKENS = 128          # tiêu đề + tóm tắt ngắn; cắt bớt cho nhanh
_DEFAULT_TTL_S = 300.0     # 5 phút không ai gọi -> maybe_unload() nhả RAM


def _models_dir() -> Path:
    try:
        from core.config import settings
        return Path(settings.worker_models_dir)
    except Exception:  # noqa: BLE001 — thiếu config vẫn chạy được (đường dẫn mặc định)
        return Path(__file__).resolve().parent.parent / "data" / "models"


class EmbedWorker:
    """Bọc ONNX session + tokenizer; thread-safe; load lười, nhả RAM chủ động."""

    def __init__(self, repo: str = _DEFAULT_REPO):
        self._repo = repo
        self._lock = threading.Lock()
        self._session = None
        self._tokenizer = None
        self._last_used = 0.0
        self._pinned = 0        # >0 khi TỔ TRƯỞNG đang giữ model cho cả ca (đừng nhả giữa chừng)

    # ------------------------------------------------------------------ #
    # Nạp / nhả
    # ------------------------------------------------------------------ #
    def _download(self) -> tuple[Path, Path]:
        """Tải model + tokenizer về data/models/embed/ (chỉ tốn mạng lần đầu).

        Có sẵn file local -> dùng luôn, KHÔNG gọi mạng: công nhân phải chạy được
        cả khi offline (chỉ lần tải đầu tiên mới cần internet).
        """
        target = _models_dir() / "embed"
        onnx_path = target / _ONNX_FILE
        tok_path = target / _TOKENIZER_FILE
        if onnx_path.is_file() and tok_path.is_file():
            return onnx_path, tok_path
        from huggingface_hub import hf_hub_download
        target.mkdir(parents=True, exist_ok=True)
        onnx_path = Path(hf_hub_download(self._repo, _ONNX_FILE, local_dir=target))
        tok_path = Path(hf_hub_download(self._repo, _TOKENIZER_FILE, local_dir=target))
        return onnx_path, tok_path

    def _ensure_loaded(self) -> None:
        if self._session is not None:
            return
        import onnxruntime as ort
        from tokenizers import Tokenizer
        t0 = time.monotonic()
        onnx_path, tok_path = self._download()
        tok = Tokenizer.from_file(str(tok_path))
        tok.enable_truncation(max_length=_MAX_TOKENS)
        tok.enable_padding()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2   # công nhân không được chiếm hết CPU của Sếp
        self._session = ort.InferenceSession(
            str(onnx_path), opts, providers=["CPUExecutionProvider"]
        )
        self._tokenizer = tok
        logger.info("EmbedWorker nạp %s trong %.1fs.", self._repo, time.monotonic() - t0)

    def pin(self) -> None:
        """TỔ TRƯỞNG ghim model trước một ca nhiều công nhân -> nạp 1 lần cho cả tổ.

        Khi đã ghim, unload() thường của từng công nhân (gọi trong finally) thành no-op,
        nên model KHÔNG bị nạp-nhả lặp lại giữa các công nhân trong cùng ca."""
        with self._lock:
            self._pinned += 1

    def unpin(self) -> None:
        with self._lock:
            if self._pinned > 0:
                self._pinned -= 1

    def unload(self, force: bool = False) -> None:
        """Nhả RAM ngay (gọi khi pipeline xong việc). Đang bị ghim thì bỏ qua (trừ force)."""
        with self._lock:
            if self._pinned and not force:
                return
            if self._session is not None:
                self._session = None
                self._tokenizer = None
                logger.info("EmbedWorker đã nhả RAM.")

    def maybe_unload(self, ttl_s: float = _DEFAULT_TTL_S) -> None:
        """Nhả RAM nếu quá TTL không ai dùng (cho caller giữ worker lâu dài)."""
        with self._lock:
            if self._pinned:
                return
            if self._session is not None and time.monotonic() - self._last_used > ttl_s:
                self._session = None
                self._tokenizer = None
                logger.info("EmbedWorker nhả RAM sau %.0fs không dùng.", ttl_s)

    @property
    def loaded(self) -> bool:
        return self._session is not None

    # ------------------------------------------------------------------ #
    # Việc duy nhất của công nhân: embed
    # ------------------------------------------------------------------ #
    def embed(self, texts: list[str]):
        """Trả ndarray (n, 384) float32, đã chuẩn hoá L2 -> dot = cosine."""
        import numpy as np
        with self._lock:
            self._ensure_loaded()
            self._last_used = time.monotonic()
            encs = self._tokenizer.encode_batch([t or " " for t in texts])
            ids = np.array([e.ids for e in encs], dtype=np.int64)
            mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
            feeds = {}
            for inp in self._session.get_inputs():
                if "input_ids" in inp.name:
                    feeds[inp.name] = ids
                elif "attention_mask" in inp.name:
                    feeds[inp.name] = mask
                elif "token_type" in inp.name:
                    feeds[inp.name] = np.zeros_like(ids)
            hidden = self._session.run(None, feeds)[0]   # (n, seq, 384)
            # Mean-pooling theo attention mask rồi chuẩn hoá L2 (chuẩn sentence-transformers).
            m = mask[..., None].astype(np.float32)
            emb = (hidden * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
            emb = emb / np.clip(np.linalg.norm(emb, axis=1, keepdims=True), 1e-9, None)
            return emb.astype(np.float32)


_worker: EmbedWorker | None = None
_worker_lock = threading.Lock()


def get_worker() -> EmbedWorker:
    """Singleton toàn tiến trình — mọi pipeline dùng chung một công nhân."""
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = EmbedWorker()
        return _worker


__all__ = ["EmbedWorker", "get_worker"]
