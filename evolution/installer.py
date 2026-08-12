"""
evolution/installer.py
=====================
DependencyInstaller — cài thư viện còn thiếu cho tool tự sinh.

NGUYÊN TẮC AN TOÀN (cố ý KHÁC với "pip install ngầm"):
  - KHÔNG bao giờ cài lén. Mọi lần cài đều cần cờ approved=True (do người gật).
  - Gói nằm trong ALLOWLIST: cài bình thường (vẫn cần approved).
  - Gói NGOÀI allowlist: chặn mặc định, đòi xác nhận gõ đúng tên gói (chống
    typosquatting — gói độc tên gần giống).
  - Dùng [sys.executable, -m, pip] — KHÔNG shell=True (chống injection).

Phát hiện thiếu bằng importlib.util.find_spec — chỉ stdlib, test được offline.
"""

from __future__ import annotations

import importlib.util
import logging
import subprocess
import sys
from dataclasses import dataclass

logger = logging.getLogger("aura.evolution.installer")

# Tên module import -> tên gói pip (những trường hợp khác nhau).
_IMPORT_TO_PIP: dict[str, str] = {
    "bs4": "beautifulsoup4",
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "deep_translator": "deep-translator",
    "easyocr": "easyocr",
    "yaml": "PyYAML",
    "fitz": "PyMuPDF",
    "sklearn": "scikit-learn",
}

# Allowlist gói tin cậy (khớp nhu cầu trong PLAN.md + thư viện phổ biến an toàn).
_ALLOWLIST: frozenset[str] = frozenset(
    {
        "requests", "beautifulsoup4", "easyocr", "deep-translator",
        "Pillow", "opencv-python", "img2pdf", "pandas", "numpy",
        "PyMuPDF", "python-docx", "openpyxl", "lxml", "PyYAML",
        "chromadb", "pydantic", "pydantic-settings",
    }
)

# Module thuộc thư viện chuẩn -> không bao giờ cần cài.
_STDLIB_HINT: frozenset[str] = frozenset(
    {
        "os", "sys", "json", "re", "pathlib", "typing", "dataclasses",
        "enum", "datetime", "logging", "textwrap", "math", "io", "time",
        "collections", "itertools", "functools", "abc", "uuid", "hashlib",
    }
)


@dataclass
class InstallOutcome:
    """Kết quả cài một gói."""

    package: str
    ok: bool
    skipped: bool
    message: str


class DependencyInstaller:
    """Phát hiện & cài thư viện thiếu, có allowlist + cổng phê duyệt."""

    def __init__(self, extra_allow: frozenset[str] | None = None) -> None:
        self.allowlist = _ALLOWLIST | (extra_allow or frozenset())

    # ------------------------------------------------------------------ #
    @staticmethod
    def detect_imports(code: str) -> set[str]:
        """Bóc tên module cấp cao nhất được import trong code (qua AST)."""
        import ast

        modules: set[str] = set()
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return modules
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                modules.add(node.module.split(".")[0])
        return modules

    def find_missing(self, code: str) -> list[str]:
        """
        Trả danh sách TÊN GÓI PIP còn thiếu (chưa import được trong env hiện tại).

        Bỏ qua stdlib và module nội bộ của AURA (core/tools/brains/...).
        """
        internal = {"core", "tools", "brains", "agents", "evolution", "interface"}
        missing: list[str] = []
        for mod in self.detect_imports(code):
            if mod in _STDLIB_HINT or mod in internal:
                continue
            if importlib.util.find_spec(mod) is not None:
                continue  # đã có sẵn
            pip_name = _IMPORT_TO_PIP.get(mod, mod)
            if pip_name not in missing:
                missing.append(pip_name)
        return missing

    def is_allowed(self, package: str) -> bool:
        return package in self.allowlist

    # ------------------------------------------------------------------ #
    def install(
        self, package: str, approved: bool, confirmed_name: str | None = None
    ) -> InstallOutcome:
        """
        Cài MỘT gói. Bắt buộc approved=True.

        - approved=False -> bỏ qua (không cài).
        - Gói ngoài allowlist -> đòi confirmed_name khớp đúng tên (chống typosquat).
        - Cài qua python -m pip, không shell.
        """
        if not approved:
            return InstallOutcome(package, ok=False, skipped=True,
                                  message="Chưa được phê duyệt — bỏ qua.")

        if not self.is_allowed(package):
            if confirmed_name != package:
                return InstallOutcome(
                    package, ok=False, skipped=True,
                    message=(
                        f"'{package}' KHÔNG có trong allowlist. Để cài, phải xác nhận "
                        f"gõ lại chính xác tên gói. (Cảnh giác typosquatting!)"
                    ),
                )
            logger.warning("Cài gói NGOÀI allowlist đã được xác nhận tên: %s", package)

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "install", package],
                capture_output=True, text=True, timeout=300,
            )
        except subprocess.TimeoutExpired:
            return InstallOutcome(package, ok=False, skipped=False,
                                  message="pip install quá thời gian (300s).")
        except Exception as exc:  # noqa: BLE001
            return InstallOutcome(package, ok=False, skipped=False,
                                  message=f"Lỗi chạy pip: {exc}")

        if proc.returncode == 0:
            return InstallOutcome(package, ok=True, skipped=False,
                                  message="Cài thành công.")
        return InstallOutcome(package, ok=False, skipped=False,
                              message=f"pip lỗi: {proc.stderr[-300:]}")


__all__ = ["DependencyInstaller", "InstallOutcome"]
