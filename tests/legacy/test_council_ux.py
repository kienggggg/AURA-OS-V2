"""Test UX fix §11.B3: gõ 'Y' khi Council đang VIẾT (chưa pending) phải được trả lời rõ,
không lọt xuống chat thường."""
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
sys.path.insert(0, r"D:\AURA_OS_v2")

from core.triad_council import CouncilChatBridge
from core.orchestrator import AURA_Orchestrator

ok = 0
def check(name, cond):
    global ok
    print(("[PASS] " if cond else "[FAIL] ") + name)
    ok += 0 if cond else 1

class FakeCouncil:
    _reviewer = None

# ---- A. Bridge in-flight counter ----
b = CouncilChatBridge(FakeCouncil())
check("fresh: no pending, not in-flight", not b.has_pending and not b.is_in_flight)
b.mark_started()
check("mark_started -> in-flight, NOT pending (đang viết)", b.is_in_flight and not b.has_pending)
b._pending["1"] = "code"  # giả lập _on_request: có gì đó để duyệt
check("pending arrives -> both true", b.has_pending and b.is_in_flight)
b.mark_done()
check("mark_done -> not in-flight, vẫn pending chờ duyệt", (not b.is_in_flight) and b.has_pending)
# bộ đếm không âm
b.mark_done(); b.mark_done()
check("mark_done không cho âm", b._in_flight == 0)

# ---- B. handle_reply không vỡ khi rỗng ----
b2 = CouncilChatBridge(FakeCouncil())
check("handle_reply rỗng -> (False,'')", b2.handle_reply("Y") == (False, ""))

# ---- C. Orchestrator routing (object.__new__: chỉ set council_bridge) ----
o = AURA_Orchestrator.__new__(AURA_Orchestrator)
o.council = FakeCouncil()
o.council_bridge = CouncilChatBridge(o.council)

# C1: đang viết + 'Y' sớm -> thông báo rõ, KHÔNG lọt chat
o.council_bridge.mark_started()
r1 = o.process_message("Y")
check("đang viết + 'Y' -> báo 'chưa có gì để Sếp duyệt'", "chưa có gì để Sếp duyệt" in r1)
r1b = o.process_message("ok duyệt đi")
check("đang viết + 'ok duyệt' -> cùng thông báo", "chưa có gì để Sếp duyệt" in r1b)

# C2: có pending + 'Y' -> đi đúng nhánh handle_reply (duyệt)
o.council_bridge._pending["42"] = "print(1)"
r2 = o.process_message("Y")
check("pending + 'Y' -> 'Đã duyệt'", "Đã duyệt" in r2)

print()
print("KẾT QUẢ:", "TẤT CẢ PASS" if ok == 0 else f"{ok} FAIL")
sys.exit(ok)
