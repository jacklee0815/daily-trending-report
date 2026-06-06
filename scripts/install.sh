#!/usr/bin/env bash
# Unix/macOS 一键安装脚本
# 用法: bash scripts/install.sh

set -e

echo "=== Installing dependencies ==="
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m pip install pytest --quiet

echo
echo "=== Running tests ==="
python3 -m pytest tests/ -v

echo
echo "=== Done ==="
echo "Next: cp .env.example .env  and fill in Gmail credentials"
echo "Then: python3 scripts/run_local.py"
