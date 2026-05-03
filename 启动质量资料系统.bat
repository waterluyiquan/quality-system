@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 正在创建本地运行环境...
  python -m venv .venv
)

echo 正在检查依赖...
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo 正在启动资料问答与自动填表工具...
start "" http://127.0.0.1:8501
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false
