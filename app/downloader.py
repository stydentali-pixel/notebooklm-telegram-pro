from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List

from .config import get_settings

URL_RE = re.compile(r'https?://\S+', re.I)


class DownloadError(RuntimeError):
    pass


def is_probably_url(text: str) -> bool:
    return bool(URL_RE.search(text or ''))


def first_url(text: str) -> str:
    m = URL_RE.search(text or '')
    if not m:
        return ''
    return m.group(0).strip().rstrip('.,)؛،')


def detect_platform(url: str) -> str:
    u = (url or '').lower()
    if 'youtube.com' in u or 'youtu.be' in u:
        return 'youtube'
    if 'tiktok.com' in u:
        return 'tiktok'
    if 'instagram.com' in u:
        return 'instagram'
    if 'x.com' in u or 'twitter.com' in u:
        return 'twitter'
    if 'facebook.com' in u or 'fb.watch' in u:
        return 'facebook'
    if 'soundcloud.com' in u:
        return 'soundcloud'
    return 'generic'


def _safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', '_', name or 'media')
    name = re.sub(r'\s+', ' ', name).strip()
    return (name[:90] or 'media')


def _cookies_args() -> list[str]:
    settings = get_settings()
    raw = (settings.ytdlp_cookies_txt or '').strip()
    if not raw:
        return []
    cookie_path = Path('/tmp/ytdlp_cookies.txt')
    cookie_path.write_text(raw, encoding='utf-8')
    cookie_path.chmod(0o600)
    return ['--cookies', str(cookie_path)]


def _common_args() -> list[str]:
    settings = get_settings()
    args = [
        '--retries', str(settings.ytdlp_retries),
        '--fragment-retries', str(settings.ytdlp_fragment_retries),
        '--socket-timeout', '30',
        '--no-check-certificates',
        '--user-agent', settings.ytdlp_user_agent,
        '--referer', 'https://www.youtube.com/',
        '--add-header', 'Accept-Language: ar,en-US;q=0.9,en;q=0.8',
    ]
    if settings.ytdlp_force_ipv4:
        args.append('--force-ipv4')
    if settings.ytdlp_geo_bypass:
        args.append('--geo-bypass')
    args += _cookies_args()
    return args


def _friendly_error(raw: str) -> str:
    text = raw or 'فشل التحميل.'
    lower = text.lower()
    if 'sign in to confirm' in lower or 'not a bot' in lower or 'confirm you' in lower:
        return (
            'يوتيوب طلب تحققًا من الجلسة لأن الطلب صادر من سيرفر. '
            'أضف متغير YTDLP_COOKIES_TXT من حساب مخصص أو جرّب رابطًا آخر.\n\n'
            + text[-900:]
        )
    if 'private video' in lower:
        return 'الفيديو خاص أو يحتاج صلاحية مشاهدة.'
    if 'video unavailable' in lower:
        return 'الفيديو غير متاح لهذا الرابط أو هذه المنطقة.'
    if 'unsupported url' in lower:
        return 'الرابط غير مدعوم من yt-dlp حاليًا.'
    return text[-1600:]


async def _run(cmd: list[str], timeout: int = 600, cwd: str | None = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        with contextlib.suppress(Exception):
            proc.kill()
        raise DownloadError('انتهت مهلة العملية. الرابط كبير أو المنصة بطيئة.') from exc
    return proc.returncode or 0, out_b.decode('utf-8', 'replace'), err_b.decode('utf-8', 'replace')


async def extract_info(url: str) -> Dict[str, Any]:
    settings = get_settings()
    cmd = [
        'python', '-m', 'yt_dlp',
        *_common_args(),
        '--dump-single-json',
        '--no-playlist',
        '--no-warnings',
        '--skip-download',
        url,
    ]
    code, out, err = await _run(cmd, timeout=settings.extract_timeout_seconds)
    if code != 0:
        raise DownloadError(_friendly_error(err or out or 'فشل استخراج معلومات الرابط'))
    try:
        info = json.loads(out)
    except Exception as exc:
        raise DownloadError('فشل قراءة بيانات yt-dlp.') from exc
    return info


def build_choices(info: Dict[str, Any]) -> List[Dict[str, str]]:
    choices: list[dict[str, str]] = []
    seen: set[int] = set()
    for fmt in info.get('formats') or []:
        height = fmt.get('height')
        vcodec = fmt.get('vcodec')
        if not height or height in seen or vcodec == 'none':
            continue
        if int(height) < 144:
            continue
        seen.add(int(height))
    for h in sorted(seen, reverse=True)[:7]:
        choices.append({'id': f'q{h}', 'label': f'🎬 فيديو {h}p'})
    choices.append({'id': 'best', 'label': '🏆 أفضل فيديو متاح'})
    choices.append({'id': 'audio-mp3', 'label': '🎧 تحويل إلى MP3'})
    choices.append({'id': 'audio-m4a', 'label': '🎵 صوت M4A'})
    return choices


def describe_info(info: Dict[str, Any]) -> str:
    title = info.get('title') or 'بدون عنوان'
    uploader = info.get('uploader') or info.get('channel') or 'غير معروف'
    duration = int(info.get('duration') or 0)
    mins = duration // 60
    secs = duration % 60
    platform = detect_platform(info.get('webpage_url') or info.get('original_url') or '')
    return f'{title}\nالمنصة: {platform}\nالناشر: {uploader}\nالمدة: {mins}:{secs:02d}'


def _format_args(choice: str) -> list[str]:
    if choice == 'audio-mp3':
        return ['-x', '--audio-format', 'mp3', '--audio-quality', '0']
    if choice == 'audio-m4a':
        return ['-f', 'bestaudio[ext=m4a]/bestaudio', '--extract-audio', '--audio-format', 'm4a']
    if choice == 'best':
        return ['-f', 'bv*+ba/b']
    m = re.search(r'(\d+)', choice)
    h = m.group(1) if m else '720'
    return ['-f', f'bestvideo[height<={h}]+bestaudio/best[height<={h}]']


async def download_media(url: str, choice: str, title: str = '') -> str:
    settings = get_settings()
    root = Path(settings.download_dir) / 'media' / f'{int(time.time())}_{os.getpid()}'
    root.mkdir(parents=True, exist_ok=True)
    out_template = str(root / (_safe_name(title) + '.%(ext)s'))
    cmd = [
        'python', '-m', 'yt_dlp',
        *_common_args(),
        '--no-playlist',
        '--max-filesize', f'{settings.download_max_file_mb}M',
        '--merge-output-format', 'mp4',
        '--newline',
        *_format_args(choice),
        '-o', out_template,
        url,
    ]
    code, out, err = await _run(cmd, timeout=settings.download_timeout_seconds, cwd=str(root))
    if code != 0:
        raise DownloadError(_friendly_error(err or out or 'فشل التحميل'))
    files = [p for p in root.iterdir() if p.is_file() and not p.name.endswith('.part')]
    if not files:
        raise DownloadError('لم ينتج yt-dlp أي ملف.')
    file_path = max(files, key=lambda p: p.stat().st_size)
    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb > settings.max_telegram_file_mb:
        raise DownloadError(f'الملف الناتج {size_mb:.1f}MB أكبر من حد تليجرام الحالي {settings.max_telegram_file_mb}MB.')
    return str(file_path)


def cleanup_old_downloads(max_age_seconds: int = 7200) -> None:
    settings = get_settings()
    root = Path(settings.download_dir) / 'media'
    if not root.exists():
        return
    now = time.time()
    for child in root.iterdir():
        try:
            if child.is_dir() and now - child.stat().st_mtime > max_age_seconds:
                shutil.rmtree(child, ignore_errors=True)
        except Exception:
            pass
