#!/usr/bin/env python3
"""Exercise migrations in disposable PostgreSQL databases using the local Compose stack.

Checks fresh installs, simultaneous upgrades, legacy adoption, drift refusal and
an incremental upgrade/downgrade. Never drops the application's own databases.
"""
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(args, source=None):
    result = subprocess.run(args, input=source, text=True, capture_output=True, cwd=ROOT)
    if result.returncode:
        from dotenv import dotenv_values
        output = result.stdout + result.stderr
        for name, value in dotenv_values(ROOT/'.env').items():
            if value and any(part in name for part in ('PASSWORD','KEY','TOKEN')):
                output = output.replace(value, '[REDACTED]')
        print(output[-8000:])
        raise RuntimeError(f'Migration check subprocess failed (exit {result.returncode})')
    return result.stdout


def postgres(sql, database="postgres"):
    return run(['docker', 'compose', 'exec', '-T', 'postgres', 'psql', '-At', '-U', 'unter',
                '-d', database, '-v', 'ON_ERROR_STOP=1', '-c', sql])


PROGRAM = r'''
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from alembic import command
from alembic.script import ScriptDirectory
from unter.common import connect
from unter.migrate import migration_config, upgrade_database

service = SERVICE
case = CASE
assert os.environ['DB_NAME'].startswith('unter_migration_test_')
tables = ['schedule','runs'] if service == 'agent' else ['activity']
config = migration_config(service)
head = ScriptDirectory.from_config(config).get_current_head()

def snapshot():
    with connect() as db:
        return {table: db.execute('SELECT * FROM '+table+' ORDER BY id').fetchall() for table in tables}

if case == 'drift':
    table = tables[0]
    with connect() as db:
        db.execute('CREATE TABLE '+table+' (id text PRIMARY KEY, unexpected text)')
        db.execute('INSERT INTO '+table+" VALUES ('keep','unchanged')")
    try:
        upgrade_database(service)
    except RuntimeError as error:
        assert 'differs from the initial schema' in str(error)
    else:
        raise AssertionError('Incompatible schema was accepted')
    with connect() as db:
        assert db.execute("SELECT to_regclass('public.alembic_version') AS name").fetchone()['name'] is None
        assert db.execute('SELECT unexpected FROM '+table).fetchone()['unexpected'] == 'unchanged'
else:
    before = None
    if case == 'legacy':
        with connect() as db:
            db.execute(LEGACY_SQL)
        before = snapshot()
        upgrade_database(service)
    else:
        # Two separate interpreters reproduce simultaneous service starts safely.
        def upgrade(_):
            result = subprocess.run([sys.executable,'-m','unter.migrate','upgrade','--service',service],capture_output=True)
            assert result.returncode == 0, 'Concurrent upgrade failed'
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(upgrade, range(2)))
    with connect() as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()['version_num'] == head
        if service == 'agent':
            # agent_0002-0004: one default settings row; empty reports, outbox, deliveries and decisions.
            assert db.execute('SELECT id, window_hours, recipients FROM report_settings').fetchall() == [
                {'id': 1, 'window_hours': 24, 'recipients': []}]
            assert db.execute('SELECT (SELECT count(*) FROM reports) + (SELECT count(*) FROM agent_outbox) '
                              '+ (SELECT count(*) FROM report_deliveries) + (SELECT count(*) FROM report_decisions) AS n').fetchone()['n'] == 0
    if before is not None:
        assert snapshot() == before, 'Legacy rows or schedule were changed'
    else:
        before = snapshot()
    # Re-running startup migrations must be a no-op.
    upgrade_database(service)
    assert snapshot() == before
    # An isolated test-only revision proves real incremental upgrade and rollback.
    with tempfile.TemporaryDirectory(prefix='unter-migration-chain-') as folder:
        original = Path(config.get_main_option('script_location'))
        shutil.copytree(original, folder, dirs_exist_ok=True)
        table = 'runs' if service == 'agent' else 'activity'
        revision = Path(folder)/'versions'/'test_incremental.py'
        revision.write_text(
            'from alembic import op\nimport sqlalchemy as sa\n'
            + "revision='migration_test_0002'\ndown_revision="+repr(head)+'\n'
            + 'def upgrade():\n    op.add_column('+repr(table)+", sa.Column('migration_probe',sa.Text))\n"
            + 'def downgrade():\n    op.drop_column('+repr(table)+", 'migration_probe')\n")
        config.set_main_option('script_location',folder)
        command.upgrade(config,'head')
        with connect() as db:
            assert db.execute('SELECT version_num FROM alembic_version').fetchone()['version_num'] == 'migration_test_0002'
            db.execute('SELECT migration_probe FROM '+table)
        command.downgrade(config,head)
        assert snapshot() == before, 'Incremental migration lost existing records'
        with connect() as db:
            assert db.execute('SELECT version_num FROM alembic_version').fetchone()['version_num'] == head
'''

for service, container in [('agent', 'agent'), ('activity', 'worker')]:
    legacy = (ROOT/'services/python/tests/fixtures'/f'{service}_legacy.sql').read_text()
    for case in ('fresh', 'legacy', 'drift'):
        name = f'unter_migration_test_{uuid.uuid4().hex}'
        assert name.startswith('unter_migration_test_') and name.replace('_', '').isalnum()
        postgres(f'CREATE DATABASE {name} OWNER {service}')
        try:
            source = f'SERVICE={service!r}\nCASE={case!r}\nLEGACY_SQL={legacy!r}\n'+PROGRAM
            run(['docker','compose','exec','-T','-e',f'DB_NAME={name}',container,'python','-'], source)
            print(f'PASS: {service} {case} migrations')
        finally:
            postgres(f'DROP DATABASE {name} WITH (FORCE)')
print('PASS: both Alembic histories, concurrent fresh upgrades, data-preserving legacy adoption, incremental upgrades/downgrades, drift refusal')

for attempt in range(30):
    found = postgres("SELECT to_regclass('public.flyway_schema_history')", database='core')
    if 'flyway_schema_history' in found:
        break
    time.sleep(2)
else:
    raise AssertionError('Core Flyway history was not created')
assert postgres('SELECT bool_and(success) FROM flyway_schema_history', database='core').strip() == 't'
print('PASS: core Flyway history is present with successful migrations')
