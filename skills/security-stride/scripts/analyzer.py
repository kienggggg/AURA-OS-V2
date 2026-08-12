"""
skills/security-stride/scripts/analyzer.py
==========================================
STRIDE Analyzer — mô hình hoá mối đe doạ cho một ý tưởng tính năng (LỚP LOGIC, Level 4).

Shift-Left Security: soi 6 nhóm rủi ro STRIDE TRƯỚC khi code. Bộ phân tích này CHẠY
LOCAL, tất định (không gọi LLM): với mỗi nhóm STRIDE có (1) câu hỏi nền luôn phải trả
lời, và (2) rủi ro cụ thể được kích hoạt theo TỪ KHOÁ trong mô tả tính năng, kèm biện
pháp giảm thiểu. Nhờ tất định nên dễ test offline và cho kết quả nhất quán.

Tool công khai `tool_stride_analyze(feature, ...)` luôn trả ToolResult.
Tham chiếu chuẩn an toàn: CONTEXT.md mục 9.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Cho phép `from core...` dù nạp qua importlib hay chạy độc lập.
# skills/security-stride/scripts/analyzer.py -> parents[3] = gốc dự án.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json
import logging

from core.schemas import ToolResult

logger = logging.getLogger("aura.skills.security_stride")

# --- Câu hỏi NỀN cho từng nhóm (luôn phải tự trả lời, dù không khớp từ khoá) ---
_BASELINE: dict[str, tuple[str, str]] = {
    "Spoofing": (
        "Giả mạo danh tính",
        "Ai/cái gì gọi tính năng này, và làm sao xác minh đúng là họ?",
    ),
    "Tampering": (
        "Sửa đổi trái phép",
        "Dữ liệu/tham số/đường dẫn đầu vào có thể bị chỉnh sửa độc hại không?",
    ),
    "Repudiation": (
        "Chối bỏ hành động",
        "Có ghi log/audit đủ để truy vết ai đã làm gì, khi nào không?",
    ),
    "Information Disclosure": (
        "Lộ thông tin",
        "Có nguy cơ rò rỉ secret/PII ra log, output, hay cloud không?",
    ),
    "Denial of Service": (
        "Từ chối dịch vụ",
        "Có giới hạn tài nguyên (timeout, kích thước, vòng lặp) để khỏi treo/cạn kiệt không?",
    ),
    "Elevation of Privilege": (
        "Leo thang đặc quyền",
        "Có thực thi lệnh/chạy mã động/đụng quyền cao hơn mức cần không?",
    ),
}

# --- Rủi ro CỤ THỂ kích theo từ khoá: nhóm -> [(keywords, rủi ro, giảm thiểu)] ---
_RULES: dict[str, list[tuple[tuple[str, ...], str, str]]] = {
    "Spoofing": [
        (("login", "đăng nhập", "auth", "xác thực", "password", "mật khẩu", "token", "session", "oauth"),
         "Tính năng có xác thực — kẻ gian có thể giả danh người dùng.",
         "Dùng xác thực mạnh, chống brute-force, hết hạn token, không tin client tự khai danh tính."),
        (("api", "webhook", "callback", "third party", "bên thứ ba"),
         "Điểm gọi từ bên ngoài có thể bị giả nguồn.",
         "Xác minh chữ ký/HMAC, allowlist nguồn, xác thực 2 chiều khi cần."),
    ],
    "Tampering": [
        (("file", "upload", "tải lên", "path", "đường dẫn", "ghi", "write", "save", "lưu"),
         "Đầu vào file/đường dẫn có thể bị lợi dụng (path traversal, ghi đè).",
         "Validate & chuẩn hoá đường dẫn, chặn '..', giới hạn thư mục data/, kiểm tra MIME/size."),
        (("url", "param", "tham số", "query", "input", "form"),
         "Tham số đầu vào có thể bị giả mạo/độc hại.",
         "Validate qua schema (pydantic), ép kiểu, allowlist giá trị, escape khi dùng."),
        (("database", "sql", "query", "db"),
         "Nguy cơ injection khi ghép truy vấn.",
         "Dùng tham số hoá truy vấn (prepared statements), không nối chuỗi SQL."),
    ],
    "Repudiation": [
        (("delete", "xoá", "xóa", "payment", "thanh toán", "giao dịch", "transaction", "admin", "sửa"),
         "Hành động hệ trọng mà thiếu vết kiểm toán -> khó quy trách nhiệm.",
         "Ghi audit log bất biến (ai/khi nào/cái gì), gắn correlation_id, không cho tự xoá log."),
    ],
    "Information Disclosure": [
        (("api key", "secret", "khoá", "token", "password", "mật khẩu", "credential", "env"),
         "Có xử lý bí mật — nguy cơ lộ ra log/output/cloud.",
         "Đọc secret qua config/.env, redact trước khi log/gửi cloud, không hardcode (CONTEXT.md §1)."),
        (("personal", "cá nhân", "pii", "email", "user data", "dữ liệu người dùng", "địa chỉ"),
         "Xử lý PII — rủi ro lộ dữ liệu riêng tư.",
         "Tối thiểu hoá dữ liệu thu thập, mã hoá khi lưu/truyền, kiểm soát truy cập."),
        (("log", "debug", "trace", "print"),
         "Log/debug có thể vô tình in dữ liệu nhạy cảm.",
         "Redact trường nhạy cảm, hạ mức log ở prod, không print secret."),
    ],
    "Denial of Service": [
        (("download", "tải", "scrape", "cào", "network", "mạng", "request", "http", "api", "loop", "vòng lặp"),
         "I/O mạng/vòng lặp có thể treo hoặc bị lạm dụng gây cạn tài nguyên.",
         "Đặt timeout + retry có giới hạn + backoff, giới hạn kích thước/tốc độ, hàng đợi có trần."),
        (("upload", "file", "image", "ảnh", "ocr", "video", "lớn"),
         "Xử lý file lớn/nặng CPU có thể làm nghẽn hệ thống.",
         "Giới hạn dung lượng & độ phân giải, xử lý nền/bất đồng bộ, hạn mức đồng thời."),
    ],
    "Elevation of Privilege": [
        (("exec", "eval", "subprocess", "shell", "command", "lệnh", "system", "os.", "run code", "chạy code"),
         "Thực thi lệnh/mã động — đường leo thang đặc quyền nguy hiểm nhất.",
         "CẤM os.system/subprocess/eval/exec (CONTEXT.md §5); nếu buộc phải, sandbox + allowlist chặt."),
        (("admin", "root", "sudo", "quyền", "privilege", "phân quyền", "role"),
         "Liên quan quyền cao — rủi ro vượt quyền.",
         "Least privilege (CONTEXT.md §6), kiểm tra phân quyền ở mọi điểm vào, mặc định từ chối."),
        (("install", "cài", "dependency", "thư viện", "pip", "package", "plugin"),
         "Cài/nạp mã ngoài có thể đưa code không kiểm soát vào hệ thống.",
         "Allowlist + phê duyệt (DependencyInstaller), ghim phiên bản, không kéo gói lạ."),
    ],
}

# Trọng số ưu tiên: nhóm có sức phá hoại cao hơn thì rủi ro 'nặng' hơn.
_PRIORITY_WEIGHT: dict[str, int] = {
    "Elevation of Privilege": 3,
    "Information Disclosure": 3,
    "Tampering": 2,
    "Spoofing": 2,
    "Denial of Service": 2,
    "Repudiation": 1,
}


def _analyze(feature: str, context: str = "") -> dict:
    """Áp bộ luật STRIDE lên mô tả tính năng. Trả dict có cấu trúc (JSON-ready)."""
    haystack = f"{feature} {context}".lower()
    categories: list[dict] = []
    total_risks = 0
    weighted = 0

    for cat, (vi_name, baseline_q) in _BASELINE.items():
        hits: list[dict] = []
        for keywords, risk, mitigation in _RULES.get(cat, []):
            matched = [k for k in keywords if k in haystack]
            if matched:
                hits.append({
                    "risk": risk,
                    "mitigation": mitigation,
                    "matched_keywords": matched,
                })
        total_risks += len(hits)
        weighted += len(hits) * _PRIORITY_WEIGHT.get(cat, 1)
        categories.append({
            "category": cat,
            "name_vi": vi_name,
            "baseline_question": baseline_q,
            "risks": hits,
            "risk_count": len(hits),
        })

    if weighted >= 8:
        level = "CAO"
    elif weighted >= 3:
        level = "TRUNG BÌNH"
    elif weighted >= 1:
        level = "THẤP"
    else:
        level = "CHƯA PHÁT HIỆN (vẫn phải trả lời câu hỏi nền)"

    return {
        "feature": feature,
        "context": context,
        "categories": categories,
        "total_risks": total_risks,
        "weighted_score": weighted,
        "risk_level": level,
    }


def _render_markdown(data: dict) -> str:
    """Dựng báo cáo markdown người-đọc-được từ kết quả phân tích."""
    lines = [
        f"# 🛡️ STRIDE Threat Model — Shift-Left",
        f"**Tính năng:** {data['feature']}",
    ]
    if data["context"]:
        lines.append(f"**Bối cảnh:** {data['context']}")
    lines.append(
        f"**Mức rủi ro tổng:** {data['risk_level']} "
        f"(điểm {data['weighted_score']}, {data['total_risks']} rủi ro cụ thể)\n"
    )

    icons = {
        "Spoofing": "🎭", "Tampering": "🔧", "Repudiation": "📝",
        "Information Disclosure": "🔓", "Denial of Service": "💥",
        "Elevation of Privilege": "⬆️",
    }
    for c in data["categories"]:
        cat = c["category"]
        lines.append(f"## {icons.get(cat, '•')} {cat} — {c['name_vi']}")
        lines.append(f"*Câu hỏi nền:* {c['baseline_question']}")
        if c["risks"]:
            for r in c["risks"]:
                lines.append(f"- ⚠️ **Rủi ro:** {r['risk']}")
                lines.append(f"  - **Giảm thiểu:** {r['mitigation']}")
        else:
            lines.append("- ✅ Không kích rủi ro theo từ khoá (vẫn cần tự trả lời câu hỏi nền).")
        lines.append("")

    lines.append("---")
    lines.append("> Soi xong STRIDE rồi mới giao code. Tham chiếu CONTEXT.md §9.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool công khai cho Registry
# ---------------------------------------------------------------------------
def tool_stride_analyze(feature: str, context: str = "", as_json: bool = False) -> ToolResult:
    """
    Tool 'security.stride': phân tích STRIDE cho một ý tưởng tính năng. Luôn trả ToolResult.

    Args:
        feature: mô tả tính năng cần soi (bắt buộc).
        context: bối cảnh thêm (ai dùng, dữ liệu gì, chạy ở đâu).
        as_json: True -> trả JSON có cấu trúc; False -> báo cáo markdown.
    """
    if not feature or not isinstance(feature, str) or not feature.strip():
        return ToolResult.failure(
            "security.stride", "Thiếu 'feature' — cần mô tả tính năng để phân tích."
        )

    try:
        data = _analyze(feature.strip(), (context or "").strip())
        output = json.dumps(data, ensure_ascii=False, indent=2) if as_json else _render_markdown(data)
    except Exception as exc:  # noqa: BLE001 — vành đai cuối, không để lọt exception
        return ToolResult.failure("security.stride", f"Lỗi phân tích STRIDE: {exc}")

    return ToolResult.success("security.stride", output=output)


# ---------------------------------------------------------------------------
# CLI độc lập (Level 4)
# ---------------------------------------------------------------------------
def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="AURA skill security.stride — threat model STRIDE.")
    ap.add_argument("--feature", required=True, help="Mô tả tính năng cần soi.")
    ap.add_argument("--context", default="", help="Bối cảnh thêm.")
    ap.add_argument("--json", action="store_true", help="Xuất JSON thay vì markdown.")
    args = ap.parse_args(argv)

    result = tool_stride_analyze(feature=args.feature, context=args.context, as_json=args.json)
    print(result.output if result.ok else f"[LỖI] {result.error}")
    return 0 if result.ok else 1


__all__ = ["tool_stride_analyze"]


if __name__ == "__main__":
    raise SystemExit(_main())
