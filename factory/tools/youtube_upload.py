"""
factory/tools/youtube_upload.py
================================
youtube.upload — ĐĂNG video lên YouTube qua API chính thức (đa kênh).

Chuẩn bị 1 lần: xem hướng dẫn trong factory/tools/youtube_auth.py (tạo
client_secret.json + chạy `python -m factory.tools.youtube_auth --channel <tên>`
cho TỪNG kênh muốn quản — AURA quản nhiều kênh song song, mỗi kênh 1 token).

Metadata tự động: bỏ trống tiêu đề thì AURA tự viết title/description/tags
tiếng Việt bằng LLM từ phụ đề .srt nằm cạnh video (sản phẩm của video.factory
luôn có sẵn .srt).

⚠️ Quota free: ~6 video/ngày/project (videos.insert = 1600 unit / 10000 unit).
⚠️ Mặc định đăng UNLISTED — Sếp xem lại ưng rồi tự chuyển public trên Studio;
   tránh strike bản quyền do đăng nhầm nội dung không có quyền.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from core.config import PROJECT_ROOT, settings
from factory import queue as job_queue
from factory.models import FormField, JobCancelled, JobRecord, ToolSpec

YT_DIR = PROJECT_ROOT / "data" / "youtube"
_PUBLISH_LEDGER = settings.ledger_dir / "publishes.jsonl"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",  # đọc + sửa/xoá video đã đăng
]


def _channels() -> tuple[str, ...]:
    """Các kênh đã cấp quyền (thư mục có token.json)."""
    if not YT_DIR.exists():
        return ()
    return tuple(sorted(
        d.name for d in YT_DIR.iterdir() if (d / "token.json").is_file()
    ))


def _channel_choices() -> tuple[str, ...]:
    """Key các kênh YouTube trong SỔ KÊNH (ưu tiên) — để form gợi ý theo ngách."""
    try:
        from factory import channels as ch_registry
        keys = tuple(c["key"] for c in ch_registry.all_channels(only_enabled=True)
                     if c.get("platform") == "youtube" and c.get("key"))
        return keys or _channels()
    except Exception:  # noqa: BLE001
        return _channels()


def _service(channel: str):
    """YouTube API client cho 1 kênh — tự refresh token hết hạn."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_path = YT_DIR / channel / "token.json"
    if not token_path.exists():
        raise RuntimeError(
            f"Kênh '{channel}' chưa cấp quyền. Chạy 1 lần trong terminal:\n"
            f"  venv\\Scripts\\python.exe -m factory.tools.youtube_auth --channel {channel}\n"
            f"(cần data/youtube/client_secret.json — hướng dẫn trong file youtube_auth.py)"
        )
    # KHÔNG truyền SCOPES khi nạp: dùng scope CỦA CHÍNH token — token cũ (upload+
    # readonly) refresh với scope mới (force-ssl) bị Google chặn 'invalid_scope'
    # làm MỌI upload gãy. Token cũ vẫn đăng được; thumbnail/sửa video cần re-auth
    # 1 lần (youtube_auth) để có force-ssl.
    creds = Credentials.from_authorized_user_file(str(token_path))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def _auto_metadata(video: Path, style: str = "", niche: str = "") -> dict:
    """LLM viết title/description/tags từ .srt cạnh video, THEO PHONG CÁCH KÊNH."""
    srt = video.with_suffix(".srt")
    if not srt.exists():
        # story_video xuất 'narration.srt' (tên khác file video) — nhặt .srt cùng thư mục
        # để vẫn tự viết được metadata thay vì rơi về tên file xấu.
        cands = sorted(video.parent.glob("*.srt"))
        srt = next((p for p in cands if p.name == "narration.srt"),
                   cands[0] if cands else srt)
    if not srt.exists():
        return {}
    text = []
    for line in srt.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line and not line.isdigit() and "-->" not in line:
            text.append(line)
    sample = "\n".join(text)[:4000]
    if len(sample) < 80:
        return {}
    brand = ""
    if niche or style:
        brand = f"\nKÊNH: ngách '{niche}'. Giọng kênh: {style} Viết metadata ĐÚNG chất kênh này."
    try:
        from core.llm import CloudEngine
        res = CloudEngine().complete(
            [{"role": "user", "content": f"Tên file: {video.stem}\nPhụ đề:\n{sample}"}],
            system_prompt=(
                "Viết metadata YouTube tiếng Việt cho video này. Trả JSON THUẦN: "
                "{\"title\": \"<=90 ký tự, hấp dẫn, có số tập nếu thấy\", "
                "\"description\": \"3-5 câu tóm tắt + mời xem, không spoil kết\", "
                "\"tags\": [\"5-10 tag ngắn\"]}. Không markdown, không giải thích." + brand),
            temperature=0.6, max_tokens=800, tier="fast",
        )
        m = re.search(r"\{.*\}", str(res.get("text", "")), re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:  # noqa: BLE001 — không có meta tự động thì dùng tên file
        pass
    return {}


def _series_title(video: Path) -> str:
    """Tên BỘ/PHIM từ bible.json của truyện — video nằm ở story_video/<bộ>/ch_NNNN/.
    Trả '' nếu không phải video truyện (để tiêu đề giữ nguyên)."""
    try:
        folder = video.parent.parent.name          # .../story_video/<bộ>/ch_NNNN/x.mp4
        bible = settings.outputs_dir / "story" / folder / "bible.json"
        if bible.is_file():
            return str(json.loads(bible.read_text(encoding="utf-8")).get("title") or "").strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def run(job: JobRecord, progress) -> None:
    params = job.params
    video = Path(str(params.get("video") or "").strip().strip('"'))
    if not video.is_file():
        raise ValueError(f"Không thấy file video: {video}")
    # Kênh: 'channel' có thể là KEY trong sổ kênh (khớp ngách+phong cách) HOẶC tên
    # thư mục token thô. Ưu tiên sổ kênh -> lấy yt_channel + style + niche.
    from factory import channels as ch_registry
    channel = str(params.get("channel") or "").strip()
    style = niche = ""
    reg = ch_registry.get(channel) if channel else None
    if reg:
        yt_channel = str(reg.get("yt_channel") or reg.get("key"))
        style, niche = str(reg.get("style") or ""), str(reg.get("niche") or "")
    else:
        yt_channel = channel

    chans = _channels()
    if not yt_channel:
        if len(chans) == 1:
            yt_channel = chans[0]
        else:
            raise ValueError(
                f"Chưa chọn kênh. Kênh đã cấp quyền: {', '.join(chans) or '(chưa có — chạy youtube_auth trước)'}"
            )

    art_dir = settings.outputs_dir / "youtube" / job.id
    art_dir.mkdir(parents=True, exist_ok=True)
    job.artifacts_dir = str(art_dir)

    # 1) Metadata: user điền > LLM tự viết (theo phong cách kênh) > tên file.
    title = str(params.get("title") or "").strip()
    description = str(params.get("description") or "").strip()
    tags = [t.strip() for t in str(params.get("tags") or "").split(",") if t.strip()]
    if not title:
        progress(5, "AURA tự viết tiêu đề/mô tả theo phong cách kênh")
        meta = _auto_metadata(video, style, niche)
        title = str(meta.get("title") or video.stem)[:95]
        description = description or str(meta.get("description") or "")
        tags = tags or [str(t) for t in (meta.get("tags") or [])][:12]

    # Tên BỘ/PHIM lên đầu tiêu đề để người xem biết đang xem bộ nào (YouTube cắt ~100 ký tự).
    series_title = _series_title(video)
    if series_title and series_title.lower() not in title.lower():
        title = f"{series_title} - {title}"
    title = title[:100]

    # Mẫu mô tả của kênh (channels.json desc_template): chèn TÓM TẮT (AURA viết /
    # user điền) vào giữa khung cố định — lời kêu gọi + hashtag + STK + chống reup.
    if reg and reg.get("desc_template"):
        synopsis = (description or title).strip()
        description = str(reg["desc_template"]).replace("{synopsis}", synopsis).strip()

    privacy = str(params.get("privacy") or getattr(settings, "youtube_default_privacy", "public")).strip()
    progress(10, f"Nối kênh '{yt_channel}'")
    yt = _service(yt_channel)

    # 2) Upload resumable theo chunk 8MB — video dài không sợ rớt mạng giữa chừng.
    from googleapiclient.http import MediaFileUpload
    body = {
        "snippet": {"title": title, "description": description, "tags": tags,
                    "categoryId": "1"},          # 1 = Film & Animation
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        if job_queue.is_cancelled(job.id):
            raise JobCancelled()
        status, response = req.next_chunk()
        if status:
            progress(10 + int(status.progress() * 80),
                     f"Đang tải lên {status.progress() * 100:.0f}%")

    vid = response.get("id", "")
    url = f"https://youtu.be/{vid}"

    # 3) Thumbnail: user đưa ảnh HOẶC tự lấy ảnh cảnh đầu (img/scene_01.jpg của
    # story.video) làm bìa. Cần token scope force-ssl + kênh xác minh SĐT — thiếu
    # thì ghi chú và bỏ qua, KHÔNG hỏng job đăng.
    thumb_note = "không có ảnh bìa"
    thumb = str(params.get("thumbnail") or "").strip()
    if not thumb:
        # Ưu tiên thumbnail.png (bìa có CHỮ TÍT do story.video dựng) -> hút click hơn
        # khung hình thô; không có thì lấy ảnh cảnh đầu.
        made = video.parent / "thumbnail.png"
        if made.is_file():
            thumb = str(made)
        else:
            scenes = sorted((video.parent / "img").glob("scene_*.jpg"))
            thumb = str(scenes[0]) if scenes else ""
    if thumb and Path(thumb).is_file():
        try:
            progress(92, "Đặt ảnh bìa (thumbnail)")
            yt.thumbnails().set(
                videoId=vid, media_body=MediaFileUpload(thumb)
            ).execute()
            thumb_note = f"OK: {Path(thumb).name}"
        except Exception as exc:  # noqa: BLE001 — thiếu quyền/chưa verify: bỏ qua
            thumb_note = f"bỏ qua ({str(exc)[:120]})"

    # 4) Ghi sổ đăng bài (audit + briefing đọc được).
    _PUBLISH_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with _PUBLISH_LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": int(time.time()), "platform": "youtube",
            "channel": channel or yt_channel, "yt_channel": yt_channel,
            "video_id": vid, "url": url, "title": title, "privacy": privacy,
            "file": str(video),
        }, ensure_ascii=False) + "\n")
    (art_dir / "result.json").write_text(json.dumps({
        "url": url, "title": title, "privacy": privacy,
        "channel": channel or yt_channel, "thumbnail": thumb_note,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(100, f"ĐÃ ĐĂNG ({privacy}) -> {url}")


SPEC = ToolSpec(
    name="youtube.upload",
    label_vi="Đăng video lên YouTube",
    description="Đăng video lên kênh YouTube qua API chính thức. Bỏ trống tiêu đề "
                 "= AURA tự viết title/mô tả/tags từ phụ đề. Mặc định UNLISTED — "
                 "xem lại ưng rồi hẵng public (an toàn bản quyền). Quota free "
                 "~6 video/ngày. Thêm kênh mới: python -m factory.tools.youtube_auth "
                 "--channel <tên>.",
    product_line="publish",
    form_fields=(
        FormField(key="video", label="Đường dẫn file video",
                  placeholder=r"D:\AURA_OS_v2\data\outputs\video\Lý_Cẩu_Tu_Tiên\...mp4"),
        FormField(key="channel", label="Kênh (theo sổ kênh — ngách + phong cách riêng)",
                  type="select" if _channel_choices() else "text",
                  choices=_channel_choices(),
                  default=(_channel_choices()[0] if _channel_choices() else ""),
                  required=False,
                  help_text="Kênh lấy từ sổ kênh (tab Kênh). Chưa cấp quyền token thì "
                            "chạy: python -m factory.tools.youtube_auth --channel <tên>."),
        FormField(key="thumbnail", label="Ảnh bìa (bỏ trống = tự lấy ảnh cảnh đầu)",
                  required=False),
        FormField(key="title", label="Tiêu đề (bỏ trống = AURA tự viết)", required=False),
        FormField(key="description", label="Mô tả (bỏ trống = AURA tự viết)",
                  type="textarea", required=False),
        FormField(key="tags", label="Tags (phẩy, bỏ trống = tự viết)", required=False),
        FormField(key="privacy", label="Chế độ", type="select", default="unlisted",
                  choices=("unlisted", "private", "public"), required=False),
    ),
    handler=run,
)

__all__ = ["SPEC", "run"]
