"""Add 'updated_at' column to posts table

Revision ID: 9d6d12885b93
Revises: 1233ab03841b  # or your actual last revision ID
Create Date: 2025-07-13 14:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, Column, DateTime

# revision identifiers, used by Alembic.
revision = "9d6d12885b93"
down_revision = "1233ab03841b"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "updated_at" not in {c["name"] for c in inspect(bind).get_columns("posts")}:
        op.add_column("posts", Column("updated_at", DateTime(), nullable=True))


def downgrade():
    op.drop_column("posts", "updated_at")
