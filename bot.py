"""華語 -> 客語 Telegram bot（私人使用）。

輸入華語文字，回覆：
  • 客語漢字（預設海陸腔）
  • 客語拼音（帶調）
  • 發音音檔（可下載）

資料來源：臺灣客語語音資料庫（客家委員會）https://speech.hakka.gov.tw
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telegram import BotCommand, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from audio import convert
from hakka_client import DIALECTS, VOICE_NAMES, HakkaClient, HakkaError
from usage import UsageTracker

# --------------------------------------------------------------------------
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not TOKEN:
    raise SystemExit("請在 .env 設定 TELEGRAM_BOT_TOKEN")

ALLOWED_USER_IDS = {
    int(x) for x in os.getenv("ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x
}
COOKIE = os.getenv("HAKKA_COOKIE", "").strip() or None
MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "180"))
DAILY_CHAR_LIMIT = int(os.getenv("DAILY_CHAR_LIMIT", "1000"))
IMPERSONATE = os.getenv("HTTP_IMPERSONATE", "chrome").strip() or "chrome"

SETTINGS_PATH = Path(os.getenv("SETTINGS_FILE", "settings.json"))
DEFAULT_SETTINGS = {
    "dialect": os.getenv("HAKKA_DIALECT", "hailu").strip(),
    "gender": os.getenv("HAKKA_VOICE", "F").strip().upper(),
    # audio delivery: audio(mp3卡片) | doc(mp3檔案,不進播放器) | voice(語音訊息,會自動播放)
    #                 | both | wav | off
    "audio": os.getenv("SEND_AUDIO_AS", "audio").strip().lower(),
    "speaking_rate": float(os.getenv("SPEAKING_RATE", "1.0")),
}

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("hakka-bot")

client = HakkaClient(cookie=COOKIE, impersonate=IMPERSONATE)
usage = UsageTracker("daily_usage.json", DAILY_CHAR_LIMIT)


# ---- settings persistence -------------------------------------------------
def load_settings() -> dict:
    data = dict(DEFAULT_SETTINGS)
    try:
        data.update(json.loads(SETTINGS_PATH.read_text("utf-8")))
    except (OSError, ValueError):
        pass
    return data


def save_settings(data: dict) -> None:
    try:
        SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    except OSError as exc:
        log.warning("無法儲存設定：%s", exc)


settings = load_settings()


# ---- helpers ------------------------------------------------------------
def authorised(update: Update) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    user = update.effective_user
    return bool(user and user.id in ALLOWED_USER_IDS)


def settings_summary() -> str:
    d = settings["dialect"]
    label = DIALECTS.get(d, {}).get("label", d)
    gender_label = "女聲" if settings["gender"] == "F" else "男聲"
    return (
        f"腔調：{label}（{d}）\n"
        f"語音：{gender_label}\n"
        f"音檔格式：{settings['audio']}\n"
        f"語速：{settings['speaking_rate']}"
    )


async def deny(update: Update) -> None:
    await update.message.reply_text(
        "這是私人使用的 bot。\n"
        f"你的 Telegram user id 是 {update.effective_user.id}，"
        "若這是你的 bot，請把它加進 .env 的 ALLOWED_USER_IDS。"
    )


# ---- command handlers --------------------------------------------------
async def cmd_start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorised(update):
        return await deny(update)
    await update.message.reply_text(
        "直接傳華語句子給我，我會回覆客語漢字、拼音與發音音檔。\n\n"
        "指令：\n"
        "/voice f|m — 切換女聲 / 男聲\n"
        "/dialect hailu|sixian — 切換海陸腔 / 四縣腔\n"
        "/audio audio|doc|voice|both|wav|off — 音檔輸出方式\n"
        "　（voice 會自動接續播放；想避免請用 audio 或 doc）\n"
        "/rate 0.8-1.2 — 語速\n"
        "/settings — 目前設定\n"
        "/quota — 今日用量\n"
        "/id — 顯示你的 user id\n\n"
        f"目前設定：\n{settings_summary()}\n\n"
        "翻譯與語音來源：臺灣客語語音資料庫（客家委員會）\n"
        "https://speech.hakka.gov.tw/"
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)


async def cmd_id(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"你的 Telegram user id：{update.effective_user.id}")


async def cmd_settings(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorised(update):
        return await deny(update)
    await update.message.reply_text(settings_summary())


async def cmd_quota(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorised(update):
        return await deny(update)
    used, limit = usage.peek()
    mode = "帳號 10000" if COOKIE else "匿名 1000"
    await update.message.reply_text(
        f"今日已用約 {used} 字 / 上限 {limit} 字（{mode} 額度）。"
    )


async def cmd_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorised(update):
        return await deny(update)
    arg = (ctx.args[0].upper() if ctx.args else "")
    if arg not in ("F", "M"):
        return await update.message.reply_text("用法：/voice f 或 /voice m")
    settings["gender"] = arg
    save_settings(settings)
    await update.message.reply_text(f"語音已切換為 {'女聲' if arg == 'F' else '男聲'}。")


async def cmd_dialect(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorised(update):
        return await deny(update)
    arg = (ctx.args[0].lower() if ctx.args else "")
    if arg not in DIALECTS:
        return await update.message.reply_text("用法：/dialect hailu 或 /dialect sixian")
    settings["dialect"] = arg
    save_settings(settings)
    await update.message.reply_text(f"腔調已切換為 {DIALECTS[arg]['label']}。")


async def cmd_audio(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorised(update):
        return await deny(update)
    arg = (ctx.args[0].lower() if ctx.args else "")
    if arg not in ("audio", "doc", "voice", "both", "wav", "off"):
        return await update.message.reply_text(
            "用法：/audio audio|doc|voice|both|wav|off\n"
            "audio=mp3音樂卡片　doc=mp3檔案(不進播放器)　"
            "voice=語音訊息(會自動播放)　wav=wav檔案　off=不送"
        )
    settings["audio"] = arg
    save_settings(settings)
    await update.message.reply_text(f"音檔輸出方式已設為 {arg}。")


async def cmd_rate(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorised(update):
        return await deny(update)
    try:
        rate = float(ctx.args[0])
        assert 0.5 <= rate <= 2.0
    except (IndexError, ValueError, AssertionError):
        return await update.message.reply_text("用法：/rate 1.0（範圍 0.5–2.0）")
    settings["speaking_rate"] = rate
    save_settings(settings)
    await update.message.reply_text(f"語速已設為 {rate}。")


# ---- main text handler ------------------------------------------------
async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorised(update):
        return await deny(update)

    text = (update.message.text or "").strip()
    if not text:
        return
    if len(text) > MAX_INPUT_CHARS:
        return await update.message.reply_text(
            f"一次最多 {MAX_INPUT_CHARS} 字，請縮短再試。"
        )

    allowed, used = usage.try_add(len(text))
    if not allowed:
        return await update.message.reply_text(
            f"今日翻譯額度用完了（已用 {used} 字 / 上限 {DAILY_CHAR_LIMIT} 字）。"
            "明天再試，或在 .env 設定 HAKKA_COOKIE 使用帳號額度。"
        )

    dialect = settings["dialect"]
    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    try:
        tr = await asyncio.to_thread(client.translate, text, dialect)
    except HakkaError as exc:
        return await update.message.reply_text(f"⚠️ 翻譯失敗：{exc}")

    if not tr.hanzi:
        return await update.message.reply_text("⚠️ 沒有翻譯結果。")

    body = f"<b>客語漢字（{tr.label}）</b>\n{tr.hanzi}"
    if tr.pinyin:
        body += f"\n\n<b>拼音</b>\n{tr.pinyin}"
    await update.message.reply_text(body, parse_mode=ParseMode.HTML)

    mode = settings["audio"]
    if mode == "off":
        return

    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_VOICE)
    try:
        wav = await asyncio.to_thread(
            client.synthesize, tr.hanzi, dialect, settings["gender"],
            settings["speaking_rate"],
        )
    except HakkaError as exc:
        return await update.message.reply_text(f"⚠️ 語音合成失敗：{exc}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"hakka-{dialect}-{stamp}"
    perf = f"客語{tr.label}{'女聲' if settings['gender'] == 'F' else '男聲'}"
    caption = tr.hanzi[:1000]

    try:
        if mode in ("voice", "both"):
            ogg = await asyncio.to_thread(convert, wav, "ogg")
            await update.message.reply_voice(voice=_named(ogg, base + ".ogg"))
        if mode in ("audio", "both"):
            mp3 = await asyncio.to_thread(convert, wav, "mp3")
            await update.message.reply_audio(
                audio=_named(mp3, base + ".mp3"),
                title=tr.hanzi[:64],
                performer=perf,
                caption=caption if mode == "audio" else None,
            )
        if mode == "doc":
            # 以「檔案」形式送出，不會進入 Telegram 音樂播放器 / 不會自動接續播放
            mp3 = await asyncio.to_thread(convert, wav, "mp3")
            await update.message.reply_document(
                document=_named(mp3, base + ".mp3"),
                caption=caption,
                disable_content_type_detection=True,
            )
        if mode == "wav":
            await update.message.reply_document(
                document=_named(wav, base + ".wav"),
                caption=caption,
                disable_content_type_detection=True,
            )
    except HakkaError as exc:
        await update.message.reply_text(f"⚠️ 音檔處理失敗：{exc}")


def _named(data: bytes, name: str) -> io.BytesIO:
    buf = io.BytesIO(data)
    buf.name = name
    return buf


# ---- bootstrap -------------------------------------------------------
async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands(
        [
            BotCommand("start", "說明與目前設定"),
            BotCommand("voice", "切換女聲 / 男聲"),
            BotCommand("dialect", "切換海陸腔 / 四縣腔"),
            BotCommand("audio", "音檔輸出方式"),
            BotCommand("rate", "語速"),
            BotCommand("settings", "目前設定"),
            BotCommand("quota", "今日用量"),
            BotCommand("id", "顯示你的 user id"),
        ]
    )
    mode = "帳號額度（cookie）" if COOKIE else "匿名額度"
    log.info("bot 啟動完成；%s；allowlist=%s", mode, ALLOWED_USER_IDS or "（不限制）")


def main() -> None:
    app = Application.builder().token(TOKEN).post_init(_post_init).build()
    app.add_handler(CommandHandler(["start", "help"], cmd_start))
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("quota", cmd_quota))
    app.add_handler(CommandHandler("voice", cmd_voice))
    app.add_handler(CommandHandler("dialect", cmd_dialect))
    app.add_handler(CommandHandler("audio", cmd_audio))
    app.add_handler(CommandHandler("rate", cmd_rate))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
