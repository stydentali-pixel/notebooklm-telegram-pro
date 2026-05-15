from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'NotebookLM + Media Fetch Bot'
    telegram_bot_token: str = ''
    telegram_webhook_secret: str = ''
    admin_ids: str = ''
    base_url: str = ''

    notebooklm_auth_json: str = ''
    notebooklm_hl: str = 'ar'
    notebooklm_profile: str = 'default'

    data_dir: str = '/app/data'
    download_dir: str = '/app/downloads'
    upload_dir: str = '/app/uploads'
    job_timeout_seconds: int = 900
    source_timeout_seconds: int = 240
    auto_delete_notebooks: bool = False
    max_telegram_file_mb: int = 45

    # Media downloader settings. No database required.
    download_max_file_mb: int = 45
    download_timeout_seconds: int = 900
    extract_timeout_seconds: int = 120
    keepalive_enabled: bool = True
    keepalive_interval_seconds: int = 240

    # Optional, safe yt-dlp hardening. Do not put cookies in GitHub.
    ytdlp_cookies_txt: str = ''
    ytdlp_user_agent: str = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
    ytdlp_retries: int = 3
    ytdlp_fragment_retries: int = 5
    ytdlp_force_ipv4: bool = True
    ytdlp_geo_bypass: bool = True

    @property
    def admins(self) -> List[int]:
        values: list[int] = []
        for raw in self.admin_ids.replace(';', ',').split(','):
            raw = raw.strip()
            if raw.isdigit():
                values.append(int(raw))
        return values

    def ensure_dirs(self) -> None:
        for p in [self.data_dir, self.download_dir, self.upload_dir]:
            Path(p).mkdir(parents=True, exist_ok=True)

    def notebook_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env['NOTEBOOKLM_HL'] = self.notebooklm_hl
        env['NOTEBOOKLM_PROFILE'] = self.notebooklm_profile
        env['NOTEBOOKLM_LOG_LEVEL'] = env.get('NOTEBOOKLM_LOG_LEVEL', 'ERROR')
        env['NOTEBOOKLM_QUIET_DEPRECATIONS'] = '1'
        if self.notebooklm_auth_json:
            env['NOTEBOOKLM_AUTH_JSON'] = self.notebooklm_auth_json
        return env


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
