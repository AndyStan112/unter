#!/usr/bin/env python3
"""Check tracked/staged content without ever printing detected values."""
import re
import subprocess
from pathlib import Path
from dotenv import dotenv_values
values=dotenv_values('.env')
secrets=[v.encode() for k,v in values.items() if v and len(v)>=16 and ('PASSWORD' in k or 'KEY' in k or 'TOKEN' in k)]
files=subprocess.check_output(['git','ls-files','-z']).decode().split('\0')
failed=[]
for name in filter(None,files):
    if Path(name).name.startswith('.env') and name!='.env.example':
        failed.append(name); continue
    data=subprocess.check_output(['git','show',':'+name])
    if any(value in data for value in secrets) or re.search(rb'sk-(?:proj-)?[A-Za-z0-9_-]{30,}',data):
        failed.append(name)
if failed:
    print('Secret check failed in: '+', '.join(failed))
    raise SystemExit(1)
print('Secret check passed: no local secret values in tracked/staged files.')
