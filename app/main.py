from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Dict

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request

from .config import get_settings
from .downloader import (
    DownloadError,
    build_choices,
    cleanup_old_downloads,
    describe_info,
    download_media,
    extract_info,
    first_url,
    is_probably_url,
    global_queue,
)
from .notebook_cli import (
    GENERATE_SPECS,
    NotebookCLIError,
    add_source,
    ask,
    auth_check,
    create_notebook,
    delete_notebook,
    generate_artifact,
    list_notebooks,
    summary,
)
from .store import create_job, get_cache, get_job, get_user, recent_jobs, set_cache, update_job, update_user
from .telegram import (
    answer_callback_query,
    download_telegram_file,
    edit_message_text,
    get_callback_query,
    get_chat_id,
    get_callback_data,
    get_document,
    get_message,
    get_text,
    get_user_id,
    html_escape,
    send_chat_action,
    send_document,
    send_message,
    set_webhook,
    telegram_api,
)

app = FastAPI(title='NotebookLM + Media Fetch Bot Pro')


def _is_admin(user_id: int | None) -> bool:
    settings = get_settings()
    return bool(user_id and user_id in settings.admins)


def _main_keyboard() -> Dict[str, Any]:
    return {'inline_keyboard': [
        [
            {'text': '📚 قسم NotebookLM', 'callback_data': 'menu:notebook'},
            {'text': '⬇️ قسم التحميل', 'callback_data': 'menu:download'},
        ],
        [{'text': '📌 حالة الجلسة والمهام', 'callback_data': 'menu:status'}],
    ]}


def _notebook_keyboard() -> Dict[str, Any]:
    return {'inline_keyboard': [
        [{'text': '🆕 دفتر جديد', 'callback_data': 'nb:new'}, {'text': '➕ إضافة مصدر', 'callback_data': 'nb:source'}],
        [{'text': '📝 ملخص', 'callback_data': 'nb:summary'}, {'text': '❓ سؤال', 'callback_data': 'nb:ask'}],
        [{'text': '🎙️ بودكاست', 'callback_data': 'nb:audio'}, {'text': '🎞️ فيديو', 'callback_data': 'nb:video'}],
        [{'text': '📊 شرائح', 'callback_data': 'nb:slides'}, {'text': '🖼️ إنفوجرافيك', 'callback_data': 'nb:infographic'}],
        [{'text': '🧪 اختبار', 'callback_data': 'nb:quiz'}, {'text': '🃏 بطاقات', 'callback_data': 'nb:cards'}],
        [{'text': '🧠 خريطة ذهنية', 'callback_data': 'nb:mindmap'}, {'text': '📋 جدول', 'callback_data': 'nb:table'}],
        [{'text': '📘 تقرير', 'callback_data': 'nb:report'}],
        [{'text': '⬅️ رجوع', 'callback_data': 'menu:main'}],
    ]}


def _download_section_keyboard() -> Dict[str, Any]:
    return {'inline_keyboard': [
        [{'text': '🔗 أرسل رابطًا الآن', 'callback_data': 'dl:await'}],
        [{'text': '🎬 فيديو أفضل جودة', 'callback_data': 'dl:hint:best'}, {'text': '🎧 MP3', 'callback_data': 'dl:hint:audio-mp3'}],
        [{'text': 'YouTube', 'callback_data': 'dl:platform:youtube'}, {'text': 'TikTok', 'callback_data': 'dl:platform:tiktok'}],
        [{'text': 'Instagram', 'callback_data': 'dl:platform:instagram'}, {'text': 'X/Twitter', 'callback_data': 'dl:platform:twitter'}],
        [{'text': 'Facebook', 'callback_data': 'dl:platform:facebook'}, {'text': 'SoundCloud', 'callback_data': 'dl:platform:soundcloud'}],
        [{'text': '⬅️ رجوع', 'callback_data': 'menu:main'}],
    ]}


def _welcome() -> str:
    return (
        'أهلًا بك. اختر القسم الذي تريد العمل عليه.\n\n'
        '📚 <b>NotebookLM</b>: مصادر، تلخيص، سؤال، بودكاست، فيديو، شرائح، إنفوجرافيك، كويز، بطاقات، خريطة ذهنية، جدول، تقرير.\n\n'
        '⬇️ <b>التحميل</b>: استخراج الجودات وتحويل الصوت MP3 من الروابط المدعومة.\n\n'
        'هذا بوت واحد. اختر قسمًا من الأزرار بالأسفل.'
    )


@app.on_event('startup')
async def startup_tasks() -> None:
    settings = get_settings()
    if settings.keepalive_enabled and settings.base_url:
        asyncio.create_task(_keepalive_loop())


async def _keepalive_loop() -> None:
    settings = get_settings()
    await asyncio.sleep(25)
    while True:
        try:
            cleanup_old_downloads()
            async with httpx.AsyncClient(timeout=20) as client:
                await client.get(settings.base_url.rstrip('/') + '/health')
        except Exception:
            pass
        await asyncio.sleep(max(60, int(settings.keepalive_interval_seconds)))


@app.get('/')
async def root() -> Dict[str, Any]:
    settings = get_settings()
    return {
        'app': settings.app_name,
        'status': 'ok',
        'health': '/health',
        'telegram_webhook': '/telegram/webhook',
    }


@app.get('/health')
async def health() -> Dict[str, Any]:
    return {'status': 'ok', 'time': int(time.time()), 'queue': {'active': global_queue.active, 'size': global_queue.size}}


@app.post('/telegram/webhook')
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)) -> Dict[str, Any]:
    settings = get_settings()
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail='Invalid secret token')
    
    update = await request.json()
    chat_id = get_chat_id(update)
    user_id = get_user_id(update)
    
    if not chat_id or not user_id:
        return {'ok': True}
        
    if not _is_admin(user_id):
        await send_message(chat_id, f'عذرًا، هذا البوت خاص. ID الخاص بك: <code>{user_id}</code>')
        return {'ok': True}

    text = get_text(update)
    cb_data = get_callback_data(update)
    
    if cb_data:
        await handle_callback(chat_id, user_id, update)
    elif text.startswith('/start'):
        await send_message(chat_id, _welcome(), _main_keyboard())
    elif text.startswith('/fetch') or text.startswith('/download') or (is_probably_url(text) and not text.startswith('/source')):
        await handle_fetch(chat_id, text)
    elif text.startswith('/source'):
        await handle_source_command(chat_id, text)
    # ... بقية الأوامر يتم التعامل معها هنا ...
    
    return {'ok': True}


async def handle_callback(chat_id: int, user_id: int, update: Dict[str, Any]) -> None:
    cb = get_callback_query(update)
    data = cb.get('data') or ''
    
    if data.startswith('menu:'):
        await handle_menu_callback(chat_id, update)
    elif data.startswith('dl:'):
        await handle_download_callback(chat_id, user_id, update)
    elif data.startswith('nb:'):
        await handle_notebook_callback(chat_id, update)


async def handle_fetch(chat_id: int, text: str) -> None:
    url = first_url(text)
    if not url:
        await send_message(chat_id, 'يرجى إرسال رابط صالح للتحميل.')
        return
        
    status_msg = await send_message(chat_id, '🔎 جاري فحص الرابط واستخراج المعلومات...')
    try:
        info = await extract_info(url)
        choices = build_choices(info)
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        
        # تخزين المعلومات مؤقتاً في حالة المستخدم
        update_user(chat_id, last_media_hash=url_hash)
        user = get_user(chat_id)
        media = user.get('media', {})
        media[url_hash] = {'url': url, 'title': info.get('title', 'media'), 'choices': choices}
        update_user(chat_id, media=media)
        
        await edit_message_text(chat_id, status_msg['result']['message_id'], 
                               describe_info(info) + '\n\nاختر الجودة المطلوبة:', 
                               _download_keyboard(url_hash, choices))
    except Exception as e:
        await edit_message_text(chat_id, status_msg['result']['message_id'], f'❌ فشل فحص الرابط:\n<code>{html_escape(str(e))}</code>')


def _download_keyboard(url_hash: str, choices: list[dict[str, str]]) -> Dict[str, Any]:
    rows = []
    for item in choices:
        rows.append([{'text': item['label'], 'callback_data': f'dl:{url_hash}:{item["id"]}'}])
    return {'inline_keyboard': rows}


async def handle_download_callback(chat_id: int, user_id: int, update: Dict[str, Any]) -> None:
    cb = get_callback_query(update)
    data = cb.get('data', '')
    parts = data.split(':')
    if len(parts) < 3: return
    
    url_hash, choice = parts[1], parts[2]
    await answer_callback_query(cb['id'], 'تمت إضافة طلبك إلى الطابور.')
    
    async def task():
        await run_download_job(chat_id, url_hash, choice)
        
    try:
        global_queue.add(str(user_id), task)
        await send_message(chat_id, f'✅ تم استلام الطلب.\nالطلبات النشطة: {global_queue.active}\nالمنتظرة: {global_queue.size}')
    except Exception as e:
        await send_message(chat_id, f'⚠️ {str(e)}')


async def run_download_job(chat_id: int, url_hash: str, choice: str) -> None:
    user = get_user(chat_id)
    media = user.get('media', {}).get(url_hash)
    if not media:
        await send_message(chat_id, '❌ لم يتم العثور على بيانات الرابط. يرجى إرساله مجدداً.')
        return
        
    progress_msg = await send_message(chat_id, f'⬇️ جاري معالجة: <b>{html_escape(media["title"])}</b>\nالنوع: {choice}')
    try:
        path = await download_media(media['url'], choice, media['title'])
        await edit_message_text(chat_id, progress_msg['result']['message_id'], '📤 جاري إرسال الملف...')
        await send_document(chat_id, path, caption=f"✅ {html_escape(media['title'])}")
        await edit_message_text(chat_id, progress_msg['result']['message_id'], '✅ تم التحميل بنجاح.')
    except Exception as e:
        await edit_message_text(chat_id, progress_msg['result']['message_id'], f'❌ فشل التحميل:\n<code>{html_escape(str(e))}</code>')


async def handle_menu_callback(chat_id: int, update: Dict[str, Any]) -> None:
    cb = get_callback_query(update)
    data = cb.get('data', '')
    msg_id = cb['message']['message_id']
    
    if data == 'menu:notebook':
        await edit_message_text(chat_id, msg_id, '📚 <b>قسم NotebookLM</b>\nإدارة الملاحظات والمصادر الذكية.', _notebook_keyboard())
    elif data == 'menu:download':
        await edit_message_text(chat_id, msg_id, '⬇️ <b>قسم التحميل</b>\nأرسل أي رابط فيديو أو صوت للتحميل.', _download_section_keyboard())
    elif data == 'menu:main':
        await edit_message_text(chat_id, msg_id, _welcome(), _main_keyboard())


async def handle_source_command(chat_id: int, text: str) -> None:
    # منطق إضافة مصدر لـ NotebookLM
    await send_message(chat_id, 'جاري إضافة المصدر إلى NotebookLM...')
    # ... (تكملة المنطق كما في الكود الأصلي)

# ... (بقية دوال المعالجة لـ NotebookLM) ...

@app.get('/set-telegram-webhook')
async def set_telegram_webhook_route(secret: str = Query(default='')) -> Dict[str, Any]:
    settings = get_settings()
    if secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail='Invalid secret')
    return await set_webhook()
