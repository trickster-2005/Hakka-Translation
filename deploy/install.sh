#!/usr/bin/env bash
# 產生並安裝 systemd 服務（使用者與路徑自動偵測，不用手改）。
#
#   bash deploy/install.sh                # 只裝 bot 服務
#   bash deploy/install.sh --autoupdate   # 另外裝「定時從 GitHub 自動更新」timer
#
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="$(id -un)"
PY="$DIR/.venv/bin/python"

WANT_AUTOUPDATE=0
[ "${1:-}" = "--autoupdate" ] && WANT_AUTOUPDATE=1

# --- 前置檢查 --------------------------------------------------------
if [ ! -x "$PY" ]; then
  echo "✗ 找不到 $PY"
  echo "  請先：  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
if [ ! -f "$DIR/.env" ]; then
  echo "✗ 找不到 $DIR/.env"
  echo "  請先：  cp .env.example .env  然後填入 TELEGRAM_BOT_TOKEN"
  exit 1
fi

echo "使用者 : $USER_NAME"
echo "路徑   : $DIR"

# --- bot 服務 -------------------------------------------------------
sudo tee /etc/systemd/system/hakka-bot.service >/dev/null <<EOF
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
echo "✓ hakka-bot.service 已啟用"

# --- 自動更新 timer（選用）----------------------------------------
if [ "$WANT_AUTOUPDATE" -eq 1 ]; then
  sudo tee /etc/systemd/system/hakka-bot-update.service >/dev/null <<EOF
[Unit]
Description=Check GitHub for Hakka bot updates
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$DIR/deploy/autoupdate.sh
EOF

  sudo tee /etc/systemd/system/hakka-bot-update.timer >/dev/null <<EOF
[Unit]
Description=Periodically update Hakka bot from GitHub

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable --now hakka-bot-update.timer
  echo "✓ hakka-bot-update.timer 已啟用（每 15 分鐘檢查 GitHub）"
fi

echo
echo "狀態： systemctl status hakka-bot --no-pager"
echo "日誌： journalctl -u hakka-bot -f"
[ "$WANT_AUTOUPDATE" -eq 1 ] && echo "更新紀錄： journalctl -t hakka-autoupdate"
