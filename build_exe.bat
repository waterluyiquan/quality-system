@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --noconsole --name "质量资料系统" launcher.py

echo.
echo 已生成：dist\质量资料系统.exe
pause
