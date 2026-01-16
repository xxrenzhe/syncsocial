"""account run retries

Revision ID: 0007_account_run_retries
Revises: 0006_proxy_pools_and_proxies
Create Date: 2026-01-16

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_account_run_retries"
down_revision = "0006_proxy_pools_and_proxies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("account_runs", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("account_runs", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_account_runs_next_retry_at", "account_runs", ["next_retry_at"])


def downgrade() -> None:
    op.drop_index("ix_account_runs_next_retry_at", table_name="account_runs")
    op.drop_column("account_runs", "next_retry_at")
    op.drop_column("account_runs", "retry_count")

