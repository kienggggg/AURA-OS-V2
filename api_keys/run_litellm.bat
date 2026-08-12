@echo off
REM Khởi động LiteLLM proxy cho AURA tại http://localhost:4000
cd /d "%~dp0.."
echo Nap key tu litellm\keys.env ...
for /f "usebackq eol=# tokens=1,* delims==" %%a in ("litellm\keys.env") do (
  if not "%%~a"=="" set "%%a=%%b"
)
echo Khoi dong LiteLLM proxy: http://localhost:4000  (Ctrl+C de dung)
venv\Scripts\litellm.exe --config litellm\config.yaml --port 4000
