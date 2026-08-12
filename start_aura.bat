@echo off
REM ============================================================
REM  start_aura.bat - Khoi dong AURA
REM  - Cua so 1 (hien): Server + Daemon (log de debug)
REM  - Cua so 2 (an)  : Mascot Miku (ui.mascot, khong can console)
REM ============================================================

REM Chuyen ve thu muc chua file .bat nay (goc du an AURA)
cd /d "%~dp0"

REM --- XA RAM THAN TOC: ep Ollama nha model NGAY sau khi tra loi (may 12GB RAM) ---
REM Bien moi truong nay duoc Ollama server ke thua neu duoc khoi chay tu day.
REM AURA cung gui keep_alive kem moi request (xem core/llm.py) nen thang ca muc server.
set "OLLAMA_KEEP_ALIVE=0"

REM --- Chon Python: dung venv THAT cua du an (KHONG PHAI .venv - rong, thieu deps) ---
set "PY=python"
if exist "venv\Scripts\pythonw.exe" set "PYW=venv\Scripts\pythonw.exe"
if exist "venv\Scripts\python.exe"  set "PY=venv\Scripts\python.exe"
if not defined PYW set "PYW=pythonw"

echo ============================================
echo   AURA dang khoi dong...
echo   - Server/Daemon : cua so nay (de xem log)
echo   - Desktop Chat  : http://localhost:8765/chat.html
echo   - Mascot        : DA TAT (chuyen sang Desktop App)
echo   Dong cua so nay = tat AURA.
echo ============================================
echo.

REM --- Cua so 2: Mascot da tat theo yeu cau cua Sep ---
REM start "" /b cmd /c "timeout /t 3 >nul & %PYW% -m ui.mascot"

REM --- Cua so 3: HEALTH GUARD (ep nghi 60p/30p) ---
REM BUG DA SUA 24/07/2026: truoc day file .bat nay KHONG bat health_guard.
REM Daemon van dem gio va phat lenh "ep nghi" dung han (log co 4 lan trong 1 ngay),
REM nhung KHONG CO TIEN TRINH NAO NGHE -> tinh nang ep nghi chua tung song.
start "" /b cmd /c "timeout /t 5 >nul & %PYW% -m ui.health_guard"

REM --- Cua so 1 (chinh): Server + Daemon, chay o cua so hien tai de thay log ---

:: ĐÂY LÀ DÒNG QUAN TRỌNG NHẤT: Bật môi trường ảo trước khi chạy
call venv\Scripts\activate.bat

:: Bây giờ gọi python nó sẽ lấy đúng python trong venv
python main.py

REM Khi main.py thoat (dong cua so / Ctrl+C), bao da tat
echo.
echo AURA da tat.
pause
