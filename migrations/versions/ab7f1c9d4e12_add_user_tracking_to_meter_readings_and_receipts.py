"""add user tracking to meter readings and receipts

Revision ID: ab7f1c9d4e12
Revises: 9f10845ac021
Create Date: 2026-07-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ab7f1c9d4e12'
down_revision = '9f10845ac021'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('meter_readings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('recorded_by_user_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_meter_readings_recorded_by_user_id'), ['recorded_by_user_id'], unique=False)
        batch_op.create_foreign_key(None, 'users', ['recorded_by_user_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('receipts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('received_by_user_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_receipts_received_by_user_id'), ['received_by_user_id'], unique=False)
        batch_op.create_foreign_key(None, 'users', ['received_by_user_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('receipts', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_receipts_received_by_user_id'))
        batch_op.drop_column('received_by_user_id')

    with op.batch_alter_table('meter_readings', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_meter_readings_recorded_by_user_id'))
        batch_op.drop_column('recorded_by_user_id')
