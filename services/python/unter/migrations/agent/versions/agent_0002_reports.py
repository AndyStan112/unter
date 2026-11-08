"""Reports, their settings and an outbox for report.ready events.

report_settings sits next to schedule (which keeps cron, timezone and enabled) instead of adding
columns to it, so existing schedule rows are untouched.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = 'agent_0002'
down_revision = 'agent_0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('report_settings',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=False),
        sa.Column('window_hours', sa.Integer, nullable=False, server_default='24'),
        sa.Column('recipients', ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.CheckConstraint('id = 1', name='report_settings_id_check'),
        sa.CheckConstraint('window_hours BETWEEN 1 AND 168', name='report_settings_window_check'),
    )
    op.execute('INSERT INTO report_settings (id) VALUES (1) ON CONFLICT DO NOTHING')
    op.create_table('reports',
        sa.Column('id', UUID, primary_key=True),
        sa.Column('run_id', UUID, sa.ForeignKey('runs.id'), nullable=False, unique=True),
        sa.Column('window_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('window_to', sa.DateTime(timezone=True), nullable=False),
        sa.Column('report', JSONB, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('reports_created_at', 'reports', [sa.text('created_at DESC')])
    # Same pattern as core.outbox: written in the report's transaction, published afterwards.
    op.create_table('agent_outbox',
        sa.Column('id', UUID, primary_key=True),
        sa.Column('seq', sa.BigInteger, sa.Identity(), nullable=False, unique=True),
        sa.Column('kind', sa.Text, nullable=False),
        sa.Column('payload', JSONB, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('sent', sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index('agent_outbox_unsent', 'agent_outbox', ['seq'], postgresql_where=sa.text('NOT sent'))


def downgrade():
    op.drop_table('agent_outbox')
    op.drop_table('reports')
    op.drop_table('report_settings')
