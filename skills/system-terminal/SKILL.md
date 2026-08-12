---
name: system.terminal
description: Công cụ thực thi lệnh Terminal/Shell/Command Prompt/PowerShell trực tiếp trên máy tính. Dùng để chạy git, xem logs, hoặc gọi script CLI. Trả về kết quả thật sự từ stdout/stderr.
entrypoint: scripts/executor.py
function: tool_system_terminal
version: 1.0.0
tier: local
cost: free
permissions: [shell]
---

# System Terminal — Chạy lệnh Shell

Cho phép AURA chạy các lệnh terminal như `git log`, `dir`, `python script.py`, v.v.

## Khi nào DÙNG
- Sếp yêu cầu chạy lệnh terminal, CMD, hoặc PowerShell.
- Sếp muốn xem log của git, kiểm tra trạng thái thư mục, hệ thống qua command line.

## Tham số
- `command` (chuỗi, bắt buộc): Lệnh muốn chạy (VD: `git log -n 1`).
- `cwd` (chuỗi, tùy chọn): Thư mục để chạy lệnh. Nếu không có, mặc định lấy gốc hệ thống (PROJECT_ROOT).

## An toàn
- Mặc định chạy shell trực tiếp qua `subprocess`.
- Tránh chạy các lệnh tương tác dài hơi (interactive shells). Có timeout 60 giây.
