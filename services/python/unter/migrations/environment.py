"""Shared Alembic environment; each database retains its own revision chain."""
import os
from alembic import context
from sqlalchemy import URL, create_engine, text
from sqlalchemy.pool import NullPool


def run():
    if context.is_offline_mode():
        raise RuntimeError('These migrations require an online database to validate existing schemas')
    # URL.create avoids quoting/interpolation problems with arbitrary passwords.
    url = URL.create(
        'postgresql+psycopg', host=os.getenv('DB_HOST', 'postgres'),
        port=int(os.getenv('DB_PORT', '5432')), database=os.environ['DB_NAME'],
        username=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'],
    )
    engine = create_engine(url, poolclass=NullPool, hide_parameters=True,
                           connect_args={'connect_timeout': 10})
    try:
        with engine.begin() as connection:
            # Serialize version checks and DDL across simultaneous service starts.
            connection.execute(text('SET LOCAL lock_timeout = \'60s\''))
            connection.execute(text('SELECT pg_advisory_xact_lock(83113)'))
            context.configure(connection=connection, target_metadata=None,
                              compare_type=True, transactional_ddl=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
