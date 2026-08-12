"""
core/triad_council.py
=====================
TRIAD COUNCIL (bản "xịn") — nhân mạng 3 thực thể + VÒNG HỌC từ Sếp.

  • Agent_Generator (LLM, tier cấu hình) : nhận lệnh + LUẬT đã học -> {"task_id","code_payload"}.
  • Agent_Validator (Sandbox tất định)   : lọc an ninh AST + chạy thử cô lập (PASS/FAIL).
  • Human Gate (Sếp nghiệm thu)          : code sạch sandbox -> trình Sếp DUYỆT (Y/lý do).
  • Master_AURA (Điều phối + Học)        : Sếp bác -> ghi LUẬT vào system_rules (ChromaDB),
                                            nhồi lại cho Generator vòng sau; PASS -> lưu đĩa.

"Học dần" = In-context Learning + RAG: KHÔNG fine-tune. Mỗi lần Sếp bác, lý do được lưu
vào `system_rules`; lần sau chỉ những luật LIÊN QUAN tới task được recall (semantic) và
nhồi vào prompt — nên không làm vỡ context của model nhỏ (gemma:e2b).

Human Gate KHÔNG dùng input() (chết khi chạy nền pythonw). Dùng `reviewer` bất đồng bộ:
  - mặc định: console reviewer (chạy tay trong terminal, an toàn khi không có stdin).
  - tích hợp chat: `make_event_reviewer(on_request)` -> (reviewer, resolve) kiểu Vibe Diff:
    council CHỜ tới khi phía chat gọi resolve(task_id, approved, reason).

Giao thức giữa các agent: THUẦN JSON. Output không-JSON bị coi là vi phạm, phải làm lại.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from pathlib import Path

logger = logging.getLogger("aura.triad_council")

_JSON_FORMAT = {"type": "json_object"}
# Trần token output cho Generator. Cần RỘNG vì model thinking (Gemini 2.5-flash) tiêu nhiều
# token reasoning trước khi in JSON; chật quá -> code_payload bị cắt cụt -> JSON hỏng.
_GEN_MAX_TOKENS = 8192
_MAX_RETRIES = 3
_RECALL_K = 5

_GENERATOR_SYSTEM = (
    "Bạn là Agent_Generator của AURA. CHỈ in DUY NHẤT một object JSON hợp lệ, không markdown, "
    "không lời dẫn ngoài JSON. Định dạng: "
    '{"task_id": <int>, "code_payload": "<mã Python hoàn chỉnh dạng chuỗi, xuống dòng bằng \\n>"}.'
    "\n\nMÃ trong code_payload BẮT BUỘC tuân HỢP ĐỒNG TOOL của AURA (nếu không sẽ bị Sandbox loại):\n"
    "1) Dòng đầu: `from core.schemas import ToolResult` (KHÔNG import gì khác nếu không thật sự cần).\n"
    "2) Có ĐÚNG MỘT entrypoint tên `tool_<tên_việc>` nhận `**params` và CHÚ THÍCH trả `-> ToolResult`, "
    "ví dụ: `def tool_nth_prime(**params) -> ToolResult:`.\n"
    "3) Lấy tham số từ `params` (vd `n = params.get(\"n\")`) và VALIDATE đầu vào.\n"
    "4) Thành công: `return ToolResult.success(\"<tên.tool>\", \"<chuỗi kết quả>\")`. "
    "Lỗi/tham số sai: `return ToolResult.failure(\"<tên.tool>\", \"<thông điệp>\")`. "
    "TUYỆT ĐỐI không để exception thoát ra ngoài — bọc toàn bộ thân hàm trong try/except và "
    "trả ToolResult.failure khi lỗi.\n"
    "5) CẤM: os.system, subprocess, eval, exec, __import__, shutil.rmtree, os.remove, socket, "
    "ctypes... (CodeGate sẽ chặn).\n"
    "6) `requests`, `urllib`, `open()` ĐƯỢC PHÉP dùng cho việc mạng/ghi file THẬT (tải trang, "
    "tải file, gọi API, lưu vào data/downloads/). TUYỆT ĐỐI KHÔNG viết code MÔ PHỎNG/GIẢ LẬP "
    "(vd trả ToolResult.success() mà không thật sự làm việc được yêu cầu) — nếu việc khó quá "
    "để làm THẬT trong một hàm, cứ viết code THẬT dùng thư viện cho phép, đừng giả vờ xong.\n\n"
    "KHUNG MẪU ĐÚNG (bám sát khung này):\n"
    "from core.schemas import ToolResult\n"
    "def tool_nth_prime(**params) -> ToolResult:\n"
    "    try:\n"
    "        n = int(params.get(\"n\", 0))\n"
    "        if n < 1:\n"
    "            return ToolResult.failure(\"math.nth_prime\", \"n phải là số nguyên >= 1\")\n"
    "        count, num = 0, 1\n"
    "        while count < n:\n"
    "            num += 1\n"
    "            if all(num % d for d in range(2, int(num ** 0.5) + 1)):\n"
    "                count += 1\n"
    "        return ToolResult.success(\"math.nth_prime\", f\"Số nguyên tố thứ {n} là {num}\")\n"
    "    except Exception as exc:\n"
    "        return ToolResult.failure(\"math.nth_prime\", str(exc))\n\n"
    "Nếu input có 'must_obey_rules', BẮT BUỘC tuân thủ TẤT CẢ các luật đó. "
    "Nếu có 'previous_error', SỬA code theo lỗi/lý do đó."
)


class CouncilProtocolError(Exception):
    """Output không phải JSON hợp lệ -> vi phạm giao thức."""


# --------------------------------------------------------------------------- #
# Trích JSON nghiêm ngặt
# --------------------------------------------------------------------------- #
def _extract_json(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        raise CouncilProtocolError("output rỗng")
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:  # noqa: BLE001
        pass
    start = raw.find("{")
    if start == -1:
        raise CouncilProtocolError("không tìm thấy JSON object")
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(raw[start:i + 1])
                    if isinstance(obj, dict):
                        return obj
                    raise CouncilProtocolError("JSON không phải object")
                except CouncilProtocolError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    raise CouncilProtocolError(f"JSON hỏng: {exc}") from exc
    raise CouncilProtocolError("JSON không cân bằng ngoặc")


# --------------------------------------------------------------------------- #
# Sandbox mặc định: cổng AST (an ninh) + smoke test
# --------------------------------------------------------------------------- #
def _default_sandbox(code: str) -> tuple[bool, str]:
    try:
        from evolution.gate import CodeGate
        gate = CodeGate().check(code)
        if not gate.ok:
            return False, "CodeGate chặn (an ninh AST):\n" + gate.feedback()
    except Exception as exc:  # noqa: BLE001
        logger.warning("CodeGate không dùng được (bỏ kiểm AST): %s", exc)
    try:
        from evolution.sandbox import Sandbox
        res = Sandbox().smoke_test(code)
        return bool(res.ok), ("" if res.ok else res.summary())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sandbox không dùng được (fallback compile): %s", exc)
        try:
            compile(code, "<council>", "exec")
            return True, ""
        except SyntaxError as se:
            return False, f"SyntaxError: {se}"


# --------------------------------------------------------------------------- #
# Human Gate kiểu Vibe Diff: bắn yêu cầu ra ngoài, CHỜ phía chat resolve
# --------------------------------------------------------------------------- #
def make_event_reviewer(on_request):
    """
    Trả (reviewer, resolve) để nối Human Gate vào Chat Window (Vibe Diff).

    - `on_request(task_id, code, task)`: được gọi để ĐẨY yêu cầu duyệt ra UI (vd bỏ
      approval_request vào event_queue -> Chat hiện code + hỏi 'Y/không').
    - `reviewer(code, task)` (async): CHỜ tới khi phía chat gọi `resolve(...)`.
    - `resolve(task_id, approved, reason="")`: phía orchestrator gọi khi Sếp trả lời.
    """
    pending: dict = {}

    async def reviewer(code: str, task: dict) -> dict:
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        pending[task["task_id"]] = fut
        try:
            on_request(task["task_id"], code, task)
        except Exception as exc:  # noqa: BLE001 — bắn UI lỗi -> coi như chưa duyệt
            logger.warning("on_request lỗi: %s", exc)
        try:
            return await fut
        finally:
            pending.pop(task["task_id"], None)

    def resolve(task_id, approved: bool, reason: str = "") -> bool:
        fut = pending.get(task_id)
        if fut is None or fut.done():
            return False
        fut.get_loop().call_soon_threadsafe(
            fut.set_result, {"approved": bool(approved), "reason": reason}
        )
        return True

    return reviewer, resolve


# --------------------------------------------------------------------------- #
# Council
# --------------------------------------------------------------------------- #
class TriadCouncil:
    """Hội đồng 3 thực thể + Human Gate + học luật. Mọi phụ thuộc tiêm được để test."""

    def __init__(
        self,
        cloud_json_fn=None,
        sandbox_fn=None,
        reviewer=None,
        memory=None,
        save_dir: str | Path | None = None,
        max_retries: int = _MAX_RETRIES,
        generator_tier: str = "local",
        recall_k: int = _RECALL_K,
    ) -> None:
        self._cloud_json = cloud_json_fn or self._default_generate
        self._sandbox = sandbox_fn or _default_sandbox
        self._reviewer = reviewer            # async (code, task) -> {approved, reason}
        self._memory = memory                # MemoryStore-like; None -> nạp lười
        self._mem_tried = memory is not None
        self.max_retries = max(1, int(max_retries))
        self.recall_k = max(1, int(recall_k))
        self.save_dir = self._resolve_save_dir(save_dir)
        self._engines_cache = None
        t = (generator_tier or "local").strip().lower()
        self._generator_tier = t if t in ("local", "cloud", "auto") else "local"
        self.votes: list[dict] = []

    # ---- engine LLM ----
    def _engines(self):
        if self._engines_cache is None:
            try:
                from core.llm import build_engines
                self._engines_cache = build_engines()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Không dựng được engine LLM: %s", exc)
                self._engines_cache = (None, None)
        return self._engines_cache

    @staticmethod
    def _safe_complete(eng, messages, system):
        # max_tokens RỘNG: model "thinking" (vd Gemini 2.5-flash) tiêu nhiều token cho lý luận
        # nội bộ — nếu chật, JSON code_payload bị CẮT CỤT giữa chừng -> GEN_BADJSON. 8192 đủ
        # cho cả thinking lẫn tool dài.
        try:
            return eng.complete(messages, system_prompt=system, temperature=0.0,
                                max_tokens=_GEN_MAX_TOKENS, response_format=_JSON_FORMAT,
                                tier="smart")   # codegen = việc KHÓ -> GPT-4o; router tự fallback nếu hết
        except TypeError:
            return eng.complete(messages, system_prompt=system, temperature=0.0,
                                max_tokens=_GEN_MAX_TOKENS, tier="smart")

    def _default_generate(self, system: str, user: str) -> str:
        local, cloud = self._engines()
        eng = (local or cloud) if self._generator_tier == "local" else (cloud or local)
        if eng is None:
            raise CouncilProtocolError("không có engine LLM khả dụng")
        res = self._safe_complete(eng, [{"role": "user", "content": user}], system)
        if not res.get("ok"):
            raise CouncilProtocolError(f"engine lỗi: {res.get('error', '?')}")
        return res.get("text", "")

    @staticmethod
    def _resolve_save_dir(save_dir) -> Path:
        if save_dir:
            return Path(save_dir)
        try:
            from core.config import settings
            return Path(settings.generated_tools_dir)
        except Exception:  # noqa: BLE001
            return Path(__file__).resolve().parent.parent / "data" / "tools_generated"

    # ---- Tàng Kinh Các: system_rules ChromaDB (RAG) ----
    def _get_memory(self):
        if not self._mem_tried:
            self._mem_tried = True
            try:
                from core.memory import MemoryStore
                self._memory = MemoryStore()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Không mở được MemoryStore (bỏ học luật): %s", exc)
                self._memory = None
        return self._memory

    def _recall_rules(self, task: dict) -> list[str]:
        """RAG: chỉ lôi LUẬT liên quan tới task hiện tại (không nhồi cả kho)."""
        mem = self._get_memory()
        if mem is None:
            return []
        try:
            recs = mem.recall_rules(task.get("instruction", ""), k=self.recall_k)
            return [r.text for r in recs]
        except Exception as exc:  # noqa: BLE001
            logger.warning("recall_rules lỗi (bỏ qua): %s", exc)
            return []

    def _remember_rejection(self, task: dict, reason: str) -> None:
        mem = self._get_memory()
        if mem is None:
            return
        try:
            mem.remember_rule(
                context=task.get("instruction", "")[:200],
                error="Sếp BÁC code do Generator viết",
                solution=reason,
            )
            logger.info("Đã khắc luật từ Sếp: %s", reason[:120])
        except Exception as exc:  # noqa: BLE001
            logger.warning("remember_rule lỗi (bỏ qua): %s", exc)

    # ================================================================= #
    # 3 THỰC THỂ + Human Gate
    # ================================================================= #
    async def agent_generator(self, task: dict, error_log: str = "",
                              rules: list[str] | None = None) -> dict:
        """Generator (tier cấu hình, mặc định Local) -> JSON, có nhồi LUẬT đã học."""
        user = json.dumps({
            "task_id": task["task_id"],
            "instruction": task["instruction"],
            "previous_error": error_log or None,
            "must_obey_rules": rules or None,
        }, ensure_ascii=False)
        raw = await asyncio.to_thread(self._cloud_json, _GENERATOR_SYSTEM, user)
        obj = _extract_json(raw)
        payload = str(obj.get("code_payload", "")).strip()
        if not payload:
            raise CouncilProtocolError("thiếu 'code_payload' trong JSON")
        return {"task_id": obj.get("task_id", task["task_id"]), "code_payload": payload}

    async def agent_validator(self, payload: dict) -> dict:
        """Validator = Sandbox tất định (an ninh + chạy thử). JSON {status, error_log}."""
        ok, log = await asyncio.to_thread(self._sandbox, payload.get("code_payload", ""))
        return {"status": "PASS" if ok else "FAIL", "error_log": "" if ok else log[:1000]}

    async def _review(self, code: str, task: dict) -> dict:
        """Human Gate: hỏi Sếp duyệt. Reviewer lỗi/thiếu -> coi như BÁC (an toàn)."""
        reviewer = self._reviewer or self._console_reviewer
        try:
            res = reviewer(code, task)
            if asyncio.iscoroutine(res):
                res = await res
            return {"approved": bool(res.get("approved")), "reason": str(res.get("reason", ""))}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Reviewer lỗi -> coi như BÁC: %s", exc)
            return {"approved": False, "reason": f"reviewer lỗi: {exc}"}

    async def _console_reviewer(self, code: str, task: dict) -> dict:
        """Reviewer mặc định cho chạy TAY trong terminal. Không có stdin -> BÁC (an toàn)."""
        def _ask() -> dict:
            print("\n" + "=" * 60)
            print(f"🕵️  MÃ CHỜ SẾP NGHIỆM THU (task {task.get('task_id')}):")
            print("-" * 60)
            print(code)
            print("=" * 60)
            try:
                choice = input("Sếp duyệt? (Y/N): ").strip().upper()
            except EOFError:
                return {"approved": False, "reason": "không có kênh nghiệm thu (chạy nền?)"}
            if choice == "Y":
                return {"approved": True, "reason": ""}
            try:
                reason = input("Lý do bác (AURA sẽ học): ").strip()
            except EOFError:
                reason = ""
            return {"approved": False, "reason": reason or "Sếp bác (không nêu lý do)"}
        return await asyncio.to_thread(_ask)

    # ================================================================= #
    async def master_deliberate(self, task: dict) -> dict:
        """
        Vòng đời 1 task: Generator (kèm LUẬT) -> Sandbox -> Human Gate.
        Sếp BÁC -> ghi luật + nhồi lý do, viết lại (tối đa max_retries). DUYỆT -> lưu đĩa.
        """
        rules = self._recall_rules(task)
        error_log = ""
        # Trần thời gian CỨNG mỗi bước: dù treo ở đâu không lường trước (mạng "đen", subprocess
        # kẹt...) cũng thất bại CÓ TIẾNG trong thời gian giới hạn — không im lặng mãi mãi như
        # từng gặp (task không ghi nổi 1 dòng log dù chờ >10 phút).
        _GEN_TIMEOUT_S, _SANDBOX_TIMEOUT_S = 60.0, 30.0
        for attempt in range(1, self.max_retries + 1):
            try:
                gen = await asyncio.wait_for(
                    self.agent_generator(task, error_log, rules), timeout=_GEN_TIMEOUT_S)
            except CouncilProtocolError as exc:
                error_log = f"Generator vi phạm giao thức JSON: {exc}"
                self._record(task, attempt, "GEN_BADJSON", error_log)
                continue
            except asyncio.TimeoutError:
                error_log = f"Generator quá {_GEN_TIMEOUT_S:.0f}s không phản hồi (treo mạng?)."
                self._record(task, attempt, "GEN_TIMEOUT", error_log)
                continue

            try:
                vote = await asyncio.wait_for(
                    self.agent_validator(gen), timeout=_SANDBOX_TIMEOUT_S)
            except asyncio.TimeoutError:
                self._record(task, attempt, "SANDBOX_TIMEOUT",
                             f"Sandbox quá {_SANDBOX_TIMEOUT_S:.0f}s không phản hồi.")
                error_log = "Sandbox không phản hồi kịp."
                continue
            if vote["status"] != "PASS":
                self._record(task, attempt, "SANDBOX_FAIL", vote.get("error_log", ""))
                error_log = vote.get("error_log", "")
                continue

            verdict = await self._review(gen["code_payload"], task)   # Human Gate
            if verdict["approved"]:
                path = self._save(task, gen)
                self._record(task, attempt, "HUMAN_PASS", "")
                return {"task_id": task["task_id"], "status": "PASS",
                        "attempts": attempt, "path": str(path)}

            reason = (verdict.get("reason") or "").strip() or "Sếp bác (không nêu lý do)"
            self._remember_rejection(task, reason)          # HỌC: khắc vào system_rules
            rules = self._recall_rules(task)                # cập nhật luật cho vòng sau
            error_log = f"Sếp bác với lý do: {reason}"
            self._record(task, attempt, "HUMAN_REJECT", reason)

        return {"task_id": task["task_id"], "status": "FAIL",
                "attempts": self.max_retries, "error_log": error_log}

    async def convene(self, tasks: list[dict]) -> list[dict]:
        return await asyncio.gather(*(self.master_deliberate(t) for t in tasks))

    # ================================================================= #
    def _record(self, task: dict, attempt: int, status: str, log: str) -> None:
        self.votes.append({
            "task_id": task["task_id"], "attempt": attempt,
            "status": status, "note": (log or "")[:300],
        })
        logger.info("Council task=%s vòng %d -> %s", task["task_id"], attempt, status)

    def _save(self, task: dict, gen: dict) -> Path:
        self.save_dir.mkdir(parents=True, exist_ok=True)
        path = self.save_dir / f"council_task_{task['task_id']}_{int(time.time())}.py"
        path.write_text(gen["code_payload"], encoding="utf-8")
        logger.info("Council PASS (Sếp duyệt) -> lưu %s", path)
        return path


class CouncilChatBridge:
    """
    Cầu HUMAN GATE <-> Chat Window.

    - Khi Hội đồng cần Sếp nghiệm thu -> bắn 'approval_request' ra event_queue (Chat hiện code).
    - Tin "Y" / "không <lý do>" của Sếp ở lượt chat sau -> route vào `handle_reply` để resolve.
    An toàn xuyên luồng: resolve dùng call_soon_threadsafe (xem make_event_reviewer).
    """

    def __init__(self, council: "TriadCouncil", event_queue=None) -> None:
        self.council = council
        self.event_queue = event_queue
        self._reviewer, self._resolve = make_event_reviewer(self._on_request)
        council._reviewer = self._reviewer          # gắn Human Gate vào council
        self._pending: dict = {}                     # task_id -> code đang chờ duyệt
        self._in_flight: int = 0                     # số phiên Hội đồng ĐANG VIẾT (chưa pending)

    def _on_request(self, task_id, code: str, task: dict) -> None:
        self._pending[task_id] = code
        snippet = code if len(code) <= 1500 else code[:1500] + "\n# ...(cắt bớt)"
        msg = (f"🛡️ Hội đồng đã viết xong code cho task #{task_id} (đã qua Sandbox an toàn). "
               "Sếp nghiệm thu: gõ 'Y' để DUYỆT (lưu đĩa), hoặc 'không, <lý do>' để bắt viết "
               "lại — AURA sẽ khắc luật.\n\n```python\n" + snippet + "\n```")
        if self.event_queue is not None:
            try:
                self.event_queue.put_nowait(
                    {"type": "approval_request", "text": msg, "task_id": task_id})
            except Exception as exc:  # noqa: BLE001
                logger.warning("Không bắn được approval_request: %s", exc)

    @property
    def has_pending(self) -> bool:
        return bool(self._pending)

    def mark_started(self) -> None:
        """Đánh dấu một phiên Hội đồng bắt đầu chạy (đang viết code)."""
        self._in_flight += 1

    def mark_done(self) -> None:
        """Một phiên Hội đồng kết thúc (xong/lỗi) — gọi trong done-callback."""
        if self._in_flight > 0:
            self._in_flight -= 1

    @property
    def is_in_flight(self) -> bool:
        """Có phiên Hội đồng đang chạy (kể cả lúc đang chờ duyệt). Dùng kèm has_pending
        để biết riêng pha 'đang viết, chưa có gì duyệt'."""
        return self._in_flight > 0

    def handle_reply(self, text: str) -> tuple[bool, str]:
        """(handled, response). Xử lý Y/không cho review đang chờ; mơ hồ -> (False, '')."""
        if not self._pending:
            return False, ""
        from core.vibe_diff import is_approval, is_rejection
        task_id = next(iter(self._pending))
        if is_rejection(text):
            self._pending.pop(task_id, None)
            self._resolve(task_id, False, text.strip())
            return True, "Dạ, Sếp bác — Hội đồng sẽ viết lại theo lý do, AURA khắc luật vào sổ."
        if is_approval(text):
            self._pending.pop(task_id, None)
            self._resolve(task_id, True, "")
            return True, "Đã duyệt — Hội đồng lưu code ra ổ đĩa nội bộ."
        return False, ""


def convene_sync(tasks: list[dict], **kwargs) -> list[dict]:
    council = TriadCouncil(**kwargs)
    return asyncio.run(council.convene(tasks))


__all__ = ["TriadCouncil", "CouncilChatBridge", "CouncilProtocolError",
           "make_event_reviewer", "convene_sync"]
