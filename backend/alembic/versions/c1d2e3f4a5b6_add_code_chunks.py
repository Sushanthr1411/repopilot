"""add_code_chunks

Revision ID: c1d2e3f4a5b6
Revises: ad875e46e7ac
Create Date: 2026-09-29

Adds:
    code_chunks — searchable code excerpts produced by the chunker.
                  PostgreSQL stores source content + metadata.
                  ChromaDB stores the embedding vectors.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "ad875e46e7ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "code_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("symbol_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"], ["repositories.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["symbol_id"], ["symbols.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_chunks_repository_id", "code_chunks", ["repository_id"])
    op.create_index("ix_code_chunks_file_id", "code_chunks", ["file_id"])
    op.create_index("ix_code_chunks_symbol_id", "code_chunks", ["symbol_id"])


def downgrade() -> None:
    op.drop_index("ix_code_chunks_symbol_id", table_name="code_chunks")
    op.drop_index("ix_code_chunks_file_id", table_name="code_chunks")
    op.drop_index("ix_code_chunks_repository_id", table_name="code_chunks")
    op.drop_table("code_chunks")
