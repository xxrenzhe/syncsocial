"""init auth tables

Revision ID: 0001_init_auth_tables
Revises: 
Create Date: 2026-01-06

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0001_init_auth_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("password_hash", sa.String(length=500), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="user"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)
    op.create_index(op.f("ix_users_workspace_id"), "users", ["workspace_id"], unique=False)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_refresh_tokens_token_hash"), "refresh_tokens", ["token_hash"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=200), nullable=False),
        sa.Column("target_type", sa.String(length=100), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_audit_logs_actor_user_id"), "audit_logs", ["actor_user_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_workspace_id"), "audit_logs", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_logs_workspace_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_user_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_token_hash"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index(op.f("ix_users_workspace_id"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    op.drop_table("workspaces")
