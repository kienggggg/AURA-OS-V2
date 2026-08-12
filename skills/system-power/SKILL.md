---
name: system.power
description: CẤP 2 — Ngủ đông PHẦN CỨNG (PC Hibernate). Cho cả laptop vào trạng thái ngủ/ngủ đông Windows qua rundll32 powrprof. Dùng khi Sếp nói "laptop ngủ đông", "máy tính đi ngủ", "sleep máy". HÀNH ĐỘNG NẶNG, KHÔNG ĐẢO NGƯỢC TỨC THỜI — bắt buộc qua VIBE DIFF, chờ Sếp gõ 'Y' mới chạy.
entrypoint: scripts/power.py
function: hibernate_laptop
version: 1.0.0
tier: local
cost: free
permissions: [shell]
---

# System Power — "Ngủ đông phần cứng"

Cấp 2 trong hệ quản lý năng lượng 2 cấp của AURA:
- **Cấp 1 (AURA Sleep):** đóng băng nhịp ngầm của AURA — xem `core/daemon.py`
  (`freeze_aura`/`unfreeze_aura`), trigger "aura ngủ đông" / "aura thức dậy".
- **Cấp 2 (PC Hibernate — skill này):** cho cả LAPTOP ngủ.

## Khi nào dùng
- Sếp nói: *"laptop ngủ đông"*, *"máy tính đi ngủ"*, *"sleep máy"*, *"cho máy ngủ"*.

## Hàm thực thi
`hibernate_laptop()` — gọi lệnh Windows:
```
rundll32.exe powrprof.dll,SetSuspendState 0,1,0
```
(Lưu ý kỹ thuật: tham số `0,1,0` = SetSuspendState(Hibernate=0, Force=1, WakeEvent=0)
-> thực tế đưa máy vào **Sleep/Suspend**. Muốn ngủ-đông-thật (ghi RAM ra đĩa) đổi
đối số đầu thành `1` VÀ bật Hibernate trong Windows: `powercfg /hibernate on`.)

## An toàn (Vibe Diff)
- Đây là hành động NẶNG (đóng băng phần cứng) -> Orchestrator BẮT BUỘC in dòng xác
  nhận và **chờ Sếp gõ 'Y'** mới chạy (Human-in-the-loop).
- Skill TIN CẬY (hand-written), cố ý được phép gọi lệnh hệ thống — khác code TỰ SINH
  (bị CONTEXT §5 cấm os.system). Có chốt chặn: chỉ chạy trên Windows, bọc try/except,
  luôn trả ToolResult (không ném exception).
