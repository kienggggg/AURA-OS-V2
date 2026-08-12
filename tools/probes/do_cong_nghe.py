# -*- coding: utf-8 -*-
"""Phép đo về SUY LUẬN CỤC BỘ và ĐỌC TÀI LIỆU.

Một trong ba tệp phép đo, tất cả dùng chung `tools/probes/chung.py`:

    do_cong_nghe.py              suy luận cục bộ + đọc tài liệu   (tệp này)
    moi_truong.py                công cụ đã cài trên máy
    hermes_openclaw_contract.py  hợp đồng của hai khung agent

    python tools/probes/do_cong_nghe.py <tên phép đo>

ĐÃ BỎ `hermes-context`. Nó đọc `MINIMUM_CONTEXT_LENGTH` của Hermes, và
`hermes_openclaw_contract.py hermes-contract` của Codex đọc đúng thứ đó mà kỹ
hơn. Bản của tôi còn là bản đẻ ra kết luận sai "OpenClaw đòi ngữ cảnh tối
thiểu 16K" — Codex đọc mã và chỉ ra runtime chặn ở 4K, cảnh báo ở 8K. Giữ
lại hai bản là mời người sau chạy nhầm bản dở.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chung import bang, chay, emit  # noqa: E402

GOC = Path(__file__).resolve().parents[2]

# PDF thật của Sếp, một trang, chữ thật (không phải ảnh scan).
#
# 12/08/2026: trước đây ghi thẳng tên tệp, mà tên tệp có HỌ TÊN Sếp — và tệp
# này lên GitHub. Đổi sang dò theo mẫu: bản thân tệp PDF vẫn bị .gitignore chặn,
# giờ tên Sếp cũng không còn nằm trong mã. Sổ bằng chứng thì KHÔNG sửa (§5:
# "sổ sống được là nhờ chỗ không được viết lại") — lệnh đã chạy hôm 11/08 vẫn
# ghi tên tệp thật; chỗ đó được che lúc dựng ảnh chụp công khai.
_UNG_VIEN = sorted(GOC.glob("*TopCV.vn-*.pdf"))
PDF_MAU = _UNG_VIEN[0] if _UNG_VIEN else GOC / "cv-mau.pdf"


def _dem_tieu_de(chu: str) -> int:
    return sum(1 for dong in chu.splitlines() if dong.strip().startswith("#"))


def _moi_truong_docling() -> dict[str, str]:
    """docling KHÔNG chạy trên máy này nếu thiếu `TORCHDYNAMO_DISABLE=1`.

    Đo 11/08/2026, cùng một PDF một trang:

        không có cờ  ->  mã 1 sau 513s / 248s / 148s (ấm dần rồi vẫn hỏng)
                         lỗi thật: "cl is not found" — TorchDynamo đi tìm
                         trình biên dịch C của MSVC, máy này không cài
        có cờ        ->  mã 0 sau 23,8s, ra 2.490 ký tự markdown
        markitdown   ->  mã 0 sau 10,6s, ra 1.991 ký tự

    Bản probe đầu có dòng này; lúc gộp hai bộ probe tôi làm rơi mất, và phép
    đo lập tức báo docling hỏng. Sổ ghi docling BLOCKED cũng vì chạy KHÔNG có
    cờ — ghi đúng một cấu hình, không phải bản chất công cụ.

    Truyền qua `env=` chứ không đặt ở vỏ ngoài: `core/tech_evidence` cố ý quét
    sạch môi trường phép đo, nên biến đặt ngoài không tới được đây.
    """
    moi = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
        "TORCHDYNAMO_DISABLE": "1",
        "HF_HUB_DISABLE_SYMLINKS": "1",
    }
    for ten in ("SYSTEMROOT", "WINDIR", "USERPROFILE", "LOCALAPPDATA",
                "APPDATA", "TEMP", "TMP"):
        gia_tri = os.environ.get(ten)
        if gia_tri:
            moi[ten] = gia_tri
    return moi


_MOI_TRUONG_DOCLING = _moi_truong_docling()


# --------------------------------------------------------------- PDF -> Markdown
def pdf_matrix() -> int:
    """So markitdown với docling trên CÙNG một tệp, CÙNG một máy.

    KHÔNG gộp MinerU vào đây nữa. Sổ bằng chứng chặn phép đo ở 120 giây, mà
    MinerU cần 247 giây cho một trang — bản cũ khai `timeout_s=1800` nên cả
    mục bị sổ từ chối, và phép đo tốt (docling 8,2 giây) chết theo phép đo
    không lọt cửa.

    Việc MinerU quá chậm KHÔNG mất: nó là một QUYẾT ĐỊNH, không phải một phép
    đo. Sổ đã tách sẵn hai thứ đó — `local_command` không được phép chứng minh
    `REJECTED`, đúng vì lý do này.
    """
    ket: dict[str, dict] = {}
    for ten, argv, han in (
        ("markitdown",
         [str(GOC / ".venv311" / "Scripts" / "python.exe"), "-m", "markitdown",
          str(PDF_MAU)], 90),
        ("docling",
         [str(GOC / ".venv-mineru" / "Scripts" / "python.exe"), "-c",
          "import sys,io;sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8');"
          "from docling.document_converter import DocumentConverter;"
          f"print(DocumentConverter().convert(r'{PDF_MAU}').document.export_to_markdown())"],
         100),
    ):
        bat_dau = time.monotonic()
        try:
            xong = subprocess.run(argv, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=han,
                                  env=_MOI_TRUONG_DOCLING)
            chu = (xong.stdout or "").strip()
            ma = xong.returncode
        except subprocess.TimeoutExpired:
            chu, ma = "", 124
        ket[ten] = {"giay": round(time.monotonic() - bat_dau, 1),
                    "ky_tu": len(chu), "tieu_de": _dem_tieu_de(chu),
                    "ma_thoat": ma}

    ok = all(m["ma_thoat"] == 0 for m in ket.values())
    ra = {
        "ok": ok,
        "phep_do": "markitdown so docling, cùng PDF, cùng máy",
        "tep_byte": PDF_MAU.stat().st_size if PDF_MAU.is_file() else 0,
        "mineru_tach_rieng": "247s/trang, vượt trần 120s của sổ — là quyết định, không phải phép đo",
        "cong_cu": [{"ten": t, **s} for t, s in ket.items()],
    }
    emit(ra)
    bang(ra, cot=("cong_cu",))
    return 0 if ok else 1


# ------------------------------------------------------------------- AirLLM
def tran_dia() -> int:
    """Trần vật lý của AirLLM: nó đọc lại TOÀN BỘ trọng số cho MỖI token.

    Không cần cài AirLLM mới biết nhanh chậm — cơ chế đã nói hết. Đo tốc độ
    đọc đĩa là đủ dựng trần trên, và trần đó không mẹo nào vượt được.
    """
    # Phải theo OLLAMA_MODELS. Sáng 11/08 Sếp dời kho model sang F: cho nhẹ ổ
    # C:, và phép đo này — vốn cắm cứng `~/.ollama` — im lặng trả "không tìm
    # thấy blob" suốt từ đó. Việc gộp hai bộ phép đo mới lôi nó ra.
    import os
    kho = Path(os.environ.get("OLLAMA_MODELS") or (Path.home() / ".ollama" / "models"))
    thu = [kho / "blobs", kho, Path.home() / ".ollama" / "models" / "blobs"]
    mau = next((b for d in thu if d.is_dir()
                for b in d.glob("sha256-*")), None)
    if mau is None:
        emit({"ok": False,
              "ly_do": "không tìm thấy blob model nào để đo",
              "da_tim": [str(d) for d in thu]})
        return 1

    khoi, doc, han = 8 * 1024 * 1024, 0, 1_200_000_000
    bat_dau = time.monotonic()
    with open(mau, "rb", buffering=0) as f:
        while doc < han:
            mieng = f.read(khoi)
            if not mieng:
                break
            doc += len(mieng)
    giay = time.monotonic() - bat_dau
    mb_s = doc / 1024**2 / giay

    ra = {
        "ok": True,
        "doc_gb": round(doc / 1024**3, 2),
        "giay": round(giay, 1),
        "mb_moi_giay": round(mb_s),
        "aura_dang_chay_tok_s": 5.9,
        "tran_tren": [
            {"model": ten, "gb": gb,
             "giay_moi_token": round(gb * 1024 / mb_s, 1),
             "tok_s": round(mb_s / (gb * 1024), 2)}
            for ten, gb in (("qwen3.5:4b", 3.16), ("8B Q4", 4.7),
                            ("14B Q4", 8.5), ("32B Q4", 19.0), ("70B Q4", 40.0))
        ],
    }
    emit(ra)
    bang(ra, cot=("tran_tren",))
    return 0


# ------------------------------------------- Speculative decoding trên Ollama
def ollama_spec() -> int:
    """Ollama có cắm được model nháp không — hỏi thẳng nhị phân, không tra mạng."""
    xong = subprocess.run(["ollama", "serve", "--help"], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=60)
    van_ban = (xong.stdout or "") + (xong.stderr or "")
    khop = [d.strip() for d in van_ban.splitlines()
            if re.search(r"draft|spec[-_]", d, re.IGNORECASE)]
    phien = subprocess.run(["ollama", "--version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
    ra = {
        "ok": True,
        "phien_ban": (phien.stdout or "").strip().splitlines()[-1:],
        "so_dong_nhac_draft_spec": len(khop),
        "co_tuy_chon": bool(khop),
        "ket_luan": ("Ollama bản này KHÔNG có tuỳ chọn speculative decoding"
                     if not khop else "có tuỳ chọn — đọc lại"),
        "dong_khop": khop[:10],
    }
    emit(ra)
    bang(ra)
    return 0


# ---------------------------------------------------------- Agents' Last Exam
def ale_task_cards() -> int:
    """ALE đòi agent những gì — đếm trên chính bộ đề, không tin bài giới thiệu.

    CẦN `.venv-mineru` (có pandas + pyarrow). `venv` chính không đọc được
    parquet — chạy nhầm thì nhận một ImportError dài ba dòng chẳng nói lên
    điều gì, nên chặn sớm và nói thẳng phải dùng trình thông dịch nào.
    """
    import importlib.util

    if importlib.util.find_spec("pandas") is None or not any(
        importlib.util.find_spec(m) for m in ("pyarrow", "fastparquet")
    ):
        emit({"ok": False, "do_duoc": False,
              "ly_do": "thiếu pandas hoặc bộ đọc parquet",
              "chay_bang": ".venv-mineru/Scripts/python.exe"})
        return 2

    import pandas as pd

    bang_de = pd.read_parquet(GOC / "data" / "tech_evidence" / "ale_task_cards.parquet")

    def so(x) -> int:
        try:
            return len(x)
        except TypeError:
            return 0

    file_vao = bang_de["input_files"].map(so)
    phan_mem = bang_de["software"].map(so)
    khong_gi = int(((file_vao == 0) & (phan_mem == 0)).sum())
    ra = {
        "ok": True,
        "tong_nhiem_vu": len(bang_de),
        "khong_can_file_vao": int((file_vao == 0).sum()),
        "khong_file_va_khong_phan_mem": khong_gi,
        "ty_le": round(khong_gi / len(bang_de), 3),
        "tb_file_vao": round(float(file_vao.mean()), 1),
        "tb_buoc_phai_lam": round(float(bang_de["agent_must_do"].map(so).mean()), 1),
        "so_nganh": int(bang_de["category"].nunique()),
        "ghi_chu": ("AURA v3 là màn hình chat: không đọc file, không chạy mã, "
                    f"nên chỉ khởi động nổi {khong_gi}/{len(bang_de)} nhiệm vụ"),
    }
    emit(ra)
    bang(ra)
    return 0


# ----------------------------------------------- docling leo lại từ BLOCKED
#
# Sổ chốt docling ở BLOCKED ngày 11/08 lúc 02:37, và ghi ĐÚNG: lệnh chạy lúc
# đó không có `TORCHDYNAMO_DISABLE=1` nên vượt trần 120 giây. Nhưng chốt đó
# đọc thành "docling không dùng được trên máy này", mà sự thật là nó chạy
# trong 23,8 giây khi có cờ.
#
# `BLOCKED` chỉ đi tiếp được sang `READ`, cố ý — phải leo lại cả thang, mỗi
# nấc một bằng chứng mới. Ba phép đo dưới đây là ba nấc đó.
_FIXTURE = GOC / "tests" / "fixtures" / "tech_evidence" / "sample_document.html"


def _chay_docling(ma_python: str, han: int) -> tuple[int, str, str]:
    xong = subprocess.run(
        [str(GOC / ".venv-mineru" / "Scripts" / "python.exe"), "-c", ma_python],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=han, env=_MOI_TRUONG_DOCLING)
    return xong.returncode, (xong.stdout or "").strip(), (xong.stderr or "").strip()


def docling_doc() -> int:
    """Đọc phiên bản docling và ghi lại NGUYÊN NHÂN chốt cũ, không chuyển tệp."""
    ma, ra, _ = _chay_docling(
        "import importlib.metadata as m; print(m.version('docling'))", 90)
    ket = {
        "ok": ma == 0,
        "phien_ban": ra.splitlines()[-1:] or ["?"],
        "chot_cu": "BLOCKED 11/08 02:37 — chuyển PDF 1 trang vượt trần 120s",
        "nguyen_nhan_that": ("TorchDynamo đi tìm cl.exe (trình biên dịch C của "
                             "MSVC), máy này không cài -> 'cl is not found'"),
        "do_lai_khong_co_co": {"ma_thoat": 1, "giay": [513.0, 248.1, 148.0]},
        "do_lai_co_co": {"ma_thoat": 0, "giay": 23.8, "ky_tu": 2490},
        "cach_go": "TORCHDYNAMO_DISABLE=1 truyền qua env của tiến trình con",
    }
    emit(ket)
    bang(ket)
    return 0 if ma == 0 else 1


def docling_import() -> int:
    """docling và DocumentConverter nạp được — đúng lệnh Codex đã dùng."""
    ma, ra, loi = _chay_docling(
        "import docling; from docling.document_converter import DocumentConverter;"
        " print('docling_import_ok')", 110)
    ket = {"ok": ma == 0 and "docling_import_ok" in ra,
           "ma_thoat": ma, "dau_ra": ra.splitlines()[-1:] or [""],
           "loi": loi[-200:] if ma else ""}
    emit(ket)
    bang(ket)
    return 0 if ket["ok"] else 1


def docling_smoke() -> int:
    """Chuyển thật một tệp NHỎ, KHÔNG phải PDF của Sếp.

    Dùng đúng fixture Codex dùng cho markitdown (310 byte, không có gì riêng
    tư) để hai công cụ smoke trên cùng một thứ. PDF một trang để dành cho
    `pdf-matrix` — smoke mà mất 38 giây thì sát trần quá.
    """
    bat_dau = time.monotonic()
    ma, ra, loi = _chay_docling(
        "import sys,io;sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8');"
        "from docling.document_converter import DocumentConverter;"
        f"print(len(DocumentConverter().convert(r'{_FIXTURE}').document.export_to_markdown()))",
        110)
    so = ra.splitlines()[-1:] or ["0"]
    ky_tu = int(so[0]) if so[0].isdigit() else 0
    ket = {"ok": ma == 0 and ky_tu > 0,
           "giay": round(time.monotonic() - bat_dau, 1),
           "ma_thoat": ma, "ky_tu": ky_tu,
           "tep": str(_FIXTURE.relative_to(GOC)),
           "loi": loi[-200:] if ma else ""}
    emit(ket)
    bang(ket)
    return 0 if ket["ok"] else 1


LENH = {
    "pdf-matrix": pdf_matrix,
    "docling-doc": docling_doc,
    "docling-import": docling_import,
    "docling-smoke": docling_smoke,
    "tran-dia": tran_dia,
    "ollama-spec": ollama_spec,
    "ale-task-cards": ale_task_cards,
}


if __name__ == "__main__":
    raise SystemExit(chay(LENH))
