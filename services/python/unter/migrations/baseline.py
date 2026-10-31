"""Strict adoption of the original unversioned schema, without discarding data.

Used only by the initial revisions. Future revisions must use explicit operations.
"""
import re
from alembic import op
from sqlalchemy import inspect


def normalized(value):
    return re.sub(r'[\s()]', '', ('' if value is None else str(value))).lower()


def ensure_initial_table(table):
    connection = op.get_bind()
    inspector = inspect(connection)
    if not inspector.has_table(table.name):
        table.create(connection)
        return
    actual = {column['name']: column for column in inspector.get_columns(table.name)}
    expected = {column.name: column for column in table.columns}
    mismatch = actual.keys() != expected.keys()
    for name in actual.keys() & expected.keys():
        old, new = actual[name], expected[name]
        expected_default = new.server_default.arg if new.server_default is not None else None
        mismatch |= (
            str(old['type'].compile(dialect=connection.dialect)) != str(new.type.compile(dialect=connection.dialect))
            or old['nullable'] != new.nullable
            or normalized(old['default']) != normalized(expected_default)
        )
    mismatch |= inspector.get_pk_constraint(table.name)['constrained_columns'] != [c.name for c in table.primary_key]
    actual_checks = sorted(normalized(c['sqltext']) for c in inspector.get_check_constraints(table.name))
    expected_checks = sorted(normalized(c.sqltext) for c in table.constraints if hasattr(c, 'sqltext'))
    mismatch |= actual_checks != expected_checks
    mismatch |= bool(inspector.get_foreign_keys(table.name) or inspector.get_unique_constraints(table.name))
    if mismatch:
        # Include only table names; never print connection URLs, rows or passwords.
        raise RuntimeError(f'Existing table {table.name} differs from the initial schema; review it before migrating')
