"""
ui/health_guard.py
==================
Health Guard — KHIÊN ĐEN ép nghỉ kỷ luật (tiến trình UI riêng, PyQt5).

Nghe sự kiện `health_break` từ AURA server qua WebSocket. Khi tới giờ ép nghỉ:
  1) Nổi BONG BÓNG cảnh báo (toast) giữa-trên màn hình.
  2) Tự lưu công việc: pyautogui.hotkey('ctrl', 's').
  3) Sau 10 giây -> phủ KHIÊN ĐEN toàn màn hình + đồng hồ đếm ngược (mặc định 05:00),
     CHẶN click chuột & gõ phím cơ bản; về 00:00 thì tự .close() trả màn hình lại.

An toàn dữ liệu: auto-save TRƯỚC khi khoá; daemon đã hoãn 30' nếu đang render nặng.
Van an toàn: khiên TỰ ĐÓNG khi hết giờ (không treo vĩnh viễn).

Chạy:
    python -m ui.health_guard            # nghe server (cần: python main.py)
    python -m ui.health_guard --demo 10  # thử KHIÊN ĐEN 10 giây, không cần server

PyQt5/websockets/pyautogui import TRỄ + bọc lỗi: thiếu cái nào báo rõ, không sập.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger("aura.ui.health_guard")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Câu cảnh báo (đồng bộ với daemon._emit_health_break).
_WARN_TEXT = ("Sếp ngồi quá lâu rồi. Đã tự động lưu công việc. "
              "Màn hình sẽ khóa sau 10 giây!")
_WARN_TO_LOCK_MS = 10_000   # 10 giây từ lúc cảnh báo tới lúc khoá
_DEFAULT_BREAK_S = 300      # 05:00


def _require_qt():
    """Import PyQt5 trễ, báo cài rõ nếu thiếu."""
    try:
        from PyQt5 import QtCore, QtGui, QtWidgets  # noqa: F401
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("Thiếu 'PyQt5'. Cài: pip install PyQt5") from exc
    return QtCore, QtGui, QtWidgets


def _ws_uri() -> str:
    try:
        from core.config import settings
        return f"ws://{settings.ws_host}:{settings.ws_port}"
    except Exception as exc:  # noqa: BLE001 — thiếu config không được chặn
        logger.warning("Không đọc được config WS (mặc định): %s", exc)
        return "ws://localhost:8765"


def _busy_now() -> bool:
    """CHỐT CỨNG: Sếp đang họp / share màn hình / trình chiếu -> KHÔNG che màn.

    Sinh sau sự cố 05/08/2026 (khiên đen bung giữa buổi phỏng vấn TEKY).
    Đọc lỗi cũng coi là BẬN — thà lỡ một ca nghỉ còn hơn phá cuộc họp của Sếp.
    """
    try:
        from core.presence import busy_reason
        reason = busy_reason()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không đọc được trạng thái màn hình (%s) -> KHÔNG che màn.", exc)
        return True
    if reason:
        logger.info("Health Guard: KHÔNG che màn — %s.", reason)
        return True
    return False


def _auto_save() -> bool:
    """Lưu công việc hiện tại bằng Ctrl+S. Guard pyautogui; lỗi -> False (không sập)."""
    try:
        import pyautogui  # type: ignore
        pyautogui.FAILSAFE = True   # kéo chuột vào góc màn hình = thoát khẩn cấp
        pyautogui.hotkey("ctrl", "s")
        logger.info("Health Guard: đã gửi Ctrl+S auto-save.")
        return True
    except Exception as exc:  # noqa: BLE001 — thiếu pyautogui / lỗi không được sập
        logger.warning("Auto-save (Ctrl+S) lỗi/thiếu pyautogui: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Worker WebSocket — nghe lệnh health_break từ server
# ---------------------------------------------------------------------------
def _build_ws_worker(QtCore):
    class WSWorker(QtCore.QThread):
        break_requested = QtCore.pyqtSignal(int)   # số giây khoá màn hình

        def __init__(self, uri: str) -> None:
            super().__init__()
            self._uri = uri
            self._running = True

        def stop(self) -> None:
            self._running = False

        def run(self) -> None:
            import asyncio
            try:
                import websockets  # noqa: F401
            except ModuleNotFoundError:
                logger.warning("Thiếu 'websockets' -> Health Guard không nghe được server.")
                return
            try:
                asyncio.run(self._loop())
            except Exception as exc:  # noqa: BLE001
                logger.info("WS health worker dừng: %s", exc)

        async def _loop(self) -> None:
            import asyncio
            import websockets
            while self._running:
                try:
                    async with websockets.connect(self._uri) as ws:
                        logger.info("Health Guard đã nối server.")
                        async for raw in ws:
                            self._dispatch(raw)
                except Exception as exc:  # noqa: BLE001 — rớt thì thử lại
                    logger.info("Health WS chưa nối (%s) — thử lại 2s.", exc)
                    await asyncio.sleep(2)

        def _dispatch(self, raw: str) -> None:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return
            if data.get("type") == "health_break":
                try:
                    secs = int(data.get("break_s") or _DEFAULT_BREAK_S)
                except (TypeError, ValueError):
                    secs = _DEFAULT_BREAK_S
                self.break_requested.emit(max(5, secs))

    return WSWorker


# ---------------------------------------------------------------------------
# App: Toast cảnh báo + Khiên đen + Controller
# ---------------------------------------------------------------------------
def build_app(demo_seconds: int | None = None):
    """Dựng QApplication + Health Guard. Trả (app, controller, worker|None)."""
    QtCore, QtGui, QtWidgets = _require_qt()
    WSWorker = _build_ws_worker(QtCore)

    class WarningToast(QtWidgets.QWidget):
        """Bong bóng cảnh báo nổi giữa-trên màn hình, tự đóng sau khi khiên hiện."""

        def __init__(self, text: str):
            super().__init__()
            self.setWindowFlags(
                QtCore.Qt.FramelessWindowHint
                | QtCore.Qt.WindowStaysOnTopHint
                | QtCore.Qt.Tool
            )
            self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
            lab = QtWidgets.QLabel(text, self)
            lab.setWordWrap(True)
            lab.setAlignment(QtCore.Qt.AlignCenter)
            lab.setStyleSheet(
                "QLabel{"
                " background: rgba(200,40,60,0.95);"   # đỏ cảnh báo
                " color: #FFFFFF; font-size: 16px; font-weight: bold;"
                " border: 2px solid #FFD2D2; border-radius: 16px;"
                " padding: 14px 20px;"
                "}"
            )
            lay = QtWidgets.QVBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(lab)
            self.setFixedWidth(440)
            self.adjustSize()
            scr = QtWidgets.QApplication.primaryScreen().availableGeometry()
            self.move(scr.center().x() - self.width() // 2, scr.top() + 80)
            # Tự đóng sau khi khiên đã lên (đỡ chồng lấn).
            QtCore.QTimer.singleShot(_WARN_TO_LOCK_MS + 1500, self.close)

    class BlackoutOverlay(QtWidgets.QWidget):
        """Khiên đen toàn màn hình + đếm ngược; chặn input cơ bản; tự đóng khi hết giờ."""

        def __init__(self, seconds: int):
            super().__init__()
            self._remaining = max(1, int(seconds))
            self.setWindowFlags(
                QtCore.Qt.FramelessWindowHint
                | QtCore.Qt.WindowStaysOnTopHint
            )
            self.setStyleSheet("background-color: #000000;")
            self.setCursor(QtCore.Qt.BlankCursor)
            # Phủ TẤT CẢ màn hình (gộp geometry mọi screen).
            geo = QtCore.QRect()
            for scr in QtWidgets.QApplication.screens():
                geo = geo.united(scr.geometry())
            self.setGeometry(geo)

            self._clock = QtWidgets.QLabel(self._fmt(self._remaining), self)
            self._clock.setAlignment(QtCore.Qt.AlignCenter)
            self._clock.setStyleSheet(
                "color: #FF5555; font-size: 140px; font-weight: 800;"
                " font-family: 'Consolas','Courier New',monospace;"
            )
            cap = QtWidgets.QLabel("Nghỉ ngơi một chút nhé Sếp 💪 — màn hình sẽ tự mở lại.", self)
            cap.setAlignment(QtCore.Qt.AlignCenter)
            cap.setStyleSheet("color: #888888; font-size: 20px;")

            lay = QtWidgets.QVBoxLayout(self)
            lay.addStretch(1)
            lay.addWidget(self._clock, 0, QtCore.Qt.AlignCenter)
            lay.addWidget(cap, 0, QtCore.Qt.AlignCenter)
            lay.addStretch(1)

            self._timer = QtCore.QTimer(self)
            self._timer.timeout.connect(self._tick)

        @staticmethod
        def _fmt(s: int) -> str:
            s = max(0, int(s))
            return f"{s // 60:02d}:{s % 60:02d}"

        def start(self):
            self.show()
            self.raise_()
            self.activateWindow()
            self.setFocusPolicy(QtCore.Qt.StrongFocus)
            self.setFocus()
            try:
                self.grabKeyboard()   # nuốt phím để User khỏi can thiệp
            except Exception:  # noqa: BLE001
                pass
            self._timer.start(1000)

        def _tick(self):
            self._remaining -= 1
            if self._remaining <= 0:
                self._release()
            else:
                self._clock.setText(self._fmt(self._remaining))

        def _release(self):
            self._timer.stop()
            try:
                self.releaseKeyboard()
            except Exception:  # noqa: BLE001
                pass
            self.close()

        # --- CHẶN sự kiện cơ bản (nuốt click & gõ phím) ---
        def keyPressEvent(self, e):      e.accept()
        def keyReleaseEvent(self, e):    e.accept()
        def mousePressEvent(self, e):    e.accept()
        def mouseReleaseEvent(self, e):  e.accept()
        def mouseDoubleClickEvent(self, e): e.accept()
        def mouseMoveEvent(self, e):     e.accept()
        def contextMenuEvent(self, e):   e.accept()
        def wheelEvent(self, e):         e.accept()

    class HealthController(QtCore.QObject):
        """Điều phối: cảnh báo -> auto-save -> (10s) -> khiên đen."""

        def __init__(self):
            super().__init__()
            self._toast = None
            self._overlay = None

        def trigger(self, break_s: int):
            logger.info("Health Guard: nhận lệnh ép nghỉ (%ds).", break_s)
            if _busy_now():                      # chốt cứng lớp 1
                return
            # 1) Cảnh báo
            self._toast = WarningToast(_WARN_TEXT)
            self._toast.show()
            # 2) Auto-save NGAY (trước khi khoá) — an toàn dữ liệu
            _auto_save()
            # 3) Sau 10 giây -> khiên đen
            QtCore.QTimer.singleShot(_WARN_TO_LOCK_MS, lambda: self._lock(break_s))

        def _lock(self, break_s: int):
            # Chốt cứng lớp 2: 10 giây vừa rồi Sếp có thể VỪA vào cuộc họp.
            if _busy_now():
                if self._toast is not None:
                    self._toast.close()
                    self._toast = None
                return
            self._overlay = BlackoutOverlay(break_s)
            self._overlay.start()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    ctrl = HealthController()

    if demo_seconds is not None:
        # Demo: khoá ngay (bỏ qua cảnh báo 10s) để xem KHIÊN ĐEN nhanh.
        QtCore.QTimer.singleShot(300, lambda: ctrl._lock(int(demo_seconds)))
        return app, ctrl, None

    worker = WSWorker(_ws_uri())
    worker.break_requested.connect(ctrl.trigger)
    worker.start()
    return app, ctrl, worker


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Health Guard — khiên đen ép nghỉ.")
    ap.add_argument("--demo", type=int, default=None,
                    help="Thử KHIÊN ĐEN N giây, không cần server.")
    args = ap.parse_args()

    app, ctrl, worker = build_app(demo_seconds=args.demo)
    rc = app.exec_()
    if worker is not None:
        worker.stop()
        worker.wait(1000)
    sys.exit(rc)


if __name__ == "__main__":
    # Chống CHẠY ĐÔI — 2 bản health_guard nghĩa là 2 lần phủ khiên đen chồng nhau.
    from core.single_instance import ensure_single
    ensure_single("health_guard")
    main()


__all__ = ["build_app", "main"]
