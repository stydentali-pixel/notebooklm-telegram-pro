from __future__ import annotations

import asyncio
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
    return m.group(0) if m else ''


def _safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', '_', name or 'media')
    name = re.sub(r'\s+', ' ', name).strip()
    return (name[:90] or 'media')


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


# Avoid importing contextlib only inside exception path on old linters.
import contextlib  # noqa: E402


def _get_yt_dlp_base_args() -> list[str]:
    settings = get_settings()
    args = [
        'python', '-m', 'yt_dlp',
        '--no-playlist',
        '--no-warnings',
    ]
    
    # إضافة الكوكيز إذا وجدت في ملف
    cookies_file = Path(settings.data_dir) / 'cookies.txt'
    if cookies_file.exists():
        args.extend(['--cookies', str(cookies_file)])
    
    # إضافة البروكسي إذا وجد في المتغيرات
    proxy = os.getenv('DOWNLOAD_PROXY')
    if proxy:
        args.extend(['--proxy', proxy])
        
    # إضافة User-Agent قوي لتجنب الحظر
    args.extend(['--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'])
    
    return args


async def extract_info(url: str) -> Dict[str, Any]:
    settings = get_settings()
    cmd = _get_yt_dlp_base_args() + [
        '--dump-single-json',
        '--skip-download',
        url,
    ]
    code, out, err = await _run(cmd, timeout=settings.extract_timeout_seconds)
    if code != 0:
        # محاولة استخدام مكتبة بديلة أو استراتيجية أخرى إذا فشل yt-dlp الأساسي
        raise DownloadError((err or out or 'فشل استخراج معلومات الرابط')[-1500:])
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
    for h in sorted(seen, reverse=True)[:6]:
        choices.append({'id': f'q{h}', 'label': f'🎬 {h}p'})
    choices.append({'id': 'best', 'label': '🎬 أفضل جودة'})
    choices.append({'id': 'audio-mp3', 'label': '🎧 MP3 صوت'})
    return choices


def describe_info(info: Dict[str, Any]) -> str:
    title = info.get('title') or 'بدون عنوان'
    uploader = info.get('uploader') or info.get('channel') or 'غير معروف'
    duration = int(info.get('duration') or 0)
    mins = duration // 60
    secs = duration % 60
    return f'{title}\nالناشر: {uploader}\nالمدة: {mins}:{secs:02d}'


def _format_args(choice: str) -> list[str]:
    if choice == 'audio-mp3':
        return ['-x', '--audio-format', 'mp3', '--audio-quality', '0']
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
    
    cmd = _get_yt_dlp_base_args() + [
        '--max-filesize', f'{settings.download_max_file_mb}M',
        '--merge-output-format', 'mp4',
        '--newline',
        *_format_args(choice),
        '-o', out_template,
        url,
    ]
    
    code, out, err = await _run(cmd, timeout=settings.download_timeout_seconds, cwd=str(root))
    if code != 0:
        # إذا كان الخطأ متعلقاً بـ Sign in، نقوم بتنبيه المستخدم بوضوح
        if 'Sign in to confirm you' in err or 'confirm you’re not a bot' in err:
            raise DownloadError('يوتيوب يطلب تسجيل الدخول (Bot Detection). يرجى إضافة ملف cookies.txt إلى مجلد data في المستودع.')
        raise DownloadError((err or out or 'فشل التحميل')[-1800:])
        
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
