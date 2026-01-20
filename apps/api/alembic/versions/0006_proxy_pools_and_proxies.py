"""proxy pools and proxies

Revision ID: 0006_proxy_pools_and_proxies
Revises: 0005_social_account_fingerprint_profile
Create Date: 2026-01-16

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_proxy_pools_and_proxies"
down_revision = "0005_social_account_fingerprint_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proxy_pools",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("strategy", sa.String(length=32), nullable=False, server_default="hash"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_proxy_pools_workspace_id", "proxy_pools", ["workspace_id"])

    op.create_table(
        "proxies",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.Uuid(), sa.ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("pool_id", sa.Uuid(), sa.ForeignKey("proxy_pools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheme", sa.String(length=16), nullable=False, server_default="http"),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("auth_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_proxies_workspace_id", "proxies", ["workspace_id"])
    op.create_index("ix_proxies_pool_id", "proxies", ["pool_id"])

    with op.batch_alter_table("social_accounts") as batch_op:
        batch_op.add_column(sa.Column("proxy_pool_id", sa.Uuid(), nullable=True))
        batch_op.create_index("ix_social_accounts_proxy_pool_id", ["proxy_pool_id"])
        batch_op.create_foreign_key(
            "fk_social_accounts_proxy_pool_id",
            "proxy_pools",
            ["proxy_pool_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("social_accounts") as batch_op:
        batch_op.drop_constraint("fk_social_accounts_proxy_pool_id", type_="foreignkey")
        batch_op.drop_index("ix_social_accounts_proxy_pool_id")
        batch_op.drop_column("proxy_pool_id")

    op.drop_index("ix_proxies_pool_id", table_name="proxies")
    op.drop_index("ix_proxies_workspace_id", table_name="proxies")
    op.drop_table("proxies")

    op.drop_index("ix_proxy_pools_workspace_id", table_name="proxy_pools")
    op.drop_table("proxy_pools")
