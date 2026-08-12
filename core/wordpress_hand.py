"""
core/wordpress_hand.py
======================
TAY ĐĂNG TRUYỆN qua **WordPress REST API** — sạch nhất trong các loại "tay chân":
dùng API CHÍNH CHỦ của site, không giả lập trình duyệt, không đụng lớp chống-bot,
không vi phạm ToS.

Phát hiện 2026-07-22: `huyensonquan.com` (Huyền Sơn Quán — trang truyện sáng tác
Việt) chạy WordPress, `/wp-json/` MỞ và **Application Passwords BẬT**. Nghĩa là
AURA đăng chương được bằng một request HTTP có xác thực chuẩn.

An toàn:
- Xác thực bằng **Application Password** (mã ứng dụng) — KHÔNG phải mật khẩu chính
  của Sếp, tạo/thu hồi độc lập ở wp-admin. AURA (và tôi) không bao giờ thấy mật
  khẩu thật.
- Mặc định đăng ở trạng thái **draft (nháp)** — không có gì lên công khai khi Sếp
  chưa duyệt. Muốn công khai: đổi WP_DEFAULT_STATUS=publish hoặc truyền status.

Cấu hình trong .env:
    WP_SITE_URL=https://huyensonquan.com
    WP_USERNAME=<tên đăng nhập của Sếp>
    WP_APP_PASSWORD=<mã ứng dụng, dạng "abcd efgh ijkl mnop">
    WP_DEFAULT_STATUS=draft

Dùng:
    venv/Scripts/python.exe -m core.wordpress_hand --check
    venv/Scripts/python.exe -m core.wordpress_hand --series "Tên_Bộ" --chapter 7
"""

from __future__ import annotations

import argparse
import html
import logging
import sys
from pathlib import Path

import requests

from core.config import settings
from core.wattpad_hand import parse_chapter, latest_chapter, _find_chapter

logger = logging.getLogger(__name__)


def _auth() -> tuple[str, str] | None:
    """(user, app_password) nếu đã cấu hình; None nếu chưa."""
    user = (settings.wp_username or "").strip()
    pw = settings.wp_app_password
    if not user or pw is None:
        return None
    return user, pw.get_secret_value()


def _api(path: str) -> str:
    return f"{settings.wp_site_url.rstrip('/')}/wp-json/wp/v2/{path.lstrip('/')}"


def check() -> str:
    """Kiểm tra cấu hình + xác thực: gọi /users/me (chỉ đọc, không đăng gì)."""
    auth = _auth()
    if auth is None:
        return ("⚠️ Chưa cấu hình. Cần WP_USERNAME + WP_APP_PASSWORD trong .env "
                "(tạo mã ứng dụng ở wp-admin > Hồ sơ > Application Passwords).")
    try:
        r = requests.get(_api("users/me"), auth=auth, timeout=25,
                         headers={"Accept": "application/json"})
    except requests.RequestException as exc:
        return f"⚠️ Không gọi được site: {exc}"
    if r.status_code == 401:
        return "⚠️ Sai tên đăng nhập hoặc mã ứng dụng (401). Kiểm tra lại .env."
    if r.status_code != 200:
        return f"⚠️ Site trả HTTP {r.status_code}: {r.text[:160]}"
    me = r.json()
    return (f"✅ Kết nối OK — đăng nhập với tư cách '{me.get('name')}' "
            f"(id {me.get('id')}). Quyền: {', '.join(me.get('roles', [])) or 'không rõ'}.")


def _to_html(paras: list[str]) -> str:
    """Đoạn văn -> HTML <p> (escape để không vỡ layout site)."""
    return "\n\n".join(f"<p>{html.escape(p)}</p>" for p in paras)


def publish_chapter(series: str, chapter: int, status: str | None = None) -> str:
    """Đăng 1 chương lên WordPress. Mặc định NHÁP (draft) — an toàn."""
    auth = _auth()
    if auth is None:
        return ("⚠️ Chưa cấu hình WP_USERNAME/WP_APP_PASSWORD trong .env — "
                "chạy `--check` để xem hướng dẫn.")
    ch_path = _find_chapter(series, chapter)
    title, paras = parse_chapter(ch_path)
    body = _to_html(paras)
    st = (status or settings.wp_default_status or "draft").strip().lower()
    if st not in ("draft", "publish", "pending", "private"):
        st = "draft"

    payload = {"title": title, "content": body, "status": st}
    try:
        r = requests.post(_api("posts"), auth=auth, json=payload, timeout=60,
                          headers={"Accept": "application/json"})
    except requests.RequestException as exc:
        return f"⚠️ Gửi bài lỗi mạng: {exc}"
    if r.status_code not in (200, 201):
        return f"⚠️ Site từ chối (HTTP {r.status_code}): {r.text[:200]}"
    d = r.json()
    link = d.get("link") or "(chưa có link)"
    nhan = "NHÁP (chưa công khai)" if st == "draft" else st.upper()
    return (f"✅ Đã đăng '{title}' lên {settings.wp_site_url} — trạng thái {nhan}.\n"
            f"🔗 {link}\n({len(paras)} đoạn, ~{len(body)} ký tự HTML)")


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tay đăng truyện qua WordPress REST API")
    ap.add_argument("--check", action="store_true", help="Kiểm tra cấu hình + xác thực")
    ap.add_argument("--series", help="Tên thư mục bộ truyện")
    ap.add_argument("--chapter", type=int, help="Số chương (bỏ trống = mới nhất)")
    ap.add_argument("--status", help="draft|publish|pending (mặc định theo .env)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if args.check:
        print(check()); return 0
    if args.series:
        ch = args.chapter or latest_chapter(args.series)
        if ch < 1:
            print("📭 Bộ này chưa có chương nào."); return 1
        print(publish_chapter(args.series, ch, status=args.status)); return 0
    ap.print_help(); return 1


if __name__ == "__main__":
    sys.exit(main())
