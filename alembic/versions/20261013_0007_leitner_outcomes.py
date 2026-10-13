"""Add idempotent outcomes and zero-based Leitner boxes.

Revision ID: 20261013_0007
Revises: 20261013_0006
Create Date: 2026-10-13
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "20261013_0007"
down_revision: str | None = "20261013_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE review_states SET box_number = box_number - 1"))
    with op.batch_alter_table("review_states") as batch_op:
        batch_op.drop_constraint(
            "ck_review_states_box_number_range",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_review_states_box_number_range",
            "box_number >= 0 AND box_number <= 4",
        )
        batch_op.alter_column(
            "box_number",
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default="0",
        )

    with op.batch_alter_table("learning_events") as batch_op:
        batch_op.drop_constraint(
            "ck_learning_events_attempts_positive",
            type_="check",
        )
        batch_op.alter_column(
            "attempts",
            new_column_name="attempt_count",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "received_at",
            new_column_name="created_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
        )
        batch_op.add_column(
            sa.Column("client_event_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("client_attempt_count", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("vocabulary_snapshot", sa.JSON(), nullable=True))

    events = sa.table(
        "learning_events",
        sa.column("id", sa.Integer()),
        sa.column("client_event_id", sa.String()),
        sa.column("attempt_count", sa.Integer()),
        sa.column("client_attempt_count", sa.Integer()),
        sa.column("vocabulary_id_snapshot", sa.Integer()),
        sa.column("vocabulary_name_snapshot", sa.String()),
        sa.column("vocabulary_snapshot", sa.JSON()),
        sa.column("result", sa.String()),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(
            events.c.id,
            events.c.attempt_count,
            events.c.vocabulary_id_snapshot,
            events.c.vocabulary_name_snapshot,
            events.c.result,
        )
    ).mappings()
    for row in rows:
        connection.execute(
            events.update()
            .where(events.c.id == row["id"])
            .values(
                client_event_id=str(uuid4()),
                client_attempt_count=row["attempt_count"],
                vocabulary_snapshot={
                    "id": row["vocabulary_id_snapshot"],
                    "name": row["vocabulary_name_snapshot"],
                },
                result=(
                    row["result"] if row["result"] in {"seen", "again"} else "seen"
                ),
            )
        )

    with op.batch_alter_table("learning_events") as batch_op:
        batch_op.alter_column(
            "client_event_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch_op.alter_column(
            "client_attempt_count",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "vocabulary_snapshot",
            existing_type=sa.JSON(),
            nullable=False,
        )
        batch_op.drop_column("vocabulary_name_snapshot")
        batch_op.drop_column("vocabulary_id_snapshot")
        batch_op.create_unique_constraint(
            "uq_learning_events_client_event_id",
            ["client_event_id"],
        )
        batch_op.create_check_constraint(
            "ck_learning_events_result_allowed",
            "result IN ('seen', 'again')",
        )
        batch_op.create_check_constraint(
            "ck_learning_events_attempt_count_positive",
            "attempt_count > 0",
        )
        batch_op.create_check_constraint(
            "ck_learning_events_client_attempt_count_positive",
            "client_attempt_count > 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("learning_events") as batch_op:
        batch_op.drop_constraint(
            "ck_learning_events_client_attempt_count_positive",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_learning_events_attempt_count_positive",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_learning_events_result_allowed",
            type_="check",
        )
        batch_op.drop_constraint(
            "uq_learning_events_client_event_id",
            type_="unique",
        )
        batch_op.add_column(
            sa.Column("vocabulary_id_snapshot", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "vocabulary_name_snapshot",
                sa.String(length=200),
                nullable=True,
            )
        )

    events = sa.table(
        "learning_events",
        sa.column("id", sa.Integer()),
        sa.column("vocabulary_snapshot", sa.JSON()),
        sa.column("vocabulary_id_snapshot", sa.Integer()),
        sa.column("vocabulary_name_snapshot", sa.String()),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(events.c.id, events.c.vocabulary_snapshot)
    ).mappings()
    for row in rows:
        snapshot = row["vocabulary_snapshot"]
        connection.execute(
            events.update()
            .where(events.c.id == row["id"])
            .values(
                vocabulary_id_snapshot=snapshot["id"],
                vocabulary_name_snapshot=snapshot["name"],
            )
        )

    with op.batch_alter_table("learning_events") as batch_op:
        batch_op.alter_column(
            "vocabulary_id_snapshot",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.alter_column(
            "vocabulary_name_snapshot",
            existing_type=sa.String(length=200),
            nullable=False,
        )
        batch_op.drop_column("vocabulary_snapshot")
        batch_op.drop_column("client_attempt_count")
        batch_op.drop_column("client_event_id")
        batch_op.alter_column(
            "created_at",
            new_column_name="received_at",
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "attempt_count",
            new_column_name="attempts",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_learning_events_attempts_positive",
            "attempts > 0",
        )

    op.execute(sa.text("UPDATE review_states SET box_number = box_number + 1"))
    with op.batch_alter_table("review_states") as batch_op:
        batch_op.drop_constraint(
            "ck_review_states_box_number_range",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_review_states_box_number_range",
            "box_number >= 1 AND box_number <= 5",
        )
        batch_op.alter_column(
            "box_number",
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default="1",
        )
