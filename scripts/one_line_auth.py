from __future__ import annotations

import json
import sys
from pathlib import Path

if len(sys.argv) != 2:
    print('Usage: python scripts/one_line_auth.py /path/to/storage_state.json')
    raise SystemExit(1)

path = Path(sys.argv[1]).expanduser()
if not path.exists():
    print(f'File not found: {path}')
    raise SystemExit(1)

obj = json.loads(path.read_text(encoding='utf-8'))
print(json.dumps(obj, ensure_ascii=False, separators=(',', ':')))
