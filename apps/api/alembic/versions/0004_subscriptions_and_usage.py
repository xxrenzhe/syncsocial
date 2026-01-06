"""subscriptions and usage

Revision ID: 0004_subscriptions_and_usage
Revises: 0003_strategy_schedule_runs
Create Date: 2026-01-06

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_subscriptions_and_usage"
down_revision = "0003_strategy_schedule_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="trial"),
        sa.Column("plan_key", sa.String(length=64), nullable=False, server_default="trial"),
        sa.Column("seats", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_social_accounts", sa.Integer(), nullable=True),
        sa.Column("max_parallel_sessions", sa.Integer(), nullable=True),
        sa.Column("automation_runtime_hours", sa.Integer(), nullable=True),
        sa.Column("artifact_retention_days", sa.Integer(), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id"),
    )
    op.create_index(op.f("ix_workspace_subscriptions_workspace_id"), "workspace_subscriptions", ["workspace_id"], unique=False)

    op.create_table(
        "workspace_usage_monthly",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("automation_runtime_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "period_start"),
    )
    op.create_index(op.f("ix_workspace_usage_monthly_period_start"), "workspace_usage_monthly", ["period_start"], unique=False)
    op.create_index(op.f("ix_workspace_usage_monthly_workspace_id"), "workspace_usage_monthly", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_workspace_usage_monthly_workspace_id"), table_name="workspace_usage_monthly")
    op.drop_index(op.f("ix_workspace_usage_monthly_period_start"), table_name="workspace_usage_monthly")
    op.drop_table("workspace_usage_monthly")

    op.drop_index(op.f("ix_workspace_subscriptions_workspace_id"), table_name="workspace_subscriptions")
    op.drop_table("workspace_subscriptions")

