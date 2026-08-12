"""
factory/qc.py
=============
Kiểm định chất lượng (QC) — chạy tự động ngay sau khi handler của một job xong,
TRƯỚC khi job được đánh dấu 'done'. Mỗi product_line có bộ kiểm riêng, thêm dần
ở Phase 1 (video), Phase 2 (novel), Phase 3 (comic). product_line chưa có bộ
kiểm (kể cả "_debug") thì coi như PASS luôn — không chặn tool mới ra đời.

Report lưu ra <artifacts_dir>/qc_report.json để dashboard hiển thị ở tab QC.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from factory.models import JobRecord


@dataclass
class QCReport:
    passed: bool
    checks: list[dict] = field(default_factory=list)
    path: str = ""


def _write(job: JobRecord, report: QCReport) -> QCReport:
    if job.artifacts_dir:
        out = Path(job.artifacts_dir) / "qc_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {"passed": report.passed, "checks": report.checks, "ts": time.time()},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        report.path = str(out)
    return report


def _pass_through(job: JobRecord) -> QCReport:
    return QCReport(passed=True, checks=[
        {"name": "no_qc_defined", "ok": True,
         "note": "Chưa có bộ kiểm định cho product_line này."},
    ])


# Đăng ký qua register_checker() — mỗi tool tự đăng ký bộ kiểm của product_line
# mình lúc import (xem factory/tools/video_batch.py làm mẫu).
_CHECKERS: dict[str, Callable[[JobRecord], QCReport]] = {}


def register_checker(product_line: str, fn: Callable[[JobRecord], QCReport]) -> None:
    _CHECKERS[product_line] = fn


def run(product_line: str, job: JobRecord) -> QCReport:
    checker = _CHECKERS.get(product_line, _pass_through)
    report = checker(job)
    return _write(job, report)


__all__ = ["QCReport", "run", "register_checker"]
