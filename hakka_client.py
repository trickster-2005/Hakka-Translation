"""Client for the 臺灣客語語音資料庫 (speech.hakka.gov.tw) web endpoints.

This wraps the same XHR calls the official website makes:

  POST /Translation/Translate   {Code, Before}  -> 翻譯 / 轉拼音
  POST /TTS/Synthesize          {...}           -> 回傳 WAV bytes

The site sits behind a WAF that rejects non-browser TLS fingerprints on the
POST endpoints (plain requests/httpx get HTTP 500), so we use curl_cffi with
Chrome impersonation.

Anonymous use works out of the box (limit ~1000 字/日 by IP). Passing a logged-in
Cookie string raises the quota to 10000 字/日 on the account.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from curl_cffi import requests as cr

BASE = "https://speech.hakka.gov.tw"

# dialect -> translate codes + TTS language code + human label
DIALECTS: dict[str, dict[str, str]] = {
    "hailu": {
        "zh_hk": "hakka_hailu_zh_hk",          # 華語 -> 海陸客語漢字
        "hk_py": "hakka_hailu_hk_py_tone",     # 海陸客語漢字 -> 海陸拼音(帶調)
        "hk_zh": "hakka_hk_zh",                # 客語漢字 -> 華語
        "tts_lang": "hak-hoi-TW",
        "label": "海陸腔",
    },
    "sixian": {
        "zh_hk": "hakka_zh_hk",
        "hk_py": "hakka_hk_py_tone",
        "hk_zh": "hakka_hk_zh",
        "tts_lang": "hak-xi-TW",
        "label": "四縣腔",
    },
}

# dialect -> gender -> TTS voice name
VOICE_NAMES: dict[str, dict[str, str]] = {
    "hailu": {"F": "hak-hoi-TW-vs2-F01", "M": "hak-hoi-TW-vs2-M01"},
    "sixian": {"F": "hak-xi-TW-vs2-F01", "M": "hak-xi-TW-vs2-M01"},
}


class HakkaError(RuntimeError):
    """Raised when the upstream service fails or returns an error payload."""


@dataclass
class Translation:
    source: str
    hanzi: str
    pinyin: str
    dialect: str

    @property
    def label(self) -> str:
        return DIALECTS[self.dialect]["label"]


class HakkaClient:
    def __init__(
        self,
        cookie: str | None = None,
        impersonate: str = "chrome",
        timeout: int = 30,
    ) -> None:
        self.timeout = timeout
        self._lock = Lock()  # curl_cffi Session isn't thread-safe
        self._session = cr.Session(impersonate=impersonate)
        # Match what the site's own fetch() sends (Content-Type is added by
        # curl_cffi for json=). Do NOT add headers the browser doesn't send
        # (e.g. X-Requested-With) — the WAF fingerprints on that.
        self._session.headers.update(
            {
                "Origin": BASE,
                "Referer": f"{BASE}/Translation/Online",
            }
        )
        if cookie:
            self._session.headers["Cookie"] = cookie.strip()

    # -- low level ---------------------------------------------------------
    def _translate(self, code: str, text: str) -> str:
        try:
            with self._lock:
                resp = self._session.post(
                    f"{BASE}/Translation/Translate",
                    json={"Code": code, "Before": text},
                    timeout=self.timeout,
                )
        except Exception as exc:  # network / TLS
            raise HakkaError(f"連線翻譯服務失敗：{exc}") from exc

        if resp.status_code != 200:
            raise HakkaError(
                f"翻譯服務回應 HTTP {resp.status_code}"
                "（可能被 WAF 阻擋或服務忙碌，稍後再試）"
            )
        try:
            data = resp.json()
        except Exception as exc:
            raise HakkaError("翻譯服務回應非 JSON（可能被導向錯誤頁）") from exc

        if not data.get("success"):
            raise HakkaError(data.get("message") or "翻譯失敗（未知原因）")
        return (data.get("message") or "").strip()

    # -- public -----------------------------------------------------------
    def translate(self, text: str, dialect: str = "hailu") -> Translation:
        """華語 -> 客語漢字 + 拼音。"""
        if dialect not in DIALECTS:
            raise HakkaError(f"不支援的腔調：{dialect}")
        codes = DIALECTS[dialect]
        hanzi = self._translate(codes["zh_hk"], text)
        pinyin = self._translate(codes["hk_py"], hanzi) if hanzi else ""
        return Translation(source=text, hanzi=hanzi, pinyin=pinyin, dialect=dialect)

    def to_mandarin(self, hakka_text: str, dialect: str = "hailu") -> str:
        """客語漢字 -> 華語。"""
        return self._translate(DIALECTS[dialect]["hk_zh"], hakka_text)

    def synthesize(
        self,
        hanzi: str,
        dialect: str = "hailu",
        gender: str = "F",
        rate: float = 1.0,
    ) -> bytes:
        """客語漢字 -> WAV bytes（16-bit mono 16 kHz）。"""
        gender = gender.upper()
        if dialect not in VOICE_NAMES or gender not in VOICE_NAMES[dialect]:
            raise HakkaError(f"不支援的語音組合：{dialect}/{gender}")
        payload = {
            "input": {"text": hanzi, "textType": "characters"},
            "voice": {
                "model": "broncitts",
                "languageCode": DIALECTS[dialect]["tts_lang"],
                "name": VOICE_NAMES[dialect][gender],
            },
            "audioConfig": {"speakingRate": rate},
            "outputConfig": {
                "streamMode": 0,
                "shortPauseDuration": 150,
                "longPauseDuration": 300,
            },
        }
        try:
            with self._lock:
                resp = self._session.post(
                    f"{BASE}/TTS/Synthesize", json=payload, timeout=self.timeout
                )
        except Exception as exc:
            raise HakkaError(f"連線語音合成服務失敗：{exc}") from exc

        ctype = resp.headers.get("content-type", "")
        if resp.status_code != 200 or "audio" not in ctype:
            raise HakkaError(f"語音合成失敗（HTTP {resp.status_code}）")
        if not resp.content:
            raise HakkaError("語音合成回傳空檔案")
        return resp.content
