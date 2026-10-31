"""Track the original agent schema, preserving existing schedules and runs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from unter.migrations.baseline import ensure_initial_table

revision = 'agent_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    metadata = sa.MetaData()
    ensure_initial_table(sa.Table('schedule', metadata,
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=False),
        sa.Column('cron', sa.Text, nullable=False),
        sa.Column('timezone', sa.Text, nullable=False),
        sa.Column('enabled', sa.Boolean, nullable=False),
        sa.Column('next_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('id = 1', name='schedule_id_check'),
    ))
    ensure_initial_table(sa.Table('runs', metadata,
        sa.Column('id', UUID, primary_key=True),
        sa.Column('source', sa.Text, nullable=False),
        sa.Column('status', sa.Text, nullable=False),
        sa.Column('mode', sa.Text, nullable=False),
        sa.Column('model', sa.Text, nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.Column('result', sa.Text), sa.Column('error', sa.Text),
        sa.Column('tool_calls', JSONB),
    ))


def downgrade():
    op.drop_table('runs')
    op.drop_table('schedule')
