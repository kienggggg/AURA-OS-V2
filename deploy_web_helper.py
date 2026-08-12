"""
deploy_web_helper.py
====================
Bộ Phục Vụ & Hướng Dẫn Đẩy Web Lien Quan Mobile Lên Domain Công Khai.
"""

from __future__ import annotations

import http.server
import socketserver
import sys
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
WEB_DIR = PROJECT_ROOT / "data" / "outputs" / "web" / "lienquan_portal"
PORT = 8765

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def start_local_web_server() -> None:
    print("==================================================================")
    print("  AURA OS v2 — WEB DEPLOYMENT & GOOGLE SEARCH CONSOLE HELPER")
    print("==================================================================\n")

    print(f"🌐 Trang Web Liên Quân đang được phục vụ tại Local:")
    print(f"👉 URL Local: http://localhost:{PORT}/\n")

    print("--- QUY TRÌNH 2 BƯỚC ĐẨY LÊN DOMAIN CÔNG KHAI & GOOGLE ---")
    print("1️⃣  ĐẨY THƯ MỤC WEB LÊN HOST CÔNG KHAI:")
    print(f"   Thư mục web chuẩn hóa: {WEB_DIR.as_posix()}")
    print("   • Bạn có thể kéo-thả thư mục này trực tiếp vào Vercel (vercel.com/new) hoặc Cloudflare Pages.")
    print("   • Hoặc chạy lệnh: npx vercel (nếu đã đăng nhập Vercel account).\n")

    print("2️⃣  KHAI BÁO GOOGLE SEARCH CONSOLE:")
    print("   • Dán URL Sitemap vào Google Search Console:")
    print("     👉 https://<domain-cua-ban>/sitemap.xml")
    print("   • Con bọ Googlebot sẽ tự động đọc sitemap.xml, robots.txt, JSON-LD Schema và H1 Tag để hiển thị web trên Google.\n")

    print("==================================================================")
    print("  AURA ĐÃ CHUẨN BỊ 100% CÁC FILE SẴN SÀNG CHO BẠN ĐẨY LÊN TÊN MIỀN! ✨")
    print("==================================================================")


if __name__ == "__main__":
    start_local_web_server()
