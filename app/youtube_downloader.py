from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import Optional

from youtube_cookies import prepare_youtube_cookies


YOUTUBE_RE = re.compile(
    r"(https?://(?:www\.)?(?:youtube\.com|youtu\.be|m\.youtube\.com)/\S+)",
    re.I,
)


def extract_youtube_url(text: str) -> Optional[str]:
    match = YOUTUBE_RE.search(text or "")
    return match.group(1) if match else None


async def download_youtube_video(url: str, download_dir: str = "/tmp") -> Path:
    out_dir = Path(download_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    output_template = str(out_dir / f"youtube_{int(time.time())}.%(ext)s")

    cookies_args = prepare_youtube_cookies()

    cmd = [
        "yt-dlp",
        *cookies_args,
        "-f",
        "bv*[height<=720]+ba/b[height<=720]/best",
        "--merge-output-format",
        "mp4",
        "--max-filesize",
        os.getenv("YOUTUBE_MAX_FILESIZE", "45M"),
        "-o",
        output_template,
        url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = (stderr or stdout).decode("utf-8", errors="ignore")[-2000:]
        raise RuntimeError(err or "yt-dlp failed")

    files = sorted(out_dir.glob("youtube_*"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not files:
        raise RuntimeError("لم يتم العثور على ملف الفيديو بعد التحميل.")

    return files[0]
