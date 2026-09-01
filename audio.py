"""WAV -> OGG/Opus or MP3 conversion via ffmpeg (stdin/stdout, no temp files)."""
from __future__ import annotations

import shutil
import subprocess

from hakka_client import HakkaError

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

_ARGS = {
    "ogg": ["-c:a", "libopus", "-b:a", "32k", "-application", "voip", "-f", "ogg"],
    "mp3": ["-c:a", "libmp3lame", "-q:a", "4", "-f", "mp3"],
}


def convert(wav: bytes, fmt: str) -> bytes:
    if fmt not in _ARGS:
        raise HakkaError(f"未知音檔格式：{fmt}")
    try:
        proc = subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
             *_ARGS[fmt], "pipe:1"],
            input=wav,
            capture_output=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise HakkaError("找不到 ffmpeg，請安裝並加入 PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise HakkaError("音檔轉換逾時") from exc
    if proc.returncode != 0 or not proc.stdout:
        detail = proc.stderr.decode(errors="ignore")[:200]
        raise HakkaError(f"音檔轉換失敗：{detail}")
    return proc.stdout
