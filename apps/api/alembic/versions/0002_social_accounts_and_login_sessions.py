"""social accounts and login sessions

Revision ID: 0002_social_accounts_and_login_sessions
Revises: 0001_init_auth_tables
Create Date: 2026-01-06

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002_social_accounts_and_login_sessions"
down_revision = "0001_init_auth_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "social_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("platform_key", sa.String(length=32), nullable=False),
        sa.Column("handle", sa.String(length=200), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="needs_login"),
        sa.Column("labels", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_social_accounts_platform_key"), "social_accounts", ["platform_key"], unique=False)
    op.create_index(op.f("ix_social_accounts_workspace_id"), "social_accounts", ["workspace_id"], unique=False)

    op.create_table(
        "credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("social_account_id", sa.Uuid(), nullable=False),
        sa.Column("credential_type", sa.String(length=32), nullable=False),
        sa.Column("encrypted_blob", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_hint", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["social_account_id"], ["social_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("social_account_id", "credential_type"),
    )
    op.create_index(op.f("ix_credentials_credential_type"), "credentials", ["credential_type"], unique=False)
    op.create_index(op.f("ix_credentials_social_account_id"), "credentials", ["social_account_id"], unique=False)
    op.create_index(op.f("ix_credentials_workspace_id"), "credentials", ["workspace_id"], unique=False)

    op.create_table(
        "login_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("social_account_id", sa.Uuid(), nullable=False),
        sa.Column("platform_key", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="created"),
        sa.Column("remote_url", sa.String(length=1000), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["social_account_id"], ["social_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_login_sessions_created_by"), "login_sessions", ["created_by"], unique=False)
    op.create_index(op.f("ix_login_sessions_platform_key"), "login_sessions", ["platform_key"], unique=False)
    op.create_index(op.f("ix_login_sessions_social_account_id"), "login_sessions", ["social_account_id"], unique=False)
    op.create_index(op.f("ix_login_sessions_status"), "login_sessions", ["status"], unique=False)
    op.create_index(op.f("ix_login_sessions_workspace_id"), "login_sessions", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_login_sessions_workspace_id"), table_name="login_sessions")
    op.drop_index(op.f("ix_login_sessions_status"), table_name="login_sessions")
    op.drop_index(op.f("ix_login_sessions_social_account_id"), table_name="login_sessions")
    op.drop_index(op.f("ix_login_sessions_platform_key"), table_name="login_sessions")
    op.drop_index(op.f("ix_login_sessions_created_by"), table_name="login_sessions")
    op.drop_table("login_sessions")

    op.drop_index(op.f("ix_credentials_workspace_id"), table_name="credentials")
    op.drop_index(op.f("ix_credentials_social_account_id"), table_name="credentials")
    op.drop_index(op.f("ix_credentials_credential_type"), table_name="credentials")
    op.drop_table("credentials")

    op.drop_index(op.f("ix_social_accounts_workspace_id"), table_name="social_accounts")
    op.drop_index(op.f("ix_social_accounts_platform_key"), table_name="social_accounts")
    op.drop_table("social_accounts")

