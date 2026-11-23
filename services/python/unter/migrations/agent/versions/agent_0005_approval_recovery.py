"""Terminal application failures are visible and manually retriable, not retried forever."""
from alembic import op
import sqlalchemy as sa

revision = 'agent_0005'
down_revision = 'agent_0004'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('report_decisions_status_check', 'report_decisions', type_='check')
    op.create_check_constraint('report_decisions_status_check', 'report_decisions',
                               "status IN ('applying','applied','created','rejected','failed')")
    op.add_column('report_decisions', sa.Column('error', sa.Text))


def downgrade():
    op.execute("UPDATE report_decisions SET status='applying' WHERE status='failed'")
    op.drop_column('report_decisions', 'error')
    op.drop_constraint('report_decisions_status_check', 'report_decisions', type_='check')
    op.create_check_constraint('report_decisions_status_check', 'report_decisions',
                               "status IN ('applying','applied','created','rejected')")
