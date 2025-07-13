"""Add 'updated_at' column to posts table

Revision ID: 9d6d12885b93
Revises: 1233ab03841b  # or your actual last revision ID
Create Date: 2025-07-13 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9d6d12885b93'
down_revision = '1233ab03841b'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('posts', sa.Column('updated_at', sa.DateTime(), nullable=True))

def downgrade():
    op.drop_column('posts', 'updated_at')
