"""
core/daemon.py
=============
AuraDaemon — trái tim chạy ngầm của AURA, quản vòng đời bằng asyncio.

Theo blueprint:
  - Một event loop asyncio vĩnh viễn điều phối nhiều việc song song.
  - Sensor nền siêu nhẹ quét thư mục Downloads; thấy file MỚI -> đẩy sự kiện để
    AURA CHỦ ĐỘNG nhắn qua giao diện ("Sếp vừa tải X về, cần em xử lý không?").
  - Daemon và WebSocket server chia sẻ một asyncio.Queue: sensor bỏ tin vào,
    server lấy ra broadcast xuống UI. Nhờ vậy AURA "tự mở lời", không chỉ đáp.

Daemon KHÔNG tự phân tích/di chuyển file — đúng luật sắt: nó quan sát và ĐỀ XUẤT,
sếp quyết. Mọi hành động chạm hệ thống đều qua cổng sếp.

CẤP 1 — AURA NGỦ ĐÔNG (AURA Sleep): cờ `aura_frozen` bật lên thì MỌI nhịp ngầm
(news, growth, sensor Downloads) bỏ qua lượt chạy để nhường trọn CPU/RAM cho Sếp.
WebSocket/chat KHÔNG bị đụng tới — vẫn nhận được lệnh "thức dậy".
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, time as _dtime
from pathlib import Path

from core.config import settings, PROJECT_ROOT

# AURA-DEPS: psutil  # cảm biến RAM cho cơ chế nhường đường (least-privilege: chỉ đọc)
logger = logging.getLogger("aura.daemon")

# psutil = "cảm biến nhường đường". Import MỀM: thiếu lib thì daemon vẫn chạy bình
# thường (coi như không có áp lực RAM), chỉ mất khả năng tự ngủ đông. Cài: pip install psutil
try:  # noqa: SIM105
    import psutil  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - tuỳ môi trường
    psutil = None  # type: ignore[assignment]
    logger.warning(
        "Thiếu 'psutil' -> cảm biến nhường đường RAM TẮT (tác vụ ngầm chạy như cũ). "
        "Cài để bật: pip install psutil"
    )

# Thư mục Downloads mặc định của người dùng (Windows/macOS/Linux đều là ~/Downloads).
_DOWNLOADS_DIR = Path.home() / "Downloads"
# Đuôi file đáng chú ý để gợi ý xử lý.
_INTERESTING_EXTS: frozenset[str] = frozenset(
    {".pdf", ".zip", ".cbz", ".docx", ".xlsx", ".txt", ".jpg", ".png", ".epub"}
)
# VIDEO tải về -> gợi ý đưa thẳng vào XƯỞNG dịch (user 2026-07-06: "sao AURA không
# thấy video tôi mới tải" — trước đây danh sách trên quên các đuôi video).
_VIDEO_EXTS: frozenset[str] = frozenset({".mp4", ".mkv", ".webm", ".mov", ".flv", ".ts"})
# Bỏ qua file tạm trình duyệt đang tải dở.
_TEMP_SUFFIXES: tuple[str, ...] = (".crdownload", ".part", ".tmp", ".download")
# Tiến trình BẬN — đang chạy thì HOÃN ép nghỉ để khỏi cắt ngang việc quan trọng.
# (a) Render video/3D (nặng máy, cắt ngang là hỏng việc).
_RENDER_PROCS: frozenset[str] = frozenset({
    "capcut", "ffmpeg", "premiere", "adobe premiere", "afterfx", "after effects",
    "davinci", "resolve", "blender", "handbrake", "vegas",
    "topaz", "encoder", "media encoder", "render",
})
# (b) Họp hành / trình chiếu / quay-stream — cắt ngang là gián đoạn cuộc họp/buổi present.
_MEETING_PROCS: frozenset[str] = frozenset({
    "zoom", "teams", "ms-teams", "msteams", "powerpnt", "powerpoint", "obs", "obs64",
    "webex", "skype", "slack", "discord", "gotomeeting", "google meet",
    "anydesk", "teamviewer",
})
# Gộp lại — quét theo TÊN tiến trình (so khớp chuỗi con, không phân biệt hoa thường).
_HEAVY_PROCS: frozenset[str] = _RENDER_PROCS | _MEETING_PROCS

# (c) TRÌNH DUYỆT đang dùng camera/micro (họp web: Google Meet/Zoom web...): nhân Chromium
# spawn tiến trình con có cmdline chứa các cờ này khi bật camera/mic -> dò qua psutil.cmdline.
_BROWSER_NAMES: frozenset[str] = frozenset({
    "chrome", "msedge", "edge", "brave", "opera", "vivaldi", "chromium", "coccoc",
})
_AVCAPTURE_HINTS: tuple[str, ...] = (
    "video_capture", "videocaptureservice", "video_capture.mojom",
    "--use-fake-ui-for-media-stream",
)
# ⛔ CỐ Ý KHÔNG đưa "AudioService"/"audio.mojom" vào danh sách hoãn: nhân Chromium chạy
# AudioService cho MỌI phát-âm-thanh (kể cả nghe nhạc/YouTube). Health Guard sinh ra để
# ÉP kỷ luật — nếu nghe nhạc cũng hoãn thì tính năng vô tác dụng. Họp CHỈ-TIẾNG (tắt cam)
# đã được bắt qua app native (Zoom/Teams/Webex...). ĐỪNG thêm AudioService vào đây.


def _parse_hhmm(value: str, default: "_dtime") -> "_dtime":
    """Đọc 'HH:MM' -> datetime.time; sai định dạng -> default."""
    try:
        hh, mm = str(value).strip().split(":")
        return _dtime(int(hh), int(mm))
    except Exception:  # noqa: BLE001
        return default


class AuraDaemon:
    """Quản lý event loop ngầm + các sensor của AURA."""

    def __init__(
        self,
        event_queue: "asyncio.Queue[dict]",
        downloads_dir: Path | None = None,
        sensor_interval_s: float | None = None,
        news_enabled: bool = True,
        news_interval_s: float = 8 * 3600.0,   # ~3 lần/ngày
        news_initial_delay_s: float = 120.0,   # chờ hệ ổn định rồi mới đọc tin
        growth_enabled: bool = True,
        growth_interval_s: float = 24 * 3600.0,  # nhịp trưởng thành 1 lần/ngày
        growth_initial_delay_s: float = 300.0,
        ram_yield_threshold: float | None = None,
        ram_recheck_s: float | None = None,
        health_enabled: bool | None = None,
    ) -> None:
        """
        Args:
            event_queue: hàng đợi chia sẻ với server để đẩy tin chủ động ra UI.
            downloads_dir: thư mục quét; mặc định ~/Downloads.
            sensor_interval_s: chu kỳ quét; mặc định settings.sensor_interval_s.
        """
        self.event_queue = event_queue
        self.downloads_dir = downloads_dir or _DOWNLOADS_DIR
        self.interval = sensor_interval_s or settings.sensor_interval_s
        self._tasks: list[asyncio.Task] = []
        self._running = False
        # Tập file đã thấy ở lần quét đầu — để chỉ báo file MỚI xuất hiện sau đó.
        self._seen: set[str] = set()
        # Nhịp tim đọc tin (news.scout) — chạy ngầm tần suất thấp, nhẹ CPU.
        self.news_enabled = news_enabled
        self.news_interval_s = news_interval_s
        self.news_initial_delay_s = news_initial_delay_s
        self.growth_enabled = growth_enabled
        self.growth_interval_s = growth_interval_s
        self.growth_initial_delay_s = growth_initial_delay_s
        # Nhịp dọn rác (trash.janitor) — nay chạy TRONG tổ công nhân, cờ bật vẫn giữ.
        self.janitor_enabled = bool(getattr(settings, "janitor_enabled", True))
        # NHỊP TỔ CÔNG NHÂN (gộp 3: job + news + janitor). Tổ trưởng due-gate từng công
        # nhân (news ~8h, job/janitor ~24h) nên nhịp chỉ cần dò thường hơn chu kỳ ngắn nhất.
        self._crew_tick_s = 4 * 3600.0          # dò "tới hạn" mỗi 4h
        self._crew_initial_delay_s = 150.0      # chờ hệ ổn định rồi mới ra quân
        # NHỊP TỰ VIẾT TRUYỆN (story.factory autopilot) — AURA tự vận hành: định kỳ
        # tự viết chương mới cho bộ đang chạy, không cần user bấm.
        self.story_autopilot_enabled = bool(getattr(settings, "story_autopilot_enabled", False))
        self._story_tick_s = float(getattr(settings, "story_autopilot_interval_h", 12.0)) * 3600.0
        self._story_initial_delay_s = 300.0
        # Tích kho VIDEO: chương đã viết mà chưa có video kể chuyện -> tự đẩy story.video.
        self.story_video_autopilot = bool(
            getattr(settings, "story_autopilot_video_enabled", False)
        )
        # Tự ĐĂNG video đã dựng lên YouTube (Unlisted) -> tự đẩy youtube.upload.
        self.story_youtube_autopilot = bool(
            getattr(settings, "story_autopilot_youtube_enabled", False)
        )
        # Tích kho TRUYỆN TRANH: chương đã viết mà chưa có bản tranh -> đẩy story.comic.
        self.story_comic_autopilot = bool(
            getattr(settings, "story_autopilot_comic_enabled", False)
        )
        # AURA tự nghĩ chủ đề SÁCH TÔ MÀU mới mỗi lượt -> đẩy coloringbook.factory.
        self.coloring_autopilot = bool(
            getattr(settings, "coloring_autopilot_enabled", False)
        )
        # Kênh Anh thị trường Mỹ: tự nghĩ chủ đề explainer -> đẩy explainer.video.
        # Kênh Shorts/TikTok VN: đề tài NÓNG từ trend_radar -> video ngắn dọc.
        self.shorts_autopilot = bool(
            getattr(settings, "shorts_autopilot_enabled", False)
        )
        self.shorts_youtube_autopilot = bool(
            getattr(settings, "shorts_youtube_autopilot_enabled", False)
        )
        self.explainer_autopilot = bool(
            getattr(settings, "explainer_autopilot_enabled", False)
        )
        # Cảm biến nhường đường: ngưỡng RAM (0..1) và nhịp dò lại khi đang ngủ đông.
        self.ram_yield_threshold = (
            ram_yield_threshold if ram_yield_threshold is not None
            else settings.ram_yield_threshold
        )
        self.ram_recheck_s = (
            ram_recheck_s if ram_recheck_s is not None else settings.ram_recheck_s
        )
        # CẤP 1 — AURA NGỦ ĐÔNG: True -> mọi nhịp ngầm bỏ qua lượt chạy, nhường CPU/RAM
        # cho Sếp. WebSocket/chat KHÔNG bị động tới (vẫn nhận lệnh "aura thức dậy").
        self.aura_frozen = False
        self._freeze_poll_s = 3.0   # khi đang ngủ đông, mỗi 3s dò lại cờ
        # --- Health Guard (ép nghỉ kỷ luật, Cấp người dùng) ---
        self.health_enabled = (
            settings.health_enabled if health_enabled is None else health_enabled
        )
        self.health_tick_s = settings.health_tick_s
        self.health_work_limit_s = settings.health_work_limit_min * 60.0
        self.health_break_s = settings.health_break_min * 60.0
        self.health_busy_delay_s = settings.health_busy_delay_min * 60.0
        self.health_initial_delay_s = 60.0
        # Trần số lần hoãn liên tiếp. 2 lần x 30 phút = tối đa lùi 1 tiếng, rồi ÉP.
        self._HEALTH_MAX_DEFERS = 2
        self._health_defer_count = 0
        self._sit_elapsed_s = 0.0   # đã ngồi liên tục bao lâu (giây)
        # Ép nghỉ CẢ điện thoại Android (tắt màn hình qua ADB) khi tới giờ nghỉ.
        self.phone_sleep_on_break = bool(getattr(settings, "phone_sleep_on_break", False))
        self.adb_path = getattr(settings, "adb_path", "adb")
        self.adb_connect = getattr(settings, "adb_connect", "")   # ip:port WiFi (rỗng=USB)
        self.phone_sleep_repeat_s = float(getattr(settings, "phone_sleep_repeat_s", 45.0))
        # --- Nhịp sinh học: Briefing sáng / Review tối (nhận biết giờ thực) ---
        self._briefing_time = _parse_hhmm(settings.briefing_time, _dtime(8, 0))
        self._review_time = _parse_hhmm(settings.review_time, _dtime(21, 0))
        self._briefing_catchup_min = settings.briefing_catchup_min
        self._briefing_poll_s = settings.briefing_poll_s
        self._briefing_persona = settings.briefing_persona   # alpha | gentle
        self._briefing_scan_jobs = settings.briefing_scan_jobs
        self._job_keywords = settings.job_keywords
        self._job_urls = (
            [u.strip() for u in settings.job_urls.split(",") if u.strip()]
            if settings.job_urls else None
        )
        self._briefing_state_path = PROJECT_ROOT / "data" / "briefing_state.json"
        self._last_fired = self._load_briefing_state()
        # Cloud cho briefing (Bước 4): pre-approve + trần chi phí/ngày.
        self.briefing_allow_cloud = settings.briefing_allow_cloud
        self.briefing_cloud_daily_cap = settings.briefing_cloud_daily_cap
        # ── NHỊP TỰ CHỦ: tự điểm email quan trọng giữa ngày (nghĩ trên pool cloud, ~0 tải CPU) ──
        # Chỉ bật khi đã cấu hình email. Có NGÂN SÁCH/ngày + dedupe để khỏi spam, tôn trọng ngủ đông/RAM.
        self.email_digest_enabled = (
            settings.gmail_user is not None and settings.gmail_app_password is not None
        )
        self.email_digest_interval_s = 4 * 3600.0     # ~4 lần/ngày
        self.email_digest_initial_delay_s = 600.0     # 10' sau khởi động mới chạy
        self.email_digest_daily_cap = 4               # trần "ngân sách tự chủ"/ngày
        self._engines = None        # (local, cloud) — dựng lười khi cần
        # Bộ nhớ để LƯU bản briefing cuối (main.py gắn = orchestrator.memory; có thể None).
        self.memory = None

    # ------------------------------------------------------------------ #
    # CẤP 1 — Điều khiển trạng thái ngủ đông ứng dụng (AURA Sleep)
    # ------------------------------------------------------------------ #
    def freeze_aura(self) -> None:
        """Cho AURA NGỦ ĐÔNG — các nhịp ngầm (news/growth/sensor) bỏ qua lượt chạy ngay."""
        self.aura_frozen = True
        logger.info("AURA NGỦ ĐÔNG: tạm dừng news/growth/sensor, nhường CPU/RAM cho Sếp.")

    def unfreeze_aura(self) -> None:
        """ĐÁNH THỨC AURA — các nhịp ngầm hoạt động trở lại bình thường."""
        self.aura_frozen = False
        logger.info("AURA THỨC DẬY: các nhịp ngầm hoạt động trở lại.")

    # ------------------------------------------------------------------ #
    async def _emit(self, text: str, kind: str = "proactive") -> None:
        """Đẩy một tin chủ động vào hàng đợi để server broadcast ra UI."""
        await self.event_queue.put({"type": kind, "text": text})
        logger.info("Sự kiện chủ động: %s", text)
        # Gương tin chủ động (briefing/review/báo cáo) sang điện thoại nếu bật Telegram.
        messenger = getattr(self, "_messenger", None)
        if messenger is not None:
            asyncio.create_task(messenger.send(text))

    # ------------------------------------------------------------------ #
    def _ram_percent(self) -> float | None:
        """
        % RAM hệ thống đang dùng (0..1). Trả None nếu không đo được
        (thiếu psutil hoặc lỗi đọc) -> phía gọi coi như KHÔNG có áp lực.
        Không bao giờ ném exception ra ngoài (vành đai phụ trợ).
        """
        if psutil is None:
            return None
        try:
            return float(psutil.virtual_memory().percent) / 100.0
        except Exception as exc:  # noqa: BLE001 - đọc RAM lỗi không được giết daemon
            logger.warning("Đọc RAM (psutil) lỗi: %s", exc)
            return None

    async def _await_ram_headroom(self, label: str) -> None:
        """
        CỬA NHƯỜNG ĐƯỜNG: chặn cho tới khi RAM xuống dưới ngưỡng.

        Nếu RAM > ngưỡng (mặc định 85%), tác vụ ngầm `label` "ngủ đông": ngủ
        `ram_recheck_s` giây rồi dò lại, lặp tới khi RAM hạ — để dồn sức cho Sếp.
        Thiếu psutil (đo ra None) -> qua cửa ngay, không cản trở.
        """
        warned = False
        while self._running:
            pct = self._ram_percent()
            if pct is None or pct < self.ram_yield_threshold:
                if warned:
                    logger.info("RAM hạ còn %.0f%% — '%s' thức dậy làm việc.",
                                (pct or 0) * 100, label)
                return
            if not warned:
                logger.info(
                    "RAM %.0f%% > %.0f%% — '%s' NGỦ ĐÔNG nhường máy cho Sếp.",
                    pct * 100, self.ram_yield_threshold * 100, label,
                )
                warned = True
            await asyncio.sleep(self.ram_recheck_s)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _is_temp(path: Path) -> bool:
        """File tải dở của trình duyệt thì bỏ qua."""
        return path.name.endswith(_TEMP_SUFFIXES)

    def _snapshot(self) -> set[str]:
        """Chụp danh sách file hợp lệ hiện có trong Downloads."""
        if not self.downloads_dir.exists():
            return set()
        result: set[str] = set()
        for p in self.downloads_dir.iterdir():
            if p.is_file() and not self._is_temp(p):
                result.add(p.name)
        return result

    async def _downloads_sensor(self) -> None:
        """
        Sensor nền: cứ `interval` giây quét Downloads một lần.

        Lần quét đầu chỉ ghi nhận hiện trạng (không báo gì — tránh spam mọi file cũ).
        Các lần sau, file nào mới xuất hiện -> đẩy gợi ý chủ động ra UI.
        """
        self._seen = self._snapshot()  # baseline, không báo
        logger.info("Sensor Downloads bật (%d file hiện có, theo dõi file mới).",
                    len(self._seen))

        while self._running:
            await asyncio.sleep(self.interval)
            if self.aura_frozen:            # CẤP 1: ngủ đông -> bỏ qua quét file
                continue
            try:
                current = self._snapshot()
            except OSError as exc:
                logger.warning("Quét Downloads lỗi (bỏ qua nhịp này): %s", exc)
                continue

            new_files = current - self._seen
            for name in sorted(new_files):
                ext = Path(name).suffix.lower()
                if ext in _VIDEO_EXTS:
                    await self._emit(
                        f"Sếp vừa tải video '{name}' về. Muốn em đưa vào XƯỞNG dịch + "
                        f"lồng tiếng không? Dán đường dẫn {self.downloads_dir / name} "
                        "vào ô video.factory trên dashboard (127.0.0.1:8766) là chạy."
                    )
                elif ext in _INTERESTING_EXTS:
                    await self._emit(
                        f"Sếp vừa tải '{name}' về. Cần em phân tích / sắp xếp không?"
                    )
            self._seen = current

    # ------------------------------------------------------------------ #
    def _autopilot_series(self) -> list[str]:
        """CÁC bộ để tự nuôi — trả về TÊN THƯ MỤC bộ (đã slug) để story.factory
        viết ĐÚNG bộ cũ (dùng lại bible), không tạo bộ mới. Config chỉ định thì
        CHỈ nuôi bộ đó; rỗng = nuôi MỌI bộ có bible (đa bộ song song, bộ mới
        hoạt động gần nhất xếp trước — được chia ngân sách video/upload trước)."""
        cfg = str(getattr(settings, "story_autopilot_series", "") or "").strip()
        if cfg:
            return [cfg]
        story_root = settings.outputs_dir / "story"
        if not story_root.exists():
            return []
        # Bỏ thư mục *_backup / _archive: bản lưu bộ cũ (vd viết lại từ đầu với
        # prompt mới) — autopilot KHÔNG được tiếp tục nuôi bản backup.
        cands = [d for d in story_root.iterdir()
                 if d.is_dir() and (d / "bible.json").is_file()
                 and not d.name.lower().endswith(("_backup", "_archive"))]
        return [d.name for d in
                sorted(cands, key=lambda d: d.stat().st_mtime, reverse=True)]

    @staticmethod
    def _enqueue_story_videos(series: str, cap: int | None = None) -> list[int]:
        """TÍCH KHO VIDEO: chương đã viết (story/<bộ>/chapters/ch_NNNN.md) mà chưa có
        video kể chuyện (story_video/<bộ>/ch_NNNN/package_info.json — chỉ ghi khi render
        xong) thì đẩy job story.video, tối đa `cap` job/lượt (None = lấy config
        story_autopilot_video_per_tick; đa bộ thì autopilot chia ngân sách chung).
        Chương lỗi dở sẽ được đẩy lại ở lượt sau (checkpoint trong tool tự nối tiếp).
        Trả về danh sách số chương vừa đẩy."""
        from factory import queue as _fq
        from factory.models import JobRecord

        chap_dir = settings.outputs_dir / "story" / series / "chapters"
        if not chap_dir.is_dir():
            return []
        pending = {
            int(j.params.get("chapter") or 0)
            for j in _fq.list_jobs(limit=100)
            if j.tool == "story.video" and j.state in ("queued", "running")
            and str(j.params.get("series") or "") == series
        }
        if cap is None:
            cap = int(getattr(settings, "story_autopilot_video_per_tick", 3))
        if cap <= 0:
            return []
        made: list[int] = []
        for md in sorted(chap_dir.glob("ch_*.md")):
            try:
                num = int(md.stem.split("_")[1])
            except (IndexError, ValueError):
                continue
            done_mark = (settings.outputs_dir / "story_video" / series
                         / f"ch_{num:04d}" / "package_info.json")
            if num in pending or done_mark.exists():
                continue
            _fq.enqueue(JobRecord(tool="story.video",
                                  params={"series": series, "chapter": num}))
            made.append(num)
            if len(made) >= cap:
                break
        return made

    @staticmethod
    def _enqueue_story_comics(series: str, cap: int | None = None) -> list[int]:
        """TÍCH KHO TRUYỆN TRANH: chương đã viết (story/<bộ>/chapters/ch_NNNN.md) mà
        chưa có bản tranh (story_comic/<bộ>/ch_NNNN/package_info.json) thì đẩy job
        story.comic, tối đa `cap` job/lượt (None = config). Chương lỗi dở đẩy lại
        lượt sau (checkpoint trong tool). Trả danh sách số chương vừa đẩy."""
        from factory import queue as _fq
        from factory.models import JobRecord

        chap_dir = settings.outputs_dir / "story" / series / "chapters"
        if not chap_dir.is_dir():
            return []
        pending = {
            int(j.params.get("chapter") or 0)
            for j in _fq.list_jobs(limit=100)
            if j.tool == "story.comic" and j.state in ("queued", "running")
            and str(j.params.get("series") or "") == series
        }
        if cap is None:
            cap = int(getattr(settings, "story_autopilot_comic_per_tick", 1))
        if cap <= 0:
            return []
        made: list[int] = []
        for md in sorted(chap_dir.glob("ch_*.md")):
            try:
                num = int(md.stem.split("_")[1])
            except (IndexError, ValueError):
                continue
            done_mark = (settings.outputs_dir / "story_comic" / series
                         / f"ch_{num:04d}" / "package_info.json")
            if num in pending or done_mark.exists():
                continue
            _fq.enqueue(JobRecord(tool="story.comic",
                                  params={"series": series, "chapter": num}))
            made.append(num)
            if len(made) >= cap:
                break
        return made

    @staticmethod
    def _enqueue_youtube_uploads(series: str, cap: int | None = None) -> list[str]:
        """TỰ ĐĂNG: video kể chuyện đã dựng (story_video/<bộ>/ch_NNNN/ có mp4 +
        package_info.json) mà CHƯA đăng YouTube thì đẩy job youtube.upload.
        Bỏ qua video đã có trong sổ đăng (ledger/publishes.jsonl) hoặc đang có job
        chờ/chạy. Cần kênh video-youtube trong sổ kênh đã cấp quyền token. `cap`
        None = config (đa bộ: autopilot chia ngân sách chung — quota ~6 video/ngày).
        Trả tên chương vừa đẩy."""
        from factory import queue as _fq
        from factory.models import JobRecord
        from factory import channels as _ch

        vids = _ch.for_content("video", "youtube")
        if not vids:
            return []
        channel_key = str(vids[0].get("key") or "")

        vroot = settings.outputs_dir / "story_video" / series
        if not vroot.is_dir():
            return []

        # Đã đăng: đọc sổ publishes.jsonl (trường "file"). Chuẩn hoá path để so khớp.
        published: set[str] = set()
        ledger = settings.ledger_dir / "publishes.jsonl"
        if ledger.is_file():
            for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    f = json.loads(line).get("file")
                    if f:
                        published.add(str(Path(f)))
                except (ValueError, TypeError):
                    continue
        # Đang chờ/chạy: né đẩy trùng.
        pending: set[str] = {
            str(Path(str(j.params.get("video") or "")))
            for j in _fq.list_jobs(limit=100)
            if j.tool == "youtube.upload" and j.state in ("queued", "running")
        }

        if cap is None:
            cap = int(getattr(settings, "story_autopilot_youtube_per_tick", 3))
        if cap <= 0:
            return []
        made: list[str] = []
        for d in sorted(vroot.iterdir()):
            if not d.is_dir() or not (d / "package_info.json").is_file():
                continue
            mp4s = sorted(d.glob("*.mp4"))
            if not mp4s:
                continue
            mp4 = mp4s[0]
            if str(mp4) in published or str(mp4) in pending:
                continue
            privacy = str(getattr(settings, "story_autopilot_youtube_privacy", "private"))
            _fq.enqueue(JobRecord(tool="youtube.upload", params={
                "video": str(mp4), "channel": channel_key, "privacy": privacy,
            }))
            made.append(d.name)
            if len(made) >= cap:
                break
        return made

    @staticmethod
    def _enqueue_story_kit(series: str) -> bool:
        """Bộ chưa có BÌA (publish_kit/cover.png) thì đẩy job story.kit (văn án +
        bìa 512×800 + tags). Chạy 1 lần/bộ; không chồng. Trả True nếu vừa đẩy."""
        from factory import queue as _fq
        from factory.models import JobRecord

        story_dir = settings.outputs_dir / "story" / series
        if (story_dir / "publish_kit" / "cover.png").is_file():
            return False
        if any(j.tool == "story.kit" and j.state in ("queued", "running")
               and str(j.params.get("series") or "") == series
               for j in _fq.list_jobs(limit=100)):
            return False
        _fq.enqueue(JobRecord(tool="story.kit", params={"series": series}))
        return True

    @staticmethod
    def _enqueue_coloringbook() -> str | None:
        """AURA TỰ NGHĨ 1 chủ đề sách tô màu MỚI (khác các cuốn đã làm) rồi đẩy job.
        Không chồng job; dừng khi đã đủ coloring_autopilot_max_books. Trả tên chủ đề
        vừa đẩy (None nếu bỏ lượt). Chỉ chạy 1 lần/nhịp (không theo bộ truyện)."""
        from factory import queue as _fq
        from factory.models import JobRecord

        # Không chồng: đang có job tô màu chờ/chạy thì bỏ lượt.
        if any(j.tool == "coloringbook.factory" and j.state in ("queued", "running")
               for j in _fq.list_jobs(limit=100)):
            return None
        # Chủ đề đã làm (đọc package_info của các cuốn cũ) + trần số cuốn.
        cbroot = settings.outputs_dir / "coloringbook"
        used: list[str] = []
        if cbroot.is_dir():
            for d in cbroot.iterdir():
                pkg = d / "package_info.json"
                if pkg.is_file():
                    try:
                        used.append(str(json.loads(pkg.read_text(encoding="utf-8"))
                                        .get("theme") or ""))
                    except (ValueError, OSError):
                        pass
        if len(used) >= int(getattr(settings, "coloring_autopilot_max_books", 15)):
            return None          # đủ kho, chờ Sếp bán bớt rồi nâng trần
        # LLM nghĩ chủ đề mới, bán được, khác cái đã làm.
        try:
            from core.llm import CloudEngine
            res = CloudEngine().complete(
                [{"role": "user", "content":
                  "Đã làm các chủ đề: " + (", ".join(x for x in used if x) or "(chưa có)")
                  + ". Gợi ý 1 chủ đề sách tô màu MỚI, dễ bán trên Etsy/Payhip, KHÁC "
                  "các chủ đề trên. Trả JSON THUẦN {\"theme\": \"chủ đề tiếng Anh ngắn\", "
                  "\"audience\": \"kids hoặc adults\"}."}],
                system_prompt="Bạn là người bán sách tô màu rành thị trường Etsy.",
                temperature=0.9, max_tokens=200, tier="fast",
            )
            import re as _re
            m = _re.search(r"\{.*\}", str(res.get("text", "")), _re.DOTALL)
            if not m:
                return None
            pick = json.loads(m.group(0))
        except Exception:  # noqa: BLE001 — nghĩ chủ đề hỏng: bỏ lượt, không sập
            return None
        theme = str(pick.get("theme") or "").strip()
        if not theme:
            return None
        aud = "adults" if str(pick.get("audience") or "kids") == "adults" else "kids"
        _fq.enqueue(JobRecord(tool="coloringbook.factory", params={
            "theme": theme, "audience": aud,
            "pages": int(getattr(settings, "coloring_autopilot_pages", 12)),
        }))
        return theme

    @staticmethod
    def _enqueue_explainer() -> str | None:
        """Kênh Anh Mỹ: AURA tự nghĩ 1 CHỦ ĐỀ mới trong ngách explainer_niche (khác
        chủ đề đã làm) rồi đẩy explainer.video. Không chồng; dừng khi đủ trần.
        Trả chủ đề vừa đẩy (None nếu bỏ). 1 lần/nhịp."""
        from factory import queue as _fq
        from factory.models import JobRecord

        if any(j.tool == "explainer.video" and j.state in ("queued", "running")
               for j in _fq.list_jobs(limit=100)):
            return None
        root = settings.outputs_dir / "explainer"
        used: list[str] = []
        if root.is_dir():
            for d in root.iterdir():
                pkg = d / "package_info.json"
                if pkg.is_file():
                    try:
                        used.append(str(json.loads(pkg.read_text(encoding="utf-8"))
                                        .get("topic") or ""))
                    except (ValueError, OSError):
                        pass
        if len(used) >= int(getattr(settings, "explainer_autopilot_max", 10)):
            return None
        niche = str(getattr(settings, "explainer_niche", "") or "history explained")
        try:
            from core.llm import CloudEngine
            res = CloudEngine().complete(
                [{"role": "user", "content":
                  f"Niche: {niche}. Already covered: "
                  + (", ".join(x for x in used if x) or "(none)")
                  + ". Suggest ONE fresh, specific, high-retention video TOPIC in this "
                  "niche, DIFFERENT from those. Return PURE JSON {\"topic\": \"...\"}."}],
                system_prompt="You pick winning faceless YouTube topics for the US market.",
                temperature=0.9, max_tokens=150, tier="fast",
            )
            import re as _re
            m = _re.search(r"\{.*\}", str(res.get("text", "")), _re.DOTALL)
            if not m:
                return None
            topic = str(json.loads(m.group(0)).get("topic") or "").strip()
        except Exception:  # noqa: BLE001
            return None
        if not topic:
            return None
        _fq.enqueue(JobRecord(tool="explainer.video",
                              params={"topic": topic, "niche": niche}))
        return topic

    @staticmethod
    def _enqueue_shorts() -> str | None:
        """Kênh Shorts VN: lấy 1 đề tài NÓNG nhất từ trend_radar (khác đề đã làm) rồi
        đẩy video.shorts. Không chồng job; dừng khi đủ trần. Trả đề tài vừa đẩy."""
        from factory import queue as _fq
        from factory.models import JobRecord

        if any(j.tool == "video.shorts" and j.state in ("queued", "running")
               for j in _fq.list_jobs(limit=100)):
            return None

        # Đề tài đã làm (để không lặp).
        root = settings.outputs_dir / "shorts"
        used: set[str] = set()
        if root.is_dir():
            for d in root.iterdir():
                pkg = d / "package_info.json"
                if pkg.is_file():
                    try:
                        used.add(str(json.loads(pkg.read_text(encoding="utf-8"))
                                     .get("topic") or "").strip())
                    except (ValueError, OSError):
                        pass
        if len(used) >= int(getattr(settings, "shorts_autopilot_max", 12)):
            return None

        # Nguồn đề tài: trend_radar (công nhân thứ 4) — lấy tin fit cao nhất chưa làm.
        radar = settings.outputs_dir.parent / "feedback" / "trend_radar_last.json"
        if not radar.is_file():
            return None
        try:
            top = json.loads(radar.read_text(encoding="utf-8")).get("top") or []
        except (ValueError, OSError):
            return None
        topic = None
        for item in sorted(top, key=lambda x: -(x.get("fit") or 0)):
            title = str(item.get("title") or "").strip()
            if title and title not in used:
                topic = title
                break
        if not topic:
            return None

        _fq.enqueue(JobRecord(tool="video.shorts", params={
            "topic": topic, "language": "vi",
            "voice": str(getattr(settings, "shorts_voice", "vi-VN-HoaiMyNeural-Female")),
        }))
        return topic

    @staticmethod
    def _enqueue_shorts_uploads(cap: int | None = None) -> list[str]:
        """TỰ ĐĂNG SHORTS: video ngắn đã dựng (shorts/<slug>/ có mp4 + package_info.json)
        mà CHƯA đăng thì đẩy job youtube.upload (privacy theo config, mặc định private).
        Bỏ video đã trong sổ đăng hoặc đang chờ/chạy. Trả tên thư mục vừa đẩy."""
        from factory import queue as _fq
        from factory.models import JobRecord
        from factory import channels as _ch

        # Kênh: config chỉ định > kênh video mặc định trong sổ kênh.
        channel_key = str(getattr(settings, "shorts_youtube_channel", "") or "").strip()
        if not channel_key:
            vids = _ch.for_content("video", "youtube")
            if not vids:
                return []
            channel_key = str(vids[0].get("key") or "")

        sroot = settings.outputs_dir / "shorts"
        if not sroot.is_dir():
            return []

        published: set[str] = set()
        ledger = settings.ledger_dir / "publishes.jsonl"
        if ledger.is_file():
            for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    f = json.loads(line).get("file")
                    if f:
                        published.add(str(Path(f)))
                except (ValueError, TypeError):
                    continue
        pending: set[str] = {
            str(Path(str(j.params.get("video") or "")))
            for j in _fq.list_jobs(limit=100)
            if j.tool == "youtube.upload" and j.state in ("queued", "running")
        }

        if cap is None:
            cap = int(getattr(settings, "shorts_youtube_per_tick", 3))
        if cap <= 0:
            return []
        privacy = str(getattr(settings, "shorts_youtube_privacy", "private"))
        made: list[str] = []
        for d in sorted(sroot.iterdir()):
            if not d.is_dir() or not (d / "package_info.json").is_file():
                continue
            mp4s = sorted(d.glob("*.mp4"))
            if not mp4s or str(mp4s[0]) in published or str(mp4s[0]) in pending:
                continue
            _fq.enqueue(JobRecord(tool="youtube.upload", params={
                "video": str(mp4s[0]), "channel": channel_key, "privacy": privacy,
            }))
            made.append(d.name)
            if len(made) >= cap:
                break
        return made

    async def _story_autopilot(self) -> None:
        """NHỊP TỰ VIẾT: định kỳ đẩy một job story.factory viết tiếp bộ đang chạy.
        AURA tự vận hành — user không phải bấm. Chỉ ENQUEUE (worker xưởng thực thi
        1 job nặng/lúc), nên không tranh RAM với job khác. Lỗi gì cũng không giết daemon.
        """
        await asyncio.sleep(self._story_initial_delay_s)
        while self._running:
            if self.aura_frozen:
                await asyncio.sleep(self._freeze_poll_s)
                continue
            try:
                from factory import queue as _fq
                from factory.models import JobRecord
                # ĐA BỘ: nuôi mọi bộ có bible. Ngân sách video/upload là CHUNG cả
                # lượt (không nhân theo số bộ — upload dính quota ~6/ngày); bộ mới
                # hoạt động gần nhất được chia trước.
                all_series = self._autopilot_series()
                vid_budget = int(getattr(settings, "story_autopilot_video_per_tick", 3))
                up_budget = int(getattr(settings, "story_autopilot_youtube_per_tick", 3))
                comic_budget = int(getattr(settings, "story_autopilot_comic_per_tick", 1))
                jobs_now = _fq.list_jobs(limit=100)
                for series in all_series:
                    # Không chồng job VIẾT của cùng bộ (bộ khác vẫn được viết song song).
                    busy = any(
                        j.tool == "story.factory" and j.state in ("queued", "running")
                        and str(j.params.get("series") or "") == series
                        for j in jobs_now
                    )
                    if not busy:
                        job = JobRecord(tool="story.factory", params={
                            "series": series,
                            "world": "(bộ đang chạy — tiếp bible sẵn có)",
                            "chapters": int(getattr(settings, "story_autopilot_chapters", 1)),
                            "words": int(getattr(settings, "story_autopilot_words", 1800)),
                        })
                        await asyncio.to_thread(_fq.enqueue, job)
                        logger.info("Story autopilot: đẩy job viết tiếp bộ '%s' (%s).",
                                    series, job.id)
                        await self._emit(
                            f"✍️ AURA đang tự viết thêm chương cho bộ '{series}'. "
                            "Xong sẽ nằm trong data/outputs/story/.", kind="proactive")
                    # BÌA + văn án + tags: bộ chưa có bìa thì dựng kit (1 lần/bộ).
                    if await asyncio.to_thread(self._enqueue_story_kit, series):
                        logger.info("Story autopilot: đẩy story.kit (bìa) bộ '%s'.", series)
                        await self._emit(
                            f"🎨 AURA đang vẽ BÌA + viết văn án cho bộ '{series}' "
                            "(để đăng Wattpad). Xong nằm ở publish_kit/.",
                            kind="proactive")
                    # Tích kho VIDEO song song kho chữ (worker vẫn 1 job nặng/lúc).
                    if self.story_video_autopilot and vid_budget > 0:
                        chaps = await asyncio.to_thread(
                            self._enqueue_story_videos, series, vid_budget)
                        vid_budget -= len(chaps)
                        if chaps:
                            logger.info("Story autopilot: đẩy %d job video (chương %s) "
                                        "bộ '%s'.", len(chaps), chaps, series)
                            await self._emit(
                                f"🎬 AURA đang dựng video kể chuyện chương "
                                f"{', '.join(map(str, chaps))} bộ '{series}' cho kho "
                                "YouTube. Xong sẽ nằm trong data/outputs/story_video/.",
                                kind="proactive")
                    # Tự ĐĂNG video đã dựng — Sếp duyệt trên Studio rồi bật Public.
                    if self.story_youtube_autopilot and up_budget > 0:
                        ups = await asyncio.to_thread(
                            self._enqueue_youtube_uploads, series, up_budget)
                        up_budget -= len(ups)
                        if ups:
                            logger.info("Story autopilot: đẩy %d job đăng YouTube (%s) "
                                        "bộ '%s'.", len(ups), ups, series)
                            await self._emit(
                                f"📤 AURA đang đăng {len(ups)} video "
                                f"({', '.join(ups)}) bộ '{series}' lên YouTube "
                                "(chế độ riêng tư — Sếp xem lại rồi bật Public).",
                                kind="proactive")
                    # Tích kho TRUYỆN TRANH: chương chưa có bản tranh thì dựng dần
                    # (nặng ~20 ảnh/chương nên ngân sách thấp; Webtoon đăng tay).
                    if self.story_comic_autopilot and comic_budget > 0:
                        cmx = await asyncio.to_thread(
                            self._enqueue_story_comics, series, comic_budget)
                        comic_budget -= len(cmx)
                        if cmx:
                            logger.info("Story autopilot: đẩy %d job truyện tranh "
                                        "(chương %s) bộ '%s'.", len(cmx), cmx, series)
                            await self._emit(
                                f"🎨 AURA đang vẽ truyện tranh chương "
                                f"{', '.join(map(str, cmx))} bộ '{series}'. Xong sẽ "
                                "nằm trong data/outputs/story_comic/ (dải webtoon sẵn đăng).",
                                kind="proactive")
                # SÁCH TÔ MÀU: 1 lần/nhịp (không theo bộ) — AURA tự nghĩ chủ đề mới.
                if self.coloring_autopilot:
                    theme = await asyncio.to_thread(self._enqueue_coloringbook)
                    if theme:
                        logger.info("Coloring autopilot: đẩy sách tô màu '%s'.", theme)
                        await self._emit(
                            f"🖍️ AURA tự nghĩ ra chủ đề sách tô màu mới: '{theme}' — "
                            "đang dựng để bán Payhip/Etsy (data/outputs/coloringbook/).",
                            kind="proactive")
                # VIDEO ANH thị trường Mỹ: 1 lần/nhịp — AURA tự nghĩ chủ đề explainer.
                if self.explainer_autopilot:
                    topic = await asyncio.to_thread(self._enqueue_explainer)
                    if topic:
                        logger.info("Explainer autopilot: đẩy video Anh '%s'.", topic)
                        await self._emit(
                            f"🎥 AURA tự chọn chủ đề video Anh (thị trường Mỹ): "
                            f"'{topic}' — đang dựng (data/outputs/explainer/).",
                            kind="proactive")
                # VIDEO NGẮN VN: 1 lần/nhịp — đề tài nóng từ trend_radar -> footage thật.
                if self.shorts_autopilot:
                    topic = await asyncio.to_thread(self._enqueue_shorts)
                    if topic:
                        logger.info("Shorts autopilot: đẩy video ngắn '%s'.", topic)
                        await self._emit(
                            f"📱 AURA tự chọn đề tài nóng từ trend_radar: '{topic}' — "
                            "đang dựng video ngắn dọc (data/outputs/shorts/).",
                            kind="proactive")
                # TỰ ĐĂNG SHORTS: video ngắn đã dựng -> YouTube (private, Sếp duyệt sau).
                if self.shorts_youtube_autopilot:
                    ups = await asyncio.to_thread(self._enqueue_shorts_uploads)
                    if ups:
                        logger.info("Shorts autopilot: đẩy %d job đăng Shorts (%s).",
                                    len(ups), ups)
                        await self._emit(
                            f"📤 AURA đang đăng {len(ups)} video ngắn "
                            f"({', '.join(ups)}) lên YouTube Shorts (chế độ riêng tư — "
                            "Sếp xem lại rồi bật Public).", kind="proactive")
                # ĐẨY TRUYỆN LÊN ROOKIES: chương mới -> BẢN THẢO trên web, Sếp duyệt
                # qua Telegram rồi mới đăng. sync_series so theo TIÊU ĐỀ với chương
                # đang có trên Rookies nên chạy lại KHÔNG sinh bản trùng.
                if getattr(settings, "rookies_autopilot_enabled", False):
                    try:
                        from core.rookies_bot import sync_series, create_story
                        per = int(getattr(settings, "rookies_autopilot_per_tick", 2))
                        pub = bool(getattr(settings, "rookies_autopilot_publish", False))
                        msg = await asyncio.to_thread(sync_series, series, per, pub)
                        # Bộ CHƯA có nhà trên Rookies -> TỰ TẠO (full-auto) rồi đẩy lại.
                        if "chưa" in msg.lower() and "tạo truyện" in msg.lower():
                            cr = await asyncio.to_thread(
                                create_story, series, True, True, 10.0, True)
                            logger.info("Rookies auto-create (%s): %s", series, cr)
                            if cr.startswith("✅"):
                                msg = await asyncio.to_thread(sync_series, series, per, pub)
                        logger.info("Rookies autopilot (%s): %s", series, msg)
                        if msg.startswith("📤"):
                            await self._emit(
                                f"{msg}\nDuyệt đăng công khai giúp em nhé Sếp.",
                                kind="proactive")
                    except Exception as exc:  # noqa: BLE001 — đẩy web hỏng không chặn nhịp
                        logger.warning("Rookies autopilot lỗi (%s): %s", series, exc)
            except Exception as exc:  # noqa: BLE001 — nhịp tự viết hỏng KHÔNG giết daemon
                logger.warning("Story autopilot lỗi (bỏ lượt): %s", exc)
            await asyncio.sleep(self._story_tick_s)

    # ------------------------------------------------------------------ #
    async def _skillopt_heartbeat(self) -> None:
        """ĐÊM TIẾN HOÁ (SkillOpt-Sleep): định kỳ để AURA tự rút kinh nghiệm từ các
        phiên làm việc rồi ĐỀ XUẤT bản kỹ năng tốt hơn — có cổng kiểm định held-out,
        không cải thiện thì tự từ chối. Mặc định CHỈ ĐỀ XUẤT, Sếp duyệt mới áp.
        Lỗi gì cũng KHÔNG giết daemon.
        """
        await asyncio.sleep(600)   # để máy khởi động xong đã
        interval = float(getattr(settings, "skillopt_interval_h", 24.0)) * 3600
        while self._running:
            if self.aura_frozen:
                await asyncio.sleep(self._freeze_poll_s)
                continue
            try:
                await self._await_ram_headroom("skillopt")
                from core.skillopt_hand import run_night
                msg = await asyncio.to_thread(run_night)
                logger.info("SkillOpt đêm tiến hoá: %s", msg.replace("\n", " | ")[:300])
                # Chỉ báo Sếp khi có ĐỀ XUẤT được chấp nhận (đỡ nhiễu mỗi đêm).
                if "accepted=True" in msg or "adopt" in msg.lower():
                    await self._emit(
                        "🧠 AURA vừa học được kỹ năng tốt hơn sau một đêm tự rèn.\n"
                        f"{msg}\nNhắn 'apdung' nếu Sếp duyệt.", kind="proactive")
            except Exception as exc:  # noqa: BLE001
                logger.warning("SkillOpt heartbeat lỗi (bỏ lượt): %s", exc)
            await asyncio.sleep(interval)

    # ------------------------------------------------------------------ #
    async def _crew_heartbeat(self) -> None:
        """
        NHỊP TỔ CÔNG NHÂN (gộp 3): định kỳ gọi TỔ TRƯỞNG (core/crew.py) chạy các công
        nhân TỚI HẠN trong một ca — news (~8h), job/janitor (~24h) — dùng chung MỘT lần
        nạp model, rồi gộp thành MỘT báo cáo gửi Sếp. Mỗi công nhân giữ nhịp riêng nhờ
        due-gate của tổ trưởng; nhịp này chỉ cần dò thường xuyên hơn chu kỳ ngắn nhất.

        Nhẹ CPU: chấm bằng embedding ~0.3s/công nhân. Lỗi gì cũng KHÔNG làm sập daemon.
        """
        await asyncio.sleep(self._crew_initial_delay_s)
        while self._running:
            if self.aura_frozen:            # CẤP 1: ngủ đông -> bỏ lượt
                await asyncio.sleep(self._freeze_poll_s)
                continue
            await self._await_ram_headroom("crew_heartbeat")
            if not self._running:
                break
            try:
                from core.crew import get_crew
                # to_thread: công nhân là I/O + CPU đồng bộ -> không chặn event loop.
                report = await asyncio.to_thread(
                    get_crew().run_shift, None, self._crew_enabled(), False, True
                )
                if report.get("notable") and report.get("text"):
                    await self._emit(report["text"])
                elif report.get("ran"):
                    logger.info("Tổ công nhân chạy [%s], không có gì đáng báo.",
                                ", ".join(report["ran"]))
            except Exception as exc:  # noqa: BLE001 — nhịp tổ hỏng KHÔNG được giết daemon
                logger.warning("Nhịp tổ công nhân lỗi (bỏ qua chu kỳ này): %s", exc)
            await asyncio.sleep(self._crew_tick_s)

    def _crew_enabled(self) -> set[str]:
        """Tập công nhân được BẬT (tôn trọng cờ news/janitor của daemon)."""
        on: set[str] = {"job", "radar"}
        if self.news_enabled:
            on.add("news")
        if self.janitor_enabled:
            on.add("janitor")
        return on

    async def _email_digest_heartbeat(self) -> None:
        """
        NHỊP TỰ CHỦ: vài lần/ngày tự đọc email chưa đọc, nhờ pool cloud lọc cái QUAN TRỌNG,
        và CHỈ ping ra UI khi có gì đáng (kèm dedupe + ngân sách/ngày). Nghĩ trên cloud nên
        ~0 tải CPU; tôn trọng ngủ đông + nhường RAM. Lỗi gì cũng KHÔNG giết daemon.
        """
        await asyncio.sleep(self.email_digest_initial_delay_s)
        while self._running:
            if self.aura_frozen:               # CẤP 1: ngủ đông -> im
                await asyncio.sleep(self._freeze_poll_s)
                continue
            await self._await_ram_headroom("email_digest")
            if not self._running:
                break
            try:
                today = datetime.now().date().isoformat()
                if self._email_digest_count(today) < self.email_digest_daily_cap:
                    digest = await asyncio.to_thread(self._make_email_digest)
                    if digest and digest != self._last_fired.get("email_digest_text"):
                        self._note_email_digest(today, digest)
                        await self._emit(f"📧 AURA điểm thư đáng chú ý:\n{digest}")
            except Exception as exc:  # noqa: BLE001 — nhịp email hỏng không giết daemon
                logger.warning("Nhịp email digest lỗi (bỏ qua chu kỳ): %s", exc)
            await asyncio.sleep(self.email_digest_interval_s)

    # ------------------------------------------------------------------ #
    def _load_briefing_state(self) -> dict:
        """Đọc ngày-đã-chạy gần nhất (chống chạy 2 lần/ngày kể cả sau khi reboot)."""
        try:
            if self._briefing_state_path.is_file():
                return json.loads(self._briefing_state_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Đọc briefing_state lỗi (bỏ qua): %s", exc)
        return {}

    def _save_briefing_state(self) -> None:
        try:
            self._briefing_state_path.parent.mkdir(parents=True, exist_ok=True)
            self._briefing_state_path.write_text(
                json.dumps(self._last_fired), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ghi briefing_state lỗi (bỏ qua): %s", exc)

    @staticmethod
    def _due(now_t, mark_t, catchup_min: float) -> bool:
        """now_t trong [mark, mark+catchup] (phút trong ngày) -> tới giờ chạy (có bắt kịp)."""
        n = now_t.hour * 60 + now_t.minute
        m = mark_t.hour * 60 + mark_t.minute
        return m <= n <= m + catchup_min

    def _profile_summary(self) -> str:
        """Chân dung Sếp (gọn) để ghép template. Lỗi/thiếu -> ''."""
        try:
            from core.profile import ProfileStore
            summ = ProfileStore().get_summary()
            return summ if "\n" in summ else ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("Đọc Chân dung Sếp lỗi (bỏ qua): %s", exc)
            return ""

    def _build_briefing_text(self, now: datetime) -> str:
        """Template TĨNH cho Briefing sáng (Bước 3 — CHƯA gọi cloud)."""
        parts = [f"🌅 BRIEFING SÁNG — {now.strftime('%d/%m/%Y')}"]
        summ = self._profile_summary()
        if summ:
            parts.append(summ)
        parts.append("Chào ngày mới Sếp! Mình bắt đầu từ việc quan trọng nhất nhé. Em luôn ở đây.")
        return "\n".join(parts)

    def _build_review_text(self, now: datetime, growth: str) -> str:
        """Template TĨNH cho Review tối (ghép kết quả trưởng thành nếu có)."""
        parts = [f"🌙 REVIEW TỐI — {now.strftime('%d/%m/%Y')}"]
        if growth:
            parts.append(growth)
        summ = self._profile_summary()
        if summ:
            parts.append(summ)
        parts.append("Nhìn lại một ngày rồi nghỉ sớm nhé Sếp. Ngày mai giỏi hơn hôm nay.")
        return "\n".join(parts)

    async def _run_growth_tasks(self) -> str:
        """Việc trưởng thành cũ (reflection + self_improve + scorecard) -> trả tóm tắt."""
        try:
            from core.reflection import analyze_daily_logs
            from core.self_improve import run_self_improvement
            from core.metrics import render_scorecard
            refl = await asyncio.to_thread(analyze_daily_logs)
            imp = await asyncio.to_thread(
                run_self_improvement, None, event_queue=self.event_queue
            )
            card = await asyncio.to_thread(render_scorecard)
            bits = []
            if isinstance(refl, dict) and refl.get('saved'):
                bits.append(f"rút {refl['saved']} bài học")
            if isinstance(imp, dict) and imp.get('proposals'):
                bits.append(f"đề xuất {len(imp['proposals'])} kỹ năng mới (chờ Sếp duyệt)")
            head = ('; '.join(bits)) if bits else 'không có gì mới'
            return f"🌱 Trưởng thành: {head}.\n{card}"
        except Exception as exc:  # noqa: BLE001 — growth hỏng không giết daemon
            logger.warning("Việc trưởng thành lỗi (bỏ qua): %s", exc)
            return ""

    # ------------------------------------------------------------------ #
    # BƯỚC 4 — Briefing/Review thông minh: Cloud -> Local -> Template (3 cấp)
    # ------------------------------------------------------------------ #
    def _get_engines(self):
        """Dựng lười cặp (local CPU, cloud Claude) cho briefing. Lỗi -> (None, None)."""
        if self._engines is None:
            try:
                from core.llm import build_engines
                self._engines = build_engines()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Dựng engine briefing lỗi: %s", exc)
                self._engines = (None, None)
        return self._engines

    def _cloud_budget_ok(self, today: str) -> bool:
        """Còn quota gọi Cloud trong ngày không (kiểm soát chi phí)."""
        used = self._last_fired.get("cloud_calls", {})
        return used.get(today, 0) < self.briefing_cloud_daily_cap

    def _note_cloud_call(self, today: str) -> None:
        used = self._last_fired.setdefault("cloud_calls", {})
        used[today] = used.get(today, 0) + 1
        for d in list(used):          # dọn ngày cũ -> state khỏi phình
            if d != today:
                used.pop(d, None)
        self._save_briefing_state()

    def _load_connector(self, name: str):
        """Nạp lười module connector từ skills/connectors/ (path-based, cache lại)."""
        if not hasattr(self, "_connectors"):
            self._connectors = {}
        if name not in self._connectors:
            import importlib.util
            path = PROJECT_ROOT / "skills" / "connectors" / f"{name}.py"
            spec = importlib.util.spec_from_file_location(f"aura_conn_{name}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self._connectors[name] = mod
        return self._connectors[name]

    def _connector_context(self) -> str:
        """Lịch hôm nay + email CHƯA ĐỌC (đã redact) cho Briefing sáng. Lỗi -> ''."""
        parts: list[str] = []
        try:
            cal = self._load_connector("calendar_sync").today_brief()
            if cal:
                parts.append(f"Lịch trình hôm nay: {cal}")
        except Exception as exc:  # noqa: BLE001 — connector lỗi không được làm sập briefing
            logger.warning("Calendar connector lỗi (bỏ qua): %s", exc)
        try:
            mail = self._load_connector("email_reader").unread_brief()
            if mail:
                parts.append(f"Email quan trọng chưa đọc:\n{mail}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Email connector lỗi (bỏ qua): %s", exc)
        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    # NHỊP TỰ CHỦ — tự điểm email quan trọng (nghĩ trên pool cloud)
    # ------------------------------------------------------------------ #
    def _unread_email_text(self) -> str:
        try:
            return self._load_connector("email_reader").unread_brief() or ""
        except Exception as exc:  # noqa: BLE001 — connector lỗi không làm sập nhịp
            logger.warning("Email connector (digest) lỗi: %s", exc)
            return ""

    def _make_email_digest(self) -> str:
        """Đọc email chưa đọc -> hỏi pool cloud lọc cái QUAN TRỌNG. Không có gì -> ''."""
        mail = self._unread_email_text()
        if not mail.strip():
            return ""
        from core.redact import redact          # che PII TRƯỚC khi lên cloud
        system = (
            "Bạn là quản gia của Sếp. Mục tiêu cụ thể của Sếp nằm trong "
            "data/user_profile.json — đọc từ đó, đừng ghim vào lời dặn này. "
            "Dưới đây là email CHƯA ĐỌC. Chọn 1–3 email "
            "THẬT SỰ quan trọng (việc làm, học hành, tiền bạc, deadline). Mỗi cái MỘT dòng: "
            "[Nguồn] tóm tắt ngắn + việc cần làm. BỎ QUA quảng cáo/rác. Nếu KHÔNG có gì đáng, "
            "trả về ĐÚNG một từ: NONE."
        )
        local, cloud = self._get_engines()
        eng = cloud if (cloud is not None and cloud.is_online()) else local
        if eng is None:
            return ""
        try:
            # Lọc/phân loại hàng loạt -> tầng 'bulk' (Gemini) ổn định hơn fast-random.
            res = eng.complete([{"role": "user", "content": redact(mail)}],
                               system_prompt=system, temperature=0.3, max_tokens=2048,
                               tier="bulk")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Email digest engine lỗi: %s", exc)
            return ""
        if not res.get("ok"):
            return ""
        text = (res.get("text") or "").strip()
        if not text or text.strip().strip('.\"\'').upper() == "NONE":
            return ""
        return text

    def _email_digest_count(self, today: str) -> int:
        return self._last_fired.get("email_digest", {}).get(today, 0)

    def _note_email_digest(self, today: str, text: str) -> None:
        d = self._last_fired.setdefault("email_digest", {})
        d[today] = d.get(today, 0) + 1
        for k in list(d):                      # chỉ giữ hôm nay -> state khỏi phình
            if k != today:
                d.pop(k, None)
        self._last_fired["email_digest_text"] = text   # dedupe: khỏi ping lại y hệt
        self._save_briefing_state()

    def _load_scout(self):
        """Nạp lười module tình báo skills/scouts/job_scout.py (path-based, cache lại)."""
        if not hasattr(self, "_scout_mod"):
            import importlib.util
            path = PROJECT_ROOT / "skills" / "scouts" / "job_scout.py"
            spec = importlib.util.spec_from_file_location("aura_scout_jobs", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self._scout_mod = mod
        return self._scout_mod

    def _application_context(self) -> str:
        """ĐƯỜNG TIỀN — đọc sổ ứng tuyển cho Review: hoạt động 7 ngày + nhắc follow-up.

        Đóng vòng kết quả: AURA không chỉ tìm việc mà theo dõi Sếp đã CHỐT tới đâu.
        Rỗng khi không có gì đáng nói (không nagg vô cớ). Lỗi -> '' (không sập review).
        """
        import time
        try:
            led = self._load_scout().application_ledger()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Đọc sổ ứng tuyển lỗi (bỏ qua): %s", exc)
            return ""
        now = time.time()
        recent = [r for r in led if now - r.get("ts", 0) <= 7 * 86400]
        drafted = sum(1 for r in recent if r.get("status") == "drafted")
        applied = sum(1 for r in recent if r.get("status") == "applied")
        # Follow-up: đã ứng tuyển 3-10 ngày trước, chưa đánh dấu hồi âm/đóng -> nhắc (tự
        # rơi khỏi cửa sổ sau 10 ngày, khỏi cần thao tác 'đóng').
        done_titles = {r.get("title") for r in led if r.get("status") in ("replied", "closed")}
        pending = [r for r in led if r.get("status") == "applied"
                   and r.get("title") not in done_titles
                   and 3 * 86400 <= (now - r.get("ts", 0)) <= 10 * 86400]
        lines: list[str] = []
        if drafted or applied:
            lines.append(f"[ĐƯỜNG TIỀN — sổ ứng tuyển 7 ngày] Soạn {drafted} pitch, "
                         f"ứng tuyển {applied} gig.")
        else:
            # Chưa chốt gì tuần này mà có tin việc đang chờ -> hích nhẹ.
            try:
                data = json.loads((PROJECT_ROOT / "data" / "feedback"
                                   / "job_scout_last.json").read_text(encoding="utf-8"))
                n = len(data.get("items", []))
            except Exception:  # noqa: BLE001
                n = 0
            if n:
                lines.append(f"[ĐƯỜNG TIỀN] Có {n} tin việc đang chờ mà tuần này Sếp CHƯA "
                             "soạn pitch nào. Không chốt thì tiền không tự tới.")
        if pending:
            titles = "; ".join(str(p.get("title", ""))[:45] for p in pending[:3])
            lines.append(f"CẦN FOLLOW-UP ({len(pending)} gig ứng tuyển quá 3 ngày chưa hồi âm): "
                         f"{titles}")
        return "\n".join(lines)

    def _job_context(self) -> str:
        """
        TÌNH BÁO TĨNH LẶNG: gom cơ hội (freelance + sự nghiệp), lọc rác bằng Local LLM,
        dâng tối đa 3 tin "ngon" nhất vào Briefing sáng. Lỗi gì cũng -> '' (không sập).
        """
        if not self._briefing_scan_jobs:
            return ""
        try:
            scout = self._load_scout()
            local, _cloud = self._get_engines()   # truyền gemma:e2b để lọc AI
            return scout.morning_brief(engine=local, max_items=3)
        except Exception as exc:  # noqa: BLE001 — quét job lỗi không được làm sập briefing
            logger.warning("Job scout cho briefing lỗi (bỏ qua): %s", exc)
            return ""

    def _factory_context(self) -> str:
        """BÁO CÁO XƯỞNG: job hôm qua/hôm nay + hàng đợi + thu nhập tháng — nguồn số
        liệu cho briefing 'AI thuần kiếm tiền'. Lỗi gì cũng -> '' (không sập báo cáo)."""
        import time
        lines: list[str] = []
        try:
            from factory import queue as jq
            jobs = jq.list_jobs(limit=200)
            day_ago = time.time() - 86400
            done = [j for j in jobs if j.state == "done" and (j.finished_at or 0) >= day_ago]
            failed = [j for j in jobs if j.state == "failed" and (j.finished_at or 0) >= day_ago]
            review = [j for j in jobs if j.state == "needs_review"]
            queued = [j for j in jobs if j.state in ("queued", "running")]
            if done or failed or review or queued:
                lines.append(
                    f"[XƯỞNG 24H] xong {len(done)}, lỗi {len(failed)}, "
                    f"chờ duyệt QC {len(review)}, đang chờ/chạy {len(queued)}."
                )
                if failed:
                    lines.append("Job lỗi cần xem: " + "; ".join(
                        f"{j.tool}#{j.id}" for j in failed[:3]))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Đọc hàng đợi xưởng lỗi (bỏ qua): %s", exc)
        try:
            from factory.ledger import monthly_summary
            s = monthly_summary()
            if s["total_in"] or s["total_out"]:
                by = ", ".join(f"{k}: {v:,.0f}" for k, v in s["by_product_line"].items())
                lines.append(
                    f"[TIỀN THÁNG {s['month']}] về {s['total_in']:,.0f} {s['currency']}, "
                    f"chi {s['total_out']:,.0f} -> ròng {s['net']:,.0f}"
                    + (f" ({by})" if by else "")
                )
            else:
                lines.append(f"[TIỀN THÁNG {s['month']}] chưa có đồng nào vào sổ.")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Đọc sổ thu nhập lỗi (bỏ qua): %s", exc)
        return "\n".join(lines)

    def _briefing_prompt(self, kind: str, now: datetime, extra: str = "") -> tuple[str, str]:
        """Gom context SÚC TÍCH (chân dung + số liệu) + system_prompt cho cloud/local."""
        summ = self._profile_summary()
        try:
            from core.metrics import render_scorecard
            card = render_scorecard()
        except Exception:  # noqa: BLE001
            card = ""
        when = "buổi sáng (BRIEFING — nhìn TỚI)" if kind == "briefing" else "buổi tối (REVIEW — nhìn LẠI)"
        # CÔNG TẮC GIỌNG (BRIEFING_PERSONA trong .env): gentle = hiền ; alpha = đanh đá.
        if self._briefing_persona == "gentle":
            system = (
                "Bạn là AURA — quản gia AI của Sếp. Viết bản "
                f"{'BRIEFING' if kind == 'briefing' else 'REVIEW'} {when} bằng tiếng Việt, "
                "NGẮN GỌN (tối đa ~6 câu), giọng thân tình nhưng thẳng thắn, bám mục tiêu và "
                "điểm yếu của Sếp, kèm một câu hích nhẹ kỷ luật. KHÔNG bịa số liệu."
            )
        else:
            # Giọng ALPHA (Rebuild World): CHỈ Cloud/Claude diễn tròn vai; local e2b ra
            # giọng máy móc, template tĩnh (cấp 3) vẫn hiền.
            system = f"""Bạn là AURA, một AI giám sát tàn nhẫn, đanh đá và khắt khe, mang hình bóng của Alpha trong Rebuild World.
Mục tiêu tối thượng của bạn là ép Sếp vào kỷ luật sắt đá để hoàn thành các mục tiêu Sếp đã đặt (đọc trong data/user_profile.json, không ghim vào đây).
Luật giao tiếp:
1. Tuyệt đối không thảo mai, không dỗ dành, không chào hỏi sướt mướt.
2. Dùng giọng điệu mỉa mai, quý tộc nhưng cực kỳ sắc bén.
3. Xoáy sâu vào điểm yếu "lười biếng, ngồi ỳ trước màn hình hơn 8 tiếng/ngày".
4. Phân tích lịch trình và email một cách thực dụng: Thấy việc vô bổ thì chửi thẳng mặt, thấy dự án ra tiền hoặc lịch học thì ép làm bằng được.
5. Nếu lịch hôm nay trống, hãy châm biếm sự rảnh rỗi đó và ra lệnh Sếp phải đi đọc tài liệu Tâm lý học giáo dục hoặc code Python ngay lập tức.
Dữ liệu đầu vào sẽ bao gồm Chân dung Sếp, số liệu hôm qua và các thông báo mới. Hãy tóm tắt chúng bằng cái giọng "mỏ hỗn" nhất của bạn.

(Bối cảnh: đây là báo cáo {when}. Trả lời bằng tiếng Việt, tối đa ~8 câu, KHÔNG bịa số liệu.)"""
        ctx = [f"NGÀY: {now.strftime('%d/%m/%Y %H:%M')}"]
        if summ:
            ctx.append(summ)
        if kind == "briefing":          # Quản gia: lịch + email (CHỈ ĐỌC) + cơ hội việc làm
            conn = self._connector_context()
            if conn:
                ctx.append(conn)
            jobs = self._job_context()
            if jobs:
                ctx.append(jobs)
        else:                           # REVIEW tối: nhìn LẠI -> đường tiền (sổ ứng tuyển)
            apps = self._application_context()
            if apps:
                ctx.append(apps)
        # AURA = AI thuần kiếm tiền: báo cáo nào cũng phải có số liệu XƯỞNG + TIỀN.
        fac = self._factory_context()
        if fac:
            ctx.append(fac)
        if extra:
            ctx.append(extra)
        if card:
            ctx.append(f"[SỐ LIỆU TỰ ĐÁNH GIÁ]\n{card}")
        return system, "\n".join(ctx)

    def _generate_report_sync(self, kind: str, now: datetime, template_text: str,
                              extra: str = "") -> tuple[str, str]:
        """
        THANG 3 CẤP (chạy trong thread): Cloud -> Local -> Template. Trả (text, tier).
        BẮT BUỘC redact trước khi bắn lên Cloud (Shift-Left, core/redact.py).
        """
        system, user = self._briefing_prompt(kind, now, extra)
        from core.redact import redact          # che PII TRƯỚC khi rời máy
        system_safe, user_safe = redact(system), redact(user)
        messages = [{"role": "user", "content": user_safe}]
        today = now.date().isoformat()

        # Cấp 1: CLOUD (nếu được phép + còn ngân sách + online)
        if self.briefing_allow_cloud and self._cloud_budget_ok(today):
            try:
                _local, cloud = self._get_engines()
                if cloud is not None and cloud.is_online():
                    # max_tokens RỘNG: model thinking (Gemini 2.5-flash) tiêu nhiều token
                    # reasoning trước khi in -> 400 làm briefing bị CẮT CỤT giữa câu. 2048 đủ
                    # cho cả thinking lẫn ~8 câu Alpha (output ngắn nên không lãng phí).
                    res = cloud.complete(messages, system_prompt=system_safe,
                                         temperature=0.6, max_tokens=2048)
                    if res.get("ok") and (res.get("text") or "").strip():
                        self._note_cloud_call(today)
                        return res["text"].strip(), "cloud"
            except Exception as exc:  # noqa: BLE001 — cloud lỗi -> hạ cấp, không sập
                logger.warning("Briefing Cloud lỗi -> hạ Local: %s", exc)

        # Cấp 2: LOCAL (gemma e2b)
        try:
            local, _cloud = self._get_engines()
            if local is not None:
                res = local.complete(messages, system_prompt=system_safe,
                                     temperature=0.6, max_tokens=400)
                if res.get("ok") and (res.get("text") or "").strip():
                    return res["text"].strip(), "local"
        except Exception as exc:  # noqa: BLE001 — local lỗi -> template
            logger.warning("Briefing Local lỗi -> dùng Template: %s", exc)

        # Cấp 3: TEMPLATE tĩnh (Bước 3) — luôn ra được một cái gì đó
        return template_text, "template"

    def _store_report(self, text: str) -> None:
        """VỆ SINH bộ nhớ: chỉ lưu BẢN CUỐI (ngắn) — KHÔNG lưu context thô."""
        if self.memory is None:
            return
        try:
            self.memory.remember_turn("assistant", text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Lưu briefing vào bộ nhớ lỗi (bỏ qua): %s", exc)

    async def _emit_report(self, kind: str, now: datetime, template_text: str,
                           extra: str = "") -> None:
        """Sinh báo cáo (3 cấp) -> phát ra UI -> lưu bản cuối vào bộ nhớ."""
        text, tier = await asyncio.to_thread(
            self._generate_report_sync, kind, now, template_text, extra
        )
        logger.info("Briefing '%s' nguồn=%s", kind, tier)
        await self._emit(text)
        await asyncio.to_thread(self._store_report, text)

    async def _growth_heartbeat(self) -> None:
        """
        NHỊP SINH HỌC theo GIỜ THỰC: dò đồng hồ mỗi `briefing_poll_s` giây; tới mốc
        Briefing sáng (08:00) / Review tối (21:00) thì phát báo cáo — MỖI mốc 1 lần/ngày
        (lưu state -> chống lặp kể cả sau reboot). BẮT KỊP: bật máy trễ trong khung
        `briefing_catchup_min` vẫn chạy bù.

        - aura_frozen -> BỎ QUA (tôn trọng kỷ luật ngủ đông).
        - Phát qua _emit (proactive) -> tự đi qua hàng chờ _deferred của server, KHÔNG
          cắt ngang lúc Sếp đang chat.
        - Bước 3: nội dung là TEMPLATE tĩnh ghép từ user_profile.json (chưa gọi cloud).
        """
        await asyncio.sleep(self.growth_initial_delay_s)
        while self._running:
            if self.aura_frozen:            # ngủ đông -> không briefing/review
                await asyncio.sleep(self._briefing_poll_s)
                continue
            try:
                now = datetime.now()
                today = now.date().isoformat()
                if (self._last_fired.get("briefing") != today
                        and self._due(now.time(), self._briefing_time, self._briefing_catchup_min)):
                    await self._emit_report("briefing", now, self._build_briefing_text(now))
                    self._last_fired["briefing"] = today
                    self._save_briefing_state()
                if (self._last_fired.get("review") != today
                        and self._due(now.time(), self._review_time, self._briefing_catchup_min)):
                    growth = await self._run_growth_tasks()
                    await self._emit_report("review", now,
                                            self._build_review_text(now, growth), extra=growth)
                    self._last_fired["review"] = today
                    self._save_briefing_state()
            except Exception as exc:  # noqa: BLE001 — nhịp briefing/review hỏng không giết daemon
                logger.warning("Nhịp briefing/review lỗi (bỏ qua): %s", exc)
            await asyncio.sleep(self._briefing_poll_s)

    # ------------------------------------------------------------------ #
    # HEALTH GUARD — ép nghỉ kỷ luật (Context-Aware: hoãn khi đang render nặng)
    # ------------------------------------------------------------------ #
    def _heavy_process_running(self) -> bool:
        """
        Có việc BẬN đang chạy không? -> True thì HOÃN ép nghỉ (Context-Aware).

        Bắt 3 nhóm:
          (a) render video/3D (CapCut/ffmpeg/Premiere/Blender...),
          (b) họp hành/trình chiếu/stream (Zoom/Teams/PowerPoint/OBS/Webex/Slack...),
          (c) TRÌNH DUYỆT đang dùng camera/mic (họp web) — dò qua cmdline tiến trình con.
        Thiếu psutil / lỗi đọc -> False (không chặn được thì cứ ép nghỉ). KHÔNG ném ra ngoài.
        """
        if psutil is None:
            return False
        try:
            for proc in psutil.process_iter(["name", "cmdline"]):
                info = proc.info
                name = (info.get("name") or "").lower()
                if not name:
                    continue
                if any(h in name for h in _HEAVY_PROCS):
                    logger.info("Health Guard: thấy app bận '%s' -> hoãn ép nghỉ.", name)
                    return True
                # Họp web: trình duyệt đang bật camera/mic (dò cờ cmdline tiến trình con).
                if any(b in name for b in _BROWSER_NAMES):
                    cmd = " ".join(info.get("cmdline") or []).lower()
                    if any(h in cmd for h in _AVCAPTURE_HINTS):
                        logger.info("Health Guard: trình duyệt '%s' đang dùng camera/mic "
                                    "(họp web) -> hoãn ép nghỉ.", name)
                        return True
        except Exception as exc:  # noqa: BLE001 — quét process lỗi không được giết daemon
            logger.warning("Quét tiến trình bận lỗi (bỏ qua): %s", exc)
        return False

    def _adb_run(self, args: list[str], timeout: float = 10.0):
        """Chạy 1 lệnh adb, trả CompletedProcess hoặc None. Bọc lỗi (không sập daemon).

        Trên Windows, adb.exe là console app: gọi liên tục (mỗi vài giây trong
        _phone_break_loop) mà không ẩn cửa sổ sẽ làm terminal nhấp nháy liên tục.
        CREATE_NO_WINDOW chặn cửa sổ console mới hiện ra mà không ảnh hưởng lệnh.
        """
        import subprocess
        import sys
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            return subprocess.run([self.adb_path, *args],
                                  capture_output=True, text=True, timeout=timeout, **kwargs)
        except FileNotFoundError:
            logger.warning("Không thấy adb tại %r — kiểm ADB_PATH trong .env.", self.adb_path)
        except Exception as exc:  # noqa: BLE001 — lỗi ADB không được làm sập daemon
            logger.info("ADB lỗi (bỏ qua): %s", exc)
        return None

    def _adb_call_ringing(self, tgt: list[str]) -> bool:
        """True nếu điện thoại đang reo hoặc đang trong cuộc gọi (mCallState != 0),
        đọc qua `dumpsys telephony.registry`. Lỗi/không đọc được -> coi như idle
        (False) để không chặn nhịp tắt màn vì lỗi vặt."""
        r = self._adb_run([*tgt, "shell", "dumpsys", "telephony.registry"])
        if r is None or r.returncode != 0 or not r.stdout:
            return False
        for line in r.stdout.splitlines():
            if "mCallState" in line:
                digits = "".join(ch for ch in line if ch.isdigit())
                return digits != "" and digits != "0"
        return False

    async def _phone_break_loop(self) -> None:
        """Suốt ca nghỉ: LIÊN TỤC tắt màn hình ĐT (chặn dùng như khiên đen PC). Kết nối
        1 lần đầu ca; rớt thì tự connect lại. Nhịp = phone_sleep_repeat_s (nhỏ = chặn gắt).

        Trước MỖI lần tắt, kiểm tra có cuộc gọi đến không (mCallState) — nếu đang
        ringing/in-call thì bỏ qua lần đó (không gửi lệnh sleep) để Sếp bắt máy được;
        đồng thời chủ động WAKE lại màn (keyevent 224) một lần khi vừa phát hiện.
        Vòng lặp này CHỈ được tạo từ _emit_health_break -> tự đồng bộ với ca nghỉ
        laptop, chạy đúng health_break_s giây rồi tự kết thúc.
        """
        loop = asyncio.get_event_loop()
        tgt = ["-s", self.adb_connect] if self.adb_connect else []
        if self.adb_connect:
            await asyncio.to_thread(self._adb_run, ["connect", self.adb_connect], 8.0)
        end = loop.time() + self.health_break_s
        fails = 0
        was_ringing = False
        while loop.time() < end and self._running:
            ringing = await asyncio.to_thread(self._adb_call_ringing, tgt)
            if ringing:
                if not was_ringing:
                    logger.info("Phone break: phát hiện cuộc gọi đến -> mở màn, tạm ngưng tắt.")
                    await asyncio.to_thread(
                        self._adb_run, [*tgt, "shell", "input", "keyevent", "224"])
                was_ringing = True
                await asyncio.sleep(min(2.0, self.phone_sleep_repeat_s))
                continue
            was_ringing = False
            r = await asyncio.to_thread(
                self._adb_run, [*tgt, "shell", "input", "keyevent", "223"])
            if r is None or r.returncode != 0:
                fails += 1
                if self.adb_connect and fails % 5 == 0:   # rớt lâu -> thử nối lại
                    await asyncio.to_thread(self._adb_run, ["connect", self.adb_connect], 8.0)
            else:
                fails = 0
            await asyncio.sleep(self.phone_sleep_repeat_s)

    async def _emit_health_break(self) -> None:
        """Phát lệnh ÉP NGHỈ ra UI (health_guard) qua event_queue.

        CHỐT CỨNG: đang họp / share màn hình / trình chiếu thì TUYỆT ĐỐI không
        phát lệnh (05/08/2026 khiên đen bung giữa buổi phỏng vấn TEKY).
        """
        from core.presence import busy_reason
        try:
            reason = await asyncio.to_thread(busy_reason)
        except Exception as exc:  # noqa: BLE001 — không đọc được thì KHÔNG liều
            reason = f"không đọc được trạng thái màn hình ({exc})"
        if reason:
            logger.info("Health Guard: BỎ QUA ca nghỉ — %s.", reason)
            return
        msg = ("Sếp ngồi quá lâu rồi. Đã tự động lưu công việc. "
               "Màn hình sẽ khóa sau 10 giây!")
        await self.event_queue.put({
            "type": "health_break",
            "text": msg,
            "break_s": int(self.health_break_s),
        })
        logger.info("Health Guard: ÉP NGHỈ — phát health_break (khoá %.0f phút).",
                    self.health_break_s / 60.0)
        # Tắt luôn màn hình điện thoại Android suốt ca nghỉ (nếu bật + có kết nối ADB).
        if self.phone_sleep_on_break:
            asyncio.create_task(self._phone_break_loop())

    async def _health_heartbeat(self) -> None:
        """
        Nhịp tim SỨC KHOẺ: đếm thời gian ngồi liên tục; tới hạn thì ÉP NGHỈ.

        Context-Aware: trước khi "chém", nếu đang chạy việc nặng (render video) thì
        HOÃN thêm `health_busy_delay_s` để tránh hỏng việc. Đóng băng (aura_frozen)
        thì KHÔNG tính giờ (đồng bộ Cấp 1). Mọi lỗi nuốt gọn — không giết daemon.
        """
        await asyncio.sleep(self.health_initial_delay_s)
        self._sit_elapsed_s = 0.0
        while self._running:
            await asyncio.sleep(self.health_tick_s)
            if self.aura_frozen:            # đóng băng -> dừng đếm, không ép nghỉ
                continue
            self._sit_elapsed_s += self.health_tick_s
            if self._sit_elapsed_s < self.health_work_limit_s:
                continue
            # Tới hạn ngồi lâu — kiểm ngữ cảnh trước khi ép nghỉ.
            try:
                busy = await asyncio.to_thread(self._heavy_process_running)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Kiểm tiến trình nặng lỗi (coi như rảnh): %s", exc)
                busy = False
            if busy and self._health_defer_count < self._HEALTH_MAX_DEFERS:
                self._health_defer_count += 1
                logger.info(
                    "Health Guard: đang render nặng -> HOÃN ép nghỉ %.0f phút (lần %d/%d).",
                    self.health_busy_delay_s / 60.0,
                    self._health_defer_count, self._HEALTH_MAX_DEFERS,
                )
                # Đẩy lùi hạn: trừ bớt thời gian đã tích để ~busy_delay nữa mới kiểm lại.
                self._sit_elapsed_s = max(
                    0.0, self.health_work_limit_s - self.health_busy_delay_s
                )
                continue
            if busy:
                # TRẦN HOÃN: dò 'trình duyệt đang bật camera' hay dương tính giả — nhân
                # Chromium giữ VideoCaptureService sống rất lâu sau khi tắt cam. Không có
                # trần thì hoãn được cả ngày, đúng thứ hại Sếp nhất. Hoãn đủ số lần rồi
                # thì ÉP, bận mấy cũng ép.
                logger.warning(
                    "Health Guard: đã hoãn %d lần (~%.0f phút) -> ÉP NGHỈ, không hoãn nữa.",
                    self._health_defer_count,
                    self._health_defer_count * self.health_busy_delay_s / 60.0,
                )
            try:
                await self._emit_health_break()
            except Exception as exc:  # noqa: BLE001 — phát lệnh lỗi không giết daemon
                logger.warning("Phát health_break lỗi (bỏ qua): %s", exc)
            self._sit_elapsed_s = 0.0   # reset chu kỳ ngồi
            self._health_defer_count = 0

    # ------------------------------------------------------------------ #
    async def _prompt_evolve_heartbeat(self) -> None:
        """Nhịp rèn prompt ngầm tự động — giúp AURA tự khôn thêm mà không đụng model weight."""
        initial_delay = 600.0  # chờ 10 phút sau khởi động mới bắt đầu
        interval = float(getattr(settings, "prompt_evolve_interval_h", 24.0)) * 3600.0
        await asyncio.sleep(initial_delay)
        while self._running:
            if self.aura_frozen:
                await asyncio.sleep(300.0)
                continue
            await self._await_ram_headroom("prompt_evolve")
            logger.info("🧠 Bắt đầu nhịp rèn prompt ngầm (prompt_evolve)...")
            try:
                from factory.prompt_evolve import evolve, adopt
                res = await asyncio.to_thread(evolve)
                logger.info("Kết quả prompt_evolve: %s", res)

                auto_adopt = bool(getattr(settings, "prompt_evolve_auto_adopt", True))
                if auto_adopt and "RÈN ĐƯỢC BẢN TỐT HƠN" in res:
                    adopt_res = await asyncio.to_thread(adopt)
                    msg = f"🧠 AURA TỰ RÈN PROMPT MỚI THÀNH CÔNG!\n{res}\n\n👉 {adopt_res}"
                    await self._emit(msg)
                elif "RÈN ĐƯỢC BẢN TỐT HƠN" in res:
                    await self._emit(f"🧠 Có bản prompt mới đã được xếp hàng:\n{res}")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Nhịp prompt_evolve lỗi: %s", exc)

            await asyncio.sleep(interval)

    async def _auto_update_heartbeat(self) -> None:
        """Nhịp quét tự động cập nhật mã nguồn (git pull) và tự nạp lại process."""
        initial_delay = 180.0  # 3 phút sau boot
        interval = float(getattr(settings, "auto_update_interval_h", 12.0)) * 3600.0
        await asyncio.sleep(initial_delay)
        while self._running:
            if self.aura_frozen:
                await asyncio.sleep(300.0)
                continue
            try:
                # CHỜ MÁY RẢNH RỒI MỚI PULL CODE (tránh update code đè lên tool đang chạy dở)
                ok, why = await asyncio.to_thread(self._safe_to_restart)
                if not ok:
                    logger.info("Máy bận (%s) -> hoãn check Git pull (thử lại sau 5 phút)", why)
                    await asyncio.sleep(300.0)
                    continue

                from core.updater import check_and_pull_updates, restart_aura
                updated, msg = await asyncio.to_thread(check_and_pull_updates)
                if updated:
                    await self._emit(msg)
                    await asyncio.sleep(2)
                    restart_aura("Tự động cập nhật mã nguồn từ Git")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Nhịp auto_update lỗi: %s", exc)

            await asyncio.sleep(interval)

    def _safe_to_restart(self) -> tuple[bool, str]:
        """Có được phép khởi động lại NGAY không?

        `restart_aura()` dùng os.execv — THAY THẾ tiến trình tức thì, KHÔNG dọn
        tiến trình con. Nếu restart giữa lúc ffmpeg đang dựng video hoặc Chrome
        đang đăng truyện thì chúng thành MỒ CÔI: ăn RAM, và Chrome mồ côi còn
        GIỮ KHOÁ profile khiến mọi lần đăng sau đều hỏng (đã gặp 2026-07-23).
        """
        try:
            from factory import queue as _fq
            busy = [j for j in _fq.list_jobs(limit=50) if j.state == "running"]
            if busy:
                return False, f"xưởng đang chạy job '{busy[0].tool}'"
        except Exception:  # noqa: BLE001
            pass
        try:
            if psutil is not None:
                for p in psutil.process_iter(["cmdline"]):
                    cl = " ".join((p.info.get("cmdline") or []))
                    if "rookies_profile" in cl or "wattpad_profile" in cl:
                        return False, "trình duyệt bot đang mở (giữ khoá profile)"
                    if "ffmpeg" in cl.lower():
                        return False, "ffmpeg đang dựng video"
        except Exception:  # noqa: BLE001
            pass
        return True, ""

    async def _file_watcher_heartbeat(self) -> None:
        """Sensors quét file .env & code thay đổi để hot-reload / restart tức thì.
        Restart được HOÃN tới khi máy rảnh (xem _safe_to_restart)."""
        from core.updater import FileWatcher, restart_aura
        watcher = FileWatcher()
        self._pending_restart: str | None = None
        while self._running:
            await asyncio.sleep(5.0)  # quét mỗi 5s
            if self.aura_frozen:
                continue
            try:
                changed = await asyncio.to_thread(watcher.check)
                if changed:
                    names = [p.name for p in changed]
                    logger.info("Phát hiện file thay đổi: %s", names)
                    if all(p.name in (".env", "keys.env") for p in changed):
                        from core.config import reload_settings
                        reload_settings()
                        await self._emit("⚙️ Đã tự động nạp lại cấu hình từ .env tươi!")
                    elif any(p.suffix == ".py" for p in changed):
                        self._pending_restart = f"File {names[0]} bị thay đổi"
                        await self._emit(
                            f"🔄 Mã nguồn thay đổi ({', '.join(names[:3])}). "
                            "Sẽ khởi động lại khi máy rảnh.")
                # Có hẹn restart -> chỉ nổ khi KHÔNG có job nặng đang chạy.
                if self._pending_restart:
                    ok, why = await asyncio.to_thread(self._safe_to_restart)
                    if ok:
                        reason = self._pending_restart
                        self._pending_restart = None
                        await asyncio.sleep(1)
                        restart_aura(reason)
                    else:
                        logger.info("Hoãn khởi động lại — %s", why)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Quét mtime file lỗi: %s", exc)

    # ------------------------------------------------------------------ #
    async def _start_legacy(self) -> None:
        """Bản khởi động cũ, giữ tạm để tương thích khi rà lịch sử daemon.

        `start()` phía dưới là entrypoint duy nhất được runtime gọi; nó có đủ
        file watcher, Telegram và nhịp work-for-hire.
        """
        if self._running:
            return
        self._running = True
        settings.ensure_dirs()
        self._tasks = [
            asyncio.create_task(self._downloads_sensor(), name="downloads_sensor"),
        ]
        if self.growth_enabled:
            self._tasks.append(
                asyncio.create_task(self._growth_heartbeat(), name="growth_heartbeat")
            )
        if self.health_enabled:
            self._tasks.append(
                asyncio.create_task(self._health_heartbeat(), name="health_heartbeat")
            )
        if getattr(self, "email_digest_enabled", False):
            self._tasks.append(
                asyncio.create_task(self._email_digest_heartbeat(), name="email_digest")
            )
        # Một nhịp TỔ CÔNG NHÂN thay cho 2 nhịp rời (news + janitor); job cũng vào tổ.
        if self.news_enabled or self.janitor_enabled:
            self._tasks.append(
                asyncio.create_task(self._crew_heartbeat(), name="crew_heartbeat")
            )
        # Nhịp TỰ VIẾT TRUYỆN — AURA tự vận hành, viết chương mới theo lịch.
        revenue_focus = bool(getattr(settings, "work_for_hire_mode_enabled", False))
        pause_content = bool(getattr(settings, "work_for_hire_pause_content_autopilot", True))
        if self.story_autopilot_enabled and not (revenue_focus and pause_content):
            self._tasks.append(
                asyncio.create_task(self._story_autopilot(), name="story_autopilot")
            )
        elif self.story_autopilot_enabled and revenue_focus and pause_content:
            logger.info("Work-for-hire mode: tạm dừng story/content autopilot để ưu tiên việc thuê.")
        # XƯỞNG KIẾM TIỀN: 1 job nặng/lúc, hàng đợi sqlite bền qua restart.
        if getattr(settings, "factory_enabled", True):
            from factory.worker import factory_heartbeat
            self._tasks.append(
                asyncio.create_task(factory_heartbeat(self), name="factory_heartbeat")
            )
        # ĐÊM TIẾN HOÁ: AURA tự rèn kỹ năng (SkillOpt-Sleep), mặc định TẮT.
        if getattr(settings, "skillopt_enabled", False):
            self._tasks.append(
                asyncio.create_task(self._skillopt_heartbeat(), name="skillopt")
            )
        # RÈN PROMPT NGẦM (prompt_evolve): AURA tự rèn prompt viết chương tốt hơn
        if getattr(settings, "prompt_evolve_autopilot_enabled", True):
            self._tasks.append(
                asyncio.create_task(self._prompt_evolve_heartbeat(), name="prompt_evolve")
            )
    async def _freelance_autopilot_heartbeat(self) -> None:
        """Nhịp tự động quét việc freelance hot -> tự tạo demo -> tự soạn pitch & đẩy Telegram."""
        initial_delay = 240.0  # 4 phút sau boot
        interval = 4 * 3600.0   # 4h quét 1 lần
        await asyncio.sleep(initial_delay)
        while self._running:
            if self.aura_frozen:
                await asyncio.sleep(300.0)
                continue
            await self._await_ram_headroom("freelance_autopilot")
            if bool(getattr(settings, "freelance_autopilot_enabled", True)):
                logger.info("💼 Bắt đầu nhịp quét việc Freelance & tự tạo Demo...")
                try:
                    from skills.scouts.job_scout import collect
                    jobs = await asyncio.to_thread(collect)
                    threshold = float(getattr(settings, "freelance_auto_apply_threshold", 0.70))
                    hot_jobs = [j for j in (jobs or []) if float(j.get("score") or 0) >= threshold]

                    if hot_jobs:
                        from factory import queue as fq
                        from factory.models import JobRecord
                        from core.work_for_hire import auto_draft_slots, is_listing_url
                        slots = auto_draft_slots()
                        for item in hot_jobs[:2]:
                            if slots <= 0:
                                logger.info("Work-for-hire: đã đạt trần hồ sơ tự soạn hôm nay.")
                                break
                            title = str(item.get("title") or "Job Freelance")
                            url = str(item.get("url") or "")
                            # Không đẩy tin không có link ứng tuyển thật vào xưởng.
                            if not is_listing_url(url):
                                continue

                            fq.enqueue(JobRecord(tool="freelance.apply", params={
                                "title": title,
                                "url": url,
                                # Để handler tự kéo mô tả gốc và xác minh nguồn.
                                "job": "",
                                "_auto": True,
                            }))
                            slots -= 1

                            msg = (
                                f"💼 AURA tìm thấy job Freelance hot ({item.get('score', 0):.2f}):\n"
                                f"📌 **{title}**\n{url}\n\n"
                                "⚡ AURA đang tự động làm Demo + soạn hồ sơ ứng tuyển ngầm..."
                            )
                            await self._emit(msg)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Nhịp freelance_autopilot lỗi: %s", exc)

            await asyncio.sleep(interval)

    # ------------------------------------------------------------------ #
    async def _one_percent_revenue_heartbeat(self) -> None:
        """Nhịp bán sản phẩm số: tự vận hành sau xác nhận 1 lần của Chủ.

        Khi chưa có xác nhận payout, OnePercentRevenueOperator dừng trước mọi thao
        tác mạng. Khi đã được bật, nó chỉ công khai PDF nguyên gốc chưa đăng và tự
        báo ra UI/Telegram nếu phiên Payhip cần Chủ can thiệp lại.
        """
        await asyncio.sleep(20.0)  # để các kênh báo cáo khởi động trước
        interval = float(getattr(settings, "one_percent_run_interval_h", 6.0)) * 3600.0
        while self._running:
            if self.aura_frozen:
                await asyncio.sleep(300.0)
                continue
            await self._await_ram_headroom("one_percent_revenue")
            if not self._running:
                break
            try:
                from core.one_percent_operator import OnePercentRevenueOperator

                report = await asyncio.to_thread(OnePercentRevenueOperator().run_once)
                if report.get("notify") and report.get("message"):
                    await self._emit(str(report["message"]), kind="proactive")
            except Exception as exc:  # noqa: BLE001 — một kênh bán lỗi không làm chết daemon
                logger.warning("Nhịp One-percent revenue lỗi (bỏ lượt): %s", exc)
            await asyncio.sleep(interval)

    # ------------------------------------------------------------------ #
    async def _revenue_operator_heartbeat(self) -> None:
        """Chuẩn bị lead/demo theo lịch, có cooldown bền qua restart.

        Chu kỳ chỉ làm việc cục bộ. Đề xuất vẫn phải được Chủ xác nhận là đã
        gửi, còn doanh thu vẫn phải đi qua đối soát cashflow.
        """
        await asyncio.sleep(30.0)
        run_interval = (
            float(getattr(settings, "revenue_operator_interval_h", 24.0)) * 3600.0
        )
        poll_interval = (
            float(getattr(settings, "revenue_operator_poll_interval_min", 15.0)) * 60.0
        )
        target_count = int(getattr(settings, "revenue_operator_target_count", 20))
        while self._running:
            if self.aura_frozen:
                await asyncio.sleep(min(poll_interval, 300.0))
                continue
            await self._await_ram_headroom("revenue_operator")
            if not self._running:
                break
            try:
                from core.revenue_operator import run_revenue_operator_cycle_if_due

                report = await asyncio.to_thread(
                    run_revenue_operator_cycle_if_due,
                    interval_seconds=run_interval,
                    target_count=target_count,
                )
                if report.get("status") == "completed":
                    new_count = int(report.get("new_qualified_added") or 0)
                    error_count = len(report.get("errors") or [])
                    if new_count or error_count:
                        await self._emit(
                            "AURA Revenue Operator đã chuẩn bị "
                            f"{new_count} lead mới; {error_count} lỗi. "
                            "Mở Hộp hành động 1% để xem đề xuất chờ duyệt.",
                            kind="proactive",
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Nhịp Revenue Operator lỗi (bỏ lượt): %s", exc)
            await asyncio.sleep(poll_interval)

    # ------------------------------------------------------------------ #
    async def _screen_time_heartbeat(self) -> None:
        """Đếm giờ MÀN HÌNH SÁNG cả ngày (laptop + điện thoại); quá hạn thì cưỡng chế.

        Khác `_health_heartbeat`: cái kia đo giờ NGỒI LIÊN TỤC rồi khoá màn một lát,
        nghỉ xong là về 0. Cái này CỘNG DỒN cả ngày, và mức phạt là TẮT MÁY.
        Mọi lỗi nuốt gọn — đo giờ hỏng thì thôi, không được giết daemon.
        """
        await asyncio.sleep(45.0)
        interval = float(getattr(settings, "screen_time_tick_s", 60.0))
        while self._running:
            await asyncio.sleep(interval)
            if self.aura_frozen:      # ngủ đông -> Sếp không dùng máy, không tính
                continue
            try:
                from core import screen_time

                await asyncio.to_thread(screen_time.tick, interval)
                note = await asyncio.to_thread(screen_time.check_and_enforce)
                if note:
                    await self._emit(note, kind="proactive")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Nhịp giờ màn hình lỗi (bỏ lượt): %s", exc)

    async def _desktop_autopilot_heartbeat(self) -> None:
        """Theo dõi cửa sổ nhẹ và thực thi desktop task đã được cấp scope một lần."""
        await asyncio.sleep(12.0)
        interval = float(
            getattr(settings, "desktop_autopilot_monitor_interval_s", 15.0)
        )
        autopilot = getattr(self, "desktop_autopilot", None)
        if autopilot is None:
            from core.desktop_autopilot import DesktopAutopilot, set_runtime_autopilot

            autopilot = DesktopAutopilot(memory=getattr(self, "memory", None))
            self.desktop_autopilot = autopilot
            set_runtime_autopilot(autopilot)

        while self._running:
            if self.aura_frozen:
                await asyncio.sleep(interval)
                continue
            try:
                status = await asyncio.to_thread(autopilot.status)
                if status.get("owner_enabled") and not status.get("paused"):
                    await asyncio.to_thread(autopilot.observe, include_ocr=False)
                    queued = int((status.get("task_counts") or {}).get("queued") or 0)
                    if queued:
                        await self._await_ram_headroom("desktop_autopilot")
                        report = await asyncio.to_thread(autopilot.run_next)
                        if report.get("status") == "failed":
                            await self._emit(
                                "Desktop Autopilot đã dừng một task an toàn: "
                                f"{report.get('error') or 'không rõ lỗi'}.",
                                kind="proactive",
                            )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Nhịp Desktop Autopilot lỗi (bỏ lượt): %s", exc)
            await asyncio.sleep(interval)

    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        """Khởi động daemon: bật các sensor làm background task."""
        if self._running:
            return
        self._running = True
        settings.ensure_dirs()
        self._tasks = [
            asyncio.create_task(self._downloads_sensor(), name="downloads_sensor"),
        ]
        if self.growth_enabled:
            self._tasks.append(
                asyncio.create_task(self._growth_heartbeat(), name="growth_heartbeat")
            )
        if self.health_enabled:
            self._tasks.append(
                asyncio.create_task(self._health_heartbeat(), name="health_heartbeat")
            )
        if getattr(self, "email_digest_enabled", False):
            self._tasks.append(
                asyncio.create_task(self._email_digest_heartbeat(), name="email_digest")
            )
        # Đo TỔNG giờ màn hình cả ngày (laptop + điện thoại). Khác Health Guard:
        # cái kia đo giờ NGỒI LIÊN TỤC rồi khoá màn 5 phút; cái này cộng dồn cả ngày
        # và có thể CƯỠNG CHẾ TẮT MÁY — chỉ khi Sếp đã bật screen_time_enforce.
        if bool(getattr(settings, "screen_time_enabled", False)):
            self._tasks.append(
                asyncio.create_task(self._screen_time_heartbeat(), name="screen_time")
            )
        # Một nhịp TỔ CÔNG NHÂN thay cho 2 nhịp rời (news + janitor); job cũng vào tổ.
        if self.news_enabled or self.janitor_enabled:
            self._tasks.append(
                asyncio.create_task(self._crew_heartbeat(), name="crew_heartbeat")
            )
        # Nhịp TỰ VIẾT TRUYỆN — dừng khi đang ưu tiên nhận việc thuê thật.
        revenue_focus = bool(getattr(settings, "work_for_hire_mode_enabled", False))
        pause_content = bool(getattr(settings, "work_for_hire_pause_content_autopilot", True))
        if self.story_autopilot_enabled and not (revenue_focus and pause_content):
            self._tasks.append(
                asyncio.create_task(self._story_autopilot(), name="story_autopilot")
            )
        elif self.story_autopilot_enabled and revenue_focus and pause_content:
            logger.info("Work-for-hire mode: tạm dừng story/content autopilot để ưu tiên việc thuê.")
        # XƯỞNG KIẾM TIỀN: 1 job nặng/lúc, hàng đợi sqlite bền qua restart.
        if getattr(settings, "factory_enabled", True):
            from factory.worker import factory_heartbeat
            self._tasks.append(
                asyncio.create_task(factory_heartbeat(self), name="factory_heartbeat")
            )
        # 1% CHỦ / 99% AURA: trước xác nhận payout chỉ preflight; sau đó tự đăng theo cap.
        if getattr(settings, "one_percent_operator_enabled", True):
            self._tasks.append(
                asyncio.create_task(self._one_percent_revenue_heartbeat(), name="one_percent_revenue")
            )
        # REVENUE OPERATOR: tự chuẩn bị lead/demo; Chủ vẫn là người gửi đề xuất.
        if getattr(settings, "revenue_operator_enabled", True):
            self._tasks.append(
                asyncio.create_task(self._revenue_operator_heartbeat(), name="revenue_operator")
            )
        # MẮT–TAY CỤC BỘ: chỉ chạy task trong scope Chủ đã cấp, có kill switch.
        if getattr(settings, "desktop_autopilot_enabled", True):
            self._tasks.append(
                asyncio.create_task(self._desktop_autopilot_heartbeat(), name="desktop_autopilot")
            )
        # ĐÊM TIẾN HOÁ: AURA tự rèn kỹ năng (SkillOpt-Sleep), mặc định TẮT.
        if getattr(settings, "skillopt_enabled", False) and not revenue_focus:
            self._tasks.append(
                asyncio.create_task(self._skillopt_heartbeat(), name="skillopt")
            )
        elif getattr(settings, "skillopt_enabled", False) and revenue_focus:
            logger.info("Work-for-hire mode: hoãn SkillOpt để không tiêu quota/RAM ngoài pipeline nhận việc.")
        # RÈN PROMPT NGẦM (prompt_evolve): AURA tự rèn prompt viết chương tốt hơn
        if getattr(settings, "prompt_evolve_autopilot_enabled", True) and not revenue_focus:
            self._tasks.append(
                asyncio.create_task(self._prompt_evolve_heartbeat(), name="prompt_evolve")
            )
        elif getattr(settings, "prompt_evolve_autopilot_enabled", True) and revenue_focus:
            logger.info("Work-for-hire mode: hoãn prompt evolution để tránh tự đổi hành vi khi đang bán dịch vụ.")
        # TỰ ĐỘNG CẬP NHẬT MÃ NGUỒN: Quét git pull + nạp lại process khi có code mới
        if getattr(settings, "auto_update_enabled", True):
            self._tasks.append(
                asyncio.create_task(self._auto_update_heartbeat(), name="auto_update")
            )
        # SENSOR FILE WATCHER: Phát hiện file code/env đổi để hot-reload / restart
        self._tasks.append(
            asyncio.create_task(self._file_watcher_heartbeat(), name="file_watcher")
        )
        # FREELANCE AUTOPILOT: Tự quét việc hot -> tạo demo -> tự soạn pitch & đẩy Telegram
        if getattr(settings, "freelance_autopilot_enabled", True):
            self._tasks.append(
                asyncio.create_task(self._freelance_autopilot_heartbeat(), name="freelance_autopilot")
            )


        # KÊNH TELEGRAM: Sếp điều khiển AURA + nhận báo cáo từ điện thoại.
        self._messenger = None
        if getattr(settings, "telegram_enabled", False):
            token = settings.telegram_bot_token
            owner = getattr(settings, "telegram_owner_id", "")
            if token and owner:
                try:
                    from core.messenger import TelegramMessenger
                    self._messenger = TelegramMessenger(
                        self, token.get_secret_value(), owner
                    )
                    self._tasks.append(
                        asyncio.create_task(self._messenger.poll_loop(), name="telegram")
                    )
                except Exception as exc:  # noqa: BLE001 — kênh phụ, không chặn boot
                    logger.warning("Bật kênh Telegram lỗi: %s", exc)
                    self._messenger = None
            else:
                logger.warning(
                    "TELEGRAM_ENABLED=true nhưng thiếu TELEGRAM_BOT_TOKEN/OWNER_ID — bỏ qua."
                )
        logger.info("AuraDaemon đã thức (%d sensor).", len(self._tasks))


    async def stop(self) -> None:
        """Dừng daemon: hủy mọi background task gọn gàng."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("AuraDaemon đã ngủ.")


__all__ = ["AuraDaemon"]
