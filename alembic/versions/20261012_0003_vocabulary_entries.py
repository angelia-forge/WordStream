"""Add vocabularies and entries.

Revision ID: 20261012_0003
Revises: 20261010_0002
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261012_0003"
down_revision: str | None = "20261010_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vocabularies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_vocabularies_name_not_empty",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_vocabularies"),
    )
    op.create_table(
        "entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vocabulary_id", sa.Integer(), nullable=False),
        sa.Column("term", sa.String(length=500), nullable=False),
        sa.Column("normalized_term", sa.String(length=500), nullable=False),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("meaning", sa.Text(), nullable=False),
        sa.Column("part_of_speech", sa.String(length=100), nullable=True),
        sa.Column("phonetic", sa.String(length=255), nullable=True),
        sa.Column("example", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entry_type IN ('word', 'phrase')",
            name="ck_entries_entry_type_allowed",
        ),
        sa.CheckConstraint(
            "length(trim(meaning)) > 0",
            name="ck_entries_meaning_not_empty",
        ),
        sa.CheckConstraint(
            "length(trim(normalized_term)) > 0",
            name="ck_entries_normalized_term_not_empty",
        ),
        sa.CheckConstraint(
            "length(trim(term)) > 0",
            name="ck_entries_term_not_empty",
        ),
        sa.ForeignKeyConstraint(
            ["vocabulary_id"],
            ["vocabularies.id"],
            name="fk_entries_vocabulary_id_vocabularies",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_entries"),
        sa.UniqueConstraint(
            "vocabulary_id",
            "normalized_term",
            name="uq_entries_vocabulary_normalized_term",
        ),
    )
    op.create_index(
        "ix_entries_vocabulary_created_at",
        "entries",
        ["vocabulary_id", "created_at"],
    )
    op.create_index(
        "ix_entries_vocabulary_term",
        "entries",
        ["vocabulary_id", "term"],
    )


def downgrade() -> None:
    op.drop_index("ix_entries_vocabulary_term", table_name="entries")
    op.drop_index("ix_entries_vocabulary_created_at", table_name="entries")
    op.drop_table("entries")
    op.drop_table("vocabularies")
