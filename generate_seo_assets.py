"""
generate_seo_assets.py
======================
Tạo sitemap.xml và robots.txt chuẩn Google Search Console cho Trang Web Liên Quân.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
WEB_DIR = PROJECT_ROOT / "data" / "outputs" / "web" / "lienquan_portal"

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def generate_seo_files(domain: str = "https://lienquanmeta.vercel.app") -> None:
    print("==================================================================")
    print("  LIÊN QUÂN PORTAL — KHỞI TẠO FILE TỐI ƯU GOOGLE SEARCH CONSOLE")
    print("==================================================================\n")

    # 1. robots.txt
    robots_content = f"""# robots.txt generated for Googlebot
User-agent: *
Allow: /

Sitemap: {domain}/sitemap.xml
"""
    robots_file = WEB_DIR / "robots.txt"
    robots_file.write_text(robots_content, encoding="utf-8")
    print(f"✅ Đã tạo robots.txt: {robots_file}")

    # 2. sitemap.xml
    sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{domain}/</loc>
    <lastmod>2026-07-24</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
"""
    sitemap_file = WEB_DIR / "sitemap.xml"
    sitemap_file.write_text(sitemap_content, encoding="utf-8")
    print(f"✅ Đã tạo sitemap.xml: {sitemap_file}\n")

    print("==================================================================")
    print("  KẾT QUẢ: 100% SẴN SÀNG CHO GOOGLE SEARCH CONSOLE INDEXING ✨")
    print("==================================================================")


if __name__ == "__main__":
    generate_seo_files()
