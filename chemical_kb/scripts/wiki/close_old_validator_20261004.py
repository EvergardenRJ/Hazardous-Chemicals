import os,signal,json
from pathlib import Path
proc=Path('/proc/7425/cmdline')
if proc.exists():
 cmd=proc.read_bytes()
 assert b'validate_full_catalogue_20261004.py' in cmd and b'extract_corpus' not in cmd
 os.kill(7425,signal.SIGTERM)
print(json.dumps({'old_output_blocked_validator_stopped':True,'kg_running':Path('/proc/5132').exists()}))
