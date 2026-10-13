"""Expand study plan configuration.

Revision ID: 20261013_0005
Revises: 20261012_0004
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261013_0005"
down_revision: str | None = "20261012_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("study_plans") as batch_op:
        batch_op.drop_constraint(
            "ck_study_plans_daily_new_limit_positive",
            type_="check",
        )
        batch_op.alter_column(
            "daily_new_limit",
            new_column_name="daily_new_count",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.add_column(
            sa.Column(
                "daily_review_count",
                sa.Integer(),
                nullable=False,
                server_default="20",
            )
        )
        batch_op.add_column(
            sa.Column(
                "interval_seconds",
                sa.Integer(),
                nullable=False,
                server_default="5",
            )
        )
        batch_op.add_column(
            sa.Column(
                "is_random",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "is_loop",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            )
        )
        batch_op.create_check_constraint(
            "ck_study_plans_daily_new_count_range",
            "daily_new_count >= 0 AND daily_new_count <= 500",
        )
        batch_op.create_check_constraint(
            "ck_study_plans_daily_review_count_range",
            "daily_review_count >= 0 AND daily_review_count <= 500",
        )
        batch_op.create_check_constraint(
            "ck_study_plans_interval_seconds_range",
            "interval_seconds >= 1 AND interval_seconds <= 10",
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE study_plans SET daily_new_count = 1 " "WHERE daily_new_count = 0"
        )
    )
    with op.batch_alter_table("study_plans") as batch_op:
        batch_op.drop_constraint(
            "ck_study_plans_interval_seconds_range",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_study_plans_daily_review_count_range",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_study_plans_daily_new_count_range",
            type_="check",
        )
        batch_op.drop_column("updated_at")
        batch_op.drop_column("is_loop")
        batch_op.drop_column("is_random")
        batch_op.drop_column("interval_seconds")
        batch_op.drop_column("daily_review_count")
        batch_op.alter_column(
            "daily_new_count",
            new_column_name="daily_new_limit",
            existing_type=sa.Integer(),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_study_plans_daily_new_limit_positive",
            "daily_new_limit > 0",
        )
