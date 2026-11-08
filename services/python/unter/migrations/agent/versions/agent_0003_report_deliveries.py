"""Email delivery state per report, written by the mailer and shown with the report.

No foreign key to reports: the mailer must be able to record the outcome of any report.ready it
receives, so a bad message is parked instead of failing forever.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'agent_0003'
down_revision = 'agent_0002'
branch_labels = None
depends_on = None

STATUSES = ('sending', 'sent', 'failed', 'parked', 'skipped', 'not_configured')


def upgrade():
    op.create_table('report_deliveries',
        sa.Column('report_id', UUID, primary_key=True),
        sa.Column('status', sa.Text, nullable=False),
        sa.Column('attempts', sa.Integer, nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('sent_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint('status IN (' + ', '.join(f"'{s}'" for s in STATUSES) + ')',
                           name='report_deliveries_status_check'),
    )


def downgrade():
    op.drop_table('report_deliveries')
