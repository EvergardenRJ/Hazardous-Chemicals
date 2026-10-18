"""Apply narrow compatibility edits; never replace other workspaces' API/frontend code."""
from pathlib import Path
import re
root=Path(__file__).resolve().parents[2]
p=root/"app/explorer_api.py"
if p.exists():
    text=p.read_text(encoding="utf-8")
    start=text.find('@app.get("/api/wiki")')
    end=text.find('@app.get("/")',start)
    if start>=0 and end>start:
        text=text[:start]+"from core.wiki.routes import register as register_wiki\nwiki_service = register_wiki(app)\n\n\n"+text[end:]
    elif "wiki_service = register_wiki(app)" not in text:
        raise RuntimeError("Wiki API boundary changed; preserve file and review")
    text=re.sub(r'wiki_count = [^\n]+', 'wiki_count = len(wiki_service.repo.list())',text,count=1)
    p.write_text(text,encoding="utf-8")
p=root/"explorer_web/src/Panels.jsx"
text=p.read_text(encoding="utf-8")
start=text.find("export function WikiWorkspace()")
if start>=0:
    text=text[:start]+"export { default as WikiWorkspace } from './WikiWorkspace.jsx';\n"
p.write_text(text,encoding="utf-8")
p=root/"core/wiki/repository.py"
text=p.read_text(encoding="utf-8").replace("INSERT INTO review_events VALUES(?,?,?,?,?,?,?,?,?,?)","INSERT INTO review_events VALUES(?,?,?,?,?,?,?,?,?)")
p.write_text(text,encoding="utf-8")
print("compatibility boundaries patched")
