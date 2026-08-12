# -*- coding: utf-8 -*-
"""Khai các công nghệ đã đo ngày 10-11/08/2026 vào sổ bằng chứng.

Vì sao có tệp này: mấy công nghệ đã được đo thật trên máy Sếp, và nếu không
vào sổ thì vài tháng nữa sẽ có người tải MinerU về lần nữa — đúng cái bệnh
`tools/ra_kho_cong_nghe.py` vừa chỉ ra (86/379 cái tên chưa từng ra khỏi
trang giấy).

Tệp này CHỈ khai công nghệ và phép đo. Nó KHÔNG viết kết quả:
`tools/benchmark_tech_matrix.py probe ... --promote` mới chạy phép đo thật và
băm kết quả lại. Con số nào vào sổ cũng phải do một lệnh sinh ra tại chỗ.

    python tools/nap_do_hom_nay.py

BẢN ĐẦU BỊ SỔ TỪ CHỐI, ba chỗ sai — ghi lại để không ai viết lại y thế:

  1. `claim` khai `{text, source_url, captured_at}`; sổ đòi ĐÚNG bộ
     `{id, text, source_urls, video_urls}`. Sổ so bằng `set(claim) != expected`
     nên thừa một khoá cũng hỏng, không chỉ thiếu.
  2. `probe` khai `description`; sổ đòi `summary`.
  3. `timeout_s=1800` cho `pdf-matrix`; sổ chặn 1..120. Đây KHÔNG phải lỗi khai
     mà là phép đo sai thiết kế: nó gọi cả MinerU (247 giây/trang). Đã tách —
     `pdf-matrix` giờ chỉ so markitdown với docling và lọt trần.

Chuyện MinerU quá chậm không mất đi đâu. Sổ tách sẵn hai loại: `local_command`
được chứng minh READ/INSTALLED/SMOKE_TESTED/BENCHMARKED, KHÔNG được chứng minh
REJECTED. Loại bỏ là một QUYẾT ĐỊNH của người, không phải kết quả của một lệnh.
"""
from __future__ import annotations

import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from core.tech_evidence import (  # noqa: E402
    load_registry, new_registry, new_technology, save_registry, validate_registry,
)

SO = GOC / "data" / "tech_evidence" / "registry.json"
PY = sys.executable
PY_MINERU = str(GOC / ".venv-mineru" / "Scripts" / "python.exe")

# Ba tệp phép đo, đã gộp về một thư mục và một hợp đồng (11/08/2026).
DO = "tools/probes/do_cong_nghe.py"
MOI_TRUONG = "tools/probes/moi_truong.py"
HOP_DONG = "tools/probes/hermes_openclaw_contract.py"


def _loi_khai(ma: str, chu: str, *, nguon: list[str], video: list[str] | None = None) -> dict:
    """Một lời khai. Đúng bốn khoá — sổ so bộ khoá chứ không chỉ đếm."""
    return {"id": ma, "text": chu, "source_urls": nguon, "video_urls": video or []}


def _lenh(argv: list[str], *, ma: str, chung_minh: str, tom_tat: str,
          han_giay: int = 120) -> dict:
    return {
        "id": ma,
        "kind": "local_command",
        "proves_state": chung_minh,
        "summary": tom_tat,
        "argv": argv,
        "cwd": ".",
        "timeout_s": han_giay,
    }


CONG_NGHE = [
    new_technology(
        "docling", "docling (IBM)", "tài liệu",
        claims=[_loi_khai(
            "docling-pdf-md",
            "PDF -> Markdown giữ cấu trúc, chạy cục bộ, không cần GPU",
            nguon=["https://github.com/docling-project/docling"])],
        probes=[_lenh(
            [PY, DO, "pdf-matrix"], ma="pdf-matrix", chung_minh="BENCHMARKED",
            tom_tat="So markitdown với docling trên cùng một PDF, cùng máy.")],
    ),
    new_technology(
        "mineru", "MinerU (OpenDataLab)", "tài liệu",
        claims=[_loi_khai(
            "mineru-pdf-rag",
            "PDF/scan -> Markdown+JSON có cấu trúc cho RAG",
            nguon=["https://github.com/opendatalab/mineru"])],
        # KHÔNG khai phép đo: 247 giây/trang vượt trần 120 giây của sổ. Việc
        # nó quá chậm là quyết định loại bỏ, ghi bằng `decision`, không bằng
        # một lệnh chạy dối cho lọt cửa.
        probes=[],
    ),
    new_technology(
        "airllm", "AirLLM", "suy luận cục bộ",
        claims=[_loi_khai(
            "airllm-70b-4gb",
            "Chạy model 70B trên 4 GB bằng cách nạp từng lớp một",
            nguon=["https://github.com/lyogavin/airllm"])],
        probes=[_lenh(
            [PY, DO, "tran-dia"], ma="tran-dia", chung_minh="READ",
            tom_tat=("Cơ chế nạp-từng-lớp buộc đọc lại toàn bộ trọng số mỗi "
                     "token, nên tốc độ đĩa là trần trên."))],
    ),
    new_technology(
        "speculative-decoding", "Speculative decoding (draft model)", "suy luận cục bộ",
        claims=[_loi_khai(
            "spec-decode-1x7",
            "Nhanh 1,7-3 lần mà giữ nguyên 100% chất lượng",
            nguon=["https://arxiv.org/abs/2211.17192"])],
        probes=[_lenh(
            [PY, DO, "ollama-spec"], ma="ollama-spec", chung_minh="READ",
            tom_tat="Ollama — thứ AURA đang chạy — có cắm được model nháp không.")],
    ),
    new_technology(
        "hermes-agent", "Hermes Agent (Nous Research)", "khung agent",
        claims=[_loi_khai(
            "hermes-self-improving",
            "Agent tự cải thiện, sandbox cách ly, cổng nhắn tin đa kênh",
            nguon=["https://github.com/NousResearch/hermes-agent"])],
        # Dùng phép đo của Codex. Bản `hermes-context` của Claude đã bỏ: cùng
        # đọc một hằng số, mà bản này đọc kỹ hơn và không đẻ ra kết luận sai.
        probes=[_lenh(
            [PY, HOP_DONG, "hermes-contract"], ma="hermes-contract",
            chung_minh="READ",
            tom_tat="Đọc thẳng ngưỡng ngữ cảnh trong mã Hermes, không load model.")],
    ),
    new_technology(
        "openclaw", "OpenClaw", "khung agent",
        claims=[_loi_khai(
            "openclaw-68-providers",
            "68 nhà cung cấp, cắm thẳng Ollama/LM Studio/vLLM cục bộ",
            nguon=["https://github.com/openclaw/openclaw"])],
        probes=[_lenh(
            [PY, HOP_DONG, "openclaw-contract"], ma="openclaw-contract",
            chung_minh="READ",
            tom_tat="Đọc ngưỡng ngữ cảnh thật (chặn 4K, cảnh báo 8K) và giấy phép.")],
    ),
    new_technology(
        "agents-last-exam", "Agents' Last Exam (Berkeley RDI)", "thước đo",
        claims=[_loi_khai(
            "ale-1500-tasks",
            "1.500+ nhiệm vụ nghề nghiệp thật, kết quả kiểm chứng được",
            nguon=["https://github.com/rdi-berkeley/agents-last-exam"])],
        probes=[_lenh(
            [PY_MINERU, DO, "ale-task-cards"], ma="ale-task-cards",
            chung_minh="READ",
            tom_tat=("Đếm trên chính bộ đề: bao nhiêu nhiệm vụ AURA khởi động "
                     "nổi. Cần .venv-mineru vì phải đọc parquet."))],
    ),
]


def main() -> int:
    so = load_registry(SO) if SO.exists() else new_registry()
    dang_co = {t["id"] for t in so["technologies"]}
    them = 0
    for cong_nghe in CONG_NGHE:
        if cong_nghe["id"] in dang_co:
            print(f"  bỏ qua (đã có): {cong_nghe['id']}")
            continue
        so["technologies"].append(cong_nghe)
        them += 1
        print(f"  thêm: {cong_nghe['id']}")
    validate_registry(so, GOC)
    save_registry(SO, so)
    print(f"\n  {them} công nghệ mới, tổng {len(so['technologies'])}.")
    print("  Chưa có bằng chứng nào — chạy `probe ... --promote` để leo thang.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
