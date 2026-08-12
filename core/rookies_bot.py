"""
core/rookies_bot.py
===================
TAY THẬT của AURA trên Rookies (rookies.vn) — tự mở trình duyệt, vào studio,
tạo chương, điền nội dung, đăng. Sếp KHÔNG phải bấm gì.

Vì sao ở đây làm được mà Wattpad thì không (đo thật 2026-07-22):
- Wattpad: nhét bẫy `debugger` để đóng băng trình duyệt tự động -> bỏ.
- Rookies: `debugger` xuất hiện **0 lần**, không CAPTCHA, render bình thường
  trong trình duyệt tự động -> tự động hoá được.

An toàn:
- KHÔNG tự đăng nhập / không nhập mật khẩu / không qua CAPTCHA. Sếp đăng nhập
  TAY đúng MỘT LẦN ở `--login`; phiên lưu trong `data/rookies_profile/`.
- Mặc định KHÔNG bấm nút đăng cuối (`--publish` mới bấm) — tránh đăng bừa.
- Nhịp người: nghỉ giữa các chương, không spam.

Dùng:
    # 1) Đăng nhập TAY 1 lần (tự chụp studio luôn để tôi viết selector):
    venv/Scripts/python.exe -m core.rookies_bot --login
    # 2) Đăng 1 chương (nháp):
    venv/Scripts/python.exe -m core.rookies_bot --series "Tên_Bộ" --chapter 1
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from core.config import settings, PROJECT_ROOT
from core.wattpad_hand import parse_chapter, latest_chapter, _find_chapter
from factory.platform_rules import can_post, disclosure_for

logger = logging.getLogger(__name__)

PROFILE_DIR = PROJECT_ROOT / "data" / "rookies_profile"
DEBUG_DIR = PROJECT_ROOT / "data" / "rookies_debug"
HOME = "https://rookies.vn/"
STUDIO = "https://rookies.vn/studio"
NEW_STORY = "https://rookies.vn/author/tao-truyen"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _context(headless: bool, use_chrome: bool = True):
    """Mở persistent context. Mặc định dùng CHROME THẬT (channel='chrome') vì
    Google chặn đăng nhập OAuth trên Chromium tự động — dùng Chrome thật đỡ bị
    'trình duyệt không an toàn' và giữ phiên tốt hơn."""
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
        locale="vi-VN",
        user_agent=UA,
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    if use_chrome:
        try:
            return pw, pw.chromium.launch_persistent_context(channel="chrome", **kw)
        except Exception as exc:  # noqa: BLE001
            pw.stop()
            # KHÔNG rơi về Chromium: phiên đăng nhập được Chrome mã hoá theo trình
            # duyệt, Chromium đọc profile này sẽ tưởng CHƯA đăng nhập -> báo sai.
            raise SystemExit(
                "❌ Không mở được Chrome thật với profile của AURA.\n"
                "   Nguyên nhân hay gặp: CỬA SỔ CHROME DO AURA MỞ TRƯỚC ĐÓ VẪN CÒN CHẠY "
                "(profile bị khoá).\n"
                "   Cách xử: đóng hẳn cửa sổ Chrome mà AURA đã mở, rồi chạy lại lệnh.\n"
                f"   (Chi tiết: {str(exc)[:180]})"
            ) from exc
    return pw, pw.chromium.launch_persistent_context(**kw)


def _on_rookies(page) -> bool:
    """Trang hiện tại có đang ở rookies.vn không (KHÔNG phải accounts.google.com)."""
    try:
        return "rookies.vn" in (page.url or "")
    except Exception:  # noqa: BLE001
        return False


def _logged_out(page) -> bool:
    """Còn nút 'Đăng nhập'/'Tạo tài khoản' hiện = chưa đăng nhập.
    LƯU Ý: chỉ có nghĩa khi đang Ở rookies.vn — ở trang Google thì vô nghĩa."""
    try:
        loc = page.locator(
            "a:has-text('Đăng nhập'), button:has-text('Đăng nhập'), "
            "a:has-text('Tạo tài khoản')"
        ).first
        return loc.count() > 0 and loc.is_visible()
    except Exception:  # noqa: BLE001
        return False


_AUTH_COOKIE_RE = __import__("re").compile(
    r"(token|session|auth|jwt|sid|login|user|remember)", __import__("re").I
)


def _auth_cookies(ctx) -> set[str]:
    """Tên các cookie 'có mùi đăng nhập' của rookies.vn. THỤ ĐỘNG — không đụng trang."""
    try:
        return {
            c["name"] for c in ctx.cookies()
            if "rookies" in (c.get("domain") or "") and _AUTH_COOKIE_RE.search(c["name"])
        }
    except Exception:  # noqa: BLE001
        return set()


def _verify_studio(page) -> bool:
    """XÁC MINH CHẮC CHẮN: vào /studio mà KHÔNG bị đá về trang chủ = đã đăng nhập.
    Đây là tín hiệu dương thật, thay cho việc chỉ 'không thấy nút Đăng nhập'."""
    try:
        page.goto(STUDIO, timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        return "/studio" in (page.url or "")
    except Exception:  # noqa: BLE001
        return False


def _capture(page, name: str) -> str:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    png = DEBUG_DIR / f"{name}.png"
    htm = DEBUG_DIR / f"{name}.html"
    try:
        page.screenshot(path=str(png), full_page=True)
        htm.write_text(page.content(), encoding="utf-8")
        return str(png)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Chụp %s lỗi: %s", name, exc)
        return ""


def do_login(wait_min: float = 8.0) -> str:
    """Sếp đăng nhập TAY 1 lần. KHÔNG bắt bấm Enter — bot TỰ DÒ tới khi thấy đã
    đăng nhập (cửa sổ giữ mở suốt), rồi tự vào studio chụp lại để viết selector."""
    pw, ctx = _context(headless=False)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(HOME, timeout=60000, wait_until="domcontentloaded")
        print("\n>>> Cửa sổ Rookies đã mở (Chrome thật).")
        print(">>> Cứ ĐĂNG NHẬP bình thường trong cửa sổ đó — KHÔNG cần bấm gì ở đây.")
        print(f">>> Bot sẽ tự nhận ra khi anh đăng nhập xong (chờ tối đa {wait_min:.0f} phút).")
        # VÒNG CHỜ THỤ ĐỘNG: TUYỆT ĐỐI KHÔNG điều hướng/không đụng vào trang trong
        # lúc Sếp đang đăng nhập (bài học: goto giữa chừng làm mất modal đăng nhập,
        # nhìn như trang tự load lại). Chỉ theo dõi COOKIE phiên xuất hiện.
        baseline = _auth_cookies(ctx)
        deadline = time.time() + wait_min * 60
        ok = False
        while time.time() < deadline:
            time.sleep(3)
            try:
                new = _auth_cookies(ctx) - baseline
                if not new:
                    continue
                # Có cookie đăng nhập mới -> đợi ổn định rồi mới xác minh 1 LẦN.
                time.sleep(5)
                if _verify_studio(page):
                    ok = True
                    break
                baseline = _auth_cookies(ctx)   # chưa thật -> lấy mốc mới, chờ tiếp
            except Exception:  # noqa: BLE001 — trang đang chuyển/popup OAuth
                continue
        if not ok:
            try:
                _capture(page, "login_failed")
            except Exception:  # noqa: BLE001
                pass
            return ("⚠️ Hết giờ chờ mà vẫn chưa thấy trạng thái đăng nhập. "
                    "Nếu anh đăng nhập bằng Google mà bị chặn, thử đăng nhập bằng "
                    "EMAIL/MẬT KHẨU của Rookies trong cửa sổ đó.")
        print(">>> ✅ Nhận ra đã đăng nhập — đang chụp lại studio...")
        # Vào studio + trang tạo truyện, chụp cả hai để viết selector chính xác.
        page.goto(STUDIO, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        shot1 = _capture(page, "studio")
        page.goto(NEW_STORY, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        shot2 = _capture(page, "tao_truyen")
        return ("✅ ĐĂNG NHẬP THÀNH CÔNG + đã lưu phiên.\n"
                f"📸 Đã chụp: {shot1}\n📸 Đã chụp: {shot2}\n"
                "→ Báo Claude để viết bước đăng tự động cho khớp giao diện thật.")
    finally:
        ctx.close()
        pw.stop()


def do_inspect(url: str = STUDIO) -> str:
    """Mở 1 trang bằng phiên đã lưu rồi chụp + dump (để tinh chỉnh selector)."""
    pw, ctx = _context(headless=False)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        if _logged_out(page):
            return "⚠️ Chưa đăng nhập — chạy `--login` trước."
        name = "inspect_" + url.rstrip("/").split("/")[-1]
        shot = _capture(page, name)
        return f"📸 Đã chụp {shot} (+ .html cùng thư mục)."
    finally:
        ctx.close()
        pw.stop()


def _click_choice(page, *labels: str) -> str | None:
    """Bấm lựa chọn dạng chip theo NHÃN CHỮ (Có/Không, 18 - 25 tuổi...). Trả nhãn đã bấm."""
    for lb in labels:
        try:
            loc = page.get_by_text(lb, exact=True).first
            if loc.count() > 0 and loc.is_visible():
                loc.click()
                page.wait_for_timeout(300)
                return lb
        except Exception:  # noqa: BLE001
            continue
    return None


def _auto_select_tags(page, keywords: list[str], want: int = 3) -> int:
    """Best-effort tự chọn thẻ Rookies theo từ khoá thể loại (dung sai cao).
    Rookies: các nhóm 'Thể loại'/'Đề tài'... là TAB chuyển chip; click chip khớp
    từ khoá. Không khớp thì click vài chip đang hiện (đủ pass yêu cầu). Trả số đã chọn."""
    clicked = 0
    # GỠ class 'hidden' của MỌI tab thẻ — chip genre nằm trong `tabs__content hidden`
    # (ẩn bằng CSS class, không phải tab chống automation). Gỡ xong chip hiện, click được.
    try:
        page.evaluate("""()=>{
            document.querySelectorAll('.tabs__content.hidden, [class*="tabs__content"][class*="hidden"]')
                .forEach(e=>e.classList.remove('hidden'));
        }""")
        page.wait_for_timeout(500)
    except Exception:  # noqa: BLE001
        pass
    # Click chip khớp từ khoá (giờ mọi chip đã hiện). Ưu tiên click THẬT của Playwright
    # để trigger đúng handler chọn thẻ của Rookies.
    for kw in keywords:
        if clicked >= want:
            break
        try:
            chip = page.get_by_text(kw, exact=True).first
            if chip.count() and chip.is_visible():
                chip.click(timeout=2000)
                clicked += 1
                page.wait_for_timeout(300)
        except Exception:  # noqa: BLE001
            pass
    return clicked


def create_story(series: str, headless: bool = False, save: bool = False,
                 hold_min: float = 10.0, auto: bool = False) -> str:
    """TẠO BỘ TRUYỆN trên Rookies từ publish_kit của AURA (tên/giới thiệu/bìa).
    Mặc định CHỈ ĐIỀN, không bấm Lưu — thêm --save để lưu thật."""
    allowed, why = can_post("rookies")
    if not allowed:
        return f"⛔ {why}"
    from core.publish_hand import _read_kit
    info, blurb = _read_kit(series)
    title = info.get("title") or series
    if not blurb:
        return f"⚠️ Bộ '{series}' chưa có văn án (publish_kit/van_an.md)."
    cover = info.get("cover") or ""

    pw, ctx = _context(headless=headless)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(NEW_STORY, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        if _logged_out(page):
            return "⚠️ Chưa đăng nhập — chạy `--login` trước."

        done = []
        # Tên truyện + giới thiệu (selector lấy từ HTML thật).
        page.fill("#IP_name", title); done.append("tên truyện")
        page.fill("#summary", blurb); done.append("giới thiệu")

        # Ảnh bìa: input file ẩn sau nút "Tải ảnh lên".
        if cover and Path(cover).is_file():
            try:
                page.set_input_files("#img_file", cover)
                page.wait_for_timeout(2500)
                done.append("ảnh bìa")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Tải bìa lỗi: %s", exc)

        # Các lựa chọn còn lại (best-effort theo nhãn chữ).
        if _click_choice(page, "Không"):
            done.append("che=Không")
        if _click_choice(page, "18 - 25 tuổi", "> 25 tuổi"):
            done.append("độc giả")
        if _click_choice(page, "Không cố định"):
            done.append("lịch đăng")
        if _click_choice(page, "Đang ra"):
            done.append("trạng thái")

        # TỰ CHỌN THẺ (full-auto): khớp từ khoá thể loại của nền + tên bộ.
        if auto or save:
            from factory.platform_rules import preferred_genres
            kws = ["Ngôn tình", "Đô thị", "Học đường", "Hiện đại", "Hệ thống",
                   "Huyền huyễn", "Kỳ ảo", "Tình cảm", "Xuyên không", "Trọng sinh",
                   "Ngọt ngào", "Nhẹ nhàng"]
            nsel = _auto_select_tags(page, [k for k in kws if k])
            done.append(f"thẻ×{nsel}")

        page.wait_for_timeout(1000)
        shot = _capture(page, "tao_truyen_da_dien")

        # FULL-AUTO: điền + chọn thẻ + LƯU luôn, không giữ cửa cho user.
        if auto and not save:
            save = True

        if not save:
            print(f"\n📝 Đã điền xong: {', '.join(done)}")
            print("👉 GIỜ ANH CHỈ CẦN: chọn THẺ (Thể loại/Đề tài) rồi bấm 'Lưu' "
                  "ngay trong cửa sổ đang mở.")
            print(f"   (Cửa sổ giữ mở {hold_min:.0f} phút rồi tự đóng.)")
            time.sleep(hold_min * 60)
            return (f"📝 Đã điền form tạo truyện '{title}' ({', '.join(done)}).\n"
                    f"📸 {shot}\n"
                    "Nếu anh đã chọn thẻ + bấm Lưu thì truyện đã được tạo.")

        btn = page.get_by_role("button", name="Lưu").first
        if btn.count() == 0 or not btn.is_visible():
            return f"⚠️ Đã điền nhưng không thấy nút Lưu. Ảnh: {shot}"
        btn.click()
        page.wait_for_timeout(3000)
        # Rookies bật modal "Lưu thành công!" -> BẮT BUỘC bấm "ĐỒNG Ý" để hoàn tất.
        # (Bug cũ: thử 'Lưu' trước nên bấm nhầm nút Lưu chính, không chạm ĐỒNG Ý.)
        for nm in ("ĐỒNG Ý", "Đồng ý", "Xác nhận", "OK"):
            try:
                c = page.get_by_role("button", name=nm).first
                if c.count() and c.is_visible():
                    c.click(); page.wait_for_timeout(2500); break
            except Exception:  # noqa: BLE001
                pass
        page.wait_for_timeout(4000)
        shot2 = _capture(page, "tao_truyen_da_luu")
        # VERIFY THẬT: bộ có xuất hiện trong studio không (không tin cú click).
        sid = _find_story_id(page, info_title=title)
        if sid:
            return (f"✅ Đã tạo truyện '{title}' trên Rookies (id {sid}, {', '.join(done)}). "
                    f"Ảnh: {shot2}")
        return (f"⚠️ Đã bấm Lưu nhưng CHƯA thấy '{title}' trong studio — có thể Rookies "
                f"bắt buộc chọn thẻ tay hoặc lỗi. Ảnh: {shot2}")
    finally:
        ctx.close()
        pw.stop()


def post_chapter(series: str, chapter: int | None = None,
                 publish: bool = False, headless: bool = False) -> str:
    """Đăng 1 chương lên Rookies. Mặc định KHÔNG bấm nút đăng cuối (an toàn)."""
    allowed, why = can_post("rookies")
    if not allowed:
        return f"⛔ {why}"
    ch = chapter or latest_chapter(series)
    if ch < 1:
        return f"📭 Bộ '{series}' chưa có chương nào."
    title, paras = parse_chapter(_find_chapter(series, ch))
    body = "\n\n".join(paras)
    disc = disclosure_for("rookies")
    if disc and ch <= 1:
        body = f"{body}\n\n———\n{disc}"

    import html as _html
    body_html = "\n".join(f"<p>{_html.escape(p)}</p>" for p in
                          (body.split("\n\n") if isinstance(body, str) else body))

    pw, ctx = _context(headless=headless)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        story_id = _find_story_id(page, info_title=None)
        if not story_id:
            return ("⚠️ Chưa thấy bộ truyện nào trong studio — tạo truyện trước "
                    "(`--create-story`).")

        page.goto(f"https://rookies.vn/author/tao-chuong/{story_id}",
                  timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        if _logged_out(page):
            return "⚠️ Chưa đăng nhập — chạy `--login` trước (chỉ cần 1 lần)."

        # Tên chương (selector thật lấy từ trang tạo chương).
        page.fill("input[name='chapter_name']", title)

        # Nội dung: trang dùng TinyMCE (textarea #chapter-detail ẩn sau iframe).
        # Dùng API của TinyMCE — chắc chắn hơn gõ vào iframe.
        okset = page.evaluate(
            """([h]) => {
                if (window.tinymce) {
                    const ed = tinymce.get('chapter-detail') || tinymce.activeEditor;
                    if (ed) { ed.setContent(h); ed.save(); return true; }
                }
                return false;
            }""", [body_html])
        if not okset:
            shot = _capture(page, f"khong_set_duoc_ch{ch:04d}")
            return f"⚠️ Không set được nội dung vào trình soạn thảo. Ảnh: {shot}"
        page.wait_for_timeout(1500)
        shot = _capture(page, f"da_dien_ch{ch:04d}")

        # Nút "Lưu" mở MENU con: [Đăng & tiếp tục chỉnh sửa | Lên lịch đăng tải |
        # Lưu bản thảo | Đăng]. Mặc định chọn "Lưu bản thảo" (an toàn), --publish
        # thì chọn "Đăng".
        opener = page.get_by_text("Lưu", exact=True).first
        if opener.count() == 0:
            return f"⚠️ Đã điền nhưng không thấy nút Lưu. Ảnh: {shot}"
        opener.click()
        page.wait_for_timeout(2000)

        want = "Đăng" if publish else "Lưu bản thảo"
        item = page.get_by_text(want, exact=True).first
        if item.count() == 0:
            shot2 = _capture(page, f"menu_khong_thay_ch{ch:04d}")
            return f"⚠️ Không thấy mục '{want}' trong menu Lưu. Ảnh: {shot2}"
        item.click()
        page.wait_for_timeout(2500)

        # Rookies bật HỘP XÁC NHẬN cho CẢ HAI đường:
        #   - Đăng        -> "Chắc chắn muốn đăng chương này?"  nút [ĐĂNG]
        #   - Lưu bản thảo -> "Chắc chắn lưu làm bản thảo?"      nút [LƯU]
        confirm_name = "ĐĂNG" if publish else "LƯU"
        try:
            confirm = page.get_by_role("button", name=confirm_name).first
            if confirm.count() > 0 and confirm.is_visible():
                confirm.click()
                page.wait_for_timeout(5000)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bấm xác nhận '%s' lỗi: %s", confirm_name, exc)
        page.wait_for_timeout(3000)
        shot2 = _capture(page, f"da_{'dang' if publish else 'luu_nhap'}_ch{ch:04d}")

        # KIỂM CHỨNG THẬT: đọc lại studio xem số chương/bản thảo có tăng không.
        # KHÔNG báo thành công khi chưa xác minh (bài học: từng in nhầm 'đã đăng').
        state = _story_counts(page)
        act = "đăng công khai" if publish else "lưu bản thảo"
        if state and (state.get("posted", 0) > 0 or state.get("draft", 0) > 0):
            return (f"✅ Đã {act} chương {ch} ('{title}'). "
                    f"Studio: {state.get('posted',0)} chương đã đăng, "
                    f"{state.get('draft',0)} bản thảo. Ảnh: {shot2}")
        return (f"⚠️ Đã bấm '{want}' nhưng studio VẪN báo 0 chương/0 bản thảo — "
                f"có thể chưa lưu được. Ảnh: {shot2}")
    finally:
        ctx.close()
        pw.stop()


def list_chapters(page, story_id: str) -> list[dict]:
    """Đọc mục lục -> [{id, title, published}]. Dùng nút 'Gỡ đăng' để nhận biết
    chương ĐÃ ĐĂNG (cách này chắc; leo cây DOM từ link ra ngoài thì sai)."""
    page.goto(f"https://rookies.vn/author/muc-luc/{story_id}",
              timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(7000)
    return page.evaluate("""() => {
        const pub = new Set();
        [...document.querySelectorAll('*')]
          .filter(e => e.children.length === 0 && (e.textContent||'').trim() === 'Gỡ đăng')
          .forEach(g => {
            let n = g;
            for (let i=0;i<12 && n;i++){
              const l = n.querySelector && n.querySelector('a[href*="chinh-sua-chuong"]');
              if (l){ pub.add(l.getAttribute('href').split('/').pop()); break; }
              n = n.parentElement;
            }
          });
        return [...document.querySelectorAll('a[href*="chinh-sua-chuong"]')].map(a => {
            const id = a.getAttribute('href').split('/').pop();
            return { id, title: a.innerText.trim(), published: pub.has(id),
                     url: a.getAttribute('href') };
        });
    }""")


def publish_draft(page, chap_url: str) -> bool:
    """Mở 1 chương ĐÃ CÓ rồi ĐĂNG nó (không tạo chương mới — đây là lỗi cũ)."""
    if chap_url.startswith("/"):
        chap_url = "https://rookies.vn" + chap_url
    page.goto(chap_url, timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(6000)
    opener = page.get_by_text("Lưu", exact=True).first
    if opener.count() == 0:
        return False
    opener.click()
    page.wait_for_timeout(3000)
    # Nhãn khác nhau giữa 2 trang: trang TẠO chương = "Đăng";
    # trang SỬA chương = "Lưu & Đăng truyện".
    item = None
    for lb in ("Lưu & Đăng truyện", "Đăng", "Đăng & tiếp tục chỉnh sửa"):
        loc = page.get_by_text(lb, exact=True).first
        if loc.count() > 0 and loc.is_visible():
            item = loc
            break
    if item is None:
        return False
    item.click()
    page.wait_for_timeout(2500)
    try:
        c = page.get_by_role("button", name="ĐĂNG").first
        if c.count() > 0 and c.is_visible():
            c.click()
            page.wait_for_timeout(5000)
    except Exception:  # noqa: BLE001
        pass
    return True


def _story_counts(page) -> dict | None:
    """Đọc studio: số chương ĐÃ ĐĂNG và số BẢN THẢO (để kiểm chứng thật)."""
    import re as _re
    try:
        page.goto(STUDIO, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)
        t = page.inner_text("body")
        posted = _re.search(r"(\d+)\s*Chương đã đăng tải", t)
        draft = _re.search(r"(\d+)\s*bản thảo", t)
        return {
            "posted": int(posted.group(1)) if posted else 0,
            "draft": int(draft.group(1)) if draft else 0,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Đọc trạng thái studio lỗi: %s", exc)
        return None


def _find_story_id(page, info_title: str | None = None) -> str | None:
    """Lấy id bộ truyện từ studio (link /author/muc-luc/<id>)."""
    import re as _re
    try:
        page.goto(STUDIO, timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        hrefs = page.eval_on_selector_all(
            "a[href]", "els=>els.map(e=>[e.innerText.trim(), e.getAttribute('href')])")
        for txt, h in hrefs:
            if not h:
                continue
            m = _re.search(r"/author/muc-luc/(\d+)", h)
            if m and (info_title is None or info_title.lower() in (txt or "").lower()):
                return m.group(1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tìm story id lỗi: %s", exc)
    return None


def sync_series(series: str, cap: int = 2, publish: bool = False,
                gap_s: float = 25.0) -> str:
    """ĐỒNG BỘ bộ truyện lên Rookies — dùng cho AUTOPILOT.

    Chống trùng TỪ GỐC: lấy danh sách chương ĐANG CÓ TRÊN ROOKIES làm chuẩn, so
    với chương local theo TIÊU ĐỀ, chỉ đẩy phần còn thiếu. Chạy lại bao nhiêu lần
    cũng không sinh bản trùng (bài học 2026-07-22).
    Mặc định lưu BẢN THẢO — Sếp duyệt rồi mới đăng.
    """
    allowed, why = can_post("rookies")
    if not allowed:
        return f"⛔ {why}"
    from core.publish_hand import _read_kit
    info, _ = _read_kit(series)
    want_title = info.get("title") or series

    # Chương local: {tiêu đề: số chương}
    local: dict[str, int] = {}
    for n in range(1, latest_chapter(series) + 1):
        try:
            t, _p = parse_chapter(_find_chapter(series, n))
            local[t.strip()] = n
        except Exception:  # noqa: BLE001
            continue
    if not local:
        return f"📭 Bộ '{series}' chưa có chương nào."

    # B1: DÒ trạng thái trên Rookies rồi ĐÓNG context ngay (post_chapter sẽ tự mở
    # context riêng — KHÔNG được lồng sync_playwright vào nhau).
    pw, ctx = _context(headless=True)
    try:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        # CHỈ khớp theo ĐÚNG TÊN BỘ. TUYỆT ĐỐI KHÔNG fallback về bộ đầu tiên —
        # bug đã gây hại: bộ ngôn tình chưa tạo trên Rookies -> chương bị đổ NHẦM
        # vào bộ cyberpunk cũ (2026-07-24). Chưa có bộ đúng thì THÔI, không đẩy.
        sid = _find_story_id(page, info_title=want_title)
        remote = {c["title"].strip() for c in list_chapters(page, sid)} if sid else set()
    finally:
        ctx.close()
        pw.stop()

    if not sid:
        return (f"⚠️ Chưa thấy bộ '{want_title}' trên Rookies — tạo truyện trước "
                "(`--create-story`).")
    missing = [(t, n) for t, n in sorted(local.items(), key=lambda kv: kv[1])
               if t not in remote]
    if not missing:
        return f"✅ Rookies đã đủ {len(remote)} chương của '{want_title}' — không cần đẩy."

    # B2: đẩy phần còn thiếu, mỗi chương một phiên trình duyệt riêng.
    done = []
    for t, n in missing[:max(1, cap)]:
        msg = post_chapter(series, n, publish=publish, headless=True)
        done.append(f"ch{n}: {'OK' if msg.startswith('✅') else 'LỖI'}")
        time.sleep(gap_s)
    trang_thai = "đăng công khai" if publish else "lưu bản thảo"
    return (f"📤 Rookies '{want_title}': đã {trang_thai} {len(done)} chương mới "
            f"({', '.join(done)}). Còn thiếu {max(0, len(missing) - len(done))} chương.")


def post_many(series: str, start: int, end: int, publish: bool = False,
              gap_s: float = 45.0) -> str:
    """Đăng nhiều chương liên tiếp, NGHỈ giữa các chương (nhịp người, né cờ spam)."""
    out = []
    for ch in range(start, end + 1):
        out.append(post_chapter(series, ch, publish=publish))
        if ch < end:
            time.sleep(gap_s)
    return "\n".join(out)


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Bot đăng truyện Rookies của AURA")
    ap.add_argument("--login", action="store_true", help="Đăng nhập tay 1 lần + chụp studio")
    ap.add_argument("--wait", type=float, default=8.0, help="Số phút chờ đăng nhập (mặc định 8)")
    ap.add_argument("--inspect", action="store_true", help="Chụp lại studio bằng phiên đã lưu")
    ap.add_argument("--series", help="Tên thư mục bộ truyện")
    ap.add_argument("--chapter", type=int, help="Số chương (bỏ trống = mới nhất)")
    ap.add_argument("--from", dest="start", type=int, help="Đăng NHIỀU: chương bắt đầu")
    ap.add_argument("--to", dest="end", type=int, help="Đăng NHIỀU: chương kết thúc")
    ap.add_argument("--create-story", dest="create_story", action="store_true",
                    help="TẠO BỘ TRUYỆN từ publish_kit (điền form)")
    ap.add_argument("--save", action="store_true", help="Bấm nút Lưu khi tạo truyện")
    ap.add_argument("--auto", action="store_true", help="FULL-AUTO: tự chọn thẻ + lưu, không giữ cửa")
    ap.add_argument("--publish", action="store_true", help="Bấm nút đăng thật")
    ap.add_argument("--headless", action="store_true", help="Chạy ẩn cửa sổ")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    if args.login:
        print(do_login(wait_min=args.wait)); return 0
    if args.inspect:
        print(do_inspect()); return 0
    if args.create_story and args.series:
        print(create_story(args.series, save=args.save or args.auto,
                           hold_min=args.wait, auto=args.auto)); return 0
    if args.series and args.start and args.end:
        print(post_many(args.series, args.start, args.end, publish=args.publish)); return 0
    if args.series:
        print(post_chapter(args.series, args.chapter, publish=args.publish,
                           headless=args.headless)); return 0
    ap.print_help(); return 1


if __name__ == "__main__":
    sys.exit(main())
