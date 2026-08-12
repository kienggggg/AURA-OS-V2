"""
factory/tools/youtube_auth.py
==============================
Xin quyền YouTube MỘT LẦN cho một kênh (chạy tay từ terminal, mở trình duyệt):

    venv\\Scripts\\python.exe -m factory.tools.youtube_auth --channel kenh-chinh

Cần sẵn `data/youtube/client_secret.json` (user tự tạo 1 lần trên Google Cloud:
Console -> New Project -> bật "YouTube Data API v3" -> OAuth consent screen
(External, thêm chính email mình làm test user) -> Credentials -> Create OAuth
client ID -> Desktop app -> Download JSON).

Mỗi KÊNH một thư mục token riêng (data/youtube/<tên kênh>/token.json) — lúc màn
hình consent hiện ra, CHỌN ĐÚNG kênh/brand account muốn cấp quyền. Nhờ vậy AURA
quản được NHIỀU kênh cùng lúc: mỗi kênh chạy script này 1 lần với --channel khác.

⚠️ client_secret.json + token.json là BÍ MẬT (đã gitignore data/youtube/).
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

YT_DIR = _PROJECT_ROOT / "data" / "youtube"
CLIENT_SECRET = YT_DIR / "client_secret.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    # force-ssl = đọc + QUẢN LÝ (sửa tiêu đề/mô tả, đổi chế độ, xoá, đặt thumbnail)
    # — cần cho việc cập nhật video đã đăng; bao trùm cả readonly.
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def authorize(channel: str) -> Path:
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRET.exists():
        raise SystemExit(
            f"Chưa có {CLIENT_SECRET}.\n"
            "Tạo 1 lần trên Google Cloud Console: New Project -> bật 'YouTube Data "
            "API v3' -> OAuth consent screen (External, thêm email mình làm test "
            "user) -> Credentials -> OAuth client ID -> Desktop app -> tải JSON về "
            "đúng đường dẫn trên."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")

    token_path = YT_DIR / channel / "token.json"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")

    # Xác nhận đã cấp cho kênh nào (đọc tên kênh thật từ API).
    try:
        from googleapiclient.discovery import build
        yt = build("youtube", "v3", credentials=creds)
        ch = yt.channels().list(part="snippet", mine=True).execute()
        name = ch["items"][0]["snippet"]["title"] if ch.get("items") else "(không rõ)"
        print(f"✓ Đã cấp quyền kênh YouTube: {name}")
    except Exception:  # noqa: BLE001 — không đọc được tên vẫn coi như xong
        print("✓ Đã lưu token (không đọc được tên kênh — vẫn dùng được).")
    print(f"Token: {token_path}")
    return token_path


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Xin quyền YouTube 1 lần cho 1 kênh.")
    ap.add_argument("--channel", required=True,
                    help="Tên gọi nội bộ của kênh (đặt tuỳ ý, vd 'kenh-truyen').")
    args = ap.parse_args()
    authorize(args.channel.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
