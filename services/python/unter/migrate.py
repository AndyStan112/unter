"""Run or inspect the selected Python service's Alembic migration chain."""
import argparse
import os
from pathlib import Path
from alembic import command
from alembic.config import Config

SERVICES = ('agent', 'activity')


def migration_config(service):
    if service not in SERVICES:
        raise ValueError('Only agent and activity use Alembic; core uses Flyway')
    return Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'),
                  ini_section=service)


def upgrade_database(service):
    command.upgrade(migration_config(service), 'head')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('upgrade', 'current', 'history', 'heads', 'downgrade'))
    parser.add_argument('revision', nargs='?')
    parser.add_argument('--service', choices=SERVICES,
                        default=os.getenv('MIGRATION_SERVICE', os.getenv('DB_NAME')))
    args = parser.parse_args()
    if args.service not in SERVICES:
        parser.error('Pass --service agent or --service activity')
    if args.action == 'downgrade' and not args.revision:
        parser.error('downgrade requires an explicit target revision')
    if args.revision and args.action not in ('upgrade', 'downgrade'):
        parser.error('This command does not accept a target revision')
    config = migration_config(args.service)
    if args.action in ('upgrade', 'downgrade'):
        getattr(command, args.action)(config, args.revision or 'head')
    else:
        getattr(command, args.action)(config)


if __name__ == '__main__':
    main()
