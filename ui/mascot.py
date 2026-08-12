"""
ui/mascot.py
============
AURA Mascot — sự hiện diện vật lý của AURA trên Desktop (kiểu Shimeji), dựng bằng PyQt5.

Cửa sổ "tàng hình": không viền, luôn nổi trên cùng, nền trong suốt hoàn toàn -> chỉ thấy
nhân vật, không thấy khung. Hai trạng thái khuôn mặt: idle <-> talk (PNG tĩnh hoặc GIF động).
Kéo–thả tự do. Tự nối WebSocket tới AURA: khi model BẮT ĐẦU generate -> talk, KẾT THÚC -> idle.

Giao tiếp 2 chiều:
  - DOUBLE-CLICK vào mascot -> hiện/ẩn khung gõ; Enter -> gửi {"type":"chat"} tới AURA, tự xoá trắng.
  - Khi AURA trả lời (type "response"/"error") hoặc tự mở lời (type "proactive"), văn bản hiện
    lên BONG BÓNG THOẠI nổi trên đầu mascot, tự biến mất sau 15s nếu không có tin mới.

Chạy:
    python -m ui.mascot              # mở mascot (cửa sổ riêng)
    # cần AURA server chạy nền để chat: python main.py

Ảnh nhân vật: đặt vào assets/mascot/ (ưu tiên) hoặc assets/avatar/
    idle.png / idle.gif   — lúc rảnh
    talk.png / talk.gif   — lúc đang nhả chữ
Thiếu ảnh -> hiện một huy hiệu placeholder phẳng (KHÔNG vẽ chibi), chỉ để mascot
vẫn hiện & kéo được; thả 2 file PNG chất lượng cao vào là thay ngay.

PyQt5 + websockets import TRỄ: thiếu PyQt5 -> báo lệnh cài; thiếu websockets -> mascot vẫn
chạy (tĩnh, kéo được), chỉ không tự đổi mặt / không gửi & nhận chat được.
"""

from __future__ import annotations

import json
import logging
import math
import random
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("aura.ui.mascot")

# Cho phép `from core...` khi chạy `python -m ui.mascot` lẫn chạy file trực tiếp.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Thư mục ảnh: ưu tiên assets/mascot, sau đó assets/avatar.
_ASSET_DIRS = [
    _PROJECT_ROOT / "assets" / "mascot",
    _PROJECT_ROOT / "assets" / "avatar",
]
_MAX_DIM = 200       # cạnh lớn nhất của nhân vật (px) — nguồn HD 384px nên hiển thị to vẫn nét
_BUBBLE_W = 260      # bề rộng tối đa bong bóng thoại (px)
_BUBBLE_MS = 15000   # bong bóng tự biến mất sau 15s nếu không có tin mới


def _require_qt():
    """Import PyQt5 trễ, báo cài rõ nếu thiếu."""
    try:
        from PyQt5 import QtCore, QtGui, QtWidgets  # noqa: F401
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("Thiếu 'PyQt5'. Cài: pip install PyQt5") from exc
    return QtCore, QtGui, QtWidgets


def _ws_uri() -> str:
    """Lấy ws://host:port từ core.config; fallback localhost nếu chưa cấu hình được."""
    try:
        from core.config import settings
        return f"ws://{settings.ws_host}:{settings.ws_port}"
    except Exception as exc:  # noqa: BLE001 — thiếu config không được chặn mascot
        logger.warning("Không đọc được config WS (dùng mặc định): %s", exc)
        return "ws://localhost:8765"


def _find_asset(stem: str) -> Path | None:
    """Tìm file ảnh cho một trạng thái (idle/talk) theo nhiều đuôi, trong các thư mục asset."""
    for d in _ASSET_DIRS:
        for ext in (".gif", ".png", ".webp", ".jpg", ".jpeg"):
            f = d / f"{stem}{ext}"
            if f.is_file():
                return f
    return None


# ---------------------------------------------------------------------------
# Chấm tin việc làm 🗳️ — nối UI với công nhân job_scout (vòng feedback tiến hoá)
# ---------------------------------------------------------------------------
_SCOUT_LAST_PATH = _PROJECT_ROOT / "data" / "feedback" / "job_scout_last.json"
_scout_mod = None


def _load_scout_items(max_items: int = 8) -> list[dict]:
    """Đọc top tin của lượt quét job gần nhất (daemon ghi). Thiếu/hỏng file -> []."""
    try:
        data = json.loads(_SCOUT_LAST_PATH.read_text(encoding="utf-8"))
        return [it for it in data.get("items", []) if it.get("title")][:max_items]
    except Exception:  # noqa: BLE001 — chưa có lượt quét nào thì menu vắng mục này
        return []


def _load_scout_mod():
    """Nạp lười module job_scout (path-based như daemon), cache lại."""
    global _scout_mod
    if _scout_mod is None:
        import importlib.util
        path = _PROJECT_ROOT / "skills" / "scouts" / "job_scout.py"
        spec = importlib.util.spec_from_file_location("aura_scout_jobs_ui", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _scout_mod = mod
    return _scout_mod


def _scout_vote(title: str, url: str, liked: bool) -> bool:
    """Ghi 👍/👎 của Sếp qua record_feedback của job_scout."""
    try:
        _load_scout_mod().record_feedback(title, liked, url=url)
        return True
    except Exception as exc:  # noqa: BLE001 — ghi hỏng thì báo bong bóng, không sập mascot
        logger.warning("Ghi feedback job từ mascot lỗi: %s", exc)
        return False


def _record_application(title: str, url: str, status: str) -> bool:
    """Ghi sổ ứng tuyển (drafted/applied) qua job_scout.record_application."""
    try:
        _load_scout_mod().record_application(title, url=url, status=status)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ghi sổ ứng tuyển từ mascot lỗi: %s", exc)
        return False


def _draft_pitch(title: str, url: str) -> str:
    """Gọi job_scout.draft_pitch (cloud, ~10-15s) — CHỈ chạy trong thread nền."""
    return _load_scout_mod().draft_pitch(title, url=url)


_RADAR_LAST_PATH = _PROJECT_ROOT / "data" / "feedback" / "trend_radar_last.json"


def _load_radar_items(max_items: int = 6) -> tuple[list[dict], str]:
    """Đọc top chủ đề trend gần nhất (radar ghi) + brief cloud nếu có. Thiếu -> ([], '')."""
    try:
        data = json.loads(_RADAR_LAST_PATH.read_text(encoding="utf-8"))
        tops = [it for it in data.get("top", []) if it.get("title")][:max_items]
        return tops, str(data.get("cloud_briefs", "") or "")
    except Exception:  # noqa: BLE001 — chưa quét trend thì menu vắng mục này
        return [], ""


# ---------------------------------------------------------------------------
# SỔ BIỂU CẢM (assets/mascot/behaviors.json) — data-driven: thêm biểu cảm =
# thêm mục JSON, không sửa code. Mỗi mục: trigger (khi nào) + clip + lời thoại.
# ---------------------------------------------------------------------------
_BEHAVIORS_PATH = _PROJECT_ROOT / "assets" / "mascot" / "behaviors.json"


def _load_behaviors() -> list[dict]:
    """Đọc sổ biểu cảm. Thiếu/hỏng file -> [] (mascot dùng bộ lời thoại cứng cũ)."""
    try:
        data = json.loads(_BEHAVIORS_PATH.read_text(encoding="utf-8"))
        book = [b for b in data.get("behaviors", [])
                if isinstance(b, dict) and isinstance(b.get("trigger"), dict)]
        logger.info("Sổ biểu cảm: %d mục.", len(book))
        return book
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không đọc được behaviors.json (%s) -> dùng lời thoại cứng.", exc)
        return []


def _hm_in_range(hm: str, lo: str, hi: str) -> bool:
    """'HH:MM' có nằm trong [lo, hi]? Hỗ trợ khung QUA nửa đêm (vd 22:30 -> 05:00)."""
    if lo <= hi:
        return lo <= hm <= hi
    return hm >= lo or hm <= hi


# ---------------------------------------------------------------------------
# Worker WebSocket trên QThread — nhận trạng thái + LỜI THOẠI, và GỬI lệnh chat
# ---------------------------------------------------------------------------
def _build_pitch_worker(QtCore):
    """QThread soạn pitch: cloud mất ~10-15s -> chạy nền để KHÔNG đơ mascot."""
    class PitchWorker(QtCore.QThread):
        drafted = QtCore.pyqtSignal(str, str, str)   # (title, url, pitch_text)

        def __init__(self, title: str, url: str) -> None:
            super().__init__()
            self._title, self._url = title, url

        def run(self) -> None:
            try:
                pitch = _draft_pitch(self._title, self._url)
            except Exception as exc:  # noqa: BLE001 — lỗi soạn không được làm sập mascot
                pitch = f"(Soạn pitch lỗi, Sếp thử lại sau nhé: {exc})"
            self.drafted.emit(self._title, self._url, pitch)
    return PitchWorker


def _build_ws_worker(QtCore):
    class WSWorker(QtCore.QThread):
        talking_changed = QtCore.pyqtSignal(bool)
        connection_changed = QtCore.pyqtSignal(bool)
        response_received = QtCore.pyqtSignal(str)   # văn bản AURA nói -> bong bóng thoại

        def __init__(self, uri: str) -> None:
            super().__init__()
            self._uri = uri
            self._running = True
            self._aloop = None   # event loop của thread WS (để gửi xuyên luồng)
            self._ws = None      # kết nối đang mở (None khi rớt) — chỉ gửi khi có

        def stop(self) -> None:
            self._running = False

        def send(self, text: str) -> bool:
            """
            Gửi 1 lệnh chat lên server theo giao thức {"type":"chat","text":...}.
            Gọi TỪ luồng GUI -> đẩy coroutine vào event loop của thread WS bằng
            run_coroutine_threadsafe (an toàn xuyên luồng). Trả False nếu chưa nối.
            """
            loop, ws = self._aloop, self._ws
            if loop is None or ws is None:
                logger.info("Chưa nối AURA — chưa gửi được: %r", text)
                return False
            payload = json.dumps({"type": "chat", "text": text})
            try:
                import asyncio
                asyncio.run_coroutine_threadsafe(ws.send(payload), loop)
                return True
            except Exception as exc:  # noqa: BLE001 — gửi lỗi không được làm sập UI
                logger.warning("Gửi WS lỗi: %s", exc)
                return False

        def run(self) -> None:
            import asyncio
            try:
                import websockets  # noqa: F401
            except ModuleNotFoundError:
                logger.warning("Thiếu 'websockets' -> mascot chạy tĩnh. Cài: pip install websockets")
                return
            try:
                asyncio.run(self._loop())
            except Exception as exc:  # noqa: BLE001
                logger.info("WS worker dừng: %s", exc)

        async def _loop(self) -> None:
            import asyncio
            import websockets
            self._aloop = asyncio.get_running_loop()  # để send() đẩy việc vào đây
            while self._running:
                try:
                    async with websockets.connect(self._uri) as ws:
                        self._ws = ws                  # mở cổng gửi
                        self.connection_changed.emit(True)
                        async for raw in ws:
                            self._dispatch(raw)
                except Exception as exc:  # noqa: BLE001 — rớt thì thử lại
                    self.connection_changed.emit(False)
                    logger.info("WS chưa nối được (%s) — thử lại sau 2s.", exc)
                    await asyncio.sleep(2)
                finally:
                    self._ws = None                    # đóng cổng gửi khi rớt

        def _dispatch(self, raw: str) -> None:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return
            t = data.get("type")
            raw_text = data.get("text") or ""          # GIỮ nguyên (không lower) cho bong bóng
            low = raw_text.lower()                      # bản lower CHỈ để so trạng thái
            # BẮT ĐẦU nhả chữ -> talk ; KẾT THÚC -> idle.
            if t == "status" and low in ("talking_start", "thinking", "generating"):
                self.talking_changed.emit(True)
            elif t == "status" and low in ("talking_end", "idle", "done"):
                self.talking_changed.emit(False)
            elif t == "response":
                self.talking_changed.emit(False)
                self.response_received.emit(raw_text)   # -> hiện lời đáp lên bong bóng
            elif t == "error":
                self.talking_changed.emit(False)
                self.response_received.emit("⚠ " + raw_text)
            elif t in ("proactive", "news", "growth"):  # AURA tự mở lời (daemon)
                self.response_received.emit(raw_text)
            elif t == "approval_request":               # Hội đồng chờ Sếp duyệt (Y/không, lý do)
                self.talking_changed.emit(False)
                self.response_received.emit(raw_text)

    return WSWorker


# ---------------------------------------------------------------------------
# Cửa sổ mascot
# ---------------------------------------------------------------------------
def build_app():
    """Dựng QApplication + mascot. Trả (app, mascot)."""
    QtCore, QtGui, QtWidgets = _require_qt()
    WSWorker = _build_ws_worker(QtCore)
    PitchWorker = _build_pitch_worker(QtCore)

    def _placeholder(talking: bool):
        """
        Huy hiệu placeholder PHẲNG khi thiếu ảnh — KHÔNG phải chibi, chỉ là chỗ giữ
        để mascot vẫn hiện & kéo được. Đặt idle.png/talk.png vào assets/ là thay ngay.
        Idle = hồng nhạt, Talk = xanh ngọc; chấm nhỏ báo trạng thái + nhãn 'AURA'.
        """
        size = 132
        pm = QtGui.QPixmap(size, size)
        pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        accent = QtGui.QColor("#52E0CC") if talking else QtGui.QColor("#FF6B9D")
        # Nền bo tròn mờ nhẹ.
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(67, 65, 79, 235))
        p.drawRoundedRect(6, 6, size - 12, size - 12, 26, 26)
        # Vòng nhấn theo trạng thái.
        pen = QtGui.QPen(accent); pen.setWidth(3)
        p.setPen(pen); p.setBrush(QtCore.Qt.NoBrush)
        p.drawRoundedRect(6, 6, size - 12, size - 12, 26, 26)
        # Chấm trạng thái.
        p.setPen(QtCore.Qt.NoPen); p.setBrush(accent)
        p.drawEllipse(size // 2 - 6, 34, 12, 12)
        # Nhãn.
        f = p.font(); f.setPixelSize(20); f.setBold(True); p.setFont(f)
        p.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF")))
        p.drawText(QtCore.QRect(0, 58, size, 30), QtCore.Qt.AlignCenter, "AURA")
        f.setPixelSize(11); f.setBold(False); p.setFont(f)
        p.setPen(QtGui.QPen(accent))
        p.drawText(QtCore.QRect(0, 86, size, 18), QtCore.Qt.AlignCenter,
                   "talk" if talking else "idle")
        p.end()
        return pm

    def _scaled_pix(path: Path):
        pm = QtGui.QPixmap(str(path))
        if pm.isNull():
            return None
        return pm.scaled(_MAX_DIM, _MAX_DIM, QtCore.Qt.KeepAspectRatio,
                         QtCore.Qt.SmoothTransformation)

    class Mascot(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            # --- Cửa sổ "tàng hình" ---
            self.setWindowFlags(
                QtCore.Qt.FramelessWindowHint
                | QtCore.Qt.WindowStaysOnTopHint
                | QtCore.Qt.Tool
            )
            self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
            self.setWindowTitle("AURA")

            self.label = QtWidgets.QLabel(self)
            self.label.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
            self.label.setAlignment(QtCore.Qt.AlignCenter)

            # --- Bong bóng thoại: nổi TRÊN đầu mascot, ẩn cho tới khi AURA nói ---
            self.bubble = QtWidgets.QLabel(self)
            self.bubble.setWordWrap(True)
            self.bubble.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
            self.bubble.setStyleSheet(
                "QLabel{"
                " background: rgba(43,41,63,0.92);"        # đồng bộ phong cách khung gõ
                " color: #F5F5F7;"
                " border: 1px solid rgba(82,224,204,0.85);"
                " border-radius: 14px;"
                " padding: 8px 12px;"
                " font-size: 13px;"
                "}"
            )
            self.bubble.hide()
            # Hẹn giờ tự ẩn bong bóng sau 15s (reset mỗi lần có tin mới).
            self._bubble_timer = QtCore.QTimer(self)
            self._bubble_timer.setSingleShot(True)
            self._bubble_timer.timeout.connect(self._hide_bubble)

            # --- Khung gõ lệnh: ẩn mặc định, hiện khi double-click vào mascot ---
            self.input = QtWidgets.QLineEdit(self)
            self.input.setPlaceholderText("Nhắn cho AURA…")
            self.input.setStyleSheet(
                "QLineEdit{"
                " background: rgba(43,41,63,0.86);"
                " color: #FFFFFF;"
                " border: 1px solid rgba(82,224,204,0.85);"
                " border-radius: 14px;"
                " padding: 6px 12px;"
                " font-size: 13px;"
                " selection-background-color: #52E0CC;"
                "}"
                "QLineEdit:focus{ border: 1px solid #FF6B9D; }"
            )
            self.input.returnPressed.connect(self._send_current_text)
            self.input.hide()

            self._img_w, self._img_h = 80, 80       # kích thước ảnh hiện tại (cập nhật ở _apply)
            self._states = self._load_states()      # {"idle": (kind,obj), "talk": (...)}
            self._current_movie = None
            self._talking = False
            self._drag = None
            self._voted_titles: set[str] = set()    # tin đã chấm trong phiên -> ẩn khỏi menu

            self._apply("idle")
            self._place_bottom_right()

            # --- nối WebSocket ---
            self.worker = WSWorker(_ws_uri())
            self.worker.talking_changed.connect(self.set_talking_state)
            self.worker.response_received.connect(self.show_bubble)   # lời AURA -> bong bóng
            self.chat_win = ChatWindow(self.worker.send)              # cửa sổ chat TO
            self.worker.response_received.connect(self.chat_win.append_aura)
            self.worker.start()
            self._pitch_workers = []      # giữ ref QThread soạn pitch (khỏi bị GC giữa chừng)

            # --- ĐI LANG THANG trên desktop (Shimeji-style): tự dạo dọc cạnh dưới ---
            self._wander_target_x = None
            self._wander_dir = 1
            self._wander_phase = 0.0
            self._base_pix = None               # ảnh gốc (hướng phải) để lật theo chiều đi
            self._wander_timer = QtCore.QTimer(self)
            self._wander_timer.timeout.connect(self._wander_step)
            self._wander_timer.start(40)        # ~25 khung/giây

            # Khung hình ĐỘNG Miku (cắt từ MikuPet): idle 20 + walk 8 frame.
            self._idle_frames, self._idle_frames_l = self._load_frames("idle")
            self._walk_frames, self._walk_frames_l = self._load_frames("walk")
            self._wave_frames, self._wave_frames_l = self._load_frames("wave")
            self._happy_frames, self._happy_frames_l = self._load_frames("happy")
            self._look_frames, self._look_frames_l = self._load_frames("look")
            self._eat_frames, self._eat_frames_l = self._load_frames("eat")
            self._color_frames, self._color_frames_l = self._load_frames("color")
            self._frame_i = 0
            self._anim_div = 0
            self._action_frames = None        # animation tạm đang phát
            self._action_frames_l = None       # ... và bản lật trái tương ứng
            self._action_left = 0
            # KHO hành động tự phát (phải, trái) -> giống sinh vật sống, không chỉ đi tới lui
            self._action_pool = [
                (self._wave_frames, self._wave_frames_l),
                (self._happy_frames, self._happy_frames_l),
                (self._look_frames, self._look_frames_l),
                (self._eat_frames, self._eat_frames_l),
                (self._color_frames, self._color_frames_l),
            ]
            # --- SỔ BIỂU CẢM: tra clip theo tên + index behavior theo loại trigger ---
            self._clips = {
                "idle": (self._idle_frames, self._idle_frames_l),
                "walk": (self._walk_frames, self._walk_frames_l),
                "wave": (self._wave_frames, self._wave_frames_l),
                "happy": (self._happy_frames, self._happy_frames_l),
                "look": (self._look_frames, self._look_frames_l),
                "eat": (self._eat_frames, self._eat_frames_l),
                "color": (self._color_frames, self._color_frames_l),
            }
            self._book_by_type: dict[str, list[dict]] = {}
            for b in _load_behaviors():
                ttype = str(b["trigger"].get("type", ""))
                self._book_by_type.setdefault(ttype, []).append(b)
            self._fired_once: set[str] = set()   # time/dow/date/hour chỉ bắn 1 lần/phiên
            self._last_hour = datetime.now().hour  # không "boong" ngay lúc mới mở
            self._hour_timer = QtCore.QTimer(self)
            self._hour_timer.timeout.connect(self._maybe_hour_chime)
            self._hour_timer.start(60000)          # dò đổi giờ mỗi phút
            QtCore.QTimer.singleShot(2500, self._greet_startup)
            # dirty-check: chỉ setPixmap khi THẬT SỰ đổi (đỡ vẽ lại vô ích mỗi 40ms)
            self._last_drawn = None
            self._act_timer = QtCore.QTimer(self)
            self._act_timer.timeout.connect(self._maybe_action)
            self._act_timer.start(14000)      # mỗi 14s xét tự làm 1 hành động
            if self._idle_frames:
                p0 = self._idle_frames[0]
                self.label.setPixmap(p0)
                self._img_w, self._img_h = p0.width(), p0.height()
                self._relayout()

            # --- Tương tác thêm ---
            self._wander_on = True          # bật/tắt đi lang thang (menu)
            self._hopping = False           # đang nhảy phản ứng vỗ
            self._press_pos = None          # để phân biệt VỖ (click) với KÉO
            self._pat_lines = ["Sếp gọi em à? 💚", "Hí hí~ nhột!", "Em đây Sếp!",
                               "Iu Sếp 💕", "Dạ em nghe!"]
            self._chatter_lines = [
                "Sếp code Python chút chưa ạ? 🐍",
                "Đừng quên ôn bài nha Sếp!",
                "Ngồi lâu rồi, đứng dậy vươn vai cái nào~",
                "Mục tiêu của Sếp — mình làm được mà! ✨",
                "Em luôn ở đây với Sếp nè.",
            ]
            self._chatter_timer = QtCore.QTimer(self)
            self._chatter_timer.timeout.connect(self._maybe_chatter)
            self._chatter_timer.start(120000)   # mỗi 2' xét nói 1 câu (xác suất thấp)

        # ---- nạp 2 trạng thái idle/talk: GIF (động) -> PNG (tĩnh) -> placeholder ----
        def _load_one(self, key: str):
            """Trả (kind, obj) cho một trạng thái. Ưu tiên ảnh thật, fallback placeholder."""
            path = _find_asset(key)
            talking = key == "talk"
            if path is None:
                return ("pix", _placeholder(talking))
            if path.suffix.lower() == ".gif":          # ảnh ĐỘNG
                movie = QtGui.QMovie(str(path))
                movie.jumpToFrame(0)
                sz = movie.currentImage().size()
                if sz.width() > 0:
                    movie.setScaledSize(
                        sz.scaled(_MAX_DIM, _MAX_DIM, QtCore.Qt.KeepAspectRatio)
                    )
                return ("movie", movie)
            pm = _scaled_pix(path)                      # ảnh TĨNH (png/webp/jpg)
            return ("pix", pm if pm is not None else _placeholder(talking))

        def _load_states(self):
            return {key: self._load_one(key) for key in ("idle", "talk")}

        def _apply(self, state: str):
            kind, obj = self._states.get(state, self._states["idle"])
            if self._current_movie is not None:
                self._current_movie.stop()
                self._current_movie = None
            if kind == "movie":
                self.label.setMovie(obj)
                obj.start()
                self._current_movie = obj
                size = obj.currentImage().size()
                w, h = max(size.width(), 80), max(size.height(), 80)
            else:
                self.label.setPixmap(obj)
                self._base_pix = obj            # giữ ảnh gốc (hướng phải) để lật theo chiều đi
                w, h = obj.width(), obj.height()
            self._img_w, self._img_h = w, h
            self._relayout()

        def _load_frames(self, prefix: str):
            """Nạp chuỗi khung hình (cắt từ MikuPet) + LẬT SẴN cả 2 chiều MỘT LẦN lúc
            nạp (tối ưu kiểu 'game cũ': tính trước, đừng tính lại mỗi khung hình —
            trước đây lật ảnh bằng QTransform ở MỖI tick 25 lần/giây, lãng phí CPU)."""
            right, left = [], []
            # Ưu tiên bộ HD (anim_hd, hq4x 384px từ tools/upscale_mascot.py); thiếu thì
            # về bộ pixel gốc — mascot vẫn chạy nếu chưa upscale.
            anim_dir = _PROJECT_ROOT / "assets" / "mascot" / "anim_hd"
            if not anim_dir.is_dir():
                anim_dir = _PROJECT_ROOT / "assets" / "mascot" / "anim"
            if not anim_dir.is_dir():
                return right, left
            for f in sorted(anim_dir.glob(f"{prefix}_*.png")):
                pm = QtGui.QPixmap(str(f))
                if not pm.isNull():
                    pm = pm.scaled(_MAX_DIM, _MAX_DIM, QtCore.Qt.KeepAspectRatio,
                                   QtCore.Qt.SmoothTransformation)
                    right.append(pm)
                    left.append(pm.transformed(QtGui.QTransform().scale(-1, 1)))
            return right, left

        def _wander_step(self):
            """Đi lang thang + ANIMATION Miku: idle khi đứng, walk khi đi, lật theo
            chiều. Dừng ĐI (vẫn idle) khi đang kéo / gõ chat / nói — 'đứng làm việc'."""
            if not self._idle_frames:           # chưa có frame -> giữ ảnh tĩnh cũ
                return
            acting = self._action_left > 0
            paused = (self._drag is not None or self.input.isVisible() or self._talking
                      or not self._wander_on or self._hopping or acting)
            moving = False
            if not paused:
                scr = QtWidgets.QApplication.primaryScreen().availableGeometry()
                x = self.x()
                if self._wander_target_x is None or abs(x - self._wander_target_x) < 6:
                    lo = scr.left() + 10
                    hi = max(lo + 1, scr.right() - self.width() - 10)
                    # 1/3 cơ hội đứng nghỉ một quãng (idle) cho tự nhiên
                    self._wander_target_x = x if random.random() < 0.33 else random.randint(lo, hi)
                if abs(x - self._wander_target_x) >= 6:
                    moving = True
                    self._wander_dir = 1 if self._wander_target_x > x else -1
                    self._wander_phase += 0.4
                    base_y = scr.bottom() - self.height() + 6
                    ny = int(base_y - abs(math.sin(self._wander_phase)) * 4)
                    self.move(x + self._wander_dir * 2, ny)
            # --- chọn bộ frame (PHẢI/TRÁI đã lật SẴN lúc nạp -> không transform mỗi tick) ---
            if self._talking and self._happy_frames:      # AURA đang nói -> phấn khích
                frames, frames_l = self._happy_frames, self._happy_frames_l
            elif acting and self._action_frames:          # đang phát wave/happy tạm
                frames, frames_l = self._action_frames, self._action_frames_l
            elif moving and self._walk_frames:            # đang đi -> walk
                frames, frames_l = self._walk_frames, self._walk_frames_l
            else:                                         # đứng -> idle
                frames, frames_l = self._idle_frames, self._idle_frames_l
            self._anim_div += 1
            if self._anim_div >= (3 if (moving or acting) else 6):
                self._anim_div = 0
                self._frame_i += 1
                if acting:
                    self._action_left -= 1
                    if self._action_left <= 0:
                        self._action_frames = None
                        self._action_frames_l = None
                        self._frame_i = 0
            i = self._frame_i % len(frames)
            # DIRTY-CHECK: chỉ vẽ lại khi khung/chiều THẬT SỰ đổi -> đỡ setPixmap vô ích
            # 25 lần/giây khi đang đứng yên (kiểu tối ưu game cũ: đừng vẽ lại khung không đổi).
            key = (id(frames), i, self._wander_dir < 0)
            if key == self._last_drawn:
                return
            self._last_drawn = key
            self.label.setPixmap((frames_l if self._wander_dir < 0 else frames)[i])

        # ---- bố cục dọc: [bong bóng] -> [ảnh] -> [khung gõ], cái nào ẩn thì bỏ qua ----
        def _relayout(self):
            iw, ih = self._img_w, self._img_h
            bubble_on = self.bubble.isVisible()
            input_on = self.input.isVisible()
            gap = 6
            cw = max(iw, _BUBBLE_W) if (bubble_on or input_on) else iw

            top = 0
            if bubble_on:
                self.bubble.setFixedWidth(cw)
                bub_h = self.bubble.heightForWidth(cw)
                if not isinstance(bub_h, int) or bub_h <= 0:
                    bub_h = self.bubble.sizeHint().height()
                bub_h = max(int(bub_h), 30)
                self.bubble.setGeometry(0, 0, cw, bub_h)
                top = bub_h + gap

            self.label.setGeometry((cw - iw) // 2, top, iw, ih)
            bottom = top + ih

            if input_on:
                in_h = 34
                self.input.setGeometry(8, bottom + gap, cw - 16, in_h)
                bottom = bottom + gap + in_h

            self.setFixedSize(cw, bottom)
            self._clamp_on_screen()

        def _clamp_on_screen(self):
            """Sau khi nở thêm bong bóng/khung gõ, kéo cửa sổ vào trong màn nếu lỡ tràn mép."""
            scr = QtWidgets.QApplication.primaryScreen().availableGeometry()
            g = self.frameGeometry()
            x, y = g.x(), g.y()
            if g.right() > scr.right():
                x = scr.right() - self.width()
            if g.bottom() > scr.bottom():
                y = scr.bottom() - self.height()
            x = max(scr.left(), x)
            y = max(scr.top(), y)
            self.move(x, y)

        # ---- BONG BÓNG THOẠI: hiện lời AURA, tự ẩn sau 15s ----
        def show_bubble(self, text: str):
            text = (text or "").strip()
            if not text:
                return
            if len(text) > 600:                         # cắt gọn cho khỏi che màn hình
                text = text[:600].rstrip() + "…"
            self.bubble.setText(text)
            self.bubble.setVisible(True)
            self.bubble.raise_()
            self._relayout()
            self._bubble_timer.start(_BUBBLE_MS)        # reset đồng hồ 15s mỗi tin mới

        def _hide_bubble(self):
            self.bubble.hide()
            self.bubble.clear()
            self._relayout()

        # ---- ĐỘNG CƠ SỔ BIỂU CẢM: chọn -> phát (bong bóng + clip) ----
        def _pick(self, ttype: str, **match) -> dict | None:
            """Chọn ngẫu nhiên 1 behavior loại `ttype`, lọc thêm theo field trong trigger."""
            pool = self._book_by_type.get(ttype, [])
            if match:
                pool = [b for b in pool
                        if all(b["trigger"].get(k) == v for k, v in match.items())]
            return random.choice(pool) if pool else None

        def _fire(self, b: dict | None) -> bool:
            """Phát một biểu cảm: nói 1 câu trong lines (nếu có) + chạy clip (nếu có)."""
            if b is None:
                return False
            lines = b.get("lines") or []
            if lines:
                self.show_bubble(random.choice(lines))
            clip = b.get("clip")
            if clip == "hop":
                self._do_jump()
            elif clip:
                frames, frames_l = self._clips.get(clip, (None, None))
                if frames:
                    self._play_action(frames, frames_l, int(b.get("loops", 2)))
            return True

        def _fire_once(self, b: dict | None) -> bool:
            """Như _fire nhưng mỗi behavior chỉ bắn 1 lần/phiên (chào theo giờ/thứ/ngày lễ)."""
            if b is None or b.get("id") in self._fired_once:
                return False
            self._fired_once.add(b.get("id"))
            return self._fire(b)

        def _greet_startup(self):
            self._fire(self._pick("startup"))

        def _maybe_hour_chime(self):
            """Điểm giờ: sang giờ mới mà sổ có mục 'hour' khớp thì boong một câu."""
            h = datetime.now().hour
            if h == self._last_hour:
                return
            self._last_hour = h
            for b in self._book_by_type.get("hour", []):
                if int(b["trigger"].get("at", -1)) == h:
                    self._fire_once(b)
                    return

        # ---- tương tác thêm ----
        def _maybe_chatter(self):
            """Thi thoảng tự nói khi rảnh. Ưu tiên: ngày lễ > thứ trong tuần > khung giờ
            (mỗi loại 1 lần/phiên) > câu chuyện phiếm ngẫu nhiên."""
            if self._talking or self.input.isVisible() or self.bubble.isVisible():
                return
            now = datetime.now()
            md = now.strftime("%m-%d")
            for b in self._book_by_type.get("date", []):
                if b["trigger"].get("md") == md and self._fire_once(b):
                    return
            for b in self._book_by_type.get("dow", []):
                if int(b["trigger"].get("day", -1)) == now.weekday() and self._fire_once(b):
                    return
            hm = now.strftime("%H:%M")
            for b in self._book_by_type.get("time", []):
                t = b["trigger"]
                if (_hm_in_range(hm, str(t.get("from", "00:00")), str(t.get("to", "23:59")))
                        and self._fire_once(b)):
                    return
            if random.random() < 0.5:
                if not self._fire(self._pick("chatter")):
                    self.show_bubble(random.choice(self._chatter_lines))

        def _maybe_action(self):
            """Khi rảnh, thi thoảng tự làm một hành động ngẫu nhiên -> giống sinh vật sống."""
            if (self._talking or self.input.isVisible() or self._drag is not None
                    or self._hopping or self._action_left > 0):
                return
            if random.random() < 0.6:
                if self._fire(self._pick("self")):
                    return
                pool = [pair for pair in self._action_pool if pair[0]]
                if pool:
                    frames, frames_l = random.choice(pool)
                    self._play_action(frames, frames_l, 1)

        def _do_pending_pat(self):
            if getattr(self, "_pat_pending", False):
                self._pat_pending = False
                self._pat_react()

        def _play_action(self, frames, frames_l, loops=2):
            """Phát một chuỗi animation TẠM (wave/happy) rồi tự về idle/walk."""
            if not frames:
                return
            self._action_frames = frames
            self._action_frames_l = frames_l
            self._action_left = len(frames) * loops
            self._frame_i = 0

        def _pat_react(self):
            """Vỗ (click) / chào -> biểu cảm từ sổ (fallback: vẫy tay + câu cứng)."""
            if self._fire(self._pick("pat")):
                return
            self.show_bubble(random.choice(self._pat_lines))
            self._play_action(self._wave_frames, self._wave_frames_l, 2)

        def _do_jump(self):
            """Nhảy nhẹ (menu)."""
            if self._hopping:
                return
            self._hopping = True
            self._hop_base_y = self.y()
            self._hop_i = 0
            if not hasattr(self, "_hop_timer"):
                self._hop_timer = QtCore.QTimer(self)
                self._hop_timer.timeout.connect(self._hop_step)
            self._hop_timer.start(18)

        def _hop_step(self):
            self._hop_i += 1
            off = int(abs(math.sin(self._hop_i / 9.0 * math.pi)) * 18)   # lên rồi xuống
            self.move(self.x(), self._hop_base_y - off)
            if self._hop_i >= 9:
                self._hop_timer.stop()
                self.move(self.x(), self._hop_base_y)
                self._hopping = False

        def _come_here(self):
            """Đi tới gần con trỏ chuột."""
            scr = QtWidgets.QApplication.primaryScreen().availableGeometry()
            c = QtGui.QCursor.pos()
            x = min(max(scr.left(), c.x() - self.width() // 2), scr.right() - self.width())
            self._wander_target_x = x
            self.move(x, scr.bottom() - self.height() + 6)

        # ---- gửi lệnh: Enter -> WebSocket -> xoá trắng ----
        def _send_current_text(self):
            text = self.input.text().strip()
            if not text:
                return
            ok = self.worker.send(text)
            self.input.clear()                          # xoá trắng ngay sau khi gửi
            if not ok:
                self.input.setPlaceholderText("Chưa nối được AURA — chạy main.py?")
            else:
                self.input.setPlaceholderText("Nhắn cho AURA…")

        # ---- double-click: bật/tắt khung gõ ----
        def _toggle_input(self):
            show = not self.input.isVisible()
            self.input.setVisible(show)
            self._relayout()
            if show:
                self.input.raise_()
                self.input.setFocus()

        # ---- API trạng thái khuôn mặt ----
        def set_talking_state(self, is_talking: bool):
            is_talking = bool(is_talking)
            if is_talking == self._talking:
                return
            self._talking = is_talking
            self._apply("talk" if is_talking else "idle")

        # ---- vị trí ban đầu: góc dưới-phải ----
        def _place_bottom_right(self):
            screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
            self.move(screen.right() - self.width() - 40,
                      screen.bottom() - self.height() - 60)

        # ---- kéo–thả (giữ nguyên: chỉ kéo khi nhấn-giữ-rê chuột trái trên thân mascot) ----
        def mousePressEvent(self, e):
            if e.button() == QtCore.Qt.LeftButton:
                self._drag = e.globalPos() - self.frameGeometry().topLeft()
                self._press_pos = e.globalPos()
                e.accept()

        def mouseMoveEvent(self, e):
            if self._drag is not None and (e.buttons() & QtCore.Qt.LeftButton):
                self.move(e.globalPos() - self._drag)
                if (self._press_pos is not None
                        and (e.globalPos() - self._press_pos).manhattanLength() > 6):
                    self._press_pos = None      # đã kéo đi -> không tính là vỗ
                e.accept()

        def mouseReleaseEvent(self, e):
            self._drag = None
            # VỖ = nhấn–thả tại chỗ (không kéo). Hoãn 230ms để double-click kịp huỷ.
            if self._press_pos is not None:
                self._press_pos = None
                self._pat_pending = True
                QtCore.QTimer.singleShot(230, self._do_pending_pat)

        def mouseDoubleClickEvent(self, e):
            if e.button() == QtCore.Qt.LeftButton:
                self._drag = None
                self._pat_pending = False       # huỷ vỗ -> ưu tiên mở chat
                self.chat_win.show_raise()      # mở CỬA SỔ CHAT TO
                e.accept()

        # ---- menu chuột phải: nhắn / thử nói / chấm tin việc / thoát ----
        def contextMenuEvent(self, e):
            menu = QtWidgets.QMenu(self)
            act_chat = menu.addAction("Mở khung chat 💬")
            act_here = menu.addAction("Lại đây với tôi")
            act_wave = menu.addAction("Vẫy tay 👋")
            act_wander = menu.addAction("Đứng yên" if self._wander_on else "Đi dạo tiếp")
            act_jump = menu.addAction("Nhảy phát nào 🐰")
            act_feed = menu.addAction("Cho ăn 🍙")
            # Tin việc làm của lượt quét gần nhất: mỗi tin một submenu 🔗/👍/👎.
            # Vote đi thẳng vào record_feedback -> công nhân embedding tự tiến hoá cách chấm.
            vote_map: dict = {}
            jobs = [it for it in _load_scout_items()
                    if it.get("title") not in self._voted_titles]
            if jobs:
                menu.addSeparator()
                jobs_menu = menu.addMenu("Chấm tin việc làm 🗳️")
                for it in jobs:
                    title = str(it.get("title", ""))
                    short = title if len(title) <= 48 else title[:47] + "…"
                    try:
                        score = f"{float(it.get('score') or 0):.2f}"
                    except (TypeError, ValueError):
                        score = "?"
                    sub = jobs_menu.addMenu(f"[{score}] {short}")
                    if it.get("url"):
                        vote_map[sub.addAction("🔗 Mở link")] = ("open", it)
                    vote_map[sub.addAction("✍️ Soạn pitch (kiếm tiền)")] = ("pitch", it)
                    vote_map[sub.addAction("✅ Đã ứng tuyển")] = ("applied", it)
                    vote_map[sub.addAction("👍 Đáng xem")] = ("like", it)
                    vote_map[sub.addAction("👎 Rác")] = ("dislike", it)
            # Brief chủ đề trend của radar: mỗi chủ đề một submenu 📖 Xem brief / 🔗 Mở link.
            radar_map: dict = {}
            radar_items, radar_cloud = _load_radar_items()
            if radar_items:
                menu.addSeparator()
                radar_menu = menu.addMenu("Xem brief trend 📡")
                for it in radar_items:
                    title = str(it.get("title", ""))
                    short = title if len(title) <= 48 else title[:47] + "…"
                    try:
                        pct = int(round(float(it.get("fit") or 0) * 100))
                    except (TypeError, ValueError):
                        pct = 0
                    sub = radar_menu.addMenu(f"[{pct}%] {short}")
                    radar_map[sub.addAction("📖 Xem brief")] = ("brief", it, radar_cloud)
                    if it.get("link"):
                        radar_map[sub.addAction("🔗 Mở link")] = ("open", it, radar_cloud)
            menu.addSeparator()
            act_quit = menu.addAction("Thoát mascot")
            chosen = menu.exec_(e.globalPos())
            if chosen == act_chat:
                self.chat_win.show_raise()
                self._fire(self._pick("menu", id="chat"))
            elif chosen == act_here:
                self._come_here()
                self._fire(self._pick("menu", id="come"))
            elif chosen == act_wave:
                self._pat_react()
            elif chosen == act_wander:
                self._wander_on = not self._wander_on
                self._fire(self._pick(
                    "menu", id="wander_on" if self._wander_on else "wander_off"))
            elif chosen == act_jump:
                if not self._fire(self._pick("menu", id="jump")):
                    self._do_jump()
            elif chosen == act_feed:
                if not self._fire(self._pick("menu", id="feed")):
                    self._play_action(self._eat_frames, self._eat_frames_l, 2)
            elif chosen in vote_map:
                kind, it = vote_map[chosen]
                if kind == "open":
                    QtGui.QDesktopServices.openUrl(QtCore.QUrl(str(it.get("url", ""))))
                elif kind == "pitch":
                    self._start_pitch(it.get("title", ""), it.get("url", ""))
                elif kind == "applied":
                    _record_application(it.get("title", ""), it.get("url", ""), "applied")
                    self._voted_titles.add(it.get("title"))
                    self.show_bubble("Ghi sổ 'đã ứng tuyển' rồi! Chúc Sếp gặp khách xịn 💪")
                elif _scout_vote(it.get("title", ""), it.get("url", ""), kind == "like"):
                    self._voted_titles.add(it.get("title"))
                    if not self._fire(self._pick("vote", liked=(kind == "like"))):
                        self.show_bubble(
                            "Đã ghi 👍 — mai tôi ưu tiên săn tin kiểu này!" if kind == "like"
                            else "Đã ghi 👎 — tin kiểu này sẽ bị dìm điểm."
                        )
                else:
                    self.show_bubble("Hỏng ghi được feedback, Sếp xem log giúp tôi 🥲")
            elif chosen in radar_map:
                kind, it, cloud = radar_map[chosen]
                if kind == "open":
                    QtGui.QDesktopServices.openUrl(QtCore.QUrl(str(it.get("link", ""))))
                else:
                    self._show_radar_brief(it, cloud)
            elif chosen == act_quit:
                self.close()

        def _start_pitch(self, title: str, url: str) -> None:
            """Soạn nháp pitch trong THREAD NỀN (cloud ~10-15s, khỏi đơ mascot)."""
            if not title:
                return
            self.show_bubble("Em soạn nháp pitch nhé, chờ ~15 giây… ✍️")
            self.chat_win.append_aura(f"✍️ Đang soạn pitch cho: {title}\n(chờ cloud viết, ~10-15s…)")
            self.chat_win.show_raise()
            w = PitchWorker(title, url)
            w.drafted.connect(self._on_pitch_drafted)
            w.finished.connect(lambda: self._pitch_workers.remove(w)
                               if w in self._pitch_workers else None)
            self._pitch_workers.append(w)
            w.start()

        def _on_pitch_drafted(self, title: str, url: str, pitch: str) -> None:
            """Nhận pitch từ thread -> đưa vào chat + ghi sổ 'đã soạn'."""
            self.chat_win.append_aura(
                f"📄 Pitch cho \"{title}\":\n\n{pitch}\n\n"
                "— Sếp sửa lại (tên/giá/portfolio) rồi TỰ gửi nha. Em ghi vào sổ 'đã soạn'."
            )
            self.chat_win.show_raise()
            _record_application(title, url, "drafted")
            self.show_bubble("Pitch xong rồi, Sếp xem trong khung chat nha! 📄")

        def _show_radar_brief(self, it: dict, cloud_briefs: str) -> None:
            """Đưa brief chủ đề trend vào CỬA SỔ CHAT (đọc thoải mái hơn bong bóng 15s)."""
            title = str(it.get("title", ""))
            why = it.get("why") or (f"~{it['signal']} lượt tìm" if it.get("signal") else "")
            # Ưu tiên brief cloud (đầy đủ) nếu có; không thì brief khung mẫu của từng chủ đề.
            body = str(cloud_briefs).strip() if cloud_briefs else str(it.get("brief", "")).strip()
            parts = [f"📡 Chủ đề trend: {title}"]
            if why:
                parts.append(f"Vì sao lúc này: {why}")
            if it.get("link"):
                parts.append(f"Link: {it['link']}")
            if body:
                parts.append("\n" + body)
            self.chat_win.append_aura("\n".join(parts))
            self.chat_win.show_raise()
            self._fire(self._pick("menu", id="chat"))

        def closeEvent(self, e):
            try:
                self.chat_win.close()
                self._bubble_timer.stop()
                self.worker.stop()
                self.worker.wait(1500)
                for w in list(getattr(self, "_pitch_workers", [])):
                    w.wait(2000)          # chờ pitch đang soạn xong, tránh hủy QThread giữa chừng
            except Exception:  # noqa: BLE001
                pass
            super().closeEvent(e)

    # ================================================================== #
    # Cửa sổ CHAT TO — lịch sử hội thoại đầy đủ (mở khi double-click mascot)
    # ================================================================== #
    class ChatWindow(QtWidgets.QWidget):
        def __init__(self, send_fn):
            super().__init__()
            self._send_fn = send_fn
            self.setWindowTitle("AURA — Trò chuyện")
            self.setWindowFlags(QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Window)
            self.resize(440, 560)
            self.setStyleSheet("QWidget{ background:#1e1c2b; color:#F5F5F7; font-size:14px; }")
            lay = QtWidgets.QVBoxLayout(self)
            lay.setContentsMargins(12, 12, 12, 12)
            title = QtWidgets.QLabel("🎤 AURA")
            title.setStyleSheet("font-size:16px; font-weight:bold; color:#52E0CC;")
            lay.addWidget(title)
            self.history = QtWidgets.QTextEdit()
            self.history.setReadOnly(True)
            self.history.setStyleSheet(
                "QTextEdit{ background:#26243a; border:1px solid #3a3856;"
                " border-radius:12px; padding:10px; }")
            lay.addWidget(self.history, 1)
            row = QtWidgets.QHBoxLayout()
            self.input = QtWidgets.QLineEdit()
            self.input.setPlaceholderText("Nhắn cho AURA…  (Enter để gửi)")
            self.input.setStyleSheet(
                "QLineEdit{ background:#2b293f; border:1px solid #52E0CC; border-radius:12px;"
                " padding:9px 12px; } QLineEdit:focus{ border:1px solid #FF6B9D; }")
            self.input.returnPressed.connect(self._send)
            btn = QtWidgets.QPushButton("Gửi")
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton{ background:#52E0CC; color:#1e1c2b; border:none; border-radius:12px;"
                " padding:9px 18px; font-weight:bold; } QPushButton:hover{ background:#6cf0dc; }")
            btn.clicked.connect(self._send)
            row.addWidget(self.input, 1)
            row.addWidget(btn)
            lay.addLayout(row)

        def _append(self, who, text, color):
            import html as _html
            import re
            escaped_text = _html.escape(text)
            # Khắc phục lỗi mất xuống dòng trên UI HTML của PyQt
            escaped_text = escaped_text.replace('\n', '<br>')
            # Thêm bộ parse sơ lược để vẽ hộp code (Markdown code blocks)
            escaped_text = re.sub(
                r'```[a-zA-Z]*<br>(.*?)```',
                r'<div style="background-color:#2a2b36; color:#f8f8f2; padding:8px; border-radius:4px; font-family:Consolas,monospace; margin:6px 0;">\1</div>',
                escaped_text,
                flags=re.DOTALL
            )
            self.history.append(
                f'<p style="margin:4px 0;"><b style="color:{color};">{who}:</b> '
                f'{escaped_text}</p>')
            sb = self.history.verticalScrollBar()
            sb.setValue(sb.maximum())

        def append_aura(self, text):
            text = (text or "").strip()
            if text:
                self._append("AURA", text, "#FF9DC7")

        def _send(self):
            t = self.input.text().strip()
            if not t:
                return
            self._append("Sếp", t, "#52E0CC")
            self.input.clear()
            ok = False
            try:
                ok = bool(self._send_fn(t))
            except Exception:  # noqa: BLE001
                ok = False
            if not ok:
                self._append("(hệ thống)", "Chưa nối được AURA — đảm bảo main.py đang chạy.", "#888")

        def show_raise(self):
            scr = QtWidgets.QApplication.primaryScreen().availableGeometry()
            if not self.isVisible():
                self.move(scr.center().x() - self.width() // 2,
                          scr.center().y() - self.height() // 2)
            self.show()
            self.raise_()
            self.activateWindow()
            self.input.setFocus()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    mascot = Mascot()
    return app, mascot


def main() -> None:
    app, mascot = build_app()
    mascot.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    # Chống CHẠY ĐÔI (2 launcher) — nếu không sẽ có 2 Miku đi lại trên desktop.
    from core.single_instance import ensure_single
    ensure_single("mascot")
    main()


__all__ = ["build_app", "main"]
