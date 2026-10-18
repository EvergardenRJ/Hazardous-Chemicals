import json
from pathlib import Path
from core.news_store import apply_export,NEWS_DIR
p=NEWS_DIR/'initial_export.json'
print(json.dumps(apply_export(json.loads(p.read_text(encoding='utf-8-sig'))),ensure_ascii=False))
p.unlink()
