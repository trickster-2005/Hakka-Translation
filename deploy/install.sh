#!/usr/bin/env bash
# 產生並安裝 systemd 服務（使用者與路徑自動偵測，不用手改）
#
#   在專案根目錄執行：  bash deploy/install.sh
#
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="$(id -un)"
PY="$DIR/.venv/bin/python"
UNIT=/etc/systemd/system/hakka-bot.service

if [ ! -x "$PY" ]; then
  echo "✗ 找不到 $PY"
  echo "  請先建立 venv：  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
if [ ! -f "$DIR/.env" ]; then
  echo "✗ 找不到 $DIR/.env"
  echo "  請先：  cp .env.example .env  然後填入 TELEGRAM_BOT_TOKEN"
  exit 1
fi

echo "使用者 : $USER_NAME"
echo "路徑   : $DIR"
echo "寫入   : $UNIT"

sudo tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=Hakka (Mandarin -> Hakka) Telegram Bot
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=10

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$DIR
ExecStart=$PY bot.py
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl reset-failed hakka-bot.service 2>/dev/null || true
sudo systemctl enable --now hakka-bot.service

echo
echo "✓ 完成。看即時日誌： journalctl -u hakka-bot -f"
