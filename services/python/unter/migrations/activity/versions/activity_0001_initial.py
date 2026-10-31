"""Track the original worker schema while retaining the event feed."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from unter.migrations.baseline import ensure_initial_table

revision = 'activity_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    ensure_initial_table(sa.Table('activity', sa.MetaData(),
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('kind', sa.Text, nullable=False),
        sa.Column('payload', JSONB, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    ))


def downgrade():
    op.drop_table('activity')
