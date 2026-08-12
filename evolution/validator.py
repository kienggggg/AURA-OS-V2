"""
evolution/validator.py
======================
ASTValidator — vòng kiểm tra đầu tiên cho code do AURA tự sinh.

QUAN TRỌNG — đọc kỹ giới hạn:
  Đây là phòng thủ theo lớp (defense-in-depth), KHÔNG phải biên giới an ninh.
  Blocklist AST nâng cao rào cản và phơi bày rủi ro cho người duyệt, nhưng một
  bộ sinh code cố tình hiểm độc vẫn có thể lách (mã hoá chuỗi, getattr dunder,
  importlib động...). Lá chắn THẬT là: (1) con người đọc code trước khi gật,
  (2) chạy thử trong sandbox subprocess cô lập. Validator chỉ làm hai việc:
  chặn các mẫu nguy hiểm hiển nhiên, và liệt kê cảnh báo cho người duyệt.

Chỉ dùng stdlib `ast` — không phụ thuộc gì, nên test được đầy đủ offline.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """Mức độ của một phát hiện."""

    BLOCK = "block"  # cấm tuyệt đối — không cho qua
    WARN = "warn"    # cần người duyệt chú ý
    INFO = "info"    # ghi chú


@dataclass(frozen=True)
class Finding:
    """Một phát hiện trong quá trình quét AST."""

    severity: Severity
    rule: str
    message: str
    lineno: int


@dataclass
class ValidationReport:
    """Tổng hợp kết quả quét."""

    findings: list[Finding] = field(default_factory=list)
    syntax_ok: bool = True

    @property
    def has_blocking(self) -> bool:
        """True nếu có bất kỳ phát hiện mức BLOCK (hoặc lỗi cú pháp)."""
        return (not self.syntax_ok) or any(
            f.severity == Severity.BLOCK for f in self.findings
        )

    @property
    def blocks(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.BLOCK]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARN]

    def summary(self) -> str:
        """Bản tóm tắt người-đọc-được để hiển thị trước khi phê duyệt."""
        if not self.syntax_ok:
            return "❌ Code lỗi cú pháp — không thể phân tích."
        if not self.findings:
            return "✅ Không phát hiện mẫu nguy hiểm. (Vẫn cần người duyệt đọc code.)"
        lines = []
        for f in self.findings:
            icon = {"block": "⛔", "warn": "⚠️", "info": "ℹ️"}[f.severity.value]
            lines.append(f"{icon} [dòng {f.lineno}] {f.rule}: {f.message}")
        return "\n".join(lines)


# --- Bảng luật ---------------------------------------------------------------

# Builtin calls are dangerous regardless of receiver/import provenance.
_BLOCK_BARE_CALLS: frozenset[str] = frozenset(
    {
        "eval", "exec", "compile", "__import__",
    }
)

# Calls whose danger depends on their imported owner.  Matching a raw final
# attribute (for example ``remove``) falsely blocks safe code such as
# ``list.remove``.  Imported aliases are resolved before comparing this set.
_BLOCK_DOTTED_CALLS: frozenset[str] = frozenset(
    {
        "os.system", "os.popen", "os.spawn", "os.spawnl", "os.spawnv",
        "os.execv", "os.execve", "os.execvp", "os.kill",
        "os.remove", "os.unlink", "os.rmdir",
        "shutil.rmtree",
    }
)

# Module bị CẤM import (sinh tool không được dùng các thứ này).
_BLOCK_IMPORTS: frozenset[str] = frozenset(
    {"subprocess", "ctypes", "socket", "marshal", "multiprocessing", "pty"}
)

# Module CẢNH BÁO (hợp lệ trong vài trường hợp nhưng cần người duyệt để ý).
_WARN_IMPORTS: frozenset[str] = frozenset(
    {"os", "sys", "shutil", "importlib", "pickle", "requests", "urllib", "http"}
)

# Thuộc tính dunder thường dùng để thoát sandbox.
_BLOCK_DUNDER: frozenset[str] = frozenset(
    {
        "__globals__", "__builtins__", "__subclasses__", "__bases__",
        "__import__", "__code__", "__class__", "__mro__", "__dict__",
    }
)

# Tiền tố đường dẫn hệ thống nhạy cảm (phát hiện trong chuỗi literal).
_SYSTEM_PATH_HINTS: tuple[str, ...] = (
    "/etc", "/usr", "/bin", "/sbin", "/var", "/root", "/boot",
    "c:\\windows", "c:\\program files", "%systemroot%",
)


def _dotted_name(node: ast.AST) -> str:
    """Dựng tên gọi dạng 'os.system' / 'eval' từ node func của ast.Call."""
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


class ASTValidator:
    """Quét một chuỗi mã nguồn Python và trả về ValidationReport."""

    def validate(self, code: str) -> ValidationReport:
        report = ValidationReport()

        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            report.syntax_ok = False
            report.findings.append(
                Finding(Severity.BLOCK, "syntax", f"Lỗi cú pháp: {exc}", exc.lineno or 0)
            )
            return report

        import_aliases = self._collect_import_aliases(tree)
        for node in ast.walk(tree):
            self._check_imports(node, report)
            self._check_calls(node, report, import_aliases)
            self._check_dunder(node, report)
            self._check_string_literals(node, report)

        self._check_structure(tree, report)
        return report

    # ------------------------------------------------------------------ #
    def _check_imports(self, node: ast.AST, report: ValidationReport) -> None:
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "").split(".")[0]]

        for name in names:
            if name in _BLOCK_IMPORTS:
                report.findings.append(
                    Finding(Severity.BLOCK, "import",
                            f"Cấm import '{name}'.", getattr(node, "lineno", 0))
                )
            elif name in _WARN_IMPORTS:
                report.findings.append(
                    Finding(Severity.WARN, "import",
                            f"Module '{name}' cần người duyệt để ý (OS/mạng/động).",
                            getattr(node, "lineno", 0))
                )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _collect_import_aliases(tree: ast.Module) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    aliases[alias.asname or root] = root
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                for alias in node.names:
                    aliases[alias.asname or alias.name] = f"{root}.{alias.name}"
        return aliases

    @staticmethod
    def _resolve_imported_name(dotted: str, aliases: dict[str, str]) -> str:
        parts = dotted.split(".")
        if parts and parts[0] in aliases:
            return ".".join([aliases[parts[0]], *parts[1:]])
        return dotted

    @classmethod
    def _is_pathlib_destructive_call(
        cls, node: ast.Call, aliases: dict[str, str], last: str,
    ) -> bool:
        if last not in {"unlink", "rmdir"} or not isinstance(node.func, ast.Attribute):
            return False
        receiver = node.func.value
        if not isinstance(receiver, ast.Call):
            return False
        constructor = cls._resolve_imported_name(_dotted_name(receiver.func), aliases)
        return constructor == "pathlib.Path"

    def _check_calls(
        self, node: ast.AST, report: ValidationReport,
        aliases: dict[str, str],
    ) -> None:
        if not isinstance(node, ast.Call):
            return
        dotted = _dotted_name(node.func)
        if not dotted:
            return
        last = dotted.split(".")[-1]
        resolved = self._resolve_imported_name(dotted, aliases)

        if (
            last in _BLOCK_BARE_CALLS
            or resolved in _BLOCK_DOTTED_CALLS
            or self._is_pathlib_destructive_call(node, aliases, last)
        ):
            report.findings.append(
                Finding(Severity.BLOCK, "call",
                        f"Cấm gọi '{resolved}()' (thực thi/xoá nguy hiểm).",
                        node.lineno)
            )
            return

        # open(..., 'w'/'a'/'x') -> cảnh báo ghi file.
        if last == "open":
            mode = self._open_mode(node)
            if mode and any(c in mode for c in ("w", "a", "x", "+")):
                report.findings.append(
                    Finding(Severity.WARN, "file-write",
                            f"open() chế độ ghi ({mode!r}) — kiểm tra đường dẫn.",
                            node.lineno)
                )

    @staticmethod
    def _open_mode(call: ast.Call) -> str | None:
        """Lấy tham số mode của open() nếu là literal chuỗi."""
        if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
            val = call.args[1].value
            return val if isinstance(val, str) else None
        for kw in call.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                return kw.value.value if isinstance(kw.value.value, str) else None
        return None

    # ------------------------------------------------------------------ #
    def _check_dunder(self, node: ast.AST, report: ValidationReport) -> None:
        if isinstance(node, ast.Attribute) and node.attr in _BLOCK_DUNDER:
            report.findings.append(
                Finding(Severity.BLOCK, "dunder",
                        f"Cấm truy cập '{node.attr}' (mẫu thoát sandbox).",
                        getattr(node, "lineno", 0))
            )

    # ------------------------------------------------------------------ #
    def _check_string_literals(self, node: ast.AST, report: ValidationReport) -> None:
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            return
        val = node.value
        low = val.lower()

        # Path traversal.
        if ".." in val.replace("\\", "/").split("/"):
            report.findings.append(
                Finding(Severity.BLOCK, "path-traversal",
                        f"Chuỗi chứa '..' (path traversal): {val!r}",
                        getattr(node, "lineno", 0))
            )
            return

        # Ghi vào thư mục hệ thống.
        for hint in _SYSTEM_PATH_HINTS:
            if low.startswith(hint):
                report.findings.append(
                    Finding(Severity.BLOCK, "system-path",
                            f"Trỏ tới đường dẫn hệ thống nhạy cảm: {val!r}",
                            getattr(node, "lineno", 0))
                )
                return

    # ------------------------------------------------------------------ #
    def _check_structure(self, tree: ast.Module, report: ValidationReport) -> None:
        """Kiểm tra cấu trúc tối thiểu của một tool hợp lệ."""
        func_names = [
            n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
        ]
        if not any(name.startswith("tool_") for name in func_names):
            report.findings.append(
                Finding(Severity.WARN, "structure",
                        "Không thấy hàm 'tool_*' — tool cần một entrypoint tool_<tên>.",
                        0)
            )
        if "ToolResult" not in (
            ast.dump(tree) if False else "".join(  # nhanh: quét tên xuất hiện
                n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
            )
        ):
            report.findings.append(
                Finding(Severity.WARN, "structure",
                        "Không thấy tham chiếu 'ToolResult' — tool phải trả ToolResult.",
                        0)
            )


__all__ = ["ASTValidator", "ValidationReport", "Finding", "Severity"]
