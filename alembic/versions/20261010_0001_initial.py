"""Create the initial settings schema.

Revision ID: 20261010_0001
Revises:
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261010_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("tts_rate", sa.Float(), nullable=False),
        sa.Column("default_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("daily_goal", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_app_settings_singleton_id"),
        sa.CheckConstraint(
            "tts_rate >= 0.5 AND tts_rate <= 2.0",
            name="ck_app_settings_tts_rate",
        ),
        sa.CheckConstraint(
            "default_interval_seconds >= 2 AND default_interval_seconds <= 60",
            name="ck_app_settings_default_interval",
        ),
        sa.CheckConstraint(
            "daily_goal >= 0 AND daily_goal <= 500",
            name="ck_app_settings_daily_goal",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_app_settings"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
