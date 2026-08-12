"""
evolution/engine.py
==================
EvolutionEngine — Lò phản ứng Tiến hóa: điều phối toàn bộ pipeline an toàn.

Đây chính là "core/evolution.py" mà sếp nhắc tới; theo ARCHITECTURE_v2 đã chốt,
nó nằm trong package evolution/ cùng các thành phần con.

LUỒNG BẤT BIẾN (mỗi bước có tác dụng phụ đều có cổng):

    CoderAgent.generate
        -> Validator.validate        (có BLOCK -> DỪNG)
        -> Sandbox.smoke_test        (lỗi/timeout -> DỪNG)
        -> Installer.find_missing     (thiếu lib -> hỏi duyệt -> cài allowlist)
        -> Loader.request_approval    (người đọc code, gật Y/N)
        -> Loader.load_into_registry  (hot-reload vào registry đang chạy)

Trả về EvolutionLog ghi lại từng chặng để soi khi cần.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from agents.coder_agent import CoderAgent
from core.brain_router import BrainRouter
from evolution.installer import DependencyInstaller
from evolution.loader import ApproveFn, ToolLoader
from evolution.sandbox import Sandbox
from evolution.validator import ASTValidator
from evolution.gate import CodeGate
from tools.registry import ToolRegistry

logger = logging.getLogger("aura.evolution.engine")

# Số lần ÉP CoderAgent tự sửa trước khi báo thất bại ra UI (Shift-Left).
_MAX_REMEDIATION_ATTEMPTS = 3


@dataclass
class EvolutionLog:
    """Nhật ký một lần tiến hóa — minh bạch từng chặng."""

    spec: str
    stages: list[str] = field(default_factory=list)
    success: bool = False
    tool_registered: str | None = None
    aborted_reason: str | None = None

    def stage(self, name: str, detail: str = "") -> None:
        entry = name if not detail else f"{name}: {detail}"
        self.stages.append(entry)
        logger.info("[evolution] %s", entry)


class EvolutionEngine:
    """Ráp Coder + Validator + Sandbox + Installer + Loader thành một quy trình."""

    def __init__(
        self,
        router: BrainRouter,
        registry: ToolRegistry,
        approve_fn: ApproveFn | None = None,
        install_approve_fn=None,
    ) -> None:
        self.coder = CoderAgent(router)
        self.validator = ASTValidator()
        # Cổng kiểm tĩnh (cú pháp + an ninh AST) cho vòng tự sửa Shift-Left.
        self.gate = CodeGate(validator=self.validator)
        self.sandbox = Sandbox()
        self.installer = DependencyInstaller()
        self.loader = ToolLoader(approve_fn=approve_fn)
        self.registry = registry
        # Cổng phê duyệt cài lib: (danh sách gói) -> True/False. Mặc định hỏi CLI.
        self._install_approve = install_approve_fn or self._default_install_approval

    # ------------------------------------------------------------------ #
    @staticmethod
    def _default_install_approval(packages: list[str]) -> bool:
        try:
            ans = input(
                f"  Cài các thư viện sau cho tool mới? {packages} [y/N]: "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return ans in {"y", "yes", "có", "co"}

    # ------------------------------------------------------------------ #
    def evolve(self, spec: str, tool_name_hint: str = "") -> EvolutionLog:
        """Chạy trọn pipeline tiến hóa cho một đặc tả. Trả EvolutionLog."""
        log = EvolutionLog(spec=spec)

        # 1-3) SINH CODE + CỔNG SHIFT-LEFT + SANDBOX — có VÒNG TỰ SỬA -------- #
        # Code tự sinh PHẢI qua cổng tĩnh (cú pháp + an ninh AST) và sandbox.
        # Nếu fail -> nhồi lỗi lại cho CoderAgent tự sửa, tối đa N lần, TRƯỚC khi
        # dám báo ra Avatar UI. Không bao giờ lộ code rác cho Sếp duyệt.
        candidate = None
        report = None
        sbx = None
        feedback = ""
        for attempt in range(1, _MAX_REMEDIATION_ATTEMPTS + 1):
            effective_spec = spec if not feedback else (
                f"{spec}\n\n# LỖI LẦN TRƯỚC — SỬA TRIỆT ĐỂ RỒI XUẤT LẠI:\n{feedback}"
            )
            log.stage("coder", f"sinh code ứng viên (lần {attempt}/{_MAX_REMEDIATION_ATTEMPTS})")
            candidate = self.coder.generate_tool(effective_spec, tool_name_hint)
            if candidate is None:
                feedback = "Không bóc được khối ```python hợp lệ. Xuất đúng MỘT khối python."
                log.stage("remediate", f"lần {attempt}: coder không ra code")
                continue

            # CỔNG TĨNH (Shift-Left): cú pháp + an ninh AST.
            gate_result = self.gate.check(candidate.code)
            report = gate_result.report
            if report is not None:
                log.stage("gate", report.summary().replace("\n", " | "))
            if not gate_result.ok:
                feedback = gate_result.feedback()
                log.stage("remediate", f"lần {attempt}: cổng tĩnh CHẶN -> tự sửa")
                continue

            # CỔNG ĐỘNG: chạy thử trong sandbox cô lập.
            sbx = self.sandbox.smoke_test(candidate.code)
            log.stage("sandbox", sbx.summary().replace("\n", " | "))
            if not sbx.ok:
                feedback = f"Sandbox báo lỗi khi chạy thử:\n{sbx.summary()}"
                log.stage("remediate", f"lần {attempt}: sandbox fail -> tự sửa")
                continue

            log.stage("gate", f"ĐẠT cổng Shift-Left sau {attempt} lần tự sửa")
            break
        else:
            log.aborted_reason = (
                f"Hết {_MAX_REMEDIATION_ATTEMPTS} lần tự sửa mà code vẫn chưa đạt cổng "
                f"Shift-Left. Lỗi cuối:\n{feedback}"
            )
            log.stage("ABORT", log.aborted_reason)
            return log

        # 4) CÀI THƯ VIỆN THIẾU (allowlist + phê duyệt) ---------------- #
        missing = self.installer.find_missing(candidate.code)
        if missing:
            log.stage("installer", f"thiếu: {missing}")
            if not self._install_approve(missing):
                log.aborted_reason = "Người dùng từ chối cài thư viện."
                log.stage("ABORT", log.aborted_reason)
                return log
            for pkg in missing:
                # Gói ngoài allowlist sẽ bị chặn ở installer (cần confirm tên riêng).
                outcome = self.installer.install(pkg, approved=True)
                log.stage("install", f"{pkg}: {outcome.message}")
                if not outcome.ok:
                    log.aborted_reason = f"Cài '{pkg}' thất bại/bị chặn."
                    log.stage("ABORT", log.aborted_reason)
                    return log

        # 5) PHÊ DUYỆT NẠP (Human-in-the-loop) ------------------------- #
        report_text = f"{report.summary()}\n\n{sbx.summary()}"
        if not self.loader.request_approval(candidate.name, candidate.code, report_text):
            log.aborted_reason = "Người dùng không phê duyệt nạp tool."
            log.stage("ABORT", log.aborted_reason)
            return log

        # 6) HOT-RELOAD ------------------------------------------------ #
        load_result = self.loader.load_into_registry(
            candidate.name, candidate.code, self.registry
        )
        log.stage("loader", load_result.message)
        if load_result.ok:
            log.success = True
            log.tool_registered = load_result.registered_as
        else:
            log.aborted_reason = load_result.message
        return log


__all__ = ["EvolutionEngine", "EvolutionLog"]
