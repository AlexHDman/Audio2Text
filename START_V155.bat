@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo Python venv not found. Existing environment is required.
  pause
  exit /b 1
)
"venv\Scripts\python.exe" -B -X utf8 "audio_pipeline_cuda_v155_FIXED.py" %*
set "A2T_EXIT=%ERRORLEVEL%"
echo.
echo Exit code: %A2T_EXIT% ^(0=processed, 2=partial/review required, 1=error^)
echo Outputs: %~dp0output
pause
exit /b %A2T_EXIT%
