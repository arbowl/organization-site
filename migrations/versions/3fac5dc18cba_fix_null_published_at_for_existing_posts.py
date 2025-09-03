"""fix_null_published_at_for_existing_posts

Revision ID: 3fac5dc18cba
Revises: 084e773361a0
Create Date: 2025-09-03 13:36:55.933930

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3fac5dc18cba'
down_revision = '084e773361a0'
branch_labels = None
depends_on = None


def upgrade():
    # Fix existing posts that have published_at = NULL but are not drafts
    # These posts were created directly (not as drafts) before published_at was properly set
    connection = op.get_bind()
    
    # Update posts where published_at is NULL and is_draft is False
    # Set published_at to timestamp (when the post was originally created)
    connection.execute(
        sa.text("""
            UPDATE posts 
            SET published_at = timestamp 
            WHERE published_at IS NULL 
            AND is_draft = FALSE
        """)
    )


def downgrade():
    # This migration is not easily reversible since we can't distinguish
    # between posts that originally had NULL published_at vs those that had it set
    # We'll leave the data as-is in case of rollback
    pass
