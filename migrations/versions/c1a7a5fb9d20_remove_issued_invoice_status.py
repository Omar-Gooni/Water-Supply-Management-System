"""remove issued invoice status

Revision ID: c1a7a5fb9d20
Revises: b830646bb08e
Create Date: 2026-07-05 12:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1a7a5fb9d20'
down_revision = 'b830646bb08e'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("UPDATE invoices SET status = 'unpaid' WHERE status = 'issued'"))


def downgrade():
    op.execute(sa.text("UPDATE invoices SET status = 'issued' WHERE status = 'unpaid'"))