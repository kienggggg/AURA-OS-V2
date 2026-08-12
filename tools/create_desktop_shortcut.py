# -*- coding: utf-8 -*-
"""Đặt lối tắt "AURA" ra màn hình nền.

Bấm vào là mở thẳng AURA v3 trong một cửa sổ riêng (xem `aura_app.pyw`).

10/08/2026 sửa hai chỗ: `ICON_PATH` cũ trỏ vào `assets/mascot/idle.png` —
mascot đã tắt hẳn nên biểu tượng không được lấy từ đó nữa; và biến đó vốn KHÔNG
BAO GIỜ được dùng trong đoạn VBScript bên dưới, tức lối tắt xưa nay vẫn mang
biểu tượng mặc định của Windows. Giờ gán thật, và lấy từ trình duyệt Chromium
đang có (cửa sổ mở ra là của nó, nên biểu tượng khớp với thứ Sếp nhìn thấy).
"""
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TARGET_BAT = PROJECT_ROOT / "start_aura_app.bat"


def _icon() -> str:
    """Biểu tượng cho lối tắt; rỗng thì Windows tự chọn mặc định."""
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        import importlib.machinery
        import importlib.util

        nap = importlib.machinery.SourceFileLoader(
            "aura_app", str(PROJECT_ROOT / "aura_app.pyw")
        )
        spec = importlib.util.spec_from_loader("aura_app", nap)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        duong = mod.tim_trinh_duyet()
        return f"{duong},0" if duong else ""
    except Exception:                                   # noqa: BLE001
        return ""

def create_shortcut():
    desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    if not desktop.is_dir():
        print("Không tìm thấy thư mục Desktop.")
        return False

    shortcut_path = desktop / "AURA.lnk"
    bieu_tuong = _icon()
    dong_icon = f'Shortcut.IconLocation = "{bieu_tuong}"' if bieu_tuong else ""
    vbs_script = f"""
Set WshShell = WScript.CreateObject("WScript.Shell")
Set Shortcut = WshShell.CreateShortcut("{shortcut_path}")
Shortcut.TargetPath = "{TARGET_BAT}"
Shortcut.WorkingDirectory = "{PROJECT_ROOT}"
Shortcut.Description = "AURA v3 - chat"
Shortcut.WindowStyle = 7
{dong_icon}
Shortcut.Save
"""
    tmp_vbs = PROJECT_ROOT / ".tmp_create_shortcut.vbs"
    # UTF-16 LE có BOM, KHÔNG phải UTF-8: `cscript` đọc tệp .vbs theo bảng mã
    # ANSI của hệ thống nếu không thấy BOM.
    #
    # Nhưng ĐỔI SANG UTF-16 VẪN CHƯA ĐỦ, và tôi chỉ biết sau khi đo: phần
    # `Description` đi qua `WScript.Shell` bị ép về bảng mã hệ thống dù gọi
    # bằng cách nào — thử cả `cscript` lẫn COM trực tiếp từ PowerShell, "ệ"
    # đều thành "?" (mã 63) trong khi "—" và "ò" sống sót, đúng dấu hiệu của
    # Windows-1252. Đó là giới hạn của chính API, không phải cách gọi.
    #
    # Một dòng chú giải không đáng viết `ctypes` gọi `IShellLinkW`, nên phần
    # mô tả dùng chữ không dấu. TÊN lối tắt và ĐƯỜNG CHẠY thì không qua đường
    # này nên vẫn nguyên vẹn.
    tmp_vbs.write_text(vbs_script, encoding="utf-16")
    try:
        subprocess.run(["cscript", "//Nologo", str(tmp_vbs)], check=True)
        print(f"Created shortcut successfully at: {shortcut_path}")
        return True
    finally:
        if tmp_vbs.is_file():
            tmp_vbs.unlink()

if __name__ == "__main__":
    create_shortcut()
