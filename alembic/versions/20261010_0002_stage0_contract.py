"""Align the Stage 0 settings contract.

Revision ID: 20261010_0002
Revises: 20261010_0001
Create Date: 2026-10-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261010_0002"
down_revision: str | None = "20261010_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("app_settings") as batch_op:
        batch_op.drop_constraint(
            "ck_app_settings_default_interval",
            type_="check",
        )
        batch_op.alter_column(
            "default_interval_seconds",
            new_column_name="default_interval",
        )
        batch_op.create_check_constraint(
            "ck_app_settings_default_interval",
            "default_interval >= 2 AND default_interval <= 60",
        )


def downgrade() -> None:
    with op.batch_alter_table("app_settings") as batch_op:
        batch_op.drop_constraint(
            "ck_app_settings_default_interval",
            type_="check",
        )
        batch_op.alter_column(
            "default_interval",
            new_column_name="default_interval_seconds",
        )
        batch_op.create_check_constraint(
            "ck_app_settings_default_interval",
            "default_interval_seconds >= 2 AND default_interval_seconds <= 60",
        )
