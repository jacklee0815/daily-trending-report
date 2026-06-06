@echo off
REM Windows 一键安装脚本
REM 用法: scripts\install.bat

echo === Installing dependencies ===
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pytest --quiet

echo.
echo === Running tests ===
python -m pytest tests/ -v

echo.
echo === Done ===
echo Next: copy .env.example to .env and fill in your Gmail credentials
echo Then: python scripts\run_local.py --no-scrape  (after one run with scrape)
