#!/usr/bin/env python3
"""Add only Unter's route, preserving other applications and keeping a backup."""
import subprocess
from pathlib import Path

remote = r'''
from pathlib import Path
from datetime import datetime, timezone
import subprocess

config=Path('/home/andy/apps/caddy_proxy/Caddyfile')
original=config.read_text()
route="\nunter.windogs.win {\n    encode zstd gzip\n    reverse_proxy 172.22.0.1:30574\n}\n"
def docker(*args):
    return subprocess.run(['docker','exec','windogs-proxy',*args],capture_output=True,text=True)
if docker('wget','-q','-O','/dev/null','http://172.22.0.1:30574/healthz').returncode:
    raise SystemExit('Private Unter gateway is not healthy; Caddy left unchanged.')
if 'unter.windogs.win' in original:
    if '172.22.0.1:30574' not in original:
        raise SystemExit('Hostname already exists with an unexpected route; Caddy left unchanged.')
    print('Unter Caddy route is already present.')
    raise SystemExit(0)
backup=Path('/home/andy/apps/unter/caddy-backups')
backup.mkdir(parents=True,exist_ok=True)
filename=backup/('Caddyfile.'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
filename.write_text(original)
filename.chmod(0o600)
# Preserve the existing inode because Caddy may bind-mount this file.
config.write_text(original+route)
validate=docker('caddy','validate','--config','/etc/caddy/Caddyfile','--adapter','caddyfile')
if validate.returncode:
    config.write_text(original)
    raise SystemExit('Caddy validation failed; original configuration restored.')
reload=docker('caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile')
if reload.returncode:
    config.write_text(original)
    docker('caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile')
    raise SystemExit('Caddy reload failed; original configuration restored.')
print('Unter HTTPS route added. Previous Caddyfile backed up under apps/unter/caddy-backups.')
'''
result=subprocess.run(['ssh','-F','/dev/null','-o','BatchMode=yes','andy@ssh.windogs.win','python3 -'],input=remote,text=True)
raise SystemExit(result.returncode)
