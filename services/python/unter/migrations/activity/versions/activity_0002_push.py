"""Persistent push identity, subscriptions and deduplicated delivery queue."""
from alembic import op

revision = 'activity_0002'
down_revision = 'activity_0001'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE TABLE push_identity (id integer PRIMARY KEY CHECK (id=1), private_key text NOT NULL, public_key text NOT NULL)')
    op.execute('''CREATE TABLE push_subscriptions (
        id uuid PRIMARY KEY, endpoint text NOT NULL UNIQUE, subscription jsonb NOT NULL,
        role text NOT NULL CHECK (role IN ('driver','passenger')), profile_id uuid NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now())''')
    op.execute('CREATE INDEX push_profile ON push_subscriptions(role,profile_id)')
    op.execute('''CREATE TABLE push_deliveries (
        event_id text NOT NULL, subscription_id uuid NOT NULL REFERENCES push_subscriptions(id) ON DELETE CASCADE,
        payload jsonb NOT NULL, expires_at timestamptz NOT NULL,
        attempts integer NOT NULL DEFAULT 0, next_attempt_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(event_id,subscription_id))''')


def downgrade():
    for table in ('push_deliveries', 'push_subscriptions', 'push_identity'):
        op.execute('DROP TABLE ' + table)
