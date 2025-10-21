"""create customers table"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c0577aebce13"
down_revision = "9e3b5b5d4ffd"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.String(length=32), nullable=False),      # unique business ID
        sa.Column("customer_name", sa.String(length=120), nullable=False),
        sa.Column("customer_type", sa.String(length=32), nullable=False),
        sa.Column("address", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),

        sa.Column("service_area_id", sa.Integer(), nullable=False),
        sa.Column("supply_line_id", sa.Integer(), nullable=False),

        # IMPORTANT: no server_default=sa.text('CURRENT_DATE') for MySQL DATE
        sa.Column("created_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),

        sa.ForeignKeyConstraint(["service_area_id"], ["service_areas.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supply_line_id"], ["pipelines.id"], ondelete="RESTRICT"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )

    # Indexes (run AFTER table is created)
    op.create_index("ix_customers_customer_id", "customers", ["customer_id"], unique=True)
    op.create_index("ix_customers_service_area_id", "customers", ["service_area_id"])
    op.create_index("ix_customers_supply_line_id", "customers", ["supply_line_id"])


def downgrade():
    # Drop indexes first (safe order), then table
    op.drop_index("ix_customers_supply_line_id", table_name="customers")
    op.drop_index("ix_customers_service_area_id", table_name="customers")
    op.drop_index("ix_customers_customer_id", table_name="customers")
    op.drop_table("customers")