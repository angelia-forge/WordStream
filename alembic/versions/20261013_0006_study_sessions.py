"""Add resumable study sessions and attempts.

Revision ID: 20261013_0006
Revises: 20261013_0005
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261013_0006"
down_revision: str | None = "20261013_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "study_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("vocabulary_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_index", sa.Integer(), nullable=False),
        sa.Column("plan_snapshot", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "current_index >= 0",
            name="ck_study_sessions_current_index_non_negative",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'finished', 'abandoned')",
            name="ck_study_sessions_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["study_plans.id"],
            name="fk_study_sessions_plan_id_study_plans",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["vocabulary_id"],
            ["vocabularies.id"],
            name="fk_study_sessions_vocabulary_id_vocabularies",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_study_sessions"),
    )
    op.create_index(
        "ix_study_sessions_vocabulary_id",
        "study_sessions",
        ["vocabulary_id"],
    )
    op.create_index(
        "uq_study_sessions_active_vocabulary",
        "study_sessions",
        ["vocabulary_id"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "session_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("entry_snapshot", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_session_items_attempt_count_non_negative",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_session_items_position_non_negative",
        ),
        sa.CheckConstraint(
            "result IS NULL OR result IN ('seen', 'again')",
            name="ck_session_items_result_allowed",
        ),
        sa.CheckConstraint(
            "source IN ('review', 'new')",
            name="ck_session_items_source_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["entries.id"],
            name="fk_session_items_entry_id_entries",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["study_sessions.id"],
            name="fk_session_items_session_id_study_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_session_items"),
    )
    op.create_index(
        "ix_session_items_session_position",
        "session_items",
        ["session_id", "position"],
    )

    op.create_table(
        "session_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_item_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('seen', 'again', 'replayed')",
            name="ck_session_attempts_action_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["session_item_id"],
            ["session_items.id"],
            name="fk_session_attempts_session_item_id_session_items",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_session_attempts"),
    )
    op.create_index(
        "ix_session_attempts_session_item_id",
        "session_attempts",
        ["session_item_id"],
    )

    with op.batch_alter_table("learning_events") as batch_op:
        batch_op.add_column(
            sa.Column("session_item_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_learning_events_session_item_id_session_items",
            "session_items",
            ["session_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_learning_events_session_item_id",
            ["session_item_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("learning_events") as batch_op:
        batch_op.drop_constraint(
            "uq_learning_events_session_item_id",
            type_="unique",
        )
        batch_op.drop_constraint(
            "fk_learning_events_session_item_id_session_items",
            type_="foreignkey",
        )
        batch_op.drop_column("session_item_id")

    op.drop_index(
        "ix_session_attempts_session_item_id",
        table_name="session_attempts",
    )
    op.drop_table("session_attempts")
    op.drop_index(
        "ix_session_items_session_position",
        table_name="session_items",
    )
    op.drop_table("session_items")
    op.drop_index(
        "uq_study_sessions_active_vocabulary",
        table_name="study_sessions",
    )
    op.drop_index(
        "ix_study_sessions_vocabulary_id",
        table_name="study_sessions",
    )
    op.drop_table("study_sessions")
