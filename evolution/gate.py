"""
evolution/gate.py
=================
CodeGate — cổng kiểm duyệt code Shift-Left (pre-execution / pre-commit hook giả lập).

Gói GỌN hai lớp kiểm TĨNH thành một cổng pass/fail có phản hồi tự-sửa-được:
  1. AST cú pháp  : code phải `compile()` được (không syntax error).
  2. An ninh AST  : tái dùng `ASTValidator` để chặn mẫu nguy hiểm (CONTEXT.md §5).

Dùng ở hai nơi:
  - Trong `EvolutionEngine`: chặn TRƯỚC khi báo code ra UI; fail -> vòng tự sửa.
  - Như một pre-commit hook thật: `python -m evolution.gate <file.py> [...]`
    (exit != 0 nếu có file không qua cổng — cắm vào .git/hooks/pre-commit được).

Chỉ dùng stdlib + ASTValidator nội bộ -> test được đầy đủ offline.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field

from evolution.validator import ASTValidator, ValidationReport

logger = logging.getLogger("aura.evolution.gate")


@dataclass
class GateResult:
    """Kết quả qua cổng. `ok=True` nghĩa là code đủ an toàn để đi tiếp."""

    ok: bool
    report: ValidationReport | None = None
    reasons: list[str] = field(default_factory=list)

    def feedback(self) -> str:
        """Phản hồi cô đọng để nhồi lại cho CoderAgent tự sửa (remediation)."""
        if self.ok:
            return ""
        return "\n".join(f"- {r}" for r in self.reasons)


class CodeGate:
    """Cổng kiểm tĩnh: cú pháp + an ninh AST. KHÔNG chạy code (đó là việc Sandbox)."""

    def __init__(self, validator: ASTValidator | None = None) -> None:
        self.validator = validator or ASTValidator()

    def check(self, code: str) -> GateResult:
        """
        Kiểm một chuỗi mã. Trả GateResult(ok, report, reasons).

        - Lỗi cú pháp -> ok=False, nêu rõ dòng/thông điệp.
        - Có phát hiện BLOCK của ASTValidator -> ok=False, liệt kê từng vi phạm.
        - Cảnh báo (WARN) KHÔNG chặn (để người duyệt cân nhắc), nhưng vẫn ghi log.
        """
        reasons: list[str] = []

        # 1) Cú pháp: phải compile được.
        try:
            compile(code, "<generated>", "exec", flags=ast.PyCF_ONLY_AST)
        except SyntaxError as exc:
            reasons.append(f"Lỗi cú pháp [dòng {exc.lineno}]: {exc.msg}")
            return GateResult(ok=False, report=None, reasons=reasons)

        # 2) An ninh: ASTValidator.
        report = self.validator.validate(code)
        if report.has_blocking:
            if not report.syntax_ok:
                reasons.append("ASTValidator: code không phân tích được.")
            for f in report.blocks:
                reasons.append(f"[dòng {f.lineno}] {f.rule}: {f.message}")
            return GateResult(ok=False, report=report, reasons=reasons)

        # Qua cổng. Ghi log cảnh báo (không chặn) để minh bạch.
        for w in report.warnings:
            logger.info("CodeGate WARN [dòng %d] %s: %s", w.lineno, w.rule, w.message)
        return GateResult(ok=True, report=report, reasons=[])

    def check_file(self, path: str) -> GateResult:
        """Tiện ích cho pre-commit: đọc file rồi kiểm."""
        try:
            with open(path, encoding="utf-8") as f:
                code = f.read()
        except OSError as exc:
            return GateResult(ok=False, reasons=[f"Không đọc được file '{path}': {exc}"])
        return self.check(code)


# ---------------------------------------------------------------------------
# CLI — pre-commit hook thật: python -m evolution.gate file1.py file2.py ...
# ---------------------------------------------------------------------------
def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="CodeGate — kiểm cú pháp + an ninh AST cho file Python (pre-commit)."
    )
    ap.add_argument("files", nargs="+", help="Các file .py cần kiểm.")
    args = ap.parse_args(argv)

    gate = CodeGate()
    failed = 0
    for path in args.files:
        res = gate.check_file(path)
        if res.ok:
            print(f"✅ PASS  {path}")
        else:
            failed += 1
            print(f"⛔ FAIL  {path}")
            print(res.feedback())
    if failed:
        print(f"\n{failed} file KHÔNG qua cổng — chặn commit/thực thi.")
    return 1 if failed else 0


__all__ = ["CodeGate", "GateResult"]


if __name__ == "__main__":
    raise SystemExit(_main())
