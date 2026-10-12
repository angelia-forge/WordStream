"""Add study state and retained learning events.

Revision ID: 20261012_0004
Revises: 20261012_0003
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261012_0004"
down_revision: str | None = "20261012_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "study_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vocabulary_id", sa.Integer(), nullable=False),
        sa.Column("daily_new_limit", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "daily_new_limit > 0",
            name="ck_study_plans_daily_new_limit_positive",
        ),
        sa.ForeignKeyConstraint(
            ["vocabulary_id"],
            ["vocabularies.id"],
            name="fk_study_plans_vocabulary_id_vocabularies",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_study_plans"),
        sa.UniqueConstraint(
            "vocabulary_id",
            name="uq_study_plans_vocabulary_id",
        ),
    )
    op.create_table(
        "review_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("box_number", sa.Integer(), nullable=False),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "box_number >= 1 AND box_number <= 5",
            name="ck_review_states_box_number_range",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["entries.id"],
            name="fk_review_states_entry_id_entries",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_states"),
        sa.UniqueConstraint("entry_id", name="uq_review_states_entry_id"),
    )
    op.create_table(
        "learning_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=True),
        sa.Column("term_key", sa.String(length=500), nullable=False),
        sa.Column("term_snapshot", sa.String(length=500), nullable=False),
        sa.Column("vocabulary_id_snapshot", sa.Integer(), nullable=False),
        sa.Column(
            "vocabulary_name_snapshot",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.CheckConstraint(
            "attempts > 0",
            name="ck_learning_events_attempts_positive",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["entries.id"],
            name="fk_learning_events_entry_id_entries",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_learning_events"),
    )
    op.create_index(
        "ix_learning_events_activity_date",
        "learning_events",
        ["activity_date"],
    )
    op.create_index(
        "ix_learning_events_entry_id",
        "learning_events",
        ["entry_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_learning_events_entry_id", table_name="learning_events")
    op.drop_index(
        "ix_learning_events_activity_date",
        table_name="learning_events",
    )
    op.drop_table("learning_events")
    op.drop_table("review_states")
    op.drop_table("study_plans")
