from __future__ import annotations

import os
from pathlib import Path


def prepare_youtube_cookies() -> list[str]:
    """
    Reads YouTube cookies from Railway env variables and writes them to /tmp.
    Returns yt-dlp args: ["--cookies", "/tmp/youtube-cookies.txt"]
    """
    cookies = os.getenv("YTDLP_COOKIES") or os.getenv("YOUTUBE_COOKIES")

    if not cookies:
        return []

    cookies_path = Path("/tmp/youtube-cookies.txt")
    cookies_path.write_text(cookies, encoding="utf-8")

    return ["--cookies", str(cookies_path)]
