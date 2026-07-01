"""add created dates for report filters

Revision ID: 9f10845ac021
Revises: 2dfb29089c6c
Create Date: 2026-06-30 17:10:35.048722

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9f10845ac021'
down_revision = '2dfb29089c6c'
branch_labels = None
depends_on = None


def upgrade():
    # Add columns as nullable, backfill existing rows, then make them required.
    with op.batch_alter_table('service_areas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_date', sa.Date(), nullable=True))

    op.execute(sa.text("UPDATE service_areas SET created_date = CURDATE() WHERE created_date IS NULL"))

    with op.batch_alter_table('service_areas', schema=None) as batch_op:
        batch_op.alter_column('created_date', existing_type=sa.Date(), nullable=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_date', sa.Date(), nullable=True))

    op.execute(sa.text("UPDATE users SET created_date = CURDATE() WHERE created_date IS NULL"))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('created_date', existing_type=sa.Date(), nullable=False)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('created_date')

    with op.batch_alter_table('service_areas', schema=None) as batch_op:
        batch_op.drop_column('created_date')
