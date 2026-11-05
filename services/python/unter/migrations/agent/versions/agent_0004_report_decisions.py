"""What an operator decided about each reported proposal.

One row per (report, proposal). The row is claimed before core is called, so two clicks can't
approve the same proposal twice. status: applying -> applied (core rule created and approved),
created (core proposal created but its approval failed), or rejected (core isn't called).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'agent_0004'
down_revision = 'agent_0003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('report_decisions',
        sa.Column('report_id', UUID, sa.ForeignKey('reports.id'), primary_key=True),
        sa.Column('proposal_id', sa.Text, primary_key=True),
        sa.Column('status', sa.Text, nullable=False),
        sa.Column('core_proposal_id', UUID),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint("status IN ('applying', 'applied', 'created', 'rejected')", name='report_decisions_status_check'),
    )


def downgrade():
    op.drop_table('report_decisions')
