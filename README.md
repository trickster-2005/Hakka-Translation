# 華語 → 客語 Telegram Bot

傳一句華語給 Telegram bot，它會回覆：

- **客語漢字**（預設海陸腔，可切四縣腔）
- **客語拼音**（帶聲調）
- **發音音檔**（mp3，可下載／轉傳；也可改成語音訊息或 wav）

翻譯與語音皆來自 [臺灣客語語音資料庫](https://speech.hakka.gov.tw)（客家委員會）。
本專案只是把官方網站「線上即時翻譯」頁面的請求包成 Telegram bot，方便個人隨手使用。

> ⚠️ **僅供個人使用。** 這是非官方用法，詳見下方「使用規範與免責聲明」。

---

## 目錄

- [功能](#功能)
- [運作原理](#運作原理方法-a)
- [每日額度](#每日額度)
- [系統需求](#系統需求)
- [安裝](#安裝)
- [設定 `.env`](#設定-env)
- [如何取得 `HAKKA_COOKIE`](#如何取得-hakka_cookie選填)
- [執行](#執行)
- [指令](#指令)
- [專案結構](#專案結構)
- [疑難排解](#疑難排解)
- [使用規範與免責聲明](#使用規範與免責聲明)
- [引用格式](#引用格式)
- [授權](#授權)
- [資料來源與致謝](#資料來源與致謝)

---

## 功能

| 項目 | 說明 |
|---|---|
| 華語 → 客語漢字 | 支援海陸腔（`hailu`）、四縣腔（`sixian`） |
| 客語拼音 | 客語通用拼音，帶聲調符號（如 `ˊ ˇ ˋ +`） |
| 語音合成 | 男聲 / 女聲，語速可調（0.5–2.0） |
| 音檔輸出 | `audio`（mp3 卡片）、`doc`（mp3 檔案，不進播放器）、`voice`（語音訊息）、`both`、`wav`、`off` |
| 使用者白名單 | 只允許指定 Telegram 帳號使用 |
| 每日額度控管 | 累計當日字數，超過上限自動暫停至隔天 |
| 設定持久化 | 腔調／語音／格式等設定寫入 `settings.json`，重開仍生效 |

---

## 運作原理（方法 A）

官方網頁的翻譯頁面實際上只打三個請求，本 bot 直接呼叫相同端點：

| 請求 | 用途 |
|---|---|
| `POST /Translation/Translate` `{"Code":"hakka_hailu_zh_hk","Before":"…"}` | 華語 → 海陸客語漢字 |
| `POST /Translation/Translate` `{"Code":"hakka_hailu_hk_py_tone","Before":"…"}` | 海陸客語漢字 → 海陸拼音（帶調） |
| `POST /TTS/Synthesize` `{…}` | 客語漢字 → WAV（16-bit mono 16 kHz） |

（四縣腔對應 `hakka_zh_hk`、`hakka_hk_py_tone`；反向客語→華語為 `hakka_hk_zh`。）

### 為什麼需要 `curl_cffi`

`speech.hakka.gov.tw` 的 POST 端點前有 WAF，會用 **TLS 指紋**辨識來源：
一般的 `requests` / `httpx` / `curl` 直接呼叫會被擋、回傳 HTTP 500，只有瀏覽器能通過。
因此本專案使用 [`curl_cffi`](https://github.com/lexiforest/curl_cffi) 模擬 Chrome 的
TLS/HTTP2 指紋（`HTTP_IMPERSONATE=chrome`）。

> 這是方法 A 最脆弱的一環：若官方調整 WAF，可能需要改 `HTTP_IMPERSONATE` 的值
> （`chrome124`、`chrome131`、`edge` 等），或整個失效。

### 流程

```
華語文字
   │  POST /Translation/Translate  (zh → hk 漢字)
   ▼
客語漢字 ──► 顯示
   │  POST /Translation/Translate  (hk 漢字 → 拼音)
   ▼
客語拼音 ──► 顯示
   │  POST /TTS/Synthesize
   ▼
WAV ──► ffmpeg ──► mp3 / ogg ──► 傳給使用者
```

---

## 每日額度

| 使用方式 | 額度 | 設定 |
|---|---|---|
| **匿名**（預設） | 約 1,000 字／日（以 IP 計算） | 不用做任何事 |
| **登入帳號** | 10,000 字／日（以帳號計算） | `.env` 填 `HAKKA_COOKIE`，並把 `DAILY_CHAR_LIMIT` 改成 `10000` |

`daily_usage.json` 會記錄當日累計字數（以輸入字數計），跨日自動歸零。
達到 `DAILY_CHAR_LIMIT` 時，bot 會回覆額度用完並暫停，直到隔天。
可用 `/quota` 查詢目前用量。

---

## 系統需求

- **Python 3.11 以上**
- **[ffmpeg](https://ffmpeg.org/)**（需在系統 PATH 中，用來把 WAV 轉成 mp3 / ogg）
  - Windows：下載後把 `bin` 資料夾加入環境變數 PATH，或用 `winget install Gyan.FFmpeg`
  - 驗證：終端機執行 `ffmpeg -version` 有輸出即可
- 一個 Telegram bot token（見下方）

---

## 安裝

```bash
# 1. 進入專案資料夾
cd C:\Users\user\Desktop\Hakka-Translation

# 2. 建立虛擬環境（擇一）
py -3.11 -m venv .venv
# 或
python -m venv .venv

# 3. 安裝套件
.venv\Scripts\python -m pip install -r requirements.txt

# 4. 建立設定檔
copy .env.example .env
```

套件清單（`requirements.txt`）：

| 套件 | 用途 |
|---|---|
| `python-telegram-bot` (>=21,<23) | Telegram bot 框架 |
| `curl_cffi` (>=0.7) | 模擬瀏覽器 TLS 指紋，繞過 WAF |
| `python-dotenv` (>=1.0) | 讀取 `.env` |

---

## 設定 `.env`

編輯專案根目錄的 `.env`：

### 必填

| 變數 | 說明 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | 跟 [@BotFather](https://t.me/BotFather) 用 `/newbot` 申請後取得的 token |

### 建議填（私人 bot）

| 變數 | 說明 |
|---|---|
| `ALLOWED_USER_IDS` | 允許使用的 Telegram user id，逗號分隔。**留空 = 任何人都能用**。啟動 bot 後傳 `/id` 給它即可查到自己的 id |

### 選填（有預設值）

| 變數 | 預設 | 說明 |
|---|---|---|
| `HAKKA_DIALECT` | `hailu` | 預設腔調：`hailu`（海陸）／`sixian`（四縣） |
| `HAKKA_VOICE` | `F` | 預設語音：`F`（女聲）／`M`（男聲） |
| `SEND_AUDIO_AS` | `audio` | 音檔輸出：`audio`(mp3卡片) / `doc`(mp3檔案,不進播放器) / `voice`(語音訊息,會自動接續播放) / `both` / `wav` / `off` |
| `SPEAKING_RATE` | `1.0` | 語速，範圍 0.5–2.0 |
| `MAX_INPUT_CHARS` | `180` | 單則訊息最多字數 |
| `DAILY_CHAR_LIMIT` | `1000` | 每日翻譯字數上限（用帳號 cookie 時可設 `10000`） |
| `HAKKA_COOKIE` | （空） | 登入後的 cookie 字串，見下節 |
| `HTTP_IMPERSONATE` | `chrome` | `curl_cffi` 模擬的瀏覽器指紋（`chrome` / `chrome124` / `edge` …） |
| `SETTINGS_FILE` | `settings.json` | 執行期設定的儲存路徑 |

執行期用指令（`/voice`、`/dialect` 等）改的設定會蓋過 `.env` 的預設，並寫入 `settings.json`。

---

## 如何取得 `HAKKA_COOKIE`（選填）

只有想用帳號的 **10,000 字／日** 額度時才需要。

1. 用瀏覽器登入 <https://speech.hakka.gov.tw>
2. 按 <kbd>F12</kbd> 開開發者工具 → **Network（網路）** 分頁
3. 在網站上隨便按一下（例如翻譯一句），讓它發出請求
4. 點任一個發往 `speech.hakka.gov.tw` 的請求 → **Headers** → 找到 **Request Headers** 裡的 `Cookie:`
5. 複製整段 `Cookie:` 後面的值，貼到 `.env`：
   ```
   HAKKA_COOKIE=.AspNetCore.Cookies=xxxxx; 其他=yyyyy
   DAILY_CHAR_LIMIT=10000
   ```

> Cookie 會過期（通常數天到數週），失效後 bot 會自動退回匿名額度或回報錯誤，
> 屆時重複上面步驟更新即可。

---

## 執行

### 前景執行

```bash
.venv\Scripts\python bot.py
```

或直接雙擊 `run.bat`。保持視窗開著，bot 就會運作。按 <kbd>Ctrl</kbd>+<kbd>C</kbd> 停止。

### 開機自動執行（Windows 工作排程器）

1. 開「工作排程器」→ 建立基本工作
2. 觸發程序：登入時
3. 動作：啟動程式
   - 程式：`C:\Users\user\Desktop\Hakka-Translation\.venv\Scripts\pythonw.exe`
   - 引數：`bot.py`
   - 起始位置：`C:\Users\user\Desktop\Hakka-Translation`

### 部署到 Raspberry Pi / Linux（systemd）

推薦用 Raspberry Pi 常駐：省電、台灣住宅 IP、免月租。

**1. 確認環境**

```bash
uname -m            # aarch64 = 64 位元（建議）；armv7l = 32 位元也能跑
python3 --version   # 需要 3.11 以上
```

- 建議用 **Raspberry Pi OS Bookworm（64-bit）**，內建 Python 3.11，`curl_cffi` 有現成套件。
- 舊的 **Bullseye 內建 Python 3.9 不夠**，請升級到 Bookworm（或自行裝 3.11+）。
- 32 位元（armv7l）＋ Bookworm 也可以，只是效能較差。

**2. 安裝相依套件**

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg git
```

**3. 取得專案並安裝**

```bash
git clone https://github.com/trickster-2005/Hakka-Translation.git ~/hakka-translation
cd ~/hakka-translation
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env                                  # 填 TELEGRAM_BOT_TOKEN、ALLOWED_USER_IDS
```

**4. 先手動測試**

```bash
.venv/bin/python bot.py
```

到 Telegram 傳訊息確認有回應，然後 <kbd>Ctrl</kbd>+<kbd>C</kbd> 停掉。

**5. 設成開機自動啟動**

用安裝腳本（會自動偵測你的使用者帳號和專案路徑，不用手改）：

```bash
bash deploy/install.sh                # 只裝 bot
# 或
bash deploy/install.sh --autoupdate   # 順便裝「定時從 GitHub 自動更新」

systemctl status hakka-bot --no-pager   # 看狀態
journalctl -u hakka-bot -f              # 看即時日誌
```

之後 bot 會開機自動跑、當掉自動重啟。

> 手動安裝：`deploy/hakka-bot.service` 是參考範本，把裡面 `__USER__`、`__DIR__`
> 換成 `id -un` 和 `pwd` 的結果後，複製到 `/etc/systemd/system/` 再
> `sudo systemctl daemon-reload && sudo systemctl enable --now hakka-bot`。

**更新程式**

- **手動**：`cd ~/hakka-translation && git pull && sudo systemctl restart hakka-bot`
- **自動**：裝了 `--autoupdate` 後，每 15 分鐘會自己 `git fetch`，有新 commit 就
  `git reset --hard`、（`requirements.txt` 有變才）重裝套件、重啟 bot。
  紀錄看 `journalctl -t hakka-autoupdate`。
  改間隔：`sudo systemctl edit hakka-bot-update.timer` 覆寫 `OnUnitActiveSec`。
  關掉：`sudo systemctl disable --now hakka-bot-update.timer`。

> 自動更新是**強制對齊 GitHub**（`reset --hard`）—— Pi 上不要直接改被追蹤的檔案，
> 改動會被蓋掉。設定放在未追蹤的 `.env`，不受影響。

> **若 `curl_cffi` 裝不起來**（多半是 Python 太舊或 32 位元舊系統）：升級到
> Raspberry Pi OS Bookworm（64-bit）最省事；或 `sudo apt install -y
> libcurl4-openssl-dev build-essential` 後再 `pip install`。

---

## 指令

| 指令 | 說明 |
|---|---|
| （直接傳文字） | 華語 → 客語漢字＋拼音＋音檔 |
| `/start`、`/help` | 說明與目前設定 |
| `/voice f` \| `/voice m` | 切換女聲 / 男聲 |
| `/dialect hailu` \| `/dialect sixian` | 切換海陸腔 / 四縣腔 |
| `/audio audio\|doc\|voice\|both\|wav\|off` | 音檔輸出方式（`voice` 會被 Telegram 自動接續播放，想避免用 `audio` 或 `doc`） |
| `/rate 1.0` | 語速（0.5–2.0） |
| `/settings` | 顯示目前設定 |
| `/quota` | 今日已用字數 |
| `/id` | 顯示你的 Telegram user id |

---

## 專案結構

```
Hakka-Translation/
├── bot.py              # Telegram bot 主程式（指令、訊息處理、設定）
├── hakka_client.py     # 呼叫 speech.hakka.gov.tw 的 client（翻譯 / 拼音 / TTS）
├── audio.py            # WAV → mp3 / ogg（呼叫 ffmpeg）
├── usage.py            # 每日字數計數器（daily_usage.json）
├── requirements.txt
├── .env.example        # 設定範本
├── .gitignore
├── run.bat             # Windows 啟動捷徑
├── deploy/
│   ├── install.sh          # 一鍵安裝 systemd 服務（可加 --autoupdate）
│   ├── autoupdate.sh       # 定時檢查 GitHub 並更新（由 timer 呼叫）
│   └── hakka-bot.service   # systemd 服務參考範本（手動安裝用）
├── README.md
├── LICENSE             # MIT
│
├── .env                # ← 你的設定（git 忽略）
├── settings.json       # ← 執行期設定（自動產生，git 忽略）
└── daily_usage.json    # ← 當日用量（自動產生，git 忽略）
```

---

## 疑難排解

| 症狀 | 可能原因與處理 |
|---|---|
| `翻譯服務回應 HTTP 500` / `被 WAF 阻擋` | WAF 擋掉了指紋。試著把 `.env` 的 `HTTP_IMPERSONATE` 改成 `chrome131`、`chrome124` 或 `edge`；或稍後再試（也可能是官方服務暫時忙碌） |
| `找不到 ffmpeg` | ffmpeg 沒安裝或不在 PATH。安裝後重開終端機，`ffmpeg -version` 確認 |
| `今日翻譯額度用完了` | 當日字數達 `DAILY_CHAR_LIMIT`。等隔天，或設定 `HAKKA_COOKIE` 改用帳號額度並調高上限 |
| bot 已啟動但不回話 | 檢查 `ALLOWED_USER_IDS` 是否填了你的 id（傳 `/id` 查）；或先留空測試 |
| `請在 .env 設定 TELEGRAM_BOT_TOKEN` | `.env` 沒建立或 token 沒填。`copy .env.example .env` 後編輯 |
| 拼音看起來怪怪的 | 客語通用拼音的聲調用符號標示（`ˊ ˇ ˋ ^ +`），與華語拼音不同，屬正常 |
| Cookie 失效（帳號額度變回匿名） | 重新依「如何取得 `HAKKA_COOKIE`」更新 |
| 音檔會自動接著播前一則 | 這是 Telegram 對「語音訊息」和「音樂檔」的接續播放行為，client 沒有關閉開關。改用 `/audio doc`（送成一般檔案，不進播放器）；並把聊天室裡先前測試 `voice`／`both` 時留下的舊語音訊息刪掉 |

---

## 使用規範與免責聲明

- **僅供個人使用。** 請勿以單一帳號對外開放給多人共用 —— 那等同規避官方「每帳號每日額度」的限制，也會對政府服務造成額外負擔。
- 本專案為 **非官方** 用法，直接呼叫官方網站前端所使用的端點。官方網站若改版、調整 WAF 或端點，本工具可能隨時失效，作者不保證持續可用。
- 依官方規定：本資料庫提供之檢索結果（合成音檔、翻譯結果等），使用時皆須符合中華民國法律，以及著作權法有關合理使用等相關規定，並須**註明出處**（見下方「引用格式」）。
- 若需要**穩定、正式、可對外**的服務，請循客委會
  [「臺灣客語語音資料庫應用程式介面管理要點」](https://www.hakka.gov.tw/)
  申請正式 API（客華雙向文字翻譯 API、客語漢字轉拼音 API、客語語音合成 API）。
  第一階段開放對象為各級政府機關、機構、行政法人及學校。
- 本專案的程式碼以 MIT 授權釋出；但**翻譯內容、語音資料的權利屬客家委員會**，不在本授權範圍內。
- 本軟體按「現狀」提供，作者不對使用結果負責。

---

## 引用格式

依 [臺灣客語語音資料庫 — 關於我們](https://speech.hakka.gov.tw/Document/AboutUs)：
使用本資料庫提供之檢索結果（不論合成音檔、語音辨識或翻譯結果）時，**請註明出處**。
官方提供二種引用格式：

### 一般資源運用（中英文）

> 客家委員會（2023）。《臺灣客語語音資料庫》。檢索自 https://speech.hakka.gov.tw/

> Hakka Affairs Council (2023). Taiwanese Hakka speech corpus. Retrieved from https://speech.hakka.gov.tw/

### 使用於論文發表

> Hakka Affairs Council (2023). Y.-F. Liao et al., "Taiwanese Hakka Across Taiwan
> Corpus and Formosa Speech Recognition Challenge 2023 - Hakka ASR," 2023 26th
> Conference of the Oriental COCOSDA International Committee for the Co-ordination
> and Standardisation of Speech Databases and Assessment Techniques (O-COCOSDA),
> Delhi, India, 2023, pp. 1-6, doi: 10.1109/O-COCOSDA60357.2023.10482979.
> https://ieeexplore.ieee.org/document/10482979

---

## 授權

本專案程式碼採 [MIT License](LICENSE)。

```
Copyright (c) 2026 trickster-2005
```

> 請把上面（及 `LICENSE` 檔案中）的名字換成你自己的姓名或慣用名稱。

翻譯與語音合成結果之著作權及相關權利屬**客家委員會 臺灣客語語音資料庫**，
不隨本專案之 MIT 授權釋出。

---

## 資料來源與致謝

- [臺灣客語語音資料庫](https://speech.hakka.gov.tw) — 客家委員會
- 翻譯與語音合成引擎：元鼎科技（Bronci）`hakka-mt.bronci.com.tw` / `hktts.bronci.com.tw`
- [`curl_cffi`](https://github.com/lexiforest/curl_cffi)
- [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot)
