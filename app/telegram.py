from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from .config import get_settings


def html_escape(value: Any) -> str:
    return html.escape(str(value), quote=False)


def get_message(update: Dict[str, Any]) -> Dict[str, Any]:
    return update.get('message') or update.get('edited_message') or {}


def get_callback_query(update: Dict[str, Any]) -> Dict[str, Any]:
    return update.get('callback_query') or {}


def get_chat_id(update: Dict[str, Any]) -> Optional[int]:
    cb = get_callback_query(update)
    if cb:
        msg = cb.get('message') or {}
        chat = msg.get('chat') or {}
    else:
        msg = get_message(update)
        chat = msg.get('chat') or {}
    cid = chat.get('id')
    return int(cid) if cid is not None else None


def get_user_id(update: Dict[str, Any]) -> Optional[int]:
    cb = get_callback_query(update)
    user = (cb.get('from') if cb else None) or (get_message(update).get('from') or {})
    uid = user.get('id')
    return int(uid) if uid is not None else None


def get_text(update: Dict[str, Any]) -> str:
    msg = get_message(update)
    return msg.get('text') or msg.get('caption') or ''


def get_callback_data(update: Dict[str, Any]) -> str:
    return (get_callback_query(update).get('data') or '').strip()


def get_document(update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return get_message(update).get('document')


def get_photo(update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    photos = get_message(update).get('photo') or []
    return photos[-1] if photos else None


def _api_url(method: str) -> str:
    token = get_settings().telegram_bot_token
    return f'https://api.telegram.org/bot{token}/{method}'


async def telegram_api(method: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=70) as client:
        r = await client.post(_api_url(method), json=payload or {})
        r.raise_for_status()
        return r.json()


async def send_chat_action(chat_id: int, action: str = 'typing') -> Dict[str, Any]:
    return await telegram_api('sendChatAction', {'chat_id': chat_id, 'action': action})


async def send_message(
    chat_id: int,
    text: str,
    reply_markup: Dict[str, Any] | None = None,
    *,
    disable_preview: bool = True,
) -> Dict[str, Any]:
    max_len = 3900
    if len(text) <= max_len:
        payload: Dict[str, Any] = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': disable_preview,
        }
        if reply_markup:
            payload['reply_markup'] = reply_markup
        return await telegram_api('sendMessage', payload)

    last: Dict[str, Any] = {}
    for i in range(0, len(text), max_len):
        chunk = text[i:i + max_len]
        payload = {
            'chat_id': chat_id,
            'text': chunk,
            'parse_mode': 'HTML',
            'disable_web_page_preview': disable_preview,
        }
        if i + max_len >= len(text) and reply_markup:
            payload['reply_markup'] = reply_markup
        last = await telegram_api('sendMessage', payload)
    return last


async def edit_message_text(chat_id: int, message_id: int, text: str, reply_markup: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text[:3900],
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
    }
    if reply_markup:
        payload['reply_markup'] = reply_markup
    return await telegram_api('editMessageText', payload)


async def send_document(chat_id: int, path: str, caption: str = '') -> Dict[str, Any]:
    token = get_settings().telegram_bot_token
    url = f'https://api.telegram.org/bot{token}/sendDocument'
    p = Path(path)
    async with httpx.AsyncClient(timeout=360) as client:
        with p.open('rb') as f:
            r = await client.post(
                url,
                data={'chat_id': str(chat_id), 'caption': caption[:1024], 'parse_mode': 'HTML'},
                files={'document': (p.name, f, 'application/octet-stream')},
            )
        r.raise_for_status()
        return r.json()


async def set_webhook() -> Dict[str, Any]:
    settings = get_settings()
    webhook_url = settings.base_url.rstrip('/') + '/telegram/webhook'
    return await telegram_api('setWebhook', {
        'url': webhook_url,
        'secret_token': settings.telegram_webhook_secret,
        'drop_pending_updates': True,
        'allowed_updates': ['message', 'edited_message', 'callback_query'],
    })


async def get_file(file_id: str) -> Dict[str, Any]:
    return await telegram_api('getFile', {'file_id': file_id})


async def download_telegram_file(file_id: str, target_path: str) -> str:
    settings = get_settings()
    meta = await get_file(file_id)
    file_path = meta.get('result', {}).get('file_path')
    if not file_path:
        raise RuntimeError('Telegram did not return file_path')
    url = f'https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}'
    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=360) as client:
        r = await client.get(url)
        r.raise_for_status()
        Path(target_path).write_bytes(r.content)
    return target_path


async def answer_callback_query(callback_query_id: str, text: str = '', *, alert: bool = False) -> Dict[str, Any]:
    return await telegram_api('answerCallbackQuery', {
        'callback_query_id': callback_query_id,
        'text': text[:200],
        'show_alert': alert,
    })
