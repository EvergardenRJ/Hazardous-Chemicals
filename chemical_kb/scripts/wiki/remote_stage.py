"""Server-local staging, preserving unrelated runtime modules."""
import hashlib,json,os,shutil,subprocess,sys,tarfile
from pathlib import Path
runtime=Path("/root/autodl-tmp/chemical_kb")
stage=Path("/root/autodl-tmp/chemical_kb_wiki_stage_20261001")
archive=Path("/root/autodl-tmp/llmwiki-v2-release-20261001.tgz")
stage.mkdir(exist_ok=True)
for name in ("core","app","configs"):
    if (runtime/name).exists():shutil.copytree(runtime/name,stage/name,dirs_exist_ok=True)
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        target=(stage/member.name).resolve()
        if not target.is_relative_to(stage.resolve()) or member.issym() or member.islnk():raise ValueError("Unsafe archive")
    tar.extractall(stage)
subprocess.run([sys.executable,str(stage/"scripts/wiki/patch_compat.py")],check=True)
shutil.copytree(runtime/"data/wiki",stage/"data/wiki",dirs_exist_ok=True)
print(json.dumps({"stage":str(stage),"files":len(json.loads((stage/"release_manifest.json").read_text()))},ensure_ascii=False))
