#!/usr/bin/env bash
# 檢查 GitHub 有沒有新版本，有就更新並重啟 bot。
# 由 hakka-bot-update.service（root）定時呼叫；git / pip 以專案擁有者身分執行。
# 想手動跑一次也可以：  sudo bash deploy/autoupdate.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE=hakka-bot.service
OWNER="$(stat -c '%U' "$DIR")"

if [ "$(id -u)" -eq 0 ]; then
    as_owner() { runuser -u "$OWNER" -- "$@"; }
else
    as_owner() { "$@"; }
fi

git config --global --add safe.directory "$DIR" 2>/dev/null || true

as_owner git -C "$DIR" fetch --quiet origin

LOCAL="$(as_owner git -C "$DIR" rev-parse HEAD)"
if ! REMOTE="$(as_owner git -C "$DIR" rev-parse '@{u}' 2>/dev/null)"; then
    logger -t hakka-autoupdate "目前分支沒有設定 upstream，略過"
    exit 0
fi

[ "$LOCAL" = "$REMOTE" ] && exit 0   # 沒有更新

logger -t hakka-autoupdate "更新 ${LOCAL:0:7} -> ${REMOTE:0:7}"
as_owner git -C "$DIR" reset --hard "$REMOTE"

if ! as_owner git -C "$DIR" diff --quiet "$LOCAL" "$REMOTE" -- requirements.txt; then
    logger -t hakka-autoupdate "requirements.txt 有變，重裝套件"
    as_owner "$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"
fi

if [ "$(id -u)" -eq 0 ]; then
    systemctl restart "$SERVICE"
else
    sudo systemctl restart "$SERVICE"
fi
logger -t hakka-autoupdate "已重啟 $SERVICE @ ${REMOTE:0:7}"
