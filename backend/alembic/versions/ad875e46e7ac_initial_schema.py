"""initial_schema

Revision ID: ad875e46e7ac
Revises:
Create Date: 2026-09-29

Creates:
    repositories  — root entity, one per analysed repo
    files         — source files belonging to a repository
    symbols       — named code elements (class/function/method/…) inside a file
    relationships — directed edges between symbols (CALLS/IMPORTS/INHERITS/…)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "ad875e46e7ac"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # repositories
    # ------------------------------------------------------------------
    op.create_table(
        "repositories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("local_path", sa.String(length=4096), nullable=True),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default="pending",
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------
    # files
    # ------------------------------------------------------------------
    op.create_table(
        "files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.String(length=4096), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repository_id", "path", name="uq_files_repository_path"),
    )
    op.create_index("ix_files_repository_id", "files", ["repository_id"])

    # ------------------------------------------------------------------
    # symbols
    # ------------------------------------------------------------------
    op.create_table(
        "symbols",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("qualified_name", sa.String(length=1024), nullable=False),
        sa.Column("symbol_type", sa.String(length=50), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("docstring", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_symbols_file_id", "symbols", ["file_id"])
    op.create_index("ix_symbols_qualified_name", "symbols", ["qualified_name"])

    # ------------------------------------------------------------------
    # relationships
    # ------------------------------------------------------------------
    op.create_table(
        "relationships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("source_symbol_id", sa.Uuid(), nullable=False),
        sa.Column("target_symbol_id", sa.Uuid(), nullable=False),
        sa.Column("relationship_type", sa.String(length=50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"], ["repositories.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_symbol_id"], ["symbols.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_symbol_id"], ["symbols.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_relationships_repository_id", "relationships", ["repository_id"])
    op.create_index("ix_relationships_source_symbol_id", "relationships", ["source_symbol_id"])
    op.create_index("ix_relationships_target_symbol_id", "relationships", ["target_symbol_id"])


def downgrade() -> None:
    op.drop_index("ix_relationships_target_symbol_id", table_name="relationships")
    op.drop_index("ix_relationships_source_symbol_id", table_name="relationships")
    op.drop_index("ix_relationships_repository_id", table_name="relationships")
    op.drop_table("relationships")

    op.drop_index("ix_symbols_qualified_name", table_name="symbols")
    op.drop_index("ix_symbols_file_id", table_name="symbols")
    op.drop_table("symbols")

    op.drop_index("ix_files_repository_id", table_name="files")
    op.drop_table("files")

    op.drop_table("repositories")
