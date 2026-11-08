#!/usr/bin/env python3
"""Fill missing local secrets without displaying or replacing existing values."""
import os
from pathlib import Path
import secrets
from dotenv import dotenv_values

path = Path('.env')
values = dotenv_values(path)
defaults = {
    'ADMIN_USERNAME': 'admin', 'ADMIN_PASSWORD': secrets.token_urlsafe(32),
    'SERVICE_USERNAME': 'unter-service', 'SERVICE_PASSWORD': secrets.token_urlsafe(32),
    'READER_USERNAME': 'unter-reader', 'READER_PASSWORD': secrets.token_urlsafe(32),
    'POSTGRES_PASSWORD': secrets.token_urlsafe(32),
    'CORE_DB_PASSWORD': secrets.token_urlsafe(32),
    'AGENT_DB_PASSWORD': secrets.token_urlsafe(32),
    'ACTIVITY_DB_PASSWORD': secrets.token_urlsafe(32),
    'RABBITMQ_PASSWORD': secrets.token_urlsafe(32),
    'OPENAI_MODEL': 'gpt-5-nano', 'AGENT_MODE': 'live',
}
with path.open('a') as stream:
    stream.write('\n')
    for name, value in defaults.items():
        if not values.get(name):
            stream.write(f'{name}={value}\n')
os.chmod(path, 0o600)
print('Local .env initialized; existing values preserved. No secrets displayed.')
