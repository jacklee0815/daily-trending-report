#!/bin/bash
# Daily Trending Report - VPS 部署脚本 (Rocky Linux 8 / CentOS 8)
# 用法: sudo bash install_vps.sh

set -e

APP_DIR="/opt/daily-trending-report"
PYTHON_VERSION="3.11"
VENV_DIR="$APP_DIR/venv"

echo "=========================================="
echo "  Daily Trending Report VPS Installer"
echo "  Target: Rocky Linux 8 / CentOS 8"
echo "=========================================="

# 1. 安装系统依赖
echo ""
echo "[1/6] Installing system dependencies ..."
dnf install -y python3.11 python3.11-pip python3.11-devel gcc git || {
    # 如果 3.11 不在默认源, 尝试 epel 或 dnf module
    dnf install -y epel-release
    dnf module -y install python39
    dnf install -y python39-pip python39-devel gcc git
    PYTHON_VERSION="3.9"
}

# 2. 克隆或更新代码
echo ""
echo "[2/6] Setting up code ..."
if [ -d "$APP_DIR/.git" ]; then
    echo "  → Updating existing repo ..."
    cd "$APP_DIR"
    git pull origin master
else
    echo "  → Cloning repo ..."
    git clone https://github.com/jacklee0815/daily-trending-report.git "$APP_DIR"
    cd "$APP_DIR"
fi

# 3. 创建 virtualenv
echo ""
echo "[3/6] Creating virtualenv ..."
if [ ! -d "$VENV_DIR" ]; then
    python${PYTHON_VERSION} -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# 4. 安装依赖
echo ""
echo "[4/6] Installing Python dependencies ..."
pip install --upgrade pip
pip install -r requirements.txt
pip install fpdf2  # PDF 附件

# 5. 配置环境变量
echo ""
echo "[5/6] Setting up environment ..."
ENV_FILE="$APP_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" << 'ENVEOF'
# Gmail 配置
GMAIL_ADDRESS=你的Gmail地址
GMAIL_APP_PASSWORD=你的Gmail应用专用密码
RECIPIENT_EMAIL=收件邮箱

# LLM (可选)
# LLM_API_KEY=sk-xxx
# LLM_BASE_URL=https://api.openai.com/v1
# LLM_MODEL=gpt-4o-mini
ENVEOF
    echo "  → Created .env file. Please edit it with your credentials:"
    echo "    vi $ENV_FILE"
else
    echo "  → .env already exists, skipping."
fi

# 6. 设置 cron 定时任务
echo ""
echo "[6/6] Setting up cron job ..."
CRON_CMD="0 6 * * * cd $APP_DIR && source $VENV_DIR/bin/activate && python -m src.main >> $APP_DIR/cron.log 2>&1"
(crontab -l 2>/dev/null | grep -v "daily-trending-report"; echo "$CRON_CMD") | crontab -
echo "  → Cron job installed: every day at 6:00 AM"

echo ""
echo "=========================================="
echo "  ✅ Installation complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your Gmail credentials:"
echo "     vi $APP_DIR/.env"
echo ""
echo "  2. Test manually:"
echo "     cd $APP_DIR && source venv/bin/activate"
echo "     python -m src.main"
echo ""
echo "  3. Check cron:"
echo "     crontab -l"
echo ""
echo "  4. View logs:"
echo "     tail -f $APP_DIR/cron.log"
echo ""
echo "  5. Update code (when needed):"
echo "     cd $APP_DIR && git pull origin master"
echo ""
