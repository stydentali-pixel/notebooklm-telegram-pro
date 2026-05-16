from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Awaitable

from .config import get_settings
from .telegram import answer_callback_query, send_document, send_message as default_send_message, html_escape

VIDEO_HEIGHTS = [144, 240, 360, 480, 720, 1080, 1440, 2160]
AUDIO_CHOICES = [
    ('mp3_64', '🎧 MP3 64kbps'),
    ('mp3_128', '🎧 MP3 128kbps'),
    ('mp3_192', '🎧 MP3 192kbps'),
    ('m4a', '🎧 M4A أصلي'),
    ('webm', '🎧 WEBM Audio'),
]

SendMessage = Callable[..., Awaitable[Any]]


def _settings():
    return get_settings()


def _data_dir() -> Path:
    return Path(_settings().data_dir)


def _download_dir() -> Path:
    return Path(_settings().download_dir)


def _sessions_file() -> Path:
    return _data_dir() / 'download_sessions.json'


def _ensure_dirs() -> None:
    _data_dir().mkdir(parents=True, exist_ok=True)
    _download_dir().mkdir(parents=True, exist_ok=True)


def is_direct_download_url(text: str) -> bool:
    text = (text or '').strip()
    return bool(re.match(r'^https?://\S+$', text, flags=re.I))


def _load_sessions() -> dict[str, Any]:
    _ensure_dirs()
    p = _sessions_file()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _save_sessions(data: dict[str, Any]) -> None:
    _ensure_dirs()
    p = _sessions_file()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def _new_sid() -> str:
    return secrets.token_urlsafe(8).replace('-', '').replace('_', '')[:10]


def _cookies_args() -> list[str]:
    cookies = os.getenv('YTDLP_COOKIES_TXT') or getattr(_settings(), 'ytdlp_cookies_txt', '')
    cookies = (cookies or '').strip()
    if not cookies:
        return []
    path = Path('/tmp/ytdlp_cookies.txt')
    path.write_text(cookies, encoding='utf-8')
    return ['--cookies', str(path)]


def _base_ytdlp_args() -> list[str]:
    s = _settings()
    args = [
        'yt-dlp',
        '--no-playlist',
        '--retries', str(getattr(s, 'ytdlp_retries', 3)),
        '--fragment-retries', str(getattr(s, 'ytdlp_fragment_retries', 5)),
        '--socket-timeout', '30',
        '--user-agent', getattr(s, 'ytdlp_user_agent', 'Mozilla/5.0'),
    ]
    if getattr(s, 'ytdlp_force_ipv4', True):
        args.append('--force-ipv4')
    if getattr(s, 'ytdlp_geo_bypass', True):
        args.append('--geo-bypass')
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


async def _safe_send(send_message: SendMessage, chat_id: int, text: str, reply_markup: dict | None = None):
    try:
        return await send_message(chat_id, text, reply_markup=reply_markup)
    except TypeError:
        return await send_message(chat_id, text)


def _clean_error(msg: str) -> str:
    msg = (msg or '').strip()
    if 'Sign in to confirm' in msg or 'not a bot' in msg:
        return 'يوتيوب طلب تحققًا من الجلسة. أضف YTDLP_COOKIES_TXT في Railway أو جرّب رابطًا آخر.'
    if 'Unsupported URL' in msg:
        return 'الرابط غير مدعوم من yt-dlp. جرّب رابطًا من منصة مدعومة.'
    return msg[:1800] or 'حدث خطأ غير معروف.'


async def _get_info(url: str) -> dict[str, Any]:
    cmd = _base_ytdlp_args() + ['--dump-single-json', '--skip-download', url]
    code, out, err = await _run(cmd, timeout=int(os.getenv('EXTRACT_TIMEOUT_SECONDS', str(_settings().extract_timeout_seconds))))
    if code != 0:
        raise RuntimeError(_clean_error(err or out))
    return json.loads(out)


def _extract_available_heights(info: dict[str, Any]) -> list[int]:
    heights: set[int] = set()
    for f in info.get('formats', []):
        if f.get('vcodec') in (None, 'none'):
            continue
        h = f.get('height')
        if isinstance(h, int) and h > 0:
            for candidate in VIDEO_HEIGHTS:
                if abs(candidate - h) <= 40 or candidate == h:
                    heights.add(candidate)
                    break
            else:
                heights.add(h)
    if not heights:
        heights.update([360, 720])
    return sorted(h for h in heights if h > 0)


def _title(info_or_session: dict[str, Any]) -> str:
    return str(info_or_session.get('title') or 'media')[:120]


async def start_download_quality_flow(chat_id: int, url: str, send_message: SendMessage = default_send_message):
    url = (url or '').strip()
    if not is_direct_download_url(url):
        await _safe_send(send_message, chat_id, 'أرسل رابطًا صحيحًا بعد /fetch أو /download.')
        return

    await _safe_send(send_message, chat_id, '🔎 جاري فحص الرابط واستخراج الجودات...')
    try:
        info = await _get_info(url)
    except Exception as e:
        await _safe_send(send_message, chat_id, f'فشل فحص الرابط:\n<code>{html_escape(_clean_error(str(e)))}</code>')
        return

    sid = _new_sid()
    sessions = _load_sessions()
    now = int(time.time())
    sessions = {k: v for k, v in sessions.items() if now - int(v.get('created_at', now)) < 7200}
    sessions[sid] = {
        'url': url,
        'title': _title(info),
        'created_at': now,
        'heights': _extract_available_heights(info),
    }
    _save_sessions(sessions)

    keyboard = {
        'inline_keyboard': [
            [
                {'text': '🎬 فيديو', 'callback_data': f'dlq:video:{sid}'},
                {'text': '🎧 صوت', 'callback_data': f'dlq:audio:{sid}'},
            ],
            [
                {'text': '✂️ تقطيع فيديو', 'callback_data': f'dlq:triminfo:{sid}'},
                {'text': '❌ إلغاء', 'callback_data': f'dlq:cancel:{sid}'},
            ],
        ]
    }
    await _safe_send(send_message, chat_id, f'✅ تم فحص الرابط:\n<b>{html_escape(sessions[sid]["title"])}</b>\n\nاختر نوع التحميل:', reply_markup=keyboard)


async def handle_download_quality_callback(data: dict[str, Any], send_message: SendMessage = default_send_message) -> bool:
    callback = data.get('callback_query')
    if not callback:
        return False
    callback_data = callback.get('data', '')
    if not callback_data.startswith('dlq:'):
        return False

    callback_id = callback.get('id', '')
    message = callback.get('message') or {}
    chat = message.get('chat') or {}
    chat_id = chat.get('id')
    if not chat_id:
        return True

    parts = callback_data.split(':')
    action = parts[1] if len(parts) > 1 else ''
    sid = parts[2] if len(parts) > 2 else ''
    sessions = _load_sessions()
    session = sessions.get(sid)

    if action == 'cancel':
        sessions.pop(sid, None)
        _save_sessions(sessions)
        await answer_callback_query(callback_id, 'تم الإلغاء')
        await _safe_send(send_message, chat_id, 'تم إلغاء عملية التحميل.')
        return True

    if not session:
        await answer_callback_query(callback_id, 'انتهت الجلسة')
        await _safe_send(send_message, chat_id, 'انتهت جلسة التحميل. أرسل الرابط مرة أخرى.')
        return True

    if action == 'triminfo':
        await answer_callback_query(callback_id, 'طريقة التقطيع')
        await _safe_send(send_message, chat_id, '✂️ لتقطيع الفيديو استخدم:\n<code>/trim الرابط 00:00:10 00:00:30</code>\n\nأو:\n<code>/trim الرابط 10 30</code>')
        return True

    if action == 'video':
        await answer_callback_query(callback_id, 'اختر الدقة')
        rows: list[list[dict[str, str]]] = []
        row: list[dict[str, str]] = []
        for h in session.get('heights') or [360, 720]:
            row.append({'text': f'🎬 {h}p', 'callback_data': f'dlq:v:{sid}:{h}'})
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([{'text': '🔙 رجوع', 'callback_data': f'dlq:back:{sid}'}])
        await _safe_send(send_message, chat_id, 'اختر دقة الفيديو:', reply_markup={'inline_keyboard': rows})
        return True

    if action == 'audio':
        await answer_callback_query(callback_id, 'اختر الصوت')
        rows: list[list[dict[str, str]]] = []
        row: list[dict[str, str]] = []
        for key, label in AUDIO_CHOICES:
            row.append({'text': label, 'callback_data': f'dlq:a:{sid}:{key}'})
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([{'text': '🔙 رجوع', 'callback_data': f'dlq:back:{sid}'}])
        await _safe_send(send_message, chat_id, 'اختر نوع الصوت:', reply_markup={'inline_keyboard': rows})
        return True

    if action == 'back':
        await answer_callback_query(callback_id)
        keyboard = {'inline_keyboard': [[
            {'text': '🎬 فيديو', 'callback_data': f'dlq:video:{sid}'},
            {'text': '🎧 صوت', 'callback_data': f'dlq:audio:{sid}'},
        ], [{'text': '✂️ تقطيع فيديو', 'callback_data': f'dlq:triminfo:{sid}'}, {'text': '❌ إلغاء', 'callback_data': f'dlq:cancel:{sid}'}]]}
        await _safe_send(send_message, chat_id, 'اختر نوع التحميل:', reply_markup=keyboard)
        return True

    if action == 'v' and len(parts) >= 4:
        await answer_callback_query(callback_id, f'تحميل {parts[3]}p')
        await _download_and_send(chat_id, session, send_message, kind='video', choice=parts[3])
        return True

    if action == 'a' and len(parts) >= 4:
        await answer_callback_query(callback_id, 'تحميل الصوت')
        await _download_and_send(chat_id, session, send_message, kind='audio', choice=parts[3])
        return True

    await answer_callback_query(callback_id)
    return True


async def _download_and_send(chat_id: int, session: dict[str, Any], send_message: SendMessage, kind: str, choice: str):
    _ensure_dirs()
    url = session['url']
    title = session.get('title') or 'media'
    await _safe_send(send_message, chat_id, f'⏳ بدأ التحميل:\n<b>{html_escape(title)}</b>')
    started_at = time.time()
    out_tpl = str(_download_dir() / '%(title).80s-%(id)s.%(ext)s')
    cmd = _base_ytdlp_args() + ['-o', out_tpl]

    if kind == 'video':
        height = int(choice)
        cmd += ['-f', f'bestvideo[height<={height}]+bestaudio/best[height<={height}]/best', '--merge-output-format', 'mp4', url]
    else:
        if choice.startswith('mp3_'):
            kbps = choice.split('_', 1)[1]
            cmd += ['-x', '--audio-format', 'mp3', '--audio-quality', f'{kbps}K', url]
        elif choice == 'm4a':
            cmd += ['-f', 'bestaudio[ext=m4a]/bestaudio', url]
        elif choice == 'webm':
            cmd += ['-f', 'bestaudio[ext=webm]/bestaudio', url]
        else:
            cmd += ['-f', 'bestaudio/best', url]

    code, out, err = await _run(cmd, timeout=int(os.getenv('DOWNLOAD_TIMEOUT_SECONDS', str(_settings().download_timeout_seconds))))
    if code != 0:
        await _safe_send(send_message, chat_id, f'فشل التحميل:\n<code>{html_escape(_clean_error(err or out))}</code>')
        return

    await _send_latest_file(chat_id, title, started_at, send_message)


async def trim_video_url(chat_id: int, url: str, start: str, end: str, send_message: SendMessage = default_send_message):
    url, start, end = url.strip(), start.strip(), end.strip()
    if not is_direct_download_url(url):
        await _safe_send(send_message, chat_id, 'رابط التقطيع غير صحيح.')
        return
    await _safe_send(send_message, chat_id, f'✂️ جارٍ تحميل وقص الفيديو من {html_escape(start)} إلى {html_escape(end)}...')
    _ensure_dirs()
    job = f'trim_{int(time.time())}_{secrets.token_hex(4)}'
    raw_tpl = str(_download_dir() / f'{job}_raw.%(ext)s')
    raw_cmd = _base_ytdlp_args() + ['-f', 'bestvideo[height<=720]+bestaudio/best[height<=720]/best', '--merge-output-format', 'mp4', '-o', raw_tpl, url]
    started_at = time.time()
    code, out, err = await _run(raw_cmd, timeout=int(os.getenv('DOWNLOAD_TIMEOUT_SECONDS', str(_settings().download_timeout_seconds))))
    if code != 0:
        await _safe_send(send_message, chat_id, f'فشل تحميل الفيديو للتقطيع:\n<code>{html_escape(_clean_error(err or out))}</code>')
        return
    raw_files = [f for f in _download_dir().glob(f'{job}_raw.*') if f.is_file()]
    if not raw_files:
        await _safe_send(send_message, chat_id, 'لم أجد ملف الفيديو بعد التحميل.')
        return
    raw = max(raw_files, key=lambda f: f.stat().st_mtime)
    out_file = _download_dir() / f'{job}_trim.mp4'
    ff_cmd = ['ffmpeg', '-y', '-ss', start, '-to', end, '-i', str(raw), '-c', 'copy', str(out_file)]
    code, out, err = await _run(ff_cmd, timeout=300)
    if code != 0 or not out_file.exists() or out_file.stat().st_size == 0:
        ff_cmd = ['ffmpeg', '-y', '-ss', start, '-to', end, '-i', str(raw), '-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'aac', str(out_file)]
        code, out, err = await _run(ff_cmd, timeout=600)
    try:
        raw.unlink()
    except Exception:
        pass
    if code != 0 or not out_file.exists():
        await _safe_send(send_message, chat_id, f'فشل تقطيع الفيديو:\n<code>{html_escape(err or out)}</code>')
        return
    await _send_file(chat_id, out_file, f'مقطع فيديو: {start} - {end}', send_message)


async def _send_latest_file(chat_id: int, title: str, started_at: float, send_message: SendMessage):
    files = [f for f in _download_dir().glob('*') if f.is_file() and f.stat().st_mtime >= started_at - 5]
    if not files:
        await _safe_send(send_message, chat_id, 'اكتمل yt-dlp لكن لم أجد الملف الناتج.')
        return
    file_path = max(files, key=lambda f: f.stat().st_mtime)
    await _send_file(chat_id, file_path, title, send_message)


async def _send_file(chat_id: int, file_path: Path, caption: str, send_message: SendMessage):
    max_mb = int(os.getenv('DOWNLOAD_MAX_FILE_MB', str(_settings().download_max_file_mb)))
    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb > max_mb:
        await _safe_send(send_message, chat_id, f'الملف حجمه {size_mb:.1f}MB وهو أكبر من الحد {max_mb}MB. اختر جودة أقل أو قص مدة أقصر.')
        try:
            file_path.unlink()
        except Exception:
            pass
        return
    await send_document(chat_id, str(file_path), caption=caption[:900])
    try:
        file_path.unlink()
    except Exception:
        pass
