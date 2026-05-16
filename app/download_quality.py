
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

DATA_DIR = Path("app/data")
SESSIONS_FILE = DATA_DIR / "download_sessions.json"
DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "app/downloads"))

VIDEO_HEIGHTS = [144, 240, 360, 480, 720, 1080, 1440, 2160]
AUDIO_CHOICES = [
    ("mp3_64", "🎧 MP3 64kbps"),
    ("mp3_128", "🎧 MP3 128kbps"),
    ("mp3_192", "🎧 MP3 192kbps"),
    ("m4a", "🎧 M4A أصلي"),
    ("webm", "🎧 WEBM Audio"),
]


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def is_direct_download_url(text: str) -> bool:
    text = (text or "").strip()
    return bool(re.match(r"^https?://", text, flags=re.I))


def _load_sessions() -> dict[str, Any]:
    _ensure_dirs()
    if not SESSIONS_FILE.exists():
        return {}
    try:
        return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_sessions(data: dict[str, Any]) -> None:
    _ensure_dirs()
    SESSIONS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _new_sid() -> str:
    return secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]


def _cookies_args() -> list[str]:
    cookies = os.getenv("YTDLP_COOKIES_TXT", "").strip()
    if not cookies:
        return []

    path = Path("/tmp/ytdlp_cookies.txt")
    path.write_text(cookies, encoding="utf-8")
    return ["--cookies", str(path)]


def _base_ytdlp_args() -> list[str]:
    args = [
        "yt-dlp",
        "--no-playlist",
        "--force-ipv4",
        "--retries", "3",
        "--fragment-retries", "3",
        "--socket-timeout", "30",
        "--user-agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    ]
    args.extend(_cookies_args())
    return args


async def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    def _call():
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
        return p.returncode, p.stdout, p.stderr

    return await asyncio.to_thread(_call)


async def _safe_send(send_message, chat_id: int, text: str, reply_markup: dict | None = None):
    try:
        return await send_message(chat_id, text, reply_markup=reply_markup)
    except TypeError:
        # لو send_message لا يدعم reply_markup
        return await send_message(chat_id, text)


async def _answer_callback(callback_id: str, text: str = ""):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or not callback_id:
        return None

    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text

    def _post():
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as res:
            return json.loads(res.read().decode("utf-8"))

    return await asyncio.to_thread(_post)


def _extract_available_heights(info: dict[str, Any]) -> list[int]:
    heights = set()

    for f in info.get("formats", []):
        if f.get("vcodec") in (None, "none"):
            continue

        h = f.get("height")
        if isinstance(h, int) and h > 0:
            nearest = min(VIDEO_HEIGHTS, key=lambda x: abs(x - h))
            # لا نعرض جودة أعلى بكثير من المتاح
            if nearest <= h or abs(nearest - h) <= 40:
                heights.add(nearest)

    if not heights:
        # fallback
        heights.update([360, 720])

    return sorted(heights)


async def _get_info(url: str) -> dict[str, Any]:
    cmd = _base_ytdlp_args() + [
        "--dump-single-json",
        "--skip-download",
        url,
    ]
    code, out, err = await _run(cmd, timeout=int(os.getenv("EXTRACT_TIMEOUT_SECONDS", "120")))

    if code != 0:
        msg = err.strip() or out.strip() or "فشل استخراج معلومات الرابط."
        if "Sign in to confirm" in msg or "not a bot" in msg:
            msg = "يوتيوب طلب تحققًا من الجلسة. أضف YTDLP_COOKIES_TXT في Railway أو جرّب رابطًا آخر."
        raise RuntimeError(msg[:1500])

    return json.loads(out)


async def start_download_quality_flow(chat_id: int, url: str, send_message):
    url = (url or "").strip()
    if not is_direct_download_url(url):
        await _safe_send(send_message, chat_id, "أرسل رابطًا صحيحًا بعد /fetch أو /download.")
        return

    await _safe_send(send_message, chat_id, "🔎 جاري فحص الرابط واستخراج الجودات...")

    try:
        info = await _get_info(url)
    except Exception as e:
        await _safe_send(send_message, chat_id, f"فشل فحص الرابط:\n{e}")
        return

    sid = _new_sid()
    sessions = _load_sessions()
    sessions[sid] = {
        "url": url,
        "title": info.get("title") or "media",
        "created_at": int(time.time()),
        "heights": _extract_available_heights(info),
    }

    # تنظيف جلسات قديمة
    now = int(time.time())
    sessions = {
        k: v for k, v in sessions.items()
        if now - int(v.get("created_at", now)) < 7200
    }
    _save_sessions(sessions)

    title = sessions[sid]["title"]
    title = title[:120]

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🎬 فيديو", "callback_data": f"dlq:video:{sid}"},
                {"text": "🎧 صوت", "callback_data": f"dlq:audio:{sid}"},
            ],
            [
                {"text": "❌ إلغاء", "callback_data": f"dlq:cancel:{sid}"},
            ],
        ]
    }

    await _safe_send(
        send_message,
        chat_id,
        f"✅ تم فحص الرابط:\n{title}\n\nاختر نوع التحميل:",
        reply_markup=keyboard,
    )


async def handle_download_quality_callback(data: dict[str, Any], send_message) -> bool:
    callback = data.get("callback_query")
    if not callback:
        return False

    callback_data = callback.get("data", "")
    if not callback_data.startswith("dlq:"):
        return False

    callback_id = callback.get("id", "")
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    if not chat_id:
        return True

    parts = callback_data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    sid = parts[2] if len(parts) > 2 else ""

    sessions = _load_sessions()
    session = sessions.get(sid)

    if action == "cancel":
        sessions.pop(sid, None)
        _save_sessions(sessions)
        await _answer_callback(callback_id, "تم الإلغاء")
        await _safe_send(send_message, chat_id, "تم إلغاء عملية التحميل.")
        return True

    if not session:
        await _answer_callback(callback_id, "انتهت الجلسة")
        await _safe_send(send_message, chat_id, "انتهت جلسة التحميل. أرسل الرابط مرة أخرى.")
        return True

    if action == "video":
        await _answer_callback(callback_id, "اختر الدقة")
        heights = session.get("heights") or [360, 720]

        rows = []
        row = []
        for h in heights:
            row.append({"text": f"🎬 {h}p", "callback_data": f"dlq:v:{sid}:{h}"})
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)

        rows.append([{"text": "🔙 رجوع", "callback_data": f"dlq:back:{sid}"}])

        await _safe_send(
            send_message,
            chat_id,
            "اختر دقة الفيديو:",
            reply_markup={"inline_keyboard": rows},
        )
        return True

    if action == "audio":
        await _answer_callback(callback_id, "اختر الصوت")
        rows = []
        row = []
        for key, label in AUDIO_CHOICES:
            row.append({"text": label, "callback_data": f"dlq:a:{sid}:{key}"})
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)

        rows.append([{"text": "🔙 رجوع", "callback_data": f"dlq:back:{sid}"}])

        await _safe_send(
            send_message,
            chat_id,
            "اختر نوع الصوت:",
            reply_markup={"inline_keyboard": rows},
        )
        return True

    if action == "back":
        await _answer_callback(callback_id)
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🎬 فيديو", "callback_data": f"dlq:video:{sid}"},
                    {"text": "🎧 صوت", "callback_data": f"dlq:audio:{sid}"},
                ],
                [{"text": "❌ إلغاء", "callback_data": f"dlq:cancel:{sid}"}],
            ]
        }
        await _safe_send(send_message, chat_id, "اختر نوع التحميل:", reply_markup=keyboard)
        return True

    if action == "v" and len(parts) >= 4:
        height = int(parts[3])
        await _answer_callback(callback_id, f"تحميل {height}p")
        await _download_and_send(chat_id, session, send_message, kind="video", choice=str(height))
        return True

    if action == "a" and len(parts) >= 4:
        choice = parts[3]
        await _answer_callback(callback_id, "تحميل الصوت")
        await _download_and_send(chat_id, session, send_message, kind="audio", choice=choice)
        return True

    await _answer_callback(callback_id)
    return True


async def _download_and_send(chat_id: int, session: dict[str, Any], send_message, kind: str, choice: str):
    _ensure_dirs()

    url = session["url"]
    title = (session.get("title") or "media")[:90]

    await _safe_send(send_message, chat_id, f"⏳ بدأ التحميل:\n{title}")

    started_at = time.time()
    out_tpl = str(DOWNLOAD_DIR / "%(title).80s-%(id)s.%(ext)s")

    cmd = _base_ytdlp_args() + ["-o", out_tpl]

    if kind == "video":
        height = int(choice)
        fmt = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"
        cmd += [
            "-f", fmt,
            "--merge-output-format", "mp4",
            url,
        ]
    else:
        if choice.startswith("mp3_"):
            kbps = choice.split("_", 1)[1]
            cmd += [
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", f"{kbps}K",
                url,
            ]
        elif choice == "m4a":
            cmd += ["-f", "bestaudio[ext=m4a]/bestaudio", url]
        elif choice == "webm":
            cmd += ["-f", "bestaudio[ext=webm]/bestaudio", url]
        else:
            cmd += ["-f", "bestaudio/best", url]

    timeout = int(os.getenv("DOWNLOAD_TIMEOUT_SECONDS", "900"))
    code, out, err = await _run(cmd, timeout=timeout)

    if code != 0:
        msg = err.strip() or out.strip() or "فشل التحميل."
        if "Sign in to confirm" in msg or "not a bot" in msg:
            msg = "يوتيوب طلب تحققًا من الجلسة. تأكد من إضافة YTDLP_COOKIES_TXT في Railway."
        await _safe_send(send_message, chat_id, f"فشل التحميل:\n{msg[:1800]}")
        return

    files = [
        f for f in DOWNLOAD_DIR.glob("*")
        if f.is_file() and f.stat().st_mtime >= started_at - 5
    ]

    if not files:
        await _safe_send(send_message, chat_id, "اكتمل yt-dlp لكن لم أجد الملف الناتج.")
        return

    file_path = max(files, key=lambda f: f.stat().st_mtime)

    max_mb = int(os.getenv("DOWNLOAD_MAX_FILE_MB", "45"))
    size_mb = file_path.stat().st_size / (1024 * 1024)

    if size_mb > max_mb:
        await _safe_send(
            send_message,
            chat_id,
            f"الملف حجمه {size_mb:.1f}MB وهو أكبر من الحد {max_mb}MB. اختر جودة أقل.",
        )
        try:
            file_path.unlink()
        except Exception:
            pass
        return

    await _send_document(chat_id, file_path, caption=title)

    try:
        file_path.unlink()
    except Exception:
        pass


async def _send_document(chat_id: int, file_path: Path, caption: str = ""):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing")

    boundary = "----WebKitFormBoundary" + secrets.token_hex(16)
    url = f"https://api.telegram.org/bot{token}/sendDocument"

    def _field(name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode("utf-8")

    def _file_field(name: str, path: Path) -> bytes:
        filename = path.name
        head = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
        return head + path.read_bytes() + b"\r\n"

    body = b""
    body += _field("chat_id", str(chat_id))
    if caption:
        body += _field("caption", caption[:900])
    body += _file_field("document", file_path)
    body += f"--{boundary}--\r\n".encode("utf-8")

    def _post():
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as res:
            return json.loads(res.read().decode("utf-8"))

    return await asyncio.to_thread(_post)
