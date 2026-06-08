"""add research_notes table

Revision ID: 004_research_notes
Revises: 003_job_runs
"""
from alembic import op
import sqlalchemy as sa

revision = "004_research_notes"
down_revision = "003_job_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_notes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False, server_default="default"),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("note_type", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("paper_id", sa.Integer(), nullable=True),
        sa.Column("chunk_id", sa.Integer(), nullable=True),
        sa.Column("source_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("tags", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["chunk_id"], ["paper_chunks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_notes_user_id", "research_notes", ["user_id"])
    op.create_index("ix_research_notes_paper_id", "research_notes", ["paper_id"])
    op.create_index("ix_research_notes_chunk_id", "research_notes", ["chunk_id"])


def downgrade() -> None:
    op.drop_index("ix_research_notes_chunk_id", table_name="research_notes")
    op.drop_index("ix_research_notes_paper_id", table_name="research_notes")
    op.drop_index("ix_research_notes_user_id", table_name="research_notes")
    op.drop_table("research_notes")
