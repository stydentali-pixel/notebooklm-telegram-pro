from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from .config import get_settings

_lock = Lock()


def _path() -> Path:
    return Path(get_settings().data_dir) / 'state.json'


def _load() -> Dict[str, Any]:
    p = _path()
    if not p.exists():
        return {'users': {}, 'jobs': {}}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {'users': {}, 'jobs': {}}


def _save(data: Dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(p)


def get_user(chat_id: int) -> Dict[str, Any]:
    with _lock:
        data = _load()
        users = data.setdefault('users', {})
        user = users.setdefault(str(chat_id), {'chat_id': chat_id, 'created_at': time.time()})
        _save(data)
        return user


def update_user(chat_id: int, **patch: Any) -> Dict[str, Any]:
    with _lock:
        data = _load()
        users = data.setdefault('users', {})
        user = users.setdefault(str(chat_id), {'chat_id': chat_id, 'created_at': time.time()})
        user.update(patch)
        user['updated_at'] = time.time()
        _save(data)
        return user


def create_job(chat_id: int, kind: str, notebook_id: str, description: str = '') -> Dict[str, Any]:
    with _lock:
        data = _load()
        jobs = data.setdefault('jobs', {})
        job_id = uuid.uuid4().hex[:12]
        job = {
            'id': job_id,
            'chat_id': chat_id,
            'kind': kind,
            'notebook_id': notebook_id,
            'description': description,
            'status': 'queued',
            'created_at': time.time(),
        }
        jobs[job_id] = job
        _save(data)
        return job


def update_job(job_id: str, **patch: Any) -> Dict[str, Any]:
    with _lock:
        data = _load()
        job = data.setdefault('jobs', {}).setdefault(job_id, {'id': job_id})
        job.update(patch)
        job['updated_at'] = time.time()
        _save(data)
        return job


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return _load().get('jobs', {}).get(job_id)


def recent_jobs(chat_id: int, limit: int = 5) -> list[Dict[str, Any]]:
    with _lock:
        jobs = [j for j in _load().get('jobs', {}).values() if j.get('chat_id') == chat_id]
        jobs.sort(key=lambda j: j.get('created_at', 0), reverse=True)
        return jobs[:limit]
