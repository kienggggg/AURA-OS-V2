"""
core/payhip_bot.py
==================
TAY ĐĂNG SẢN PHẨM SỐ PAYHIP — Đăng bán Ebook, Sách tô màu PDF lên Payhip.com
========================================================================
- Persistent Profile: data/payhip_profile/
- Mặc định: ĐĂNG NHÁP (Draft mode). Chỉ công khai khi có cờ --publish.
- Bán 19 cuốn sách tô màu có sẵn trong data/outputs/coloringbook/*
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from core.config import settings, PROJECT_ROOT
from factory.platform_rules import can_post

logger = logging.getLogger(__name__)

PROFILE_DIR = PROJECT_ROOT / "data" / "payhip_profile"
DEBUG_DIR = PROJECT_ROOT / "data" / "payhip_debug"
COLORING_DIR = PROJECT_ROOT / "data" / "outputs" / "coloringbook"

HOME = "https://payhip.com/"
LOGIN_URL = "https://payhip.com/auth/login"
ADD_PRODUCT_URL = "https://payhip.com/dashboard/products/add"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _context(headless: bool, use_chrome: bool = True):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Thiếu Playwright. Cài: pip install playwright && playwright install chromium"
        ) from exc
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    kw = dict(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        viewport={"width": 1400, "height": 950},
        locale="en-US",
        user_agent=UA,
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    if use_chrome:
        try:
            return pw, pw.chromium.launch_persistent_context(channel="chrome", **kw)
        except Exception as exc:  # noqa: BLE001
            pw.stop()
            raise SystemExit(
                f"❌ Không mở được Chrome với profile Payhip: {exc}"
            ) from exc
    return pw, pw.chromium.launch_persistent_context(**kw)


def _payhip_logged_in(page) -> bool:
    """Chỉ kết luận ĐÃ ĐĂNG NHẬP khi đang Ở TRÊN payhip.com và vào được khu
    dashboard. Không phán khi Sếp đang ở trang bên thứ ba (Google/PayPal)."""
    try:
        url = page.url or ""
    except Exception:  # noqa: BLE001 — page có thể đang điều hướng
        return False
    if "payhip.com" not in url:
        return False
    if "/auth/" in url or "/login" in url or "/signup" in url:
        return False
    return "/dashboard" in url or "/account" in url


def cmd_login(timeout_min: float = 20.0) -> None:
    """Mở cửa sổ Chrome cho Sếp đăng nhập Payhip 1 lần.

    KHÔNG dùng input(): chạy qua tool/daemon là không có TTY -> input() trả về
    ngay -> cửa sổ đóng sập trước khi Sếp kịp gõ (đúng bug đã gặp ở Rookies).
    Thay bằng CHỜ THỤ ĐỘNG: chỉ đọc URL, tuyệt đối không tự điều hướng để khỏi
    thổi bay form đăng nhập Sếp đang gõ dở.
    """
    print("=" * 60)
    print("PAYHIP LOGIN MODE — Đăng nhập Payhip thủ công")
    print("1. Cửa sổ Chrome đang mở trang Payhip login.")
    print("2. Sếp đăng nhập (hoặc đăng ký) tài khoản Payhip của Sếp.")
    print(f"3. Cứ để đó — bot tự nhận ra khi vào Dashboard (chờ tối đa {timeout_min:.0f} phút).")
    print("=" * 60)

    pw, ctx = _context(headless=False, use_chrome=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(LOGIN_URL)

    deadline = time.time() + timeout_min * 60
    ok = False
    try:
        while time.time() < deadline:
            # Sếp có thể mở tab mới (login bằng Google) -> quét mọi tab.
            for p in list(ctx.pages):
                if _payhip_logged_in(p):
                    page, ok = p, True
                    break
            if ok:
                break
            time.sleep(3)

        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        shot = DEBUG_DIR / "login_success.png"
        try:
            page.screenshot(path=str(shot))
        except Exception:  # noqa: BLE001
            shot = None

        if ok:
            time.sleep(2)  # để cookie kịp ghi xuống profile
            print(f"✅ ĐÃ ĐĂNG NHẬP Payhip — phiên lưu vào {PROFILE_DIR}")
            if shot:
                print(f"📸 Bằng chứng: {shot}")
        else:
            print("⏳ Hết giờ chờ mà chưa thấy Dashboard Payhip. Phiên CHƯA lưu.")
            print("   Chạy lại `python -m core.payhip_bot --login` khi Sếp rảnh.")
    finally:
        ctx.close()
        pw.stop()


def list_coloring_books() -> list[Path]:
    """Danh sách các file PDF sách tô màu sẵn có."""
    if not COLORING_DIR.is_dir():
        return []
    # PDF nằm trong thư mục con theo hash: coloringbook/<hash>/*.pdf (KHÔNG phải
    # ngay trong coloringbook/). Antigravity glob sai -> tìm ra 0 cuốn.
    return sorted(COLORING_DIR.glob("*/*.pdf")) or sorted(COLORING_DIR.glob("*.pdf"))


def check_seller_session() -> dict:
    """Kiểm tra phiên Payhip còn vào được dashboard hay không.

    Đây chỉ là kiểm tra phiên đăng nhập, *không* khẳng định Payhip đã duyệt payout
    hay đã có tiền. Việc xác minh danh tính/phương thức nhận tiền luôn do chủ tài
    khoản tự thực hiện trên Payhip.
    """
    pw = ctx = None
    try:
        pw, ctx = _context(headless=True, use_chrome=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(ADD_PRODUCT_URL, wait_until="domcontentloaded", timeout=30_000)
        logged_in = _payhip_logged_in(page)
        return {
            "ok": logged_in,
            "reason": "session_active" if logged_in else "login_required",
            "url": page.url if logged_in else "",
        }
    except BaseException as exc:  # _context có thể báo SystemExit khi thiếu Chrome/Playwright
        logger.warning("Không kiểm tra được phiên Payhip: %s", exc)
        return {"ok": False, "reason": "session_check_failed", "detail": str(exc)}
    finally:
        if ctx is not None:
            try:
                ctx.close()
            except Exception:  # noqa: BLE001
                pass
        if pw is not None:
            try:
                pw.stop()
            except Exception:  # noqa: BLE001
                pass


def upload_product(pdf_file: Path, price: float = 3.99, publish: bool = False) -> dict:
    """Upload 1 sản phẩm PDF tô màu lên Payhip (Mặc định: Nháp/Draft)."""
    ok, why = can_post("payhip")
    if not ok:
        print(f"❌ {why}")
        return {"success": False, "reason": why}

    pw, ctx = _context(headless=True, use_chrome=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    title = pdf_file.stem.replace("_", " ").title()
    desc = (
        f"High-quality digital coloring book: {title}. Instant PDF download with printable pages.\n\n"
        "For personal use only. This original digital coloring book may not be resold, "
        "redistributed, or offered with PLR, MRR, or resale rights."
    )

    result = {"success": False, "title": title, "file": str(pdf_file), "status": "draft"}

    try:
        page.goto(ADD_PRODUCT_URL, wait_until="networkidle", timeout=30000)
        time.sleep(2)

        if not _payhip_logged_in(page):
            print("❌ Phiên đăng nhập Payhip đã hết hạn. Hãy chạy `--login` để đăng nhập lại.")
            result["reason"] = "session_expired"
            return result

        # Chọn loại sản phẩm: Digital Product
        page.click("text=Digital Product", timeout=10000)
        time.sleep(2)

        # Upload file PDF
        file_input = page.locator("input[type='file']")
        if file_input.count() > 0:
            file_input.set_input_files(str(pdf_file))
            print(f"[+] Đã tải file: {pdf_file.name}")
            time.sleep(3)

        # Điền tiêu đề & giá
        page.fill("input[name='title']", title)
        page.fill("input[name='price']", str(price))

        # Điền mô tả
        page.fill("textarea[name='description']", desc)

        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        screenshot_path = DEBUG_DIR / f"draft_{pdf_file.stem}.png"
        page.screenshot(path=str(screenshot_path))
        print(f"📸 Đã lưu nháp sản phẩm: '{title}' (${price}). Ảnh bằng chứng: {screenshot_path}")

        if publish:
            # Nếu có cờ --publish mới bấm nút Add Product
            page.click("button:has-text('Add Product')", timeout=10000)
            time.sleep(3)
            result["status"] = "published"
            print(f"🎉 ĐÃ PUBLISH CÔNG KHAI: '{title}' lên Payhip!")
        else:
            print(f"✅ ĐÃ LƯU BẢN THẢO (Draft): '{title}'. Chưa publish theo quy định an toàn.")

        result["success"] = True

    except Exception as exc:
        print(f"⚠️ Lỗi upload Payhip: {exc}")
        result["reason"] = str(exc)
    finally:
        ctx.close()
        pw.stop()

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA Payhip Digital Product Bot")
    parser.add_argument("--login", action="store_true", help="Đăng nhập Payhip thủ công 1 lần")
    parser.add_argument("--list", action="store_true", help="Liệt kê danh sách PDF sách tô màu sẵn có")
    parser.add_argument("--upload", type=str, help="Tên file PDF tô màu cần upload (hoặc 'all')")
    parser.add_argument("--price", type=float, default=3.99, help="Giá bán (USD)")
    parser.add_argument("--publish", action="store_true", help="Publish công khai (Mặc định: Lưu nháp/Draft)")

    args = parser.parse_args()

    if args.login:
        cmd_login()
        return

    if args.list:
        files = list_coloring_books()
        print(f"📚 Tìm thấy {len(files)} cuốn sách tô màu PDF:")
        for f in files:
            print(f"  - {f.name} ({f.stat().st_size / (1024*1024):.2f} MB)")
        return

    if args.upload:
        files = list_coloring_books()
        if not files:
            print("❌ Không tìm thấy file PDF nào trong data/outputs/coloringbook/")
            return

        target_files = files if args.upload == "all" else [f for f in files if args.upload.lower() in f.name.lower()]

        if not target_files:
            print(f"❌ Không tìm thấy file khớp với từ khóa '{args.upload}'")
            return

        for f in target_files:
            print(f"\n🚀 Đang xử lý: {f.name}...")
            upload_product(f, price=args.price, publish=args.publish)


if __name__ == "__main__":
    main()
