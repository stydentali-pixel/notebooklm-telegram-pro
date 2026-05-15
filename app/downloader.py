from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from .config import get_settings

URL_RE = re.compile(r'https?://\S+', re.I)


class DownloadError(RuntimeError):
    pass


# --- نظام الطابور (Queue System) المدمج ---
class JobQueue:
    def __init__(self, concurrency: int = 2):
        self.concurrency = concurrency
        self.running = 0
        self.items: List[Dict[str, Any]] = []
        self.user_locks: set[str] = set()
        self.last_user_run: Dict[str, float] = {}

    @property
    def size(self) -> int:
        return len(self.items)

    @property
    def active(self) -> int:
        return self.running

    def can_accept_user(self, user_id: str) -> bool:
        settings = get_settings()
        last = self.last_user_run.get(user_id, 0)
        cooldown = getattr(settings, 'user_cooldown_seconds', 10)
        return (time.time() - last) >= cooldown

    def add(self, user_id: str, fn: Callable):
        user_id = str(user_id)
        if user_id in self.user_locks:
            raise DownloadError('لديك طلب قيد التنفيذ. انتظر حتى ينتهي ثم أرسل طلبًا جديدًا.')
        
        if not self.can_accept_user(user_id):
            settings = get_settings()
            cooldown = getattr(settings, 'user_cooldown_seconds', 10)
            raise DownloadError(f'انتظر {cooldown} ثوانٍ بين الطلبات.')
            
        self.items.append({'user_id': user_id, 'fn': fn})
        asyncio.create_task(self.pump())

    async def pump(self):
        while self.running < self.concurrency and self.items:
            item = self.items.pop(0)
            if item['user_id'] in self.user_locks:
                self.items.append(item)
                break
                
            self.running += 1
            self.user_locks.add(item['user_id'])
            self.last_user_run[item['user_id']] = time.time()
            
            try:
                await item['fn']()
            except Exception:
                pass
            finally:
                self.running -= 1
                self.user_locks.remove(item['user_id'])
                asyncio.create_task(self.pump())

# إنشاء نسخة واحدة من الطابور
# ملاحظة: max_concurrent_jobs يمكن إضافته للإعدادات لاحقاً
global_queue = JobQueue(concurrency=2)


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
    # التحقق من المتغير الجديد YTDLP_COOKIES_TXT أو ملف cookies.txt التقليدي
    raw = (settings.ytdlp_cookies_txt or '').strip()
    if raw:
        cookie_path = Path('/tmp/ytdlp_cookies.txt')
        cookie_path.write_text(raw, encoding='utf-8')
        cookie_path.chmod(0o600)
        return ['--cookies', str(cookie_path)]
    
    # التحقق من وجود ملف cookies.txt في مجلد data
    local_cookies = Path(settings.data_dir) / 'cookies.txt'
    if local_cookies.exists():
        return ['--cookies', str(local_cookies)]
        
    return []


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
        '--no-playlist',
        '--restrict-filenames',
        '--no-warnings',
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
            'يرجى إضافة الكوكيز عبر متغير YTDLP_COOKIES_TXT في Railway.\n\n'
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
    
    # عرض الجودات بطريقة مرتبة كما في الحزمة الجديدة
    for h in sorted(seen, reverse=True)[:7]:
        icon = '🎥' if h >= 720 else '🎬'
        choices.append({'id': f'q{h}', 'label': f'{icon} فيديو {h}p'})
        
    choices.append({'id': 'best', 'label': '🏆 أفضل جودة متاحة'})
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
    size = info.get('filesize') or info.get('filesize_approx') or 0
    size_str = f"{size / (1024*1024):.1f}MB" if size else "غير معروف"
    
    return f'🎬 <b>{_safe_name(title)}</b>\nالمنصة: {platform}\nالناشر: {uploader}\nالمدة: {mins}:{secs:02d}\nالحجم التقريبي: {size_str}'


def _format_args(choice: str) -> list[str]:
    if choice == 'audio-mp3':
        return ['-x', '--audio-format', 'mp3', '--audio-quality', '0']
    if choice == 'audio-m4a':
        return ['-f', 'bestaudio[ext=m4a]/bestaudio', '--extract-audio', '--audio-format', 'm4a']
    if choice == 'best':
        return ['-f', 'bestvideo+bestaudio/best']
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
