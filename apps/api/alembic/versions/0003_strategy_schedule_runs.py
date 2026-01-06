"""strategy schedule runs

Revision ID: 0003_strategy_schedule_runs
Revises: 0002_social_accounts_and_login_sessions
Create Date: 2026-01-06

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003_strategy_schedule_runs"
down_revision = "0002_social_accounts_and_login_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("platform_key", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_strategies_platform_key"), "strategies", ["platform_key"], unique=False)
    op.create_index(op.f("ix_strategies_workspace_id"), "strategies", ["workspace_id"], unique=False)

    op.create_table(
        "schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("account_selector", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("frequency", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column("schedule_spec", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("random_config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("max_parallel", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_schedules_strategy_id"), "schedules", ["strategy_id"], unique=False)
    op.create_index(op.f("ix_schedules_workspace_id"), "schedules", ["workspace_id"], unique=False)

    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=True),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("triggered_by", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["triggered_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_runs_schedule_id"), "runs", ["schedule_id"], unique=False)
    op.create_index(op.f("ix_runs_status"), "runs", ["status"], unique=False)
    op.create_index(op.f("ix_runs_strategy_id"), "runs", ["strategy_id"], unique=False)
    op.create_index(op.f("ix_runs_triggered_by"), "runs", ["triggered_by"], unique=False)
    op.create_index(op.f("ix_runs_workspace_id"), "runs", ["workspace_id"], unique=False)

    op.create_table(
        "account_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("social_account_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["social_account_id"], ["social_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_account_runs_run_id"), "account_runs", ["run_id"], unique=False)
    op.create_index(op.f("ix_account_runs_social_account_id"), "account_runs", ["social_account_id"], unique=False)
    op.create_index(op.f("ix_account_runs_status"), "account_runs", ["status"], unique=False)
    op.create_index(op.f("ix_account_runs_workspace_id"), "account_runs", ["workspace_id"], unique=False)

    op.create_table(
        "actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("account_run_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("platform_key", sa.String(length=32), nullable=False),
        sa.Column("target_external_id", sa.String(length=200), nullable=True),
        sa.Column("target_url", sa.String(length=1000), nullable=True),
        sa.Column("idempotency_key", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_run_id"], ["account_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "idempotency_key"),
    )
    op.create_index(op.f("ix_actions_account_run_id"), "actions", ["account_run_id"], unique=False)
    op.create_index(op.f("ix_actions_action_type"), "actions", ["action_type"], unique=False)
    op.create_index(op.f("ix_actions_platform_key"), "actions", ["platform_key"], unique=False)
    op.create_index(op.f("ix_actions_status"), "actions", ["status"], unique=False)
    op.create_index(op.f("ix_actions_workspace_id"), "actions", ["workspace_id"], unique=False)

    op.create_table(
        "artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.String(length=1000), nullable=False),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["action_id"], ["actions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_artifacts_action_id"), "artifacts", ["action_id"], unique=False)
    op.create_index(op.f("ix_artifacts_type"), "artifacts", ["type"], unique=False)
    op.create_index(op.f("ix_artifacts_workspace_id"), "artifacts", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_artifacts_workspace_id"), table_name="artifacts")
    op.drop_index(op.f("ix_artifacts_type"), table_name="artifacts")
    op.drop_index(op.f("ix_artifacts_action_id"), table_name="artifacts")
    op.drop_table("artifacts")

    op.drop_index(op.f("ix_actions_workspace_id"), table_name="actions")
    op.drop_index(op.f("ix_actions_status"), table_name="actions")
    op.drop_index(op.f("ix_actions_platform_key"), table_name="actions")
    op.drop_index(op.f("ix_actions_action_type"), table_name="actions")
    op.drop_index(op.f("ix_actions_account_run_id"), table_name="actions")
    op.drop_table("actions")

    op.drop_index(op.f("ix_account_runs_workspace_id"), table_name="account_runs")
    op.drop_index(op.f("ix_account_runs_status"), table_name="account_runs")
    op.drop_index(op.f("ix_account_runs_social_account_id"), table_name="account_runs")
    op.drop_index(op.f("ix_account_runs_run_id"), table_name="account_runs")
    op.drop_table("account_runs")

    op.drop_index(op.f("ix_runs_workspace_id"), table_name="runs")
    op.drop_index(op.f("ix_runs_triggered_by"), table_name="runs")
    op.drop_index(op.f("ix_runs_strategy_id"), table_name="runs")
    op.drop_index(op.f("ix_runs_status"), table_name="runs")
    op.drop_index(op.f("ix_runs_schedule_id"), table_name="runs")
    op.drop_table("runs")

    op.drop_index(op.f("ix_schedules_workspace_id"), table_name="schedules")
    op.drop_index(op.f("ix_schedules_strategy_id"), table_name="schedules")
    op.drop_table("schedules")

    op.drop_index(op.f("ix_strategies_workspace_id"), table_name="strategies")
    op.drop_index(op.f("ix_strategies_platform_key"), table_name="strategies")
    op.drop_table("strategies")

