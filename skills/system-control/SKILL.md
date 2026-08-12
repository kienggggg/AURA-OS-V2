---
name: system.control
description: Tay chân điều khiển "căn nhà" (laptop) — mở app, mở file/thư mục/URL, liệt kê & dọn dẹp file (di chuyển/đổi tên/sao chép/xoá vào thùng rác), xem dung lượng ổ/RAM. MỌI thao tác đều qua cổng VIBE DIFF xin Sếp duyệt.
entrypoint: scripts/controller.py
function: tool_system_control
version: 1.0.0
tier: local
cost: free
permissions: [file_write, shell]
---

# System Control — "Tay chân" của AURA

Biến AURA từ "trợ lý biết nói" thành "trợ lý điều khiển căn nhà": thao tác thật trên
laptop của Sếp. Thiết kế theo **hành động tường minh** (không chạy shell tự do) để an
toàn, và **mọi hành động có tác dụng phụ đều qua cổng VIBE DIFF** xin duyệt trước.

Tuân thủ `CONTEXT.md`: bọc try/except (§2), trả `ToolResult` (không ném), validate
input (§7), **least privilege** (§6) — chỉ thao tác trong thư mục an toàn, CHẶN thư mục
hệ thống & path traversal; xoá → **Thùng rác** (không xoá cứng trừ khi ép). KHÔNG dùng
`shell=True`, không `eval/exec`.

## Khi nào DÙNG
- Mở ứng dụng (Notepad, Calculator, trình duyệt...), mở file/thư mục/đường link.
- Dọn dẹp: liệt kê, di chuyển, đổi tên, sao chép, xoá (vào Thùng rác) file.
- Xem nhanh dung lượng ổ đĩa / RAM.

## Khi nào KHÔNG dùng
- Cào web (web.scrape/web.agent), tải truyện (manga.download), săn việc (job.scout).
- Thao tác phá huỷ trên thư mục hệ thống → bị CHẶN cứng.

## Hai cách gọi
**1) Hành động tường minh (đáng tin nhất):**

| Tham số | Ý nghĩa |
|---|---|
| `action` | `sysinfo` · `list_dir` · `mkdir` · `move` · `rename` · `copy` · `delete` · `open_app` · `open_path` · `open_url` |
| `target` | đối tượng chính (đường dẫn / tên app / URL) |
| `dst` | đích (cho move/rename/copy) |
| `force` | `true` để xoá CỨNG khi không có Thùng rác (mặc định false → an toàn) |

**2) Câu lệnh tự nhiên** (`command`): skill tự suy ra action (best-effort). Không chắc
chắn → trả lỗi kèm gợi ý, KHÔNG đoán liều thao tác phá huỷ.

## Hướng dẫn thực thi (Instructions)
- Đường chính: `registry.execute_tool("system.control", {"action":"open_app","target":"notepad"})`.
- Hoặc: `registry.execute_tool("system.control", {"command":"mở Notepad"})`.
- CLI:
  ```bash
  python skills/system-control/scripts/controller.py --action sysinfo
  python skills/system-control/scripts/controller.py --action list_dir --target ~/Downloads
  ```

## An toàn (rào cản cứng)
- Thư mục cho phếp: HOME, thư mục làm việc, TEMP, data của AURA (đổi qua `allowed_roots`).
- CHẶN: `/etc /usr /bin /sbin /boot /sys /proc /var`, `C:\Windows`, `C:\Program Files`, và mọi `..`.
- `delete` mặc định đẩy vào **Thùng rác** (`send2trash` nếu có); không có thì TỪ CHỐI xoá cứng trừ khi `force=true` và đường dẫn an toàn.
- App chỉ mở theo **allowlist**; mở app lạ cần khai báo trước.

## Đầu ra
`ToolResult.output`: JSON/markdown mô tả kết quả (đường dẫn, danh sách, dung lượng...).
`artifacts` chứa đường dẫn vừa tạo/đổi nếu có.
